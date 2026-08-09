"""Unit tests for the upstream hypercontinuum plane (hermetic; no network)."""

from __future__ import annotations

from blackhole_agent import upstream_hypercontinuum as uh


def test_builtin_proof_green() -> None:
    result = uh.builtin_upstream_hypercontinuum_proof()
    assert result["ok"], result.get("flags")
    assert result["hypercontinuum_met"]
    assert result["multi_hypercontinuum_progressed"]
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


def test_normalize_hypercontinuum_charter_dedupes_and_requires_work() -> None:
    charter = uh.normalize_hypercontinuum_charter(
        [
            uh._continuum_slot(
                "a",
                institutions=[
                    uh._inst_slot(
                        "i1",
                        programs=[
                            uh._program_slot(
                                "p1", initial=[("x", "1.0.0", "x-1")]
                            )
                        ],
                    )
                ],
            ),
            uh._continuum_slot(
                "a",  # duplicate id ignored
                institutions=[
                    uh._inst_slot(
                        "i2",
                        programs=[
                            uh._program_slot(
                                "p2", initial=[("y", "1.0.0", "y-1")]
                            )
                        ],
                    )
                ],
            ),
            {
                "continuum_id": "empty",
                # no nested charter → dropped
            },
        ]
    )
    assert [s["continuum_id"] for s in charter] == ["a"]
    assert charter[0]["charter"]  # nested omniverse slots present


def test_merge_hypercontinuum_charter_dedupes_ids() -> None:
    base = [
        uh._continuum_slot(
            "m1",
            institutions=[
                uh._inst_slot(
                    "mi",
                    programs=[
                        uh._program_slot("mp", initial=[("m", "1.0.0", "m-1")])
                    ],
                )
            ],
        )
    ]
    extra = [
        uh._continuum_slot(
            "m1",
            institutions=[
                uh._inst_slot(
                    "mi2",
                    programs=[
                        uh._program_slot("mp2", initial=[("m2", "1.0.0", "m2-1")])
                    ],
                )
            ],
        ),
        uh._continuum_slot(
            "m2",
            institutions=[
                uh._inst_slot(
                    "mj",
                    programs=[
                        uh._program_slot("mq", initial=[("n", "1.0.0", "n-1")])
                    ],
                )
            ],
        ),
    ]
    merged = uh.merge_hypercontinuum_charter(base, extra)
    assert [s["continuum_id"] for s in merged] == ["m1", "m2"]
