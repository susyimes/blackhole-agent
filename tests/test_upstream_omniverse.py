"""Unit tests for the upstream omniverse plane (hermetic; no network)."""

from __future__ import annotations

from blackhole_agent import upstream_omniverse as uov


def test_builtin_proof_green() -> None:
    result = uov.builtin_upstream_omniverse_proof()
    assert result["ok"], result.get("flags")
    assert result["omniverse_met"]
    assert result["multi_omniverse_progressed"]
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


def test_normalize_omniverse_charter_dedupes_and_requires_work() -> None:
    charter = uov.normalize_omniverse_charter(
        [
            uov._multiverse_slot(
                "a",
                institutions=[
                    uov._inst_slot(
                        "i1",
                        programs=[
                            uov._program_slot(
                                "p1", initial=[("x", "1.0.0", "x-1")]
                            )
                        ],
                    )
                ],
            ),
            uov._multiverse_slot(
                "a",  # duplicate id ignored
                institutions=[
                    uov._inst_slot(
                        "i2",
                        programs=[
                            uov._program_slot(
                                "p2", initial=[("y", "1.0.0", "y-1")]
                            )
                        ],
                    )
                ],
            ),
            {
                "multiverse_id": "empty",
                # no nested charter → dropped
            },
        ]
    )
    assert [s["multiverse_id"] for s in charter] == ["a"]
    assert charter[0]["charter"]  # nested cosmos slots present


def test_merge_omniverse_charter_dedupes_ids() -> None:
    base = [
        uov._multiverse_slot(
            "m1",
            institutions=[
                uov._inst_slot(
                    "mi",
                    programs=[
                        uov._program_slot("mp", initial=[("m", "1.0.0", "m-1")])
                    ],
                )
            ],
        )
    ]
    extra = [
        uov._multiverse_slot(
            "m1",
            institutions=[
                uov._inst_slot(
                    "mi2",
                    programs=[
                        uov._program_slot("mp2", initial=[("m2", "1.0.0", "m2-1")])
                    ],
                )
            ],
        ),
        uov._multiverse_slot(
            "m2",
            institutions=[
                uov._inst_slot(
                    "mj",
                    programs=[
                        uov._program_slot("mq", initial=[("n", "1.0.0", "n-1")])
                    ],
                )
            ],
        ),
    ]
    merged = uov.merge_omniverse_charter(base, extra)
    assert [s["multiverse_id"] for s in merged] == ["m1", "m2"]
