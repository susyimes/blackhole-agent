"""Post-actuation total-spine dispatch is one spine-stage catalog walk."""

from __future__ import annotations

import inspect

from blackhole_agent.upstream_control_engine import (
    SPINE_POST_CONSENSUS_CHAIN,
    SPINE_RESUME_PLANES,
    SPINE_STAGE_CHAIN,
    SPINE_STAGE_ENGINE_IMPL,
    SPINE_STAGE_POST_ACTUATION_START,
    SPINE_STAGE_POST_CONSENSUS_START,
    _apply_resume_implies,
    _apply_spine_stages,
    _attach_total_spine_effects,
    _imply_caller_spine_flags,
    _select_post_consensus_short_circuit,
    _spine_on_flags,
    _total_spine_short_circuit,
    builtin_spine_resume_catalog_proof,
    builtin_spine_stage_engine_proof,
)


def test_builtin_spine_stage_engine_proof() -> None:
    result = builtin_spine_stage_engine_proof()
    assert result["ok"] is True
    assert result["stage_count"] == 17
    assert result["post_consensus_count"] == 19
    assert result["used_skill_route_discovery"] is False
    assert all(result["checks"].values())
    assert all(result["wired"].values())


def test_attach_and_short_circuit_share_the_catalog_walk() -> None:
    assert SPINE_STAGE_ENGINE_IMPL is True
    assert SPINE_STAGE_POST_ACTUATION_START == "settlement"
    assert SPINE_STAGE_POST_CONSENSUS_START == "execution"
    assert [row[0] for row in SPINE_STAGE_CHAIN][0] == "settlement"
    assert [row[0] for row in SPINE_STAGE_CHAIN][-1] == "reorganization"
    assert [row[0] for row in SPINE_POST_CONSENSUS_CHAIN][:2] == [
        "execution",
        "actuation",
    ]
    attach_src = inspect.getsource(_attach_total_spine_effects)
    short_src = inspect.getsource(_total_spine_short_circuit)
    apply_src = inspect.getsource(_apply_spine_stages)
    assert attach_src.count("_apply_spine_stages") == 2
    assert "SPINE_STAGE_POST_CONSENSUS_START" in attach_src
    assert "_apply_total_spine_effect(" not in attach_src
    assert "_apply_total_spine_chain(" not in attach_src
    assert "execute_total_spine(" not in attach_src
    assert "actuate_total_spine(" not in attach_src
    assert "_apply_spine_stages" in short_src
    assert "actuate_total_spine(" not in short_src
    assert "_apply_total_spine_chain" in apply_src


def test_builtin_spine_resume_catalog_proof() -> None:
    result = builtin_spine_resume_catalog_proof()
    assert result["ok"] is True
    assert result["plane_count"] == 20
    assert result["used_skill_route_discovery"] is False
    assert all(result["checks"].values())
    assert all(result["wired"].values())


def test_resume_catalog_owns_attach_rehydrate() -> None:
    assert list(SPINE_RESUME_PLANES)[0] == "finality"
    assert list(SPINE_RESUME_PLANES)[-1] == "reorganization"
    attach_src = inspect.getsource(_attach_total_spine_effects)
    assert "_load_spine_resume_certificates" in attach_src
    assert "_select_post_consensus_short_circuit" in attach_src
    assert "load_total_spine_reorganization_certificate" not in attach_src
    assert "if resume_reorganization is not None" not in attach_src
    assert "execution_on=execution_on" not in attach_src
    implied = _imply_caller_spine_flags({"reorganization": True})
    assert implied["finality"] is True
    assert implied["execution"] is True
    settlement_only = _imply_caller_spine_flags({"settlement": True})
    assert settlement_only["actuation"] is False
    resume = {name: None for name in SPINE_RESUME_PLANES}
    resume["solvency"] = {"kind": "probe"}
    asserted = _apply_resume_implies({}, resume)
    assert asserted["finality"] is True
    assert asserted["solvency"] is True
    assert asserted["risk"] is False
    assert _select_post_consensus_short_circuit(resume) == "solvency"
    on_flags = _spine_on_flags({}, resume)
    assert on_flags["solvency_on"] is True
    assert on_flags["risk_on"] is False
