"""Unit tests for stewardship tower facade collapse (hermetic)."""

from __future__ import annotations

from blackhole_agent import upstream_constitution_engine as ce
from blackhole_agent import upstream_stewardship_facade as facade
from blackhole_agent import upstream_league as ul
from blackhole_agent import upstream_quettacontinuum as qt


def test_builtin_facade_collapse_proof_green() -> None:
    result = facade.builtin_stewardship_facade_proof()
    assert result["ok"], result
    assert result["layer_count"] == 23
    assert result["layers_ok"] == 23
    assert result["facade_files"] == 23
    assert result["tower_loc_after"] < result["tower_loc_before"] // 10
    assert result["nested_composition"]
    assert result["constitution_engine_ok"]
    assert result["ledger_capability_ok"]
    assert result["stack_complete"]
    assert result["done_when_met"]
    assert not result["used_skill_route_discovery"]


def test_every_layer_module_is_engine_facade() -> None:
    for name in ce.list_stewardship_layers():
        mod = __import__(f"blackhole_agent.upstream_{name}", fromlist=["*"])
        assert getattr(mod, "ENGINE_FACADE", False) is True
        proof = getattr(mod, f"builtin_upstream_{name}_proof")()
        assert proof["ok"], (name, proof.get("flags"))
        assert proof.get("engine_facade") is True


def test_league_and_quetta_public_api_still_callable() -> None:
    assert ul.ENGINE_FACADE is True
    assert qt.ENGINE_FACADE is True
    league = ul.builtin_upstream_league_proof()
    quetta = qt.builtin_upstream_quettacontinuum_proof()
    assert league["ok"] and league["league_met"]
    assert quetta["ok"] and quetta["quettacontinuum_met"] and quetta["charter_expand"]
