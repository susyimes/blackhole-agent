"""Capability application plane: goal-directed pipeline synthesis over the ledger.

The utility plane grades *hand-authored* pipelines: a human wrote each task's
step sequence and the plane only checks it. This module closes the next gap —
the pipeline itself is **synthesized from a declarative goal**, not authored:

- each task declares only an initial state, a set of goal keys, and a frozen
  outcome oracle; no step sequence is given;
- a BFS planner searches the live proved capability ledger (capabilities whose
  ``last_proof_exit_code == 0``) for a minimal step sequence whose provided
  state keys cover the goal — the plan is derived, never hard-coded;
- the executor threads real capability behavior (the same step surfaces the
  utility plane grades) through the planned order and the final state is
  graded against the oracle — outcome grading, not exit codes;
- **plan minimality** is proven per task: re-executing with any one planned
  capability removed must break the outcome, so a plan padded with no-op
  members fails;
- **order sensitivity** is proven per task: executing the reversed plan must
  break, so the plan's order carries the causal structure;
- **planner honesty** is falsified directly: hiding one capability from the
  registry must make the tasks that need it honestly unplannable (reported
  unsolved, never faked);
- a digest-sealed report under ``artifacts/capability-application/`` whose
  grade is a pure function of the recorded plans, outcomes, and ablations;
  verification additionally re-checks every recorded plan against the live
  ledger, so a plan naming an unproved capability fails verification;
- a registered proof (:func:`builtin_application_plane`) that proves outcome
  determinism across runs and falsifies tampered, misgraded, and
  unsound-plan reports.

Determinism contract: task outcomes, plans, and ablation verdicts must be
reproducible across runs on the same checkout. Durations and timestamps are
diagnostics only and are excluded from every digest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from blackhole_agent.capability_compounder import (
    CapabilityLedger,
    atomic_write_json,
    default_ledger_path,
    legacy_pipeline_was_used,
    load_ledger,
    utc_now_iso,
)
from blackhole_agent.capability_utility import STEP_REGISTRY

SCHEMA_VERSION = 1

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT_DIR = "artifacts/capability-application"
LATEST_POINTER = REPO_ROOT / DEFAULT_ARTIFACT_DIR / "latest-application.json"

StateFn = Callable[[Mapping[str, Any]], dict[str, Any]]


# ---------------------------------------------------------------------------
# Step adapters: one uniform state-threading surface per ledger capability.
# An adapter reads its declared ``requires`` keys from the state, invokes the
# real capability behavior surface, and returns its declared ``provides``
# keys. Keeping adapters small and total (no optional inputs) is what makes
# plans minimally falsifiable: remove a member and the chain type-checks no
# longer, or the oracle breaks.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ApplicationStep:
    """One ledger capability shaped for goal-directed composition."""

    capability_id: str
    requires: tuple[str, ...]
    provides: tuple[str, ...]
    invoke: StateFn


def _invoke_tool_routing(state: Mapping[str, Any]) -> dict[str, Any]:
    return {"preflight": STEP_REGISTRY["domain.tool-routing"]({"required": state["tool_requirements"]})}


def _invoke_issue_triage(state: Mapping[str, Any]) -> dict[str, Any]:
    issue = state["issue"]
    preflight = state["preflight"]
    out = STEP_REGISTRY["domain.issue-triage"](
        {
            "title": issue["title"],
            "body": issue["body"],
            "labels": issue["labels"],
            # Composition rule: triage only runs when the routing preflight
            # cleared its tool — the chain, not one capability in isolation.
            "lane_gate": preflight["preflight_ok"],
        }
    )
    return {"triage": {"lane": out["lane"], "gated": out["gated"]}}


def _invoke_local_memory(state: Mapping[str, Any]) -> dict[str, Any]:
    triage = state["triage"]
    out = STEP_REGISTRY["domain.local-memory"](
        {"key": "last-triage", "value": f"triage:{triage['lane']}"}
    )
    return {
        "memory_record": {
            "key": out["read_key"],
            "value": out["read_value"],
            "deleted": out["deleted"],
        }
    }


def _invoke_ci_security(state: Mapping[str, Any]) -> dict[str, Any]:
    return {"scan_gate": STEP_REGISTRY["domain.ci-security"](state["scan"])}


def _invoke_harness_activation(state: Mapping[str, Any]) -> dict[str, Any]:
    out = STEP_REGISTRY["domain.harness-activation"](
        {"failure_mode": "none", "scan_allowed": state["scan_gate"]["allowed"]}
    )
    return {"activation": out}


def _invoke_ledger_inventory(state: Mapping[str, Any]) -> dict[str, Any]:
    out = STEP_REGISTRY["capability.ledger-inventory"]({})
    return {"ledger_ready": out["ready"]}


def _invoke_proposal_eval(state: Mapping[str, Any]) -> dict[str, Any]:
    out = STEP_REGISTRY["domain.proposal-eval"](
        {"fixture": state["proposal_fixture"], "ledger_ready": state["ledger_ready"]}
    )
    return {"proposal_review": out}


APPLICATION_STEPS: dict[str, ApplicationStep] = {
    step.capability_id: step
    for step in (
        ApplicationStep(
            capability_id="domain.tool-routing",
            requires=("tool_requirements",),
            provides=("preflight",),
            invoke=_invoke_tool_routing,
        ),
        ApplicationStep(
            capability_id="domain.issue-triage",
            requires=("issue", "preflight"),
            provides=("triage",),
            invoke=_invoke_issue_triage,
        ),
        ApplicationStep(
            capability_id="domain.local-memory",
            requires=("triage",),
            provides=("memory_record",),
            invoke=_invoke_local_memory,
        ),
        ApplicationStep(
            capability_id="domain.ci-security",
            requires=("scan",),
            provides=("scan_gate",),
            invoke=_invoke_ci_security,
        ),
        ApplicationStep(
            capability_id="domain.harness-activation",
            requires=("scan_gate",),
            provides=("activation",),
            invoke=_invoke_harness_activation,
        ),
        ApplicationStep(
            capability_id="capability.ledger-inventory",
            requires=(),
            provides=("ledger_ready",),
            invoke=_invoke_ledger_inventory,
        ),
        ApplicationStep(
            capability_id="domain.proposal-eval",
            requires=("proposal_fixture", "ledger_ready"),
            provides=("proposal_review",),
            invoke=_invoke_proposal_eval,
        ),
    )
}


# ---------------------------------------------------------------------------
# Application tasks: declarative goals. No step sequence appears anywhere in
# a task definition — the planner derives it from the goal keys.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ApplicationTask:
    """One goal-directed application task over the live proved ledger."""

    id: str
    description: str
    initial_state: Mapping[str, Any]
    goal: tuple[str, ...]
    oracle: Mapping[str, Any]


APPLICATION_TASKS: tuple[ApplicationTask, ...] = (
    ApplicationTask(
        id="routed-triage-record",
        description=(
            "From a raw bug report and a tool requirement, produce a persisted, "
            "verified triage record — a three-capability chain that exists "
            "nowhere in the hand-authored utility suite."
        ),
        initial_state={
            "issue": {
                "title": "tests failing on main",
                "body": "regression in harness coverage",
                "labels": ["bug"],
            },
            "tool_requirements": ("issue_triage",),
        },
        goal=("triage", "memory_record"),
        oracle={
            "preflight": {
                "preflight_ok": True,
                "executable": ["auto_merge", "issue_triage"],
                "missing_required": [],
            },
            "triage": {"lane": "validation", "gated": False},
            "memory_record": {"key": "last-triage", "value": "triage:validation", "deleted": True},
        },
    ),
    ApplicationTask(
        id="scan-gated-activation",
        description="From a raw scan verdict, reach an allowed harness activation.",
        initial_state={"scan": {"scan_conclusion": "success"}},
        goal=("activation",),
        oracle={
            "scan_gate": {"allowed": True, "outcome": "security_scan_passed"},
            "activation": {
                "decision": "ready_for_local_eval_activation",
                "allowed": True,
                "external_allowed": False,
            },
        },
    ),
    ApplicationTask(
        id="blocked-scan-honesty",
        description=(
            "From a failing scan verdict, reach the activation surface and "
            "honestly report the blocked outcome — negative oracles are goals too."
        ),
        initial_state={"scan": {"scan_conclusion": "failure"}},
        goal=("activation",),
        oracle={
            "scan_gate": {"allowed": False, "outcome": "security_scan_blocked"},
            "activation": {
                "decision": "ready_for_local_eval_activation",
                "allowed": False,
                "external_allowed": False,
            },
        },
    ),
    ApplicationTask(
        id="ledger-gated-proposal",
        description="From a raw proposal fixture, reach a recorded review decision.",
        initial_state={"proposal_fixture": "benign_agent_harness.json"},
        goal=("proposal_review",),
        oracle={
            "ledger_ready": True,
            "proposal_review": {
                "passed": True,
                "review_status": "accepted",
                "accepted_count": 1,
                "rejected_count": 0,
                "decision": "record",
            },
        },
    ),
    ApplicationTask(
        id="ledger-inventory-check",
        description=(
            "Attest that the capability ledger is ready to carry new records. "
            "Deliberately shares capability.ledger-inventory with "
            "ledger-gated-proposal so blast-radius analysis has shared "
            "structure to measure."
        ),
        initial_state={},
        goal=("ledger_ready",),
        oracle={"ledger_ready": True},
    ),
)


# ---------------------------------------------------------------------------
# Planner and executor.
# ---------------------------------------------------------------------------


def _capability_proved(ledger: CapabilityLedger, capability_id: str) -> bool:
    capability = ledger.capabilities.get(capability_id)
    return bool(capability is not None and capability.last_proof_exit_code == 0)


def build_application_registry(
    ledger: CapabilityLedger, *, hide: Sequence[str] = ()
) -> dict[str, ApplicationStep]:
    """The planning surface: registered steps whose capability is proved live.

    A capability that is absent from the ledger or whose proof stamp is red is
    excluded — the planner may never plan over unproved behavior. ``hide``
    additionally removes proved capabilities; this is how planner honesty is
    falsified (a hidden capability must make dependent tasks unplannable).
    """

    hidden = set(hide)
    return {
        capability_id: step
        for capability_id, step in APPLICATION_STEPS.items()
        if capability_id not in hidden and _capability_proved(ledger, capability_id)
    }


def plan_application_task(
    task: ApplicationTask, registry: Mapping[str, ApplicationStep]
) -> list[str] | None:
    """BFS for a minimal capability sequence whose provides cover the goal.

    Returns the plan as an ordered list of capability ids, or ``None`` when no
    plan exists — an honest unsolvable, never a fabricated sequence. BFS over
    monotone key-set growth yields shortest plans first, and the sorted step
    order makes the result deterministic.
    """

    goal = set(task.goal)
    start = frozenset(task.initial_state)
    if goal <= start:
        return []
    queue: deque[tuple[frozenset[str], tuple[str, ...]]] = deque([(start, ())])
    visited = {start}
    while queue:
        available, plan = queue.popleft()
        for capability_id in sorted(registry):
            if capability_id in plan:
                continue
            step = registry[capability_id]
            if not set(step.requires) <= available:
                continue
            new_available = available | frozenset(step.provides)
            new_plan = plan + (capability_id,)
            if goal <= new_available:
                return list(new_plan)
            if new_available not in visited:
                visited.add(new_available)
                queue.append((new_available, new_plan))
    return None


def execute_application_plan(
    task: ApplicationTask,
    plan: Sequence[str],
    registry: Mapping[str, ApplicationStep],
) -> dict[str, Any]:
    """Thread real capability behavior through the planned order."""

    state = dict(task.initial_state)
    for capability_id in plan:
        step = registry[capability_id]
        missing = [key for key in step.requires if key not in state]
        if missing:
            raise KeyError(f"{capability_id} missing required state keys: {missing}")
        state.update(step.invoke(state))
    return state


def _oracle_matched(task: ApplicationTask, state: Mapping[str, Any]) -> bool:
    return all(state.get(key) == value for key, value in task.oracle.items())


def run_application_task(
    task: ApplicationTask,
    registry: Mapping[str, ApplicationStep],
    *,
    plan_override: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Plan (or take an override), execute, and grade one task by outcome."""

    plan = list(plan_override) if plan_override is not None else plan_application_task(task, registry)
    if plan is None:
        return {"ok": False, "plan": None, "outcome": {}, "error": "no plan covers the goal"}
    outcome: dict[str, Any] = {}
    error = ""
    try:
        outcome = execute_application_plan(task, plan, registry)
        matched = _oracle_matched(task, outcome)
    except Exception as exc:  # noqa: BLE001 - a crashed plan is a broken outcome, not a crashed plane
        matched = False
        error = f"{type(exc).__name__}: {exc}"
    return {"ok": matched, "plan": plan, "outcome": outcome, "error": error}


# ---------------------------------------------------------------------------
# Pure grading.
# ---------------------------------------------------------------------------


def compute_application_grade(task_records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Pure application derivation from recorded task outcomes.

    A task is **plan-attributed** when a plan was found, the executed outcome
    matched the oracle, corrupting the plan by removing any one member broke
    the outcome (minimality), and executing the reversed plan broke it too
    (order carries the causal structure). The application score is the
    fraction of suite tasks plan-attributed. This function is the single
    grading rule: a report whose recorded grade disagrees with its recorded
    outcomes is misgraded and fails verification.
    """

    attributed: list[str] = []
    for record in task_records:
        plan = record.get("plan") or []
        minimality = record.get("minimality") or []
        if not record.get("ok") or not plan:
            continue
        if len(minimality) != len(plan) or not all(bool(item.get("broke_outcome")) for item in minimality):
            continue
        if not bool(record.get("reversed_broke", len(plan) < 2)):
            continue
        attributed.append(str(record.get("id")))

    task_ids = [str(record.get("id")) for record in task_records]
    return {
        "task_pass_count": sum(1 for record in task_records if record.get("ok")),
        "task_count": len(task_records),
        "unsolvable_count": sum(1 for record in task_records if record.get("plan") is None),
        "plan_attributed": attributed,
        "application_score": round(len(attributed) / len(task_ids), 4) if task_ids else 0.0,
    }


# ---------------------------------------------------------------------------
# Plane execution.
# ---------------------------------------------------------------------------


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def run_application_plane(*, hide: Sequence[str] = ()) -> dict[str, Any]:
    """Plan, execute, grade, and falsify every application task."""

    ledger = load_ledger(default_ledger_path(REPO_ROOT))
    registry = build_application_registry(ledger, hide=hide)

    task_records: list[dict[str, Any]] = []
    for task in APPLICATION_TASKS:
        started = time.perf_counter()
        result = run_application_task(task, registry)
        duration_ms = round((time.perf_counter() - started) * 1000, 3)
        plan = result["plan"] or []

        minimality: list[dict[str, Any]] = []
        reversed_broke = True
        if result["ok"]:
            # Plan minimality: removing any one planned capability must break
            # the outcome — a padded plan fails here.
            for removed in plan:
                sub_plan = [capability_id for capability_id in plan if capability_id != removed]
                ablated = run_application_task(task, registry, plan_override=sub_plan)
                minimality.append({"removed": removed, "broke_outcome": not ablated["ok"]})
            # Order sensitivity: the reversed plan must break.
            if len(plan) >= 2:
                reversed_result = run_application_task(task, registry, plan_override=list(reversed(plan)))
                reversed_broke = not reversed_result["ok"]

        task_records.append(
            {
                "id": task.id,
                "description": task.description,
                "goal": list(task.goal),
                "ok": result["ok"],
                "plan": result["plan"],
                "plan_sound": bool(plan)
                and all(_capability_proved(ledger, capability_id) for capability_id in plan),
                "outcome": result["outcome"],
                "error": result["error"],
                "minimality": minimality,
                "reversed_broke": reversed_broke,
                "duration_ms": duration_ms,
            }
        )

    grade = compute_application_grade(task_records)
    plans_digest = _digest([{"id": record["id"], "plan": record["plan"]} for record in task_records])
    outcomes_digest = _digest(
        [
            {
                "id": record["id"],
                "ok": record["ok"],
                "minimality": record["minimality"],
                "reversed_broke": record["reversed_broke"],
            }
            for record in task_records
        ]
    )
    grade_digest = _digest(grade)
    report_digest = hashlib.sha256(
        f"application:{plans_digest}:{outcomes_digest}:{grade_digest}".encode("utf-8")
    ).hexdigest()
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "capability_application_plane",
        "run_at": utc_now_iso(),
        "hidden_capabilities": sorted(hide),
        "task_records": task_records,
        "application": grade,
        "plans_digest": plans_digest,
        "outcomes_digest": outcomes_digest,
        "grade_digest": grade_digest,
        "report_digest": report_digest,
        "ok": (
            grade["task_pass_count"] == grade["task_count"]
            and grade["unsolvable_count"] == 0
            and grade["application_score"] == 1.0
            and all(record["plan_sound"] for record in task_records)
        ),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }


def write_application_report(report: Mapping[str, Any], output_dir: Path) -> dict[str, Any]:
    """Seal the application report artifact and refresh the latest pointer."""

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
        "application_score": (report.get("application") or {}).get("application_score"),
    }


def verify_application_report(report_dir: Path) -> dict[str, Any]:
    """Recompute every digest, re-grade, and re-check plan soundness.

    Verification never re-executes a pipeline. A report whose outcomes were
    flipped, whose minimality verdicts were fabricated, whose grade was
    miscomputed, whose digest chain was edited, or whose recorded plans name
    a capability that is not proved in the live ledger fails verification.
    """

    report_path = report_dir / "report.json"
    if not report_path.exists():
        return {"ok": False, "error": f"missing report.json in {report_dir}"}
    report = json.loads(report_path.read_text(encoding="utf-8"))
    task_records = report.get("task_records") or []

    ledger = load_ledger(default_ledger_path(REPO_ROOT))
    regraded = compute_application_grade(task_records)
    plans_digest = _digest([{"id": record.get("id"), "plan": record.get("plan")} for record in task_records])
    outcomes_digest = _digest(
        [
            {
                "id": record.get("id"),
                "ok": record.get("ok"),
                "minimality": record.get("minimality"),
                "reversed_broke": record.get("reversed_broke"),
            }
            for record in task_records
        ]
    )
    grade_digest = _digest(regraded)
    report_digest = hashlib.sha256(
        f"application:{plans_digest}:{outcomes_digest}:{grade_digest}".encode("utf-8")
    ).hexdigest()

    plans_sound = all(
        all(_capability_proved(ledger, capability_id) for capability_id in (record.get("plan") or []))
        for record in task_records
    )
    checks = {
        "plans_digest": plans_digest == report.get("plans_digest"),
        "outcomes_digest": outcomes_digest == report.get("outcomes_digest"),
        "grade_recomputed_matches": regraded == report.get("application"),
        "grade_digest": grade_digest == report.get("grade_digest"),
        "report_digest": report_digest == report.get("report_digest"),
        "plans_sound_against_live_ledger": plans_sound,
    }
    return {"ok": all(checks.values()), "checks": checks, "report_digest": report_digest}


def check_planner_honesty() -> dict[str, Any]:
    """Hidden capabilities must make dependent tasks honestly unplannable.

    Runs the plane with ``domain.tool-routing`` hidden: the routed triage
    chain has no plan and must be reported unsolved (never faked), while the
    tasks that do not need routing still solve. Then with
    ``capability.ledger-inventory`` hidden: the proposal gate must go
    unsolvable. A planner that fabricates plans over hidden capabilities, or
    that reports success without one, fails this check.
    """

    hidden_routing = run_application_plane(hide=("domain.tool-routing",))
    routing_records = {record["id"]: record for record in hidden_routing["task_records"]}
    routed = routing_records.get("routed-triage-record") or {}
    routing_honest = (
        routed.get("plan") is None
        and routed.get("ok") is False
        and (routing_records.get("scan-gated-activation") or {}).get("ok") is True
        and hidden_routing["application"]["unsolvable_count"] == 1
    )

    hidden_inventory = run_application_plane(hide=("capability.ledger-inventory",))
    inventory_records = {record["id"]: record for record in hidden_inventory["task_records"]}
    proposal = inventory_records.get("ledger-gated-proposal") or {}
    inventory_check = inventory_records.get("ledger-inventory-check") or {}
    inventory_honest = (
        proposal.get("plan") is None
        and proposal.get("ok") is False
        and inventory_check.get("plan") is None
        and inventory_check.get("ok") is False
        and hidden_inventory["application"]["unsolvable_count"] == 2
    )

    return {
        "honest": routing_honest and inventory_honest,
        "routing_hidden_unsolvable": routing_honest,
        "inventory_hidden_unsolvable": inventory_honest,
    }


def builtin_application_plane() -> dict[str, Any]:
    """Registered proof for ``capability.application-plane``.

    Runs the plane twice to prove plan and outcome determinism, proves
    planner honesty (hidden capabilities yield honest unsolvables), seals and
    verifies a report, then proves falsifiability three ways: a tampered task
    outcome, a fabricated plan naming an unproved capability, and a misgraded
    application score must all fail verification.
    """

    import os
    import tempfile

    first = run_application_plane()
    second = run_application_plane()
    determinism = (
        first["plans_digest"] == second["plans_digest"]
        and first["outcomes_digest"] == second["outcomes_digest"]
    )
    if not determinism:
        return {"ok": False, "stage": "determinism"}
    if not first["ok"]:
        return {"ok": False, "stage": "plane", "application": first["application"]}

    honesty = check_planner_honesty()
    if not honesty["honest"]:
        return {"ok": False, "stage": "planner-honesty", "honesty": honesty}

    report_dir_raw = (os.environ.get("BLACKHOLE_APPLICATION_REPORT_DIR") or "").strip()
    if report_dir_raw:
        out = Path(report_dir_raw)
        out.mkdir(parents=True, exist_ok=True)
        write_application_report(first, out)
        verified = verify_application_report(out)
        if not verified["ok"]:
            return {"ok": False, "stage": "verify", "checks": verified.get("checks")}
        return {
            "ok": True,
            "application": first["application"],
            "report_digest": first["report_digest"],
            "report_dir": str(out),
            "deterministic": True,
            "planner_honesty": honesty["honest"],
            "used_skill_route_discovery": first["used_skill_route_discovery"],
        }

    with tempfile.TemporaryDirectory(prefix="capability-application-proof-") as tmp:
        out = Path(tmp) / "report"
        write_application_report(first, out)
        verified = verify_application_report(out)
        if not verified["ok"]:
            return {"ok": False, "stage": "verify", "checks": verified.get("checks")}

        # Falsifiability 1: flip one recorded task outcome; verification must fail.
        tampered = json.loads((out / "report.json").read_text(encoding="utf-8"))
        tampered["task_records"][0]["ok"] = not tampered["task_records"][0]["ok"]
        atomic_write_json(out / "report.json", tampered)
        if verify_application_report(out)["ok"]:
            return {"ok": False, "stage": "tamper-falsification", "detail": "flipped outcome passed verification"}

        # Falsifiability 2: fabricate a plan naming an unproved capability.
        forged = json.loads(json.dumps(first))
        forged["task_records"][0]["plan"] = ["capability.no-such-capability"]
        forged["task_records"][0]["plan_sound"] = True
        # Re-seal digests so only the soundness re-check can catch the forgery.
        forged["plans_digest"] = _digest(
            [{"id": record["id"], "plan": record["plan"]} for record in forged["task_records"]]
        )
        forged["grade_digest"] = _digest(forged["application"])
        forged["report_digest"] = hashlib.sha256(
            f"application:{forged['plans_digest']}:{forged['outcomes_digest']}:{forged['grade_digest']}".encode(
                "utf-8"
            )
        ).hexdigest()
        atomic_write_json(out / "report.json", forged)
        if verify_application_report(out)["ok"]:
            return {
                "ok": False,
                "stage": "unsound-plan-falsification",
                "detail": "plan naming an unproved capability passed verification",
            }

        # Falsifiability 3: restore outcomes but misgrade the application score.
        misgraded = json.loads(json.dumps(first))
        misgraded["application"]["application_score"] = 0.0
        atomic_write_json(out / "report.json", misgraded)
        if verify_application_report(out)["ok"]:
            return {"ok": False, "stage": "misgrade-falsification", "detail": "misgraded score passed verification"}

    return {
        "ok": not first["used_skill_route_discovery"],
        "application": first["application"],
        "report_digest": first["report_digest"],
        "deterministic": True,
        "planner_honesty": honesty["honest"],
        "tamper_detected": True,
        "unsound_plan_detected": True,
        "misgrade_detected": True,
        "used_skill_route_discovery": first["used_skill_route_discovery"],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Capability application plane")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--run", action="store_true", help="run the plane and seal a report artifact")
    mode.add_argument("--verify", type=Path, help="verify a sealed report directory")
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args(argv)

    if args.run:
        report = run_application_plane()
        stamp = report["run_at"].replace(":", "").replace("-", "")
        out = args.output_dir or (REPO_ROOT / DEFAULT_ARTIFACT_DIR / stamp)
        summary = write_application_report(report, out)
        summary["application"] = report["application"]
    else:
        summary = verify_application_report(args.verify)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
