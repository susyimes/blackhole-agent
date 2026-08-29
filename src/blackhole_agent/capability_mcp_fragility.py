"""Fragility plane for mixed MCP+absorbed pipelines the base audit cannot score.

The goal fragility audit, recovery priority, and stack-health plane plan
only over ``APPLICATION_TASKS`` on the base registry. After a typed
key-bridge made a live MCP tool compose with an absorbed Python leaf, that
mixed hop was still invisible to hide-one blast radius: a SPOF that
recovery should heal first never entered the impact matrix.

This module closes that scoring failure without changing pre-growth
semantics of the base audit:

- default fragility results still omit mixed MCP+absorbed goals and keep
  the base score (robust ``ledger-inventory-check``, max blast 2);
- the grown mixed-pipeline registry is scored for every persisted MCP
  bridge, restricted to those members so hide-one analysis cannot explode
  over the absorbed zoo;
- hiding the live MCP hop, the typed key-bridge, or the absorbed producer
  names the mixed composition goal in blast radius and as a SPOF;
- a digest-sealed report under ``artifacts/capability-mcp-fragility/``
  whose verification recomputes the mixed matrix from the live ledger and
  rejects tamper and misgrade.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any, Sequence

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
from blackhole_agent.capability_mcp_application import (
    MCP_APPLICATION_BRIDGE_ID,
    load_persisted_mcp_bridge_records,
)
from blackhole_agent.capability_mcp_reliability import (
    load_mcp_composition_tasks,
    mixed_watch_registry,
)
from blackhole_agent.durable_state import durable_read_path

SCHEMA_VERSION = 1
MCP_FRAGILITY_ID = "capability.mcp-fragility-plane"
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "capability-mcp-fragility"
LATEST_POINTER = DEFAULT_ARTIFACT_DIR / "latest-fragility.json"
_DIGEST_EXCLUDE = frozenset({"generated_at", "run_at", "report_dir"})


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def run_mcp_fragility_audit(
    *,
    tasks: Sequence[ApplicationTask] | None = None,
    ledger=None,
) -> dict[str, Any]:
    """Hide-one impact matrix over persisted mixed MCP+absorbed pipelines."""

    active = ledger if ledger is not None else load_ledger(default_ledger_path(REPO_ROOT))
    task_list = list(tasks) if tasks is not None else load_mcp_composition_tasks()
    registry = mixed_watch_registry(active)
    matrix = compute_impact_matrix(active, tasks=task_list, registry=registry)
    depth = compute_redundancy_depth(active, tasks=task_list, registry=registry)
    grade = compute_fragility_grade(matrix, tasks=task_list, depth=depth)
    matrix_digest = _digest(matrix)
    depth_digest = _digest(depth)
    grade_digest = _digest(grade)
    report_digest = hashlib.sha256(
        f"mcp-fragility:{matrix_digest}:{depth_digest}:{grade_digest}".encode("utf-8")
    ).hexdigest()
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "capability_mcp_fragility",
        "run_at": utc_now_iso(),
        "task_ids": [task.id for task in task_list],
        "surface_ids": sorted(registry),
        "impact_matrix": matrix,
        "redundancy_depth": depth,
        "fragility": grade,
        "matrix_digest": matrix_digest,
        "depth_digest": depth_digest,
        "grade_digest": grade_digest,
        "report_digest": report_digest,
        "ok": bool(task_list) and bool(registry),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }


def compute_fragility_verdicts(
    *,
    tasks: Sequence[ApplicationTask] | None = None,
) -> dict[str, Any]:
    """Live isolation plus mixed-pipeline blast-radius and SPOF verdicts."""

    mcp_tasks = list(tasks) if tasks is not None else load_mcp_composition_tasks()
    mcp_ids = [task.id for task in mcp_tasks]
    pairs = load_persisted_mcp_bridge_records()
    mcp_id = str(pairs[0].get("consumer_id") or "") if pairs else ""
    bridge_id = str(pairs[0].get("bridge_id") or "") if pairs else ""
    producer_id = str(pairs[0].get("producer_id") or "") if pairs else ""
    composition_id = mcp_ids[0] if mcp_ids else ""
    base_ids = {task.id for task in APPLICATION_TASKS}

    base = run_fragility_audit()
    mixed = run_mcp_fragility_audit(tasks=mcp_tasks) if mcp_tasks else {
        "ok": False,
        "task_ids": [],
        "surface_ids": [],
        "impact_matrix": {},
        "fragility": {},
        "redundancy_depth": {},
    }
    base_grade = base.get("fragility") or {}
    mixed_grade = mixed.get("fragility") or {}
    mixed_blast = dict(mixed_grade.get("blast_radius") or {})
    mixed_spofs = dict(mixed_grade.get("spofs_per_goal") or {})
    base_blast = dict(base_grade.get("blast_radius") or {})
    base_matrix = base.get("impact_matrix") or {}
    mixed_matrix = mixed.get("impact_matrix") or {}

    def _blocks(capability_id: str) -> list[str]:
        return list(mixed_matrix.get(capability_id) or [])

    verdicts = {
        "has_mcp_goals": bool(mcp_ids),
        "base_isolation": bool(mcp_ids)
        and mcp_id not in base_blast
        and composition_id not in {
            goal
            for blocked in base_matrix.values()
            for goal in blocked
        }
        and base_grade.get("fragility_score") == 0.1667
        and base_grade.get("robust_goals") == ["ledger-inventory-check"]
        and base_grade.get("max_blast_radius") == 2,
        "mcp_hop_blast_named": bool(mcp_id)
        and mixed_blast.get(mcp_id) == 1
        and _blocks(mcp_id) == [composition_id],
        "bridge_blast_named": bool(bridge_id)
        and mixed_blast.get(bridge_id) == 1
        and _blocks(bridge_id) == [composition_id],
        "producer_blast_named": bool(producer_id)
        and mixed_blast.get(producer_id) == 1
        and _blocks(producer_id) == [composition_id],
        "mcp_hop_is_spof": bool(composition_id)
        and mcp_id in list(mixed_spofs.get(composition_id) or []),
        "bridge_is_spof": bool(composition_id)
        and bridge_id in list(mixed_spofs.get(composition_id) or []),
        "mixed_goal_fragile": mixed_grade.get("fragile_goals") == mcp_ids
        and mixed_grade.get("robust_goals") == []
        and mixed_grade.get("fragility_score") == 0.0
        and mixed_grade.get("max_blast_radius") == 1,
        "no_base_goal_in_mcp_audit": all(
            goal_id not in base_ids
            for goal_id in (mixed_grade.get("spofs_per_goal") or {})
        ),
        "no_skill_route": not legacy_pipeline_was_used(),
    }
    return {
        "mcp_ids": mcp_ids,
        "mcp_id": mcp_id,
        "bridge_id": bridge_id,
        "producer_id": producer_id,
        "composition_id": composition_id,
        "base": {
            "fragility_score": base_grade.get("fragility_score"),
            "max_blast_radius": base_grade.get("max_blast_radius"),
            "robust_goals": list(base_grade.get("robust_goals") or []),
        },
        "mixed": {
            "ok": bool(mixed.get("ok")),
            "task_ids": list(mixed.get("task_ids") or []),
            "surface_ids": list(mixed.get("surface_ids") or []),
            "blast_radius": mixed_blast,
            "spofs_per_goal": mixed_spofs,
            "fragility_score": mixed_grade.get("fragility_score"),
            "max_blast_radius": mixed_grade.get("max_blast_radius"),
            "fragile_goals": list(mixed_grade.get("fragile_goals") or []),
            "robust_goals": list(mixed_grade.get("robust_goals") or []),
            "impact_matrix": mixed_matrix,
            "redundancy_depth": mixed.get("redundancy_depth") or {},
            "matrix_digest": mixed.get("matrix_digest"),
            "depth_digest": mixed.get("depth_digest"),
            "grade_digest": mixed.get("grade_digest"),
            "report_digest": mixed.get("report_digest"),
        },
        "verdicts": verdicts,
        "ok": all(verdicts.values()) and not legacy_pipeline_was_used(),
    }


def run_mcp_fragility_plane(output_dir: Path | None = None) -> dict[str, Any]:
    """Prove isolation + MCP-hop blast radius, seal a report, persist the live artifact."""

    honesty = compute_fragility_verdicts()
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": "capability_mcp_fragility",
        "generated_at": utc_now_iso(),
        "mcp_ids": honesty["mcp_ids"],
        "mcp_id": honesty["mcp_id"],
        "bridge_id": honesty["bridge_id"],
        "producer_id": honesty["producer_id"],
        "composition_id": honesty["composition_id"],
        "base": honesty["base"],
        "mixed": honesty["mixed"],
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
        "mixed": honesty["mixed"],
        "used_skill_route_discovery": report["used_skill_route_discovery"],
    }


def verify_mcp_fragility_report(report_dir: Path) -> dict[str, Any]:
    """Recompute live mixed-pipeline verdicts and re-check the sealed digest."""

    report_path = durable_read_path(report_dir / "report.json")
    if not report_path.is_file():
        return {"ok": False, "error": f"missing report.json in {report_dir}"}
    report = json.loads(report_path.read_text(encoding="utf-8"))
    honesty = compute_fragility_verdicts()
    recomputed = {
        "schema_version": SCHEMA_VERSION,
        "kind": "capability_mcp_fragility",
        "mcp_ids": honesty["mcp_ids"],
        "mcp_id": honesty["mcp_id"],
        "bridge_id": honesty["bridge_id"],
        "producer_id": honesty["producer_id"],
        "composition_id": honesty["composition_id"],
        "base": honesty["base"],
        "mixed": honesty["mixed"],
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
        "mcp_hop_blast_match": (honesty["mixed"].get("blast_radius") or {}).get(honesty["mcp_id"])
        == ((report.get("mixed") or {}).get("blast_radius") or {}).get(report.get("mcp_id")),
        "no_skill_route": not legacy_pipeline_was_used(),
    }
    return {"ok": all(checks.values()), "checks": checks, "report_digest": report.get("report_digest")}


def mcp_fragility_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.capability_mcp_fragility import "
        "builtin_mcp_fragility_proof; "
        "r=builtin_mcp_fragility_proof(); "
        "assert r['ok'] and r.get('verdicts',{}).get('base_isolation') "
        "and r.get('verdicts',{}).get('mcp_hop_blast_named') "
        "and r.get('verdicts',{}).get('mcp_hop_is_spof') "
        "and r.get('verdicts',{}).get('mixed_goal_fragile') "
        "and r.get('verify_ok') and r.get('tamper_detected') "
        "and r.get('misgrade_detected') and not r.get('used_skill_route_discovery')\""
    )


def ensure_mcp_fragility_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the plane on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=MCP_FRAGILITY_ID,
        name="MCP mixed-composition fragility plane",
        description=(
            "Scores mixed MCP+absorbed pipelines the base fragility audit "
            "cannot see: a live MCP hop is a SPOF counted in blast radius, "
            "and base-audit pre-growth semantics stay intact."
        ),
        kind="python",
        entry="blackhole_agent.capability_mcp_fragility:builtin_mcp_fragility_proof",
        proof_command=mcp_fragility_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "capability.fragility-audit",
            MCP_APPLICATION_BRIDGE_ID,
        ),
        behavior_paths=(
            "src/blackhole_agent/capability_mcp_fragility.py",
            "src/blackhole_agent/capability_fragility.py",
            "src/blackhole_agent/capability_application.py",
            "src/blackhole_agent/capability_mcp_application.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "Mixed MCP+absorbed pipelines are fragility-visible: a live MCP "
            "hop is a SPOF counted in blast radius, while the base audit "
            "score and max blast stay unchanged."
        ),
        tags=("mcp", "absorbed", "fragility", "spof", "blast-radius", "composition"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_mcp_fragility_proof() -> dict[str, Any]:
    """Registered proof: isolation, MCP-hop blast, SPOF, seal, tamper, misgrade."""

    with tempfile.TemporaryDirectory(prefix="blackhole-mcp-fragility-") as tmp:
        report_dir = Path(tmp) / "report"
        result = run_mcp_fragility_plane(report_dir)
        if not result.get("ok"):
            return {**result, "verify_ok": False, "tamper_detected": False, "misgrade_detected": False}
        verification = verify_mcp_fragility_report(report_dir)
        report_path = report_dir / "report.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        tampered = json.loads(json.dumps(report))
        tampered["verdicts"]["mcp_hop_blast_named"] = not tampered["verdicts"]["mcp_hop_blast_named"]
        atomic_write_json(report_path, tampered)
        tamper_failed = not verify_mcp_fragility_report(report_dir)["ok"]
        misgraded = json.loads(json.dumps(report))
        misgraded["grade"]["ok"] = not bool(misgraded["grade"]["ok"])
        atomic_write_json(report_path, misgraded)
        misgrade_failed = not verify_mcp_fragility_report(report_dir)["ok"]
        atomic_write_json(report_path, report)

    live = run_mcp_fragility_plane(DEFAULT_ARTIFACT_DIR)
    ok = (
        bool(result["ok"])
        and bool(verification.get("ok"))
        and tamper_failed
        and misgrade_failed
        and bool(live.get("ok"))
        and not legacy_pipeline_was_used()
    )
    if ok:
        ensure_mcp_fragility_capability()
    return {
        **result,
        "ok": ok,
        "verify_ok": bool(verification.get("ok")),
        "tamper_detected": tamper_failed,
        "misgrade_detected": misgrade_failed,
        "action": "mcp_fragility_plane",
        "live_report_dir": str(DEFAULT_ARTIFACT_DIR),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }
