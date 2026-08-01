"""Tests for the capability fitness benchmark suite."""

from __future__ import annotations

import json
from pathlib import Path

from blackhole_agent.capability_benchmark import (
    BENCHMARK_TASKS,
    TASK_RUNNERS,
    builtin_fitness_benchmark_proof,
    compute_fitness,
    run_fitness_benchmark,
    verify_fitness_report,
    write_benchmark_report,
)


def test_task_specs_cover_runners() -> None:
    assert {task.id for task in BENCHMARK_TASKS} == set(TASK_RUNNERS)
    for task in BENCHMARK_TASKS:
        assert task.exercises, task.id


def test_compute_fitness_grades_purely() -> None:
    outcomes = [
        {"id": task.id, "ok": task.id != "local-memory-roundtrip"}
        for task in BENCHMARK_TASKS
    ]
    graded = compute_fitness(outcomes)
    assert graded["capability_fitness"]["domain.local-memory"] == 0.0
    assert graded["capability_fitness"]["repo.import-health"] == 1.0
    assert "domain.local-memory" in graded["weakest_capabilities"]
    assert graded["suite_score"] < 1.0
    # Pure: same input reproduces the same grading.
    assert compute_fitness(outcomes) == graded


def test_run_fitness_benchmark_is_deterministic() -> None:
    first = run_fitness_benchmark()
    second = run_fitness_benchmark()
    assert first["outcomes_digest"] == second["outcomes_digest"]
    assert first["fitness"] == second["fitness"]
    assert first["ok"] is True


def test_sealed_report_verifies(tmp_path: Path) -> None:
    report = run_fitness_benchmark()
    write_benchmark_report(report, tmp_path)
    verified = verify_fitness_report(tmp_path)
    assert verified["ok"] is True
    assert all(verified["checks"].values())


def test_tampered_outcome_fails_verification(tmp_path: Path) -> None:
    report = run_fitness_benchmark()
    write_benchmark_report(report, tmp_path)
    tampered = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    tampered["task_outcomes"][0]["ok"] = not tampered["task_outcomes"][0]["ok"]
    (tmp_path / "report.json").write_text(json.dumps(tampered, indent=2), encoding="utf-8")
    assert verify_fitness_report(tmp_path)["ok"] is False


def test_misgraded_fitness_fails_verification(tmp_path: Path) -> None:
    report = run_fitness_benchmark()
    write_benchmark_report(report, tmp_path)
    misgraded = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    sample_id = sorted(misgraded["fitness"]["capability_fitness"])[0]
    misgraded["fitness"]["capability_fitness"][sample_id] = 0.0
    (tmp_path / "report.json").write_text(json.dumps(misgraded, indent=2), encoding="utf-8")
    assert verify_fitness_report(tmp_path)["ok"] is False


def test_missing_report_fails_closed(tmp_path: Path) -> None:
    assert verify_fitness_report(tmp_path)["ok"] is False


def test_builtin_fitness_benchmark_proof() -> None:
    result = builtin_fitness_benchmark_proof()
    assert result["ok"] is True
    assert result["deterministic"] is True
    assert result["tamper_detected"] is True
    assert result["misgrade_detected"] is True
    assert result["suite_score"] == 1.0
