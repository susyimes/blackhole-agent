"""Post-actuation total-spine dispatch is one spine-stage catalog walk."""

from __future__ import annotations

import inspect

from blackhole_agent.upstream_control_engine import (
    SPINE_STAGE_CHAIN,
    SPINE_STAGE_ENGINE_IMPL,
    SPINE_STAGE_POST_ACTUATION_START,
    _apply_spine_stages,
    _attach_total_spine_effects,
    _total_spine_short_circuit,
    builtin_spine_stage_engine_proof,
)


def test_builtin_spine_stage_engine_proof() -> None:
    result = builtin_spine_stage_engine_proof()
    assert result["ok"] is True
    assert result["stage_count"] == 17
    assert result["used_skill_route_discovery"] is False
    assert all(result["checks"].values())
    assert all(result["wired"].values())


def test_attach_and_short_circuit_share_the_catalog_walk() -> None:
    assert SPINE_STAGE_ENGINE_IMPL is True
    assert SPINE_STAGE_POST_ACTUATION_START == "settlement"
    assert [row[0] for row in SPINE_STAGE_CHAIN][0] == "settlement"
    assert [row[0] for row in SPINE_STAGE_CHAIN][-1] == "reorganization"
    attach_src = inspect.getsource(_attach_total_spine_effects)
    short_src = inspect.getsource(_total_spine_short_circuit)
    apply_src = inspect.getsource(_apply_spine_stages)
    assert attach_src.count("_apply_spine_stages") == 2
    assert "_apply_total_spine_effect(" not in attach_src
    assert "_apply_total_spine_chain(" not in attach_src
    assert "_apply_spine_stages" in short_src
    assert "_apply_total_spine_chain" in apply_src
