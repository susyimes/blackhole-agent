"""Unit tests for the upstream multiverse plane (hermetic; no network)."""

from __future__ import annotations

from blackhole_agent import upstream_multiverse as umv


def test_builtin_proof_green() -> None:
    result = umv.builtin_upstream_multiverse_proof()
    assert result["ok"], result.get("flags")
    assert result["multiverse_met"]
    assert result["multi_cosmos_progressed"]
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


def test_normalize_multiverse_charter_dedupes_and_requires_work() -> None:
    charter = umv.normalize_multiverse_charter(
        [
            umv._cosmos_slot(
                "a",
                institutions=[
                    umv._inst_slot(
                        "i1",
                        programs=[
                            umv._program_slot(
                                "p1", initial=[("x", "1.0.0", "x-1")]
                            )
                        ],
                    )
                ],
            ),
            umv._cosmos_slot(
                "a",  # duplicate id ignored
                institutions=[
                    umv._inst_slot(
                        "i2",
                        programs=[
                            umv._program_slot(
                                "p2", initial=[("y", "1.0.0", "y-1")]
                            )
                        ],
                    )
                ],
            ),
            {
                "cosmos_id": "empty",
                # no nested charter → dropped
            },
        ]
    )
    assert [s["cosmos_id"] for s in charter] == ["a"]
    assert charter[0]["charter"]  # nested civilization slots present


def test_merge_multiverse_charter_dedupes_ids() -> None:
    base = [
        umv._cosmos_slot(
            "m1",
            institutions=[
                umv._inst_slot(
                    "mi",
                    programs=[
                        umv._program_slot("mp", initial=[("m", "1.0.0", "m-1")])
                    ],
                )
            ],
        )
    ]
    extra = [
        umv._cosmos_slot(
            "m1",
            institutions=[
                umv._inst_slot(
                    "mi2",
                    programs=[
                        umv._program_slot("mp2", initial=[("m2", "1.0.0", "m2-1")])
                    ],
                )
            ],
        ),
        umv._cosmos_slot(
            "m2",
            institutions=[
                umv._inst_slot(
                    "mj",
                    programs=[
                        umv._program_slot("mq", initial=[("n", "1.0.0", "n-1")])
                    ],
                )
            ],
        ),
    ]
    merged = umv.merge_multiverse_charter(base, extra)
    assert [s["cosmos_id"] for s in merged] == ["m1", "m2"]
