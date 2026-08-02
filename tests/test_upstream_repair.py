"""Tests for the upstream repair plane (real-release security stewardship)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from blackhole_agent import upstream_repair
from blackhole_agent.upstream_repair import (
    apply_file_patch,
    apply_patch_text,
    builtin_upstream_repair_proof,
    extract_sdist,
    load_target,
    parse_unified_diff,
    run_repair_campaign,
    run_repro,
    verify_repair_report,
    verify_sdist,
)

TARGET_ROOT = upstream_repair.TARGET_ROOT
ARTIFACT_DIR = upstream_repair.ARTIFACT_DIR


def test_manifest_sdist_provenance_matches_pypi_digest() -> None:
    target = load_target()
    verdict = verify_sdist(target)
    assert verdict["ok"], verdict
    assert verdict["actual"] == "708487c8a8cdd99c9d90eb3ed4c3ed961246ff78ac82f03418f5183ab70e398a"
    assert len(target.defects) == 9
    for defect in target.defects:
        assert defect.repro.is_file(), defect.id
        assert defect.patch.is_file(), defect.id


def test_unified_diff_parser_counts_bound_hunk_bodies() -> None:
    # a '--- ' file header directly after a hunk must not be swallowed as a removal
    text = (
        "--- a/f1.txt\n+++ b/f1.txt\n@@ -1,2 +1,2 @@\n-old\n+new\n keep\n"
        "--- a/f2.txt\n+++ b/f2.txt\n@@ -1 +1 @@\n-x\n+y\n"
    )
    patches = parse_unified_diff(text)
    assert [p.path for p in patches] == ["f1.txt", "f2.txt"]
    assert patches[0].hunks[0].lines == ("-old", "+new", " keep")


def test_apply_file_patch_strict_context() -> None:
    original = "alpha\nbeta\ngamma\n"
    (patch,) = parse_unified_diff("--- a/f\n+++ b/f\n@@ -2,1 +2,1 @@\n-beta\n+BETA\n")
    assert apply_file_patch(original, patch) == "alpha\nBETA\ngamma\n"
    (bad,) = parse_unified_diff("--- a/f\n+++ b/f\n@@ -2,1 +2,1 @@\n-delta\n+DELTA\n")
    with pytest.raises(ValueError, match="context mismatch"):
        apply_file_patch(original, bad)


def test_real_patches_apply_to_pristine_tree(tmp_path: Path) -> None:
    target = load_target()
    tree = extract_sdist(target, tmp_path / "tree")
    for defect in target.defects:
        apply_patch_text(tree, defect.patch.read_text(encoding="utf-8"))
    helpers = (tree / "mistune-3.2.0/src/mistune/helpers.py").read_text(encoding="utf-8")
    assert '[^"\\\\\\x00]' in helpers  # ReDoS fix present
    html = (tree / "mistune-3.2.0/src/mistune/renderers/html.py").read_text(encoding="utf-8")
    assert 'id="\' + escape_text(_id)' in html or 'escape_text(_id)' in html


def test_repro_discriminates_pristine_vs_repaired(tmp_path: Path) -> None:
    target = load_target()
    defect = next(d for d in target.defects if d.id == "math-xss")
    pristine = extract_sdist(target, tmp_path / "pristine")
    assert run_repro(defect, pristine, target.manifest)["exit_code"] != 0
    repaired = extract_sdist(target, tmp_path / "repaired")
    apply_patch_text(repaired, defect.patch.read_text(encoding="utf-8"))
    assert run_repro(defect, repaired, target.manifest)["exit_code"] == 0


@pytest.mark.slow
def test_full_campaign_and_tamper_falsification() -> None:
    report = run_repair_campaign()
    assert report["ok"], json.dumps(report, indent=2)[:2000]
    assert report["repair_score"] == 1.0
    assert report["repaired_count"] == report["defect_count"] == 9
    assert report["suites"]["pristine"]["exit_code"] == 0
    assert report["suites"]["repaired"]["exit_code"] == 0

    report_dir = Path(report["report_dir"])
    verdict = verify_repair_report(report_dir)
    assert verdict["ok"], verdict

    # tamper: one flipped outcome must fail verification
    from blackhole_agent.capability_compounder import atomic_write_json
    from blackhole_agent.durable_state import durable_read_path

    tampered = json.loads(durable_read_path(report_dir / "report.json").read_text(encoding="utf-8"))
    tampered["defects"][0]["repaired_exit"] = 1
    tamper_dir = report_dir.parent / "pytest-tamper"
    if tamper_dir.exists():
        shutil.rmtree(tamper_dir)
    tamper_dir.mkdir(parents=True)
    atomic_write_json(tamper_dir / "report.json", tampered)
    assert not verify_repair_report(tamper_dir)["ok"]


@pytest.mark.slow
def test_builtin_proof_green() -> None:
    result = builtin_upstream_repair_proof()
    assert result["ok"], result
    assert result["tamper_detected"] and result["verified"] and result["suite_green"]
    assert not result["used_skill_route_discovery"]
