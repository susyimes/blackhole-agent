"""Streak storage for the invocation failure circuit."""

from __future__ import annotations

from pathlib import Path

import pytest

from blackhole_agent.invocation_failure_circuit import (
    FAILURE_CIRCUIT_THRESHOLD,
    FailureCircuit,
    parse_circuit_path,
)


def test_three_nonzero_exits_open_and_survive_a_new_instance(tmp_path: Path) -> None:
    first = FailureCircuit(tmp_path)
    assert first.note_failure("capability.absorbed-flaky")["open"] is False
    assert first.note_failure("capability.absorbed-flaky")["consecutive_failures"] == 2
    opened = first.note_failure("capability.absorbed-flaky")
    assert opened["open"] is True
    assert opened["consecutive_failures"] == FAILURE_CIRCUIT_THRESHOLD

    restarted = FailureCircuit(tmp_path)
    view = restarted.view("capability.absorbed-flaky")
    assert view["open"] is True
    assert view["consecutive_failures"] == 3
    assert restarted.open_count() == 1
    sibling = restarted.view("capability.absorbed-sibling")
    assert sibling["open"] is False
    assert sibling["consecutive_failures"] == 0


def test_success_before_threshold_resets_the_streak(tmp_path: Path) -> None:
    circuit = FailureCircuit(tmp_path)
    circuit.note_failure("capability.absorbed-flaky")
    circuit.note_failure("capability.absorbed-flaky")
    cleared = circuit.note_success("capability.absorbed-flaky")
    assert cleared["consecutive_failures"] == 0
    assert cleared["open"] is False
    again = circuit.note_failure("capability.absorbed-flaky")
    assert again["consecutive_failures"] == 1
    assert again["open"] is False


def test_close_clears_an_open_circuit(tmp_path: Path) -> None:
    circuit = FailureCircuit(tmp_path)
    for _ in range(FAILURE_CIRCUIT_THRESHOLD):
        circuit.note_failure("capability.absorbed-flaky")
    closed = circuit.close("capability.absorbed-flaky")
    assert closed["open"] is False
    assert circuit.view("capability.absorbed-flaky")["consecutive_failures"] == 0
    assert circuit.open_count() == 0
    assert circuit.close("capability.absorbed-flaky")["open"] is False


def test_parse_circuit_path_rejects_other_routes() -> None:
    assert parse_circuit_path("/circuits/capability.absorbed-flaky") == "capability.absorbed-flaky"
    assert parse_circuit_path("/circuits/capability.absorbed-flaky?x=1") == "capability.absorbed-flaky"
    assert parse_circuit_path("/invoke") is None
    assert parse_circuit_path("/circuits") is None
    assert parse_circuit_path("/circuits/a/b") is None


def test_invalid_capability_id_is_refused(tmp_path: Path) -> None:
    circuit = FailureCircuit(tmp_path)
    with pytest.raises(ValueError):
        circuit.note_failure("../ledger")


def test_further_failures_do_not_advance_an_open_circuit(tmp_path: Path) -> None:
    circuit = FailureCircuit(tmp_path)
    for _ in range(FAILURE_CIRCUIT_THRESHOLD):
        circuit.note_failure("capability.absorbed-flaky")
    again = circuit.note_failure("capability.absorbed-flaky")
    assert again["open"] is True
    assert again["consecutive_failures"] == FAILURE_CIRCUIT_THRESHOLD
