"""Unit tests for the upstream teracontinuum plane (hermetic; no network)."""

from __future__ import annotations

from blackhole_agent import upstream_teracontinuum as gg


def test_builtin_proof_green() -> None:
    result = gg.builtin_upstream_teracontinuum_proof()
    assert result["ok"], result.get("flags")
    assert result["teracontinuum_met"]
    assert result["multi_teracontinuum_progressed"]
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


def test_normalize_teracontinuum_charter_dedupes_and_requires_work() -> None:
    charter = gg.normalize_teracontinuum_charter(
        [
            gg._gigacontinuum_slot(
                "a",
                institutions=[
                    gg._inst_slot(
                        "i1",
                        programs=[
                            gg._program_slot(
                                "p1", initial=[("x", "1.0.0", "x-1")]
                            )
                        ],
                    )
                ],
            ),
            gg._gigacontinuum_slot(
                "a",  # duplicate id ignored
                institutions=[
                    gg._inst_slot(
                        "i2",
                        programs=[
                            gg._program_slot(
                                "p2", initial=[("y", "1.0.0", "y-1")]
                            )
                        ],
                    )
                ],
            ),
            {
                "gigacontinuum_id": "empty",
                # no nested charter → dropped
            },
        ]
    )
    assert [s["gigacontinuum_id"] for s in charter] == ["a"]
    assert charter[0]["charter"]  # nested megacontinuum slots present


def test_merge_teracontinuum_charter_dedupes_ids() -> None:
    base = [
        gg._gigacontinuum_slot(
            "m1",
            institutions=[
                gg._inst_slot(
                    "mi",
                    programs=[
                        gg._program_slot("mp", initial=[("m", "1.0.0", "m-1")])
                    ],
                )
            ],
        )
    ]
    extra = [
        gg._gigacontinuum_slot(
            "m1",
            institutions=[
                gg._inst_slot(
                    "mi2",
                    programs=[
                        gg._program_slot("mp2", initial=[("m2", "1.0.0", "m2-1")])
                    ],
                )
            ],
        ),
        gg._gigacontinuum_slot(
            "m2",
            institutions=[
                gg._inst_slot(
                    "mj",
                    programs=[
                        gg._program_slot("mp3", initial=[("m3", "1.0.0", "m3-1")])
                    ],
                )
            ],
        ),
    ]
    merged = gg.merge_teracontinuum_charter(base, extra)
    ids = [s["gigacontinuum_id"] for s in merged]
    assert ids == ["m1", "m2"]
