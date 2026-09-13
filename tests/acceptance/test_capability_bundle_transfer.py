"""Acceptance probe: proved capabilities transfer between checkouts as sealed bundles.

The controller replays probes via runpy from a temp copy with only the
implementation ``src`` on sys.path (isolated ``python -I``), so this probe is
fully self-contained: it builds a minimal source workspace (a ledger plus a
vendored absorbed tool), exports the capability as a bundle, imports it into
a bare target workspace that has no ledger and no vendored tools, invokes the
imported capability through the real governed invocation machinery on a novel
input, and confirms a tampered copy of the bundle is refused without writing
anything into another bare target.

Prints JSON with boolean passed and nonempty observed. Exits 0 for both met
and unmet outcomes so the controller can replay the same probe on baseline
and candidate source trees (baseline lacks the bundle module and reports
passed=false instead of crashing).
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

_TOOL_PY = """\
import json
import sys

payload = json.loads(sys.stdin.read())
print(json.dumps({"reversed_text": payload["raw_text"][::-1]}))
"""

_MANIFEST = {
    "schema_version": 1,
    "slug": "text-reverser",
    "name": "Text Reverser (external fixture tool)",
    "version": "1.0.0",
    "origin": {"kind": "fixture", "source": "probe", "commit": ""},
    "command": ["python", "tool.py"],
    "requires": ["raw_text"],
    "provides": ["reversed_text"],
    "cases": [
        {"input": {"raw_text": "blackhole"}, "expect": {"reversed_text": "elohkcalb"}},
        {"input": {"raw_text": "unbound"}, "expect": {"reversed_text": "dnuobnu"}},
    ],
}

_LEDGER_ENTRY = {
    "id": "capability.absorbed-text-reverser",
    "name": "Absorbed external capability: Text Reverser",
    "kind": "python",
    "description": "Absorbed fixture tool providing reversed_text.",
    "last_proof_exit_code": 0,
    "last_proved_at": "2026-09-13T00:00:00Z",
}


def _write_source_workspace(root: Path) -> None:
    tool_root = root / "capabilities" / "absorbed" / "text-reverser"
    tool_root.mkdir(parents=True)
    (tool_root / "absorption.json").write_text(json.dumps(_MANIFEST, indent=2), encoding="utf-8")
    (tool_root / "tool.py").write_text(_TOOL_PY, encoding="utf-8")
    (root / "capabilities").mkdir(exist_ok=True)
    (root / "capabilities" / "ledger.json").write_text(
        json.dumps(
            {
                "capabilities": {"capability.absorbed-text-reverser": _LEDGER_ENTRY},
                "schema_version": 1,
                "updated_at": "2026-09-13T00:00:00Z",
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def main() -> dict[str, object]:
    observed: dict[str, object] = {"family": "capability-bundle-transfer"}
    checks: dict[str, bool] = {}
    try:
        from blackhole_agent.capability_bundle import (
            BundleError,
            export_capability_bundle,
            import_capability_bundle,
        )
        from blackhole_agent.capability_service import invoke_capability
    except ImportError as exc:
        observed["error"] = f"module unavailable: {exc}"
        return {"passed": False, "observed": observed}
    try:
        with tempfile.TemporaryDirectory(prefix="capability-bundle-") as directory:
            base = Path(directory)
            source = base / "source"
            target = base / "target"
            tampered_target = base / "tampered-target"
            source.mkdir()
            target.mkdir()
            tampered_target.mkdir()
            _write_source_workspace(source)

            exported = export_capability_bundle(
                source, "capability.absorbed-text-reverser", base / "reverser.bundle.json"
            )
            checks["export_ok"] = exported.get("ok") is True

            imported = import_capability_bundle(base / "reverser.bundle.json", target)
            checks["import_ok"] = imported.get("ok") is True
            checks["import_reproved"] = imported.get("reproof") == {"cases_passed": 2, "cases_total": 2}
            target_ledger = json.loads(
                (target / "capabilities" / "ledger.json").read_text(encoding="utf-8")
            )
            target_entry = target_ledger["capabilities"].get("capability.absorbed-text-reverser")
            checks["registered_proved"] = (
                isinstance(target_entry, dict)
                and target_entry.get("last_proof_exit_code") == 0
                and target_entry.get("imported_bundle_digest") == exported.get("bundle_digest")
                and isinstance(target_entry.get("import_reproof"), dict)
            )

            invoked = invoke_capability(target, "capability.absorbed-text-reverser", {"raw_text": "transferable"})
            checks["novel_input_executes"] = invoked.get("output", {}).get("reversed_text") == "elbarefsnart"

            tampered = json.loads((base / "reverser.bundle.json").read_text(encoding="utf-8"))
            record = tampered["files"]["tool.py"]
            record["content_b64"] = ("A" if record["content_b64"][0] != "A" else "B") + record["content_b64"][1:]
            (base / "tampered.bundle.json").write_text(json.dumps(tampered), encoding="utf-8")
            try:
                import_capability_bundle(base / "tampered.bundle.json", tampered_target)
                checks["tamper_refused"] = False
                observed["tamper_verdict"] = "imported"
            except BundleError as exc:
                checks["tamper_refused"] = exc.verdict in {"tampered", "malformed"}
                observed["tamper_verdict"] = exc.verdict
            checks["tamper_left_nothing"] = not (tampered_target / "capabilities").exists()

            # A legitimately sealed bundle whose tool contradicts its frozen
            # cases must be refused by import-time re-proof, leaving the
            # target exactly as it was.
            import base64
            import hashlib

            misbehaving_target = base / "misbehaving-target"
            misbehaving_target.mkdir()
            original = json.loads((base / "reverser.bundle.json").read_text(encoding="utf-8"))
            payload = {key: value for key, value in original.items() if key != "bundle_digest"}
            bad_tool = (
                b"import json,sys\n"
                b"print(json.dumps({'reversed_text': json.loads(sys.stdin.read())['raw_text']}))\n"
            )
            payload["files"]["tool.py"] = {
                "sha256": hashlib.sha256(bad_tool).hexdigest(),
                "content_b64": base64.b64encode(bad_tool).decode("ascii"),
            }
            canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
            payload["bundle_digest"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            (base / "misbehaving.bundle.json").write_text(json.dumps(payload), encoding="utf-8")
            try:
                import_capability_bundle(base / "misbehaving.bundle.json", misbehaving_target)
                checks["reproof_refused"] = False
                observed["reproof_verdict"] = "imported"
            except BundleError as exc:
                checks["reproof_refused"] = exc.verdict == "reproof_failed"
                observed["reproof_verdict"] = exc.verdict
            absorbed_dir = misbehaving_target / "capabilities" / "absorbed"
            checks["reproof_left_nothing"] = not (misbehaving_target / "capabilities" / "ledger.json").exists() and (
                not absorbed_dir.exists()
                or [p for p in absorbed_dir.iterdir()] == []
            )
    except Exception as exc:
        observed["error"] = f"{type(exc).__name__}: {exc}"
        observed["checks"] = checks
        return {"passed": False, "observed": observed}
    observed["checks"] = checks
    observed["bundle_digest"] = exported.get("bundle_digest")
    observed["invoked_output"] = invoked.get("output")
    return {"passed": bool(all(checks.values())), "observed": observed}


if __name__ == "__main__":
    try:
        outcome = main()
    except Exception as error:  # an unmet outcome must exit 0, not crash
        outcome = {
            "passed": False,
            "observed": {"family": "capability-bundle-transfer", "error": type(error).__name__, "detail": str(error)},
        }
    print(json.dumps(outcome, sort_keys=True))
    sys.exit(0)
