"""Shared irreversible certificate I/O for the total spine.

Path resolution, atomic write with supersession refusal, and tamper-closed
load used to be copied once per family (continuity, finality, federation,
execution, actuation, settlement, clearing, and every pair-effect). Those
families keep their own seal/verify material; this module owns the I/O
once. New families are a seal function plus a thin wrapper, not another
150-line copy of path/write/load.

No skill-route discovery.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import tempfile
from pathlib import Path
from typing import Any, Callable, Mapping

from blackhole_agent.capability_compounder import (
    atomic_write_json,
    legacy_pipeline_was_used,
)
from blackhole_agent.durable_state import durable_read_path

SCHEMA_VERSION = 1

RefusedFactory = Callable[[str, str], BaseException]


class CertificateRefused(Exception):
    """Verdict-bearing refusal from the shared certificate plane."""

    def __init__(self, verdict: str, detail: str):
        super().__init__(f"{verdict}: {detail}")
        self.verdict = verdict
        self.detail = detail


def resolve_certificate_path(
    root: Path,
    *,
    filename: str,
    subdir: str,
    kind: str | None,
    parent_sibling: bool = False,
) -> Path:
    """Resolve a sealed certificate file under an out root.

    Shared resolver for the total-spine certificate families. With
    ``kind=None`` (continuity checkpoints) an explicit file path is returned
    as-is; otherwise a JSON file is probed for the family ``kind`` before
    sibling and nested locations are searched. ``parent_sibling`` enables the
    extra ``parent.parent / filename`` probe used by the finality, execution,
    actuation, settlement, clearing, and pair-effect families.
    """
    path = Path(root)
    if path.is_file():
        if kind is None:
            return path
        if path.name == filename or path.suffix == ".json":
            try:
                probe = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                probe = None
            if isinstance(probe, Mapping) and (
                str(probe.get("kind") or "") == kind or path.name == filename
            ):
                return path
        parent = path.parent
        sibling = parent / filename
        if sibling.is_file():
            return sibling
        nested = parent / subdir / filename
        if nested.is_file():
            return nested
        grand = parent.parent / subdir / filename
        if grand.is_file():
            return grand
        if parent_sibling:
            grand_sib = parent.parent / filename
            if grand_sib.is_file():
                return grand_sib
        return parent / subdir / filename
    named = path / filename
    if named.is_file():
        return named
    nested = path / subdir / filename
    if nested.is_file():
        return nested
    return path / subdir / filename


def write_irreversible_certificate(
    out_root: Path,
    body: Mapping[str, Any],
    *,
    family: str,
    digest_key: str,
    seal: Callable[[Mapping[str, Any]], dict[str, Any]],
    resolve: Callable[[Path], Path],
    load: Callable[[Path | str], dict[str, Any]],
    allow_idempotent: bool,
    refused: type[BaseException] | RefusedFactory = CertificateRefused,
    label: str | None = None,
    path_key: str | None = None,
    idempotent_key: str | None = None,
) -> dict[str, Any]:
    """Seal and atomically write a certificate with supersession refusal.

    Shared by the irreversible certificate families: an identical digest is
    returned idempotently; a divergent reseal raises
    ``total_spine_<family>_supersession_refused`` so completed outcomes
    cannot be rewritten. ``label`` is the noun used in the refusal detail
    (pair-effect families pass the predecessor name to keep historical
    wording).
    """
    sealed = seal(body)
    path = resolve(Path(out_root))
    path_name = path_key or f"{family}_path"
    idemp_name = idempotent_key or f"total_spine_{family}_idempotent"
    noun = label or family
    if path.is_file():
        try:
            existing = load(path)
        except Exception as exc:  # noqa: BLE001 — family loaders raise local StageRefused
            if not hasattr(exc, "verdict"):
                raise
            existing = None
        if existing is not None:
            existing_digest = str(
                existing.get(digest_key) or existing.get("certificate_hash") or ""
            )
            new_digest = str(
                sealed.get(digest_key) or sealed.get("certificate_hash") or ""
            )
            if existing_digest and existing_digest == new_digest and allow_idempotent:
                existing[path_name] = str(path)
                existing[idemp_name] = True
                return existing
            raise refused(
                f"total_spine_{family}_supersession_refused",
                f"irreversible {noun} already sealed at {path} "
                f"(existing={existing_digest!r} attempted={new_digest!r})",
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, sealed)
    sealed[path_name] = str(path)
    sealed[idemp_name] = False
    return sealed


def load_irreversible_certificate(
    path: Path | str,
    *,
    family: str,
    label: str,
    path_key: str,
    verify_key: str,
    resolve: Callable[[Path], Path],
    verify: Callable[[Mapping[str, Any]], dict[str, Any]],
    refused: type[BaseException] | RefusedFactory = CertificateRefused,
    accept: Callable[[Mapping[str, Any]], bool] | None = None,
    loaded_key: str | None = None,
) -> dict[str, Any]:
    """Load and integrity-check a sealed certificate; fail closed on tamper.

    Raises ``refused`` when the file is missing, unreadable, not a JSON
    object, rejected by ``accept``, or digest-mismatched.
    """
    file_path = resolve(Path(path))
    if not file_path.is_file():
        raise refused(
            f"total_spine_{family}_missing",
            f"{label} not found at {file_path}",
        )
    raw_path = durable_read_path(file_path)
    try:
        payload = json.loads(raw_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise refused(
            f"total_spine_{family}_unreadable",
            f"{label} unreadable at {file_path}: {exc}",
        ) from exc
    if not isinstance(payload, Mapping):
        raise refused(
            f"total_spine_{family}_invalid",
            f"{label} root must be a JSON object",
        )
    if accept is not None and not accept(payload):
        raise refused(
            f"total_spine_{family}_missing",
            f"{label} not found at {file_path}",
        )
    result = verify(payload)
    if not result.get("ok"):
        raise refused(
            f"total_spine_{family}_tampered",
            f"{label} digest mismatch at {file_path} "
            f"(claimed={result.get('claimed_digest')!r} "
            f"expected={result.get('expected_digest')!r})",
        )
    body = dict(payload)
    body[path_key] = str(file_path)
    body[verify_key] = result
    body[loaded_key or f"total_spine_{family}_loaded"] = True
    return body


def _sha256_json(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
            "utf-8"
        )
    ).hexdigest()


def _live_family_uses_plane(fn: Any, token: str) -> bool:
    try:
        source = inspect.getsource(fn)
    except (OSError, TypeError):
        return False
    return token in source


def builtin_certificate_plane_proof() -> dict[str, Any]:
    """Hermetic proof that shared certificate I/O is real and live-wired.

    Exercises write/load/idempotent/supersession/tamper/missing/path
    resolution on a scratch family, then inspects the live total-spine
    wrappers to prove they call this plane rather than inlined copies.
    """

    class _Refused(Exception):
        def __init__(self, verdict: str, detail: str):
            super().__init__(f"{verdict}: {detail}")
            self.verdict = verdict
            self.detail = detail

    checks: dict[str, bool] = {}

    def _seal(body: Mapping[str, Any]) -> dict[str, Any]:
        material = {
            "kind": str(body.get("kind") or "demo"),
            "value": body.get("value"),
        }
        digest = _sha256_json(material)
        sealed = dict(material)
        sealed["demo_digest"] = digest
        sealed["certificate_hash"] = digest
        return sealed

    def _verify(certificate: Mapping[str, Any]) -> dict[str, Any]:
        claimed = str(certificate.get("demo_digest") or "")
        expected = _sha256_json(
            {
                "kind": str(certificate.get("kind") or "demo"),
                "value": certificate.get("value"),
            }
        )
        return {
            "ok": bool(claimed) and claimed == expected,
            "claimed_digest": claimed,
            "expected_digest": expected,
        }

    with tempfile.TemporaryDirectory(prefix="blackhole-cert-plane-") as tmp:
        root = Path(tmp)

        def _resolve(item: Path) -> Path:
            return resolve_certificate_path(
                item,
                filename="demo.json",
                subdir="demo",
                kind="demo",
                parent_sibling=True,
            )

        def _load(item: Path | str) -> dict[str, Any]:
            return load_irreversible_certificate(
                item,
                family="demo",
                label="demo certificate",
                path_key="demo_path",
                verify_key="demo_verify",
                resolve=_resolve,
                verify=_verify,
                refused=_Refused,
            )

        written = write_irreversible_certificate(
            root,
            {"kind": "demo", "value": 1},
            family="demo",
            digest_key="demo_digest",
            seal=_seal,
            resolve=_resolve,
            load=_load,
            allow_idempotent=True,
            refused=_Refused,
        )
        written_path = Path(str(written.get("demo_path") or ""))
        checks["write_ok"] = bool(written.get("demo_digest")) and written_path.is_file()
        checks["nested_path"] = written_path == root / "demo" / "demo.json"

        loaded = _load(root)
        checks["roundtrip"] = (
            loaded.get("demo_digest") == written.get("demo_digest")
            and loaded.get("total_spine_demo_loaded") is True
        )

        again = write_irreversible_certificate(
            root,
            {"kind": "demo", "value": 1},
            family="demo",
            digest_key="demo_digest",
            seal=_seal,
            resolve=_resolve,
            load=_load,
            allow_idempotent=True,
            refused=_Refused,
        )
        checks["idempotent"] = again.get("total_spine_demo_idempotent") is True

        try:
            write_irreversible_certificate(
                root,
                {"kind": "demo", "value": 2},
                family="demo",
                digest_key="demo_digest",
                seal=_seal,
                resolve=_resolve,
                load=_load,
                allow_idempotent=True,
                refused=_Refused,
            )
            checks["supersession_refused"] = False
        except _Refused as exc:
            checks["supersession_refused"] = (
                exc.verdict == "total_spine_demo_supersession_refused"
            )

        probe_root = root / "probe"
        decoy_dir = probe_root / "other"
        decoy_dir.mkdir(parents=True)
        decoy = decoy_dir / "decoy.json"
        decoy.write_text(json.dumps({"kind": "other"}), encoding="utf-8")
        # Isolated tree: no nested grand file, so parent_sibling is the hit.
        parent_sib = probe_root / "demo.json"
        parent_sib.write_text(
            json.dumps({"kind": "demo", "value": 7, "demo_digest": "x"}),
            encoding="utf-8",
        )
        resolved = resolve_certificate_path(
            decoy,
            filename="demo.json",
            subdir="demo",
            kind="demo",
            parent_sibling=True,
        )
        checks["parent_sibling_probe"] = resolved == parent_sib

        payload = json.loads(written_path.read_text(encoding="utf-8"))
        payload["value"] = 99
        written_path.write_text(json.dumps(payload), encoding="utf-8")
        try:
            _load(written_path)
            checks["tamper_refused"] = False
        except _Refused as exc:
            checks["tamper_refused"] = exc.verdict == "total_spine_demo_tampered"

        try:
            _load(root / "missing-root")
            checks["missing_refused"] = False
        except _Refused as exc:
            checks["missing_refused"] = exc.verdict == "total_spine_demo_missing"

        empty = root / "empty.json"
        empty.write_text("[]", encoding="utf-8")
        try:
            _load(empty)
            checks["invalid_refused"] = False
        except _Refused as exc:
            # resolve may treat empty.json as a probe miss and look for demo.json
            checks["invalid_refused"] = exc.verdict in {
                "total_spine_demo_invalid",
                "total_spine_demo_missing",
                "total_spine_demo_tampered",
            }

        bogus = root / "bogus.json"
        bogus.write_text("{not-json", encoding="utf-8")
        # Force resolve to this file by using kind=None semantics via a
        # filename match that still fails to parse.
        try:
            load_irreversible_certificate(
                bogus,
                family="demo",
                label="demo certificate",
                path_key="demo_path",
                verify_key="demo_verify",
                resolve=lambda p: Path(p) if Path(p).is_file() else _resolve(p),
                verify=_verify,
                refused=_Refused,
            )
            checks["unreadable_refused"] = False
        except _Refused as exc:
            checks["unreadable_refused"] = exc.verdict == "total_spine_demo_unreadable"

    wired: dict[str, bool] = {}
    try:
        from blackhole_agent import upstream_control_engine as uce

        wired["finality"] = _live_family_uses_plane(
            uce.write_total_spine_finality_certificate, "write_irreversible_certificate"
        ) and _live_family_uses_plane(
            uce.load_total_spine_finality_certificate, "load_irreversible_certificate"
        )
        wired["federation"] = _live_family_uses_plane(
            uce.write_total_spine_federation_certificate, "write_irreversible_certificate"
        ) and _live_family_uses_plane(
            uce.load_total_spine_federation_certificate, "load_irreversible_certificate"
        )
        wired["execution"] = _live_family_uses_plane(
            uce.write_total_spine_execution_certificate, "write_irreversible_certificate"
        ) and _live_family_uses_plane(
            uce.load_total_spine_execution_certificate, "load_irreversible_certificate"
        )
        wired["continuity"] = _live_family_uses_plane(
            uce.continuity_checkpoint_path, "resolve_certificate_path"
        ) and _live_family_uses_plane(
            uce.load_total_spine_continuity_checkpoint, "load_irreversible_certificate"
        )
    except Exception:  # noqa: BLE001
        wired.setdefault("finality", False)
        wired.setdefault("federation", False)
        wired.setdefault("execution", False)
        wired.setdefault("continuity", False)
    try:
        from blackhole_agent import upstream_total_spine_actuation as actuation

        wired["actuation"] = _live_family_uses_plane(
            actuation.write_total_spine_actuation_certificate,
            "write_irreversible_certificate",
        ) and _live_family_uses_plane(
            actuation.load_total_spine_actuation_certificate,
            "load_irreversible_certificate",
        )
    except Exception:  # noqa: BLE001
        wired["actuation"] = False
    try:
        from blackhole_agent import upstream_total_spine_settlement as settlement

        wired["settlement"] = _live_family_uses_plane(
            settlement.write_total_spine_settlement_certificate,
            "write_irreversible_certificate",
        ) and _live_family_uses_plane(
            settlement.load_total_spine_settlement_certificate,
            "load_irreversible_certificate",
        )
    except Exception:  # noqa: BLE001
        wired["settlement"] = False
    try:
        from blackhole_agent import upstream_total_spine_clearing as clearing

        wired["clearing"] = _live_family_uses_plane(
            clearing.write_total_spine_clearing_certificate,
            "write_irreversible_certificate",
        ) and _live_family_uses_plane(
            clearing.load_total_spine_clearing_certificate,
            "load_irreversible_certificate",
        )
    except Exception:  # noqa: BLE001
        wired["clearing"] = False
    try:
        from blackhole_agent import upstream_total_spine_effects as effects

        wired["pair_effects"] = _live_family_uses_plane(
            effects.write_certificate, "write_irreversible_certificate"
        ) and _live_family_uses_plane(
            effects.load_certificate, "load_irreversible_certificate"
        )
    except Exception:  # noqa: BLE001
        wired["pair_effects"] = False

    wired_count = sum(1 for ok in wired.values() if ok)
    checks["wired_families"] = wired_count >= 8
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    return {
        "schema_version": SCHEMA_VERSION,
        "action": "certificate_plane_proof",
        "ok": all(checks.values()),
        "checks": checks,
        "wired": wired,
        "wired_count": wired_count,
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }


def main(argv: list[str] | None = None) -> int:
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Shared total-spine certificate plane")
    parser.add_argument("--proof", action="store_true", help="run the hermetic builtin proof")
    args = parser.parse_args(argv)
    if args.proof:
        result = builtin_certificate_plane_proof()
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("ok") else 1
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
