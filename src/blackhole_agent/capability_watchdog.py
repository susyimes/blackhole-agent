"""Goal watchdog: detect drift in goal solvability before it ships.

Every milestone claims a capability increment; nothing checked that the
*existing* goals still solve afterwards. This module closes that gap:

- run every application goal over a ledger (live by default, or an override
  for scratch experiments) and record per-goal solvability, derived plan,
  and oracle outcome — a goal that was solvable yesterday and is not today
  is **drift**, reported by name;
- digest-sealed reports under ``artifacts/capability-watchdog/`` whose
  verification recomputes the grade and re-checks every recorded plan
  against the live ledger — a watchdog that rounds drift up to healthy
  fails verification;
- a registered proof (:func:`builtin_goal_watchdog`) that proves the live
  workspace is healthy, that a synthetic red stamp on a surface capability
  is flagged as drift by goal name, and that tampered and misgraded reports
  fail verification.

The Unbound milestone gate consumes :func:`run_goal_watchdog` through a
workspace subprocess: a milestone that regresses an existing goal is
refused with the drifted goal names in the gate reasons.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from blackhole_agent.durable_state import durable_read_path

from blackhole_agent.capability_application import (
    APPLICATION_TASKS,
    ApplicationStep,
    ApplicationTask,
    build_application_registry,
    plan_member_is_sound,
    run_application_task,
)
from blackhole_agent.capability_compounder import (
    CapabilityLedger,
    atomic_write_json,
    default_ledger_path,
    legacy_pipeline_was_used,
    load_ledger,
    utc_now_iso,
)
from blackhole_agent.capability_repair import _clone_ledger, _replace_capability_fields

SCHEMA_VERSION = 1

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT_DIR = "artifacts/capability-watchdog"
LATEST_POINTER = REPO_ROOT / DEFAULT_ARTIFACT_DIR / "latest-watchdog.json"


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def run_goal_watchdog(
    *,
    ledger: CapabilityLedger | None = None,
    tasks: Sequence[ApplicationTask] | None = None,
    include_absorbed: bool = False,
    hide: Sequence[str] = (),
    registry: Mapping[str, ApplicationStep] | None = None,
) -> dict[str, Any]:
    """Check application goals against a ledger (live by default).

    Default arguments preserve pre-growth semantics: only ``APPLICATION_TASKS``
    over the base registry. Pass ``include_absorbed=True`` and absorbed
    composition or mixed MCP+absorbed tasks to watch typed key-bridge
    pipelines; ``hide`` removes surface members the same way planner honesty
    does. ``registry`` overrides the built surface so a mixed MCP or
    absorbed composition pipeline can be watched without BFS-exhausting
    the whole absorbed zoo when a hop or producer is hidden.
    """

    active = ledger if ledger is not None else load_ledger(default_ledger_path(REPO_ROOT))
    if registry is None:
        surface = build_application_registry(active, hide=hide, include_absorbed=include_absorbed)
    else:
        hidden = set(hide)
        surface = {key: step for key, step in registry.items() if key not in hidden}
    task_list = tuple(tasks) if tasks is not None else APPLICATION_TASKS

    goal_results: list[dict[str, Any]] = []
    for task in task_list:
        result = run_application_task(task, surface)
        plan = result["plan"] or []
        goal_results.append(
            {
                "id": task.id,
                "solvable": result["plan"] is not None,
                "ok": result["ok"],
                "plan": result["plan"],
                "plan_sound": bool(plan)
                and all(plan_member_is_sound(active, capability_id) for capability_id in plan),
                "error": result["error"],
            }
        )

    drifted = sorted(record["id"] for record in goal_results if not record["ok"])
    goals_digest = _digest(
        [{"id": record["id"], "ok": record["ok"], "plan": record["plan"]} for record in goal_results]
    )
    report_digest = hashlib.sha256(f"watchdog:{goals_digest}".encode("utf-8")).hexdigest()
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "capability_goal_watchdog",
        "run_at": utc_now_iso(),
        "goal_results": goal_results,
        "goal_count": len(goal_results),
        "healthy_count": sum(1 for record in goal_results if record["ok"]),
        "drifted_goals": drifted,
        "goals_digest": goals_digest,
        "report_digest": report_digest,
        "ok": not drifted and all(record["plan_sound"] for record in goal_results),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }


def write_watchdog_report(report: Mapping[str, Any], output_dir: Path) -> dict[str, Any]:
    """Seal the watchdog report artifact and refresh the latest pointer."""

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
        "drifted_goals": list(report.get("drifted_goals") or []),
    }


def verify_watchdog_report(report_dir: Path) -> dict[str, Any]:
    """Recompute the digest and re-check recorded plans against the live ledger.

    Verification never re-executes a goal. A report that hides drift (an
    ``ok`` flag or ``drifted_goals`` that disagree with the recorded goal
    results), a tampered digest, or a recorded plan naming a capability that
    is not a green ledger member and not a persisted bridge with green
    endpoints fails verification.
    """

    report_path = report_dir / "report.json"
    if not durable_read_path(report_path).exists():
        return {"ok": False, "error": f"missing report.json in {report_dir}"}
    report = json.loads(durable_read_path(report_path).read_text(encoding="utf-8"))
    goal_results = report.get("goal_results") or []

    ledger = load_ledger(default_ledger_path(REPO_ROOT))
    drifted = sorted(record.get("id") for record in goal_results if not record.get("ok"))
    goals_digest = _digest(
        [{"id": record.get("id"), "ok": record.get("ok"), "plan": record.get("plan")} for record in goal_results]
    )
    report_digest = hashlib.sha256(f"watchdog:{goals_digest}".encode("utf-8")).hexdigest()
    plans_sound = all(
        all(plan_member_is_sound(ledger, capability_id) for capability_id in (record.get("plan") or []))
        for record in goal_results
    )
    expected_ok = not drifted and plans_sound
    checks = {
        "goals_digest": goals_digest == report.get("goals_digest"),
        "report_digest": report_digest == report.get("report_digest"),
        "drifted_matches_records": drifted == sorted(report.get("drifted_goals") or []),
        "ok_matches_records": bool(report.get("ok")) == expected_ok,
        "healthy_count_matches": report.get("healthy_count")
        == sum(1 for record in goal_results if record.get("ok")),
        "plans_sound_against_live_ledger": plans_sound,
    }
    return {"ok": all(checks.values()), "checks": checks, "report_digest": report_digest}


def builtin_goal_watchdog() -> dict[str, Any]:
    """Registered proof for ``capability.goal-watchdog``.

    Proves the live workspace is healthy, then proves drift detection: a
    scratch ledger with ``domain.tool-routing`` stamped red must flag
    ``routed-triage-record`` by name while the other goals stay healthy.
    Then seals and verifies a report and falsifies two ways: a tampered
    goal outcome and a misgraded (drift-hiding) report must fail
    verification.
    """

    import os
    import tempfile

    live = run_goal_watchdog()
    if not live["ok"]:
        return {"ok": False, "stage": "live-health", "drifted_goals": live["drifted_goals"]}
    again = run_goal_watchdog()
    if again["goals_digest"] != live["goals_digest"]:
        return {"ok": False, "stage": "determinism"}

    drifted_ledger = _replace_capability_fields(
        _clone_ledger(load_ledger(default_ledger_path(REPO_ROOT))),
        "domain.tool-routing",
        last_proof_exit_code=1,
        last_proved_at="",
    )
    drift = run_goal_watchdog(ledger=drifted_ledger)
    drift_detected = (
        not drift["ok"]
        and drift["drifted_goals"] == ["routed-triage-record"]
        and drift["healthy_count"] == drift["goal_count"] - 1
    )
    if not drift_detected:
        return {"ok": False, "stage": "drift-detection", "drifted_goals": drift["drifted_goals"]}

    report_dir_raw = (os.environ.get("BLACKHOLE_WATCHDOG_REPORT_DIR") or "").strip()
    if report_dir_raw:
        out = Path(report_dir_raw)
        out.mkdir(parents=True, exist_ok=True)
        write_watchdog_report(live, out)
        verified = verify_watchdog_report(out)
        if not verified["ok"]:
            return {"ok": False, "stage": "verify", "checks": verified.get("checks")}
        return {
            "ok": not live["used_skill_route_discovery"],
            "drifted_goals": live["drifted_goals"],
            "report_digest": live["report_digest"],
            "report_dir": str(out),
            "deterministic": True,
            "drift_detected": True,
            "used_skill_route_discovery": live["used_skill_route_discovery"],
        }

    with tempfile.TemporaryDirectory(prefix="capability-watchdog-proof-") as tmp:
        out = Path(tmp) / "report"
        write_watchdog_report(live, out)
        verified = verify_watchdog_report(out)
        if not verified["ok"]:
            return {"ok": False, "stage": "verify", "checks": verified.get("checks")}

        # Falsifiability 1: flip one recorded goal outcome; verification must fail.
        tampered = json.loads(durable_read_path(out / "report.json").read_text(encoding="utf-8"))
        tampered["goal_results"][0]["ok"] = not tampered["goal_results"][0]["ok"]
        atomic_write_json(out / "report.json", tampered)
        if verify_watchdog_report(out)["ok"]:
            return {"ok": False, "stage": "tamper-falsification", "detail": "flipped outcome passed verification"}

        # Falsifiability 2: hide drift — claim the drifted run was healthy.
        hidden = json.loads(json.dumps(drift))
        hidden["drifted_goals"] = []
        hidden["ok"] = True
        atomic_write_json(out / "report.json", hidden)
        if verify_watchdog_report(out)["ok"]:
            return {
                "ok": False,
                "stage": "drift-hiding-falsification",
                "detail": "drift-hiding report passed verification",
            }

    return {
        "ok": not live["used_skill_route_discovery"],
        "drifted_goals": live["drifted_goals"],
        "report_digest": live["report_digest"],
        "deterministic": True,
        "drift_detected": True,
        "tamper_detected": True,
        "drift_hiding_detected": True,
        "used_skill_route_discovery": live["used_skill_route_discovery"],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Goal watchdog")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--run", action="store_true", help="run the watchdog and seal a report artifact")
    mode.add_argument("--verify", type=Path, help="verify a sealed report directory")
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args(argv)

    if args.run:
        report = run_goal_watchdog()
        stamp = report["run_at"].replace(":", "").replace("-", "")
        out = args.output_dir or (REPO_ROOT / DEFAULT_ARTIFACT_DIR / stamp)
        summary = write_watchdog_report(report, out)
        summary["healthy_count"] = report["healthy_count"]
        summary["goal_count"] = report["goal_count"]
    else:
        summary = verify_watchdog_report(args.verify)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
