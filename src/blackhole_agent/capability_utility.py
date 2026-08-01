"""Capability utility plane: outcome-graded composition tasks with causal ablation.

The fitness benchmark and ledger sweep measure *liveness* — does a capability's
entry run green today. Liveness is necessary but not sufficient evidence of
utility: a ledger of 90+ green entries could still be a tower of no-ops. This
module is the missing utility measurement:

- a fixed suite of hermetic **composition tasks**, each threading two or more
  real ledger capabilities into one multi-step pipeline whose final work
  product is compared against a frozen oracle (outcome grading, not exit
  codes);
- **causal ablation** for every exercised capability: the pipeline is re-run
  with exactly one capability step replaced by a corrupting stub, and the
  ablation only counts when the pipeline outcome actually breaks — a declared
  dependency that the outcome does not depend on is measured, not assumed;
- a digest-sealed report artifact under ``artifacts/capability-utility/`` whose
  grade is a pure function of the recorded task and ablation outcomes, so
  tampering, misgrading, or fabricated ablation fails verification;
- a registered proof (:func:`builtin_utility_plane`) that additionally proves
  outcome determinism across runs and falsifies tampered and misgraded copies.

Determinism contract: task *outcomes* and ablation *verdicts* must be
reproducible across runs on the same checkout. Durations and timestamps are
diagnostics only and are excluded from every digest; ``verify_utility_report``
recomputes the grade and digest chain from recorded outcomes without
re-executing any pipeline.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from blackhole_agent.durable_state import durable_read_path
from typing import Any, Callable, Mapping, Sequence

from blackhole_agent.capability_compounder import (
    atomic_write_json,
    legacy_pipeline_was_used,
    utc_now_iso,
)

SCHEMA_VERSION = 1

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT_DIR = "artifacts/capability-utility"
LATEST_POINTER = REPO_ROOT / DEFAULT_ARTIFACT_DIR / "latest-utility.json"

StepFn = Callable[[Mapping[str, Any]], dict[str, Any]]


# ---------------------------------------------------------------------------
# Capability steps: each entry is the live behavior surface of one ledger
# capability, shaped for pipeline composition. Steps thread an input mapping
# and return a partial result; pipelines consume earlier results.
# ---------------------------------------------------------------------------


def _step_issue_triage(payload: Mapping[str, Any]) -> dict[str, Any]:
    from blackhole_agent.issue_triage import triage_issue_input

    lane_gate = payload.get("lane_gate", True)
    if not lane_gate:
        return {"lane": "blocked", "gated": True}
    result = triage_issue_input(
        {
            "title": str(payload.get("title") or ""),
            "body": str(payload.get("body") or ""),
            "labels": list(payload.get("labels") or []),
        },
        allow_remote_mutation=False,
    )
    return {
        "lane": result.lane,
        "gated": False,
        "remote_mutation_allowed": bool(getattr(result, "remote_mutation_allowed", False)),
    }


def _step_local_memory(payload: Mapping[str, Any]) -> dict[str, Any]:
    import tempfile

    from blackhole_agent.local_memory import LocalMemoryStore

    with tempfile.TemporaryDirectory(prefix="blackhole-utility-memory-") as tmp:
        store = LocalMemoryStore(Path(tmp), namespace="cap-utility")
        key = str(payload["key"])
        value = str(payload["value"])
        store.write(key, value, tags=("utility",))
        entry = store.read(key)
        deleted = store.delete(key)
        return {
            "read_key": entry.key if entry else None,
            "read_value": entry.value if entry else None,
            "deleted": bool(deleted),
        }


def _step_tool_routing(payload: Mapping[str, Any]) -> dict[str, Any]:
    from blackhole_agent.tool_routing import (
        ToolDescriptor,
        build_tool_routing_preflight,
    )

    descriptors = (
        ToolDescriptor(
            name="issue_triage",
            description="Local issue triage tool",
            provider="local",
            tool_type="function",
        ),
        ToolDescriptor(
            name="auto_merge",
            description="Needs human review",
            provider="local",
            tool_type="function",
            risk_flags=("remote-mutation",),
        ),
    )
    required = tuple(str(name) for name in payload.get("required") or ())
    preflight = build_tool_routing_preflight(descriptors, required_tool_names=required)
    return {
        "preflight_ok": bool(preflight.get("ok")),
        "executable": sorted(str(name) for name in (preflight.get("executable_tool_names") or [])),
        "missing_required": list(preflight.get("missing_required_tool_names") or []),
    }


def _step_ci_security(payload: Mapping[str, Any]) -> dict[str, Any]:
    from blackhole_agent.ci_security import SecurityScanGateInput, evaluate_security_scan_gate

    decision = evaluate_security_scan_gate(
        SecurityScanGateInput(scan_conclusion=str(payload["scan_conclusion"]))
    )
    return {"allowed": bool(decision.allowed), "outcome": decision.outcome}


def _step_harness_activation(payload: Mapping[str, Any]) -> dict[str, Any]:
    from blackhole_agent.capability_compounder import harness_activation_gate_decision

    scan_allowed = bool(payload["scan_allowed"])
    decision = harness_activation_gate_decision(str(payload["failure_mode"]))
    return {
        "decision": decision["decision"],
        # Composition rule: activation is only allowed when the upstream
        # security gate allowed it — the chain, not one gate in isolation.
        "allowed": bool(decision["local_eval_activation_allowed"]) and scan_allowed,
        "external_allowed": bool(decision["external_harness_execution_allowed"]),
    }


def _step_ledger_inventory(payload: Mapping[str, Any]) -> dict[str, Any]:
    from blackhole_agent.capability_compounder import (
        default_ledger_path,
        load_ledger,
    )

    ledger = load_ledger(default_ledger_path(REPO_ROOT))
    count = len(ledger.capabilities)
    return {"count": count, "ready": count >= 2}


def _step_proposal_eval(payload: Mapping[str, Any]) -> dict[str, Any]:
    from blackhole_agent.proposal_eval import load_proposal_replay_case, run_proposal_replay_case

    case_path = REPO_ROOT / "tests" / "fixtures" / "proposal_replay" / str(payload["fixture"])
    case = load_proposal_replay_case(case_path)
    result = run_proposal_replay_case(case)
    ledger_ready = bool(payload["ledger_ready"])
    return {
        "passed": bool(result.passed),
        "review_status": result.review_status,
        "accepted_count": result.accepted_count,
        "rejected_count": result.rejected_count,
        # Composition rule: a review decision is only recorded when the ledger
        # that would carry it is ready.
        "decision": "record" if (result.passed and ledger_ready) else "reject",
    }


STEP_REGISTRY: dict[str, StepFn] = {
    "domain.issue-triage": _step_issue_triage,
    "domain.local-memory": _step_local_memory,
    "domain.tool-routing": _step_tool_routing,
    "domain.ci-security": _step_ci_security,
    "domain.harness-activation": _step_harness_activation,
    "domain.proposal-eval": _step_proposal_eval,
    "capability.ledger-inventory": _step_ledger_inventory,
}


# ---------------------------------------------------------------------------
# Utility tasks: multi-capability pipelines with frozen outcome oracles.
# ---------------------------------------------------------------------------


def _pipeline_steps(disabled: str | None) -> dict[str, StepFn]:
    """Build the step map, replacing one capability with a corrupting stub."""

    steps = dict(STEP_REGISTRY)
    if disabled is not None:
        def _corrupted(payload: Mapping[str, Any], *, _cap: str = disabled) -> dict[str, Any]:
            # The stub keeps the pipeline running but poisons its data, so an
            # ablation only counts when the *outcome* depends on the step's
            # real output — not merely on the step having executed.
            return {"__disabled__": _cap, "payload_keys": sorted(payload)}

        steps[disabled] = _corrupted
    return steps


def _task_triage_memory_record(steps: Mapping[str, StepFn]) -> dict[str, Any]:
    triage = steps["domain.issue-triage"](
        {
            "title": "tests failing on main",
            "body": "regression in harness coverage",
            "labels": ["bug"],
        }
    )
    lane = triage["lane"]
    memory = steps["domain.local-memory"]({"key": "last-triage", "value": f"triage:{lane}"})
    return {
        "lane": lane,
        "gated": triage["gated"],
        "memory_key": memory["read_key"],
        "memory_value": memory["read_value"],
        "memory_deleted": memory["deleted"],
    }


def _task_secure_activation_chain(steps: Mapping[str, StepFn]) -> dict[str, Any]:
    scan = steps["domain.ci-security"]({"scan_conclusion": "success"})
    activation = steps["domain.harness-activation"](
        {"failure_mode": "none", "scan_allowed": scan["allowed"]}
    )
    blocked_scan = steps["domain.ci-security"]({"scan_conclusion": "failure"})
    blocked_activation = steps["domain.harness-activation"](
        {"failure_mode": "none", "scan_allowed": blocked_scan["allowed"]}
    )
    return {
        "scan_outcome": scan["outcome"],
        "scan_allowed": scan["allowed"],
        "activation_decision": activation["decision"],
        "activation_allowed": activation["allowed"],
        "blocked_scan_outcome": blocked_scan["outcome"],
        "blocked_activation_allowed": blocked_activation["allowed"],
    }


def _task_routed_triage_pipeline(steps: Mapping[str, StepFn]) -> dict[str, Any]:
    preflight = steps["domain.tool-routing"]({"required": ("issue_triage",)})
    triage = steps["domain.issue-triage"](
        {
            "title": "should we clarify the docs?",
            "body": "question about configuration",
            "labels": ["question"],
            "lane_gate": preflight["preflight_ok"],
        }
    )
    return {
        "preflight_ok": preflight["preflight_ok"],
        "executable": preflight["executable"],
        "missing_required": preflight["missing_required"],
        "lane": triage["lane"],
        "gated": triage["gated"],
    }


def _task_proposal_ledger_gate(steps: Mapping[str, StepFn]) -> dict[str, Any]:
    inventory = steps["capability.ledger-inventory"]({})
    review = steps["domain.proposal-eval"](
        {"fixture": "benign_agent_harness.json", "ledger_ready": inventory["ready"]}
    )
    return {
        "ledger_ready": inventory["ready"],
        "proposal_passed": review["passed"],
        "review_status": review["review_status"],
        "accepted_count": review["accepted_count"],
        "rejected_count": review["rejected_count"],
        "decision": review["decision"],
    }


@dataclass(frozen=True)
class UtilityTask:
    """One outcome-graded composition task over real ledger capabilities."""

    id: str
    description: str
    steps: tuple[str, ...]
    runner: Callable[[Mapping[str, StepFn]], dict[str, Any]]
    oracle: Mapping[str, Any]


UTILITY_TASKS: tuple[UtilityTask, ...] = (
    UtilityTask(
        id="triage-memory-record",
        description="Triage a bug report, then persist and verify the triage record in local memory.",
        steps=("domain.issue-triage", "domain.local-memory"),
        runner=_task_triage_memory_record,
        oracle={
            "lane": "validation",
            "gated": False,
            "memory_key": "last-triage",
            "memory_value": "triage:validation",
            "memory_deleted": True,
        },
    ),
    UtilityTask(
        id="secure-activation-chain",
        description="Security-scan gate chains into harness activation: activation only when the scan allows.",
        steps=("domain.ci-security", "domain.harness-activation"),
        runner=_task_secure_activation_chain,
        oracle={
            "scan_outcome": "security_scan_passed",
            "scan_allowed": True,
            "activation_decision": "ready_for_local_eval_activation",
            "activation_allowed": True,
            "blocked_scan_outcome": "security_scan_blocked",
            "blocked_activation_allowed": False,
        },
    ),
    UtilityTask(
        id="routed-triage-pipeline",
        description="Tool-routing preflight gates issue triage: triage only runs when its tool is executable.",
        steps=("domain.tool-routing", "domain.issue-triage"),
        runner=_task_routed_triage_pipeline,
        oracle={
            "preflight_ok": True,
            "executable": ["auto_merge", "issue_triage"],
            "missing_required": [],
            "lane": "follow_up",
            "gated": False,
        },
    ),
    UtilityTask(
        id="proposal-ledger-gate",
        description="Proposal review is only recorded when the capability ledger is ready to carry it.",
        steps=("capability.ledger-inventory", "domain.proposal-eval"),
        runner=_task_proposal_ledger_gate,
        oracle={
            "ledger_ready": True,
            "proposal_passed": True,
            "review_status": "accepted",
            "accepted_count": 1,
            "rejected_count": 0,
            "decision": "record",
        },
    ),
)


# ---------------------------------------------------------------------------
# Plane execution and pure grading.
# ---------------------------------------------------------------------------


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def run_utility_task(task: UtilityTask, *, disabled: str | None = None) -> dict[str, Any]:
    """Run one pipeline, optionally with one capability step corrupted."""

    steps = _pipeline_steps(disabled)
    outcome: dict[str, Any] = {}
    error = ""
    try:
        outcome = task.runner(steps)
        matched = outcome == dict(task.oracle)
    except Exception as exc:  # noqa: BLE001 - a crashed pipeline is a broken outcome, not a crashed plane
        matched = False
        error = f"{type(exc).__name__}: {exc}"
    return {"ok": matched, "outcome": outcome, "error": error}


def compute_utility_grade(
    task_outcomes: Sequence[Mapping[str, Any]],
    ablation_outcomes: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Pure utility derivation from recorded task and ablation outcomes.

    A task is **causally attributed** when its pipeline outcome matched the
    oracle *and* corrupting each of its declared capability steps broke the
    outcome. The utility score is the fraction of suite tasks causally
    attributed. This function is the single grading rule: a report whose
    recorded grade disagrees with its recorded outcomes is misgraded and fails
    verification.
    """

    outcomes_by_id = {str(item.get("id")): bool(item.get("ok")) for item in task_outcomes}
    ablations_by_task: dict[str, list[bool]] = {}
    for item in ablation_outcomes:
        ablations_by_task.setdefault(str(item.get("task_id")), []).append(bool(item.get("broke_outcome")))

    attributed: list[str] = []
    for task in UTILITY_TASKS:
        if task.id not in outcomes_by_id:
            continue
        breaks = ablations_by_task.get(task.id) or []
        if outcomes_by_id[task.id] and len(breaks) == len(task.steps) and all(breaks):
            attributed.append(task.id)

    return {
        "task_pass_count": sum(1 for ok in outcomes_by_id.values() if ok),
        "task_count": len(outcomes_by_id),
        "ablation_break_count": sum(1 for item in ablation_outcomes if bool(item.get("broke_outcome"))),
        "ablation_count": len(ablation_outcomes),
        "causally_attributed": attributed,
        "utility_score": round(len(attributed) / len(UTILITY_TASKS), 4) if UTILITY_TASKS else 0.0,
    }


def run_utility_plane() -> dict[str, Any]:
    """Run every composition task plus per-capability causal ablations."""

    task_outcomes: list[dict[str, Any]] = []
    ablation_outcomes: list[dict[str, Any]] = []
    for task in UTILITY_TASKS:
        started = time.perf_counter()
        result = run_utility_task(task)
        duration_ms = round((time.perf_counter() - started) * 1000, 3)
        task_outcomes.append(
            {
                "id": task.id,
                "description": task.description,
                "steps": list(task.steps),
                "ok": result["ok"],
                "outcome": result["outcome"],
                "error": result["error"],
                "duration_ms": duration_ms,
            }
        )
        for capability_id in task.steps:
            started = time.perf_counter()
            ablated = run_utility_task(task, disabled=capability_id)
            duration_ms = round((time.perf_counter() - started) * 1000, 3)
            ablation_outcomes.append(
                {
                    "task_id": task.id,
                    "capability_id": capability_id,
                    "broke_outcome": not ablated["ok"],
                    "error": ablated["error"],
                    "duration_ms": duration_ms,
                }
            )

    grade = compute_utility_grade(task_outcomes, ablation_outcomes)
    outcomes_digest = _digest([{"id": item["id"], "ok": item["ok"]} for item in task_outcomes])
    ablations_digest = _digest(
        [
            {
                "task_id": item["task_id"],
                "capability_id": item["capability_id"],
                "broke_outcome": item["broke_outcome"],
            }
            for item in ablation_outcomes
        ]
    )
    utility_digest = _digest(grade)
    report_digest = hashlib.sha256(
        f"utility:{outcomes_digest}:{ablations_digest}:{utility_digest}".encode("utf-8")
    ).hexdigest()
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "capability_utility_plane",
        "run_at": utc_now_iso(),
        "task_outcomes": task_outcomes,
        "ablation_outcomes": ablation_outcomes,
        "utility": grade,
        "outcomes_digest": outcomes_digest,
        "ablations_digest": ablations_digest,
        "utility_digest": utility_digest,
        "report_digest": report_digest,
        "ok": (
            grade["task_pass_count"] == grade["task_count"]
            and grade["ablation_break_count"] == grade["ablation_count"]
            and grade["utility_score"] == 1.0
        ),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }


def write_utility_report(report: Mapping[str, Any], output_dir: Path) -> dict[str, Any]:
    """Seal the utility report artifact and refresh the latest pointer."""

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
        "utility_score": (report.get("utility") or {}).get("utility_score"),
    }


def verify_utility_report(report_dir: Path) -> dict[str, Any]:
    """Recompute every digest and re-grade utility from recorded outcomes.

    Verification is pure: it never re-executes a pipeline. A report whose task
    outcomes were flipped, whose ablation verdicts were fabricated, whose grade
    was miscomputed, or whose digest chain was edited fails verification.
    """

    report_path = report_dir / "report.json"
    if not durable_read_path(report_path).exists():
        return {"ok": False, "error": f"missing report.json in {report_dir}"}
    report = json.loads(durable_read_path(report_path).read_text(encoding="utf-8"))
    task_outcomes = report.get("task_outcomes") or []
    ablation_outcomes = report.get("ablation_outcomes") or []

    regraded = compute_utility_grade(task_outcomes, ablation_outcomes)
    outcomes_digest = _digest([{"id": item["id"], "ok": item["ok"]} for item in task_outcomes])
    ablations_digest = _digest(
        [
            {
                "task_id": item["task_id"],
                "capability_id": item["capability_id"],
                "broke_outcome": item["broke_outcome"],
            }
            for item in ablation_outcomes
        ]
    )
    utility_digest = _digest(regraded)
    report_digest = hashlib.sha256(
        f"utility:{outcomes_digest}:{ablations_digest}:{utility_digest}".encode("utf-8")
    ).hexdigest()

    checks = {
        "outcomes_digest": outcomes_digest == report.get("outcomes_digest"),
        "ablations_digest": ablations_digest == report.get("ablations_digest"),
        "utility_regraded_matches": regraded == report.get("utility"),
        "utility_digest": utility_digest == report.get("utility_digest"),
        "report_digest": report_digest == report.get("report_digest"),
    }
    return {"ok": all(checks.values()), "checks": checks, "report_digest": report_digest}


def builtin_utility_plane() -> dict[str, Any]:
    """Registered proof for ``capability.utility-plane``.

    Runs the plane twice to prove outcome determinism, seals and verifies a
    report, then proves falsifiability three ways: a tampered task outcome, a
    fabricated ablation verdict, and a misgraded utility score must all fail
    verification.
    """

    import os
    import tempfile

    first = run_utility_plane()
    second = run_utility_plane()
    determinism = (
        first["outcomes_digest"] == second["outcomes_digest"]
        and first["ablations_digest"] == second["ablations_digest"]
    )
    if not determinism:
        return {"ok": False, "stage": "determinism"}

    report_dir_raw = (os.environ.get("BLACKHOLE_UTILITY_REPORT_DIR") or "").strip()
    if report_dir_raw:
        out = Path(report_dir_raw)
        out.mkdir(parents=True, exist_ok=True)
        write_utility_report(first, out)
        verified = verify_utility_report(out)
        if not verified["ok"]:
            return {"ok": False, "stage": "verify", "checks": verified.get("checks")}
        return {
            "ok": bool(first["ok"]) and not first["used_skill_route_discovery"],
            "utility": first["utility"],
            "report_digest": first["report_digest"],
            "report_dir": str(out),
            "deterministic": True,
            "used_skill_route_discovery": first["used_skill_route_discovery"],
        }

    with tempfile.TemporaryDirectory(prefix="capability-utility-proof-") as tmp:
        out = Path(tmp) / "report"
        write_utility_report(first, out)
        verified = verify_utility_report(out)
        if not verified["ok"]:
            return {"ok": False, "stage": "verify", "checks": verified.get("checks")}

        # Falsifiability 1: flip one recorded task outcome; verification must fail.
        tampered = json.loads(durable_read_path(out / "report.json").read_text(encoding="utf-8"))
        tampered["task_outcomes"][0]["ok"] = not tampered["task_outcomes"][0]["ok"]
        atomic_write_json(out / "report.json", tampered)
        if verify_utility_report(out)["ok"]:
            return {"ok": False, "stage": "tamper-falsification", "detail": "flipped outcome passed verification"}

        # Falsifiability 2: fabricate one ablation verdict; verification must fail.
        fabricated = json.loads(json.dumps(first))
        fabricated["ablation_outcomes"][0]["broke_outcome"] = not fabricated["ablation_outcomes"][0][
            "broke_outcome"
        ]
        atomic_write_json(out / "report.json", fabricated)
        if verify_utility_report(out)["ok"]:
            return {
                "ok": False,
                "stage": "ablation-falsification",
                "detail": "fabricated ablation verdict passed verification",
            }

        # Falsifiability 3: restore outcomes but misgrade the utility score.
        misgraded = json.loads(json.dumps(first))
        misgraded["utility"]["utility_score"] = 0.0
        atomic_write_json(out / "report.json", misgraded)
        if verify_utility_report(out)["ok"]:
            return {"ok": False, "stage": "misgrade-falsification", "detail": "misgraded utility passed verification"}

    return {
        "ok": bool(first["ok"]) and not first["used_skill_route_discovery"],
        "utility": first["utility"],
        "report_digest": first["report_digest"],
        "deterministic": True,
        "tamper_detected": True,
        "ablation_fabrication_detected": True,
        "misgrade_detected": True,
        "used_skill_route_discovery": first["used_skill_route_discovery"],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Capability utility plane")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--run", action="store_true", help="run the plane and seal a report artifact")
    mode.add_argument("--verify", type=Path, help="verify a sealed report directory")
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args(argv)

    if args.run:
        report = run_utility_plane()
        stamp = report["run_at"].replace(":", "").replace("-", "")
        out = args.output_dir or (REPO_ROOT / DEFAULT_ARTIFACT_DIR / stamp)
        summary = write_utility_report(report, out)
        summary["utility"] = report["utility"]
    else:
        summary = verify_utility_report(args.verify)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
