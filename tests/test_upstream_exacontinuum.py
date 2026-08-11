"""Unit tests for the upstream exacontinuum plane (hermetic; no network)."""

from __future__ import annotations

from blackhole_agent import upstream_exacontinuum as ee


def test_builtin_proof_green() -> None:
    result = ee.builtin_upstream_exacontinuum_proof()
    assert result["ok"], result.get("flags")
    assert result["exacontinuum_met"]
    assert result["multi_exacontinuum_progressed"]
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


def test_normalize_exacontinuum_charter_dedupes_and_requires_work() -> None:
    charter = ee.normalize_exacontinuum_charter(
        [
            ee._petacontinuum_slot(
                "a",
                institutions=[
                    ee._inst_slot(
                        "i1",
                        programs=[
                            ee._program_slot(
                                "p1", initial=[("x", "1.0.0", "x-1")]
                            )
                        ],
                    )
                ],
            ),
            ee._petacontinuum_slot(
                "a",  # duplicate id ignored
                institutions=[
                    ee._inst_slot(
                        "i2",
                        programs=[
                            ee._program_slot(
                                "p2", initial=[("y", "1.0.0", "y-1")]
                            )
                        ],
                    )
                ],
            ),
            {
                "petacontinuum_id": "empty",
                # no nested charter → dropped
            },
        ]
    )
    assert [s["petacontinuum_id"] for s in charter] == ["a"]
    assert charter[0]["charter"]  # nested teracontinuum slots present


def test_merge_exacontinuum_charter_dedupes_ids() -> None:
    base = [
        ee._petacontinuum_slot(
            "m1",
            institutions=[
                ee._inst_slot(
                    "mi",
                    programs=[
                        ee._program_slot("mp", initial=[("m", "1.0.0", "m-1")])
                    ],
                )
            ],
        )
    ]
    extra = [
        ee._petacontinuum_slot(
            "m1",
            institutions=[
                ee._inst_slot(
                    "mi2",
                    programs=[
                        ee._program_slot("mp2", initial=[("m2", "1.0.0", "m2-1")])
                    ],
                )
            ],
        ),
        ee._petacontinuum_slot(
            "m2",
            institutions=[
                ee._inst_slot(
                    "mj",
                    programs=[
                        ee._program_slot("mp3", initial=[("m3", "1.0.0", "m3-1")])
                    ],
                )
            ],
        ),
    ]
    merged = ee.merge_exacontinuum_charter(base, extra)
    ids = [s["petacontinuum_id"] for s in merged]
    assert ids == ["m1", "m2"]
