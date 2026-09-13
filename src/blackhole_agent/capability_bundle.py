"""Portable capability bundles: proved absorbed capabilities transfer between checkouts.

The compounded ledger's absorbed capabilities are invocable only in the
checkout that absorbed them: the proof record lives in ``capabilities/ledger.json``
and the vendored tool tree lives under ``capabilities/absorbed/<slug>/``, and
nothing moves the pair to another workspace. This module closes that gap with
a **capability bundle** — one self-contained, digest-sealed JSON artifact that
carries everything a bare checkout needs to serve the capability:

- ``export_capability_bundle`` collects the vendored tool tree (every file,
  base64-encoded, each with its sha256) plus the ledger registration record
  into a canonical payload and seals it with a ``bundle_digest`` — a sha256
  over the canonical payload. The seal is deterministic: exporting the same
  capability twice from the same tree yields the same digest.
- ``import_capability_bundle`` verifies the seal and every per-file digest
  *before writing anything*, refuses duplicate registrations and path
  traversal, and then **re-proves the capability in the target checkout**:
  the bundle is staged in a temporary sibling tree, its manifest is
  re-validated, and every frozen case is re-executed for real under the
  plane's governed resource bounds. Only when all cases pass does the staged
  tree move into ``capabilities/absorbed/<slug>/`` and the target ledger
  register the capability — proved status in the target is earned by local
  execution, not copied from the source ledger. A sealed-but-misbehaving
  bundle (valid digests, wrong behavior) is refused with a ``reproof_failed``
  verdict and the target is left exactly as it was.
- Imported capabilities are immediately invocable through the existing
  governed machinery (:func:`blackhole_agent.capability_service.invoke_capability`)
  — same scrubbed environment, same resource limits — because import
  reconstructs exactly the on-disk contract the plane already serves.
- Tampering fails closed: a flipped byte anywhere in the payload or file
  contents invalidates the seal or a per-file digest, and the import is
  refused with a ``tampered`` verdict before a single byte lands in the
  target checkout.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

from blackhole_agent.capability_absorption import load_manifest
from blackhole_agent.capability_compounder import atomic_write_json, utc_now_iso
from blackhole_agent.capability_service import (
    ABSORBED_ID_PREFIX,
    absorbed_root,
    _run_governed_case,
)
from blackhole_agent.process_capture import ResourceLimits

REPROOF_TIMEOUT_SECONDS = 30
REPROOF_LIMITS = ResourceLimits(
    memory_bytes=256 << 20,
    max_processes=32,
    cpu_seconds=25,
)

BUNDLE_SCHEMA_VERSION = 1
BUNDLE_KIND = "capability-bundle"
# Ledger entry fields copied verbatim into the bundle's registration record.
_ENTRY_FIELDS = (
    "name",
    "kind",
    "description",
    "dependencies",
    "tags",
    "capability_delta",
)


class BundleError(Exception):
    """Fail-closed bundle refusal; ``verdict`` is the machine-readable reason."""

    def __init__(self, verdict: str, detail: str) -> None:
        super().__init__(detail)
        self.verdict = verdict
        self.detail = detail


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _ledger_path(root: Path) -> Path:
    return root / "capabilities" / "ledger.json"


def _load_ledger_document(root: Path) -> dict[str, Any]:
    path = _ledger_path(root)
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"capabilities": {}, "schema_version": 1, "updated_at": ""}
    except json.JSONDecodeError as exc:
        raise BundleError("target_ledger_unreadable", f"target ledger is not valid JSON: {exc}")
    if not isinstance(document, dict) or not isinstance(document.get("capabilities"), dict):
        raise BundleError("target_ledger_unreadable", "target ledger has no capabilities object")
    return document


def _iter_tool_files(tool_root: Path) -> list[Path]:
    return sorted(path for path in tool_root.rglob("*") if path.is_file())


def export_capability_bundle(root: Path, capability_id: str, out_path: Path) -> dict[str, Any]:
    """Export one proved absorbed capability as a digest-sealed bundle file."""

    root = Path(root)
    document = _load_ledger_document(root)
    entry = document["capabilities"].get(capability_id)
    if not isinstance(entry, dict):
        raise BundleError("unknown_capability", f"unknown capability: {capability_id}")
    if not capability_id.startswith(ABSORBED_ID_PREFIX):
        raise BundleError("not_absorbed", f"only absorbed capabilities are exportable: {capability_id}")
    if entry.get("last_proof_exit_code") != 0:
        raise BundleError("not_proved", f"capability is not proved: {capability_id}")
    slug = capability_id[len(ABSORBED_ID_PREFIX):]
    tool_root = absorbed_root(root) / slug
    try:
        manifest = load_manifest(tool_root)
    except ValueError as exc:
        raise BundleError("manifest_invalid", f"vendored manifest is not loadable: {exc}")
    files: dict[str, dict[str, Any]] = {}
    for path in _iter_tool_files(tool_root):
        relative = path.relative_to(tool_root).as_posix()
        content = path.read_bytes()
        files[relative] = {
            "sha256": hashlib.sha256(content).hexdigest(),
            "content_b64": base64.b64encode(content).decode("ascii"),
        }
    registration = {field: entry[field] for field in _ENTRY_FIELDS if field in entry}
    registration["last_proved_at"] = str(entry.get("last_proved_at") or "")
    payload = {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "kind": BUNDLE_KIND,
        "capability_id": capability_id,
        "slug": slug,
        "requires": [str(key) for key in manifest["requires"]],
        "provides": [str(key) for key in manifest["provides"]],
        "registration": registration,
        "files": files,
    }
    bundle = {**payload, "bundle_digest": _digest(payload)}
    atomic_write_json(Path(out_path), bundle)
    return {
        "ok": True,
        "capability_id": capability_id,
        "bundle": str(out_path),
        "bundle_digest": bundle["bundle_digest"],
        "file_count": len(files),
    }


def _verify_bundle(bundle: Any) -> dict[str, Any]:
    if not isinstance(bundle, dict):
        raise BundleError("malformed", "bundle must be a JSON object")
    if int(bundle.get("schema_version") or 0) != BUNDLE_SCHEMA_VERSION:
        raise BundleError("unsupported_schema", f"unsupported bundle schema_version: {bundle.get('schema_version')!r}")
    if bundle.get("kind") != BUNDLE_KIND:
        raise BundleError("malformed", f"bundle kind must be {BUNDLE_KIND!r}")
    seal = bundle.get("bundle_digest")
    if not isinstance(seal, str) or not seal:
        raise BundleError("malformed", "bundle has no bundle_digest")
    payload = {key: value for key, value in bundle.items() if key != "bundle_digest"}
    if _digest(payload) != seal:
        raise BundleError("tampered", "bundle payload does not match its bundle_digest seal")
    capability_id = str(payload.get("capability_id") or "")
    slug = str(payload.get("slug") or "")
    if not capability_id.startswith(ABSORBED_ID_PREFIX) or capability_id[len(ABSORBED_ID_PREFIX):] != slug:
        raise BundleError("tampered", "capability_id and slug disagree")
    files = payload.get("files")
    if not isinstance(files, dict) or not files:
        raise BundleError("malformed", "bundle carries no files")
    for relative, record in files.items():
        path = PurePosixPath(relative)
        if path.is_absolute() or ".." in path.parts or not relative:
            raise BundleError("unsafe_path", f"unsafe bundle member path: {relative!r}")
        if not isinstance(record, dict):
            raise BundleError("malformed", f"bundle member {relative!r} is not an object")
        try:
            content = base64.b64decode(str(record.get("content_b64") or ""), validate=True)
        except ValueError as exc:
            raise BundleError("malformed", f"bundle member {relative!r} content is not base64: {exc}")
        if hashlib.sha256(content).hexdigest() != record.get("sha256"):
            raise BundleError("tampered", f"bundle member {relative!r} content does not match its sha256")
    registration = payload.get("registration")
    if not isinstance(registration, dict):
        raise BundleError("malformed", "bundle registration record must be an object")
    return payload


def verify_capability_bundle(bundle_path: Path) -> dict[str, Any]:
    """Verify a bundle file without importing it; returns its identity summary."""

    try:
        bundle = json.loads(Path(bundle_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BundleError("malformed", f"bundle is not readable JSON: {exc}")
    payload = _verify_bundle(bundle)
    return {
        "ok": True,
        "capability_id": payload["capability_id"],
        "bundle_digest": bundle["bundle_digest"],
        "file_count": len(payload["files"]),
        "requires": payload["requires"],
        "provides": payload["provides"],
    }


def _reproof_staged_tree(staging: Path, manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Re-execute every frozen case in the staged tree under governed bounds."""

    results = [
        _run_governed_case(
            staging, manifest["command"], case, REPROOF_LIMITS, REPROOF_TIMEOUT_SECONDS
        )
        for case in manifest["cases"]
    ]
    failures = [
        {"case": index, "error": result.get("error", "unknown")}
        for index, result in enumerate(results)
        if not result.get("ok")
    ]
    return {"cases_passed": len(results) - len(failures), "cases_total": len(results), "failures": failures}


def import_capability_bundle(
    bundle_path: Path, target_root: Path, *, overwrite: bool = False
) -> dict[str, Any]:
    """Import a verified bundle into a bare target checkout, fail-closed.

    Verification (seal, per-file digests, path safety, duplicate policy)
    completes before anything is written. The vendored tree is then staged
    in a temporary sibling directory and re-proved locally — every frozen
    manifest case re-executes under the plane's governed resource bounds —
    so the target's proved status is earned by its own execution evidence.
    Only a fully re-proved tree moves into place and registers in the
    target ledger; any earlier failure leaves the target untouched.
    """

    summary = verify_capability_bundle(bundle_path)
    bundle = json.loads(Path(bundle_path).read_text(encoding="utf-8"))
    payload = {key: value for key, value in bundle.items() if key != "bundle_digest"}
    capability_id = payload["capability_id"]
    slug = payload["slug"]
    target_root = Path(target_root)
    document = _load_ledger_document(target_root)
    if capability_id in document["capabilities"] and not overwrite:
        raise BundleError("duplicate", f"target ledger already registers {capability_id}")
    parent = absorbed_root(target_root)
    parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".bundle-staging-", dir=parent))
    try:
        for relative, record in payload["files"].items():
            destination = staging / PurePosixPath(relative)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(base64.b64decode(record["content_b64"]))
        # Re-validate the staged manifest against the absorption schema so a
        # bundle whose files hash correctly but describe an invalid tool still
        # fails closed before registration.
        try:
            manifest = load_manifest(staging)
        except ValueError as exc:
            raise BundleError("manifest_invalid", f"staged manifest is invalid: {exc}")
        reproof = _reproof_staged_tree(staging, manifest)
        if reproof["failures"]:
            raise BundleError(
                "reproof_failed",
                f"import-time re-proof failed in target checkout: {reproof['failures']}",
            )
        tool_root = parent / slug
        if tool_root.exists():
            shutil.rmtree(tool_root)
        staging.replace(tool_root)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    registration = dict(payload["registration"])
    registration.update(
        {
            "id": capability_id,
            "last_proof_exit_code": 0,
            "origin": "capability-bundle-import",
            "imported_bundle_digest": summary["bundle_digest"],
            "import_reproof": {
                "cases_passed": reproof["cases_passed"],
                "cases_total": reproof["cases_total"],
                "proved_at": utc_now_iso(),
            },
            "imported_at": utc_now_iso(),
            "updated_at": utc_now_iso(),
        }
    )
    document["capabilities"][capability_id] = registration
    document["updated_at"] = utc_now_iso()
    atomic_write_json(_ledger_path(target_root), document)
    return {
        "ok": True,
        "capability_id": capability_id,
        "target_root": str(target_root),
        "bundle_digest": summary["bundle_digest"],
        "file_count": summary["file_count"],
        "reproof": {"cases_passed": reproof["cases_passed"], "cases_total": reproof["cases_total"]},
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="export/import digest-sealed capability bundles")
    sub = parser.add_subparsers(dest="action", required=True)
    export_cmd = sub.add_parser("export")
    export_cmd.add_argument("capability_id")
    export_cmd.add_argument("out_path", type=Path)
    export_cmd.add_argument("--root", type=Path, default=Path.cwd())
    import_cmd = sub.add_parser("import")
    import_cmd.add_argument("bundle_path", type=Path)
    import_cmd.add_argument("--target-root", type=Path, required=True)
    import_cmd.add_argument("--overwrite", action="store_true")
    verify_cmd = sub.add_parser("verify")
    verify_cmd.add_argument("bundle_path", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.action == "export":
            outcome = export_capability_bundle(args.root, args.capability_id, args.out_path)
        elif args.action == "import":
            outcome = import_capability_bundle(args.bundle_path, args.target_root, overwrite=args.overwrite)
        else:
            outcome = verify_capability_bundle(args.bundle_path)
    except BundleError as exc:
        print(json.dumps({"ok": False, "verdict": exc.verdict, "detail": exc.detail}))
        return 1
    print(json.dumps(outcome, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
