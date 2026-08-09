"""Unit tests for the upstream domain plane (hermetic; no network)."""

from __future__ import annotations

from pathlib import Path

from blackhole_agent import upstream_domain as ud
from blackhole_agent import upstream_fleet as uf


def test_builtin_proof_green() -> None:
    result = ud.builtin_upstream_domain_proof()
    assert result["ok"], result.get("flags")
    assert result["domain_met"]
    assert result["multi_commonwealth_progressed"]
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


def test_normalize_domain_charter_dedupes_and_requires_work() -> None:
    charter = ud.normalize_domain_charter(
        [
            {
                "commonwealth_id": "a",
                "charter": [
                    {
                        "confederation_id": "ca",
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
            },
            {
                "commonwealth_id": "a",  # duplicate id ignored
                "charter": [
                    {
                        "confederation_id": "ca2",
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
                    }
                ],
            },
            {
                "commonwealth_id": "empty",
                # no nested charter → dropped
            },
            {
                "commonwealth_id": "b",
                "confederations": [
                    {
                        "confederation_id": "cb",
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
                    }
                ],
            },
        ]
    )
    ids = [c["commonwealth_id"] for c in charter]
    assert ids == ["a", "b"]
    assert charter[0]["charter"][0]["confederation_id"] == "ca"
    assert charter[1]["charter"][0]["confederation_id"] == "cb"


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
    fed = ud.federate_portfolios([p1, p2])
    by_key = {
        (e["name"], e["version"], e["defect_id"]): e for e in fed["entries"]
    }
    assert by_key[("a", "1.0.0", "a-1")]["outcome"] == "impact_merged"
    assert ("b", "1.0.0", "b-1") in by_key
    assert fed["source"] == "domain_federation"
    assert fed["portfolio_digest"]


def test_empty_charter_refuses(tmp_path: Path) -> None:
    try:
        ud.run_domain(
            charter=[],
            dispatch=False,
            domain_goal="none",
            out_root=tmp_path / "e",
        )
        raise AssertionError("expected DomainRefused")
    except ud.DomainRefused as exc:
        assert exc.verdict in {"domain_empty", "domain_invalid"}


def test_commonwealth_slot_wraps_institutions() -> None:
    slot = ud._commonwealth_slot(
        "c1",
        institutions=[
            ud._inst_slot(
                "i1",
                programs=[
                    ud._program_slot("p1", initial=[("pkg", "1.0.0", "pkg-1")])
                ],
            )
        ],
    )
    assert slot["commonwealth_id"] == "c1"
    assert slot["charter"][0]["confederation_id"] == "c1c"
    assert slot["charter"][0]["charter"][0]["league_id"] == "c1cl"
    assert slot["charter"][0]["charter"][0]["charter"][0]["institution_id"] == "i1"


def test_merge_domain_charter_appends_and_dedupes() -> None:
    a = ud._commonwealth_slot(
        "a",
        institutions=[
            ud._inst_slot(
                "ia",
                programs=[ud._program_slot("pa", initial=[("x", "1.0.0", "x-1")])],
            )
        ],
    )
    b = ud._commonwealth_slot(
        "b",
        institutions=[
            ud._inst_slot(
                "ib",
                programs=[ud._program_slot("pb", initial=[("y", "1.0.0", "y-1")])],
            )
        ],
    )
    a_dup = ud._commonwealth_slot(
        "a",
        institutions=[
            ud._inst_slot(
                "ia2",
                programs=[ud._program_slot("pa2", initial=[("z", "1.0.0", "z-1")])],
            )
        ],
    )
    merged = ud.merge_domain_charter([a], [a_dup, b])
    assert [s["commonwealth_id"] for s in merged] == ["a", "b"]
    # existing id wins — nested charter of first a kept
    assert merged[0]["charter"][0]["confederation_id"] == "ac"


def test_charter_expand_grows_constitution() -> None:
    # Short root: deep domain→wave nesting must stay under Windows MAX_PATH.
    scratch = ud._proof_scratch()
    try:
        campaign = ud._proof_campaign_runner(scratch / "c")
        expand = ud.make_domain_charter_expand(
            [
                ud._commonwealth_slot(
                    "g2",
                    institutions=[
                        ud._inst_slot(
                            "i2",
                            programs=[
                                ud._program_slot(
                                    "p2", initial=[("g2", "1.0.0", "g2-1")]
                                )
                            ],
                        )
                    ],
                )
            ]
        )
        result = ud.run_domain(
            charter=[
                ud._commonwealth_slot(
                    "g1",
                    institutions=[
                        ud._inst_slot(
                            "i1",
                            programs=[
                                ud._program_slot(
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
            max_active_commonwealths=1,
            dispatch=True,
            campaign_runner=campaign,
            charter_expand=expand,
            domain_goal="all_commonwealths_met",
            out_root=scratch / "d",
        )
        assert result["ok"]
        assert result["domain_met"]
        assert result["commonwealths_admitted"] == 2
        assert result["charter_expansion_count"] >= 1
        assert "g2" in set(result.get("charter_expanded_ids") or [])
    finally:
        import shutil

        shutil.rmtree(scratch, ignore_errors=True)
