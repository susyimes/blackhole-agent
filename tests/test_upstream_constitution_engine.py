"""Unit tests for the generic multi-child constitution engine (hermetic)."""

from __future__ import annotations

from blackhole_agent import upstream_constitution_engine as ce


def test_builtin_proof_green() -> None:
    result = ce.builtin_constitution_engine_proof()
    assert result["ok"], result.get("flags")
    assert result["multi_child_met"]
    assert result["priority_scheduling"]
    assert result["federation_coverage"]
    assert result["seal_verified"]
    assert result["tamper_detected"]
    assert result["deferred_admission"]
    assert result["charter_expand"]
    assert result["terminal_coverage_goal"]
    assert result["budget_stops"]
    assert result["rank_only"]
    assert result["empty_refused"]
    assert result["custom_stop"]
    assert result["durable_resume"]
    assert result["roi_scored"]
    assert result["second_layer_data_only"]
    assert result["legacy_quetta_parity"]
    assert not result["used_skill_route_discovery"]


def test_normalize_charter_dedupes_and_requires_work() -> None:
    layer = ce.ConstitutionLayer(name="meta", child="province")
    charter = ce.normalize_charter(
        layer,
        [
            ce._slot(layer, "a", keys=[("x", "1.0.0", "x-1")]),
            ce._slot(layer, "a", keys=[("y", "1.0.0", "y-1")]),  # dup id
            {"province_id": "empty"},  # no work
        ],
    )
    assert [s["province_id"] for s in charter] == ["a"]
    assert charter[0]["inventory_keys"]


def test_terminal_coverage_from_inventory_keys() -> None:
    child_states = [
        {"inventory_keys": [("n", "1.0.0", "d1"), ("n", "1.0.0", "d2")]}
    ]
    empty = ce.terminal_coverage(child_states=child_states, federated_portfolio=None)
    assert empty["required"] == 2
    assert empty["covered"] == 0
    assert not empty["met"]

    portfolio = ce.make_portfolio(
        [
            {
                "name": "n",
                "version": "1.0.0",
                "defect_id": "d1",
                "outcome": "impact_merged",
                "impact_digest": "a",
            },
            {
                "name": "n",
                "version": "1.0.0",
                "defect_id": "d2",
                "outcome": "impact_released",
                "impact_digest": "b",
            },
        ],
        source="test",
    )
    full = ce.terminal_coverage(
        child_states=child_states, federated_portfolio=portfolio
    )
    assert full["met"]
    assert full["coverage_ratio"] == 1.0
