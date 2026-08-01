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
  so tampering or misgrading fails verification;
- a **ledger sweep** that closes the measurement gap: the hand-written suite
  grades a fixed set of core abilities deeply, while the sweep invokes every
  ledger capability through its live registered entry (subprocess-isolated,
  timeout-bounded, no proof commands) so all capabilities — not just the core
  ten — carry a current measured fitness that scout ranking can target.

Determinism contract: task *outcomes* (``ok`` booleans) must be reproducible
across runs on the same checkout. Durations and timestamps are recorded for
diagnostics but excluded from every digest; ``verify_fitness_report``
recomputes fitness and digests from recorded outcomes only, and the
registered proof additionally re-runs the whole suite to prove the outcome
digest is stable across executions. Sweep verification is likewise pure:
``verify_sweep_report`` re-derives fitness and digests from recorded sweep
outcomes without re-executing entries.
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
SWEEP_REPORT_NAME = "sweep-report.json"
LATEST_SWEEP_POINTER = REPO_ROOT / DEFAULT_ARTIFACT_DIR / "latest-sweep.json"
SWEEP_ENTRY_TIMEOUT_SECONDS = 180


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


def compute_sweep_fitness(sweep_outcomes: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Pure fitness derivation from recorded ledger-sweep outcomes.

    Each swept capability contributes exactly one outcome (its live entry
    invocation), so per-capability fitness is 1.0 or 0.0. This function is the
    single sweep grading rule: a sweep report whose recorded fitness disagrees
    with its recorded outcomes is misgraded and fails verification.
    """

    fitness: dict[str, float] = {}
    for item in sweep_outcomes:
        capability_id = str(item.get("id") or "")
        if not capability_id:
            continue
        fitness[capability_id] = 1.0 if bool(item.get("ok")) else 0.0
    fitness = dict(sorted(fitness.items()))
    suite_score = round(sum(fitness.values()) / len(fitness), 4) if fitness else 0.0
    weakest = [cid for cid, score in sorted(fitness.items(), key=lambda kv: (kv[1], kv[0])) if score < 1.0]
    return {
        "capability_fitness": fitness,
        "suite_score": suite_score,
        "capabilities_measured": len(fitness),
        "weakest_capabilities": weakest,
        "entry_pass_count": sum(1 for item in sweep_outcomes if bool(item.get("ok"))),
        "entry_count": len(sweep_outcomes),
    }


def run_ledger_sweep(
    *,
    repo_root: Path | None = None,
    timeout: int = SWEEP_ENTRY_TIMEOUT_SECONDS,
    capability_ids: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Invoke every ledger capability through its live registered entry.

    Entries run subprocess-isolated with a per-entry timeout — never their
    self-attested proof commands — so the sweep measures what an operator or
    the growth loop would actually get by invoking the capability today.
    A timeout, non-zero exit, or a payload without ``ok`` is recorded as a
    failed outcome; a crashed entry fails its own outcome, not the sweep.
    """

    from blackhole_agent.capability_compounder import (
        default_ledger_path,
        load_ledger,
        run_capability,
        topological_order,
    )

    root = (repo_root or REPO_ROOT).resolve()
    ledger = load_ledger(default_ledger_path(root))
    selected = [str(cid) for cid in (capability_ids or ledger.capabilities.keys())]
    order = topological_order(ledger, selected)

    outcomes: list[dict[str, Any]] = []
    for capability_id in order:
        capability = ledger.capabilities[capability_id]
        started = time.perf_counter()
        error = ""
        exit_code = 1
        try:
            result = run_capability(capability, cwd=root, timeout=timeout)
            ok = bool(result.ok)
            exit_code = int(result.exit_code)
            if not ok:
                error = (result.summary or result.stderr or "entry reported failure")[:300]
        except Exception as exc:  # noqa: BLE001 - a crashed entry is a failed outcome, not a crashed sweep
            ok = False
            error = f"{type(exc).__name__}: {exc}"[:300]
        duration_ms = round((time.perf_counter() - started) * 1000, 3)
        outcomes.append(
            {
                "id": capability_id,
                "entry": capability.entry,
                "ok": ok,
                "exit_code": exit_code,
                "duration_ms": duration_ms,
                "error": error,
            }
        )

    graded = compute_sweep_fitness(outcomes)
    outcomes_digest = _digest([{"id": item["id"], "ok": item["ok"]} for item in outcomes])
    fitness_digest = _digest(graded)
    report_digest = hashlib.sha256(f"sweep:{outcomes_digest}:{fitness_digest}".encode("utf-8")).hexdigest()
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "capability_ledger_sweep",
        "run_at": utc_now_iso(),
        "ledger_size": len(ledger.capabilities),
        "coverage": round(graded["capabilities_measured"] / len(ledger.capabilities), 4)
        if ledger.capabilities
        else 0.0,
        "sweep_outcomes": outcomes,
        "fitness": graded,
        "outcomes_digest": outcomes_digest,
        "fitness_digest": fitness_digest,
        "report_digest": report_digest,
        "ok": graded["entry_pass_count"] == graded["entry_count"] and graded["suite_score"] == 1.0,
    }


def write_sweep_report(report: Mapping[str, Any], output_dir: Path) -> dict[str, Any]:
    """Seal the sweep report artifact and refresh the latest-sweep pointer."""

    output_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(output_dir / SWEEP_REPORT_NAME, dict(report))
    if output_dir.parent == LATEST_SWEEP_POINTER.parent:
        atomic_write_json(
            LATEST_SWEEP_POINTER,
            {"report_dir": output_dir.name, "report_digest": report.get("report_digest")},
        )
    return {
        "ok": bool(report.get("ok")),
        "output_dir": str(output_dir),
        "report_digest": report.get("report_digest"),
        "suite_score": (report.get("fitness") or {}).get("suite_score"),
        "coverage": report.get("coverage"),
        "weakest_capabilities": (report.get("fitness") or {}).get("weakest_capabilities"),
    }


def verify_sweep_report(report_dir: Path) -> dict[str, Any]:
    """Recompute every sweep digest and re-grade fitness from recorded outcomes.

    Verification is pure — it never re-executes capability entries. A report
    whose outcomes were flipped, whose fitness was misgraded, or whose digest
    chain was edited fails verification.
    """

    report_path = report_dir / SWEEP_REPORT_NAME
    if not report_path.exists():
        return {"ok": False, "error": f"missing {SWEEP_REPORT_NAME} in {report_dir}"}
    report = json.loads(report_path.read_text(encoding="utf-8"))
    outcomes = report.get("sweep_outcomes") or []

    regraded = compute_sweep_fitness(outcomes)
    outcomes_digest = _digest([{"id": item["id"], "ok": item["ok"]} for item in outcomes])
    fitness_digest = _digest(regraded)
    report_digest = hashlib.sha256(f"sweep:{outcomes_digest}:{fitness_digest}".encode("utf-8")).hexdigest()

    checks = {
        "outcomes_digest": outcomes_digest == report.get("outcomes_digest"),
        "fitness_regraded_matches": regraded == report.get("fitness"),
        "fitness_digest": fitness_digest == report.get("fitness_digest"),
        "report_digest": report_digest == report.get("report_digest"),
    }
    return {"ok": all(checks.values()), "checks": checks, "report_digest": report_digest}


def load_latest_sweep_map(repo_root: Path) -> dict[str, float] | None:
    """Load the measured per-capability fitness map from the latest sealed sweep.

    Returns ``None`` when no sealed sweep report exists or its digest chain
    fails verification, so ranking falls back to the core benchmark only.
    """

    pointer_path = repo_root / DEFAULT_ARTIFACT_DIR / "latest-sweep.json"
    if not pointer_path.exists():
        return None
    try:
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
        report_dir = repo_root / DEFAULT_ARTIFACT_DIR / str(pointer.get("report_dir") or "")
        if not verify_sweep_report(report_dir)["ok"]:
            return None
        report = json.loads((report_dir / SWEEP_REPORT_NAME).read_text(encoding="utf-8"))
        fitness = (report.get("fitness") or {}).get("capability_fitness") or {}
        return {str(key): float(value) for key, value in fitness.items()}
    except Exception:  # noqa: BLE001 - an unreadable sweep means "no sweep signal"
        return None



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


def load_latest_fitness_map(repo_root: Path) -> dict[str, float] | None:
    """Load the measured per-capability fitness map from the latest sealed reports.

    Merges the core benchmark map with the ledger-sweep map. On conflict the
    stricter (lower) score wins, so a capability that passes its bare entry
    but fails a richer core task stays visibly weak. Returns ``None`` when no
    sealed report exists, so ranking falls back to pure novelty ordering.
    Every digest chain is re-verified before its map is trusted.
    """

    merged: dict[str, float] = {}

    pointer_path = repo_root / DEFAULT_ARTIFACT_DIR / "latest-benchmark.json"
    if pointer_path.exists():
        try:
            pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
            report_dir = repo_root / DEFAULT_ARTIFACT_DIR / str(pointer.get("report_dir") or "")
            if verify_fitness_report(report_dir)["ok"]:
                report = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))
                fitness = (report.get("fitness") or {}).get("capability_fitness") or {}
                merged.update({str(key): float(value) for key, value in fitness.items()})
        except Exception:  # noqa: BLE001 - an unreadable report means "no core fitness signal"
            pass

    sweep = load_latest_sweep_map(repo_root)
    if sweep:
        for capability_id, score in sweep.items():
            if capability_id in merged:
                merged[capability_id] = min(merged[capability_id], score)
            else:
                merged[capability_id] = score

    return merged or None


def builtin_fitness_scout_ablation() -> dict[str, Any]:
    """Registered proof for ``capability.fitness-scout``.

    Ablates fitness-aware frontier ranking against novelty-only ranking on the
    live ledger:

    1. coincide: with the live sealed report (uniform fitness, nothing weak),
       fitness-aware selection matches novelty-only selection — a healthy
       ledger has no weakness to target, so any divergence would be noise;
    2. sensitivity: degrading one live measured capability to 0.0 changes the
       ordered ready frontier list on the live ledger — selection tracks the
       fitness signal, diverging from novelty-only whenever fitness is
       non-uniform;
    3. causation: a counterfactual map scoring every ledger capability 1.0
       collapses fitness-aware ranking back to the exact novelty-only order,
       so sensitivity is caused by the fitness signal;
    4. weakest-targeting: the degraded capability's ready frontiers strictly
       gain fitness bonus.
    """

    from blackhole_agent.capability_compounder import (
        default_ledger_path,
        load_ledger,
        scout_capability_gaps,
    )

    ledger = load_ledger(default_ledger_path(REPO_ROOT))
    fitness_map = load_latest_fitness_map(REPO_ROOT)
    if not fitness_map:
        return {"ok": False, "stage": "load-fitness", "detail": "no sealed benchmark report"}

    def ready_order(fitness: Mapping[str, float] | None) -> list[str]:
        scout = scout_capability_gaps(ledger, repo_path=REPO_ROOT, fitness_map=fitness)
        return [
            str(item.get("suggested_id"))
            for item in (scout.get("opportunities") or [])
            if item.get("status") in {"ready", "ready_to_absorb"}
        ]

    novelty_order = ready_order(None)
    fitness_order = ready_order(fitness_map)
    coincide = novelty_order == fitness_order

    uniform_map = {capability_id: 1.0 for capability_id in ledger.capabilities}
    causation = ready_order(uniform_map) == novelty_order

    # Sensitivity + weakest-targeting: a uniform lift cannot reorder (adding a
    # constant to every frontier preserves order), so probe measured
    # capabilities from rarest to most common frontier coverage and accept the
    # first whose degradation changes the ready order — a genuine crossing.
    from collections import Counter

    scout = scout_capability_gaps(ledger, repo_path=REPO_ROOT, fitness_map=None)

    def frontier_members(item: Mapping[str, Any]) -> list[str]:
        members = [str(m) for m in (item.get("coverage") or item.get("members") or [])]
        return members or [str(item.get("suggested_id") or "")]

    member_counter: Counter[str] = Counter()
    for item in scout.get("opportunities") or []:
        if item.get("status") in {"ready", "ready_to_absorb"}:
            member_counter.update(m for m in frontier_members(item) if m in fitness_map)
    sensitivity = False
    weakest_detail: dict[str, Any] = {"target": None, "lifted": 0}
    for target, _count in sorted(member_counter.items(), key=lambda kv: (kv[1], kv[0])):
        degraded = dict(fitness_map)
        degraded[target] = 0.0
        degraded_scout = scout_capability_gaps(ledger, repo_path=REPO_ROOT, fitness_map=degraded)
        degraded_items = [
            item
            for item in (degraded_scout.get("opportunities") or [])
            if item.get("status") in {"ready", "ready_to_absorb"}
        ]
        degraded_order = [str(item.get("suggested_id")) for item in degraded_items]
        lifted = sum(
            1
            for item in degraded_items
            if target in frontier_members(item) and int(item.get("fitness_bonus") or 0) > 0
        )
        if degraded_order != novelty_order and lifted > 0:
            sensitivity = True
            weakest_detail = {"target": target, "lifted": lifted}
            break
        if lifted > 0 and not weakest_detail["lifted"]:
            weakest_detail = {"target": target, "lifted": lifted}

    ok = coincide and sensitivity and causation and weakest_detail["lifted"] > 0
    return {
        "ok": ok,
        "coincide": coincide,
        "sensitivity": sensitivity,
        "causation": causation,
        "weakest_targeting": weakest_detail,
        "fitness_aware_top": fitness_order[:3],
        "novelty_only_top": novelty_order[:3],
        "measured_capabilities": len(fitness_map),
        "used_skill_route_discovery": bool(scout.get("used_skill_route_discovery")),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Capability fitness benchmark")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--run", action="store_true", help="run the suite and seal a report artifact")
    mode.add_argument("--verify", type=Path, help="verify a sealed report directory")
    mode.add_argument("--sweep", action="store_true", help="sweep every ledger capability's live entry")
    mode.add_argument("--verify-sweep", type=Path, help="verify a sealed sweep report directory")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--sweep-timeout", type=int, default=SWEEP_ENTRY_TIMEOUT_SECONDS)
    args = parser.parse_args(argv)

    if args.run:
        report = run_fitness_benchmark()
        stamp = report["run_at"].replace(":", "").replace("-", "")
        out = args.output_dir or (REPO_ROOT / DEFAULT_ARTIFACT_DIR / stamp)
        summary = write_benchmark_report(report, out)
        summary["fitness"] = report["fitness"]
    elif args.sweep:
        report = run_ledger_sweep(timeout=args.sweep_timeout)
        stamp = report["run_at"].replace(":", "").replace("-", "")
        out = args.output_dir or (REPO_ROOT / DEFAULT_ARTIFACT_DIR / f"{stamp}-sweep")
        summary = write_sweep_report(report, out)
    elif args.verify_sweep is not None:
        summary = verify_sweep_report(args.verify_sweep)
    else:
        summary = verify_fitness_report(args.verify)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
