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


def test_compute_sweep_fitness_grades_purely() -> None:
    from blackhole_agent.capability_benchmark import compute_sweep_fitness

    outcomes = [
        {"id": "cap.b", "ok": True},
        {"id": "cap.a", "ok": False},
        {"id": "cap.c", "ok": True},
    ]
    graded = compute_sweep_fitness(outcomes)
    assert graded["capability_fitness"] == {"cap.a": 0.0, "cap.b": 1.0, "cap.c": 1.0}
    assert graded["weakest_capabilities"] == ["cap.a"]
    assert graded["entry_pass_count"] == 2
    assert graded["entry_count"] == 3
    assert graded["suite_score"] < 1.0
    assert compute_sweep_fitness(outcomes) == graded


def test_sealed_sweep_report_verifies(tmp_path: Path) -> None:
    from blackhole_agent.capability_benchmark import (
        run_ledger_sweep,
        verify_sweep_report,
        write_sweep_report,
    )

    report = run_ledger_sweep(capability_ids=["repo.import-health", "capability.ledger-inventory"])
    assert report["coverage"] > 0
    assert report["ledger_size"] >= 2
    write_sweep_report(report, tmp_path)
    verified = verify_sweep_report(tmp_path)
    assert verified["ok"] is True
    assert all(verified["checks"].values())


def test_tampered_sweep_outcome_fails_verification(tmp_path: Path) -> None:
    from blackhole_agent.capability_benchmark import (
        run_ledger_sweep,
        verify_sweep_report,
        write_sweep_report,
    )

    report = run_ledger_sweep(capability_ids=["repo.import-health"])
    write_sweep_report(report, tmp_path)
    tampered = json.loads((tmp_path / "sweep-report.json").read_text(encoding="utf-8"))
    tampered["sweep_outcomes"][0]["ok"] = not tampered["sweep_outcomes"][0]["ok"]
    (tmp_path / "sweep-report.json").write_text(json.dumps(tampered, indent=2), encoding="utf-8")
    assert verify_sweep_report(tmp_path)["ok"] is False


def test_misgraded_sweep_fitness_fails_verification(tmp_path: Path) -> None:
    from blackhole_agent.capability_benchmark import (
        run_ledger_sweep,
        verify_sweep_report,
        write_sweep_report,
    )

    report = run_ledger_sweep(capability_ids=["repo.import-health"])
    write_sweep_report(report, tmp_path)
    misgraded = json.loads((tmp_path / "sweep-report.json").read_text(encoding="utf-8"))
    sample_id = sorted(misgraded["fitness"]["capability_fitness"])[0]
    misgraded["fitness"]["capability_fitness"][sample_id] = 0.0
    (tmp_path / "sweep-report.json").write_text(json.dumps(misgraded, indent=2), encoding="utf-8")
    assert verify_sweep_report(tmp_path)["ok"] is False


def test_missing_sweep_report_fails_closed(tmp_path: Path) -> None:
    from blackhole_agent.capability_benchmark import verify_sweep_report

    assert verify_sweep_report(tmp_path)["ok"] is False


def test_fitness_map_merges_sweep_with_strictest_wins(tmp_path: Path) -> None:
    from blackhole_agent.capability_benchmark import (
        DEFAULT_ARTIFACT_DIR,
        compute_sweep_fitness,
        load_latest_fitness_map,
    )
    from blackhole_agent.capability_compounder import atomic_write_json

    import hashlib

    def seal(outcomes: list[dict], fitness: dict) -> dict:
        canonical = lambda payload: json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)  # noqa: E731
        outcomes_digest = hashlib.sha256(
            canonical([{"id": item["id"], "ok": item["ok"]} for item in outcomes]).encode()
        ).hexdigest()
        fitness_digest = hashlib.sha256(canonical(fitness).encode()).hexdigest()
        report_digest = hashlib.sha256(f"sweep:{outcomes_digest}:{fitness_digest}".encode()).hexdigest()
        return {
            "sweep_outcomes": outcomes,
            "fitness": fitness,
            "outcomes_digest": outcomes_digest,
            "fitness_digest": fitness_digest,
            "report_digest": report_digest,
        }

    artifact_root = tmp_path / DEFAULT_ARTIFACT_DIR
    sweep_dir = artifact_root / "sweep-run"
    sweep_dir.mkdir(parents=True)
    outcomes = [
        {"id": "repo.import-health", "ok": True},
        {"id": "cap.only-in-sweep", "ok": False},
    ]
    fitness = compute_sweep_fitness(outcomes)
    atomic_write_json(sweep_dir / "sweep-report.json", seal(outcomes, fitness))
    atomic_write_json(
        artifact_root / "latest-sweep.json",
        {"report_dir": "sweep-run", "report_digest": seal(outcomes, fitness)["report_digest"]},
    )

    merged = load_latest_fitness_map(tmp_path)
    assert merged is not None
    # Sweep-only capability becomes measured; weakness survives the merge.
    assert merged["cap.only-in-sweep"] == 0.0
    assert "repo.import-health" in merged


def test_sweep_failing_entry_recorded_not_raised() -> None:
    from blackhole_agent.capability_benchmark import compute_sweep_fitness

    # A timeout/crash-shaped outcome grades as weak without crashing the sweep.
    outcomes = [{"id": "cap.slow", "ok": False, "error": "TimeoutExpired: ..."}]
    graded = compute_sweep_fitness(outcomes)
    assert graded["weakest_capabilities"] == ["cap.slow"]


def test_growth_loop_fitness_gate_halts_on_measured_weakness(tmp_path: Path, monkeypatch) -> None:
    from blackhole_agent import capability_benchmark
    from blackhole_agent.capability_compounder import ensure_seeded_ledger, run_growth_loop

    ensure_seeded_ledger(tmp_path)
    monkeypatch.setattr(
        capability_benchmark,
        "load_latest_fitness_map",
        lambda root: {"repo.import-health": 0.0},
    )
    result = run_growth_loop(tmp_path, timeout=180)
    assert result["action"] == "fitness_gate"
    assert result["grew"] is False
    assert result["after_count"] == result["before_count"]
    assert result["target"] == "repo.import-health"
    assert result["weakest_capabilities"] == ["repo.import-health"]
    # The live entry actually passes, so the gate flags a stale sealed map
    # instead of a genuine repair need — growth stays halted until re-sealed.
    assert result["ok"] is True
    assert result["reason"] == "fitness_recheck_passed"
    assert result["used_skill_route_discovery"] is False


def test_growth_loop_ungated_without_fitness_signal(tmp_path: Path, monkeypatch) -> None:
    from blackhole_agent import capability_benchmark
    from blackhole_agent.capability_compounder import ensure_seeded_ledger, run_growth_loop

    ensure_seeded_ledger(tmp_path)
    monkeypatch.setattr(capability_benchmark, "load_latest_fitness_map", lambda root: None)
    result = run_growth_loop(tmp_path, timeout=180)
    assert result.get("action") != "fitness_gate"
    assert result["used_skill_route_discovery"] is False
