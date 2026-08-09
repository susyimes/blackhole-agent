"""Unit tests for the upstream institution plane (hermetic; no network)."""

from __future__ import annotations

import json
from pathlib import Path

from blackhole_agent import upstream_fleet as uf
from blackhole_agent import upstream_institution as ui
from blackhole_agent import upstream_program as up


def test_builtin_proof_green() -> None:
    result = ui.builtin_upstream_institution_proof()
    assert result["ok"]
    assert result["institution_met"]
    assert result["multi_program_progressed"]
    assert result["federation_coverage"]
    assert result["priority_scheduling"]
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


def test_normalize_institution_charter_dedupes_and_requires_work() -> None:
    charter = ui.normalize_institution_charter(
        [
            {
                "program_id": "a",
                "initial_targets": [
                    {
                        "name": "x",
                        "version": "1.0.0",
                        "defects": [{"id": "x-1"}],
                    }
                ],
            },
            {
                "program_id": "a",  # duplicate id ignored
                "initial_targets": [
                    {
                        "name": "y",
                        "version": "1.0.0",
                        "defects": [{"id": "y-1"}],
                    }
                ],
            },
            {
                "program_id": "empty",
                # no targets, no surface charter → dropped
            },
            {
                "program_id": "deferred-only",
                "surface_charter": [
                    {
                        "name": "z",
                        "version": "1.0.0",
                        "defects": [{"id": "z-1"}],
                    }
                ],
            },
        ]
    )
    ids = [c["program_id"] for c in charter]
    assert ids == ["a", "deferred-only"]
    assert charter[0]["initial_targets"][0]["name"] == "x"
    assert charter[1]["surface_charter"][0]["name"] == "z"


def test_federate_portfolios_later_wins() -> None:
    p1 = uf._proof_portfolio(
        [
            {
                "name": "a",
                "version": "1.0.0",
                "defect_id": "a-1",
                "outcome": "impact_open",
                "impact_digest": "a" * 64,
                "ok": True,
            }
        ]
    )
    p2 = uf._proof_portfolio(
        [
            {
                "name": "a",
                "version": "1.0.0",
                "defect_id": "a-1",
                "outcome": "impact_merged",
                "impact_digest": "b" * 64,
                "ok": True,
            },
            {
                "name": "b",
                "version": "1.0.0",
                "defect_id": "b-1",
                "outcome": "impact_merged",
                "impact_digest": "c" * 64,
                "ok": True,
            },
        ]
    )
    fed = ui.federate_portfolios([p1, p2])
    assert len(fed["entries"]) == 2
    by_key = {
        (e["name"], e["version"], e["defect_id"]): e["outcome"] for e in fed["entries"]
    }
    assert by_key[("a", "1.0.0", "a-1")] == "impact_merged"
    assert by_key[("b", "1.0.0", "b-1")] == "impact_merged"
    assert fed["portfolio_digest"]


def test_select_next_program_priority_and_fairness() -> None:
    states = [
        {"program_id": "low", "priority": 1, "program_met": False},
        {"program_id": "high", "priority": 5, "program_met": False},
        {"program_id": "done", "priority": 9, "program_met": True},
    ]
    selected = ui.select_next_program(states, [], round_index=0)
    assert selected is not None
    assert selected["program_id"] == "high"

    # Met programs are excluded.
    only_open = [
        {"program_id": "a", "priority": 1, "program_met": False},
        {"program_id": "b", "priority": 1, "program_met": False},
    ]
    s0 = ui.select_next_program(only_open, [], round_index=0)
    s1 = ui.select_next_program(only_open, [], round_index=1)
    assert s0 is not None and s1 is not None
    assert {s0["program_id"], s1["program_id"]} == {"a", "b"}
    assert s0["program_id"] != s1["program_id"]


def test_allocate_program_budget_split_and_boost() -> None:
    assert ui.allocate_program_budget(
        remaining_budget=None,
        open_program_count=2,
        selected={"program_id": "a"},
        roi_history=[],
    ) is None
    assert (
        ui.allocate_program_budget(
            remaining_budget=0,
            open_program_count=2,
            selected={"program_id": "a"},
            roi_history=[],
        )
        == 0
    )
    even = ui.allocate_program_budget(
        remaining_budget=4,
        open_program_count=2,
        selected={"program_id": "a"},
        roi_history=[],
    )
    assert even == 2
    boosted = ui.allocate_program_budget(
        remaining_budget=4,
        open_program_count=2,
        selected={"program_id": "a"},
        roi_history=[
            {
                "program_id": "a",
                "dispatched_ok": 2,
                "efficiency": 1.0,
                "covered_delta": 2,
                "coverage_delta": 0.5,
            }
        ],
    )
    assert boosted is not None and boosted >= even


def test_score_program_roi_efficiency() -> None:
    roi = ui.score_program_roi(
        round_index=0,
        program_id="lane-a",
        program_result={
            "total_dispatched": 2,
            "total_dispatched_ok": 2,
            "stop_reason": "program_met",
            "program_met": True,
            "program_digest": "d" * 64,
            "succession_count": 1,
        },
        coverage_before={"coverage_ratio": 0.0, "covered": 0, "required": 2},
        coverage_after={"coverage_ratio": 1.0, "covered": 2, "required": 2},
    )
    assert roi["covered_delta"] == 2
    assert roi["efficiency"] == 1.0
    assert roi["program_met"] is True


def test_durable_state_roundtrip(tmp_path: Path) -> None:
    state = ui._state_payload(
        institution_id="i1",
        round_count=1,
        total_dispatched=2,
        total_dispatched_ok=2,
        federated_portfolio={"entries": [], "portfolio_digest": "x" * 64},
        roi_history=[{"program_id": "a", "efficiency": 1.0}],
        program_states=[{"program_id": "a", "program_met": False}],
        program_digests=["d" * 64],
        charter=[{"program_id": "a"}],
        stop_reason=None,
        institution_goal="all_programs_met",
    )
    path = ui.write_institution_state(tmp_path, state)
    assert path.is_file()
    loaded = ui.load_institution_state(tmp_path)
    assert loaded["institution_id"] == "i1"
    assert loaded["round_count"] == 1
    assert loaded["program_states"][0]["program_id"] == "a"


def test_admit_program_slot_materializes_surface(tmp_path: Path) -> None:
    slot = {
        "program_id": "lane-x",
        "priority": 1,
        "initial_targets": [
            {
                "name": "pkg",
                "version": "1.0.0",
                "defects": [
                    {
                        "id": "pkg-1",
                        "title": "pkg",
                        "kind": "complexity",
                        "patch": "patches/pkg-1.patch",
                        "repro": "repros/pkg-1.py",
                    }
                ],
            }
        ],
        "surface_charter": [],
        "max_successions": 2,
        "program_goal": "terminal_coverage",
        "mandate_goal": "terminal_coverage",
    }
    admission = ui.admit_program_slot(institution_dir=tmp_path, slot=slot)
    stew = Path(admission["stewardship_root"])
    assert stew.is_dir()
    keys = up.inventory_defect_keys(stew)
    assert ("pkg", "1.0.0", "pkg-1") in keys


def test_empty_charter_refuses(tmp_path: Path) -> None:
    try:
        ui.run_institution(
            charter=[],
            dispatch=False,
            institution_goal="none",
            out_root=tmp_path / "empty",
        )
        raise AssertionError("expected InstitutionRefused")
    except ui.InstitutionRefused as exc:
        assert exc.verdict == "institution_empty"


def test_verify_detects_missing_receipt(tmp_path: Path) -> None:
    result = ui.verify_institution_receipt(tmp_path)
    assert not result["ok"]
    assert result["verdict"] == "receipt_missing"
