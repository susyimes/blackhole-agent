"""Acceptance probe: a record-gone login task is swept from the scheduler.

A scheduled login task whose registration record is gone is removed from the
scheduler so logon stops firing it, without disturbing a live owner pid in a
surviving repo. Prints JSON with boolean passed and nonempty observed.
Exits 0 for both met and unmet outcomes so the controller can replay the
same probe on baseline and candidate source trees.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

observed: dict[str, object] = {"family": "loop-login-sweep"}
passed = False

try:
    from blackhole_agent.loop_login_sweep import (
        FileLoginScheduler,
        sweep_login_tasks_missing_registration,
    )
    from blackhole_agent.loop_login_task import (
        LOGIN_TASK_NAME,
        dispatch_login_startup,
        load_login_startup_registration,
        login_startup_registration_path,
        register_loop_restore_at_login,
    )
    from blackhole_agent.unbound import (
        continuous_loop_lock_path,
        continuous_loop_state_path,
        pid_is_running,
        save_continuous_loop_state,
    )
except Exception as error:  # pragma: no cover - baseline missing login sweep
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
            "loop_id": "acceptance-login-sweep",
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


try:
    dead_pid = 1_000_161
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

    sweep_ok = False
    live_ok = False
    file_ok = False

    with tempfile.TemporaryDirectory(prefix="accept-login-sweep-", ignore_cleanup_errors=True) as tmp:
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
        surviving_registration = load_login_startup_registration(surviving)
        login_startup_registration_path(orphan).unlink()
        before = state_path.read_bytes()
        starts_at_sweep = len(starts)
        swept = sweep_login_tasks_missing_registration(scheduler=scheduler)
        again = sweep_login_tasks_missing_registration(scheduler=scheduler)
        result = dispatch_login_startup(surviving, controller_starter=starter)
        sweep_ok = (
            swept.get("started") is False
            and swept.get("action") == "sweep"
            and swept.get("swept") == [LOGIN_TASK_NAME]
            and swept.get("swept_reasons") == {LOGIN_TASK_NAME: "registration_gone"}
            and swept.get("unscheduled") is True
            and len(scheduler.tasks) == 1
            and again.get("swept") == []
            and len(starts) == starts_at_sweep
        )
        live_ok = (
            LOGIN_TASK_NAME in (swept.get("kept") or [])
            and surviving_registration is not None
            and load_login_startup_registration(surviving) == surviving_registration
            and result.get("started") is False
            and result.get("restore_reason") == "live_owner"
            and result.get("scheduled") is True
            and state_path.read_bytes() == before
            and pid_is_running(live_pid)
        )

    with tempfile.TemporaryDirectory(prefix="accept-login-sweep-file-", ignore_cleanup_errors=True) as tmp:
        parent = Path(tmp)
        repo = parent / "file-backend-repo"
        repo.mkdir()
        (repo / "mission.json").write_text('{"status":"active"}\n', encoding="utf-8")
        _seed_orphaned(repo, pid=dead_pid)
        file_scheduler = FileLoginScheduler(parent / "scheduler-root")
        register_loop_restore_at_login(repo, scheduler=file_scheduler)
        had_task = len(file_scheduler({"action": "list"}).get("tasks") or []) == 1
        login_startup_registration_path(repo).unlink()
        starts_at_sweep = len(starts)
        swept = sweep_login_tasks_missing_registration(scheduler=file_scheduler)
        remaining = file_scheduler({"action": "list"}).get("tasks") or []
        file_ok = (
            had_task
            and swept.get("action") == "sweep"
            and swept.get("backend") == "file"
            and swept.get("swept") == [LOGIN_TASK_NAME]
            and remaining == []
            and len(starts) == starts_at_sweep
        )

    observed.update(
        {
            "dead_pid": dead_pid,
            "live_pid": live_pid,
            "record_gone_task_swept": sweep_ok,
            "live_owner_not_disturbed": live_ok,
            "file_backend_swept": file_ok,
            "controller_starts": len(starts),
            "sentinel": "BH-LOOP-LOGIN-SWEEP-OK" if sweep_ok and live_ok and file_ok else "",
            "error": "",
        }
    )
    passed = bool(sweep_ok and live_ok and file_ok)
except Exception as error:  # pragma: no cover - fixture or helper failure
    observed["error"] = type(error).__name__
    observed["detail"] = str(error)
    passed = False

print(json.dumps({"passed": passed, "observed": observed}, sort_keys=True))
sys.exit(0)
