"""Restore mixed MCP+absorbed stack health after a red hop is healed.

Mixed stack-health grades a snapshot: a red MCP hop fails the mixed grade
and the recovery loop is deliberately not run there, so detection cannot
hide behind a heal. The MCP recovery plane heals that hop and re-solves
the composition, but it never re-grades mixed stack health. Default
recovery still ignores mixed goals, so a red hop that fails the mixed
grade stays failed after the base loop.

This module closes that restore gap without changing pre-growth semantics:

- default stack health and default recovery still ignore mixed pipelines;
- a live mixed stack is healthy;
- stamping the live MCP hop red fails the mixed stack grade;
- a healable hop break is repaired in-process, the composition re-plans,
  and mixed stack health returns to green;
- an unrepairable hop break stays red and leaves the mixed stack unhealthy;
- a digest-sealed report under ``artifacts/capability-mcp-stack-repair/``
  whose verification recomputes every verdict from recorded summaries and
  rejects tamper and misgrade.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from blackhole_agent.capability_application import APPLICATION_TASKS, ApplicationTask
from blackhole_agent.capability_compounder import (
    Capability,
    atomic_write_json,
    default_ledger_path,
    legacy_pipeline_was_used,
    load_ledger,
    register_capability,
    save_ledger,
    utc_now_iso,
)
from blackhole_agent.capability_mcp_application import (
    MCP_APPLICATION_BRIDGE_ID,
    load_persisted_mcp_bridge_records,
)
from blackhole_agent.capability_mcp_recovery import (
    MCP_RECOVERY_ID,
    repair_mcp_pipeline_member,
)
from blackhole_agent.capability_mcp_reliability import load_mcp_composition_tasks
from blackhole_agent.capability_mcp_stack import (
    MCP_STACK_ID,
    collect_mixed_headlines,
    compute_stack_verdicts,
)
from blackhole_agent.capability_recovery import (
    BREAK_FAILING_PROOF,
    BREAK_STALE_STAMP,
    apply_synthetic_break,
    run_recovery_loop,
)
from blackhole_agent.capability_repair import _clone_ledger
from blackhole_agent.durable_state import durable_read_path

SCHEMA_VERSION = 1
MCP_STACK_REPAIR_ID = "capability.mcp-stack-repair-plane"
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "capability-mcp-stack-repair"
LATEST_POINTER = DEFAULT_ARTIFACT_DIR / "latest-repair.json"
_DIGEST_EXCLUDE = frozenset({"generated_at", "run_at", "report_dir"})


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _health_projection(bundle: Mapping[str, Any]) -> dict[str, Any]:
    headlines = bundle.get("headlines") or {}
    health = bundle.get("health") or {}
    watchdog = headlines.get("watchdog") or {}
    recovery = headlines.get("recovery") or {}
    application = headlines.get("application") or {}
    return {
        "health": {
            "healthy": health.get("healthy"),
            "green_count": health.get("green_count"),
            "plane_count": health.get("plane_count"),
            "planes_green": dict(health.get("planes_green") or {}),
        },
        "drifted_goals": list(watchdog.get("drifted_goals") or []),
        "repair_count": recovery.get("repair_count"),
        "application_ok": application.get("ok"),
        "unsolvable_count": application.get("unsolvable_count"),
    }


def _repair_projection(capability_id: str, report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "capability_id": capability_id,
        "ok": bool(report.get("ok")),
        "verdict": str(report.get("verdict") or ""),
        "repair_actions": list(report.get("repair_actions") or []),
        "honest": bool(report.get("honest")),
        "last_proof_exit_code": report.get("last_proof_exit_code"),
    }


def _stack_is_healthy(record: Mapping[str, Any]) -> bool:
    health = record.get("health") or {}
    return (
        bool(health.get("healthy"))
        and health.get("green_count") == health.get("plane_count") == 4
        and not list(record.get("drifted_goals") or [])
        and record.get("repair_count") == 0
        and record.get("unsolvable_count") == 0
    )


def _grade_ledger(
    ledger,
    *,
    tasks: Sequence[ApplicationTask],
    live_ledger,
    mcp_id: str,
    composition_id: str,
) -> dict[str, Any]:
    bundle = collect_mixed_headlines(
        ledger,
        tasks=tasks,
        live_ledger=live_ledger,
        mcp_id=mcp_id,
        composition_id=composition_id,
    )
    return _health_projection(bundle)


def compute_repair_verdicts(
    *,
    tasks: Sequence[ApplicationTask] | None = None,
) -> dict[str, Any]:
    """Isolation, fail, heal-and-restore, and honest-unrepairable verdicts."""

    mcp_tasks = list(tasks) if tasks is not None else load_mcp_composition_tasks()
    mcp_ids = [task.id for task in mcp_tasks]
    pairs = load_persisted_mcp_bridge_records()
    mcp_id = str(pairs[0].get("consumer_id") or "") if pairs else ""
    composition_id = mcp_ids[0] if mcp_ids else ""
    base_ids = {task.id for task in APPLICATION_TASKS}
    live_ledger = load_ledger(default_ledger_path(REPO_ROOT))
    stack = compute_stack_verdicts(tasks=mcp_tasks)
    stack_verdicts = dict(stack.get("verdicts") or {})
    live = _health_projection(stack.get("live") or {})
    red = _health_projection(stack.get("red") or {})

    isolation = run_recovery_loop(breaks={mcp_id: BREAK_STALE_STAMP} if mcp_id else None)
    isolation_ids = {str(record.get("id")) for record in (isolation.get("task_records") or [])}
    isolation_summary = {
        "ok": bool(isolation.get("ok")),
        "repair_count": (isolation.get("recovery") or {}).get("repair_count"),
        "task_ids": sorted(isolation_ids),
        "repair_ids": [
            str(repair.get("capability_id")) for repair in (isolation.get("repairs") or [])
        ],
        "stack_base_isolation": bool(stack_verdicts.get("base_isolation")),
        "base_stack_ignores_red_hop": bool(stack_verdicts.get("base_stack_ignores_red_hop")),
        "stack_red_hop_fails": bool(stack_verdicts.get("red_hop_fails_stack")),
    }

    healed = {
        "repair": {
            "capability_id": mcp_id,
            "ok": False,
            "verdict": "",
            "repair_actions": [],
            "honest": False,
            "last_proof_exit_code": None,
        },
        **{
            key: None
            for key in ("health", "drifted_goals", "repair_count", "application_ok", "unsolvable_count")
        },
    }
    unrepairable = dict(healed)
    if mcp_id and mcp_tasks:
        broken = apply_synthetic_break(_clone_ledger(live_ledger), mcp_id, BREAK_STALE_STAMP)
        restored_ledger, healed_report = repair_mcp_pipeline_member(broken, mcp_id)
        healed = {
            "repair": _repair_projection(mcp_id, healed_report),
            **_grade_ledger(
                restored_ledger,
                tasks=mcp_tasks,
                live_ledger=live_ledger,
                mcp_id=mcp_id,
                composition_id=composition_id,
            ),
        }
        failing = apply_synthetic_break(_clone_ledger(live_ledger), mcp_id, BREAK_FAILING_PROOF)
        failed_ledger, failed_report = repair_mcp_pipeline_member(failing, mcp_id)
        unrepairable = {
            "repair": _repair_projection(mcp_id, failed_report),
            **_grade_ledger(
                failed_ledger,
                tasks=mcp_tasks,
                live_ledger=live_ledger,
                mcp_id=mcp_id,
                composition_id=composition_id,
            ),
        }

    verdicts = {
        "has_mcp_goals": bool(mcp_ids),
        "base_isolation": bool(mcp_ids)
        and bool(isolation_summary["ok"])
        and isolation_summary["repair_count"] == 0
        and mcp_id not in isolation_summary["repair_ids"]
        and isolation_ids.isdisjoint(mcp_ids)
        and isolation_ids == base_ids
        and bool(isolation_summary["stack_base_isolation"])
        and bool(isolation_summary["base_stack_ignores_red_hop"]),
        "live_mcp_stack_healthy": _stack_is_healthy(live) and bool(mcp_ids),
        "red_hop_fails_stack": bool(mcp_ids)
        and not bool((red.get("health") or {}).get("healthy"))
        and composition_id in list(red.get("drifted_goals") or [])
        and (red.get("repair_count") or 0) >= 1
        and bool(isolation_summary["stack_red_hop_fails"]),
        "healable_hop_restores_stack": bool(mcp_ids)
        and (healed.get("repair") or {}).get("verdict") == "repaired"
        and (healed.get("repair") or {}).get("last_proof_exit_code") == 0
        and _stack_is_healthy(healed),
        "unrepairable_hop_leaves_stack_unhealthy": bool(mcp_ids)
        and (unrepairable.get("repair") or {}).get("verdict") == "unrepairable"
        and (unrepairable.get("repair") or {}).get("last_proof_exit_code") not in (0, None)
        and not bool((unrepairable.get("health") or {}).get("healthy"))
        and composition_id in list(unrepairable.get("drifted_goals") or [])
        and (unrepairable.get("repair_count") or 0) >= 1,
        "no_skill_route": not legacy_pipeline_was_used(),
    }
    return {
        "mcp_ids": mcp_ids,
        "mcp_id": mcp_id,
        "composition_id": composition_id,
        "isolation": isolation_summary,
        "live": live,
        "red": red,
        "healed": healed,
        "unrepairable": unrepairable,
        "verdicts": verdicts,
        "ok": all(verdicts.values()) and not legacy_pipeline_was_used(),
    }


def run_mcp_stack_repair_plane(output_dir: Path | None = None) -> dict[str, Any]:
    """Prove fail/heal/restore honesty, seal a report, persist the live artifact."""

    honesty = compute_repair_verdicts()
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": "capability_mcp_stack_repair",
        "generated_at": utc_now_iso(),
        "mcp_ids": honesty["mcp_ids"],
        "mcp_id": honesty["mcp_id"],
        "composition_id": honesty["composition_id"],
        "isolation": honesty["isolation"],
        "live": honesty["live"],
        "red": honesty["red"],
        "healed": honesty["healed"],
        "unrepairable": honesty["unrepairable"],
        "verdicts": honesty["verdicts"],
        "grade": {
            "ok": honesty["ok"],
            "verdict_count": len(honesty["verdicts"]),
            "verdicts_passed": sum(1 for value in honesty["verdicts"].values() if value),
        },
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "ok": bool(honesty["ok"]) and not legacy_pipeline_was_used(),
    }
    report["report_digest"] = _digest(
        {key: value for key, value in report.items() if key not in _DIGEST_EXCLUDE and key != "report_digest"}
    )
    target_dir = output_dir or DEFAULT_ARTIFACT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(target_dir / "report.json", report)
    if output_dir is None or target_dir.resolve() == DEFAULT_ARTIFACT_DIR.resolve():
        atomic_write_json(
            LATEST_POINTER,
            {"report_dir": str(target_dir), "report_digest": report["report_digest"], "ok": report["ok"]},
        )
    return {
        "ok": report["ok"],
        "report_dir": str(target_dir),
        "report_digest": report["report_digest"],
        "mcp_ids": honesty["mcp_ids"],
        "verdicts": honesty["verdicts"],
        "healed": honesty["healed"],
        "unrepairable": honesty["unrepairable"],
        "used_skill_route_discovery": report["used_skill_route_discovery"],
    }


def _summaries_match_verdicts(report: Mapping[str, Any]) -> dict[str, bool]:
    """Pure consistency: recorded verdicts must follow recorded summaries."""

    verdicts = report.get("verdicts") or {}
    isolation = report.get("isolation") or {}
    live = report.get("live") or {}
    red = report.get("red") or {}
    healed = report.get("healed") or {}
    unrepairable = report.get("unrepairable") or {}
    mcp_ids = list(report.get("mcp_ids") or [])
    mcp_id = str(report.get("mcp_id") or "")
    composition_id = str(report.get("composition_id") or "")
    isolation_ids = set(isolation.get("task_ids") or [])
    base_ids = {task.id for task in APPLICATION_TASKS}
    derived = {
        "has_mcp_goals": bool(mcp_ids),
        "base_isolation": bool(mcp_ids)
        and bool(isolation.get("ok"))
        and isolation.get("repair_count") == 0
        and mcp_id not in list(isolation.get("repair_ids") or [])
        and isolation_ids.isdisjoint(mcp_ids)
        and isolation_ids == base_ids
        and bool(isolation.get("stack_base_isolation"))
        and bool(isolation.get("base_stack_ignores_red_hop")),
        "live_mcp_stack_healthy": _stack_is_healthy(live) and bool(mcp_ids),
        "red_hop_fails_stack": bool(mcp_ids)
        and not bool((red.get("health") or {}).get("healthy"))
        and composition_id in list(red.get("drifted_goals") or [])
        and (red.get("repair_count") or 0) >= 1
        and bool(isolation.get("stack_red_hop_fails")),
        "healable_hop_restores_stack": bool(mcp_ids)
        and (healed.get("repair") or {}).get("verdict") == "repaired"
        and (healed.get("repair") or {}).get("last_proof_exit_code") == 0
        and _stack_is_healthy(healed),
        "unrepairable_hop_leaves_stack_unhealthy": bool(mcp_ids)
        and (unrepairable.get("repair") or {}).get("verdict") == "unrepairable"
        and (unrepairable.get("repair") or {}).get("last_proof_exit_code") not in (0, None)
        and not bool((unrepairable.get("health") or {}).get("healthy"))
        and composition_id in list(unrepairable.get("drifted_goals") or [])
        and (unrepairable.get("repair_count") or 0) >= 1,
        "no_skill_route": not bool(report.get("used_skill_route_discovery")),
    }
    grade = report.get("grade") or {}
    expected_ok = all(derived.values())
    return {
        "verdicts_follow_summaries": derived == dict(verdicts),
        "grade_follows_verdicts": grade.get("ok") is expected_ok
        and grade.get("verdict_count") == len(derived)
        and grade.get("verdicts_passed") == sum(1 for value in derived.values() if value),
        "report_ok_follows_grade": bool(report.get("ok")) is expected_ok,
    }


def verify_mcp_stack_repair_report(report_dir: Path) -> dict[str, Any]:
    """Re-check the sealed digest and that verdicts follow recorded summaries.

    Verification never re-executes a repair. A report whose digest was
    retargeted, whose verdicts disagree with its summaries, or whose grade
    hides a failed verdict fails verification.
    """

    report_path = durable_read_path(report_dir / "report.json")
    if not report_path.is_file():
        return {"ok": False, "error": f"missing report.json in {report_dir}"}
    report = json.loads(report_path.read_text(encoding="utf-8"))
    recorded_body = {
        key: value
        for key, value in report.items()
        if key not in _DIGEST_EXCLUDE and key != "report_digest"
    }
    recorded_digest = _digest(recorded_body)
    consistency = _summaries_match_verdicts(report)
    checks = {
        "digest_match": recorded_digest == report.get("report_digest"),
        "no_skill_route": not bool(report.get("used_skill_route_discovery"))
        and not legacy_pipeline_was_used(),
        **consistency,
    }
    return {"ok": all(checks.values()), "checks": checks, "report_digest": report.get("report_digest")}


def mcp_stack_repair_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.capability_mcp_stack_repair import "
        "builtin_mcp_stack_repair_proof; "
        "r=builtin_mcp_stack_repair_proof(); "
        "assert r['ok'] and r.get('verdicts',{}).get('base_isolation') "
        "and r.get('verdicts',{}).get('live_mcp_stack_healthy') "
        "and r.get('verdicts',{}).get('red_hop_fails_stack') "
        "and r.get('verdicts',{}).get('healable_hop_restores_stack') "
        "and r.get('verdicts',{}).get('unrepairable_hop_leaves_stack_unhealthy') "
        "and r.get('verify_ok') and r.get('tamper_detected') "
        "and r.get('misgrade_detected') and not r.get('used_skill_route_discovery')\""
    )


def ensure_mcp_stack_repair_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the plane on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=MCP_STACK_REPAIR_ID,
        name="MCP mixed-composition stack-repair plane",
        description=(
            "Restores mixed MCP+absorbed stack health the snapshot grade "
            "cannot: a healable red MCP hop is repaired in-process and the "
            "mixed stack returns to green; an unrepairable hop leaves the "
            "stack unhealthy; default recovery stays on base goals."
        ),
        kind="python",
        entry="blackhole_agent.capability_mcp_stack_repair:builtin_mcp_stack_repair_proof",
        proof_command=mcp_stack_repair_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "capability.goal-stack-health",
            MCP_APPLICATION_BRIDGE_ID,
            MCP_RECOVERY_ID,
            MCP_STACK_ID,
        ),
        behavior_paths=(
            "src/blackhole_agent/capability_mcp_stack_repair.py",
            "src/blackhole_agent/capability_mcp_stack.py",
            "src/blackhole_agent/capability_mcp_recovery.py",
            "src/blackhole_agent/capability_recovery.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "Mixed MCP+absorbed stack health is restorable: a healable red "
            "MCP hop is repaired and the mixed stack grade returns to green, "
            "while an unrepairable hop leaves the stack unhealthy."
        ),
        tags=("mcp", "absorbed", "stack-health", "repair", "recovery", "composition"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_mcp_stack_repair_proof() -> dict[str, Any]:
    """Registered proof: isolation, restore, honest failure, seal, tamper, misgrade."""

    with tempfile.TemporaryDirectory(prefix="blackhole-mcp-stack-repair-") as tmp:
        report_dir = Path(tmp) / "report"
        result = run_mcp_stack_repair_plane(report_dir)
        if not result.get("ok"):
            return {**result, "verify_ok": False, "tamper_detected": False, "misgrade_detected": False}
        verification = verify_mcp_stack_repair_report(report_dir)
        report_path = report_dir / "report.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        tampered = json.loads(json.dumps(report))
        tampered["verdicts"]["healable_hop_restores_stack"] = not tampered["verdicts"][
            "healable_hop_restores_stack"
        ]
        atomic_write_json(report_path, tampered)
        tamper_failed = not verify_mcp_stack_repair_report(report_dir)["ok"]
        misgraded = json.loads(json.dumps(report))
        misgraded["grade"]["ok"] = not bool(misgraded["grade"]["ok"])
        atomic_write_json(report_path, misgraded)
        misgrade_failed = not verify_mcp_stack_repair_report(report_dir)["ok"]
        atomic_write_json(report_path, report)

    DEFAULT_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write_json(DEFAULT_ARTIFACT_DIR / "report.json", report)
    atomic_write_json(
        LATEST_POINTER,
        {"report_dir": str(DEFAULT_ARTIFACT_DIR), "report_digest": report["report_digest"], "ok": report["ok"]},
    )
    live_verified = verify_mcp_stack_repair_report(DEFAULT_ARTIFACT_DIR)
    ok = (
        bool(result["ok"])
        and bool(verification.get("ok"))
        and tamper_failed
        and misgrade_failed
        and bool(live_verified.get("ok"))
        and not legacy_pipeline_was_used()
    )
    if ok:
        ensure_mcp_stack_repair_capability()
    return {
        **result,
        "ok": ok,
        "verify_ok": bool(verification.get("ok")),
        "tamper_detected": tamper_failed,
        "misgrade_detected": misgrade_failed,
        "live_verify_ok": bool(live_verified.get("ok")),
        "action": "mcp_stack_repair_plane",
        "live_report_dir": str(DEFAULT_ARTIFACT_DIR),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }
