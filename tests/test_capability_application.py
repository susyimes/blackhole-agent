"""Tests for the capability application plane."""

from __future__ import annotations

import json
from pathlib import Path

from blackhole_agent.capability_application import (
    APPLICATION_STEPS,
    APPLICATION_TASKS,
    REPO_ROOT,
    builtin_application_plane,
    build_application_registry,
    check_planner_honesty,
    compute_application_grade,
    execute_application_plan,
    plan_application_task,
    run_application_plane,
    run_application_task,
    verify_application_report,
    write_application_report,
)
from blackhole_agent.capability_compounder import (
    default_ledger_path,
    load_ledger,
)


def _live_registry():
    ledger = load_ledger(default_ledger_path(REPO_ROOT))
    return build_application_registry(ledger)


def test_tasks_declare_goals_without_step_sequences() -> None:
    # The whole point of the plane: tasks name goal keys, never capabilities.
    for task in APPLICATION_TASKS:
        assert task.goal, task.id
        assert task.oracle, task.id
        assert not hasattr(task, "steps")
        for key in task.oracle:
            assert key in set(task.initial_state) | {
                provided for step in APPLICATION_STEPS.values() for provided in step.provides
            }, (task.id, key)


def test_every_step_capability_is_proved_in_live_ledger() -> None:
    ledger = load_ledger(default_ledger_path(REPO_ROOT))
    for capability_id in APPLICATION_STEPS:
        capability = ledger.capabilities.get(capability_id)
        assert capability is not None, capability_id
        assert capability.last_proof_exit_code == 0, capability_id


def test_planner_derives_minimal_plans_from_goals() -> None:
    registry = _live_registry()
    plans = {task.id: plan_application_task(task, registry) for task in APPLICATION_TASKS}
    assert plans["routed-triage-record"] == [
        "domain.tool-routing",
        "domain.issue-triage",
        "domain.local-memory",
    ]
    assert plans["scan-gated-activation"] == ["domain.ci-security", "domain.harness-activation"]
    assert plans["blocked-scan-honesty"] == ["domain.ci-security", "domain.harness-activation"]
    assert plans["ledger-gated-proposal"] == ["capability.ledger-attestation", "domain.proposal-eval"]
    assert plans["ledger-inventory-check"] == ["capability.ledger-attestation"]
    assert plans["persona-stamped-proposal"] == ["domain.persona", "domain.proposal-synthesis"]


def test_each_task_matches_oracle_and_plan_ablations_break() -> None:
    registry = _live_registry()
    for task in APPLICATION_TASKS:
        result = run_application_task(task, registry)
        assert result["ok"] is True, (task.id, result["error"], result["outcome"])
        plan = result["plan"]
        assert plan, task.id
        for removed in plan:
            sub_plan = [capability_id for capability_id in plan if capability_id != removed]
            ablated = run_application_task(task, registry, plan_override=sub_plan)
            assert ablated["ok"] is False, (task.id, removed)
        if len(plan) >= 2:
            reversed_result = run_application_task(task, registry, plan_override=list(reversed(plan)))
            assert reversed_result["ok"] is False, task.id


def test_planner_honesty_hidden_capability_goes_unsolvable() -> None:
    honesty = check_planner_honesty()
    assert honesty["honest"] is True, honesty


def test_hidden_capability_is_excluded_from_registry() -> None:
    ledger = load_ledger(default_ledger_path(REPO_ROOT))
    registry = build_application_registry(ledger, hide=("domain.tool-routing",))
    assert "domain.tool-routing" not in registry
    task = next(task for task in APPLICATION_TASKS if task.id == "routed-triage-record")
    assert plan_application_task(task, registry) is None


def test_compute_application_grade_is_pure() -> None:
    records = [
        {
            "id": task.id,
            "ok": True,
            "plan": ["a", "b"],
            "minimality": [{"removed": "a", "broke_outcome": True}, {"removed": "b", "broke_outcome": True}],
            "reversed_broke": True,
        }
        for task in APPLICATION_TASKS
    ]
    graded = compute_application_grade(records)
    assert graded["application_score"] == 1.0
    assert compute_application_grade(records) == graded

    # A plan member that does not break the outcome strips plan attribution.
    records[0]["minimality"][0]["broke_outcome"] = False
    degraded = compute_application_grade(records)
    assert degraded["application_score"] < 1.0
    assert records[0]["id"] not in degraded["plan_attributed"]


def test_run_application_plane_is_deterministic() -> None:
    first = run_application_plane()
    second = run_application_plane()
    assert first["plans_digest"] == second["plans_digest"]
    assert first["outcomes_digest"] == second["outcomes_digest"]
    assert first["ok"] is True


def test_sealed_report_verifies_and_tamper_fails(tmp_path: Path) -> None:
    report = run_application_plane()
    out = tmp_path / "report"
    summary = write_application_report(report, out)
    assert summary["ok"] is True
    verified = verify_application_report(out)
    assert verified["ok"] is True, verified

    tampered = json.loads((out / "report.json").read_text(encoding="utf-8"))
    tampered["task_records"][0]["ok"] = not tampered["task_records"][0]["ok"]
    (out / "report.json").write_text(json.dumps(tampered), encoding="utf-8")
    assert verify_application_report(out)["ok"] is False


def test_plan_naming_unproved_capability_fails_verification(tmp_path: Path) -> None:
    import hashlib

    from blackhole_agent.capability_application import _digest

    report = run_application_plane()
    forged = json.loads(json.dumps(report))
    forged["task_records"][0]["plan"] = ["capability.no-such-capability"]
    forged["task_records"][0]["plan_sound"] = True
    forged["plans_digest"] = _digest(
        [{"id": record["id"], "plan": record["plan"]} for record in forged["task_records"]]
    )
    forged["grade_digest"] = _digest(forged["application"])
    forged["report_digest"] = hashlib.sha256(
        f"application:{forged['plans_digest']}:{forged['outcomes_digest']}:{forged['grade_digest']}".encode(
            "utf-8"
        )
    ).hexdigest()
    out = tmp_path / "report"
    out.mkdir()
    (out / "report.json").write_text(json.dumps(forged), encoding="utf-8")
    result = verify_application_report(out)
    assert result["ok"] is False
    assert result["checks"]["plans_sound_against_live_ledger"] is False


def test_builtin_application_plane_proof() -> None:
    result = builtin_application_plane()
    assert result["ok"] is True, result
    assert result["application"]["application_score"] == 1.0
    assert result["planner_honesty"] is True
    assert result["deterministic"] is True
    assert result["used_skill_route_discovery"] is False


def test_execute_application_plan_threads_state() -> None:
    registry = _live_registry()
    task = next(task for task in APPLICATION_TASKS if task.id == "scan-gated-activation")
    state = execute_application_plan(task, ["domain.ci-security", "domain.harness-activation"], registry)
    assert state["scan_gate"]["allowed"] is True
    assert state["activation"]["allowed"] is True


def test_unbound_cli_goals_lists_solvability() -> None:
    import json as _json

    from typer.testing import CliRunner

    from blackhole_agent.unbound import app

    result = CliRunner().invoke(app, ["capability", "goals"])
    assert result.exit_code == 0, result.output
    data = _json.loads(result.output)
    assert data["solvable_count"] == len(APPLICATION_TASKS)
    ids = {goal["id"] for goal in data["goals"]}
    assert "persona-stamped-proposal" in ids


def test_unbound_cli_apply_solves_declared_goal() -> None:
    import json as _json

    from typer.testing import CliRunner

    from blackhole_agent.unbound import app

    result = CliRunner().invoke(app, ["capability", "apply", "persona-stamped-proposal"])
    assert result.exit_code == 0, result.output
    data = _json.loads(result.output)
    assert data["ok"] is True
    assert data["plan"] == ["domain.persona", "domain.proposal-synthesis"]
    assert data["outcome"]["proposal_package"]["persona_version"] == "2026-06-14.hermes-inspired"

    unknown = CliRunner().invoke(app, ["capability", "apply", "no-such-goal"])
    assert unknown.exit_code != 0
