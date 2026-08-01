"""Tests for the capability fitness benchmark suite."""

from __future__ import annotations

import json
from pathlib import Path

from blackhole_agent.capability_benchmark import (
    BENCHMARK_TASKS,
    TASK_RUNNERS,
    builtin_fitness_benchmark_proof,
    builtin_fitness_scout_ablation,
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


def test_fitness_annotation_targets_weak_and_unmeasured() -> None:
    from blackhole_agent.capability_compounder import (
        FITNESS_UNMEASURED_WEIGHT,
        FITNESS_WEAK_WEIGHT,
        annotate_opportunities_with_fitness,
    )

    opportunities = [
        {"suggested_id": "a", "coverage": ["fit.one", "weak.one"]},
        {"suggested_id": "b", "coverage": ["fit.one", "fit.two"]},
        {"suggested_id": "c", "status": "ready_to_absorb", "coverage": ["unknown.one"]},
        {"suggested_id": "d", "status": "ready", "coverage": ["fit.one", "unknown.one"]},
    ]
    fitness_map = {"fit.one": 1.0, "fit.two": 1.0, "weak.one": 0.5}
    annotate_opportunities_with_fitness(opportunities, fitness_map)
    first, second, third, fourth = opportunities
    assert first["fitness_bonus"] == int(round(0.5 * FITNESS_WEAK_WEIGHT))
    assert first["fitness_weak_members"] == ["weak.one"]
    assert first["fitness_unmeasured_members"] == []
    assert second["fitness_bonus"] == 0
    assert second["fitness_weak_members"] == []
    # Absorbing an unmeasured surface expands measurement: uncertainty weight.
    assert third["fitness_bonus"] == FITNESS_UNMEASURED_WEIGHT
    assert third["fitness_unmeasured_members"] == ["unknown.one"]
    # Compositions earn no uncertainty weight for already-ledgered gaps.
    assert fourth["fitness_bonus"] == 0
    assert fourth["fitness_unmeasured_members"] == []


def test_fitness_map_changes_frontier_ranking() -> None:
    from blackhole_agent.capability_compounder import rank_growth_opportunities

    base = {"status": "ready", "novel": True, "novelty_score": 500, "priority": 0}
    fit_only = {**base, "suggested_id": "fit-only", "coverage": ["m.one"]}
    weak_target = {**base, "suggested_id": "weak-target", "coverage": ["m.two"]}
    # Novelty-only: stable id order decides the tie.
    novelty_ranked = rank_growth_opportunities([dict(weak_target), dict(fit_only)])
    assert [item["suggested_id"] for item in novelty_ranked] == ["fit-only", "weak-target"]
    # Fitness-aware: the frontier covering a weak capability wins the same tier.
    fitness_ranked = rank_growth_opportunities(
        [dict(weak_target), dict(fit_only)],
        fitness_map={"m.one": 1.0, "m.two": 0.0},
    )
    assert [item["suggested_id"] for item in fitness_ranked] == ["weak-target", "fit-only"]


def test_scout_fitness_auto_load_and_explicit_disable() -> None:
    from pathlib import Path

    from blackhole_agent.capability_compounder import (
        default_ledger_path,
        load_ledger,
        scout_capability_gaps,
    )

    repo = Path(__file__).resolve().parents[1]
    ledger = load_ledger(default_ledger_path(repo))
    auto = scout_capability_gaps(ledger, repo_path=repo)
    disabled = scout_capability_gaps(ledger, repo_path=repo, fitness_map=None)
    assert auto["fitness_aware"] is True
    assert auto["fitness_measured_count"] >= 1
    assert disabled["fitness_aware"] is False
    ready = lambda scout: [  # noqa: E731
        item["suggested_id"]
        for item in scout["opportunities"]
        if item["status"] in {"ready", "ready_to_absorb"}
    ]
    # Uniform live fitness (nothing weak) must coincide with novelty-only;
    # signal sensitivity is covered by the ablation proof test below.
    assert ready(auto) == ready(disabled)


def test_builtin_fitness_scout_ablation() -> None:
    result = builtin_fitness_scout_ablation()
    assert result["ok"] is True
    assert result["coincide"] is True
    assert result["sensitivity"] is True
    assert result["causation"] is True
    assert result["weakest_targeting"]["lifted"] > 0
    assert result["used_skill_route_discovery"] is False
