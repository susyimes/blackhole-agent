"""Unit tests for the upstream campaign plane (hermetic; no network)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from blackhole_agent import upstream_campaign as camp
from blackhole_agent import upstream_contribution as uc
from blackhole_agent import upstream_publication as up


def test_empty_defects_refused(tmp_path: Path) -> None:
    target = tmp_path / "empty"
    target.mkdir()
    (target / "manifest.json").write_text(
        json.dumps({
            "schema_version": 1,
            "name": "empty",
            "version": "0.0.1",
            "upstream_repo": "https://github.com/proof/empty",
            "defects": [],
        }),
        encoding="utf-8",
    )
    with pytest.raises(camp.CampaignRefused) as excinfo:
        camp.run_campaign(target, stages=("contribution",), out_root=tmp_path / "out")
    assert excinfo.value.verdict == "no_defects"


def test_unknown_stage_refused(tmp_path: Path) -> None:
    target = uc._proof_target(tmp_path / "stewardship")
    with pytest.raises(camp.CampaignRefused) as excinfo:
        camp.run_campaign(target, stages=("teleport",), out_root=tmp_path / "out")
    assert excinfo.value.verdict == "stages_unknown"


def test_repair_failure_aborts_before_contribution(tmp_path: Path) -> None:
    target = uc._proof_target(tmp_path / "stewardship")
    calls = {"n": 0}

    def red(_td: Path) -> dict:
        return {"ok": False, "error": "red", "repair_score": 0.0}

    def builder(*_a, **_k):
        calls["n"] += 1
        raise AssertionError("must not contribute")

    result = camp.run_campaign(
        target,
        stages=("repair", "contribution"),
        skip_repair_if_green=False,
        repair_runner=red,
        contribution_builder=builder,
        out_root=tmp_path / "out",
    )
    assert not result["ok"]
    assert result["verdict"] == "repair_failed"
    assert calls["n"] == 0
    assert "contribution" not in result["stage_results"]
    verified = camp.verify_campaign_receipt(Path(result["campaign_dir"]))
    assert verified["ok"]


def test_full_campaign_seals_verifiable_receipt(tmp_path: Path) -> None:
    target = uc._proof_target(tmp_path / "stewardship")
    repo_url = "https://github.com/proof/contribprobe"
    head_url = uc.github_archive_url(repo_url, "HEAD")
    tag_archive = uc._proof_archive(uc._PROOF_INIT_BUGGY)

    def fetcher(url: str) -> bytes:
        if url == head_url:
            return uc._proof_archive(uc._PROOF_INIT_BUGGY, top=f"{uc._PROOF_PKG}-HEAD")
        return tag_archive

    def repair_green(_td: Path) -> dict:
        report_dir = tmp_path / "repair-report"
        report_dir.mkdir(parents=True, exist_ok=True)
        report = {
            "ok": True,
            "repair_score": 1.0,
            "repaired_count": 1,
            "defect_count": 1,
            "report_digest": "b" * 64,
            "report_dir": str(report_dir),
        }
        (report_dir / "report.json").write_text(json.dumps(report), encoding="utf-8")
        return report

    _, fork = up._proof_remotes(tmp_path / "remotes", up._PROOF_SOURCE_V1)
    gh = up._FakeGh(fork)

    def publisher(bundle_dir: Path, **kwargs):
        pub_bundle = up._proof_write_bundle(
            tmp_path / "pub" / Path(bundle_dir).name,
            patch=up._PROOF_PATCH,
            test_text=up._PROOF_TEST,
            repro_text=up._PROOF_REPRO,
        )
        return up.publish_contribution(
            pub_bundle,
            publish=True,
            gh=gh,
            verifier=up._proof_verifier,
            manifest={"contribution": {"tests_subdir": "tests"}},
            out_root=kwargs.get("out_root") or (tmp_path / "pub-receipts"),
        )

    result = camp.run_campaign(
        target,
        stages=("repair", "contribution", "publication"),
        publish=True,
        skip_repair_if_green=False,
        repair_runner=repair_green,
        fetcher=fetcher,
        publisher=publisher,
        contribution_out_root=tmp_path / "contrib",
        publication_out_root=tmp_path / "pub-receipts",
        out_root=tmp_path / "campaigns",
    )
    assert result["ok"]
    assert result["verdict"] == "published"
    assert result["stage_results"]["contribution"]["submittable_count"] == 1
    assert result["stage_results"]["publication"]["published_count"] == 1
    verified = camp.verify_campaign_receipt(Path(result["campaign_dir"]))
    assert verified["ok"]
    assert verified["campaign_digest"] == result["campaign_digest"]


def test_already_fixed_short_circuits_publication(tmp_path: Path) -> None:
    target = uc._proof_target(tmp_path / "stewardship")
    repo_url = "https://github.com/proof/contribprobe"
    head_url = uc.github_archive_url(repo_url, "HEAD")
    tag_archive = uc._proof_archive(uc._PROOF_INIT_BUGGY)

    def fetcher(url: str) -> bytes:
        if url == head_url:
            return uc._proof_archive(uc._PROOF_INIT_FIXED, top=f"{uc._PROOF_PKG}-HEAD")
        return tag_archive

    result = camp.run_campaign(
        target,
        stages=("contribution", "publication"),
        publish=True,
        fetcher=fetcher,
        contribution_out_root=tmp_path / "contrib",
        out_root=tmp_path / "campaigns",
    )
    assert result["ok"]
    assert result["verdict"] == "all_already_fixed"
    assert result["stage_results"]["publication"]["verdict"] == "nothing_to_publish"
    assert camp.verify_campaign_receipt(Path(result["campaign_dir"]))["ok"]


def test_tamper_breaks_campaign_seal(tmp_path: Path) -> None:
    target = uc._proof_target(tmp_path / "stewardship")
    repo_url = "https://github.com/proof/contribprobe"
    head_url = uc.github_archive_url(repo_url, "HEAD")
    tag_archive = uc._proof_archive(uc._PROOF_INIT_BUGGY)

    def fetcher(url: str) -> bytes:
        if url == head_url:
            return uc._proof_archive(uc._PROOF_INIT_BUGGY, top=f"{uc._PROOF_PKG}-HEAD")
        return tag_archive

    result = camp.run_campaign(
        target,
        stages=("contribution",),
        fetcher=fetcher,
        contribution_out_root=tmp_path / "contrib",
        out_root=tmp_path / "campaigns",
    )
    assert result["ok"]
    receipt_path = Path(result["campaign_dir"]) / "receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["campaign_digest"] = "0" * 64
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    tampered = camp.verify_campaign_receipt(Path(result["campaign_dir"]))
    assert not tampered["ok"]
    assert "campaign_digest" in tampered["mismatched"]


def test_builtin_proof_passes() -> None:
    result = camp.builtin_upstream_campaign_proof()
    assert result["ok"]
    assert result["campaign_published"]
    assert result["receipt_verified"]
    assert result["tamper_detected"]
    assert result["already_fixed_short_circuit"]
    assert result["repair_failure_aborts"]
    assert result["empty_defects_refused"]
    assert result["dry_run_gated"]
    assert result["full_loop_discovery_admit"]
    assert result["impact_stage_chained"]
    assert result["impact_nothing_to_assess"]
    assert not result["used_skill_route_discovery"]


def test_impact_stage_after_publication(tmp_path: Path) -> None:
    from blackhole_agent import upstream_impact as ui

    target = uc._proof_target(tmp_path / "stewardship")
    repo_url = "https://github.com/proof/contribprobe"
    head_url = uc.github_archive_url(repo_url, "HEAD")
    tag_archive = uc._proof_archive(uc._PROOF_INIT_BUGGY)

    def fetcher(url: str) -> bytes:
        if url == head_url:
            return uc._proof_archive(uc._PROOF_INIT_BUGGY, top=f"{uc._PROOF_PKG}-HEAD")
        return tag_archive

    _, fork = up._proof_remotes(tmp_path / "remotes", up._PROOF_SOURCE_V1)
    gh = up._FakeGh(fork)

    def publisher(bundle_dir: Path, **kwargs):
        pub_bundle = up._proof_write_bundle(
            tmp_path / "pub" / Path(bundle_dir).name,
            patch=up._PROOF_PATCH,
            test_text=up._PROOF_TEST,
            repro_text=up._PROOF_REPRO,
        )
        return up.publish_contribution(
            pub_bundle,
            publish=True,
            gh=gh,
            verifier=up._proof_verifier,
            manifest={"contribution": {"tests_subdir": "tests"}},
            out_root=kwargs.get("out_root") or (tmp_path / "pub-receipts"),
        )

    def impact_assessor(receipt_dir: Path, **kwargs):
        receipt = json.loads((Path(receipt_dir) / "receipt.json").read_text(encoding="utf-8"))
        pr = receipt.get("pull_request") or {}
        number = int(pr.get("number") or 0)
        head = str(receipt.get("head_sha") or pr.get("headRefOid") or "")
        fake = ui._FakeImpactGh({
            ("proof/pubprobe", number): {
                "number": number,
                "url": pr.get("url"),
                "state": "OPEN",
                "headRefOid": head,
                "mergedAt": None,
                "closedAt": None,
                "title": "t",
                "baseRefName": "main",
            }
        })
        return ui.assess_publication_impact(
            receipt_dir, gh=fake, out_root=kwargs.get("out_root") or (tmp_path / "impact")
        )

    result = camp.run_campaign(
        target,
        stages=("contribution", "publication", "impact"),
        publish=True,
        fetcher=fetcher,
        publisher=publisher,
        impact_assessor=impact_assessor,
        contribution_out_root=tmp_path / "contrib",
        publication_out_root=tmp_path / "pub-receipts",
        impact_out_root=tmp_path / "impact",
        out_root=tmp_path / "campaigns",
    )
    assert result["ok"]
    assert result["verdict"] == "impact_open"
    impact = result["stage_results"]["impact"]
    assert impact["assessed_count"] == 1
    assert impact["outcomes"]["impact_open"] == 1
    verified = camp.verify_campaign_receipt(Path(result["campaign_dir"]))
    assert verified["ok"]
    receipt = json.loads(
        (Path(result["campaign_dir"]) / "receipt.json").read_text(encoding="utf-8")
    )
    assert any(k.startswith("impact.") for k in receipt["stage_digests"])


def test_full_loop_discovery_admit_pending_patch(tmp_path: Path) -> None:
    from blackhole_agent import upstream_admission as ua

    target = ua._proof_target(tmp_path / "stewardship")
    sealed = ua._proof_discovery_report(tmp_path / "disc")

    def discovery_inject(_td: Path) -> dict:
        return {
            "ok": True,
            "report_dir": str(sealed),
            "finding_count": 1,
            "findings": [{"generator": "nested_link", "flagged": True, "kind": "complexity"}],
        }

    result = camp.run_campaign(
        target,
        stages=("discovery", "admit", "repair"),
        discovery_runner=discovery_inject,
        admission_out_root=tmp_path / "admission",
        out_root=tmp_path / "campaigns",
    )
    assert result["ok"]
    assert result["stage_results"]["discovery"]["ok"]
    assert result["stage_results"]["admit"]["admitted_count"] == 1
    assert result["stage_results"]["repair"]["verdict"] == "no_patch_bound_defects"
    assert camp.verify_campaign_receipt(Path(result["campaign_dir"]))["ok"]
    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    assert any(d.get("pending_patch") for d in manifest["defects"])
