"""Unit tests for the upstream commonwealth plane (hermetic; no network)."""

from __future__ import annotations

import json
from pathlib import Path

from blackhole_agent import upstream_commonwealth as uw
from blackhole_agent import upstream_fleet as uf


def test_builtin_proof_green() -> None:
    result = uw.builtin_upstream_commonwealth_proof()
    assert result["ok"], result.get("flags")
    assert result["commonwealth_met"]
    assert result["multi_confederation_progressed"]
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


def test_normalize_commonwealth_charter_dedupes_and_requires_work() -> None:
    charter = uw.normalize_commonwealth_charter(
        [
            {
                "confederation_id": "a",
                "charter": [
                    {
                        "league_id": "la",
                        "charter": [
                            {
                                "institution_id": "i1",
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
                            }
                        ],
                    }
                ],
            },
            {
                "confederation_id": "a",  # duplicate id ignored
                "charter": [
                    {
                        "league_id": "la2",
                        "charter": [
                            {
                                "institution_id": "i2",
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
                            }
                        ],
                    }
                ],
            },
            {
                "confederation_id": "empty",
                # no nested charter → dropped
            },
            {
                "confederation_id": "b",
                "leagues": [
                    {
                        "league_id": "lb",
                        "institutions": [
                            {
                                "institution_id": "ib",
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
                            }
                        ],
                    }
                ],
            },
        ]
    )
    ids = [c["confederation_id"] for c in charter]
    assert ids == ["a", "b"]
    assert charter[0]["charter"][0]["league_id"] == "la"
    assert charter[1]["charter"][0]["league_id"] == "lb"


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
    fed = uw.federate_portfolios([p1, p2])
    by_key = {
        (e["name"], e["version"], e["defect_id"]): e for e in fed["entries"]
    }
    assert by_key[("a", "1.0.0", "a-1")]["outcome"] == "impact_merged"
    assert ("b", "1.0.0", "b-1") in by_key
    assert fed["source"] == "commonwealth_federation"
    assert fed["portfolio_digest"]


def test_empty_charter_refuses(tmp_path: Path) -> None:
    try:
        uw.run_commonwealth(
            charter=[],
            dispatch=False,
            commonwealth_goal="none",
            out_root=tmp_path / "e",
        )
        raise AssertionError("expected CommonwealthRefused")
    except uw.CommonwealthRefused as exc:
        assert exc.verdict in {"commonwealth_empty", "commonwealth_invalid"}


def test_confederation_slot_wraps_institutions() -> None:
    slot = uw._confederation_slot(
        "c1",
        institutions=[
            uw._inst_slot(
                "i1",
                programs=[
                    uw._program_slot("p1", initial=[("pkg", "1.0.0", "pkg-1")])
                ],
            )
        ],
    )
    assert slot["confederation_id"] == "c1"
    assert slot["charter"][0]["league_id"] == "c1-lg"
    assert slot["charter"][0]["charter"][0]["institution_id"] == "i1"
