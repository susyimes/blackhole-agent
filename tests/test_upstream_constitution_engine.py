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
    assert result["continuum_tower_as_data"]
    assert result["stewardship_stack_as_data"]
    assert result["nested_composition"]
    assert not result["used_skill_route_discovery"]
    assert "quettacontinuum" in (result.get("continuum_layers") or [])
    assert "continuum" in (result.get("continuum_layers") or [])
    assert "institution" in (result.get("stewardship_layers") or [])
    assert int(result.get("stewardship_layer_count") or 0) >= 23


def test_continuum_stack_registered_as_data() -> None:
    names = ce.list_continuum_layers()
    assert names[0] == "quettacontinuum"
    assert names[-1] == "continuum"
    assert len(names) == len(ce.CONTINUUM_STACK)
    quetta = ce.get_continuum_layer("quettacontinuum")
    assert quetta.child == "ronnacontinuum"
    assert quetta.all_children_met_goal == "all_ronnacontinuums_met"


def test_stewardship_stack_covers_civilization_tower() -> None:
    names = ce.list_stewardship_layers()
    assert names[0] == "quettacontinuum"
    assert names[-1] == "institution"
    assert "omniverse" in names
    assert "league" in names
    assert len(names) == len(ce.STEWARDSHIP_STACK)
    assert len(names) > len(ce.CONTINUUM_STACK)
    multi = ce.get_stewardship_layer("multiverse")
    assert multi.child == "cosmos"
    assert multi.plural == "cosmoses"
    inst = ce.get_stewardship_layer("institution")
    assert inst.child == "program"
    assert inst.all_children_met_goal == "all_programs_met"
    assert ce.list_civilization_layers()[0] == "omniverse"
    assert ce.list_civilization_layers()[-1] == "institution"


def test_nested_composition_league_to_institution() -> None:
    from pathlib import Path
    import tempfile
    import shutil

    scratch = Path(tempfile.mkdtemp(prefix="ce-nest-"))
    try:
        league = ce.get_stewardship_layer("league")
        institution = ce.get_stewardship_layer("institution")
        runner = ce.make_nested_child_runner(institution)
        result = ce.run_constitution(
            league,
            charter=[
                {
                    "institution_id": "i1",
                    "priority": 1,
                    "max_rounds": 4,
                    "charter": [
                        ce._slot(institution, "p1", keys=[("n", "1.0.0", "d1")]),
                    ],
                }
            ],
            max_rounds=4,
            dispatch=True,
            child_runner=runner,
            goal=league.all_children_met_goal,
            out_root=scratch / "L",
        )
        assert result["ok"]
        assert result[league.self_met_field]
        sealed = ce.verify_receipt(league, Path(result[f"{league.name}_dir"]))
        assert sealed["ok"]
        nested_dirs = [
            r.get(league.child_dir_field)
            for r in (result.get(league.plural) or [])
            if r.get(league.child_dir_field)
        ]
        assert nested_dirs
        assert ce.verify_receipt(institution, Path(str(nested_dirs[0])))["ok"]
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


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
