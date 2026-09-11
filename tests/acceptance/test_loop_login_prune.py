"""Acceptance probe: a bounded login-scrub audit trail prunes aged-out records.

A durable login-scrub audit trail that holds a record older than the
retention window has that stale record pruned once it ages out — on the next
recorded sweep and on demand — so the trail stays bounded, while a
surviving repo with a live owner pid keeps its registration, launcher, task
XML, and state bytes untouched. Prints JSON with boolean passed and nonempty
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

observed: dict[str, object] = {"family": "loop-login-prune"}
passed = False

try:
    from blackhole_agent.loop_login_audit import (
        login_audit_log_path,
        read_login_scrub_audit,
    )
    from blackhole_agent.loop_login_prune import (
        DEFAULT_PRUNE_RETENTION_DAYS,
        prune_login_scrub_audit,
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
    from blackhole_agent.unbound import (
        continuous_loop_lock_path,
        continuous_loop_state_path,
        pid_is_running,
        save_continuous_loop_state,
    )
except Exception as error:  # pragma: no cover - baseline missing login prune
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
            "loop_id": "acceptance-login-prune",
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


try:
    dead_pid = 1_000_221
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

    prune_ok = False
    live_ok = False

    with tempfile.TemporaryDirectory(prefix="accept-login-prune-", ignore_cleanup_errors=True) as tmp:
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

        stale_entry = {
            "event": "login_task_artifacts_scrubbed",
            "task_name": "stale-task",
            "repo_path": str(orphan),
            "scrubbed_paths": ["old-launcher", "old-xml"],
            "scrubbed_at": _aged_iso(DEFAULT_PRUNE_RETENTION_DAYS + 60),
        }
        audit_path = login_audit_log_path(orphan_audit_root)
        audit_path.write_text(json.dumps(stale_entry, sort_keys=True) + "\n", encoding="utf-8")
        login_startup_registration_path(orphan).unlink()

        before = state_path.read_bytes()
        starts_at_sweep = len(starts)
        swept = sweep_login_tasks_missing_registration(scheduler=scheduler)
        trail = read_login_scrub_audit(orphan_audit_root)
        entries = trail.get("entries") or []
        names = [str(entry.get("task_name") or "") for entry in entries]

        again = prune_login_scrub_audit(orphan_audit_root)
        surviving_prune = prune_login_scrub_audit(surviving_audit_root)
        result = dispatch_login_startup(surviving, controller_starter=starter)

        prune_ok = (
            swept.get("action") == "sweep"
            and swept.get("swept") == [LOGIN_TASK_NAME]
            and swept.get("audit_recorded") == 1
            and audit_path.is_file()
            and trail.get("entry_count") == 1
            and trail.get("malformed_count") == 0
            and "stale-task" not in names
            and names == [LOGIN_TASK_NAME]
            and again.get("pruned") is False
            and again.get("pruned_count") == 0
            and surviving_prune.get("reason") == "no_trail"
            and len(starts) == starts_at_sweep
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
            "aged_out_records_pruned_trail_bounded": prune_ok,
            "live_owner_not_disturbed": live_ok,
            "controller_starts": len(starts),
            "sentinel": "BH-LOOP-LOGIN-PRUNE-OK" if prune_ok and live_ok else "",
            "error": "",
        }
    )
    passed = bool(prune_ok and live_ok)
except Exception as error:  # pragma: no cover - fixture or helper failure
    observed["error"] = type(error).__name__
    observed["detail"] = str(error)
    passed = False

print(json.dumps({"passed": passed, "observed": observed}, sort_keys=True))
sys.exit(0)
