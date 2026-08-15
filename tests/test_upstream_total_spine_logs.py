"""Log-family certificate seal/verify is one spec-driven engine."""

from __future__ import annotations

import inspect

from blackhole_agent.upstream_total_spine_logs import (
    LOG_FAMILY_SPECS,
    builtin_log_family_engine_proof,
    seal_total_spine_actuation_certificate,
    seal_total_spine_clearing_certificate,
    seal_total_spine_settlement_certificate,
    verify_total_spine_actuation_certificate,
    verify_total_spine_clearing_certificate,
    verify_total_spine_settlement_certificate,
)


def test_builtin_log_family_engine_proof() -> None:
    result = builtin_log_family_engine_proof()
    assert result["ok"] is True
    assert result["wired_count"] == 6
    assert result["used_skill_route_discovery"] is False
    assert set(result["families"]) == {"actuation", "settlement", "clearing"}
    assert all(result["wired"].values())


def test_public_seal_verify_are_spec_wrappers() -> None:
    assert set(LOG_FAMILY_SPECS) == {"actuation", "settlement", "clearing"}
    seals = (
        seal_total_spine_actuation_certificate,
        seal_total_spine_settlement_certificate,
        seal_total_spine_clearing_certificate,
    )
    verifies = (
        verify_total_spine_actuation_certificate,
        verify_total_spine_settlement_certificate,
        verify_total_spine_clearing_certificate,
    )
    for fn in seals:
        assert "_seal_log_certificate" in inspect.getsource(fn)
    for fn in verifies:
        assert "_verify_log_certificate" in inspect.getsource(fn)
