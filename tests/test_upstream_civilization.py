"""Unit tests for the upstream civilization plane (hermetic; no network)."""

from __future__ import annotations

from blackhole_agent import upstream_civilization as uc


def test_builtin_proof_green() -> None:
    result = uc.builtin_upstream_civilization_proof()
    assert result["ok"], result.get("flags")
    assert result["civilization_met"]
    assert result["multi_empire_progressed"]
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


def test_normalize_civilization_charter_dedupes_and_requires_work() -> None:
    charter = uc.normalize_civilization_charter(
        [
            {
                "empire_id": "a",
                "charter": [
                    {
                        "realm_id": "ra",
                        "institutions": [
                            {
                                "institution_id": "i1",
                                "programs": [
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
                "empire_id": "a",  # duplicate id ignored
                "charter": [
                    {
                        "realm_id": "rb",
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
                "empire_id": "empty",
                # no nested charter → dropped
            },
        ]
    )
    assert [s["empire_id"] for s in charter] == ["a"]
    assert charter[0]["charter"]  # nested realm slots present


def test_merge_civilization_charter_dedupes_ids() -> None:
    base = [
        uc._empire_slot(
            "m1",
            institutions=[
                uc._inst_slot(
                    "mi",
                    programs=[
                        uc._program_slot("mp", initial=[("m", "1.0.0", "m-1")])
                    ],
                )
            ],
        )
    ]
    extra = [
        uc._empire_slot(
            "m1",
            institutions=[
                uc._inst_slot(
                    "mi2",
                    programs=[
                        uc._program_slot("mp2", initial=[("m2", "1.0.0", "m2-1")])
                    ],
                )
            ],
        ),
        uc._empire_slot(
            "m2",
            institutions=[
                uc._inst_slot(
                    "mj",
                    programs=[
                        uc._program_slot("mq", initial=[("n", "1.0.0", "n-1")])
                    ],
                )
            ],
        ),
    ]
    merged = uc.merge_civilization_charter(base, extra)
    assert [s["empire_id"] for s in merged] == ["m1", "m2"]
