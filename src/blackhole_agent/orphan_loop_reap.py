"""Reap a durable continuous loop whose owner pid is gone.

A dead controller used to keep status=running_mission after the process
exited, so later wakes treated the orphan as still active. This module is
the first-class helper: a missing owner reports effective_status=orphaned
and reap_orphaned_loop clears status=running_mission without touching a
live owner pid. Later genesis can take continuous-loop reboot restoration.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from blackhole_agent.capability_compounder import (
    Capability,
    default_ledger_path,
    legacy_pipeline_was_used,
    load_ledger,
    register_capability,
    save_ledger,
    utc_now_iso,
)
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.loop_reboot_restore import (
    LOOP_REBOOT_RESTORE_DONE_WHEN,
    LOOP_REBOOT_RESTORE_GOAL,
    LOOP_REBOOT_RESTORE_ID,
    LOOP_REBOOT_RESTORE_LEFTOVER,
)

SCHEMA_VERSION = 1
ORPHAN_LOOP_REAP_ID = "capability.orphan-loop-reap"
ORPHAN_LOOP_REAP_DONE_WHEN = (
    "A durable continuous-loop state whose owner pid is gone reports "
    "effective_status=orphaned and a reap helper clears status=running_mission "
    "without touching a live owner pid."
)
ORPHAN_LOOP_REAP_GOAL = (
    "Repair orphaned continuous-loop reaping: a dead controller pid cannot keep "
    "status=running_mission after the process is gone, so later wakes treat an "
    "orphaned loop as still active."
)
ORPHAN_LOOP_REAP_LEFTOVER = (
    "Later genesis can take orphaned continuous-loop reaping so a dead "
    "controller pid cannot keep status=running_mission after the process is gone."
)
ACTIVE_LOOP_STATUSES = frozenset(
    {
        "starting",
        "running",
        "creating_mission",
        "running_mission",
        "publishing",
        "sleeping",
        "sleeping_publish_retry",
        "sleeping_mission_create_retry",
    }
)
REPO_ROOT = Path(__file__).resolve().parents[2]


def annotate_loop_status(payload: dict[str, Any]) -> dict[str, Any]:
    """Read-only liveness annotation; durable 'running' is not a health verdict.

    A live PID still needs command-line/parent-tree verification by the operator.
    A missing PID is sufficient evidence to reject an active durable status.
    """

    from blackhole_agent.unbound import (
        continuous_loop_owner_pid,
        pid_is_running,
        utc_now_iso as loop_now,
    )

    error = ""
    try:
        owner_pid = continuous_loop_owner_pid(payload.get("pid"))
        alive: bool | None = pid_is_running(owner_pid)
    except (OSError, ValueError) as exc:
        alive = None
        error = f"loop owner PID liveness unavailable: {exc}"
    active = str(payload.get("status") or "") in ACTIVE_LOOP_STATUSES
    effective_status = payload.get("status")
    if active and alive is False:
        effective_status = "orphaned"
        error = "durable loop owner PID is missing"
    elif active and alive is None:
        effective_status = "unknown"
    return {
        **payload,
        "pid_alive": alive,
        "checked_at": loop_now(),
        "effective_status": effective_status,
        "liveness_error": error,
    }


def reap_orphaned_loop(repo_path: Path, output_dir: Path | None = None) -> dict[str, Any]:
    """Persist a dead controller's orphaned state without changing its mission.

    Re-read both state and PID lock under the controller's OS guard so concurrent
    status calls and a successor controller cannot overwrite each other's state.
    Unknown liveness and live owners are never evidence for reaping.
    """

    from blackhole_agent.unbound import (
        DEFAULT_OUTPUT_DIR,
        append_jsonl,
        continuous_loop_events_path,
        continuous_loop_guard,
        continuous_loop_lock_path,
        continuous_loop_owner_pid,
        continuous_loop_state_path,
        pid_is_running,
        save_continuous_loop_state,
        utc_now_iso as loop_now,
    )

    output = DEFAULT_OUTPUT_DIR if output_dir is None else output_dir
    state_path = continuous_loop_state_path(repo_path, output)
    lock_path = continuous_loop_lock_path(repo_path, output)

    def snapshot() -> dict[str, Any]:
        return annotate_loop_status(json.loads(state_path.read_text(encoding="utf-8")))

    current = snapshot()
    if current["effective_status"] != "orphaned" or current.get("status") == "orphaned":
        return current
    try:
        with continuous_loop_guard(lock_path):
            payload = json.loads(state_path.read_text(encoding="utf-8"))
            current = annotate_loop_status(payload)
            if current["effective_status"] != "orphaned" or payload.get("status") == "orphaned":
                return current
            if lock_path.exists():
                lock_pid = continuous_loop_owner_pid(lock_path.read_text(encoding="utf-8").strip())
                if pid_is_running(lock_pid):
                    return {
                        **current,
                        "reaping_error": f"continuous loop PID lock has a live owner: {lock_pid}",
                    }
            at = loop_now()
            previous_status = payload["status"]
            payload.update(
                status="orphaned",
                orphaned_from_status=previous_status,
                reaped_at=at,
                reaped_by_pid=os.getpid(),
                stop_reason="controller_process_missing",
                next_wake_at="",
            )
            save_continuous_loop_state(state_path, payload)
            append_jsonl(
                continuous_loop_events_path(repo_path, output),
                {
                    "event": "continuous_loop.orphaned",
                    "at": at,
                    "loop_id": payload.get("loop_id", ""),
                    "pid": payload["pid"],
                    "previous_status": previous_status,
                    "current_mission_id": payload.get("current_mission_id", ""),
                    "current_state_path": payload.get("current_state_path", ""),
                    "reaped_by_pid": os.getpid(),
                    "reason": "controller_process_missing",
                },
            )
            lock_path.unlink(missing_ok=True)
            return annotate_loop_status(payload)
    except (OSError, ValueError, RuntimeError) as exc:
        return {**snapshot(), "reaping_error": str(exc)}


def orphan_loop_reap_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.orphan_loop_reap import "
        "builtin_orphan_loop_reap_proof; r=builtin_orphan_loop_reap_proof(); "
        "assert r['ok'] and r.get('action')=='orphan_loop_reap' "
        "and r.get('passed_count',0) >= 8 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_orphan_loop_reap_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the reaper on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=ORPHAN_LOOP_REAP_ID,
        name="Orphaned continuous-loop reaping",
        description=(
            "A durable continuous loop whose owner pid is gone reports "
            "effective_status=orphaned, and reap_orphaned_loop clears "
            "status=running_mission without rewriting a live owner pid."
        ),
        kind="python",
        entry="blackhole_agent.orphan_loop_reap:builtin_orphan_loop_reap_proof",
        proof_command=orphan_loop_reap_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.leftover-handoff-rebind",
        ),
        behavior_paths=(
            "src/blackhole_agent/orphan_loop_reap.py",
            "src/blackhole_agent/unbound.py",
            "src/blackhole_agent/loop_reboot_restore.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A dead controller pid cannot keep status=running_mission: the "
            "reap helper reports effective_status=orphaned and clears the "
            "durable status without touching a live owner pid."
        ),
        tags=("continuous-loop", "orphan", "reap", "liveness"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def _seed_loop(repo: Path, *, status: str, pid: int, lock: str | None) -> Path:
    from blackhole_agent.unbound import (
        continuous_loop_lock_path,
        continuous_loop_state_path,
        save_continuous_loop_state,
    )

    path = continuous_loop_state_path(repo)
    save_continuous_loop_state(
        path,
        {
            "loop_id": "orphan-reap-proof",
            "status": status,
            "pid": pid,
            "current_mission_id": "unfinished",
            "current_state_path": "mission.json",
            "next_wake_at": "tomorrow",
            "last_error": "preserve diagnostic",
        },
    )
    if lock is not None:
        continuous_loop_lock_path(repo).write_text(lock, encoding="utf-8")
    return path


def builtin_orphan_loop_reap_proof() -> dict[str, Any]:
    """Hermetic proof: dead owner is orphaned and reaped; live owner is left alone."""

    from blackhole_agent.evolution_quality import behavior_family
    from blackhole_agent.kernel_genesis_diversify import DIVERSITY_CATALOG
    from blackhole_agent.kernel_leftover import leftover_marker_ids
    from blackhole_agent.leftover_handoff_rebind import LEFTOVER_HANDOFF_REBIND_ID
    from blackhole_agent.unbound import (
        continuous_loop_lock_path,
        pid_is_running,
    )

    checks: dict[str, bool] = {}
    checks["denylists_self"] = ORPHAN_LOOP_REAP_ID in LOCAL_DENYLIST
    checks["denylists_next_family"] = LOOP_REBOOT_RESTORE_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(ORPHAN_LOOP_REAP_GOAL) == (
        ORPHAN_LOOP_REAP_ID,
    )
    checks["leftover_text_binds_next_family"] = leftover_marker_ids(
        LOOP_REBOOT_RESTORE_LEFTOVER
    ) == (LOOP_REBOOT_RESTORE_ID,)
    checks["next_family_goal_is_reboot_restore"] = leftover_marker_ids(
        LOOP_REBOOT_RESTORE_GOAL
    ) == (LOOP_REBOOT_RESTORE_ID,)
    checks["prior_family_markers_stay"] = leftover_marker_ids(ORPHAN_LOOP_REAP_LEFTOVER) == (
        ORPHAN_LOOP_REAP_ID,
    )
    catalog = DIVERSITY_CATALOG
    checks["catalog_names_orphan_reap"] = (
        len(catalog) > 240
        and catalog[240]["id"] == ORPHAN_LOOP_REAP_ID
        and catalog[240]["goal"] == ORPHAN_LOOP_REAP_GOAL
        and catalog[240]["done_when"] == ORPHAN_LOOP_REAP_DONE_WHEN
        and catalog[240]["source"] == "genesis_bind_orphan_loop"
    )
    checks["catalog_names_reboot_restore"] = (
        len(catalog) > 241
        and catalog[241]["id"] == LOOP_REBOOT_RESTORE_ID
        and catalog[241]["goal"] == LOOP_REBOOT_RESTORE_GOAL
        and catalog[241]["source"] == "genesis_bind_loop_reboot"
    )
    checks["rebind_stays_ahead"] = (
        len(catalog) > 239 and catalog[239]["id"] == LEFTOVER_HANDOFF_REBIND_ID
    )

    dead_pid = 1_000_003
    while pid_is_running(dead_pid):
        dead_pid += 2
    live_pid = os.getpid()

    with tempfile.TemporaryDirectory(prefix="orphan-loop-reap-dead-") as tmp:
        repo = Path(tmp)
        path = _seed_loop(repo, status="running_mission", pid=dead_pid, lock=f"{dead_pid}\n")
        original = path.read_bytes()
        shown = annotate_loop_status(json.loads(path.read_text(encoding="utf-8")))
        annotation_is_read_only = path.read_bytes() == original
        reaped = reap_orphaned_loop(repo)
        persisted = json.loads(path.read_text(encoding="utf-8"))
        checks["dead_owner_effective_orphaned"] = (
            shown.get("effective_status") == "orphaned"
            and shown.get("status") == "running_mission"
            and shown.get("pid_alive") is False
            and annotation_is_read_only
        )
        checks["reap_clears_running_mission"] = (
            reaped.get("status") == "orphaned"
            and reaped.get("effective_status") == "orphaned"
            and persisted.get("status") == "orphaned"
            and persisted.get("orphaned_from_status") == "running_mission"
            and persisted.get("pid") == dead_pid
            and persisted.get("last_error") == "preserve diagnostic"
            and persisted.get("next_wake_at") == ""
            and not continuous_loop_lock_path(repo).exists()
        )

    with tempfile.TemporaryDirectory(prefix="orphan-loop-reap-live-") as tmp:
        repo = Path(tmp)
        path = _seed_loop(repo, status="running_mission", pid=live_pid, lock=f"{live_pid}\n")
        before = path.read_bytes()
        shown = annotate_loop_status(json.loads(path.read_text(encoding="utf-8")))
        result = reap_orphaned_loop(repo)
        checks["live_owner_untouched"] = (
            shown.get("effective_status") == "running_mission"
            and shown.get("pid_alive") is True
            and result.get("status") == "running_mission"
            and result.get("effective_status") == "running_mission"
            and path.read_bytes() == before
            and continuous_loop_lock_path(repo).read_text(encoding="utf-8") == f"{live_pid}\n"
        )

    checks["next_family_is_not_handshake"] = (
        behavior_family(LOOP_REBOOT_RESTORE_GOAL) != "network/handshake-digest-demo"
        and LOOP_REBOOT_RESTORE_DONE_WHEN != ""
    )
    checks["contract_is_outcome_level"] = (
        "capability_exists:" not in ORPHAN_LOOP_REAP_DONE_WHEN
        and "capability_proved:" not in ORPHAN_LOOP_REAP_DONE_WHEN
    )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_orphan_loop_reap_capability()
    return {
        "ok": ok,
        "action": "orphan_loop_reap",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": ORPHAN_LOOP_REAP_GOAL,
        "done_when": ORPHAN_LOOP_REAP_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
