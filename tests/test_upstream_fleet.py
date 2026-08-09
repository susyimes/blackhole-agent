"""Unit tests for the upstream fleet plane (hermetic; no network)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from blackhole_agent import upstream_fleet as uf


def test_builtin_proof_green() -> None:
    result = uf.builtin_upstream_fleet_proof()
    assert result["ok"]
    assert result["inventory_ranked"]
    assert result["rework_outranks"]
    assert result["plan_verified"]
    assert result["tamper_detected"]
    assert result["dispatch_chained"]
    assert result["empty_refused"]
    assert result["monitor_only"]
    assert result["portfolio_assessed_path"]
    assert not result["used_skill_route_discovery"]


def test_rework_outranks_campaign_and_discover(tmp_path: Path) -> None:
    stew = tmp_path / "stewardship"
    stew.mkdir()
    uf._proof_target(
        stew,
        name="a",
        version="1.0.0",
        defects=[{
            "id": "a-closed",
            "title": "a",
            "kind": "complexity",
            "patch": "patches/a.patch",
            "repro": "repros/a.py",
        }],
    )
    uf._proof_target(stew, name="b", version="2.0.0", defects=[])
    uf._proof_target(
        stew,
        name="c",
        version="3.0.0",
        defects=[{
            "id": "c-ready",
            "title": "c",
            "kind": "complexity",
            "patch": "patches/c.patch",
            "repro": "repros/c.py",
        }],
    )
    portfolio = uf._proof_portfolio([{
        "name": "a",
        "version": "1.0.0",
        "defect_id": "a-closed",
        "outcome": "impact_closed_unmerged",
        "impact_digest": "a" * 64,
        "ok": True,
    }])
    actions = uf.rank_fleet_actions(uf.inventory_targets(stew), portfolio)
    assert actions[0]["action"] == "rework_closed_unmerged"
    assert actions[0]["priority"] < uf.ACTION_PRIORITY["campaign_patch_bound"]
    assert actions[0]["priority"] < uf.ACTION_PRIORITY["discover_empty"]
    kinds = {a["action"] for a in actions}
    assert "campaign_patch_bound" in kinds
    assert "discover_empty" in kinds


def test_terminal_success_not_campaignable(tmp_path: Path) -> None:
    stew = tmp_path / "stewardship"
    stew.mkdir()
    uf._proof_target(
        stew,
        name="m",
        version="1.0.0",
        defects=[{
            "id": "m-merged",
            "title": "m",
            "kind": "correctness",
            "patch": "patches/m.patch",
            "repro": "repros/m.py",
        }],
    )
    portfolio = uf._proof_portfolio([{
        "name": "m",
        "version": "1.0.0",
        "defect_id": "m-merged",
        "outcome": "impact_merged",
        "impact_digest": "b" * 64,
        "ok": True,
    }])
    actions = uf.rank_fleet_actions(uf.inventory_targets(stew), portfolio)
    assert len(actions) == 1
    assert actions[0]["action"] == "done_merged"
    assert actions[0]["campaignable"] is False


def test_empty_fleet_refused(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(uf.FleetRefused) as excinfo:
        uf.plan_fleet(stewardship_root=empty, out_root=tmp_path / "out")
    assert excinfo.value.verdict == "fleet_empty"


def test_plan_seal_and_tamper(tmp_path: Path) -> None:
    stew = tmp_path / "stewardship"
    stew.mkdir()
    uf._proof_target(
        stew,
        name="z",
        version="1.0.0",
        defects=[{
            "id": "z-ready",
            "title": "z",
            "kind": "complexity",
            "patch": "patches/z.patch",
            "repro": "repros/z.py",
        }],
    )
    result = uf.plan_fleet(
        stewardship_root=stew,
        dispatch=False,
        out_root=tmp_path / "plans",
    )
    assert result["ok"]
    plan_dir = Path(result["plan_dir"])
    assert uf.verify_fleet_plan(plan_dir)["ok"]

    plan_path = plan_dir / "plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    plan["actions_digest"] = "0" * 64
    plan_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    checked = uf.verify_fleet_plan(plan_dir)
    assert not checked["ok"]
    assert "actions_digest" in checked["mismatched"]
