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
    discover_targets,
    extract_sdist,
    load_target,
    parse_unified_diff,
    run_all_campaigns,
    run_repair_campaign,
    run_repro,
    verify_repair_report,
    verify_sdist,
)

TARGET_320 = upstream_repair.STEWARDSHIP_ROOT / "mistune-3.2.0"
TARGET_321 = upstream_repair.STEWARDSHIP_ROOT / "mistune-3.2.1"
ARTIFACT_DIR = upstream_repair.ARTIFACT_DIR


def test_target_discovery_finds_all_manifests() -> None:
    roots = discover_targets()
    names = [p.name for p in roots]
    assert "mistune-3.2.0" in names
    assert "mistune-3.2.1" in names
    assert len(names) >= 2


def test_manifest_sdist_provenance_matches_published_digests() -> None:
    expected = {
        "mistune-3.2.0": "708487c8a8cdd99c9d90eb3ed4c3ed961246ff78ac82f03418f5183ab70e398a",
        "mistune-3.2.1": "7c8e5501d38bac1582e067e46c8343f17d57ea1aaa735823f3aba1fd59c88a28",
    }
    for root in (TARGET_320, TARGET_321):
        target = load_target(root)
        verdict = verify_sdist(target)
        assert verdict["ok"], verdict
        assert verdict["actual"] == expected[root.name]
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


def test_apply_patch_text_creates_new_files(tmp_path: Path) -> None:
    diff = "--- a/added.py\n+++ b/added.py\n@@ -0,0 +1,2 @@\n+one\n+two\n"
    touched = apply_patch_text(tmp_path, diff)
    assert touched == ["added.py"]
    assert (tmp_path / "added.py").read_text() == "one\ntwo"


def test_real_patches_apply_to_pristine_tree(tmp_path: Path) -> None:
    for root in (TARGET_320, TARGET_321):
        target = load_target(root)
        tree = extract_sdist(target, tmp_path / root.name)
        for defect in target.defects:
            apply_patch_text(tree, defect.patch.read_text(encoding="utf-8"))
    helpers = (tmp_path / "mistune-3.2.0/mistune-3.2.0/src/mistune/helpers.py").read_text(encoding="utf-8")
    assert '[^"\\\\\\x00]' in helpers  # ReDoS fix present
    toc = (tmp_path / "mistune-3.2.1/mistune-3.2.1/src/mistune/toc.py").read_text(encoding="utf-8")
    assert "_unique_id" in toc  # collision fix present


def test_repro_discriminates_pristine_vs_repaired(tmp_path: Path) -> None:
    cases = [(TARGET_320, "math-xss"), (TARGET_321, "math-currency-crossline")]
    for root, defect_id in cases:
        target = load_target(root)
        defect = next(d for d in target.defects if d.id == defect_id)
        pristine = extract_sdist(target, tmp_path / f"{root.name}-pristine")
        assert run_repro(defect, pristine, target.manifest)["exit_code"] != 0
        repaired = extract_sdist(target, tmp_path / f"{root.name}-repaired")
        apply_patch_text(repaired, defect.patch.read_text(encoding="utf-8"))
        assert run_repro(defect, repaired, target.manifest)["exit_code"] == 0


@pytest.mark.slow
def test_full_campaign_and_tamper_falsification() -> None:
    report = run_repair_campaign(TARGET_320)
    assert report["ok"], json.dumps(report, indent=2)[:2000]
    assert report["repair_score"] == 1.0
    assert report["repaired_count"] == report["defect_count"] == 9
    assert report["suites"]["pristine"]["exit_code"] == 0
    assert report["suites"]["repaired"]["exit_code"] == 0

    report_dir = Path(report["report_dir"])
    verdict = verify_repair_report(report_dir, TARGET_320)
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
    assert not verify_repair_report(tamper_dir, TARGET_320)["ok"]


@pytest.mark.slow
def test_second_release_repaired_end_to_end() -> None:
    report = run_repair_campaign(TARGET_321)
    assert report["ok"], json.dumps(report, indent=2)[:2000]
    assert report["repair_score"] == 1.0
    assert report["repaired_count"] == report["defect_count"] == 7
    # repaired suite additionally runs upstream's own added security tests
    assert report["suites"]["repaired"]["passed"] > report["suites"]["pristine"]["passed"]
    verdict = verify_repair_report(Path(report["report_dir"]), TARGET_321)
    assert verdict["ok"], verdict


@pytest.mark.slow
def test_builtin_proof_green_across_targets() -> None:
    result = builtin_upstream_repair_proof()
    assert result["ok"], {k: v for k, v in result.items() if k != "targets"}
    assert result["target_count"] >= 2
    assert result["repaired_count"] == result["defect_count"]
    assert result["tamper_detected"] and result["verified"] and result["suite_green"]
    assert not result["used_skill_route_discovery"]
    assert run_all_campaigns.__module__ == "blackhole_agent.upstream_repair"
