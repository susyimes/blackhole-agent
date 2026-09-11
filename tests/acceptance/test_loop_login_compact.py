"""Acceptance probe: long-gone login-audit tombstones are compacted.

A durable login-scrub audit trail that holds a tombstone whose named
record is long gone — the tombstone's prune time is older than the compact
retention window — has that tombstone compacted so the trail stays small,
while recent tombstones stay so the trail remains reconcilable. Compaction
runs automatically on every recorded scrub, is idempotent, and a surviving
repo with a live owner pid keeps its registration, launcher, task XML, and
state bytes untouched. Prints JSON with boolean passed and nonempty
observed. Exits 0 for both met and unmet outcomes so the controller can
replay the same probe on baseline and candidate source trees.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

observed: dict[str, object] = {"family": "loop-login-compact"}
passed = False

try:
    from blackhole_agent.loop_login_audit import (
        login_audit_log_path,
        read_login_scrub_audit,
    )
    from blackhole_agent.loop_login_compact import (
        DEFAULT_COMPACT_RETENTION_DAYS,
        compact_login_audit_tombstones,
    )
    from blackhole_agent.loop_login_prune import (
        DEFAULT_PRUNE_RETENTION_DAYS,
    )
    from blackhole_agent.loop_login_sweep import sweep_login_tasks_missing_registration
    from blackhole_agent.loop_login_task import (
        LOGIN_TASK_NAME,
        dispatch_login_startup,
        load_login_startup_registration,
        login_startup_launcher_path,
        login_startup_registration_path,
        login_startup_task_xml_path,
        register_loop_restore_at_login,
    )
    from blackhole_agent.loop_login_tombstone import (
        LOGIN_AUDIT_TOMBSTONE_EVENT,
        is_login_audit_tombstone,
    )
    from blackhole_agent.unbound import (
        continuous_loop_lock_path,
        continuous_loop_state_path,
        pid_is_running,
        save_continuous_loop_state,
    )
except Exception as error:  # pragma: no cover - baseline missing login compact
    observed["error"] = type(error).__name__
    observed["detail"] = str(error)
    print(json.dumps({"passed": False, "observed": observed}, sort_keys=True))
    raise SystemExit(0)


class _Scheduler:
    def __init__(self) -> None:
        self.tasks: dict[str, dict] = {}

    @staticmethod
    def _key(payload: dict) -> str:
        return f"{payload.get('name') or ''}|{payload.get('repo_path') or ''}"

    def __call__(self, payload: dict) -> dict:
        action = payload.get("action")
        if action == "list":
            return {
                "backend": "acceptance",
                "listed": True,
                "tasks": [dict(task) for task in self.tasks.values()],
            }
        key = self._key(payload)
        if action == "unschedule":
            self.tasks.pop(key, None)
            return {"backend": "acceptance", "unscheduled": True}
        self.tasks[key] = dict(payload)
        return {"backend": "acceptance", "applied": True}


def _seed_orphaned(repo: Path, *, pid: int, status: str = "orphaned") -> Path:
    path = continuous_loop_state_path(repo)
    save_continuous_loop_state(
        path,
        {
            "loop_id": "acceptance-login-compact",
            "status": status,
            "pid": pid,
            "orphaned_from_status": "running_mission" if status == "orphaned" else "",
            "current_mission_id": "unfinished-mission",
            "current_state_path": str(repo / "mission.json"),
            "last_error": "retained diagnostic",
            "stop_reason": "controller_process_missing" if status == "orphaned" else "operator_stop",
        },
    )
    return path


def _aged_iso(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat().replace("+00:00", "Z")


def _tombstone(task_name: str, repo_path: str, *, pruned_days: int) -> dict:
    return {
        "schema_version": 1,
        "event": LOGIN_AUDIT_TOMBSTONE_EVENT,
        "tombstone": True,
        "task_name": task_name,
        "repo_path": repo_path,
        "reason": "registration_gone",
        "aged_out_scrubbed_at": _aged_iso(pruned_days + DEFAULT_PRUNE_RETENTION_DAYS),
        "pruned_at": _aged_iso(pruned_days),
        "retention_days": DEFAULT_PRUNE_RETENTION_DAYS,
    }


try:
    dead_pid = 1_000_261
    while pid_is_running(dead_pid):
        dead_pid += 2
    live_pid = os.getpid()
    starts: list[int] = []

    def starter(repo: Path, output_dir=None, payload=None):
        pid = os.getpid()
        starts.append(pid)
        save_continuous_loop_state(
            continuous_loop_state_path(repo),
            {**(payload or {}), "status": "running_mission", "pid": pid, "stop_reason": ""},
        )
        return {"started": True, "pid": pid}

    compact_ok = False
    compact_durable = False
    live_ok = False

    with tempfile.TemporaryDirectory(prefix="accept-login-compact-", ignore_cleanup_errors=True) as tmp:
        parent = Path(tmp)
        orphan = parent / "orphan-repo"
        orphan.mkdir()
        (orphan / "mission.json").write_text('{"status":"active"}\n', encoding="utf-8")
        _seed_orphaned(orphan, pid=dead_pid)
        surviving = parent / "surviving-repo"
        surviving.mkdir()
        (surviving / "mission.json").write_text('{"status":"active"}\n', encoding="utf-8")
        state_path = _seed_orphaned(surviving, pid=live_pid, status="running_mission")
        continuous_loop_lock_path(surviving).write_text(f"{live_pid}\n", encoding="utf-8")
        scheduler = _Scheduler()
        register_loop_restore_at_login(orphan, scheduler=scheduler)
        register_loop_restore_at_login(surviving, scheduler=scheduler)
        surviving_launcher = login_startup_launcher_path(surviving)
        surviving_xml = login_startup_task_xml_path(surviving)
        surviving_registration = load_login_startup_registration(surviving)
        orphan_audit_root = login_startup_registration_path(orphan).parent
        surviving_audit_root = login_startup_registration_path(surviving).parent

        ancient = _tombstone(
            "ancient-task", str(orphan), pruned_days=DEFAULT_COMPACT_RETENTION_DAYS + 30
        )
        recent = _tombstone("recent-task", str(orphan), pruned_days=100)
        audit_path = login_audit_log_path(orphan_audit_root)
        audit_path.write_text(
            json.dumps(ancient, sort_keys=True) + "\n" + json.dumps(recent, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        login_startup_registration_path(orphan).unlink()

        before = state_path.read_bytes()
        starts_at_sweep = len(starts)
        swept = sweep_login_tasks_missing_registration(scheduler=scheduler)
        trail = read_login_scrub_audit(orphan_audit_root)
        entries = trail.get("entries") or []
        names = [str(entry.get("task_name") or "") for entry in entries]
        tombstones = [entry for entry in entries if is_login_audit_tombstone(entry)]

        raw_before = audit_path.read_bytes()
        again = compact_login_audit_tombstones(orphan_audit_root)
        result = dispatch_login_startup(surviving, controller_starter=starter)

        compact_ok = (
            swept.get("action") == "sweep"
            and swept.get("swept") == [LOGIN_TASK_NAME]
            and swept.get("audit_recorded") == 1
            and audit_path.is_file()
            and trail.get("tombstone_count") == 1
            and len(tombstones) == 1
            and tombstones[0].get("task_name") == "recent-task"
            and "ancient-task" not in names
            and LOGIN_TASK_NAME in names
            and trail.get("entry_count") == 2
            and len(starts) == starts_at_sweep
        )
        compact_durable = (
            again.get("compacted") is False
            and again.get("compacted_count") == 0
            and again.get("reason") == "nothing_compactable"
            and audit_path.read_bytes() == raw_before
            and read_login_scrub_audit(orphan_audit_root).get("tombstone_count") == 1
        )
        live_ok = (
            LOGIN_TASK_NAME in (swept.get("kept") or [])
            and surviving_registration is not None
            and load_login_startup_registration(surviving) == surviving_registration
            and surviving_launcher.is_file()
            and surviving_xml.is_file()
            and not login_audit_log_path(surviving_audit_root).exists()
            and result.get("started") is False
            and result.get("restore_reason") == "live_owner"
            and result.get("scheduled") is True
            and state_path.read_bytes() == before
            and pid_is_running(live_pid)
        )

    observed.update(
        {
            "dead_pid": dead_pid,
            "live_pid": live_pid,
            "long_gone_tombstone_compacted_on_sweep": compact_ok,
            "compact_is_idempotent": compact_durable,
            "live_owner_not_disturbed": live_ok,
            "controller_starts": len(starts),
            "sentinel": "BH-LOOP-LOGIN-COMPACT-OK" if compact_ok and compact_durable and live_ok else "",
            "error": "",
        }
    )
    passed = bool(compact_ok and compact_durable and live_ok)
except Exception as error:  # pragma: no cover - fixture or helper failure
    observed["error"] = type(error).__name__
    observed["detail"] = str(error)
    passed = False

print(json.dumps({"passed": passed, "observed": observed}, sort_keys=True))
sys.exit(0)
