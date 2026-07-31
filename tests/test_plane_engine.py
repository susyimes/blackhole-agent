"""Tests for the generic data-driven plane engine."""

from __future__ import annotations

import pytest

from blackhole_agent import plane_engine as pe


def test_differential_proof_matches_legacy_realm_plane() -> None:
    result = pe.differential_proof()
    assert result["ok"] is True
    assert result["used_skill_route_discovery"] is False
    failed = [check["name"] for check in result["checks"] if not check["ok"]]
    assert failed == []
    assert {check["name"] for check in result["checks"]} == {
        "spec_derivation_equal",
        "transitions_equal",
        "cross_chain_verification",
        "bundles_equal",
        "cross_bundle_integrity",
        "adversarial_agreement",
    }


def test_engine_is_deterministic_under_frozen_clock() -> None:
    with pe._frozen_clock():
        first = pe._synthetic_parent_bundle(pe.get_layer("realm"))
        layer = pe.get_layer("realm")
        applied_first = pe.apply_bundle(layer, first, goal="determinism")
    with pe._frozen_clock():
        second = pe._synthetic_parent_bundle(pe.get_layer("realm"))
        applied_second = pe.apply_bundle(layer, second, goal="determinism")
    assert applied_first["ok"] is True
    assert applied_second["ok"] is True
    assert applied_first["tip_realm_root"] == applied_second["tip_realm_root"]
    assert applied_first["realm_plan_digest"] == applied_second["realm_plan_digest"]


def test_unknown_layer_rejected() -> None:
    with pytest.raises(KeyError):
        pe.get_layer("cosmos")


def test_apply_transition_rejects_unknown_parent_root() -> None:
    layer = pe.get_layer("realm")
    parent = pe._synthetic_parent_bundle(layer)
    spec = pe.derive_specs(layer, parent, min_count=2)[0]
    spec["bound_dominion_root"] = "0" * 24
    result = pe.apply_transition(layer, pe.empty_log(layer), spec, parent_bundle=parent)
    assert result["ok"] is False
    assert result["error"] == "bound_dominion_root_mismatch"


def test_apply_transition_rejects_duplicate_parent_binding() -> None:
    layer = pe.get_layer("realm")
    parent = pe._synthetic_parent_bundle(layer)
    specs = pe.derive_specs(layer, parent, min_count=2)
    first = pe.apply_transition(layer, pe.empty_log(layer), specs[0], parent_bundle=parent)
    assert first["ok"] is True
    duplicate = pe.apply_transition(layer, first["log"], specs[0], parent_bundle=parent)
    assert duplicate["ok"] is False
    assert duplicate["error"] == "duplicate_dominion_rejected"


def test_verify_chain_rejects_tampered_root() -> None:
    import copy

    layer = pe.get_layer("realm")
    parent = pe._synthetic_parent_bundle(layer)
    applied = pe.apply_bundle(layer, parent, goal="tamper")
    assert applied["ok"] is True
    log = copy.deepcopy(applied["log"])
    log["entries"][0]["realm_root"] = "e" * 24
    verdict = pe.verify_chain(layer, log)
    assert verdict["valid"] is False
