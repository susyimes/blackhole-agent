"""Log-family certificate seal/verify is one spec-driven engine."""

from __future__ import annotations

import inspect

from blackhole_agent.upstream_total_spine_logs import (
    LOG_FAMILY_SPECS,
    actuate_total_spine,
    builtin_log_family_engine_proof,
    builtin_log_family_runner_proof,
    builtin_total_spine_actuation_proof,
    builtin_total_spine_clearing_proof,
    builtin_total_spine_settlement_proof,
    clear_total_spine,
    seal_total_spine_actuation_certificate,
    seal_total_spine_clearing_certificate,
    seal_total_spine_execution_certificate,
    seal_total_spine_settlement_certificate,
    settle_total_spine,
    verify_total_spine_actuation_certificate,
    verify_total_spine_clearing_certificate,
    verify_total_spine_execution_certificate,
    verify_total_spine_settlement_certificate,
)


def test_builtin_log_family_engine_proof() -> None:
    result = builtin_log_family_engine_proof()
    assert result["ok"] is True
    assert result["wired_count"] == 8
    assert result["used_skill_route_discovery"] is False
    assert set(result["families"]) == {
        "actuation",
        "clearing",
        "execution",
        "settlement",
    }
    assert all(result["wired"].values())
    assert result["checks"]["execution_state_shape"] is True


def test_public_seal_verify_are_spec_wrappers() -> None:
    assert set(LOG_FAMILY_SPECS) == {
        "actuation",
        "clearing",
        "execution",
        "settlement",
    }
    assert LOG_FAMILY_SPECS["execution"].shape == "state"
    seals = (
        seal_total_spine_execution_certificate,
        seal_total_spine_actuation_certificate,
        seal_total_spine_settlement_certificate,
        seal_total_spine_clearing_certificate,
    )
    verifies = (
        verify_total_spine_execution_certificate,
        verify_total_spine_actuation_certificate,
        verify_total_spine_settlement_certificate,
        verify_total_spine_clearing_certificate,
    )
    for fn in seals:
        assert "_seal_log_certificate" in inspect.getsource(fn)
    for fn in verifies:
        assert "_verify_log_certificate" in inspect.getsource(fn)


def test_builtin_log_family_runner_proof() -> None:
    result = builtin_log_family_runner_proof()
    assert result["ok"] is True
    assert result["wired_count"] == 9
    assert result["used_skill_route_discovery"] is False
    assert all(result["wired"].values())


def test_execution_seal_digest_matches_historical_baseline() -> None:
    """State-shape seal must keep the pre-migration execution digest."""

    body = {
        "schema_version": 1,
        "kind": "total_spine_execution",
        "root_layer": "quettacontinuum",
        "goal": "baseline-execution-seal",
        "done_when": "min_proved:1; no_skill_route",
        "source_kind": "quorum",
        "source_digest": "d" * 64,
        "prior_tip": "a" * 64,
        "parent_state_root": "",
        "state_height": 1,
        "capabilities": ["repo.import-health"],
        "effects_ok": True,
        "contract_met": True,
        "origin_count": 3,
        "quorum_met": True,
        "post_finality": True,
        "deterministic": True,
        "irreversible": True,
        "success": True,
        "executed_at": "2026-08-15T00:00:00+00:00",
    }
    sealed = seal_total_spine_execution_certificate(body)
    verdict = verify_total_spine_execution_certificate(sealed)
    assert sealed["execution_digest"] == (
        "305496a9515fe8d2ba625ab8e9fe5bc7539b5efdf8e18fdbea6220081ea86716"
    )
    assert sealed["state_root"] == (
        "7c3d854ce5fa4d6bc37cd0acd6d91902e310b58af3b5ada319254a38e83d8f62"
    )
    assert verdict["ok"] is True
    assert verdict["parent_ok"] is True
    assert verdict["state_root_ok"] is True


def test_public_apply_proof_are_spec_wrappers() -> None:
    applies = (actuate_total_spine, settle_total_spine, clear_total_spine)
    proofs = (
        builtin_total_spine_actuation_proof,
        builtin_total_spine_settlement_proof,
        builtin_total_spine_clearing_proof,
    )
    for fn in applies:
        assert "_apply_log_family" in inspect.getsource(fn)
    for fn in proofs:
        assert "_run_log_family_proof" in inspect.getsource(fn)
