"""Restore a reaped orphaned continuous loop after login or reboot.

Reaping leaves status=orphaned and clears the stale PID lock. A machine
restart then keeps the native loop stopped until an operator starts it.
This helper is the missing startup path: it starts a controller only when
no live owner pid exists, and it refuses to start a second controller
beside a live owner pid. Operator-stopped loops and unknown liveness are
left alone. Paused daily-health automation is never rewritten.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

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
from blackhole_agent.loop_login_task import (
    LOOP_LOGIN_TASK_DONE_WHEN,
    LOOP_LOGIN_TASK_GOAL,
    LOOP_LOGIN_TASK_ID,
    LOOP_LOGIN_TASK_LEFTOVER,
)

SCHEMA_VERSION = 1
LOOP_REBOOT_RESTORE_ID = "capability.loop-reboot-restore"
LOOP_REBOOT_RESTORE_DONE_WHEN = (
    "A reaped orphaned continuous-loop state is restored by a startup helper "
    "that starts only when no live owner pid exists and does not start a "
    "second controller beside a live owner pid."
)
LOOP_REBOOT_RESTORE_GOAL = (
    "Repair continuous-loop reboot restoration: a reaped orphan after login "
    "or reboot stays stopped until an operator starts it, so the native loop "
    "does not resume."
)
LOOP_REBOOT_RESTORE_LEFTOVER = (
    "Later genesis can take continuous-loop reboot restoration so a reaped "
    "orphan after login or reboot stays stopped until an operator starts it."
)
REPO_ROOT = Path(__file__).resolve().parents[2]
HEALTH_AUTOMATION_NAMES = frozenset(
    {
        "daily-health.json",
        "daily-health-automation.json",
        "paused-daily-health.json",
    }
)
ControllerStarter = Callable[..., dict[str, Any]]


def health_automation_paths(repo_path: Path, output_dir: Path | None = None) -> tuple[Path, ...]:
    from blackhole_agent.unbound import DEFAULT_OUTPUT_DIR, mission_root

    root = mission_root(repo_path, DEFAULT_OUTPUT_DIR if output_dir is None else output_dir)
    return tuple(root / name for name in sorted(HEALTH_AUTOMATION_NAMES))


def default_start_restored_controller(
    repo_path: Path,
    output_dir: Path | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Spawn one detached continuous-loop controller for the restored orphan."""

    from blackhole_agent import unbound
    from blackhole_agent.unbound import DEFAULT_OUTPUT_DIR

    output = DEFAULT_OUTPUT_DIR if output_dir is None else output_dir
    src = Path(unbound.__file__).resolve().parents[1]
    child = subprocess.Popen(
        [
            sys.executable,
            "-I",
            "-c",
            (
                "import sys\n"
                "from pathlib import Path\n"
                "sys.path.insert(0, sys.argv[1])\n"
                "from blackhole_agent.unbound import run_continuous_loop\n"
                "raise SystemExit(run_continuous_loop("
                "repo_path=Path(sys.argv[2]), output_dir=Path(sys.argv[3]), "
                "publish_remote=''))\n"
            ),
            str(src),
            str(repo_path),
            str(output),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return {
        "started": True,
        "pid": child.pid,
        "action": "start_controller",
        "payload_loop_id": (payload or {}).get("loop_id", ""),
    }


def restore_orphaned_loop_on_startup(
    repo_path: Path,
    output_dir: Path | None = None,
    *,
    controller_starter: ControllerStarter | None = None,
) -> dict[str, Any]:
    """Start a reaped orphan only when no live owner pid exists.

    A live owner, an uncertain PID, or an operator-stopped loop never starts
    another controller. Daily-health automation files are not rewritten.
    """

    from blackhole_agent.orphan_loop_reap import annotate_loop_status, reap_orphaned_loop
    from blackhole_agent.unbound import (
        DEFAULT_OUTPUT_DIR,
        append_jsonl,
        continuous_loop_events_path,
        continuous_loop_lock_path,
        continuous_loop_owner_pid,
        continuous_loop_state_path,
        pid_is_running,
        utc_now_iso as loop_now,
    )

    output = DEFAULT_OUTPUT_DIR if output_dir is None else output_dir
    repo = Path(repo_path)
    state_path = continuous_loop_state_path(repo, output)
    lock_path = continuous_loop_lock_path(repo, output)
    starter = controller_starter or default_start_restored_controller

    def skip(current: dict[str, Any], reason: str) -> dict[str, Any]:
        return {
            **current,
            "started": False,
            "action": "skip",
            "restore_reason": reason,
            "health_automation_untouched": True,
        }

    if not state_path.exists():
        return skip({}, "no_loop_state")

    current = reap_orphaned_loop(repo, output)
    if current.get("pid_alive") is True:
        return skip(current, "live_owner")
    if lock_path.exists():
        try:
            lock_pid = continuous_loop_owner_pid(lock_path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError) as exc:
            return skip({**current, "liveness_error": str(exc)}, "unknown_lock")
        if pid_is_running(lock_pid):
            return skip({**current, "lock_pid": lock_pid, "pid_alive": True}, "live_owner")
    if current.get("pid_alive") is None or current.get("effective_status") == "unknown":
        return skip(current, "unknown_liveness")
    if current.get("status") != "orphaned":
        return skip(current, "not_orphaned")

    health_before = {
        str(path): path.read_bytes() if path.exists() else None
        for path in health_automation_paths(repo, output)
    }
    at = loop_now()
    try:
        started = starter(repo, output, current)
    except Exception as exc:  # noqa: BLE001 - startup must report, not raise through login
        return {
            **annotate_loop_status(json.loads(state_path.read_text(encoding="utf-8"))),
            "started": False,
            "action": "skip",
            "restore_reason": "start_failed",
            "restore_error": str(exc),
            "health_automation_untouched": all(
                (path.read_bytes() if path.exists() else None) == health_before[str(path)]
                for path in health_automation_paths(repo, output)
            ),
        }
    new_pid = started.get("pid")
    try:
        owner_pid = continuous_loop_owner_pid(new_pid)
        live = pid_is_running(owner_pid)
    except (OSError, ValueError) as exc:
        return {
            **annotate_loop_status(json.loads(state_path.read_text(encoding="utf-8"))),
            "started": False,
            "action": "skip",
            "restore_reason": "start_failed",
            "restore_error": str(exc),
            "health_automation_untouched": True,
        }
    if not live:
        return {
            **annotate_loop_status(json.loads(state_path.read_text(encoding="utf-8"))),
            "started": False,
            "action": "skip",
            "restore_reason": "start_failed",
            "restore_error": "starter did not leave a live owner pid",
            "health_automation_untouched": True,
        }
    append_jsonl(
        continuous_loop_events_path(repo, output),
        {
            "event": "continuous_loop.restored",
            "at": at,
            "loop_id": current.get("loop_id", ""),
            "previous_pid": current.get("pid"),
            "pid": owner_pid,
            "previous_status": current.get("status"),
            "current_mission_id": current.get("current_mission_id", ""),
            "current_state_path": current.get("current_state_path", ""),
            "reason": "startup_restore_orphaned",
        },
    )
    shown = annotate_loop_status(json.loads(state_path.read_text(encoding="utf-8")))
    health_untouched = all(
        (path.read_bytes() if path.exists() else None) == health_before[str(path)]
        for path in health_automation_paths(repo, output)
    )
    return {
        **shown,
        "started": True,
        "action": "restore",
        "restore_reason": "orphaned_no_live_owner",
        "restored_pid": owner_pid,
        "previous_pid": current.get("pid"),
        "health_automation_untouched": health_untouched,
    }


def loop_reboot_restore_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.loop_reboot_restore import "
        "builtin_loop_reboot_restore_proof; r=builtin_loop_reboot_restore_proof(); "
        "assert r['ok'] and r.get('action')=='loop_reboot_restore' "
        "and r.get('passed_count',0) >= 8 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_loop_reboot_restore_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the restore helper on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=LOOP_REBOOT_RESTORE_ID,
        name="Continuous-loop reboot restoration",
        description=(
            "A reaped orphaned continuous-loop state is restored by a startup "
            "helper that starts only when no live owner pid exists and does "
            "not start a second controller beside a live owner pid."
        ),
        kind="python",
        entry="blackhole_agent.loop_reboot_restore:builtin_loop_reboot_restore_proof",
        proof_command=loop_reboot_restore_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.orphan-loop-reap",
        ),
        behavior_paths=(
            "src/blackhole_agent/loop_reboot_restore.py",
            "src/blackhole_agent/unbound.py",
            "src/blackhole_agent/loop_login_task.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A reaped orphan after login or reboot resumes: the startup helper "
            "starts a controller only when no live owner pid exists and refuses "
            "to start a second controller beside a live owner pid."
        ),
        tags=("continuous-loop", "orphan", "restore", "startup", "reboot"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def _seed_orphaned(repo: Path, *, pid: int, status: str = "orphaned") -> Path:
    from blackhole_agent.unbound import (
        continuous_loop_state_path,
        save_continuous_loop_state,
    )

    path = continuous_loop_state_path(repo)
    save_continuous_loop_state(
        path,
        {
            "loop_id": "reboot-restore-proof",
            "status": status,
            "pid": pid,
            "orphaned_from_status": "running_mission" if status == "orphaned" else "",
            "current_mission_id": "unfinished",
            "current_state_path": str(repo / "mission.json"),
            "next_wake_at": "",
            "last_error": "preserve diagnostic",
            "stop_reason": "controller_process_missing" if status == "orphaned" else "operator_stop",
        },
    )
    return path


def builtin_loop_reboot_restore_proof() -> dict[str, Any]:
    """Hermetic proof: orphaned + no live pid starts once; a live owner is left alone."""

    from blackhole_agent.evolution_quality import behavior_family
    from blackhole_agent.kernel_genesis_diversify import DIVERSITY_CATALOG
    from blackhole_agent.kernel_leftover import leftover_marker_ids
    from blackhole_agent.orphan_loop_reap import ORPHAN_LOOP_REAP_ID
    from blackhole_agent.unbound import pid_is_running

    checks: dict[str, bool] = {}
    checks["denylists_self"] = LOOP_REBOOT_RESTORE_ID in LOCAL_DENYLIST
    checks["denylists_next_family"] = LOOP_LOGIN_TASK_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(LOOP_REBOOT_RESTORE_GOAL) == (
        LOOP_REBOOT_RESTORE_ID,
    )
    checks["leftover_text_binds_next_family"] = leftover_marker_ids(
        LOOP_LOGIN_TASK_LEFTOVER
    ) == (LOOP_LOGIN_TASK_ID,)
    checks["next_family_goal_is_login_task"] = leftover_marker_ids(LOOP_LOGIN_TASK_GOAL) == (
        LOOP_LOGIN_TASK_ID,
    )
    checks["prior_family_markers_stay"] = leftover_marker_ids(LOOP_REBOOT_RESTORE_LEFTOVER) == (
        LOOP_REBOOT_RESTORE_ID,
    )
    catalog = DIVERSITY_CATALOG
    checks["catalog_names_reboot_restore"] = (
        len(catalog) > 241
        and catalog[241]["id"] == LOOP_REBOOT_RESTORE_ID
        and catalog[241]["goal"] == LOOP_REBOOT_RESTORE_GOAL
        and catalog[241]["done_when"] == LOOP_REBOOT_RESTORE_DONE_WHEN
        and catalog[241]["source"] == "genesis_bind_loop_reboot"
    )
    checks["catalog_names_login_task"] = (
        len(catalog) > 242
        and catalog[242]["id"] == LOOP_LOGIN_TASK_ID
        and catalog[242]["goal"] == LOOP_LOGIN_TASK_GOAL
        and catalog[242]["source"] == "genesis_bind_loop_login"
    )
    checks["reap_stays_ahead"] = len(catalog) > 240 and catalog[240]["id"] == ORPHAN_LOOP_REAP_ID

    dead_pid = 1_000_013
    while pid_is_running(dead_pid):
        dead_pid += 2
    live_pid = os.getpid()
    starts: list[int] = []

    def starter(repo: Path, output_dir: Path | None = None, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        from blackhole_agent.unbound import (
            continuous_loop_lock,
            continuous_loop_lock_path,
            continuous_loop_state_path,
            save_continuous_loop_state,
        )

        pid = os.getpid()
        starts.append(pid)
        with continuous_loop_lock(continuous_loop_lock_path(repo)):
            save_continuous_loop_state(
                continuous_loop_state_path(repo),
                {
                    **(payload or {}),
                    "status": "running_mission",
                    "pid": pid,
                    "restored_from_status": "orphaned",
                    "stop_reason": "",
                },
            )
        return {"started": True, "pid": pid}

    import tempfile

    with tempfile.TemporaryDirectory(prefix="loop-reboot-restore-orphan-") as tmp:
        repo = Path(tmp)
        (repo / "mission.json").write_text('{"status":"active"}\n', encoding="utf-8")
        mission_before = (repo / "mission.json").read_bytes()
        health = health_automation_paths(repo)[0]
        health.parent.mkdir(parents=True, exist_ok=True)
        health.write_text('{"enabled": false, "paused": true}\n', encoding="utf-8")
        health_before = health.read_bytes()
        _seed_orphaned(repo, pid=dead_pid)
        first = restore_orphaned_loop_on_startup(repo, controller_starter=starter)
        second = restore_orphaned_loop_on_startup(repo, controller_starter=starter)
        checks["orphaned_without_live_owner_starts"] = (
            first.get("started") is True
            and first.get("action") == "restore"
            and first.get("restore_reason") == "orphaned_no_live_owner"
            and first.get("restored_pid") == live_pid
            and first.get("previous_pid") == dead_pid
            and (repo / "mission.json").read_bytes() == mission_before
            and health.read_bytes() == health_before
            and first.get("health_automation_untouched") is True
        )
        checks["live_owner_does_not_start_second"] = (
            second.get("started") is False
            and second.get("restore_reason") == "live_owner"
            and len(starts) == 1
        )

    with tempfile.TemporaryDirectory(prefix="loop-reboot-restore-live-") as tmp:
        repo = Path(tmp)
        path = _seed_orphaned(repo, pid=live_pid, status="running_mission")
        from blackhole_agent.unbound import continuous_loop_lock_path

        continuous_loop_lock_path(repo).write_text(f"{live_pid}\n", encoding="utf-8")
        before = path.read_bytes()
        starts_before = len(starts)
        result = restore_orphaned_loop_on_startup(repo, controller_starter=starter)
        checks["existing_live_owner_untouched"] = (
            result.get("started") is False
            and result.get("restore_reason") == "live_owner"
            and path.read_bytes() == before
            and len(starts) == starts_before
        )

    with tempfile.TemporaryDirectory(prefix="loop-reboot-restore-stopped-") as tmp:
        repo = Path(tmp)
        _seed_orphaned(repo, pid=dead_pid, status="stopped")
        starts_before = len(starts)
        result = restore_orphaned_loop_on_startup(repo, controller_starter=starter)
        checks["operator_stopped_is_not_auto_started"] = (
            result.get("started") is False
            and result.get("restore_reason") == "not_orphaned"
            and len(starts) == starts_before
        )

    checks["next_family_is_not_handshake"] = (
        behavior_family(LOOP_LOGIN_TASK_GOAL) != "network/handshake-digest-demo"
        and LOOP_LOGIN_TASK_DONE_WHEN != ""
    )
    checks["contract_is_outcome_level"] = (
        "capability_exists:" not in LOOP_REBOOT_RESTORE_DONE_WHEN
        and "capability_proved:" not in LOOP_REBOOT_RESTORE_DONE_WHEN
    )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_loop_reboot_restore_capability()
    return {
        "ok": ok,
        "action": "loop_reboot_restore",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": LOOP_REBOOT_RESTORE_GOAL,
        "done_when": LOOP_REBOOT_RESTORE_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
