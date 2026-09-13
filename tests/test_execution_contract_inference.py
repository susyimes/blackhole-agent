"""Prose about refusing duplicate execution must not invent a plane contract."""

import pytest

from blackhole_agent.capability_compounder import evaluate_outcome_contract, parse_outcome_contract


@pytest.mark.parametrize("text", [
    "Refuse automatic re-execution while fresh work still succeeds.",
    "After killing a server, refuse re-execution. The independent probe passes.",
    "A token is returned without execution.",
    "No execution occurs when the payload check passes.",
    "The execution plane is not required for successful HTTP retries.",
    "Execution must not succeed when authorization fails.",
    "The report describes execution. An unrelated UI test passes.",
])
def test_incidental_or_negated_execution_does_not_invent_predicate(text):
    parsed = parse_outcome_contract(text)
    assert not any(p["kind"] == "execution_ok" for p in parsed["predicates"])
    assert text in parsed["notes"]


@pytest.mark.parametrize("text", [
    "execution_ok",
    "Require execution_ok before completion",
    "Execution succeeds",
    "Execution must succeed after recovery",
    "The execution plane passes its checks",
    "The execution-plane must be successful",
    "Execution should be ok",
])
def test_explicit_and_affirmative_execution_requirements_stay_enforced(tmp_path, text):
    parsed = parse_outcome_contract(text)
    assert [p["kind"] for p in parsed["predicates"]] == ["execution_ok"]
    # No outcome is fabricated: genuine execution requirements still require
    # their execution-plane evidence, regardless of the phrasing used.
    absent = evaluate_outcome_contract(tmp_path, text, run_programs=False)
    assert absent["met"] is False
    failed = evaluate_outcome_contract(tmp_path, text, context={"execution": {"ok": False}}, run_programs=False)
    assert failed["met"] is False
    present = evaluate_outcome_contract(tmp_path, text, context={"execution": {"ok": True}}, run_programs=False)
    assert present["met"] is True


def test_explicit_predicate_is_retained_alongside_retry_prose(tmp_path):
    text = "Refuse re-execution while fresh work succeeds; execution_ok"
    parsed = parse_outcome_contract(text)
    assert [p["kind"] for p in parsed["predicates"]] == ["execution_ok"]
    assert evaluate_outcome_contract(tmp_path, text, run_programs=False)["met"] is False
