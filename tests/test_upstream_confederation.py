"""Unit tests for the upstream confederation plane (hermetic; no network)."""

from __future__ import annotations

import json
from pathlib import Path

from blackhole_agent import upstream_confederation as uc
from blackhole_agent import upstream_fleet as uf


def test_builtin_proof_green() -> None:
    result = uc.builtin_upstream_confederation_proof()
    assert result["ok"], result.get("flags")
    assert result["confederation_met"]
    assert result["multi_league_progressed"]
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


def test_normalize_confederation_charter_dedupes_and_requires_work() -> None:
    charter = uc.normalize_confederation_charter(
        [
            {
                "league_id": "a",
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
            },
            {
                "league_id": "a",  # duplicate id ignored
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
            },
            {
                "league_id": "empty",
                # no nested charter → dropped
            },
            {
                "league_id": "b",
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
            },
        ]
    )
    ids = [c["league_id"] for c in charter]
    assert ids == ["a", "b"]
    assert charter[0]["charter"][0]["institution_id"] == "i1"
    assert charter[1]["charter"][0]["institution_id"] == "ib"


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
    fed = uc.federate_portfolios([p1, p2])
    by_key = {
        (e["name"], e["version"], e["defect_id"]): e for e in fed["entries"]
    }
    assert by_key[("a", "1.0.0", "a-1")]["outcome"] == "impact_merged"
    assert ("b", "1.0.0", "b-1") in by_key
    assert fed["source"] == "confederation_federation"
    assert fed["portfolio_digest"]


def test_empty_charter_refuses(tmp_path: Path) -> None:
    try:
        uc.run_confederation(
            charter=[],
            dispatch=False,
            confederation_goal="none",
            out_root=tmp_path / "e",
        )
        raise AssertionError("expected ConfederationRefused")
    except uc.ConfederationRefused as exc:
        assert exc.verdict in {"confederation_empty", "confederation_invalid"}
