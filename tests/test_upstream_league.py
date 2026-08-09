"""Unit tests for the upstream league plane (hermetic; no network)."""

from __future__ import annotations

import json
from pathlib import Path

from blackhole_agent import upstream_fleet as uf
from blackhole_agent import upstream_league as ul
from blackhole_agent import upstream_program as up


def test_builtin_proof_green() -> None:
    result = ul.builtin_upstream_league_proof()
    assert result["ok"], result.get("flags")
    assert result["league_met"]
    assert result["multi_institution_progressed"]
    assert result["federation_coverage"]
    assert result["priority_scheduling"]
    assert result["deferred_admission"]
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


def test_normalize_league_charter_dedupes_and_requires_work() -> None:
    charter = ul.normalize_league_charter(
        [
            {
                "institution_id": "a",
                "charter": [
                    {
                        "program_id": "p1",
                        "initial_targets": [
                            {
                                "name": "x",
                                "version": "1.0.0",
                                "defects": [{"id": "x-1"}],
                            }
                        ],
                    }
                ],
            },
            {
                "institution_id": "a",  # duplicate id ignored
                "charter": [
                    {
                        "program_id": "p2",
                        "initial_targets": [
                            {
                                "name": "y",
                                "version": "1.0.0",
                                "defects": [{"id": "y-1"}],
                            }
                        ],
                    }
                ],
            },
            {
                "institution_id": "empty",
                # no nested charter → dropped
            },
            {
                "institution_id": "b",
                "programs": [
                    {
                        "program_id": "pb",
                        "surface_charter": [
                            {
                                "name": "z",
                                "version": "1.0.0",
                                "defects": [{"id": "z-1"}],
                            }
                        ],
                    }
                ],
            },
        ]
    )
    ids = [c["institution_id"] for c in charter]
    assert ids == ["a", "b"]
    assert charter[0]["charter"][0]["program_id"] == "p1"
    assert charter[1]["charter"][0]["surface_charter"][0]["name"] == "z"


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
    fed = ul.federate_portfolios([p1, p2])
    assert len(fed["entries"]) == 2
    by_key = {
        (e["name"], e["version"], e["defect_id"]): e["outcome"] for e in fed["entries"]
    }
    assert by_key[("a", "1.0.0", "a-1")] == "impact_merged"
    assert by_key[("b", "1.0.0", "b-1")] == "impact_merged"
    assert fed["portfolio_digest"]
    assert fed["source"] == "league_federation"


def test_select_next_institution_priority_and_fairness() -> None:
    states = [
        {"institution_id": "low", "priority": 1, "institution_met": False},
        {"institution_id": "high", "priority": 5, "institution_met": False},
        {"institution_id": "done", "priority": 9, "institution_met": True},
    ]
    selected = ul.select_next_institution(states, [], round_index=0)
    assert selected is not None
    assert selected["institution_id"] == "high"

    only_open = [
        {"institution_id": "a", "priority": 1, "institution_met": False},
        {"institution_id": "b", "priority": 1, "institution_met": False},
    ]
    s0 = ul.select_next_institution(only_open, [], round_index=0)
    s1 = ul.select_next_institution(only_open, [], round_index=1)
    assert s0 is not None and s1 is not None
    assert {s0["institution_id"], s1["institution_id"]} == {"a", "b"}
    assert s0["institution_id"] != s1["institution_id"]


def test_allocate_institution_budget_split_and_boost() -> None:
    assert ul.allocate_institution_budget(
        remaining_budget=None,
        open_institution_count=2,
        selected={"institution_id": "a"},
        roi_history=[],
    ) is None
    assert (
        ul.allocate_institution_budget(
            remaining_budget=0,
            open_institution_count=2,
            selected={"institution_id": "a"},
            roi_history=[],
        )
        == 0
    )
    even = ul.allocate_institution_budget(
        remaining_budget=4,
        open_institution_count=2,
        selected={"institution_id": "a"},
        roi_history=[],
    )
    assert even == 2
    boosted = ul.allocate_institution_budget(
        remaining_budget=4,
        open_institution_count=2,
        selected={"institution_id": "a"},
        roi_history=[
            {
                "institution_id": "a",
                "dispatched_ok": 2,
                "efficiency": 1.0,
                "covered_delta": 2,
                "coverage_delta": 0.5,
            }
        ],
    )
    assert boosted is not None and boosted >= even


def test_score_institution_roi_efficiency() -> None:
    roi = ul.score_institution_roi(
        round_index=0,
        institution_id="inst-a",
        institution_result={
            "total_dispatched": 2,
            "total_dispatched_ok": 2,
            "stop_reason": "institution_met",
            "institution_met": True,
            "institution_digest": "d" * 64,
            "programs_admitted": 1,
            "programs_met_count": 1,
        },
        coverage_before={"coverage_ratio": 0.0, "covered": 0, "required": 2},
        coverage_after={"coverage_ratio": 1.0, "covered": 2, "required": 2},
    )
    assert roi["covered_delta"] == 2
    assert roi["efficiency"] == 1.0
    assert roi["institution_met"] is True


def test_durable_state_roundtrip(tmp_path: Path) -> None:
    state = ul._state_payload(
        league_id="L1",
        round_count=1,
        total_dispatched=2,
        total_dispatched_ok=2,
        federated_portfolio={"entries": [], "portfolio_digest": "x" * 64},
        roi_history=[{"institution_id": "a", "efficiency": 1.0}],
        institution_states=[{"institution_id": "a", "institution_met": False}],
        institution_digests=["d" * 64],
        charter=[{"institution_id": "a"}],
        stop_reason=None,
        league_goal="all_institutions_met",
    )
    path = ul.write_league_state(tmp_path, state)
    assert path.is_file()
    loaded = ul.load_league_state(tmp_path)
    assert loaded["league_id"] == "L1"
    assert loaded["round_count"] == 1
    assert loaded["institution_states"][0]["institution_id"] == "a"


def test_admit_institution_slot_materializes_root(tmp_path: Path) -> None:
    slot = {
        "institution_id": "inst-x",
        "priority": 1,
        "charter": [
            {
                "program_id": "lane-x",
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
            }
        ],
        "max_rounds": 3,
        "institution_goal": "all_programs_met",
    }
    admission = ul.admit_institution_slot(league_dir=tmp_path, slot=slot)
    assert admission["admitted"] is True
    assert Path(admission["institution_root"]).is_dir()
    assert admission["charter"][0]["program_id"] == "lane-x"


def test_pending_and_constitution_requires_charter_exhaustion() -> None:
    charter = ul.normalize_league_charter(
        [
            {
                "institution_id": "a",
                "priority": 2,
                "charter": [
                    {
                        "program_id": "pa",
                        "initial_targets": [
                            {
                                "name": "a",
                                "version": "1.0.0",
                                "defects": [{"id": "a-1"}],
                            }
                        ],
                    }
                ],
            },
            {
                "institution_id": "b",
                "priority": 1,
                "charter": [
                    {
                        "program_id": "pb",
                        "initial_targets": [
                            {
                                "name": "b",
                                "version": "1.0.0",
                                "defects": [{"id": "b-1"}],
                            }
                        ],
                    }
                ],
            },
        ]
    )
    states = [
        {"institution_id": "a", "institution_met": True},
    ]
    pending = ul.pending_charter_slots(charter, states)
    assert [p["institution_id"] for p in pending] == ["b"]
    assert not ul.constitution_satisfied(
        institution_states=states,
        charter=charter,
        league_goal="all_institutions_met",
    )
    states2 = [
        {"institution_id": "a", "institution_met": True},
        {"institution_id": "b", "institution_met": True},
    ]
    assert ul.constitution_satisfied(
        institution_states=states2,
        charter=charter,
        league_goal="all_institutions_met",
    )
