"""Reliability plane for mixed MCP+absorbed goals the base watchdog cannot see.

The goal watchdog, recovery loop, fragility audit, and stack-health plane
plan only over ``APPLICATION_TASKS`` on the base registry. After a typed
key-bridge made a live MCP tool compose with an absorbed Python leaf, that
mixed goal was still invisible: hiding the MCP hop shipped as a healthy
stack.

This module closes that reliability failure without changing pre-growth
semantics of the base planes:

- default watchdog results still omit mixed MCP+absorbed goals;
- the grown registry (``include_absorbed=True``) is watched for every
  persisted MCP bridge pipeline;
- hiding the live MCP hop, or stamping its producer red, reports the
  mixed composition goal by name as drift;
- hiding an unrelated base capability does not take the mixed goal down,
  and hiding the MCP hop does not take a base or absorbed-composition
  goal down;
- the MCP hop is a single point of failure for its mixed goal;
- a digest-sealed report under ``artifacts/capability-mcp-reliability/``
  whose verification recomputes every verdict from the live ledger and
  rejects tamper and drift-hiding.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any, Sequence

from blackhole_agent.capability_absorbed_composition import load_persisted_bridge_records
from blackhole_agent.capability_absorbed_reliability import load_absorbed_composition_tasks
from blackhole_agent.capability_absorption import load_persisted_absorbed_steps
from blackhole_agent.capability_application import (
    APPLICATION_TASKS,
    ApplicationStep,
    ApplicationTask,
    build_application_registry,
    plan_application_task,
)
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
    mixed_task,
)
from blackhole_agent.capability_repair import _clone_ledger, _replace_capability_fields
from blackhole_agent.capability_watchdog import (
    run_goal_watchdog,
    verify_watchdog_report,
    write_watchdog_report,
)
from blackhole_agent.durable_state import durable_read_path

SCHEMA_VERSION = 1
MCP_RELIABILITY_ID = "capability.mcp-reliability-plane"
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "capability-mcp-reliability"
LATEST_POINTER = DEFAULT_ARTIFACT_DIR / "latest-reliability.json"
_DIGEST_EXCLUDE = frozenset({"generated_at", "run_at", "report_dir"})


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def load_mcp_composition_tasks() -> list[ApplicationTask]:
    """Rebuild planner tasks for every persisted mixed MCP+absorbed bridge."""

    steps = dict(load_persisted_absorbed_steps())
    tasks: list[ApplicationTask] = []
    for pair in load_persisted_mcp_bridge_records():
        producer_id = str(pair.get("producer_id") or "")
        consumer_id = str(pair.get("consumer_id") or "")
        if not producer_id or not consumer_id or producer_id not in steps:
            continue
        tasks.append(mixed_task(pair, absorbed_steps=steps))
    return tasks


def mixed_pipeline_ids() -> set[str]:
    """Producer, typed key-bridge, and live MCP hop for every persisted pair."""

    members: set[str] = set()
    for pair in load_persisted_mcp_bridge_records():
        for key in ("producer_id", "bridge_id", "consumer_id"):
            capability_id = str(pair.get(key) or "")
            if capability_id:
                members.add(capability_id)
    return members


def mixed_watch_registry(ledger, *, hide: Sequence[str] = ()) -> dict[str, ApplicationStep]:
    """Grown mixed-pipeline surface without the rest of the absorbed zoo.

    Hide-one analysis over the full absorbed registry is exponential: when
    the MCP hop is missing the BFS exhausts every reachable key-set. The
    mixed goal only needs its three pipeline members, and those still come
    from the grown ``include_absorbed`` registry so red stamps and hides
    stay honest.
    """

    grown = build_application_registry(ledger, include_absorbed=True, hide=hide)
    members = mixed_pipeline_ids()
    return {key: step for key, step in grown.items() if key in members}


def _watch_mcp(
    tasks: Sequence[ApplicationTask],
    *,
    ledger=None,
    hide: Sequence[str] = (),
):
    active = ledger if ledger is not None else load_ledger(default_ledger_path(REPO_ROOT))
    return run_goal_watchdog(
        ledger=active,
        tasks=tasks,
        include_absorbed=True,
        hide=hide,
        registry=mixed_watch_registry(active, hide=hide),
    )


def compute_reliability_verdicts(
    *,
    tasks: Sequence[ApplicationTask] | None = None,
) -> dict[str, Any]:
    """Live isolation, named drift, and SPOF verdicts for mixed MCP+absorbed goals."""

    mcp_tasks = list(tasks) if tasks is not None else load_mcp_composition_tasks()
    mcp_ids = [task.id for task in mcp_tasks]
    pairs = load_persisted_mcp_bridge_records()
    absorbed_tasks = load_absorbed_composition_tasks()
    absorbed_pairs = load_persisted_bridge_records()
    base = run_goal_watchdog()
    live = _watch_mcp(mcp_tasks) if mcp_tasks else {
        "ok": False,
        "drifted_goals": [],
        "goal_results": [],
        "goal_count": 0,
        "healthy_count": 0,
    }
    isolation = all(
        record.get("id") not in mcp_ids for record in (base.get("goal_results") or [])
    ) and bool(mcp_ids)

    drift_by_mcp: dict[str, list[str]] = {}
    drift_by_bridge: dict[str, list[str]] = {}
    drift_by_producer: dict[str, list[str]] = {}
    base_unaffected: list[bool] = []
    mcp_unaffected_by_base: list[bool] = []
    absorbed_unaffected: list[bool] = []
    mcp_unaffected_by_absorbed: list[bool] = []
    mcp_hop_spof: dict[str, bool] = {}
    bridge_spof: dict[str, bool] = {}
    ledger = load_ledger(default_ledger_path(REPO_ROOT))
    pipeline = mixed_watch_registry(ledger)
    base_ids = {task.id for task in APPLICATION_TASKS}
    absorbed_ids = [task.id for task in absorbed_tasks]
    expected_ids = sorted(mcp_ids)

    for pair in pairs:
        mcp_id = str(pair.get("consumer_id") or "")
        bridge_id = str(pair.get("bridge_id") or "")
        producer_id = str(pair.get("producer_id") or "")
        if not mcp_id or not mcp_tasks:
            continue
        hidden_mcp = _watch_mcp(mcp_tasks, hide=[mcp_id])
        drift_by_mcp[mcp_id] = list(hidden_mcp.get("drifted_goals") or [])
        if bridge_id:
            hidden_bridge = _watch_mcp(mcp_tasks, hide=[bridge_id])
            drift_by_bridge[bridge_id] = list(hidden_bridge.get("drifted_goals") or [])
        if producer_id:
            red_producer = _replace_capability_fields(
                _clone_ledger(ledger),
                producer_id,
                last_proof_exit_code=1,
                last_proved_at="",
            )
            producer_drift = _watch_mcp(mcp_tasks, ledger=red_producer)
            drift_by_producer[producer_id] = list(producer_drift.get("drifted_goals") or [])
        base_hidden = run_goal_watchdog(hide=[mcp_id])
        base_unaffected.append(bool(base_hidden.get("ok")))
        routing_hidden = _watch_mcp(mcp_tasks, hide=["domain.tool-routing"])
        mcp_unaffected_by_base.append(bool(routing_hidden.get("ok")))
        if absorbed_tasks:
            absorbed_hidden = run_goal_watchdog(
                tasks=absorbed_tasks,
                include_absorbed=True,
                hide=[mcp_id],
            )
            absorbed_unaffected.append(bool(absorbed_hidden.get("ok")))
        reduced_mcp = {key: step for key, step in pipeline.items() if key != mcp_id}
        for task in mcp_tasks:
            if task.id.startswith("mcp-compose-"):
                mcp_hop_spof[task.id] = plan_application_task(task, reduced_mcp) is None
        if bridge_id:
            reduced_bridge = {key: step for key, step in pipeline.items() if key != bridge_id}
            for task in mcp_tasks:
                if task.id.startswith("mcp-compose-"):
                    bridge_spof[task.id] = plan_application_task(task, reduced_bridge) is None

    for pair in absorbed_pairs:
        absorbed_bridge = str(pair.get("bridge_id") or "")
        if not absorbed_bridge or not mcp_tasks:
            continue
        mcp_hidden_absorbed = _watch_mcp(mcp_tasks, hide=[absorbed_bridge])
        mcp_unaffected_by_absorbed.append(bool(mcp_hidden_absorbed.get("ok")))

    verdicts = {
        "has_mcp_goals": bool(mcp_ids),
        "base_watchdog_healthy": bool(base.get("ok")),
        "base_isolation": isolation,
        "live_mcp_healthy": bool(live.get("ok")) and bool(mcp_ids),
        "mcp_hide_named_drift": bool(drift_by_mcp)
        and all(sorted(names) == expected_ids for names in drift_by_mcp.values()),
        "bridge_hide_named_drift": bool(drift_by_bridge)
        and all(sorted(names) == expected_ids for names in drift_by_bridge.values()),
        "producer_red_named_drift": bool(drift_by_producer)
        and all(sorted(names) == expected_ids for names in drift_by_producer.values()),
        "base_unaffected_by_mcp_hide": bool(base_unaffected) and all(base_unaffected),
        "mcp_unaffected_by_base_hide": bool(mcp_unaffected_by_base) and all(mcp_unaffected_by_base),
        "absorbed_unaffected_by_mcp_hide": bool(absorbed_unaffected) and all(absorbed_unaffected),
        "mcp_unaffected_by_absorbed_hide": bool(mcp_unaffected_by_absorbed)
        and all(mcp_unaffected_by_absorbed),
        "mcp_hop_is_spof": bool(mcp_hop_spof) and all(mcp_hop_spof.values()),
        "bridge_is_spof": bool(bridge_spof) and all(bridge_spof.values()),
        "no_base_goal_in_mcp_watch": all(
            record.get("id") not in base_ids for record in (live.get("goal_results") or [])
        ),
        "no_absorbed_goal_in_mcp_watch": all(
            record.get("id") not in absorbed_ids for record in (live.get("goal_results") or [])
        ),
    }
    return {
        "mcp_ids": mcp_ids,
        "absorbed_ids": absorbed_ids,
        "base_goal_ids": sorted(record.get("id") for record in (base.get("goal_results") or [])),
        "live": {
            "ok": bool(live.get("ok")),
            "goal_count": live.get("goal_count"),
            "healthy_count": live.get("healthy_count"),
            "drifted_goals": list(live.get("drifted_goals") or []),
            "plans": {
                str(record.get("id")): list(record.get("plan") or [])
                for record in (live.get("goal_results") or [])
            },
        },
        "drift_by_mcp": drift_by_mcp,
        "drift_by_bridge": drift_by_bridge,
        "drift_by_producer": drift_by_producer,
        "mcp_hop_spof": mcp_hop_spof,
        "bridge_spof": bridge_spof,
        "verdicts": verdicts,
        "ok": all(verdicts.values()) and not legacy_pipeline_was_used(),
    }


def run_mcp_reliability_plane(output_dir: Path | None = None) -> dict[str, Any]:
    """Prove isolation + named MCP-hop drift, seal a report, and persist the live artifact."""

    honesty = compute_reliability_verdicts()
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": "capability_mcp_reliability",
        "generated_at": utc_now_iso(),
        "mcp_ids": honesty["mcp_ids"],
        "absorbed_ids": honesty["absorbed_ids"],
        "base_goal_ids": honesty["base_goal_ids"],
        "live": honesty["live"],
        "drift_by_mcp": honesty["drift_by_mcp"],
        "drift_by_bridge": honesty["drift_by_bridge"],
        "drift_by_producer": honesty["drift_by_producer"],
        "mcp_hop_spof": honesty["mcp_hop_spof"],
        "bridge_spof": honesty["bridge_spof"],
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
        "live": honesty["live"],
        "used_skill_route_discovery": report["used_skill_route_discovery"],
    }


def verify_mcp_reliability_report(report_dir: Path) -> dict[str, Any]:
    """Recompute live verdicts and re-check the sealed digest."""

    report_path = durable_read_path(report_dir / "report.json")
    if not report_path.is_file():
        return {"ok": False, "error": f"missing report.json in {report_dir}"}
    report = json.loads(report_path.read_text(encoding="utf-8"))
    honesty = compute_reliability_verdicts()
    recomputed = {
        "schema_version": SCHEMA_VERSION,
        "kind": "capability_mcp_reliability",
        "mcp_ids": honesty["mcp_ids"],
        "absorbed_ids": honesty["absorbed_ids"],
        "base_goal_ids": honesty["base_goal_ids"],
        "live": honesty["live"],
        "drift_by_mcp": honesty["drift_by_mcp"],
        "drift_by_bridge": honesty["drift_by_bridge"],
        "drift_by_producer": honesty["drift_by_producer"],
        "mcp_hop_spof": honesty["mcp_hop_spof"],
        "bridge_spof": honesty["bridge_spof"],
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
        "mcp_ids_match": honesty["mcp_ids"] == list(report.get("mcp_ids") or []),
        "no_skill_route": not legacy_pipeline_was_used(),
    }
    return {"ok": all(checks.values()), "checks": checks, "report_digest": report.get("report_digest")}


def mcp_reliability_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.capability_mcp_reliability import "
        "builtin_mcp_reliability_proof; "
        "r=builtin_mcp_reliability_proof(); "
        "assert r['ok'] and r.get('verdicts',{}).get('base_isolation') "
        "and r.get('verdicts',{}).get('live_mcp_healthy') "
        "and r.get('verdicts',{}).get('mcp_hide_named_drift') "
        "and r.get('verdicts',{}).get('producer_red_named_drift') "
        "and r.get('verdicts',{}).get('mcp_hop_is_spof') "
        "and r.get('verify_ok') and r.get('tamper_detected') "
        "and r.get('misgrade_detected') and not r.get('used_skill_route_discovery')\""
    )


def ensure_mcp_reliability_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the plane on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=MCP_RELIABILITY_ID,
        name="MCP mixed-composition reliability plane",
        description=(
            "Watches mixed MCP+absorbed goals the base watchdog cannot see: "
            "a hidden live MCP hop is named drift, the hop is a SPOF for its "
            "pipeline, and base-plane pre-growth semantics stay intact."
        ),
        kind="python",
        entry="blackhole_agent.capability_mcp_reliability:builtin_mcp_reliability_proof",
        proof_command=mcp_reliability_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "capability.goal-watchdog",
            MCP_APPLICATION_BRIDGE_ID,
        ),
        behavior_paths=(
            "src/blackhole_agent/capability_mcp_reliability.py",
            "src/blackhole_agent/capability_watchdog.py",
            "src/blackhole_agent/capability_application.py",
            "src/blackhole_agent/capability_mcp_application.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "Mixed MCP+absorbed goals are reliability-visible: hiding the "
            "live MCP hop is named drift, the hop is a SPOF, and a broken "
            "Python→MCP pipeline can no longer ship as a healthy stack."
        ),
        tags=("mcp", "absorbed", "reliability", "watchdog", "drift", "composition"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_mcp_reliability_proof() -> dict[str, Any]:
    """Registered proof: isolation, named MCP-hop drift, SPOF, seal, tamper, misgrade."""

    with tempfile.TemporaryDirectory(prefix="blackhole-mcp-reliability-") as tmp:
        report_dir = Path(tmp) / "report"
        result = run_mcp_reliability_plane(report_dir)
        if not result.get("ok"):
            return {**result, "verify_ok": False, "tamper_detected": False, "misgrade_detected": False}
        verification = verify_mcp_reliability_report(report_dir)
        report_path = report_dir / "report.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        tampered = json.loads(json.dumps(report))
        tampered["verdicts"]["mcp_hide_named_drift"] = not tampered["verdicts"]["mcp_hide_named_drift"]
        atomic_write_json(report_path, tampered)
        tamper_failed = not verify_mcp_reliability_report(report_dir)["ok"]
        misgraded = json.loads(json.dumps(report))
        misgraded["grade"]["ok"] = not bool(misgraded["grade"]["ok"])
        atomic_write_json(report_path, misgraded)
        misgrade_failed = not verify_mcp_reliability_report(report_dir)["ok"]
        atomic_write_json(report_path, report)

        mcp_tasks = load_mcp_composition_tasks()
        watchdog_dir = Path(tmp) / "watchdog"
        live_watch = _watch_mcp(mcp_tasks)
        write_watchdog_report(live_watch, watchdog_dir)
        watchdog_verified = verify_watchdog_report(watchdog_dir)
        pairs = load_persisted_mcp_bridge_records()
        if pairs:
            drift = _watch_mcp(mcp_tasks, hide=[str(pairs[0].get("consumer_id") or "")])
            hidden = json.loads(json.dumps(drift))
            hidden["drifted_goals"] = []
            hidden["ok"] = True
            atomic_write_json(watchdog_dir / "report.json", hidden)
            drift_hiding_failed = not verify_watchdog_report(watchdog_dir)["ok"]
        else:
            drift_hiding_failed = False

    live = run_mcp_reliability_plane(DEFAULT_ARTIFACT_DIR)
    ok = (
        bool(result["ok"])
        and bool(verification.get("ok"))
        and tamper_failed
        and misgrade_failed
        and bool(watchdog_verified.get("ok"))
        and drift_hiding_failed
        and bool(live.get("ok"))
        and not legacy_pipeline_was_used()
    )
    if ok:
        ensure_mcp_reliability_capability()
    return {
        **result,
        "ok": ok,
        "verify_ok": bool(verification.get("ok")),
        "tamper_detected": tamper_failed,
        "misgrade_detected": misgrade_failed,
        "watchdog_verify_ok": bool(watchdog_verified.get("ok")),
        "drift_hiding_detected": drift_hiding_failed,
        "action": "mcp_reliability_plane",
        "live_report_dir": str(DEFAULT_ARTIFACT_DIR),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }
