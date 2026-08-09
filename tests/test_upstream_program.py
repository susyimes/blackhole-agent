"""Unit tests for the upstream program plane (hermetic; no network)."""

from __future__ import annotations

import json
from pathlib import Path

from blackhole_agent import upstream_fleet as uf
from blackhole_agent import upstream_program as up


def test_builtin_proof_green() -> None:
    result = up.builtin_upstream_program_proof()
    assert result["ok"]
    assert result["program_met"]
    assert result["surface_expand_reopens_mandate"]
    assert result["charter_surface_expand"]
    assert result["multi_succession_progressed"]
    assert result["seal_verified"]
    assert result["tamper_detected"]
    assert result["budget_stops"]
    assert result["premet_short_circuits"]
    assert result["rank_only"]
    assert result["empty_refused"]
    assert result["custom_stop"]
    assert result["durable_resume"]
    assert result["roi_scored"]
    assert not result["used_skill_route_discovery"]


def test_program_terminal_coverage_tracks_surface(tmp_path: Path) -> None:
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
    partial = uf._proof_portfolio([{
        "name": "a",
        "version": "1.0.0",
        "defect_id": "a-1",
        "outcome": "impact_merged",
        "impact_digest": "a" * 64,
        "ok": True,
    }])
    cov = up.program_terminal_coverage(partial, stew)
    assert cov["required"] == 1
    assert cov["met"]

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
    cov2 = up.program_terminal_coverage(partial, stew)
    assert cov2["required"] == 2
    assert not cov2["met"]
    assert cov2["covered"] == 1


def test_score_succession_roi_efficiency() -> None:
    roi = up.score_succession_roi(
        succession_index=0,
        succession_result={
            "total_dispatched": 2,
            "total_dispatched_ok": 2,
            "stop_reason": "mandate_met",
            "mandate_met": True,
            "succession_digest": "d" * 64,
        },
        coverage_before={"coverage_ratio": 0.0, "covered": 0, "required": 2},
        coverage_after={"coverage_ratio": 1.0, "covered": 2, "required": 2},
        surface_added=0,
    )
    assert roi["covered_delta"] == 2
    assert roi["efficiency"] == 1.0
    assert roi["mandate_met"] is True


def test_durable_state_roundtrip(tmp_path: Path) -> None:
    state = up._state_payload(
        program_id="p1",
        succession_count=1,
        total_dispatched=2,
        total_dispatched_ok=2,
        portfolio={"portfolio_digest": "x" * 64, "entries": []},
        roi_history=[{"succession_index": 0, "dispatched_ok": 2}],
        required_keys=[("a", "1.0.0", "a-1")],
        succession_digests=["s" * 64],
        stop_reason=None,
        program_goal="terminal_and_exhausted",
    )
    path = up.write_program_state(tmp_path, state)
    assert path.is_file()
    loaded = up.load_program_state(tmp_path)
    assert loaded["program_id"] == "p1"
    assert loaded["succession_count"] == 1
    assert loaded["total_dispatched_ok"] == 2


def test_verify_detects_missing_receipt(tmp_path: Path) -> None:
    result = up.verify_program_receipt(tmp_path)
    assert not result["ok"]
    assert result["verdict"] == "receipt_missing"


def test_charter_surface_expand_materializes(tmp_path: Path) -> None:
    stew = tmp_path / "stew"
    stew.mkdir()
    uf._proof_target(
        stew,
        name="seed",
        version="1.0.0",
        defects=[{
            "id": "seed-1",
            "title": "seed",
            "kind": "complexity",
            "patch": "patches/seed.patch",
            "repro": "repros/seed.py",
        }],
    )
    charter = [
        {
            "name": "wave2",
            "version": "1.0.0",
            "defects": [{
                "id": "wave2-1",
                "title": "wave2",
                "kind": "complexity",
                "patch": "patches/wave2.patch",
                "repro": "repros/wave2.py",
            }],
        }
    ]
    campaign = up._proof_campaign_runner(tmp_path / "camp")
    result = up.run_program(
        stewardship_root=stew,
        portfolio=None,
        max_successions=4,
        max_epochs_per_succession=2,
        max_waves_per_epoch=2,
        per_wave_dispatch_limit=1,
        dispatch_budget=4,
        dispatch=True,
        campaign_runner=campaign,
        surface_charter=charter,
        program_goal="terminal_and_exhausted",
        mandate_goal="terminal_coverage",
        out_root=tmp_path / "prog-charter",
    )
    assert result["ok"]
    assert result["program_met"]
    assert result["succession_count"] >= 2
    assert "wave2@1.0.0" in (result.get("charter_applied") or [])
    assert any(
        e.get("detail") == "charter_materialize"
        for e in (result.get("surface_expansions") or [])
    )
    keys = up.inventory_defect_keys(stew)
    assert ("wave2", "1.0.0", "wave2-1") in keys
    state = json.loads(
        (Path(result["program_dir"]) / "program_state.json").read_text(encoding="utf-8")
    )
    assert "wave2@1.0.0" in state.get("charter_applied", [])
    assert state.get("surface_charter")


def test_surface_expand_reopens_coverage(tmp_path: Path) -> None:
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
    portfolio = uf._proof_portfolio([{
        "name": "solo",
        "version": "1.0.0",
        "defect_id": "solo-1",
        "outcome": "impact_merged",
        "impact_digest": "b" * 64,
        "ok": True,
    }])
    assert up.program_terminal_coverage(portfolio, stew)["met"]

    expand_done = {"n": 0}

    def expand_once(**kw):
        expand_done["n"] += 1
        if expand_done["n"] == 1:
            uf._proof_target(
                stew,
                name="next",
                version="1.0.0",
                defects=[{
                    "id": "next-1",
                    "title": "next",
                    "kind": "complexity",
                    "patch": "patches/next.patch",
                    "repro": "repros/next.py",
                }],
            )
            return {
                "added_keys": [
                    {"name": "next", "version": "1.0.0", "defect_id": "next-1"}
                ],
                "detail": "add_next",
                "expanded": True,
            }
        return {"added_keys": [], "detail": "noop", "expanded": False}

    campaign = up._proof_campaign_runner(tmp_path / "camp")
    result = up.run_program(
        stewardship_root=stew,
        portfolio=portfolio,
        max_successions=3,
        max_epochs_per_succession=2,
        max_waves_per_epoch=2,
        per_wave_dispatch_limit=1,
        dispatch_budget=4,
        dispatch=True,
        campaign_runner=campaign,
        surface_expand_runner=expand_once,
        program_goal="terminal_and_exhausted",
        mandate_goal="terminal_coverage",
        out_root=tmp_path / "prog",
    )
    assert result["ok"]
    assert result["program_met"]
    assert result["succession_count"] >= 1
    assert expand_done["n"] >= 1
    assert float((result.get("coverage_end") or {}).get("coverage_ratio") or 0) == 1.0
    # Seal verifies.
    verified = up.verify_program_receipt(Path(result["program_dir"]))
    assert verified["ok"]
    # State persisted.
    state = json.loads(
        (Path(result["program_dir"]) / "program_state.json").read_text(encoding="utf-8")
    )
    assert state["program_id"] == result["program_id"]
