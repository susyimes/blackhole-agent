"""Unit tests for the upstream cosmos plane (hermetic; no network)."""

from __future__ import annotations

from blackhole_agent import upstream_cosmos as uxo


def test_builtin_proof_green() -> None:
    result = uxo.builtin_upstream_cosmos_proof()
    assert result["ok"], result.get("flags")
    assert result["cosmos_met"]
    assert result["multi_civilization_progressed"]
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


def test_normalize_cosmos_charter_dedupes_and_requires_work() -> None:
    charter = uxo.normalize_cosmos_charter(
        [
            uxo._civilization_slot(
                "a",
                institutions=[
                    uxo._inst_slot(
                        "i1",
                        programs=[
                            uxo._program_slot(
                                "p1", initial=[("x", "1.0.0", "x-1")]
                            )
                        ],
                    )
                ],
            ),
            uxo._civilization_slot(
                "a",  # duplicate id ignored
                institutions=[
                    uxo._inst_slot(
                        "i2",
                        programs=[
                            uxo._program_slot(
                                "p2", initial=[("y", "1.0.0", "y-1")]
                            )
                        ],
                    )
                ],
            ),
            {
                "civilization_id": "empty",
                # no nested charter → dropped
            },
        ]
    )
    assert [s["civilization_id"] for s in charter] == ["a"]
    assert charter[0]["charter"]  # nested empire slots present


def test_merge_cosmos_charter_dedupes_ids() -> None:
    base = [
        uxo._civilization_slot(
            "m1",
            institutions=[
                uxo._inst_slot(
                    "mi",
                    programs=[
                        uxo._program_slot("mp", initial=[("m", "1.0.0", "m-1")])
                    ],
                )
            ],
        )
    ]
    extra = [
        uxo._civilization_slot(
            "m1",
            institutions=[
                uxo._inst_slot(
                    "mi2",
                    programs=[
                        uxo._program_slot("mp2", initial=[("m2", "1.0.0", "m2-1")])
                    ],
                )
            ],
        ),
        uxo._civilization_slot(
            "m2",
            institutions=[
                uxo._inst_slot(
                    "mj",
                    programs=[
                        uxo._program_slot("mq", initial=[("n", "1.0.0", "n-1")])
                    ],
                )
            ],
        ),
    ]
    merged = uxo.merge_cosmos_charter(base, extra)
    assert [s["civilization_id"] for s in merged] == ["m1", "m2"]
