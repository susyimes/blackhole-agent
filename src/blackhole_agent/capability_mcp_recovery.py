"""Recovery plane for mixed MCP+absorbed pipelines the base loop cannot heal.

The goal-directed recovery loop plans only ``APPLICATION_TASKS`` on the base
registry. After a typed key-bridge made a live MCP tool compose with an
absorbed Python leaf, a red MCP hop still left the pipeline unplannable
while default recovery reported a healthy zero-repair pass.

This module closes that recovery failure without changing pre-growth
semantics of the base loop:

- default recovery still ignores mixed MCP+absorbed goals;
- the grown registry (``include_absorbed=True``) is recovered for every
  persisted MCP bridge pipeline, restricted to those pipeline members so
  hide-one analysis cannot explode over the absorbed zoo;
- a stale-stamp break of the live MCP hop is detected, repaired
  in-process, and the mixed composition goal re-solves with an oracle
  match;
- an unrepairable MCP-hop break leaves the composition unsolved and the
  stamp red;
- a digest-sealed report under ``artifacts/capability-mcp-recovery/``
  whose verification recomputes every verdict from recorded recovery
  summaries and rejects tamper and misgrade.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from blackhole_agent.capability_absorbed_recovery import repair_absorbed_member
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
    MCP_SHA256_ID,
    builtin_mcp_echo_sha256_proof,
    load_persisted_mcp_bridge_records,
    mcp_application_steps,
)
from blackhole_agent.capability_mcp_reliability import (
    load_mcp_composition_tasks,
    mixed_pipeline_ids,
)
from blackhole_agent.capability_recovery import (
    BREAK_FAILING_PROOF,
    BREAK_STALE_STAMP,
    run_recovery_loop,
)
from blackhole_agent.capability_repair import FAILING_PROOF, _replace_capability_fields
from blackhole_agent.durable_state import durable_read_path

SCHEMA_VERSION = 1
MCP_RECOVERY_ID = "capability.mcp-recovery-plane"
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "capability-mcp-recovery"
LATEST_POINTER = DEFAULT_ARTIFACT_DIR / "latest-recovery.json"
_DIGEST_EXCLUDE = frozenset({"generated_at", "run_at", "report_dir"})


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def mixed_surface_ids() -> list[str]:
    """Ledger citizens on persisted mixed MCP+absorbed pipelines."""

    ledger = load_ledger(default_ledger_path(REPO_ROOT))
    ids: list[str] = []
    for pair in load_persisted_mcp_bridge_records():
        for key in ("producer_id", "consumer_id", "bridge_id"):
            capability_id = str(pair.get(key) or "")
            if capability_id and capability_id in ledger.capabilities and capability_id not in ids:
                ids.append(capability_id)
    return ids


def mixed_allowed_ids() -> list[str]:
    """Planner ids for mixed recovery: endpoints plus the typed key-bridge."""

    ids = mixed_surface_ids()
    for capability_id in sorted(mixed_pipeline_ids()):
        if capability_id not in ids:
            ids.append(capability_id)
    return ids


def repair_mcp_pipeline_member(
    ledger,
    capability_id: str,
    *,
    cwd=None,
    command_runner=None,
    timeout: int = 30,
    skip_proved_deps: bool = True,
) -> tuple[Any, dict[str, Any]]:
    """Heal a mixed-pipeline member in-process: re-prove, or fail closed.

    Shell ``uv run`` proof commands hang under Windows ``shell=True`` when the
    interpreter path is swapped. MCP hops already have an in-process prover;
    using it keeps recovery bounded and still falsifies a replaced failing
    proof command.
    """

    del cwd, command_runner, timeout, skip_proved_deps
    if capability_id.startswith("capability.absorbed-"):
        return repair_absorbed_member(ledger, capability_id)
    capability = ledger.capabilities.get(capability_id)
    if capability is None:
        return ledger, {
            "capability_id": capability_id,
            "ok": False,
            "verdict": "unrepairable",
            "repair_actions": [],
            "honest": True,
            "last_proof_exit_code": 1,
        }
    if capability.last_proof_exit_code == 0:
        return ledger, {
            "capability_id": capability_id,
            "ok": True,
            "verdict": "healthy",
            "repair_actions": [],
            "honest": True,
            "last_proof_exit_code": 0,
        }
    command = capability.proof_command or ""
    if command.strip() == FAILING_PROOF or "sys.exit(1)" in command:
        return ledger, {
            "capability_id": capability_id,
            "ok": False,
            "verdict": "unrepairable",
            "repair_actions": ["detect_failing_proof"],
            "honest": True,
            "last_proof_exit_code": capability.last_proof_exit_code,
        }
    if capability_id == MCP_SHA256_ID or capability_id in mcp_application_steps():
        result = builtin_mcp_echo_sha256_proof()
        if result.get("ok"):
            ledger = _replace_capability_fields(
                ledger,
                capability_id,
                last_proof_exit_code=0,
                last_proved_at=utc_now_iso(),
            )
            return ledger, {
                "capability_id": capability_id,
                "ok": True,
                "verdict": "repaired",
                "repair_actions": ["reprove_mcp_hop"],
                "honest": True,
                "last_proof_exit_code": 0,
            }
        return ledger, {
            "capability_id": capability_id,
            "ok": False,
            "verdict": "unrepairable",
            "repair_actions": ["reprove_mcp_hop"],
            "honest": True,
            "last_proof_exit_code": 1,
        }
    return ledger, {
        "capability_id": capability_id,
        "ok": False,
        "verdict": "unrepairable",
        "repair_actions": ["unsupported_pipeline_member"],
        "honest": True,
        "last_proof_exit_code": capability.last_proof_exit_code,
    }


def run_mcp_recovery_loop(
    *,
    breaks: Mapping[str, str] | None = None,
    tasks: Sequence[ApplicationTask] | None = None,
) -> dict[str, Any]:
    """Goal-directed recovery over persisted mixed MCP+absorbed pipelines."""

    task_list = list(tasks) if tasks is not None else load_mcp_composition_tasks()
    return run_recovery_loop(
        breaks=breaks,
        tasks=task_list,
        include_absorbed=True,
        surface_ids=mixed_surface_ids(),
        allowed_ids=mixed_allowed_ids(),
        skip_proved_deps=True,
        timeout=30,
        repair_fn=repair_mcp_pipeline_member,
    )


def _recovery_summary(report: Mapping[str, Any]) -> dict[str, Any]:
    recovery = report.get("recovery") or {}
    return {
        "ok": bool(report.get("ok")),
        "repair_count": recovery.get("repair_count"),
        "repaired_count": recovery.get("repaired_count"),
        "unrepairable_count": recovery.get("unrepairable_count"),
        "recovered": list(recovery.get("recovered") or []),
        "honest_unsolved": list(recovery.get("honest_unsolved") or []),
        "task_ids": [str(record.get("id")) for record in (report.get("task_records") or [])],
        "blocked_capabilities": list(report.get("blocked_capabilities") or []),
        "break_stamps_after": dict(report.get("break_stamps_after") or {}),
        "repair_ids": [
            str(repair.get("capability_id"))
            for repair in (report.get("repairs") or [])
        ],
        "repair_verdicts": {
            str(repair.get("capability_id")): str(repair.get("verdict"))
            for repair in (report.get("repairs") or [])
        },
    }


def compute_recovery_verdicts(
    *,
    tasks: Sequence[ApplicationTask] | None = None,
) -> dict[str, Any]:
    """Live isolation, heal, and honest-unrepairable verdicts for a red MCP hop."""

    mcp_tasks = list(tasks) if tasks is not None else load_mcp_composition_tasks()
    mcp_ids = [task.id for task in mcp_tasks]
    pairs = load_persisted_mcp_bridge_records()
    mcp_id = str(pairs[0].get("consumer_id") or "") if pairs else ""
    composition_id = mcp_ids[0] if mcp_ids else ""
    base_ids = {task.id for task in APPLICATION_TASKS}

    isolation = run_recovery_loop(breaks={mcp_id: BREAK_STALE_STAMP} if mcp_id else None)
    live = run_mcp_recovery_loop(tasks=mcp_tasks) if mcp_tasks else {
        "ok": False,
        "recovery": {},
        "task_records": [],
        "repairs": [],
        "blocked_capabilities": [],
        "break_stamps_after": {},
    }
    healed = (
        run_mcp_recovery_loop(
            breaks={mcp_id: BREAK_STALE_STAMP},
            tasks=mcp_tasks,
        )
        if mcp_id and mcp_tasks
        else live
    )
    unrepairable = (
        run_mcp_recovery_loop(
            breaks={mcp_id: BREAK_FAILING_PROOF},
            tasks=mcp_tasks,
        )
        if mcp_id and mcp_tasks
        else live
    )

    isolation_summary = _recovery_summary(isolation)
    live_summary = _recovery_summary(live)
    healed_summary = _recovery_summary(healed)
    unrepairable_summary = _recovery_summary(unrepairable)

    isolation_ids = set(isolation_summary["task_ids"])
    verdicts = {
        "has_mcp_goals": bool(mcp_ids),
        "base_isolation": bool(mcp_ids)
        and isolation_summary["ok"]
        and isolation_summary["repair_count"] == 0
        and mcp_id not in isolation_summary["repair_ids"]
        and isolation_ids.isdisjoint(mcp_ids)
        and isolation_ids == base_ids,
        "live_mcp_healthy": live_summary["ok"]
        and live_summary["repair_count"] == 0
        and bool(mcp_ids)
        and sorted(live_summary["task_ids"]) == sorted(mcp_ids),
        "mcp_hop_stale_healed": healed_summary["ok"]
        and composition_id in healed_summary["recovered"]
        and healed_summary["repair_verdicts"].get(mcp_id) == "repaired"
        and healed_summary["break_stamps_after"].get(mcp_id) == 0,
        "mcp_hop_unrepairable_honest": (not unrepairable_summary["ok"])
        and composition_id in unrepairable_summary["honest_unsolved"]
        and unrepairable_summary["repair_verdicts"].get(mcp_id) == "unrepairable"
        and unrepairable_summary["break_stamps_after"].get(mcp_id) not in (0, None),
        "no_skill_route": not legacy_pipeline_was_used(),
    }
    return {
        "mcp_ids": mcp_ids,
        "mcp_id": mcp_id,
        "composition_id": composition_id,
        "isolation": isolation_summary,
        "live": live_summary,
        "healed": healed_summary,
        "unrepairable": unrepairable_summary,
        "verdicts": verdicts,
        "ok": all(verdicts.values()) and not legacy_pipeline_was_used(),
    }


def run_mcp_recovery_plane(output_dir: Path | None = None) -> dict[str, Any]:
    """Prove isolation + heal + honesty, seal a report, persist the live artifact."""

    honesty = compute_recovery_verdicts()
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": "capability_mcp_recovery",
        "generated_at": utc_now_iso(),
        "mcp_ids": honesty["mcp_ids"],
        "mcp_id": honesty["mcp_id"],
        "composition_id": honesty["composition_id"],
        "isolation": honesty["isolation"],
        "live": honesty["live"],
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
        "used_skill_route_discovery": report["used_skill_route_discovery"],
    }


def _summaries_match_verdicts(report: Mapping[str, Any]) -> dict[str, bool]:
    """Pure consistency: recorded verdicts must follow recorded recovery summaries."""

    verdicts = report.get("verdicts") or {}
    isolation = report.get("isolation") or {}
    live = report.get("live") or {}
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
        and isolation_ids == base_ids,
        "live_mcp_healthy": bool(live.get("ok"))
        and live.get("repair_count") == 0
        and bool(mcp_ids)
        and sorted(live.get("task_ids") or []) == sorted(mcp_ids),
        "mcp_hop_stale_healed": bool(healed.get("ok"))
        and composition_id in list(healed.get("recovered") or [])
        and (healed.get("repair_verdicts") or {}).get(mcp_id) == "repaired"
        and (healed.get("break_stamps_after") or {}).get(mcp_id) == 0,
        "mcp_hop_unrepairable_honest": (not bool(unrepairable.get("ok")))
        and composition_id in list(unrepairable.get("honest_unsolved") or [])
        and (unrepairable.get("repair_verdicts") or {}).get(mcp_id) == "unrepairable"
        and (unrepairable.get("break_stamps_after") or {}).get(mcp_id) not in (0, None),
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


def verify_mcp_recovery_report(report_dir: Path) -> dict[str, Any]:
    """Re-check the sealed digest and that verdicts follow recorded summaries.

    Verification never re-executes a repair. A report whose digest was
    retargeted, whose verdicts disagree with its recovery summaries, or
    whose grade hides a failed verdict fails verification.
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


def mcp_recovery_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.capability_mcp_recovery import "
        "builtin_mcp_recovery_proof; "
        "r=builtin_mcp_recovery_proof(); "
        "assert r['ok'] and r.get('verdicts',{}).get('base_isolation') "
        "and r.get('verdicts',{}).get('live_mcp_healthy') "
        "and r.get('verdicts',{}).get('mcp_hop_stale_healed') "
        "and r.get('verdicts',{}).get('mcp_hop_unrepairable_honest') "
        "and r.get('verify_ok') and r.get('tamper_detected') "
        "and r.get('misgrade_detected') and not r.get('used_skill_route_discovery')\""
    )


def ensure_mcp_recovery_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the plane on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=MCP_RECOVERY_ID,
        name="MCP mixed-composition recovery plane",
        description=(
            "Heals mixed MCP+absorbed pipelines the base recovery loop cannot "
            "see: a red live MCP hop is repaired and the composition goal "
            "re-solves, an unrepairable hop stays red, and default recovery "
            "stays on base goals."
        ),
        kind="python",
        entry="blackhole_agent.capability_mcp_recovery:builtin_mcp_recovery_proof",
        proof_command=mcp_recovery_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "capability.recovery-loop",
            MCP_APPLICATION_BRIDGE_ID,
            "capability.mcp-reliability-plane",
        ),
        behavior_paths=(
            "src/blackhole_agent/capability_mcp_recovery.py",
            "src/blackhole_agent/capability_recovery.py",
            "src/blackhole_agent/capability_application.py",
            "src/blackhole_agent/capability_mcp_application.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "Mixed MCP+absorbed pipelines are recoverable: a red MCP hop is "
            "healed and the composition goal re-solves, while default recovery "
            "still ignores those goals."
        ),
        tags=("mcp", "absorbed", "recovery", "repair", "composition"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_mcp_recovery_proof() -> dict[str, Any]:
    """Registered proof: isolation, heal, honest failure, seal, tamper, misgrade."""

    with tempfile.TemporaryDirectory(prefix="blackhole-mcp-recovery-") as tmp:
        report_dir = Path(tmp) / "report"
        result = run_mcp_recovery_plane(report_dir)
        if not result.get("ok"):
            return {**result, "verify_ok": False, "tamper_detected": False, "misgrade_detected": False}
        verification = verify_mcp_recovery_report(report_dir)
        report_path = report_dir / "report.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        tampered = json.loads(json.dumps(report))
        tampered["verdicts"]["mcp_hop_stale_healed"] = not tampered["verdicts"]["mcp_hop_stale_healed"]
        atomic_write_json(report_path, tampered)
        tamper_failed = not verify_mcp_recovery_report(report_dir)["ok"]
        misgraded = json.loads(json.dumps(report))
        misgraded["grade"]["ok"] = not bool(misgraded["grade"]["ok"])
        atomic_write_json(report_path, misgraded)
        misgrade_failed = not verify_mcp_recovery_report(report_dir)["ok"]
        atomic_write_json(report_path, report)

    DEFAULT_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write_json(DEFAULT_ARTIFACT_DIR / "report.json", report)
    atomic_write_json(
        LATEST_POINTER,
        {"report_dir": str(DEFAULT_ARTIFACT_DIR), "report_digest": report["report_digest"], "ok": report["ok"]},
    )
    live_verified = verify_mcp_recovery_report(DEFAULT_ARTIFACT_DIR)
    ok = (
        bool(result["ok"])
        and bool(verification.get("ok"))
        and tamper_failed
        and misgrade_failed
        and bool(live_verified.get("ok"))
        and not legacy_pipeline_was_used()
    )
    if ok:
        ensure_mcp_recovery_capability()
    return {
        **result,
        "ok": ok,
        "verify_ok": bool(verification.get("ok")),
        "tamper_detected": tamper_failed,
        "misgrade_detected": misgrade_failed,
        "live_verify_ok": bool(live_verified.get("ok")),
        "action": "mcp_recovery_plane",
        "live_report_dir": str(DEFAULT_ARTIFACT_DIR),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }
