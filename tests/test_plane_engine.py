"""Tests for the generic data-driven plane engine."""

from __future__ import annotations

import copy

import pytest

from blackhole_agent import plane_engine as pe

legacy_only = pytest.mark.skipif(
    not pe._legacy_reference_available(),
    reason="legacy plane code deleted; differential reference intentionally gone",
)


@legacy_only
def test_differential_proof_matches_legacy_planes() -> None:
    result = pe.differential_proof()
    assert result["ok"] is True
    assert result["used_skill_route_discovery"] is False
    assert result["layer_count"] == len(pe.LAYERS) == 42
    expected_checks = {
        "spec_derivation_equal",
        "transitions_equal",
        "cross_chain_verification",
        "bundles_equal",
        "cross_bundle_integrity",
        "adversarial_agreement",
    }
    for layer_result in result["layers"]:
        assert layer_result["ok"] is True, layer_result["layer"]
        failed = [c["name"] for c in layer_result["checks"] if not c["ok"]]
        assert failed == [], layer_result["layer"]
        assert {c["name"] for c in layer_result["checks"]} == expected_checks


@legacy_only
def test_differential_proof_layer_subset() -> None:
    result = pe.differential_proof(layer_names=["cosmos", "pact", "recovery"])
    assert result["ok"] is True
    assert result["layer_count"] == 3
    assert [layer["layer"] for layer in result["layers"]] == [
        "cosmos",
        "pact",
        "recovery",
    ]


@legacy_only
def test_settlement_dialect_matches_legacy() -> None:
    result = pe.differential_proof(layer_names=["settlement", "clearing", "margin"])
    assert result["ok"] is True
    assert result["layer_count"] == 3


def test_full_stack_builtin_covers_all_42_layers() -> None:
    result = pe.builtin_plane_engine_full_stack()
    assert result["ok"] is True
    assert result["layer_count"] == 42
    assert "settlement" in result["layers"]
    assert "cosmos" in result["layers"]


def test_golden_proof_is_hermetic() -> None:
    result = pe.golden_proof()
    assert result["ok"] is True
    assert result["layer_count"] == 42
    bad = [layer["layer"] for layer in result["layers"] if not layer["ok"]]
    assert bad == []


def test_engine_is_deterministic_under_frozen_clock() -> None:
    layer = pe.get_layer("realm")
    with pe._frozen_clock():
        first = pe._synthetic_parent_bundle(layer)
        applied_first = pe.apply_bundle(layer, first, goal="determinism")
    with pe._frozen_clock():
        second = pe._synthetic_parent_bundle(layer)
        applied_second = pe.apply_bundle(layer, second, goal="determinism")
    assert applied_first["ok"] is True
    assert applied_second["ok"] is True
    assert applied_first["tip_realm_root"] == applied_second["tip_realm_root"]
    assert applied_first["realm_plan_digest"] == applied_second["realm_plan_digest"]


def test_unknown_layer_rejected() -> None:
    with pytest.raises(KeyError):
        pe.get_layer("nonexistent-layer")


def test_apply_transition_rejects_unknown_parent_root() -> None:
    layer = pe.get_layer("realm")
    parent = pe.golden_parent_bundle("realm")
    spec = pe.derive_specs(layer, parent, min_count=2)[0]
    spec["bound_dominion_root"] = "0" * 24
    result = pe.apply_transition(layer, pe.empty_log(layer), spec, parent_bundle=parent)
    assert result["ok"] is False
    assert result["error"] == "bound_dominion_root_mismatch"


def test_apply_transition_rejects_duplicate_parent_binding() -> None:
    layer = pe.get_layer("realm")
    parent = pe.golden_parent_bundle("realm")
    specs = pe.derive_specs(layer, parent, min_count=2)
    first = pe.apply_transition(layer, pe.empty_log(layer), specs[0], parent_bundle=parent)
    assert first["ok"] is True
    duplicate = pe.apply_transition(layer, first["log"], specs[0], parent_bundle=parent)
    assert duplicate["ok"] is False
    assert duplicate["error"] == "duplicate_dominion_rejected"


def test_verify_chain_rejects_tampered_root() -> None:
    layer = pe.get_layer("realm")
    parent = pe.golden_parent_bundle("realm")
    applied = pe.apply_bundle(layer, parent, goal="tamper")
    assert applied["ok"] is True
    log = copy.deepcopy(applied["log"])
    log["entries"][0]["realm_root"] = "e" * 24
    verdict = pe.verify_chain(layer, log)
    assert verdict["valid"] is False
