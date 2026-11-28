"""Retain failed-turn diagnostics for mission status and recall open classes at genesis."""

from __future__ import annotations

import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

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
from blackhole_agent.file_guard import atomic_write_json, file_guard
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST

SCHEMA_VERSION = 1
MISSION_MEMORY_ID = "capability.kernel-mission-memory"
MEMORY_RELATIVE = Path(".blackhole-agent") / "unbound" / "mission-memory.json"
REPO_ROOT = Path(__file__).resolve().parents[2]
KERNEL_TURN_FAILED = "kernel_turn_failed"
_SKIP_MEMORY_CLASSES = frozenset({"", "mission_leftover"})
_SALVAGE_CLASSES = frozenset({"quota_exhausted", "auth_failed"})
_UNKNOWN_TIME = datetime.min.replace(tzinfo=timezone.utc)

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


def memory_path(root: Path) -> Path:
    return Path(root) / MEMORY_RELATIVE


def _read_json(path: Path, *, strict: bool = False) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"Expected an object in {path}")
        return payload
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        if strict:
            raise
        return {}


def load_mission_memory(root: Path) -> dict[str, Any]:
    payload = _read_json(memory_path(root))
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


def _write_memory(path: Path, payload: Mapping[str, Any]) -> None:
    atomic_write_json(path, {
        "schema_version": int(payload.get("schema_version") or SCHEMA_VERSION),
        "updated_at": utc_now_iso(),
        "classes": dict(payload.get("classes") or {}),
    })


def save_mission_memory(root: Path, payload: Mapping[str, Any]) -> Path:
    path = memory_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with file_guard(path):
        _write_memory(path, payload)
    return path


def events_from_turn(record: Mapping[str, Any] | None) -> list[dict[str, str]]:
    """Shape one turn record into operational-class events."""

    from blackhole_agent.pattern_register import classify_unbound_turn

    turn = dict(record or {})
    events = classify_unbound_turn(turn)
    salvage = turn.get("kernel_salvage")
    if isinstance(salvage, Mapping) and salvage.get("class_id") in _SALVAGE_CLASSES:
        events.insert(0, {
            "class_id": salvage["class_id"], "source": "unbound-salvage",
            "summary": f"salvaged {salvage['class_id']} without stalling",
            "evidence": str(salvage.get("evidence") or salvage.get("source") or "")[:400],
            "at": str(turn.get("finished_at") or turn.get("started_at") or ""),
        })
    iteration = "" if turn.get("iteration") is None else str(turn["iteration"])
    return [dict(event, iteration=iteration) for event in events if event["class_id"] not in _SKIP_MEMORY_CLASSES]


def iter_turn_records(state_path: Path, state: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    """Include archived turns that aged out of the recent state window."""
    state_path = Path(state_path)
    payload = state or _read_json(state_path)
    records = [turn for turn in payload.get("recent_turns") or [] if isinstance(turn, dict)]
    seen_iterations = {turn["iteration"] for turn in records if turn.get("iteration") is not None}
    for path in sorted(state_path.parent.glob("turns/*/turn.json")):
        turn = _read_json(path)
        iteration = turn.get("iteration")
        if turn and iteration not in seen_iterations:
            records.append(turn)
            if iteration is not None:
                seen_iterations.add(iteration)
    return records


def harvest_state_surface_classes(state: Mapping[str, Any] | None) -> tuple[str, ...]:
    """Classes the pre-memory harvest could see from ``state.json`` alone."""

    from blackhole_agent.pattern_register import blocked_class_id

    payload = dict(state or {})
    classes: list[str] = []
    if payload.get("last_error"):
        classes.append(KERNEL_TURN_FAILED)
    if payload.get("status") == "blocked":
        classes.append(blocked_class_id(payload))
    if leftover_next_step(str(payload.get("next_step") or "")):
        classes.append("mission_leftover")
    for turn in payload.get("recent_turns") or []:
        if isinstance(turn, dict):
            classes.extend(event["class_id"] for event in events_from_turn(turn))
    return tuple(dict.fromkeys(item for item in classes if item))


def _instant(stamp: str) -> datetime:
    try:
        value = datetime.fromisoformat(str(stamp or "").replace("Z", "+00:00"))
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    except ValueError:
        return _UNKNOWN_TIME


def _restore_identities(row: dict[str, Any]) -> list[dict[str, Any]]:
    """Keep identified legacy turns as placeholders until their own journals supply evidence."""
    if "turns" not in row:
        known = {}
        for identity in row.pop("seen", None) or []:
            parts = str(identity).split("\n", 3)
            if len(parts) == 4:
                owner, iteration, class_id, summary = parts
                if owner and iteration and class_id == row["class_id"]:
                    known[owner, iteration] = dict(mission_id=owner, iteration=iteration, summary=summary, legacy=True)
        row["turns"] = list(known.values())
        remaining = int(row.get("count") or 0) - len(known)
        if row.get("last_seen"):
            row["legacy_through"] = row["last_seen"]
        if remaining > 0:
            row["legacy_unattributed"] = remaining
        if row.get("first_seen"):
            row["legacy_first_seen"] = row["first_seen"]
        row["source_mission_id"] = ""
    return row["turns"]


def _same_turn(old: dict[str, Any], new: dict[str, Any]) -> bool:
    if old["iteration"] != new["iteration"]:
        return False
    if old["mission_id"] and new["mission_id"]:
        if old["mission_id"] != new["mission_id"]:
            return False
        if new["iteration"]:
            return True
    # An unlabelled journal can establish an alias only for the same observed event.
    if any(old.get(key) != new[key] for key in ("source", "summary", "evidence")):
        return False
    stamp = _instant(new["at"])
    return old.get("at") == new["at"] or (stamp != _UNKNOWN_TIME and _instant(old.get("at", "")) == stamp)


def _time_of(turn: dict[str, str]) -> str:
    return turn["at"] or turn["recorded_at"]


def _turn_order(turn: dict[str, str]) -> tuple:
    iteration = turn["iteration"]
    return (_instant(_time_of(turn)), turn["mission_id"], int(iteration) if iteration.isdecimal() else -1,
            iteration, turn["summary"], turn["evidence"])


def _diagnostic_order(turn: dict[str, Any]) -> tuple:
    evidence = turn.get("evidence", "")
    return bool(evidence), _instant(turn.get("at", "")), len(evidence), evidence, turn.get("summary", "")


def _merge_turn(turns: list[dict[str, Any]], fact: dict[str, Any]) -> bool:
    matches = [old for old in turns if _same_turn(old, fact)]
    old = max(matches, key=lambda item: item["mission_id"] == fact["mission_id"], default=None)
    # A named replay may link a previously anonymous observation to a legacy placeholder.
    aliases = [item for item in matches if item is not old and not item["mission_id"]]
    if old:
        fact["mission_id"] = fact["mission_id"] or old["mission_id"]
        if "at" in old and _diagnostic_order(old) > _diagnostic_order(fact):
            fact = dict(old, mission_id=fact["mission_id"])
        if old.get("legacy"):
            fact["legacy"] = True
    if not fact["at"]:
        fact["recorded_at"] = (old or {}).get("recorded_at") or utc_now_iso()
    if fact == old and not aliases:
        return False
    for alias in aliases:
        turns.remove(alias)
    if old:
        old.clear()
        old.update(fact)
    else:
        turns.append(fact)
    return True


def _summarize(row: dict[str, Any]) -> None:
    observed = [turn for turn in row["turns"] if "at" in turn]
    through = _instant(row.get("legacy_through", ""))
    # Older aggregate-only counts are a floor. Backfill can replace anonymous counts
    # with identifiable evidence, but cannot reconstruct missing historical diagnostics.
    historical = sum(not turn.get("legacy") and (not turn["at"] or _instant(turn["at"]) <= through)
                     for turn in observed)
    row["count"] = len(row["turns"]) + max(0, row.get("legacy_unattributed", 0) - historical)
    stamps = [_time_of(turn) for turn in observed]
    if row.get("legacy_first_seen"):
        stamps.append(row["legacy_first_seen"])
    row["first_seen"] = min(stamps, key=_instant)
    latest = max(observed, key=_turn_order)
    if _instant(_time_of(latest)) >= through:
        row.update(last_seen=_time_of(latest), source_mission_id=latest["mission_id"],
                   source=latest["source"], summary=latest["summary"], evidence=latest["evidence"])


def _merge_events(classes: dict[str, Any], events: Iterable[dict[str, str]], owner: str) -> tuple[bool, int]:
    before = {}
    for event in events:
        class_id = str(event.get("class_id") or "").strip()
        if class_id in _SKIP_MEMORY_CLASSES:
            continue
        row = classes.setdefault(class_id, {})
        row["class_id"] = class_id
        fact = {
            "mission_id": owner,
            "iteration": "" if event.get("iteration") is None else str(event["iteration"]),
            "at": str(event.get("at") or ""),
            "source": str(event.get("source") or "unbound"),
            "summary": str(event.get("summary") or "")[:400],
            "evidence": str(event.get("evidence") or "")[:400],
        }
        if _merge_turn(_restore_identities(row), fact):
            before.setdefault(class_id, int(row.get("count") or 0))
    for class_id in before:
        _summarize(classes[class_id])
    added = sum(max(0, classes[class_id]["count"] - count) for class_id, count in before.items())
    return bool(before), added


def remember_events(root: Path, events: list[dict[str, str]], *, source_mission_id: str = "") -> int:
    """Persist harvested operational classes into durable mission memory."""

    if not events:
        return 0
    path = memory_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with file_guard(path):
        payload = _read_json(path, strict=True)
        changed, added = _merge_events(payload.setdefault("classes", {}), events, source_mission_id)
        if changed:
            _write_memory(path, payload)
        return added


def remember_turn_record(
    root: Path,
    record: Mapping[str, Any] | None,
    *,
    source_mission_id: str = "",
) -> int:
    owner = source_mission_id or str((record or {}).get("mission_id") or "")
    return remember_events(root, events_from_turn(record), source_mission_id=owner)


def remember_completed_mission_turns(
    root: Path,
    *,
    state_path: Path | None = None,
    state: Mapping[str, Any] | None = None,
) -> int:
    """Backfill durable memory from one mission, or every mission under ``root``."""

    if state_path is None:
        states = (memory_path(root).parent / "missions").glob("*/state.json")
        return sum(remember_completed_mission_turns(root, state_path=path) for path in states)
    state_path = Path(state_path)
    payload = state or _read_json(state_path)
    owner = str(payload.get("mission_id") or state_path.parent.name)
    events = [event for turn in iter_turn_records(state_path, payload) for event in events_from_turn(turn)]
    return remember_events(root, events, source_mission_id=owner)


def recall_open_classes(root: Path, *, lineage_ref: str = "") -> list[ExperienceCandidate]:
    """Return durable-memory classes that are still structurally open."""

    try:
        from blackhole_agent.kernel_class_closure import class_is_closed
    except Exception:  # noqa: BLE001 - recall must still surface unknown classes

        def class_is_closed(class_id: str, repo: Path, **kwargs: Any) -> bool:
            return False

    candidates: list[ExperienceCandidate] = []
    for class_id, row in sorted(load_mission_memory(root)["classes"].items()):
        if class_id in _SKIP_MEMORY_CLASSES or class_is_closed(class_id, Path(root), lineage_ref=lineage_ref):
            continue
        summary = str(row.get("summary") or class_id)
        if row.get("turns") and row.get("source_mission_id"):
            summary += f" (mission {row['source_mission_id']})"
        candidates.append(
            ExperienceCandidate(
                source="mission-memory",
                class_id=class_id,
                summary=summary,
                evidence=str(row.get("evidence") or "")[:400],
                priority=4,
                forced=False,
            )
        )
    return candidates


def mission_failures(root: Path, mission_id: str, records: Iterable[dict] = ()) -> list[dict[str, Any]]:
    """Return this mission's observed failures, including classes later closed at genesis."""
    classes = load_mission_memory(root)["classes"]
    # Status also works on pre-upgrade journals. Fold them into this read without changing the store.
    _merge_events(classes, (event for turn in records for event in events_from_turn(turn)), mission_id)
    found = [
        dict(turn, class_id=class_id)
        for class_id, row in classes.items()
        for turn in row.get("turns", ())
        if mission_id and turn["mission_id"] == mission_id and "evidence" in turn
    ]
    found.sort(key=_turn_order)
    for turn in found:
        turn.pop("legacy", None)
        if turn["iteration"].isdecimal():
            turn["iteration"] = int(turn["iteration"])
    return found


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


def _write_mission_fixture(
    root: Path,
    *,
    mission_id: str,
    turn: Mapping[str, Any],
    status: str = "complete",
    last_error: str = "",
    archived: bool = True,
) -> Path:
    mission_dir = memory_path(root).parent / "missions" / mission_id
    if archived:
        atomic_write_json(mission_dir / "turns" / f"{turn['iteration']:04d}" / "turn.json", dict(turn))
    state_path = mission_dir / "state.json"
    atomic_write_json(state_path, {
        "mission_id": mission_id, "status": status, "stage": "execution",
        "goal": "Close leftover contract-materializer cliff.", "done_when": "",
        "next_step": "None. Mission complete.", "last_summary": "Mission completed after a later recovery.",
        "last_error": last_error, "milestones": [], "recent_turns": [] if archived else [dict(turn)],
    })
    return state_path


def builtin_kernel_mission_memory_proof() -> dict[str, Any]:
    """Hermetic proof: a turn-only harvested class is replayed from durable memory."""

    from blackhole_agent.experience_fuel import harvest_experience
    from blackhole_agent.kernel_class_closure import CLASS_CLOSURE_REQUIREMENTS, _register_closers, class_is_closed
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
        LocalMissionBinding,
        bind_local_mission,
        save_campaign,
    )
    from blackhole_agent.pattern_register import classify_unbound_turn, ingest_unbound_turn

    def has_failure(candidates: Iterable[ExperienceCandidate]) -> bool:
        return any(item.class_id == KERNEL_TURN_FAILED for item in candidates)

    def binds_failure(binding: LocalMissionBinding) -> bool:
        return (binding.goal == HARVESTED_KERNEL_FAILURE_GOAL
                and HARVESTED_KERNEL_FAILURE_DONE_WHEN in binding.done_when
                and ("experience/" in binding.source or "mission-memory" in binding.source))

    checks: dict[str, bool] = {}
    checks["denylists_self"] = MISSION_MEMORY_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(MISSION_MEMORY_GOAL) == (MISSION_MEMORY_ID,)
    classified = classify_unbound_turn(HARVESTED_ERROR_TURN)
    checks["harvested_turn_is_kernel_turn_failed"] = any(event["class_id"] == KERNEL_TURN_FAILED for event in classified)
    checks["success_turn_is_not_a_class"] = classify_unbound_turn(HARVESTED_SUCCESS_TURN) == []

    with tempfile.TemporaryDirectory(prefix="kernel-mission-memory-hole-") as tmp:
        root = Path(tmp)
        state_path = _write_mission_fixture(root, mission_id="prior-complete", turn=HARVESTED_ERROR_TURN)
        surface = harvest_state_surface_classes(_read_json(state_path))
        checks["state_surface_misses_turn_only_class"] = KERNEL_TURN_FAILED not in surface
        events = events_from_turn(HARVESTED_ERROR_TURN)
        checks["turn_artifact_has_class"] = any(event["class_id"] == KERNEL_TURN_FAILED for event in events)
        checks["harvest_recalls_turn_only_class"] = has_failure(harvest_experience(root).candidates)
        checks["local_bind_replays_recalled_class"] = binds_failure(bind_local_mission(_State(root)))

    with tempfile.TemporaryDirectory(prefix="kernel-mission-memory-durable-") as tmp:
        root = Path(tmp)
        ingest_unbound_turn(root, HARVESTED_ERROR_TURN)
        checks["ingest_persists_turn_into_memory"] = has_failure(recall_open_classes(root))
        _write_mission_fixture(root, mission_id="prior-complete", turn=HARVESTED_ERROR_TURN)
        before = has_failure(harvest_experience(root).candidates)
        missions = (memory_path(root).parent / "missions").resolve()
        if not missions.is_relative_to(root.resolve()):
            raise ValueError("Mission fixture is outside its temporary directory")
        shutil.rmtree(missions)
        checks["harvest_without_mission_dir_still_recalls"] = before and has_failure(harvest_experience(root).candidates)
        checks["bind_replays_after_mission_dir_gone"] = binds_failure(bind_local_mission(_State(root)))

    with tempfile.TemporaryDirectory(prefix="kernel-mission-memory-bind-") as tmp:
        root = Path(tmp)
        _write_fixture_ledger(root)
        save_campaign(root, _consumed_campaign())
        _write_mission_fixture(root, mission_id="prior-complete", turn=HARVESTED_ERROR_TURN)
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["genesis_bind_replays_instead_of_inventing"] = (
        live_goal == HARVESTED_KERNEL_FAILURE_GOAL
        and HARVESTED_KERNEL_FAILURE_DONE_WHEN in live_done
        and str(live_source).startswith("experience/")
        and live_goal != KERNEL_GENESIS_BIND_GOAL
    )

    with tempfile.TemporaryDirectory(prefix="kernel-mission-memory-closed-") as tmp:
        root = Path(tmp)
        _write_mission_fixture(root, mission_id="prior-complete", turn=HARVESTED_ERROR_TURN)
        remember_completed_mission_turns(root)
        _register_closers(root, CLASS_CLOSURE_REQUIREMENTS[KERNEL_TURN_FAILED])
        closed = class_is_closed(KERNEL_TURN_FAILED, root)
        checks["closed_class_does_not_replay"] = (
            closed is True and not has_failure(harvest_experience(root).candidates)
            and not has_failure(recall_open_classes(root))
        )

    with tempfile.TemporaryDirectory(prefix="kernel-mission-memory-success-") as tmp:
        root = Path(tmp)
        _write_mission_fixture(root, mission_id="prior-success", turn=HARVESTED_SUCCESS_TURN)
        remember_completed_mission_turns(root)
        success_fuel = harvest_experience(root)
        checks["success_turn_is_not_remembered"] = (
            KERNEL_TURN_FAILED not in load_mission_memory(root)["classes"] and not has_failure(success_fuel.candidates)
        )

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
