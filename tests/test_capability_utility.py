"""Tests for the capability utility plane."""

from __future__ import annotations

import json
from pathlib import Path

from blackhole_agent.capability_utility import (
    STEP_REGISTRY,
    UTILITY_TASKS,
    builtin_utility_plane,
    compute_utility_grade,
    run_utility_plane,
    run_utility_task,
    verify_utility_report,
    write_utility_report,
)


def test_task_specs_cover_registry_steps() -> None:
    for task in UTILITY_TASKS:
        assert len(task.steps) >= 2, task.id
        for capability_id in task.steps:
            assert capability_id in STEP_REGISTRY, (task.id, capability_id)
        assert task.oracle, task.id


def test_each_task_matches_oracle_and_ablations_break() -> None:
    for task in UTILITY_TASKS:
        result = run_utility_task(task)
        assert result["ok"] is True, (task.id, result["error"], result["outcome"])
        for capability_id in task.steps:
            ablated = run_utility_task(task, disabled=capability_id)
            assert ablated["ok"] is False, (task.id, capability_id)


def test_compute_utility_grade_is_pure() -> None:
    task_outcomes = [{"id": task.id, "ok": True} for task in UTILITY_TASKS]
    ablation_outcomes = [
        {"task_id": task.id, "capability_id": capability_id, "broke_outcome": True}
        for task in UTILITY_TASKS
        for capability_id in task.steps
    ]
    graded = compute_utility_grade(task_outcomes, ablation_outcomes)
    assert graded["utility_score"] == 1.0
    assert len(graded["causally_attributed"]) == len(UTILITY_TASKS)
    assert compute_utility_grade(task_outcomes, ablation_outcomes) == graded

    # An ablation that does not break the outcome strips causal attribution.
    ablation_outcomes[0]["broke_outcome"] = False
    degraded = compute_utility_grade(task_outcomes, ablation_outcomes)
    assert degraded["utility_score"] < 1.0
    assert UTILITY_TASKS[0].id not in degraded["causally_attributed"]


def test_run_utility_plane_is_deterministic() -> None:
    first = run_utility_plane()
    second = run_utility_plane()
    assert first["outcomes_digest"] == second["outcomes_digest"]
    assert first["ablations_digest"] == second["ablations_digest"]
    assert first["utility"] == second["utility"]
    assert first["ok"] is True
    assert first["used_skill_route_discovery"] is False


def test_sealed_report_verifies(tmp_path: Path) -> None:
    report = run_utility_plane()
    write_utility_report(report, tmp_path)
    verified = verify_utility_report(tmp_path)
    assert verified["ok"] is True
    assert all(verified["checks"].values())


def test_tampered_outcome_fails_verification(tmp_path: Path) -> None:
    report = run_utility_plane()
    write_utility_report(report, tmp_path)
    tampered = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    tampered["task_outcomes"][0]["ok"] = not tampered["task_outcomes"][0]["ok"]
    (tmp_path / "report.json").write_text(json.dumps(tampered, indent=2), encoding="utf-8")
    assert verify_utility_report(tmp_path)["ok"] is False


def test_fabricated_ablation_fails_verification(tmp_path: Path) -> None:
    report = run_utility_plane()
    write_utility_report(report, tmp_path)
    fabricated = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    fabricated["ablation_outcomes"][0]["broke_outcome"] = not fabricated["ablation_outcomes"][0][
        "broke_outcome"
    ]
    (tmp_path / "report.json").write_text(json.dumps(fabricated, indent=2), encoding="utf-8")
    assert verify_utility_report(tmp_path)["ok"] is False


def test_misgraded_utility_fails_verification(tmp_path: Path) -> None:
    report = run_utility_plane()
    write_utility_report(report, tmp_path)
    misgraded = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    misgraded["utility"]["utility_score"] = 0.0
    (tmp_path / "report.json").write_text(json.dumps(misgraded, indent=2), encoding="utf-8")
    assert verify_utility_report(tmp_path)["ok"] is False


def test_missing_report_fails_closed(tmp_path: Path) -> None:
    assert verify_utility_report(tmp_path)["ok"] is False


def test_builtin_utility_plane_proof() -> None:
    result = builtin_utility_plane()
    assert result["ok"] is True
    assert result["deterministic"] is True
    assert result["tamper_detected"] is True
    assert result["ablation_fabrication_detected"] is True
    assert result["misgrade_detected"] is True
    assert result["utility"]["utility_score"] == 1.0
    assert result["used_skill_route_discovery"] is False


def test_utility_plane_registered_and_proved() -> None:
    from blackhole_agent.capability_compounder import (
        default_ledger_path,
        load_ledger,
    )

    ledger = load_ledger(default_ledger_path(Path(__file__).resolve().parents[1]))
    capability = ledger.capabilities.get("capability.utility-plane")
    assert capability is not None
    assert capability.entry == "blackhole_agent.capability_utility:builtin_utility_plane"
    assert capability.last_proof_exit_code == 0
    for dependency in capability.dependencies:
        assert dependency in ledger.capabilities
