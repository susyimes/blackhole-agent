"""Tests for ledger structural attestation."""

from __future__ import annotations

from blackhole_agent.capability_attestation import (
    attest_ledger_structure,
    attest_payload,
    builtin_ledger_attestation,
)


def test_live_ledger_attests_ready() -> None:
    result = attest_ledger_structure()
    assert result["ready"] is True
    assert result["count"] >= 100
    assert result["missing_fields"] == {}
    assert result["unresolved_dependencies"] == {}


def test_unresolved_dependency_fails_attestation() -> None:
    payload = {
        "schema_version": 1,
        "capabilities": {
            "cap.a": {
                "id": "cap.a",
                "name": "a",
                "kind": "python",
                "entry": "m:f",
                "proof_command": "true",
                "dependencies": ["cap.missing"],
                "last_proof_exit_code": 0,
            },
        },
    }
    result = attest_payload(payload)
    assert result["ready"] is False
    assert result["unresolved_dependencies"] == {"cap.a": ["cap.missing"]}


def test_missing_required_field_fails_attestation() -> None:
    payload = {
        "schema_version": 1,
        "capabilities": {
            "cap.a": {"id": "cap.a", "name": "a", "kind": "python", "entry": "m:f",
                      "dependencies": [], "last_proof_exit_code": 0},
            "cap.b": {"id": "cap.b", "name": "b", "kind": "python", "entry": "m:g",
                      "proof_command": "true", "dependencies": [], "last_proof_exit_code": 0},
        },
    }
    result = attest_payload(payload)
    assert result["ready"] is False
    assert result["missing_fields"] == {"cap.a": ["proof_command"]}


def test_wrong_schema_version_fails_attestation() -> None:
    result = attest_payload({"schema_version": 99, "capabilities": {}})
    assert result["ready"] is False
    assert result["schema_version_ok"] is False


def test_builtin_ledger_attestation_proof() -> None:
    result = builtin_ledger_attestation()
    assert result["ok"] is True, result
    assert result["attestation"]["ready"] is True
    assert result["deterministic"] is True
    assert result["unresolved_detected"] is True
    assert result["missing_field_detected"] is True
    assert result["used_skill_route_discovery"] is False
