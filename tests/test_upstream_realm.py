"""Unit tests for the upstream realm plane (hermetic; no network)."""

from __future__ import annotations

from pathlib import Path

from blackhole_agent import upstream_fleet as uf
from blackhole_agent import upstream_realm as ur


def test_builtin_proof_green() -> None:
    result = ur.builtin_upstream_realm_proof()
    assert result["ok"], result.get("flags")
    assert result["realm_met"]
    assert result["multi_domain_progressed"]
    assert result["federation_coverage"]
    assert result["priority_scheduling"]
    assert result["deferred_admission"]
    assert result["charter_expand"]
    assert result["charter_merge"]
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


def test_normalize_realm_charter_dedupes_and_requires_work() -> None:
    charter = ur.normalize_realm_charter(
        [
            {
                "domain_id": "a",
                "charter": [
                    {
                        "commonwealth_id": "ca",
                        "charter": [
                            {
                                "confederation_id": "cfa",
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
                            }
                        ],
                    }
                ],
            },
            {
                "domain_id": "a",  # duplicate id ignored
                "charter": [
                    {
                        "commonwealth_id": "ca2",
                        "institutions": [
                            {
                                "institution_id": "i2",
                                "programs": [
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
                "domain_id": "empty",
                # no nested charter → dropped
            },
            # institutions-only domain slot via helper wrapping
            ur._domain_slot(
                "b",
                institutions=[
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
            ),
        ]
    )
    ids = [c["domain_id"] for c in charter]
    assert ids == ["a", "b"]
    assert charter[0]["charter"][0]["commonwealth_id"] == "ca"
    assert charter[1]["charter"][0]["commonwealth_id"] == "bc"


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
    fed = ur.federate_portfolios([p1, p2])
    by_key = {(e["name"], e["version"], e["defect_id"]): e for e in fed["entries"]}
    assert by_key[("a", "1.0.0", "a-1")]["outcome"] == "impact_merged"
    assert ("b", "1.0.0", "b-1") in by_key
    assert fed["source"] == "realm_federation"
    assert fed["portfolio_digest"]


def test_empty_charter_refuses(tmp_path: Path) -> None:
    try:
        ur.run_realm(
            charter=[],
            dispatch=False,
            realm_goal="none",
            out_root=tmp_path / "e",
        )
        raise AssertionError("expected RealmRefused")
    except ur.RealmRefused as exc:
        assert exc.verdict in {"realm_empty", "realm_invalid"}


def test_domain_slot_wraps_institutions() -> None:
    slot = ur._domain_slot(
        "d1",
        institutions=[
            ur._inst_slot(
                "i1",
                programs=[
                    ur._program_slot("p1", initial=[("pkg", "1.0.0", "pkg-1")])
                ],
            )
        ],
    )
    assert slot["domain_id"] == "d1"
    assert slot["charter"][0]["commonwealth_id"] == "d1c"


def test_merge_realm_charter_appends_and_dedupes() -> None:
    a = ur._domain_slot(
        "a",
        institutions=[
            ur._inst_slot(
                "ia",
                programs=[ur._program_slot("pa", initial=[("x", "1.0.0", "x-1")])],
            )
        ],
    )
    b = ur._domain_slot(
        "b",
        institutions=[
            ur._inst_slot(
                "ib",
                programs=[ur._program_slot("pb", initial=[("y", "1.0.0", "y-1")])],
            )
        ],
    )
    a_dup = ur._domain_slot(
        "a",
        institutions=[
            ur._inst_slot(
                "ia2",
                programs=[ur._program_slot("pa2", initial=[("z", "1.0.0", "z-1")])],
            )
        ],
    )
    merged = ur.merge_realm_charter([a], [a_dup, b])
    assert [s["domain_id"] for s in merged] == ["a", "b"]
    # existing id wins — nested charter of first a kept
    assert merged[0]["charter"][0]["commonwealth_id"] == "ac"


def test_charter_expand_grows_constitution() -> None:
    # Short root: deep realm→domain→wave nesting must stay under Windows MAX_PATH.
    scratch = ur._proof_scratch()
    try:
        campaign = ur._proof_campaign_runner(scratch / "c")
        expand = ur.make_realm_charter_expand(
            [
                ur._domain_slot(
                    "g2",
                    institutions=[
                        ur._inst_slot(
                            "i2",
                            programs=[
                                ur._program_slot(
                                    "p2", initial=[("g2", "1.0.0", "g2-1")]
                                )
                            ],
                        )
                    ],
                )
            ]
        )
        result = ur.run_realm(
            charter=[
                ur._domain_slot(
                    "g1",
                    institutions=[
                        ur._inst_slot(
                            "i1",
                            programs=[
                                ur._program_slot(
                                    "p1", initial=[("g1", "1.0.0", "g1-1")]
                                )
                            ],
                        )
                    ],
                )
            ],
            max_rounds=6,
            max_epochs_per_succession=2,
            max_waves_per_epoch=2,
            per_wave_dispatch_limit=1,
            dispatch_budget=4,
            max_active_domains=1,
            dispatch=True,
            campaign_runner=campaign,
            charter_expand=expand,
            realm_goal="all_domains_met",
            out_root=scratch / "r",
        )
        assert result["ok"]
        assert result["realm_met"]
        assert result["domains_admitted"] == 2
        assert result["charter_expansion_count"] >= 1
        assert "g2" in set(result.get("charter_expanded_ids") or [])
    finally:
        import shutil

        shutil.rmtree(scratch, ignore_errors=True)
