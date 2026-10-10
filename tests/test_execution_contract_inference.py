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


FS_SANDBOX_DONE_WHEN = (
    "tests/acceptance/test_tool_fs_sandbox.py exits 0 reporting passed=true on candidate src "
    "and passed=false on the previous milestone's src, demonstrating over the live HTTP "
    "invocation plane that a fixture absorbed tool invoked via POST /invoke cannot read a "
    "host canary file placed outside the sandbox allowlist, cannot create a file beside "
    "that canary, still reads a file inside its vendored tree, and still returns the "
    "correct declared output. The pre-mission plane reads the canary successfully."
)


@pytest.mark.parametrize("text", [
    FS_SANDBOX_DONE_WHEN,
    "The pre-mission plane reads the canary successfully.",
    "A fixture absorbed tool on the live HTTP invocation plane still returns output.",
    "The candidate reports passed=true; the pre-mission plane still reads the canary.",
])
def test_incidental_pre_mission_plane_does_not_invent_predicate(text):
    parsed = parse_outcome_contract(text)
    kinds = {p["kind"] for p in parsed["predicates"]}
    assert "mission_plane_ok" not in kinds
    assert "contract_plane_ok" not in kinds
    assert "assurance_plane_ok" not in kinds


@pytest.mark.parametrize("text", [
    "mission_plane_ok",
    "The mission plane passes its checks",
    "The mission-plane must be successful",
    "mission plane is ok",
])
def test_explicit_and_affirmative_mission_plane_requirements_stay_enforced(tmp_path, text):
    parsed = parse_outcome_contract(text)
    assert [p["kind"] for p in parsed["predicates"]] == ["mission_plane_ok"]
    absent = evaluate_outcome_contract(tmp_path, text, run_programs=False)
    assert absent["met"] is False
    failed = evaluate_outcome_contract(
        tmp_path, text, context={"mission": {"ok": False}}, run_programs=False
    )
    assert failed["met"] is False
    present = evaluate_outcome_contract(
        tmp_path, text, context={"mission": {"ok": True}}, run_programs=False
    )
    assert present["met"] is True
