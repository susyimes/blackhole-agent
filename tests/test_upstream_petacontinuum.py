"""Unit tests for the upstream petacontinuum plane (hermetic; no network)."""

from __future__ import annotations

from blackhole_agent import upstream_petacontinuum as pp


def test_builtin_proof_green() -> None:
    result = pp.builtin_upstream_petacontinuum_proof()
    assert result["ok"], result.get("flags")
    assert result["petacontinuum_met"]
    assert result["multi_petacontinuum_progressed"]
    assert result["federation_coverage"]
    assert result["priority_scheduling"]
    assert result["deferred_admission"]
    assert result["charter_expand"]
    assert result["charter_merge"]
    assert result["terminal_coverage_goal"]
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


def test_normalize_petacontinuum_charter_dedupes_and_requires_work() -> None:
    charter = pp.normalize_petacontinuum_charter(
        [
            pp._teracontinuum_slot(
                "a",
                institutions=[
                    pp._inst_slot(
                        "i1",
                        programs=[
                            pp._program_slot(
                                "p1", initial=[("x", "1.0.0", "x-1")]
                            )
                        ],
                    )
                ],
            ),
            pp._teracontinuum_slot(
                "a",  # duplicate id ignored
                institutions=[
                    pp._inst_slot(
                        "i2",
                        programs=[
                            pp._program_slot(
                                "p2", initial=[("y", "1.0.0", "y-1")]
                            )
                        ],
                    )
                ],
            ),
            {
                "teracontinuum_id": "empty",
                # no nested charter → dropped
            },
        ]
    )
    assert [s["teracontinuum_id"] for s in charter] == ["a"]
    assert charter[0]["charter"]  # nested gigacontinuum slots present


def test_merge_petacontinuum_charter_dedupes_ids() -> None:
    base = [
        pp._teracontinuum_slot(
            "m1",
            institutions=[
                pp._inst_slot(
                    "mi",
                    programs=[
                        pp._program_slot("mp", initial=[("m", "1.0.0", "m-1")])
                    ],
                )
            ],
        )
    ]
    extra = [
        pp._teracontinuum_slot(
            "m1",
            institutions=[
                pp._inst_slot(
                    "mi2",
                    programs=[
                        pp._program_slot("mp2", initial=[("m2", "1.0.0", "m2-1")])
                    ],
                )
            ],
        ),
        pp._teracontinuum_slot(
            "m2",
            institutions=[
                pp._inst_slot(
                    "mj",
                    programs=[
                        pp._program_slot("mp3", initial=[("m3", "1.0.0", "m3-1")])
                    ],
                )
            ],
        ),
    ]
    merged = pp.merge_petacontinuum_charter(base, extra)
    ids = [s["teracontinuum_id"] for s in merged]
    assert ids == ["m1", "m2"]
