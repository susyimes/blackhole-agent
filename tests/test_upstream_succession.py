"""Unit tests for the upstream succession plane (hermetic; no network)."""

from __future__ import annotations

import json
from pathlib import Path

from blackhole_agent import upstream_fleet as uf
from blackhole_agent import upstream_succession as us


def test_builtin_proof_green() -> None:
    result = us.builtin_upstream_succession_proof()
    assert result["ok"]
    assert result["mandate_met"]
    assert result["refresh_promotes_terminals"]
    assert result["multi_epoch_progressed"]
    assert result["seal_verified"]
    assert result["tamper_detected"]
    assert result["budget_stops"]
    assert result["premet_short_circuits"]
    assert result["rank_only"]
    assert result["empty_refused"]
    assert result["custom_stop"]
    assert result["refresh_drives_rework"]
    assert not result["used_skill_route_discovery"]


def test_mandate_terminal_coverage_requires_all_patch_bound(tmp_path: Path) -> None:
    stew = tmp_path / "stew"
    stew.mkdir()
    uf._proof_target(
        stew,
        name="a",
        version="1.0.0",
        defects=[{
            "id": "a-1",
            "title": "a",
            "kind": "complexity",
            "patch": "patches/a.patch",
            "repro": "repros/a.py",
        }],
    )
    uf._proof_target(
        stew,
        name="b",
        version="2.0.0",
        defects=[{
            "id": "b-1",
            "title": "b",
            "kind": "complexity",
            "patch": "patches/b.patch",
            "repro": "repros/b.py",
        }],
    )
    partial = uf._proof_portfolio([{
        "name": "a",
        "version": "1.0.0",
        "defect_id": "a-1",
        "outcome": "impact_merged",
        "impact_digest": "a" * 64,
        "ok": True,
    }])
    cov = us.mandate_terminal_coverage(partial, stew)
    assert cov["required"] == 2
    assert cov["covered"] == 1
    assert not cov["met"]

    full = uf._proof_portfolio([
        {
            "name": "a",
            "version": "1.0.0",
            "defect_id": "a-1",
            "outcome": "impact_merged",
            "impact_digest": "a" * 64,
            "ok": True,
        },
        {
            "name": "b",
            "version": "2.0.0",
            "defect_id": "b-1",
            "outcome": "impact_released",
            "impact_digest": "b" * 64,
            "ok": True,
        },
    ])
    cov2 = us.mandate_terminal_coverage(full, stew)
    assert cov2["met"]
    assert cov2["coverage_ratio"] == 1.0


def test_default_refresh_promotes_open(tmp_path: Path) -> None:
    portfolio = uf._proof_portfolio([{
        "name": "x",
        "version": "1.0.0",
        "defect_id": "x-1",
        "outcome": "impact_open",
        "impact_digest": "d" * 64,
        "ok": True,
    }])
    refreshed = us.default_impact_refresh(portfolio, epoch_index=0)
    assert refreshed["entries"][0]["outcome"] == "impact_merged"
    assert refreshed["refresh_applied"][0]["from"] == "impact_open"
    assert refreshed["portfolio_digest"] != portfolio["portfolio_digest"]


def test_succession_meets_mandate_via_refresh(tmp_path: Path) -> None:
    stew = tmp_path / "stew"
    stew.mkdir()
    uf._proof_target(
        stew,
        name="solo",
        version="1.0.0",
        defects=[{
            "id": "solo-1",
            "title": "solo",
            "kind": "complexity",
            "patch": "patches/solo.patch",
            "repro": "repros/solo.py",
        }],
    )
    campaign = us._proof_campaign_runner(tmp_path / "camps")
    result = us.run_succession(
        stewardship_root=stew,
        portfolio=None,
        max_epochs=3,
        max_waves_per_epoch=2,
        per_wave_dispatch_limit=1,
        dispatch=True,
        campaign_runner=campaign,
        mandate_goal="terminal_coverage",
        out_root=tmp_path / "succ",
    )
    assert result["ok"]
    assert result["mandate_met"]
    assert result["stop_reason"] == "mandate_met"
    assert result["total_dispatched_ok"] >= 1
    # Inter-epoch refresh should have promoted open → merged.
    applied = []
    for ep in result["epochs"]:
        applied.extend(ep.get("refresh_applied") or [])
    assert any(a.get("to") == "impact_merged" for a in applied)


def test_verify_detects_digest_tamper(tmp_path: Path) -> None:
    stew = tmp_path / "stew"
    stew.mkdir()
    uf._proof_target(
        stew,
        name="m",
        version="1.0.0",
        defects=[{
            "id": "m-1",
            "title": "m",
            "kind": "correctness",
            "patch": "patches/m.patch",
            "repro": "repros/m.py",
        }],
    )
    portfolio = uf._proof_portfolio([{
        "name": "m",
        "version": "1.0.0",
        "defect_id": "m-1",
        "outcome": "impact_merged",
        "impact_digest": "d" * 64,
        "ok": True,
    }])
    result = us.run_succession(
        stewardship_root=stew,
        portfolio=portfolio,
        max_epochs=2,
        dispatch=False,
        mandate_goal="terminal_coverage",
        out_root=tmp_path / "succ",
    )
    assert result["mandate_met"]
    # Pre-met path may have zero epochs; seal still writes.
    assert us.verify_succession_receipt(Path(result["succession_dir"]))["ok"]
    path = Path(result["succession_dir"]) / "succession.json"
    receipt = json.loads(path.read_text(encoding="utf-8"))
    receipt["succession_digest"] = "0" * 64
    path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    checked = us.verify_succession_receipt(Path(result["succession_dir"]))
    assert not checked["ok"]
    assert "succession_digest" in (checked.get("mismatched") or [])


def test_dispatch_budget_caps_across_epochs(tmp_path: Path) -> None:
    stew = tmp_path / "stew"
    stew.mkdir()
    for i in range(3):
        uf._proof_target(
            stew,
            name=f"t{i}",
            version="1.0.0",
            defects=[{
                "id": f"d{i}",
                "title": f"d{i}",
                "kind": "complexity",
                "patch": f"patches/d{i}.patch",
                "repro": f"repros/d{i}.py",
            }],
        )
    campaign = us._proof_campaign_runner(tmp_path / "camps")
    result = us.run_succession(
        stewardship_root=stew,
        max_epochs=10,
        max_waves_per_epoch=1,
        per_wave_dispatch_limit=1,
        dispatch_budget=2,
        dispatch=True,
        campaign_runner=campaign,
        mandate_goal="none",
        refresh_promotions={},
        out_root=tmp_path / "succ",
    )
    assert result["total_dispatched"] == 2
    assert result["stop_reason"] == "dispatch_budget"
    assert result["epoch_count"] >= 2
