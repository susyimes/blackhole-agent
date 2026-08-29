"""Stack-health plane for absorbed composition pipelines the base stack cannot grade.

Goal-stack health compounds application, watchdog, fragility, recovery, and
synthesis over ``APPLICATION_TASKS``. After a typed key-bridge made two
absorbed leaves composable, a red producer still left the composite stack
green: those composition goals never entered the headlines.

This module closes that grading failure without changing pre-growth
semantics of the base stack:

- default stack health still ignores absorbed composition goals and stays
  green when the live producer is stamped red;
- mixed application, watchdog, topology-fragility, and snapshot-recovery
  headlines are graded together on the three-member pipeline surface so
  hide-one analysis cannot explode over the absorbed zoo;
- a live absorbed pipeline is healthy only when the composition plans,
  the watchdog reports no drift, the producer is a scored SPOF, and no
  pipeline member needs repair;
- stamping the live producer red makes the mixed absorbed stack grade
  fail, naming the composition goal in watchdog drift;
- restoring that failed grade after a healable producer is the absorbed
  stack-repair plane, not this snapshot;
- a digest-sealed report under ``artifacts/capability-absorbed-stack/``
  whose verification recomputes every verdict from the live ledger and
  rejects tamper and misgrade.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from blackhole_agent.capability_absorbed_composition import (
    ABSORBED_COMPOSITION_ID,
    load_persisted_bridge_records,
)
from blackhole_agent.capability_absorbed_recovery import composition_surface_ids
from blackhole_agent.capability_absorbed_reliability import (
    absorbed_watch_registry,
    load_absorbed_composition_tasks,
)
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
from blackhole_agent.capability_fragility import (
    compute_fragility_grade,
    compute_impact_matrix,
    compute_redundancy_depth,
    run_fragility_audit,
)
from blackhole_agent.capability_recovery import BREAK_STALE_STAMP, run_recovery_loop
from blackhole_agent.capability_repair import _clone_ledger, _replace_capability_fields
from blackhole_agent.capability_watchdog import run_goal_watchdog
from blackhole_agent.durable_state import durable_read_path

SCHEMA_VERSION = 1
ABSORBED_STACK_ID = "capability.absorbed-stack-health-plane"
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "capability-absorbed-stack"
LATEST_POINTER = DEFAULT_ARTIFACT_DIR / "latest-stack.json"
_DIGEST_EXCLUDE = frozenset({"generated_at", "run_at", "report_dir"})


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def absorbed_recovery_snapshot(ledger) -> dict[str, Any]:
    """Snapshot: mixed absorbed stack recovery is green only when every member is proved.

    Stack grade is a snapshot, not a heal. Running the recovery loop here
    would repair a red producer and hide the failure the leftover asks the
    stack grade to report. Restoring the grade after a healable producer is
    ``capability.absorbed-stack-repair-plane``.
    """

    red_ids: list[str] = []
    for capability_id in composition_surface_ids():
        capability = ledger.capabilities.get(capability_id)
        if capability is None or capability.last_proof_exit_code != 0:
            red_ids.append(capability_id)
    return {
        "ok": not red_ids,
        "repair_count": len(red_ids),
        "red_ids": red_ids,
    }


def run_absorbed_stack_fragility(
    ledger,
    *,
    tasks: Sequence[ApplicationTask],
) -> dict[str, Any]:
    """Hide-one topology over persisted absorbed composition pipelines."""

    registry = absorbed_watch_registry(ledger)
    matrix = compute_impact_matrix(ledger, tasks=tasks, registry=registry)
    depth = compute_redundancy_depth(ledger, tasks=tasks, registry=registry)
    grade = compute_fragility_grade(matrix, tasks=tasks, depth=depth)
    return {
        "ok": bool(tasks) and bool(registry),
        "impact_matrix": matrix,
        "fragility": grade,
        "redundancy_depth": depth,
    }


def _watch_absorbed(tasks: Sequence[ApplicationTask], ledger) -> dict[str, Any]:
    return run_goal_watchdog(
        ledger=ledger,
        tasks=tasks,
        include_absorbed=True,
        registry=absorbed_watch_registry(ledger),
    )


def _application_headline(watchdog: Mapping[str, Any]) -> dict[str, Any]:
    results = list(watchdog.get("goal_results") or [])
    return {
        "ok": bool(results) and all(bool(record.get("ok")) for record in results),
        "task_count": len(results),
        "task_pass_count": sum(1 for record in results if record.get("ok")),
        "unsolvable_count": sum(1 for record in results if not record.get("solvable")),
        "task_ids": [str(record.get("id")) for record in results],
    }


def _watchdog_headline(watchdog: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "ok": bool(watchdog.get("ok")),
        "healthy_count": watchdog.get("healthy_count"),
        "goal_count": watchdog.get("goal_count"),
        "drifted_goals": list(watchdog.get("drifted_goals") or []),
    }


def _fragility_headline(
    audit: Mapping[str, Any],
    *,
    producer_id: str,
    composition_id: str,
) -> dict[str, Any]:
    grade = audit.get("fragility") or {}
    matrix = audit.get("impact_matrix") or {}
    spofs = dict(grade.get("spofs_per_goal") or {})
    blast = dict(grade.get("blast_radius") or {})
    return {
        "ok": bool(audit.get("ok")),
        "fragility_score": grade.get("fragility_score"),
        "producer_blast": blast.get(producer_id),
        "producer_is_spof": bool(composition_id) and producer_id in list(spofs.get(composition_id) or []),
        "blocked_goals": list(matrix.get(producer_id) or []),
    }


def compute_absorbed_stack_health(headlines: Mapping[str, Any]) -> dict[str, Any]:
    """Pure mixed-absorbed stack grade from recorded headlines.

    Fragility is topology (the producer is a scored SPOF). Application,
    watchdog, and recovery are the current stamp: a red producer must fail
    those three and therefore the composite grade.
    """

    application = headlines.get("application") or {}
    watchdog = headlines.get("watchdog") or {}
    fragility = headlines.get("fragility") or {}
    recovery = headlines.get("recovery") or {}
    planes_green = {
        "application": bool(
            application.get("unsolvable_count") == 0
            and application.get("task_count")
            and application.get("task_pass_count") == application.get("task_count")
        ),
        "watchdog": bool(watchdog.get("drifted_goals") == [] and watchdog.get("ok") is True),
        "fragility": bool(
            fragility.get("ok") is True
            and (fragility.get("producer_blast") or 0) >= 1
            and bool(fragility.get("producer_is_spof"))
        ),
        "recovery": bool(recovery.get("ok") is True and recovery.get("repair_count") == 0),
    }
    return {
        "planes_green": planes_green,
        "green_count": sum(1 for green in planes_green.values() if green),
        "plane_count": len(planes_green),
        "healthy": all(planes_green.values()),
    }


def collect_absorbed_headlines(
    ledger,
    *,
    tasks: Sequence[ApplicationTask],
    live_ledger,
    producer_id: str,
    composition_id: str,
) -> dict[str, Any]:
    """Mixed application/watchdog/recovery from ``ledger``; fragility from live topology."""

    watchdog = _watch_absorbed(tasks, ledger)
    headlines = {
        "application": _application_headline(watchdog),
        "watchdog": _watchdog_headline(watchdog),
        "fragility": _fragility_headline(
            run_absorbed_stack_fragility(live_ledger, tasks=tasks),
            producer_id=producer_id,
            composition_id=composition_id,
        ),
        "recovery": absorbed_recovery_snapshot(ledger),
    }
    return {
        "headlines": headlines,
        "health": compute_absorbed_stack_health(headlines),
    }


def compute_stack_verdicts(
    *,
    tasks: Sequence[ApplicationTask] | None = None,
) -> dict[str, Any]:
    """Live isolation, mixed-absorbed stack health, and red-producer grade-failure."""

    absorbed_tasks = list(tasks) if tasks is not None else load_absorbed_composition_tasks()
    absorbed_ids = [task.id for task in absorbed_tasks]
    pairs = load_persisted_bridge_records()
    producer_id = str(pairs[0].get("producer_id") or "") if pairs else ""
    composition_id = absorbed_ids[0] if absorbed_ids else ""
    base_ids = {task.id for task in APPLICATION_TASKS}
    live_ledger = load_ledger(default_ledger_path(REPO_ROOT))

    base_watch = run_goal_watchdog()
    base_fragility = run_fragility_audit()
    base_recovery = run_recovery_loop(breaks={producer_id: BREAK_STALE_STAMP} if producer_id else None)
    live = (
        collect_absorbed_headlines(
            live_ledger,
            tasks=absorbed_tasks,
            live_ledger=live_ledger,
            producer_id=producer_id,
            composition_id=composition_id,
        )
        if absorbed_tasks
        else {"headlines": {}, "health": {"healthy": False, "planes_green": {}, "green_count": 0, "plane_count": 0}}
    )

    red_ledger = (
        _replace_capability_fields(
            _clone_ledger(live_ledger),
            producer_id,
            last_proof_exit_code=1,
            last_proved_at="",
        )
        if producer_id
        else live_ledger
    )
    red = (
        collect_absorbed_headlines(
            red_ledger,
            tasks=absorbed_tasks,
            live_ledger=live_ledger,
            producer_id=producer_id,
            composition_id=composition_id,
        )
        if producer_id and absorbed_tasks
        else live
    )
    red_base_watch = run_goal_watchdog(ledger=red_ledger) if producer_id else base_watch

    base_watch_ids = {str(record.get("id")) for record in (base_watch.get("goal_results") or [])}
    base_grade = base_fragility.get("fragility") or {}
    isolation_ids = set(str(record.get("id")) for record in (base_recovery.get("task_records") or []))
    live_health = live.get("health") or {}
    red_health = red.get("health") or {}
    red_watch = (red.get("headlines") or {}).get("watchdog") or {}
    live_watch = (live.get("headlines") or {}).get("watchdog") or {}

    verdicts = {
        "has_absorbed_goals": bool(absorbed_ids),
        "base_isolation": bool(absorbed_ids)
        and bool(base_watch.get("ok"))
        and base_watch_ids.isdisjoint(absorbed_ids)
        and base_watch_ids == base_ids
        and bool(base_recovery.get("ok"))
        and (base_recovery.get("recovery") or {}).get("repair_count") == 0
        and isolation_ids.isdisjoint(absorbed_ids)
        and isolation_ids == base_ids
        and producer_id not in (base_grade.get("blast_radius") or {})
        and base_grade.get("fragility_score") == 0.1667
        and base_grade.get("robust_goals") == ["ledger-inventory-check"]
        and base_grade.get("max_blast_radius") == 2,
        "live_absorbed_stack_healthy": bool(live_health.get("healthy"))
        and bool(absorbed_ids)
        and live_health.get("green_count") == live_health.get("plane_count") == 4
        and not list(live_watch.get("drifted_goals") or []),
        "red_producer_fails_stack": bool(absorbed_ids)
        and not bool(red_health.get("healthy"))
        and composition_id in list(red_watch.get("drifted_goals") or [])
        and not bool((red.get("headlines") or {}).get("application", {}).get("ok"))
        and (red.get("headlines") or {}).get("recovery", {}).get("repair_count", 0) >= 1,
        "base_stack_ignores_red_producer": bool(producer_id)
        and bool(red_base_watch.get("ok"))
        and list(red_base_watch.get("drifted_goals") or []) == [],
        "no_skill_route": not legacy_pipeline_was_used(),
    }
    return {
        "absorbed_ids": absorbed_ids,
        "producer_id": producer_id,
        "composition_id": composition_id,
        "live": live,
        "red": red,
        "base": {
            "watchdog_ok": bool(base_watch.get("ok")),
            "watchdog_goal_ids": sorted(base_watch_ids),
            "recovery_ok": bool(base_recovery.get("ok")),
            "recovery_repair_count": (base_recovery.get("recovery") or {}).get("repair_count"),
            "fragility_score": base_grade.get("fragility_score"),
            "max_blast_radius": base_grade.get("max_blast_radius"),
        },
        "verdicts": verdicts,
        "ok": all(verdicts.values()) and not legacy_pipeline_was_used(),
    }


def run_absorbed_stack_health_plane(output_dir: Path | None = None) -> dict[str, Any]:
    """Prove isolation + red-producer grade failure, seal a report, persist the live artifact."""

    honesty = compute_stack_verdicts()
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": "capability_absorbed_stack_health",
        "generated_at": utc_now_iso(),
        "absorbed_ids": honesty["absorbed_ids"],
        "producer_id": honesty["producer_id"],
        "composition_id": honesty["composition_id"],
        "live": honesty["live"],
        "red": honesty["red"],
        "base": honesty["base"],
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
        "absorbed_ids": honesty["absorbed_ids"],
        "verdicts": honesty["verdicts"],
        "live": honesty["live"],
        "red": honesty["red"],
        "used_skill_route_discovery": report["used_skill_route_discovery"],
    }


def verify_absorbed_stack_health_report(report_dir: Path) -> dict[str, Any]:
    """Recompute live mixed-absorbed stack verdicts and re-check the sealed digest."""

    report_path = durable_read_path(report_dir / "report.json")
    if not report_path.is_file():
        return {"ok": False, "error": f"missing report.json in {report_dir}"}
    report = json.loads(report_path.read_text(encoding="utf-8"))
    honesty = compute_stack_verdicts()
    recomputed = {
        "schema_version": SCHEMA_VERSION,
        "kind": "capability_absorbed_stack_health",
        "absorbed_ids": honesty["absorbed_ids"],
        "producer_id": honesty["producer_id"],
        "composition_id": honesty["composition_id"],
        "live": honesty["live"],
        "red": honesty["red"],
        "base": honesty["base"],
        "verdicts": honesty["verdicts"],
        "grade": {
            "ok": honesty["ok"],
            "verdict_count": len(honesty["verdicts"]),
            "verdicts_passed": sum(1 for value in honesty["verdicts"].values() if value),
        },
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "ok": bool(honesty["ok"]) and not legacy_pipeline_was_used(),
    }
    recomputed_digest = _digest(recomputed)
    recorded_body = {
        key: value
        for key, value in report.items()
        if key not in _DIGEST_EXCLUDE and key != "report_digest"
    }
    recorded_digest = _digest(recorded_body)
    checks = {
        "honesty_ok": bool(honesty["ok"]),
        "digest_match": recorded_digest == report.get("report_digest"),
        "recomputed_digest_match": recomputed_digest == report.get("report_digest"),
        "verdicts_match": honesty["verdicts"] == (report.get("verdicts") or {}),
        "absorbed_ids_match": honesty["absorbed_ids"] == list(report.get("absorbed_ids") or []),
        "red_producer_fails_match": honesty["verdicts"].get("red_producer_fails_stack")
        is (report.get("verdicts") or {}).get("red_producer_fails_stack"),
        "live_health_recomputed": compute_absorbed_stack_health((honesty["live"] or {}).get("headlines") or {})
        == ((honesty["live"] or {}).get("health") or {}),
        "no_skill_route": not legacy_pipeline_was_used(),
    }
    return {"ok": all(checks.values()), "checks": checks, "report_digest": report.get("report_digest")}


def absorbed_stack_health_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.capability_absorbed_stack import "
        "builtin_absorbed_stack_health_proof; "
        "r=builtin_absorbed_stack_health_proof(); "
        "assert r['ok'] and r.get('verdicts',{}).get('base_isolation') "
        "and r.get('verdicts',{}).get('live_absorbed_stack_healthy') "
        "and r.get('verdicts',{}).get('red_producer_fails_stack') "
        "and r.get('verdicts',{}).get('base_stack_ignores_red_producer') "
        "and r.get('verify_ok') and r.get('tamper_detected') "
        "and r.get('misgrade_detected') and not r.get('used_skill_route_discovery')\""
    )


def ensure_absorbed_stack_health_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the plane on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=ABSORBED_STACK_ID,
        name="Absorbed composition stack-health plane",
        description=(
            "Grades absorbed composition pipelines the base stack-health "
            "surface cannot see: a red absorbed producer fails the mixed "
            "absorbed stack grade, and base-stack pre-growth semantics stay "
            "intact."
        ),
        kind="python",
        entry="blackhole_agent.capability_absorbed_stack:builtin_absorbed_stack_health_proof",
        proof_command=absorbed_stack_health_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "capability.goal-stack-health",
            ABSORBED_COMPOSITION_ID,
            "capability.absorbed-reliability-plane",
            "capability.absorbed-recovery-plane",
        ),
        behavior_paths=(
            "src/blackhole_agent/capability_absorbed_stack.py",
            "src/blackhole_agent/capability_stack.py",
            "src/blackhole_agent/capability_application.py",
            "src/blackhole_agent/capability_absorbed_reliability.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "Absorbed composition pipelines are stack-health visible: a red "
            "producer fails the mixed absorbed stack grade, while default "
            "stack health still ignores those goals."
        ),
        tags=("absorbed", "stack-health", "grade", "composition"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_absorbed_stack_health_proof() -> dict[str, Any]:
    """Registered proof: isolation, red-producer grade failure, seal, tamper, misgrade."""

    with tempfile.TemporaryDirectory(prefix="blackhole-absorbed-stack-") as tmp:
        report_dir = Path(tmp) / "report"
        result = run_absorbed_stack_health_plane(report_dir)
        if not result.get("ok"):
            return {**result, "verify_ok": False, "tamper_detected": False, "misgrade_detected": False}
        verification = verify_absorbed_stack_health_report(report_dir)
        report_path = report_dir / "report.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        tampered = json.loads(json.dumps(report))
        tampered["verdicts"]["red_producer_fails_stack"] = not tampered["verdicts"]["red_producer_fails_stack"]
        atomic_write_json(report_path, tampered)
        tamper_failed = not verify_absorbed_stack_health_report(report_dir)["ok"]
        misgraded = json.loads(json.dumps(report))
        misgraded["grade"]["ok"] = not bool(misgraded["grade"]["ok"])
        atomic_write_json(report_path, misgraded)
        misgrade_failed = not verify_absorbed_stack_health_report(report_dir)["ok"]
        atomic_write_json(report_path, report)

    live = run_absorbed_stack_health_plane(DEFAULT_ARTIFACT_DIR)
    ok = (
        bool(result["ok"])
        and bool(verification.get("ok"))
        and tamper_failed
        and misgrade_failed
        and bool(live.get("ok"))
        and not legacy_pipeline_was_used()
    )
    if ok:
        ensure_absorbed_stack_health_capability()
    return {
        **result,
        "ok": ok,
        "verify_ok": bool(verification.get("ok")),
        "tamper_detected": tamper_failed,
        "misgrade_detected": misgrade_failed,
        "action": "absorbed_stack_health_plane",
        "live_report_dir": str(DEFAULT_ARTIFACT_DIR),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }
