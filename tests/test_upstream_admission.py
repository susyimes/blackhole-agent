"""Hermetic tests for the upstream admission plane."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from blackhole_agent import upstream_admission as ua


def test_admit_promotes_finding_and_is_idempotent(tmp_path: Path) -> None:
    target = ua._proof_target(tmp_path)
    report = ua._proof_discovery_report(tmp_path / "disc")

    first = ua.admit_discovery_findings(target, report, out_root=tmp_path / "out1")
    assert first["ok"]
    assert first["verdict"] == "admitted"
    assert first["admitted_count"] == 1
    assert first["pending_patch_ids"] == ["nested-link-complexity"]

    repro = target / first["admitted"][0]["repro"]
    assert repro.is_file()
    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    assert any(d["id"] == "nested-link-complexity" for d in manifest["defects"])
    assert any(d.get("pending_patch") for d in manifest["defects"])

    verified = ua.verify_admission_receipt(Path(first["receipt_dir"]))
    assert verified["ok"]

    second = ua.admit_discovery_findings(target, report, out_root=tmp_path / "out2")
    assert second["ok"]
    assert second["verdict"] == "all_already_admitted"
    assert second["admitted_count"] == 0


def test_admit_binds_existing_patch(tmp_path: Path) -> None:
    target = ua._proof_target(tmp_path)
    report = ua._proof_discovery_report(tmp_path / "disc", generator="footnote_defs")
    patch_rel = "patches/footnote-defs-complexity.patch"
    (target / patch_rel).write_text("--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\n+b\n", encoding="utf-8")

    result = ua.admit_discovery_findings(target, report, out_root=tmp_path / "out")
    assert result["ok"]
    assert result["admitted"][0]["patch"] == patch_rel
    assert not result["admitted"][0]["pending_patch"]


def test_unsealed_report_refused(tmp_path: Path) -> None:
    target = ua._proof_target(tmp_path)
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "report.json").write_text(
        json.dumps({
            "schema_version": 1,
            "target": {"name": "x", "version": "0"},
            "sdist_sha256": "c" * 64,
            "findings": [],
            "chain_digest": "x",
        }),
        encoding="utf-8",
    )
    with pytest.raises(ua.AdmissionRefused) as excinfo:
        ua.admit_discovery_findings(target, bad, out_root=tmp_path / "out")
    assert excinfo.value.verdict == "report_unsealed"


def test_tamper_detected(tmp_path: Path) -> None:
    target = ua._proof_target(tmp_path)
    report = ua._proof_discovery_report(tmp_path / "disc")
    result = ua.admit_discovery_findings(target, report, out_root=tmp_path / "out")
    receipt_path = Path(result["receipt_dir"]) / "receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["admission_digest"] = "0" * 64
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    verified = ua.verify_admission_receipt(Path(result["receipt_dir"]))
    assert not verified["ok"]
    assert "admission_digest" in verified["mismatched"]


def test_builtin_proof() -> None:
    result = ua.builtin_upstream_admission_proof()
    assert result["ok"]
    assert result["admitted"]
    assert result["idempotent"]
    assert result["patch_bound"]
    assert result["receipt_verified"]
    assert result["tamper_detected"]
    assert result["unsealed_refused"]
    assert not result["used_skill_route_discovery"]
