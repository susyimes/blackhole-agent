"""Post-actuation total-spine dispatch is one spine-stage catalog walk."""

from __future__ import annotations

import inspect

from blackhole_agent.upstream_control_engine import (
    SPINE_POST_CONSENSUS_CHAIN,
    SPINE_PRE_CONSENSUS_CHAIN,
    SPINE_PUBLIC_STAGE_FLAGS,
    SPINE_RESUME_PLANES,
    SPINE_SURFACE_CATALOG_IMPL,
    SPINE_SURFACE_EXPORTED,
    SPINE_SURFACE_FAMILIES,
    SPINE_SURFACE_LOG_FAMILIES,
    SPINE_STAGE_CHAIN,
    SPINE_STAGE_ENGINE_IMPL,
    SPINE_STAGE_POST_ACTUATION_START,
    SPINE_STAGE_POST_CONSENSUS_START,
    _apply_pre_consensus_stages,
    _apply_resume_implies,
    _apply_spine_federation_live,
    _apply_spine_stages,
    _attach_total_spine_effects,
    _collect_spine_stage_flags,
    _imply_caller_spine_flags,
    _attach_spine_federation,
    _select_post_consensus_short_circuit,
    _spine_on_flags,
    _total_spine_short_circuit,
    _derive_spine_short_circuit,
    _TOTAL_SPINE_SHORT_CIRCUIT,
    builtin_spine_attach_catalog_proof,
    builtin_spine_finality_stage_proof,
    builtin_spine_public_catalog_proof,
    builtin_spine_resume_catalog_proof,
    builtin_spine_surface_catalog_proof,
    builtin_spine_family_catalog_proof,
    builtin_spine_short_circuit_catalog_proof,
    builtin_spine_stage_engine_proof,
    derive_spine_family_views,
    run_total_spine,
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
    assert attach_src.count("_apply_spine_stages") == 1
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


def test_builtin_spine_finality_stage_proof() -> None:
    result = builtin_spine_finality_stage_proof()
    assert result["ok"] is True
    assert result["used_skill_route_discovery"] is False
    assert all(result["checks"].values())
    assert all(result["wired"].values())


def test_finality_and_federation_are_catalog_stages() -> None:
    attach_src = inspect.getsource(_attach_total_spine_effects)
    short_src = inspect.getsource(_total_spine_short_circuit)
    fed_src = inspect.getsource(_apply_spine_federation_live)
    assert "_apply_pre_consensus_stages" in attach_src
    assert "_attach_spine_federation" in fed_src
    assert "_attach_spine_federation" in short_src
    assert "federate_total_spine(" not in attach_src
    assert "if resume_finality is not None" not in attach_src
    resume = {name: None for name in SPINE_RESUME_PLANES}
    resume["finality"] = {"kind": "probe"}
    assert _select_post_consensus_short_circuit(resume) == "finality"
    empty = _attach_spine_federation({"ok": True}, peers=[])
    assert empty["total_spine_federation"] is False
    blocked = _attach_spine_federation(
        {"ok": True, "total_spine_finality": False},
        peers=["peer"],
    )
    assert blocked["total_spine_federation_requires_finality"] is True


def test_builtin_spine_attach_catalog_proof() -> None:
    result = builtin_spine_attach_catalog_proof()
    assert result["ok"] is True
    assert result["stage_count"] == 5
    assert result["used_skill_route_discovery"] is False
    assert all(result["checks"].values())
    assert all(result["wired"].values())


def test_builtin_spine_short_circuit_catalog_proof() -> None:
    result = builtin_spine_short_circuit_catalog_proof()
    assert result["ok"] is True
    assert result["stage_count"] == 20
    assert result["used_skill_route_discovery"] is False
    assert all(result["checks"].values())
    assert all(result["wired"].values())


def test_short_circuit_rows_are_derived_from_catalogs() -> None:
    derived = _derive_spine_short_circuit()
    assert list(derived) == list(SPINE_RESUME_PLANES)
    assert derived == _TOTAL_SPINE_SHORT_CIRCUIT
    assert derived["finality"]["federate"] is True
    assert derived["finality"]["cont"] == ("execution", ())
    assert derived["execution"]["post_actuation"] is True
    assert derived["margin"]["cont"] is None
    assert "margin" in derived["custody"]["impls"]
    derive_src = inspect.getsource(_derive_spine_short_circuit)
    assert "SPINE_RESUME_PLANES" in derive_src
    assert "SPINE_RESUME_POST_CONSENSUS" in derive_src
    assert '"settlement": {' not in derive_src


def test_live_attach_is_one_pre_consensus_catalog_walk() -> None:
    assert list(SPINE_PRE_CONSENSUS_CHAIN) == [
        "dispatch",
        "adaptive",
        "continuity",
        "finality",
        "federation",
    ]
    attach_src = inspect.getsource(_attach_total_spine_effects)
    walk_src = inspect.getsource(_apply_pre_consensus_stages)
    assert attach_src.count("_apply_pre_consensus_stages") == 1
    assert attach_src.count("_apply_spine_stages") == 1
    assert "for round_index in range" not in attach_src
    assert "resume_finality =" not in attach_src
    assert "finality_on = on[" not in attach_src
    assert "write_total_spine_finality_certificate" not in attach_src
    assert "federate_total_spine(" not in attach_src
    assert "SPINE_PRE_CONSENSUS_CHAIN" in walk_src


def test_builtin_spine_public_catalog_proof() -> None:
    result = builtin_spine_public_catalog_proof()
    assert result["ok"] is True
    assert result["stage_count"] == 19
    assert result["used_skill_route_discovery"] is False
    assert all(result["checks"].values())
    assert all(result["wired"].values())


def test_public_stage_flags_are_catalog_validated() -> None:
    assert list(SPINE_PUBLIC_STAGE_FLAGS)[0] == "execution"
    assert list(SPINE_PUBLIC_STAGE_FLAGS)[-1] == "reorganization"
    assert "finality" not in SPINE_PUBLIC_STAGE_FLAGS
    collected = _collect_spine_stage_flags(None, {"solvency": True})
    assert collected["solvency"] is True
    assert collected["execution"] is False
    try:
        _collect_spine_stage_flags(None, {"not_a_spine_stage": True})
    except TypeError:
        refused = True
    else:
        refused = False
    assert refused is True
    attach_src = inspect.getsource(_attach_total_spine_effects)
    run_src = inspect.getsource(run_total_spine)
    assert "reorganization: bool = False" not in attach_src
    assert "reorganization: bool = False" not in run_src
    assert "reorganization=reorganization" not in run_src
    assert run_src.count("stages=requested_stages") == 2


def test_builtin_spine_surface_catalog_proof() -> None:
    result = builtin_spine_surface_catalog_proof()
    assert result["ok"] is True
    assert result["family_count"] == 18
    assert result["used_skill_route_discovery"] is False
    assert all(result["checks"].values())
    assert all(result["wired"].values())


def test_spine_surface_is_one_catalog_reexport() -> None:
    import blackhole_agent.upstream_control_engine as uce
    from blackhole_agent.upstream_total_spine_solvency import (
        annotate_total_spine_solvency,
    )

    assert SPINE_SURFACE_CATALOG_IMPL is True
    assert list(SPINE_SURFACE_LOG_FAMILIES) == [
        "actuation",
        "settlement",
        "clearing",
    ]
    assert list(SPINE_SURFACE_FAMILIES)[:3] == [
        "actuation",
        "settlement",
        "clearing",
    ]
    assert "execution" not in SPINE_SURFACE_FAMILIES
    assert "reorganization" in SPINE_SURFACE_FAMILIES
    assert len(SPINE_SURFACE_EXPORTED) >= 18 * 14
    src = inspect.getsource(uce)
    leftover_families = ("actuation", "solvency", "reorganization")
    assert all(
        f"from blackhole_agent.upstream_total_spine_{name} import" not in src
        for name in leftover_families
    )
    assert uce.annotate_total_spine_solvency is annotate_total_spine_solvency
    assert uce.TOTAL_SPINE_SOLVENCY_IMPL is True
    assert callable(uce.actuate_total_spine)
    assert callable(uce.reorganize_total_spine)


def test_builtin_spine_family_catalog_proof() -> None:
    result = builtin_spine_family_catalog_proof()
    assert result["ok"] is True
    assert result["chain_count"] == 19
    assert result["family_count"] == 18
    assert result["used_skill_route_discovery"] is False
    assert all(result["checks"].values())
    assert all(result["wired"].values())


def test_builtin_module_synthesis_plane_proof() -> None:
    from blackhole_agent.upstream_module_synthesis import (
        builtin_module_synthesis_plane_proof,
    )

    result = builtin_module_synthesis_plane_proof()
    assert result["ok"] is True
    assert result["catalog_count"] == 42
    assert result["facade_count"] == 23
    assert result["pair_count"] == 15
    assert result["log_count"] == 4
    assert result["used_skill_route_discovery"] is False
    assert all(result["checks"].values())
    assert all(result["wired"].values())


def test_module_synthesis_probe_is_a_catalog_row() -> None:
    from blackhole_agent.upstream_module_synthesis import (
        derive_module_synthesis_catalog,
        resolve_synthesis_row,
    )

    live = resolve_synthesis_row("blackhole_agent.upstream_total_spine_ratification")
    assert live is None
    probe = derive_module_synthesis_catalog(extra_pair=("ratification",))
    row = resolve_synthesis_row(
        "blackhole_agent.upstream_total_spine_ratification",
        catalog=probe,
    )
    assert row is not None
    assert row.kind == "pair_effect"
    assert row.name == "ratification"


def test_builtin_spine_signature_catalog_proof() -> None:
    from blackhole_agent.upstream_total_spine_effects import (
        PAIR_EFFECT_SPECS,
        builtin_spine_signature_catalog_proof,
        derive_pair_effect_signatures,
    )

    result = builtin_spine_signature_catalog_proof()
    assert result["ok"] is True
    assert result["spec_count"] == 15
    assert result["used_skill_route_discovery"] is False
    assert all(result["checks"].values())
    assert all(result["wired"].values())
    solvency = PAIR_EFFECT_SPECS["solvency"]
    derived = derive_pair_effect_signatures(solvency)
    assert derived == solvency.signatures
    assert "solvency_total_spine" in derived


def test_spine_signature_catalog_probe_is_a_token_row() -> None:
    from blackhole_agent.upstream_total_spine_effects import (
        PAIR_EFFECT_SPECS,
        PairEffectSpec,
        derive_pair_effect_signatures,
    )

    probe = PairEffectSpec(
        effect="ratification",
        plural="ratifications",
        verb="ratify",
        pred="reorganization",
        pred_plural="reorganizations",
        code="rtr",
        code_upper="Rtr",
        pred_code="rvc",
        pred_code_upper="Rvc",
        verdict_1="ratified_ok",
        verdict_2="treaty_ok",
        adj_1="ratified",
        adj_2="treatied",
        adj_1_negated="unratified",
        counterpart="treaty",
        pred_done="reorganized",
        pred_verdict_1="chartered",
        pred_verdict_2="rvc_ok",
        post_key="post_reorganization",
        min_name="RATIFICATIONS",
        collect_push=("reorganization",),
        abbr="rat",
        refusal_pred_tampered="margin_tampered",
        refusal_pred_short="margins_short",
        refusal_pred_not_done="capital_unreorganized",
        refusal_pred_unmet="capital_unrequired",
        refusal_code_failed="rvc_failed",
        summary="probe",
    )
    names = derive_pair_effect_signatures(probe)
    assert "ratify_total_spine" in names
    assert "annotate_total_spine_ratification" in names
    assert "ratification" not in PAIR_EFFECT_SPECS


def test_builtin_spine_family_engine_proof() -> None:
    from blackhole_agent.upstream_spine_family import (
        builtin_spine_family_engine_proof,
    )

    result = builtin_spine_family_engine_proof()
    assert result["ok"] is True
    assert result["catalog_count"] == 19
    assert result["pair_count"] == 15
    assert result["log_count"] == 4
    assert result["used_skill_route_discovery"] is False
    assert all(result["checks"].values())
    assert all(result["wired"].values())


def test_spine_family_engine_probe_is_a_catalog_row() -> None:
    from blackhole_agent.upstream_spine_family import (
        derive_spine_family_engine_catalog,
        resolve_family_row,
    )

    assert resolve_family_row("ratification") is None
    probe = derive_spine_family_engine_catalog(extra_pair=("ratification",))
    row = resolve_family_row("ratification", catalog=probe)
    assert row is not None
    assert row.kind == "pair_effect"
    assert row.shape == "pair"
    assert row.populate == "signatures"


def test_spine_family_catalog_probe_extends_views() -> None:
    base = derive_spine_family_views()
    probe = derive_spine_family_views(
        extra_chain=(("ratification", "reorganization", "ratify", "self"),),
        extra_surface_pair=("ratification",),
    )
    assert base["post_consensus"][-1] == "reorganization"
    assert probe["post_consensus"][-1] == "ratification"
    assert "ratification" in probe["public_flags"]
    assert "ratification" in probe["resume_planes"]
    assert probe["surface_families"][-1] == "ratification"
    assert "ratification" not in probe["continuity_guard"]
    assert "ratification" not in probe["want_effects"]
    assert "ratification" not in probe["config_order"]
    assert "ratification" not in base["public_flags"]
