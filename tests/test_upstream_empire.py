"""Unit tests for the upstream empire plane (hermetic; no network)."""

from __future__ import annotations

from blackhole_agent import upstream_empire as ue


def test_builtin_proof_green() -> None:
    result = ue.builtin_upstream_empire_proof()
    assert result["ok"], result.get("flags")
    assert result["empire_met"]
    assert result["multi_realm_progressed"]
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


def test_normalize_empire_charter_dedupes_and_requires_work() -> None:
    charter = ue.normalize_empire_charter(
        [
            {
                "realm_id": "a",
                "charter": [
                    {
                        "domain_id": "da",
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
                                                                        "defects": [
                                                                            {"id": "x-1"}
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
                            }
                        ],
                    }
                ],
            },
            {
                "realm_id": "a",  # duplicate id ignored
                "charter": [
                    {
                        "domain_id": "da2",
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
                "realm_id": "empty",
                # no nested charter → dropped
            },
        ]
    )
    assert [s["realm_id"] for s in charter] == ["a"]
    assert charter[0]["charter"]  # nested domain slots present


def test_merge_empire_charter_dedupes_ids() -> None:
    base = [
        ue._realm_slot(
            "m1",
            institutions=[
                ue._inst_slot(
                    "mi",
                    programs=[
                        ue._program_slot("mp", initial=[("m", "1.0.0", "m-1")])
                    ],
                )
            ],
        )
    ]
    extra = [
        ue._realm_slot(
            "m1",
            institutions=[
                ue._inst_slot(
                    "mi2",
                    programs=[
                        ue._program_slot("mp2", initial=[("m2", "1.0.0", "m2-1")])
                    ],
                )
            ],
        ),
        ue._realm_slot(
            "m2",
            institutions=[
                ue._inst_slot(
                    "mj",
                    programs=[
                        ue._program_slot("mq", initial=[("n", "1.0.0", "n-1")])
                    ],
                )
            ],
        ),
    ]
    merged = ue.merge_empire_charter(base, extra)
    assert [s["realm_id"] for s in merged] == ["m1", "m2"]
