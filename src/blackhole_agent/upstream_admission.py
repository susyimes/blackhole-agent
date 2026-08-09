"""Upstream admission plane: promote sealed discovery findings into stewardship.

Discovery produces measured findings and synthesized repros under
``artifacts/upstream-discovery/``. Repair and contribution only operate on
manifest-curated defects under ``stewardship/<target>/``. The admission plane
closes that gap: a sealed discovery report becomes stewarded defect entries
with copied repro evidence, optional patch binding, and a digest-sealed
admission receipt.

Rules:

- The discovery report seal is re-verified before any mutation
  (``report_unsealed`` refuses).
- Only flagged findings with a repro file are admissible.
- Defect ids are deterministic: ``{generator-with-dashes}-{kind}``.
- Repros are copied into ``repros/`` under the target (bytes-preserving).
- Existing defects with the same id are left intact (idempotent re-admit);
  a content mismatch on the repro raises ``repro_conflict``.
- Patches are optional: ``patch_map`` (generator → relative patch path) or an
  on-disk ``patches/<defect-id>.patch`` binds a patch; otherwise the defect is
  recorded with ``pending_patch: true`` and no ``patch`` field so the repair
  plane can skip it until a patch is supplied.
- The mutated manifest and admission receipt are digest-sealed; verification
  re-checks digests and detects tampering. No skill-route discovery is used.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from blackhole_agent import upstream_discovery as ud
from blackhole_agent.capability_compounder import (
    atomic_write_json,
    legacy_pipeline_was_used,
    utc_now_iso,
)
from blackhole_agent.durable_state import durable_read_path

SCHEMA_VERSION = 1

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS_ROOT = REPO_ROOT / "artifacts" / "upstream-admission"


class AdmissionRefused(Exception):
    """A verdict-bearing refusal: the admission must not mutate the target."""

    def __init__(self, verdict: str, detail: str):
        super().__init__(f"{verdict}: {detail}")
        self.verdict = verdict
        self.detail = detail


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_path(path: Path) -> str:
    return _sha256_bytes(durable_read_path(path).read_bytes())


def _sha256_json(payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return _sha256_bytes(canonical.encode("utf-8"))


def defect_id_for(generator: str, kind: str) -> str:
    """Deterministic stewardship defect id from a discovery finding."""
    gen = str(generator).strip().replace("_", "-")
    k = str(kind).strip().replace("_", "-") or "defect"
    return f"{gen}-{k}"


def _title_for(generator: str, kind: str, finding: Mapping[str, Any]) -> str:
    exp = finding.get("exponent")
    exp_bit = f" (exponent≈{exp})" if isinstance(exp, (int, float)) else ""
    return (
        f"Autonomous discovery finding: generator={generator!r} kind={kind}{exp_bit}"
    )


def _resolve_patch_rel(
    target_dir: Path,
    defect_id: str,
    generator: str,
    patch_map: Mapping[str, str] | None,
) -> str | None:
    if patch_map:
        for key in (generator, defect_id):
            if key in patch_map and patch_map[key]:
                rel = str(patch_map[key]).replace("\\", "/")
                if (target_dir / rel).is_file():
                    return rel
    default = f"patches/{defect_id}.patch"
    if (target_dir / default).is_file():
        return default
    return None


def admit_discovery_findings(
    target_dir: Path,
    report_dir: Path,
    *,
    patch_map: Mapping[str, str] | None = None,
    out_root: Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Admit flagged discovery findings into a stewardship target manifest.

    Returns a sealed admission result. When ``dry_run=True`` the manifest is
    not written; the receipt still records the would-be mutations.
    """
    target_dir = Path(target_dir)
    report_dir = Path(report_dir)
    manifest_path = target_dir / "manifest.json"
    if not manifest_path.is_file():
        raise AdmissionRefused("target_invalid", f"no manifest at {target_dir}")

    verification = ud.verify_discovery_report(report_dir)
    if not verification.get("ok"):
        raise AdmissionRefused(
            "report_unsealed",
            f"discovery report failed verification: {verification.get('problems')}",
        )

    report_path = durable_read_path(report_dir / "report.json")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    manifest = json.loads(durable_read_path(manifest_path).read_text(encoding="utf-8"))
    existing = {str(d.get("id")): d for d in (manifest.get("defects") or []) if d.get("id")}

    admitted: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    pending_patch: list[str] = []
    new_defects: list[dict[str, Any]] = list(manifest.get("defects") or [])

    for finding in report.get("findings") or []:
        if not finding.get("flagged"):
            continue
        generator = str(finding.get("generator") or "")
        kind = str(finding.get("kind") or "defect")
        if not generator:
            skipped.append({"reason": "missing_generator", "finding": finding})
            continue
        repro_rel = finding.get("repro")
        if not repro_rel:
            skipped.append({
                "generator": generator,
                "reason": "missing_repro",
            })
            continue
        src_repro = report_dir / str(repro_rel)
        if not src_repro.is_file():
            skipped.append({
                "generator": generator,
                "reason": "repro_file_missing",
                "repro": str(repro_rel),
            })
            continue

        defect_id = defect_id_for(generator, kind)
        dest_name = src_repro.name
        dest_rel = f"repros/{dest_name}"
        dest_path = target_dir / dest_rel
        src_bytes = durable_read_path(src_repro).read_bytes()
        src_sha = _sha256_bytes(src_bytes)

        if defect_id in existing:
            prior = existing[defect_id]
            prior_repro = target_dir / str(prior.get("repro") or "")
            if prior_repro.is_file() and _sha256_path(prior_repro) != src_sha:
                raise AdmissionRefused(
                    "repro_conflict",
                    f"defect {defect_id} already admitted with different repro bytes",
                )
            skipped.append({
                "generator": generator,
                "defect_id": defect_id,
                "reason": "already_admitted",
            })
            continue

        patch_rel = _resolve_patch_rel(target_dir, defect_id, generator, patch_map)
        entry: dict[str, Any] = {
            "id": defect_id,
            "title": _title_for(generator, kind, finding),
            "kind": kind,
            "upstream_ref": (
                f"admitted from discovery report {report_dir.name} "
                f"(generator={generator}, kind={kind})"
            ),
            "repro": dest_rel,
            "discovery_generator": generator,
            "discovery_report_sha256": _sha256_path(report_path),
            "repro_sha256": src_sha,
        }
        if patch_rel:
            entry["patch"] = patch_rel
            entry["pending_patch"] = False
        else:
            entry["pending_patch"] = True
            pending_patch.append(defect_id)

        if not dry_run:
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            if not dest_path.exists():
                dest_path.write_bytes(src_bytes)
            elif _sha256_path(dest_path) != src_sha:
                raise AdmissionRefused(
                    "repro_conflict",
                    f"repro path {dest_rel} exists with different bytes",
                )
            new_defects.append(entry)

        admitted.append({
            "defect_id": defect_id,
            "generator": generator,
            "kind": kind,
            "repro": dest_rel,
            "repro_sha256": src_sha,
            "patch": patch_rel,
            "pending_patch": not bool(patch_rel),
        })

    if not dry_run and admitted:
        manifest["defects"] = new_defects
        # Preserve key order stability for humans: rewrite whole file.
        atomic_write_json(manifest_path, manifest)

    root = Path(out_root) if out_root else ARTIFACTS_ROOT
    stamp = utc_now_iso().replace(":", "").replace("-", "")
    name = f"{manifest.get('name')}-{manifest.get('version')}"
    receipt_dir = root / name / stamp
    receipt_dir.mkdir(parents=True, exist_ok=True)

    receipt = {
        "schema_version": SCHEMA_VERSION,
        "created_at": utc_now_iso(),
        "target": str(target_dir),
        "name": manifest.get("name"),
        "version": manifest.get("version"),
        "report_dir": str(report_dir),
        "report_sha256": _sha256_path(report_path),
        "report_chain_digest": report.get("chain_digest"),
        "dry_run": dry_run,
        "admitted": admitted,
        "skipped": skipped,
        "admitted_count": len(admitted),
        "pending_patch_ids": pending_patch,
        "manifest_sha256": _sha256_path(manifest_path) if manifest_path.is_file() else None,
        "ok": True,
        "verdict": (
            "admitted"
            if admitted
            else ("nothing_to_admit" if not any(
                f.get("flagged") for f in (report.get("findings") or [])
            ) else "all_already_admitted")
        ),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }
    chain = _sha256_json({
        "schema_version": SCHEMA_VERSION,
        "name": receipt["name"],
        "version": receipt["version"],
        "report_sha256": receipt["report_sha256"],
        "admitted": [
            {
                "defect_id": a["defect_id"],
                "repro_sha256": a["repro_sha256"],
                "patch": a.get("patch"),
                "pending_patch": a.get("pending_patch"),
            }
            for a in admitted
        ],
        "verdict": receipt["verdict"],
        "dry_run": dry_run,
    })
    receipt["admission_digest"] = chain
    atomic_write_json(receipt_dir / "receipt.json", receipt)

    return {
        "ok": True,
        "verdict": receipt["verdict"],
        "receipt_dir": str(receipt_dir),
        "admission_digest": chain,
        "admitted": admitted,
        "skipped": skipped,
        "admitted_count": len(admitted),
        "pending_patch_ids": pending_patch,
        "target": str(target_dir),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }


def verify_admission_receipt(receipt_dir: Path) -> dict[str, Any]:
    """Re-check a sealed admission receipt against on-disk evidence."""
    receipt_dir = Path(receipt_dir)
    receipt_path = durable_read_path(receipt_dir / "receipt.json")
    if not receipt_path.is_file():
        return {"ok": False, "error": f"missing receipt: {receipt_path}"}
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    problems: list[str] = []
    mismatched: list[str] = []

    expected_chain = _sha256_json({
        "schema_version": receipt.get("schema_version", SCHEMA_VERSION),
        "name": receipt.get("name"),
        "version": receipt.get("version"),
        "report_sha256": receipt.get("report_sha256"),
        "admitted": [
            {
                "defect_id": a.get("defect_id"),
                "repro_sha256": a.get("repro_sha256"),
                "patch": a.get("patch"),
                "pending_patch": a.get("pending_patch"),
            }
            for a in (receipt.get("admitted") or [])
        ],
        "verdict": receipt.get("verdict"),
        "dry_run": receipt.get("dry_run"),
    })
    if expected_chain != receipt.get("admission_digest"):
        mismatched.append("admission_digest")
        problems.append("admission chain digest mismatch")

    report_dir = receipt.get("report_dir")
    if report_dir:
        report_json = Path(report_dir) / "report.json"
        if report_json.is_file():
            actual = _sha256_path(report_json)
            if actual != receipt.get("report_sha256"):
                mismatched.append("report_sha256")
                problems.append("discovery report digest mismatch")
            seal = ud.verify_discovery_report(Path(report_dir))
            if not seal.get("ok"):
                problems.append(f"discovery report seal broken: {seal.get('problems')}")

    target = receipt.get("target")
    if target and not receipt.get("dry_run"):
        tdir = Path(target)
        for a in receipt.get("admitted") or []:
            repro = tdir / str(a.get("repro") or "")
            if not repro.is_file():
                problems.append(f"missing admitted repro {a.get('repro')}")
            elif _sha256_path(repro) != a.get("repro_sha256"):
                mismatched.append(f"repro.{a.get('defect_id')}")
                problems.append(f"admitted repro digest mismatch for {a.get('defect_id')}")

    return {
        "ok": not problems and not mismatched,
        "problems": problems,
        "mismatched": mismatched,
        "admission_digest": receipt.get("admission_digest"),
        "verdict": receipt.get("verdict"),
    }


def _proof_discovery_report(scratch: Path, *, generator: str = "nested_link") -> Path:
    """Build a minimal sealed discovery report for hermetic proofs."""
    report_dir = scratch / "discovery-report"
    repros = report_dir / "repros"
    repros.mkdir(parents=True, exist_ok=True)
    repro_path = repros / f"{generator}.py"
    repro_body = (
        "#!/usr/bin/env python3\n"
        f"# synthetic repro for {generator}\n"
        "import sys\n"
        "sys.exit(1)  # defect present on pristine\n"
    ).encode("utf-8")
    repro_path.write_bytes(repro_body)
    findings = [
        {
            "generator": generator,
            "kind": "complexity",
            "flagged": True,
            "exponent": 2.1,
            "minimized_n": 2000,
            "repro": f"repros/{generator}.py",
            "repro_sha256": _sha256_bytes(repro_body),
            "pristine_repro_exit": 1,
        },
        {
            "generator": "benign_control",
            "kind": "complexity",
            "flagged": False,
            "exponent": 1.0,
        },
    ]
    report: dict[str, Any] = {
        "schema_version": ud.SCHEMA_VERSION,
        "target": {"name": "admitprobe", "version": "0.0.1"},
        "sdist_sha256": "b" * 64,
        "driver_runtime": "python",
        "findings": findings,
        "finding_count": 1,
        "scanned_at": utc_now_iso(),
    }
    report["chain_digest"] = ud._report_chain(report)
    atomic_write_json(report_dir / "report.json", report)
    return report_dir


def _proof_target(scratch: Path) -> Path:
    target = scratch / "stewardship" / "admitprobe-0.0.1"
    target.mkdir(parents=True, exist_ok=True)
    (target / "repros").mkdir(exist_ok=True)
    (target / "patches").mkdir(exist_ok=True)
    # Minimal dummy sdist so the directory looks like a target.
    sdist = target / "admitprobe-0.0.1.tar.gz"
    sdist.write_bytes(b"not-a-real-sdist")
    manifest = {
        "schema_version": 1,
        "name": "admitprobe",
        "version": "0.0.1",
        "kind": "pypi-sdist",
        "sdist": sdist.name,
        "sdist_sha256": _sha256_path(sdist),
        "upstream_repo": "https://github.com/proof/admitprobe",
        "src_subdir": "admitprobe-0.0.1/src",
        "driver": {"prelude": "def render(text, plugins):\n    return text\n"},
        "defects": [],
    }
    atomic_write_json(target / "manifest.json", manifest)
    return target


def builtin_upstream_admission_proof() -> dict[str, Any]:
    """Hermetic proof: admit, idempotent re-admit, seal verify, tamper detect."""
    scratch = Path(tempfile.mkdtemp(prefix="admission-proof-"))
    try:
        target = _proof_target(scratch)
        report_dir = _proof_discovery_report(scratch)

        # 1. First admission creates a pending-patch defect + copies repro.
        first = admit_discovery_findings(
            target,
            report_dir,
            out_root=scratch / "admission",
        )
        first_ok = (
            first["ok"]
            and first["verdict"] == "admitted"
            and first["admitted_count"] == 1
            and first["pending_patch_ids"] == ["nested-link-complexity"]
        )
        defect_id = first["admitted"][0]["defect_id"]
        repro_path = target / first["admitted"][0]["repro"]
        repro_copied = repro_path.is_file()
        manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
        manifest_has = any(d.get("id") == defect_id for d in manifest.get("defects") or [])

        verified = verify_admission_receipt(Path(first["receipt_dir"]))
        verify_ok = bool(verified.get("ok"))

        # 2. Idempotent re-admit: nothing new, no conflict.
        second = admit_discovery_findings(
            target,
            report_dir,
            out_root=scratch / "admission-2",
        )
        idempotent = (
            second["ok"]
            and second["verdict"] == "all_already_admitted"
            and second["admitted_count"] == 0
        )

        # 3. Patch binding: drop a patch file and admit a second generator.
        report2 = _proof_discovery_report(scratch / "r2", generator="footnote_defs")
        patch_rel = "patches/footnote-defs-complexity.patch"
        (target / patch_rel).write_text(
            "--- a/x\n+++ b/x\n@@ -1 +1 @@\n-old\n+new\n",
            encoding="utf-8",
        )
        patched = admit_discovery_findings(
            target,
            report2,
            out_root=scratch / "admission-3",
        )
        patch_bound = (
            patched["ok"]
            and patched["admitted_count"] == 1
            and patched["admitted"][0].get("patch") == patch_rel
            and not patched["admitted"][0].get("pending_patch")
        )

        # 4. Tamper detection.
        receipt_path = Path(first["receipt_dir"]) / "receipt.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["admission_digest"] = "0" * 64
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        tampered = verify_admission_receipt(Path(first["receipt_dir"]))
        tamper_detected = (not tampered.get("ok")) and "admission_digest" in (
            tampered.get("mismatched") or []
        )

        # 5. Unsealed report refused.
        bad_report = scratch / "bad-report"
        bad_report.mkdir()
        atomic_write_json(bad_report / "report.json", {
            "schema_version": 1,
            "target": {"name": "admitprobe", "version": "0.0.1"},
            "sdist_sha256": "c" * 64,
            "findings": [
                {"generator": "x", "kind": "complexity", "flagged": True, "repro": "nope.py"},
            ],
            "chain_digest": "deadbeef",
        })
        refused = False
        try:
            admit_discovery_findings(target, bad_report, out_root=scratch / "bad")
        except AdmissionRefused as exc:
            refused = exc.verdict == "report_unsealed"

        ok = (
            first_ok
            and repro_copied
            and manifest_has
            and verify_ok
            and idempotent
            and patch_bound
            and tamper_detected
            and refused
            and not first.get("used_skill_route_discovery")
        )
        return {
            "ok": ok,
            "admitted": first_ok and repro_copied and manifest_has,
            "idempotent": idempotent,
            "patch_bound": patch_bound,
            "receipt_verified": verify_ok,
            "tamper_detected": tamper_detected,
            "unsealed_refused": refused,
            "used_skill_route_discovery": legacy_pipeline_was_used(),
        }
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Upstream admission plane")
    sub = parser.add_subparsers(dest="cmd", required=True)

    admit_p = sub.add_parser("admit", help="Admit a sealed discovery report into a target")
    admit_p.add_argument("target", type=Path)
    admit_p.add_argument("report", type=Path)
    admit_p.add_argument("--out-root", type=Path, default=None)
    admit_p.add_argument("--dry-run", action="store_true")
    admit_p.add_argument(
        "--patch",
        action="append",
        default=[],
        metavar="GENERATOR=RELPATH",
        help="Bind a patch for a generator (repeatable)",
    )

    ver_p = sub.add_parser("verify", help="Verify an admission receipt")
    ver_p.add_argument("receipt_dir", type=Path)

    sub.add_parser("proof", help="Run hermetic builtin proof")

    args = parser.parse_args(argv)
    if args.cmd == "admit":
        patch_map = {}
        for item in args.patch:
            if "=" not in item:
                print(f"bad --patch {item!r}; expected GENERATOR=RELPATH", file=sys.stderr)
                return 2
            k, v = item.split("=", 1)
            patch_map[k] = v
        try:
            result = admit_discovery_findings(
                args.target,
                args.report,
                patch_map=patch_map or None,
                out_root=args.out_root,
                dry_run=args.dry_run,
            )
        except AdmissionRefused as exc:
            print(json.dumps({"ok": False, "verdict": exc.verdict, "detail": exc.detail}, indent=2))
            return 1
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1
    if args.cmd == "verify":
        result = verify_admission_receipt(args.receipt_dir)
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1
    if args.cmd == "proof":
        result = builtin_upstream_admission_proof()
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
