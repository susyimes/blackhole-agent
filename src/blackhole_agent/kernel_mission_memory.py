"""Replay harvested operational classes from durable memory at the next genesis.

Experience fuel reads ``state.json`` fields and ``recent_turns``. A harvested
class that lives only in a completed mission's ``turns/*/turn.json`` (empty
``recent_turns``, generic next_step, no last_error) never enters that surface.
``ingest_unbound_turn`` writes the pattern register, but harvest only promotes
forced rows after three recurrences, so a single completed-turn class is
forgotten. The next genesis then invents instead of replaying the failure.

This module closes that hole:

- scan completed-mission turn artifacts, not only ``recent_turns``
- persist harvested operational classes into durable mission memory
- recall those classes at the next genesis even after the mission directory
  is gone
- bind the recalled class instead of a catalog invention
- keep structurally closed classes out of fuel
"""

from __future__ import annotations

import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from blackhole_agent.capability_compounder import (
    Capability,
    default_ledger_path,
    legacy_pipeline_was_used,
    load_ledger,
    register_capability,
    save_ledger,
    utc_now_iso,
)
from blackhole_agent.experience_fuel import ExperienceCandidate, leftover_next_step
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST

SCHEMA_VERSION = 1
MISSION_MEMORY_ID = "capability.kernel-mission-memory"
MEMORY_RELATIVE = Path(".blackhole-agent") / "unbound" / "mission-memory.json"
REPO_ROOT = Path(__file__).resolve().parents[2]
KERNEL_TURN_FAILED = "kernel_turn_failed"
_SKIP_MEMORY_CLASSES = frozenset({"", "mission_leftover"})
_SALVAGE_CLASSES = frozenset({"quota_exhausted", "auth_failed"})

MISSION_MEMORY_DONE_WHEN = (
    f"capability_exists:{MISSION_MEMORY_ID};"
    f"capability_proved:{MISSION_MEMORY_ID};"
    "no_skill_route"
)
MISSION_MEMORY_GOAL = (
    "Repair mission-memory recall: a harvested operational class recorded only "
    "inside a completed mission turn never reaches the next genesis, so the same "
    "failure is re-invented instead of replayed from durable memory."
)

HARVESTED_ERROR_TURN = {
    "iteration": 13,
    "effective_status": "error",
    "error": (
        "Grok CLI failed with exit code 1; result details were written to "
        "grok-run-20260816T055123Z.json"
    ),
    "summary": "turn 13 failed before a structured decision",
    "finished_at": "2026-08-16T05:51:28Z",
}

HARVESTED_SUCCESS_TURN = {
    "iteration": 1,
    "effective_status": "complete",
    "summary": "Mission complete.",
    "next_step": "None. Mission complete.",
    "finished_at": "2026-08-30T00:00:00Z",
}


def mission_memory_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.kernel_mission_memory import "
        "builtin_kernel_mission_memory_proof; r=builtin_kernel_mission_memory_proof(); "
        "assert r['ok'] and r.get('action')=='kernel_mission_memory' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def memory_path(root: Path) -> Path:
    return Path(root) / MEMORY_RELATIVE


def load_mission_memory(root: Path) -> dict[str, Any]:
    path = memory_path(root)
    if not path.is_file():
        return {"schema_version": SCHEMA_VERSION, "updated_at": "", "classes": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"schema_version": SCHEMA_VERSION, "updated_at": "", "classes": {}}
    if not isinstance(payload, Mapping):
        return {"schema_version": SCHEMA_VERSION, "updated_at": "", "classes": {}}
    raw = payload.get("classes") if isinstance(payload.get("classes"), Mapping) else {}
    classes = {
        str(key): dict(value)
        for key, value in raw.items()
        if str(key).strip() and isinstance(value, Mapping)
    }
    return {
        "schema_version": int(payload.get("schema_version") or SCHEMA_VERSION),
        "updated_at": str(payload.get("updated_at") or ""),
        "classes": classes,
    }


def save_mission_memory(root: Path, payload: Mapping[str, Any]) -> Path:
    path = memory_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "schema_version": int(payload.get("schema_version") or SCHEMA_VERSION),
        "updated_at": _utc_now(),
        "classes": dict(payload.get("classes") or {}),
    }
    path.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def events_from_turn(record: Mapping[str, Any] | None) -> list[dict[str, str]]:
    """Shape one turn record into operational-class events."""

    from blackhole_agent.pattern_register import classify_unbound_turn

    turn = dict(record or {})
    events: list[dict[str, str]] = []
    salvage = turn.get("kernel_salvage") if isinstance(turn.get("kernel_salvage"), Mapping) else {}
    salvage_class = str(salvage.get("class_id") or "")
    if salvage_class in _SALVAGE_CLASSES:
        events.append(
            {
                "class_id": salvage_class,
                "source": "unbound-salvage",
                "summary": f"salvaged {salvage_class} without stalling",
                "evidence": str(salvage.get("evidence") or salvage.get("source") or "")[:400],
                "at": str(turn.get("finished_at") or turn.get("started_at") or ""),
            }
        )
    for event in classify_unbound_turn(turn):
        class_id = str(event.get("class_id") or "")
        if class_id in _SKIP_MEMORY_CLASSES:
            continue
        events.append(
            {
                "class_id": class_id,
                "source": str(event.get("source") or "unbound"),
                "summary": str(event.get("summary") or ""),
                "evidence": str(event.get("evidence") or "")[:400],
                "at": str(event.get("at") or ""),
            }
        )
    return events


def iter_turn_records(state_path: Path, state: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    """Yield persisted turns, including artifacts omitted from ``recent_turns``."""

    payload = dict(state or {})
    if not payload:
        payload = _read_json(Path(state_path))
    records: list[dict[str, Any]] = []
    seen_iterations: set[Any] = set()
    for turn in list(payload.get("recent_turns") or []):
        if not isinstance(turn, dict):
            continue
        records.append(turn)
        iteration = turn.get("iteration")
        if iteration is not None:
            seen_iterations.add(iteration)
    turns_dir = Path(state_path).parent / "turns"
    if not turns_dir.is_dir():
        return records
    for path in sorted(turns_dir.glob("*/turn.json")):
        turn = _read_json(path)
        if not turn:
            continue
        iteration = turn.get("iteration")
        if iteration is not None and iteration in seen_iterations:
            continue
        records.append(turn)
        if iteration is not None:
            seen_iterations.add(iteration)
    return records


def harvest_state_surface_classes(state: Mapping[str, Any] | None) -> tuple[str, ...]:
    """Classes the pre-memory harvest could see from ``state.json`` alone."""

    from blackhole_agent.pattern_register import blocked_class_id, classify_unbound_turn

    payload = dict(state or {})
    classes: list[str] = []
    if payload.get("last_error"):
        classes.append(KERNEL_TURN_FAILED)
    if payload.get("status") == "blocked":
        classes.append(blocked_class_id(payload))
    if leftover_next_step(str(payload.get("next_step") or "")):
        classes.append("mission_leftover")
    for turn in list(payload.get("recent_turns") or []):
        if not isinstance(turn, dict):
            continue
        salvage = turn.get("kernel_salvage") if isinstance(turn.get("kernel_salvage"), Mapping) else {}
        salvage_class = str(salvage.get("class_id") or "")
        if salvage_class in _SALVAGE_CLASSES:
            classes.append(salvage_class)
        for event in classify_unbound_turn(turn):
            class_id = str(event.get("class_id") or "")
            if class_id:
                classes.append(class_id)
    return tuple(dict.fromkeys(item for item in classes if item))


def remember_events(
    root: Path,
    events: list[dict[str, str]],
    *,
    source_mission_id: str = "",
) -> int:
    """Persist harvested operational classes into durable mission memory."""

    if not events:
        return 0
    payload = load_mission_memory(root)
    classes = dict(payload.get("classes") or {})
    written = 0
    now = _utc_now()
    for event in events:
        class_id = str(event.get("class_id") or "").strip()
        if class_id in _SKIP_MEMORY_CLASSES:
            continue
        existing = classes.get(class_id) if isinstance(classes.get(class_id), Mapping) else {}
        stamp = str(event.get("at") or "") or now
        classes[class_id] = {
            "class_id": class_id,
            "count": int(existing.get("count") or 0) + 1,
            "evidence": str(event.get("evidence") or existing.get("evidence") or "")[:400],
            "first_seen": str(existing.get("first_seen") or stamp),
            "last_seen": stamp,
            "source": str(event.get("source") or existing.get("source") or "unbound"),
            "source_mission_id": str(
                source_mission_id or existing.get("source_mission_id") or ""
            ),
            "summary": str(event.get("summary") or existing.get("summary") or "")[:400],
        }
        written += 1
    if not written:
        return 0
    payload["classes"] = classes
    save_mission_memory(root, payload)
    return written


def remember_turn_record(
    root: Path,
    record: Mapping[str, Any] | None,
    *,
    source_mission_id: str = "",
) -> int:
    return remember_events(
        Path(root),
        events_from_turn(record),
        source_mission_id=source_mission_id,
    )


def remember_completed_mission_turns(
    root: Path,
    *,
    state_path: Path | None = None,
    state: Mapping[str, Any] | None = None,
) -> int:
    """Backfill durable memory from one mission, or every mission under ``root``."""

    written = 0
    if state_path is not None:
        mission_id = str((state or {}).get("mission_id") or Path(state_path).parent.name)
        for turn in iter_turn_records(Path(state_path), state):
            written += remember_turn_record(root, turn, source_mission_id=mission_id)
        return written
    missions_dir = Path(root) / ".blackhole-agent" / "unbound" / "missions"
    if not missions_dir.is_dir():
        return 0
    for path in missions_dir.glob("*/state.json"):
        payload = _read_json(path)
        written += remember_completed_mission_turns(root, state_path=path, state=payload)
    return written


def recall_open_classes(
    root: Path,
    *,
    lineage_ref: str = "",
) -> list[ExperienceCandidate]:
    """Return durable-memory classes that are still structurally open."""

    try:
        from blackhole_agent.kernel_class_closure import class_is_closed
    except Exception:  # noqa: BLE001 - recall must still surface unknown classes

        def class_is_closed(class_id: str, repo: Path, **kwargs: Any) -> bool:
            return False

    candidates: list[ExperienceCandidate] = []
    payload = load_mission_memory(root)
    for class_id, row in sorted((payload.get("classes") or {}).items()):
        if not isinstance(row, Mapping):
            continue
        if class_id in _SKIP_MEMORY_CLASSES:
            continue
        if class_is_closed(class_id, Path(root), lineage_ref=lineage_ref):
            continue
        candidates.append(
            ExperienceCandidate(
                source="mission-memory",
                class_id=class_id,
                summary=str(row.get("summary") or class_id),
                evidence=str(row.get("evidence") or "")[:400],
                priority=4,
                forced=False,
            )
        )
    return candidates


def ensure_kernel_mission_memory_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=MISSION_MEMORY_ID,
        name="Kernel mission-memory recall",
        description=(
            "A harvested operational class recorded only inside a completed "
            "mission turn is persisted to durable memory and recalled at the "
            "next genesis instead of being re-invented. Closed classes stay out "
            "of fuel."
        ),
        kind="python",
        entry="blackhole_agent.kernel_mission_memory:builtin_kernel_mission_memory_proof",
        proof_command=mission_memory_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.kernel-class-closure",
            "capability.kernel-genesis-diversify",
        ),
        behavior_paths=(
            "src/blackhole_agent/kernel_mission_memory.py",
            "src/blackhole_agent/experience_fuel.py",
            "src/blackhole_agent/pattern_register.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "Harvested operational classes recorded only in a completed mission "
            "turn reach the next genesis from durable memory instead of being "
            "re-invented; structurally closed classes still drop from fuel."
        ),
        tags=("genesis", "memory", "harvest", "recall", "kernel"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def _write_turn_only_mission(
    root: Path,
    *,
    mission_id: str,
    turn: Mapping[str, Any],
    status: str = "complete",
) -> Path:
    mission_dir = Path(root) / ".blackhole-agent" / "unbound" / "missions" / mission_id
    turn_dir = mission_dir / "turns" / "0013"
    turn_dir.mkdir(parents=True, exist_ok=True)
    (turn_dir / "turn.json").write_text(json.dumps(dict(turn), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    state_path = mission_dir / "state.json"
    state_path.write_text(
        json.dumps(
            {
                "mission_id": mission_id,
                "status": status,
                "stage": "execution",
                "goal": "Close leftover contract-materializer cliff.",
                "done_when": "",
                "next_step": "None. Mission complete.",
                "last_summary": "Mission completed after a later recovery.",
                "last_error": "",
                "milestones": [],
                "recent_turns": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return state_path


def _register_closers(root: Path, ids: tuple[str, ...]) -> Path:
    from blackhole_agent.capability_compounder import CapabilityLedger

    path = default_ledger_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    ledger = load_ledger(path) if path.is_file() else CapabilityLedger()
    for capability_id in ids:
        register_capability(
            ledger,
            Capability(
                id=capability_id,
                name=capability_id,
                description="Proved structural closer for a harvested operational class.",
                kind="python",
                entry="blackhole_agent.local_capability_kernel:builtin_fixture_probe",
                proof_command="uv run python -c \"print('ok')\"",
                last_proof_exit_code=0,
            ),
            replace=True,
        )
    save_ledger(path, ledger)
    return path


def builtin_kernel_mission_memory_proof() -> dict[str, Any]:
    """Hermetic proof: a turn-only harvested class is replayed from durable memory."""

    from blackhole_agent.experience_fuel import harvest_experience
    from blackhole_agent.kernel_class_closure import CLASS_CLOSURE_REQUIREMENTS, class_is_closed
    from blackhole_agent.kernel_genesis_bind import (
        KERNEL_GENESIS_BIND_GOAL,
        _State,
        _consumed_campaign,
        bind_gate_passing_successor,
    )
    from blackhole_agent.local_capability_kernel import _write_fixture_ledger
    from blackhole_agent.local_mission_sovereignty import (
        HARVESTED_KERNEL_FAILURE_DONE_WHEN,
        HARVESTED_KERNEL_FAILURE_GOAL,
        bind_local_mission,
        save_campaign,
    )
    from blackhole_agent.pattern_register import classify_unbound_turn, ingest_unbound_turn

    checks: dict[str, bool] = {}
    checks["denylists_self"] = MISSION_MEMORY_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(MISSION_MEMORY_GOAL) == (MISSION_MEMORY_ID,)
    classified = classify_unbound_turn(HARVESTED_ERROR_TURN)
    checks["harvested_turn_is_kernel_turn_failed"] = any(
        item.get("class_id") == KERNEL_TURN_FAILED for item in classified
    )
    checks["success_turn_is_not_a_class"] = classify_unbound_turn(HARVESTED_SUCCESS_TURN) == []

    with tempfile.TemporaryDirectory(prefix="kernel-mission-memory-hole-") as tmp:
        root = Path(tmp)
        state_path = _write_turn_only_mission(root, mission_id="prior-complete", turn=HARVESTED_ERROR_TURN)
        state = _read_json(state_path)
        surface = harvest_state_surface_classes(state)
        artifact_events = events_from_turn(HARVESTED_ERROR_TURN)
        fuel = harvest_experience(root, limit=5)
        binding = bind_local_mission(_State(root), harvest=True)
    checks["state_surface_misses_turn_only_class"] = KERNEL_TURN_FAILED not in surface
    checks["turn_artifact_has_class"] = any(
        item.get("class_id") == KERNEL_TURN_FAILED for item in artifact_events
    )
    checks["harvest_recalls_turn_only_class"] = any(
        item.class_id == KERNEL_TURN_FAILED for item in fuel.candidates
    )
    checks["local_bind_replays_recalled_class"] = (
        binding.goal == HARVESTED_KERNEL_FAILURE_GOAL
        and HARVESTED_KERNEL_FAILURE_DONE_WHEN in binding.done_when
        and ("experience/" in binding.source or "mission-memory" in binding.source)
    )

    with tempfile.TemporaryDirectory(prefix="kernel-mission-memory-durable-") as tmp:
        root = Path(tmp)
        ingest_unbound_turn(root, HARVESTED_ERROR_TURN)
        recalled = recall_open_classes(root)
        fuel_before = harvest_experience(root, limit=5)
        mission_dir = root / ".blackhole-agent" / "unbound" / "missions"
        if mission_dir.exists():
            shutil.rmtree(mission_dir)
        fuel_after = harvest_experience(root, limit=5)
        binding = bind_local_mission(_State(root), harvest=True)
    checks["ingest_persists_turn_into_memory"] = any(
        item.class_id == KERNEL_TURN_FAILED for item in recalled
    )
    checks["harvest_without_mission_dir_still_recalls"] = any(
        item.class_id == KERNEL_TURN_FAILED for item in fuel_before.candidates
    ) and any(item.class_id == KERNEL_TURN_FAILED for item in fuel_after.candidates)
    checks["bind_replays_after_mission_dir_gone"] = (
        binding.goal == HARVESTED_KERNEL_FAILURE_GOAL
        and HARVESTED_KERNEL_FAILURE_DONE_WHEN in binding.done_when
        and ("mission-memory" in binding.source or "experience/" in binding.source)
    )

    with tempfile.TemporaryDirectory(prefix="kernel-mission-memory-bind-") as tmp:
        root = Path(tmp)
        _write_fixture_ledger(root)
        save_campaign(root, _consumed_campaign())
        _write_turn_only_mission(root, mission_id="prior-complete", turn=HARVESTED_ERROR_TURN)
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["genesis_bind_replays_instead_of_inventing"] = (
        live_goal == HARVESTED_KERNEL_FAILURE_GOAL
        and HARVESTED_KERNEL_FAILURE_DONE_WHEN in live_done
        and str(live_source).startswith("experience/")
        and live_goal != KERNEL_GENESIS_BIND_GOAL
    )

    with tempfile.TemporaryDirectory(prefix="kernel-mission-memory-closed-") as tmp:
        root = Path(tmp)
        _write_turn_only_mission(root, mission_id="prior-complete", turn=HARVESTED_ERROR_TURN)
        remember_completed_mission_turns(root)
        _register_closers(root, CLASS_CLOSURE_REQUIREMENTS[KERNEL_TURN_FAILED])
        closed = class_is_closed(KERNEL_TURN_FAILED, root)
        closed_fuel = harvest_experience(root, limit=5)
        closed_recall = recall_open_classes(root)
    checks["closed_class_does_not_replay"] = (
        closed is True
        and not any(item.class_id == KERNEL_TURN_FAILED for item in closed_fuel.candidates)
        and not any(item.class_id == KERNEL_TURN_FAILED for item in closed_recall)
    )

    with tempfile.TemporaryDirectory(prefix="kernel-mission-memory-success-") as tmp:
        root = Path(tmp)
        _write_turn_only_mission(root, mission_id="prior-success", turn=HARVESTED_SUCCESS_TURN)
        remember_completed_mission_turns(root)
        success_fuel = harvest_experience(root, limit=5)
        success_memory = load_mission_memory(root)
    checks["success_turn_is_not_remembered"] = KERNEL_TURN_FAILED not in (
        success_memory.get("classes") or {}
    ) and not any(item.class_id == KERNEL_TURN_FAILED for item in success_fuel.candidates)

    kept = bind_local_mission(_State(Path("."), goal="Operator growth goal."), harvest=False)
    checks["preserves_operator_goal"] = kept.goal == "Operator growth goal."
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_kernel_mission_memory_capability()
    return {
        "ok": ok,
        "action": "kernel_mission_memory",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": MISSION_MEMORY_GOAL,
        "done_when": MISSION_MEMORY_DONE_WHEN,
    }
