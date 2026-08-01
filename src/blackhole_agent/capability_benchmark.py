"""Capability fitness benchmark: a deterministic task suite that scores real ledger abilities.

The compounder grew the ledger past 90 capabilities, but proof status is
binary and self-referential: a capability is "proved" by its own proof
command. Nothing measures how well the ledger's abilities perform as one
working system. This module is the missing fitness function for the
evolution loop:

- a fixed suite of hermetic tasks, each exercising one or more real ledger
  capabilities through its live entry point (no network, no kernels);
- per-capability fitness = fraction of exercising tasks that pass, so weak
  primitives become measurable and rankable instead of invisible;
- a digest-sealed report artifact under ``artifacts/capability-benchmark/``
  whose fitness numbers are a pure function of the recorded task outcomes,
  so tampering or misgrading fails verification.

Determinism contract: task *outcomes* (``ok`` booleans) must be reproducible
across runs on the same checkout. Durations and timestamps are recorded for
diagnostics but excluded from every digest; ``verify_fitness_report``
recomputes fitness and digests from recorded outcomes only, and the
registered proof additionally re-runs the whole suite to prove the outcome
digest is stable across executions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from blackhole_agent.capability_compounder import atomic_write_json, utc_now_iso

SCHEMA_VERSION = 1

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT_DIR = "artifacts/capability-benchmark"
LATEST_POINTER = REPO_ROOT / DEFAULT_ARTIFACT_DIR / "latest-benchmark.json"


@dataclass(frozen=True)
class BenchmarkTask:
    """One hermetic fitness task over real ledger capabilities."""

    id: str
    description: str
    exercises: tuple[str, ...]


def _task_import_health() -> dict[str, Any]:
    from blackhole_agent.capability_compounder import builtin_repo_import_health

    result = builtin_repo_import_health()
    result["ok"] = bool(result.get("ok")) and not result.get("imports_skill_routing")
    return result


def _task_milestone_gate() -> dict[str, Any]:
    from blackhole_agent.capability_compounder import builtin_milestone_gate_smoke

    return builtin_milestone_gate_smoke()


def _task_ledger_inventory() -> dict[str, Any]:
    from blackhole_agent.capability_compounder import builtin_ledger_inventory

    result = builtin_ledger_inventory()
    result["ok"] = bool(result.get("ok")) and int(result.get("count") or 0) >= 2
    return result


def _task_local_memory() -> dict[str, Any]:
    from blackhole_agent.capability_compounder import builtin_local_memory_roundtrip

    return builtin_local_memory_roundtrip()


def _task_tool_routing() -> dict[str, Any]:
    from blackhole_agent.capability_compounder import builtin_tool_routing_preflight

    return builtin_tool_routing_preflight()


def _task_issue_triage() -> dict[str, Any]:
    from blackhole_agent.capability_compounder import builtin_issue_triage_smoke

    return builtin_issue_triage_smoke()


def _task_ci_security() -> dict[str, Any]:
    from blackhole_agent.capability_compounder import builtin_ci_security_gate

    return builtin_ci_security_gate()


def _task_proposal_eval() -> dict[str, Any]:
    from blackhole_agent.capability_compounder import builtin_proposal_eval_smoke

    return builtin_proposal_eval_smoke()


def _task_grounded_scan() -> dict[str, Any]:
    from blackhole_agent.grounded_growth import builtin_grounded_scan_proof

    return builtin_grounded_scan_proof()


def _task_evolution_redirect() -> dict[str, Any]:
    from blackhole_agent.capability_compounder import builtin_evolution_route_redirect

    return builtin_evolution_route_redirect()


TASK_RUNNERS: dict[str, Callable[[], dict[str, Any]]] = {
    "repo-import-health": _task_import_health,
    "milestone-gate": _task_milestone_gate,
    "ledger-inventory": _task_ledger_inventory,
    "local-memory-roundtrip": _task_local_memory,
    "tool-routing-preflight": _task_tool_routing,
    "issue-triage-smoke": _task_issue_triage,
    "ci-security-gate": _task_ci_security,
    "proposal-eval-smoke": _task_proposal_eval,
    "grounded-scan-replay": _task_grounded_scan,
    "evolution-redirect": _task_evolution_redirect,
}

BENCHMARK_TASKS: tuple[BenchmarkTask, ...] = (
    BenchmarkTask(
        id="repo-import-health",
        description="Package imports cleanly with no legacy skill-route machinery.",
        exercises=("repo.import-health",),
    ),
    BenchmarkTask(
        id="milestone-gate",
        description="Unbound milestone gate accepts behavior changes and rejects docs-only churn.",
        exercises=("unbound.milestone-gate",),
    ),
    BenchmarkTask(
        id="ledger-inventory",
        description="Durable capability ledger loads and inventories.",
        exercises=("capability.ledger-inventory", "repo.import-health"),
    ),
    BenchmarkTask(
        id="local-memory-roundtrip",
        description="Local memory write/read/delete with privacy rejection.",
        exercises=("domain.local-memory",),
    ),
    BenchmarkTask(
        id="tool-routing-preflight",
        description="Tool routing preflight and executable registry.",
        exercises=("domain.tool-routing",),
    ),
    BenchmarkTask(
        id="issue-triage-smoke",
        description="Issue triage scoring on deterministic fixtures.",
        exercises=("domain.issue-triage",),
    ),
    BenchmarkTask(
        id="ci-security-gate",
        description="CI and supply-chain security gate.",
        exercises=("domain.ci-security",),
    ),
    BenchmarkTask(
        id="proposal-eval-smoke",
        description="Proposal evaluation on deterministic fixtures.",
        exercises=("domain.proposal-eval",),
    ),
    BenchmarkTask(
        id="grounded-scan-replay",
        description="Grounded growth scan replays the committed fixture with tamper falsification.",
        exercises=("capability.grounded-scan",),
    ),
    BenchmarkTask(
        id="evolution-redirect",
        description="Evolution surface redirects to the compounder when the ledger is ready.",
        exercises=("evolution.compounder-redirect", "capability.ledger-inventory"),
    ),
)


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def compute_fitness(task_outcomes: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Pure fitness derivation from recorded task outcomes.

    Per-capability fitness is the mean pass rate over the tasks that exercise
    it. The suite score is the mean per-capability fitness. This function is
    the single grading rule: a report whose recorded fitness disagrees with
    its recorded outcomes is misgraded and fails verification.
    """

    outcomes_by_id = {str(item.get("id")): bool(item.get("ok")) for item in task_outcomes}
    per_capability: dict[str, dict[str, Any]] = {}
    for task in BENCHMARK_TASKS:
        if task.id not in outcomes_by_id:
            continue
        passed = outcomes_by_id[task.id]
        for capability_id in task.exercises:
            entry = per_capability.setdefault(capability_id, {"passed": 0, "total": 0, "tasks": []})
            entry["total"] += 1
            entry["passed"] += 1 if passed else 0
            entry["tasks"].append(task.id)

    fitness: dict[str, float] = {}
    for capability_id, entry in sorted(per_capability.items()):
        fitness[capability_id] = round(entry["passed"] / entry["total"], 4) if entry["total"] else 0.0
    suite_score = round(sum(fitness.values()) / len(fitness), 4) if fitness else 0.0
    weakest = [cid for cid, score in sorted(fitness.items(), key=lambda item: (item[1], item[0])) if score < 1.0]
    return {
        "capability_fitness": fitness,
        "suite_score": suite_score,
        "capabilities_measured": len(fitness),
        "weakest_capabilities": weakest,
        "task_pass_count": sum(1 for ok in outcomes_by_id.values() if ok),
        "task_count": len(outcomes_by_id),
    }


def run_fitness_benchmark() -> dict[str, Any]:
    """Run every benchmark task and grade the ledger's exercised abilities."""

    outcomes: list[dict[str, Any]] = []
    for task in BENCHMARK_TASKS:
        runner = TASK_RUNNERS[task.id]
        started = time.perf_counter()
        error = ""
        detail: dict[str, Any] = {}
        try:
            detail = runner()
            ok = bool(detail.get("ok"))
        except Exception as exc:  # noqa: BLE001 - a crashed task is a failed task, not a crashed suite
            ok = False
            error = f"{type(exc).__name__}: {exc}"
        duration_ms = round((time.perf_counter() - started) * 1000, 3)
        outcomes.append(
            {
                "id": task.id,
                "description": task.description,
                "exercises": list(task.exercises),
                "ok": ok,
                "duration_ms": duration_ms,
                "error": error,
            }
        )

    graded = compute_fitness(outcomes)
    outcomes_digest = _digest([{"id": item["id"], "ok": item["ok"]} for item in outcomes])
    fitness_digest = _digest(graded)
    report_digest = hashlib.sha256(f"{outcomes_digest}:{fitness_digest}".encode("utf-8")).hexdigest()
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "capability_fitness_benchmark",
        "run_at": utc_now_iso(),
        "task_outcomes": outcomes,
        "fitness": graded,
        "outcomes_digest": outcomes_digest,
        "fitness_digest": fitness_digest,
        "report_digest": report_digest,
        "ok": graded["task_pass_count"] == graded["task_count"] and graded["suite_score"] == 1.0,
    }


def write_benchmark_report(report: Mapping[str, Any], output_dir: Path) -> dict[str, Any]:
    """Seal the benchmark report artifact and refresh the latest pointer."""

    output_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(output_dir / "report.json", dict(report))
    if output_dir.parent == LATEST_POINTER.parent:
        atomic_write_json(
            LATEST_POINTER,
            {"report_dir": output_dir.name, "report_digest": report.get("report_digest")},
        )
    return {
        "ok": bool(report.get("ok")),
        "output_dir": str(output_dir),
        "report_digest": report.get("report_digest"),
        "suite_score": (report.get("fitness") or {}).get("suite_score"),
    }


def verify_fitness_report(report_dir: Path) -> dict[str, Any]:
    """Recompute every digest and re-grade fitness from recorded outcomes.

    Verification is pure: it re-derives fitness from the recorded task
    outcomes via :func:`compute_fitness` and recomputes the digest chain. A
    report whose fitness was misgraded, whose outcomes were flipped, or whose
    digest chain was edited fails verification.
    """

    report_path = report_dir / "report.json"
    if not report_path.exists():
        return {"ok": False, "error": f"missing report.json in {report_dir}"}
    report = json.loads(report_path.read_text(encoding="utf-8"))
    outcomes = report.get("task_outcomes") or []

    regraded = compute_fitness(outcomes)
    outcomes_digest = _digest([{"id": item.get("id"), "ok": item.get("ok")} for item in outcomes])
    fitness_digest = _digest(regraded)
    report_digest = hashlib.sha256(f"{outcomes_digest}:{fitness_digest}".encode("utf-8")).hexdigest()

    checks = {
        "outcomes_digest": outcomes_digest == report.get("outcomes_digest"),
        "fitness_regraded_matches": regraded == report.get("fitness"),
        "fitness_digest": fitness_digest == report.get("fitness_digest"),
        "report_digest": report_digest == report.get("report_digest"),
    }
    return {"ok": all(checks.values()), "checks": checks, "report_digest": report_digest}


def builtin_fitness_benchmark_proof() -> dict[str, Any]:
    """Registered proof for ``capability.fitness-benchmark``.

    Runs the suite twice to prove outcome determinism, seals and verifies a
    report, then proves falsifiability two ways: a tampered outcome copy and
    a misgraded fitness copy must both fail verification.
    """

    import tempfile

    first = run_fitness_benchmark()
    second = run_fitness_benchmark()
    if first["outcomes_digest"] != second["outcomes_digest"]:
        failing = [
            a["id"]
            for a, b in zip(first["task_outcomes"], second["task_outcomes"], strict=True)
            if a["ok"] != b["ok"]
        ]
        return {"ok": False, "stage": "determinism", "flaky_tasks": failing}

    with tempfile.TemporaryDirectory(prefix="fitness-benchmark-proof-") as tmp:
        out = Path(tmp) / "report"
        write_benchmark_report(first, out)
        verified = verify_fitness_report(out)
        if not verified["ok"]:
            return {"ok": False, "stage": "verify", "checks": verified.get("checks")}

        # Falsifiability 1: flip one recorded outcome; verification must fail.
        tampered = json.loads((out / "report.json").read_text(encoding="utf-8"))
        tampered["task_outcomes"][0]["ok"] = not tampered["task_outcomes"][0]["ok"]
        atomic_write_json(out / "report.json", tampered)
        if verify_fitness_report(out)["ok"]:
            return {"ok": False, "stage": "tamper-falsification", "detail": "flipped outcome passed verification"}

        # Falsifiability 2: restore outcomes but misgrade one fitness value.
        misgraded = json.loads(json.dumps(first))
        sample_id = sorted(misgraded["fitness"]["capability_fitness"])[0]
        misgraded["fitness"]["capability_fitness"][sample_id] = 0.0
        atomic_write_json(out / "report.json", misgraded)
        if verify_fitness_report(out)["ok"]:
            return {"ok": False, "stage": "misgrade-falsification", "detail": "misgraded fitness passed verification"}

    return {
        "ok": bool(first["ok"]),
        "suite_score": first["fitness"]["suite_score"],
        "capabilities_measured": first["fitness"]["capabilities_measured"],
        "task_pass_count": first["fitness"]["task_pass_count"],
        "task_count": first["fitness"]["task_count"],
        "weakest_capabilities": first["fitness"]["weakest_capabilities"],
        "report_digest": first["report_digest"],
        "deterministic": True,
        "tamper_detected": True,
        "misgrade_detected": True,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Capability fitness benchmark")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--run", action="store_true", help="run the suite and seal a report artifact")
    mode.add_argument("--verify", type=Path, help="verify a sealed report directory")
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args(argv)

    if args.run:
        report = run_fitness_benchmark()
        stamp = report["run_at"].replace(":", "").replace("-", "")
        out = args.output_dir or (REPO_ROOT / DEFAULT_ARTIFACT_DIR / stamp)
        summary = write_benchmark_report(report, out)
        summary["fitness"] = report["fitness"]
    else:
        summary = verify_fitness_report(args.verify)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
