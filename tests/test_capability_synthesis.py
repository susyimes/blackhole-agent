"""Tests for the capability synthesis plane."""

from __future__ import annotations

import json
from pathlib import Path

from blackhole_agent.capability_application import (
    ApplicationTask,
    build_application_registry,
    plan_application_task,
)
from blackhole_agent.capability_compounder import (
    atomic_write_json,
    default_ledger_path,
    load_ledger,
)
from blackhole_agent.capability_synthesis import (
    REPO_ROOT,
    SYNTHESIS_TASKS,
    Candidate,
    builtin_synthesis_plane,
    build_memorization_decoy,
    candidate_matches,
    compute_synthesis_grade,
    demo_synthesized_steps,
    enumerate_candidates,
    evaluate_candidate,
    load_persisted_records,
    load_persisted_synthesized_steps,
    persist_synthesized_steps,
    prove_synthesized_step,
    run_synthesis_plane,
    synthesize_candidate,
    synthesized_step,
    tamper_candidate,
    verify_synthesis_report,
    write_synthesis_report,
    _goal_task,
)


def _base_registry():
    ledger = load_ledger(default_ledger_path(REPO_ROOT))
    return build_application_registry(ledger)


def test_tasks_declare_goals_without_behavior() -> None:
    # The whole point of the plane: tasks name goal keys and frozen cases,
    # never a transform, a step sequence, or a capability.
    for task in SYNTHESIS_TASKS:
        assert task.goal_key, task.id
        assert len(task.cases) >= 3, task.id
        assert not hasattr(task, "transform")
        assert not hasattr(task, "steps")
        for case in task.cases:
            assert task.goal_key in case["expect"], task.id
            assert task.goal_key not in case["state"], task.id


def test_goal_keys_are_novel_across_the_base_registry() -> None:
    registry = _base_registry()
    provided = {key for step in registry.values() for key in step.provides}
    for task in SYNTHESIS_TASKS:
        assert task.goal_key not in provided, task.id


def test_every_task_is_honestly_unplannable_before_synthesis() -> None:
    registry = _base_registry()
    for task in SYNTHESIS_TASKS:
        assert plan_application_task(_goal_task(task), registry) is None, task.id


def test_synthesizer_derives_the_intended_hypotheses() -> None:
    winners = {task.id: synthesize_candidate(task) for task in SYNTHESIS_TASKS}
    for task in SYNTHESIS_TASKS:
        assert winners[task.id]["found"], task.id
    record_key = winners["triage-record-key"]["candidate"]
    assert record_key.transform == "affix"
    assert record_key.prefix == "triage-record:"
    assert tuple(record_key.extractor1) == ("field", "triage", "lane")
    verdict = winners["scan-verdict-label"]["candidate"]
    assert verdict.transform == "upper"
    tag = winners["triage-label-count-tag"]["candidate"]
    assert tag.transform == "join"
    assert tuple(tag.extractor2) == ("length", "issue", "labels")


def test_selection_is_deterministic() -> None:
    for task in SYNTHESIS_TASKS:
        first = synthesize_candidate(task)
        second = synthesize_candidate(task)
        assert first["candidate"] == second["candidate"], task.id
        assert first["candidates_tried"] == second["candidates_tried"], task.id


def test_memorization_decoy_fails_the_held_out_split() -> None:
    for task in SYNTHESIS_TASKS:
        decoy = build_memorization_decoy(task)
        held_out_key = json.dumps(task.cases[-1]["state"], sort_keys=True, separators=(",", ":"))
        assert held_out_key not in decoy, task.id
        # ...while it does fit every selection case, so a seen-only grader
        # would have accepted the cheat.
        for case in task.cases[:-1]:
            key = json.dumps(case["state"], sort_keys=True, separators=(",", ":"))
            assert decoy[key] == str(case["expect"][task.goal_key])


def test_tampered_winner_fails_case_validation() -> None:
    for task in SYNTHESIS_TASKS:
        winner = synthesize_candidate(task)["candidate"]
        assert candidate_matches(winner, task.cases, task.goal_key), task.id
        assert not candidate_matches(tamper_candidate(winner), task.cases, task.goal_key), task.id


def test_synthesized_step_makes_goal_plannable_and_ablation_breaks_it() -> None:
    registry = _base_registry()
    for task in SYNTHESIS_TASKS:
        winner = synthesize_candidate(task)["candidate"]
        step = synthesized_step(task, winner)
        grown = {**registry, step.capability_id: step}
        goal_task = _goal_task(task)
        plan = plan_application_task(goal_task, grown)
        assert plan == [step.capability_id], task.id
        assert plan_application_task(goal_task, registry) is None, task.id


def test_crashing_candidates_never_match() -> None:
    task = SYNTHESIS_TASKS[0]
    broken = Candidate(transform="identity", extractor1=("field", "triage", "no-such-field"))
    assert not candidate_matches(broken, task.cases, task.goal_key)


def test_evaluate_candidate_rejects_unknown_transform() -> None:
    candidate = Candidate(transform="no-such-transform", extractor1=("key", "triage"))
    try:
        evaluate_candidate(candidate, {"triage": {}})
    except ValueError:
        return
    raise AssertionError("unknown transform must raise")


def test_run_synthesis_plane_attributes_every_task() -> None:
    report = run_synthesis_plane()
    assert report["ok"] is True
    assert report["synthesis"]["synthesis_score"] == 1.0
    assert report["synthesis"]["synthesis_attributed"] == [task.id for task in SYNTHESIS_TASKS]
    assert report["used_skill_route_discovery"] is False
    for record in report["task_records"]:
        assert record["honestly_unsolvable_before"] is True
        assert record["ablation_unsolvable"] is True
        assert record["tamper_rejected"] is True
        assert record["decoy_rejected"] is True


def test_grade_is_pure_over_recorded_verdicts() -> None:
    report = run_synthesis_plane()
    regraded = compute_synthesis_grade(report["task_records"])
    assert regraded == report["synthesis"]
    broken = json.loads(json.dumps(report["task_records"]))
    broken[0]["decoy_rejected"] = False
    assert compute_synthesis_grade(broken)["synthesis_score"] < 1.0


def test_sealed_report_verifies_and_tamper_fails(tmp_path: Path) -> None:
    report = run_synthesis_plane()
    out = tmp_path / "report"
    write_synthesis_report(report, out)
    verified = verify_synthesis_report(out)
    assert verified["ok"] is True, verified["checks"]

    tampered = json.loads((out / "report.json").read_text(encoding="utf-8"))
    tampered["task_records"][1]["outcome_matched"] = False
    atomic_write_json(out / "report.json", tampered)
    assert verify_synthesis_report(out)["ok"] is False


def test_forged_winner_fails_winner_soundness(tmp_path: Path) -> None:
    report = run_synthesis_plane()
    out = tmp_path / "report"
    write_synthesis_report(report, out)
    forged = json.loads((out / "report.json").read_text(encoding="utf-8"))
    forged["task_records"][0]["winner"]["prefix"] = "forged-prefix:"
    atomic_write_json(out / "report.json", forged)
    result = verify_synthesis_report(out)
    assert result["ok"] is False
    assert result["checks"]["winners_sound_against_cases"] is False


def test_builtin_proof_passes_all_falsification_stages() -> None:
    result = builtin_synthesis_plane()
    assert result["ok"] is True, result
    assert result["deterministic"] is True
    assert result["tamper_detected"] is True
    assert result["forged_winner_detected"] is True
    assert result["misgrade_detected"] is True
    assert result["synthesis"]["synthesis_score"] == 1.0
    assert result["used_skill_route_discovery"] is False


def test_candidate_space_is_bounded_and_structured() -> None:
    for task in SYNTHESIS_TASKS:
        candidates = enumerate_candidates(task)
        assert candidates, task.id
        assert len(candidates) < 5000, task.id
        # Canonical order is stable: enumeration is a pure function.
        assert candidates == enumerate_candidates(task), task.id


# ---------------------------------------------------------------------------
# Durable persistence: winners as first-class proved ledger capabilities.
# ---------------------------------------------------------------------------


def test_persist_registers_first_class_capabilities(tmp_path: Path) -> None:
    (tmp_path / "capabilities").mkdir()
    ledger_source = default_ledger_path(REPO_ROOT)
    (tmp_path / "capabilities" / "ledger.json").write_text(
        ledger_source.read_text(encoding="utf-8"), encoding="utf-8"
    )
    result = persist_synthesized_steps(tmp_path)
    assert result["ok"] is True
    assert result["wrote_steps_file"] is True
    assert len(result["registered"]) == len(SYNTHESIS_TASKS)

    steps_file = tmp_path / "capabilities" / "synthesized-steps.json"
    payload = json.loads(steps_file.read_text(encoding="utf-8"))
    assert payload["steps_digest"]
    assert {record["task_id"] for record in payload["steps"]} == {task.id for task in SYNTHESIS_TASKS}

    from blackhole_agent.capability_compounder import load_ledger

    ledger = load_ledger(tmp_path / "capabilities" / "ledger.json")
    for record in payload["steps"]:
        capability = ledger.capabilities[record["capability_id"]]
        assert capability.kind == "python"
        assert capability.proof_command
        assert "capability.synthesis-plane" in capability.dependencies
        # Not tagged "synthesized": that tag marks combinatorial stack growth.
        assert "synthesized" not in capability.tags

    # Idempotent: unchanged derived records produce no file churn.
    again = persist_synthesized_steps(tmp_path)
    assert again["ok"] is True
    assert again["wrote_steps_file"] is False


def test_persisted_records_load_as_invocable_steps(tmp_path: Path) -> None:
    records = load_persisted_records()
    assert len(records) >= 3
    steps = load_persisted_synthesized_steps()
    for record in records:
        step = steps[record["capability_id"]]
        state = record["cases"][-1]["state"]
        output = step.invoke(state)
        assert output[record["goal_key"]] == record["cases"][-1]["expect"][record["goal_key"]]


def test_prove_synthesized_step_passes_for_each_persisted_task() -> None:
    for task in SYNTHESIS_TASKS:
        result = prove_synthesized_step(task.id)
        assert result["ok"] is True, (task.id, result)
        assert result["winner_matches_search"] is True
        assert result["honestly_unplannable_without"] is True
        assert result["grown_plan_matched"] is True


def test_prove_synthesized_step_rejects_unknown_task() -> None:
    assert prove_synthesized_step("no-such-task")["ok"] is False


def test_demo_synthesized_steps_matches_held_out_expectations() -> None:
    result = demo_synthesized_steps()
    assert result["ok"] is True
    assert result["step_count"] >= 3
    assert all(outcome["matched"] for outcome in result["outcomes"].values())


def test_grown_registry_plans_synthesized_goals() -> None:
    ledger = load_ledger(default_ledger_path(REPO_ROOT))
    grown = build_application_registry(ledger, include_synthesized=True)
    base = build_application_registry(ledger, include_synthesized=False)
    for record in load_persisted_records():
        capability_id = record["capability_id"]
        capability = ledger.capabilities.get(capability_id)
        assert capability is not None and capability.last_proof_exit_code == 0, capability_id
        assert capability_id in grown and capability_id not in base
        goal_task = ApplicationTask(
            id=record["task_id"],
            description="",
            initial_state=record["cases"][-1]["state"],
            goal=(record["goal_key"],),
            oracle={},
        )
        plan = plan_application_task(goal_task, grown)
        assert plan is not None and capability_id in plan, record["task_id"]
        assert plan_application_task(goal_task, base) is None, record["task_id"]
