"""Acceptance probe: a deleted repo's login registration is unscheduled.

A login startup registration whose repo was deleted is unscheduled so logon
stops firing a dead launcher, without disturbing a live owner pid in a
surviving repo. Prints JSON with boolean passed and nonempty observed.
Exits 0 for both met and unmet outcomes so the controller can replay the
same probe on baseline and candidate source trees.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

observed: dict[str, object] = {"family": "loop-login-retire"}
passed = False

try:
    from blackhole_agent.loop_login_retire import retire_login_startup_registration
    from blackhole_agent.loop_login_task import (
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
except Exception as error:  # pragma: no cover - baseline missing login retire
    observed["error"] = type(error).__name__
    observed["detail"] = str(error)
    print(json.dumps({"passed": False, "observed": observed}, sort_keys=True))
    raise SystemExit(0)


class _Scheduler:
    def __init__(self) -> None:
        self.tasks: dict[str, dict] = {}

    def __call__(self, payload: dict) -> dict:
        name = str(payload.get("name") or "")
        if payload.get("action") == "unschedule":
            self.tasks.pop(name, None)
            return {"backend": "acceptance", "unscheduled": True}
        self.tasks[name] = dict(payload)
        return {"backend": "acceptance", "applied": True}


def _seed_orphaned(repo: Path, *, pid: int, status: str = "orphaned") -> Path:
    path = continuous_loop_state_path(repo)
    save_continuous_loop_state(
        path,
        {
            "loop_id": "acceptance-login-retire",
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
    dead_pid = 1_000_139
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

    unscheduled_ok = False
    dispatch_ok = False
    live_ok = False

    with tempfile.TemporaryDirectory(prefix="accept-login-retire-task-", ignore_cleanup_errors=True) as tmp:
        repo = Path(tmp) / "deleted-repo"
        repo.mkdir()
        (repo / "mission.json").write_text('{"status":"active"}\n', encoding="utf-8")
        _seed_orphaned(repo, pid=dead_pid)
        scheduler = _Scheduler()
        register_loop_restore_at_login(repo, scheduler=scheduler)
        had_task = "BlackholeUnboundLoopRestore" in scheduler.tasks
        shutil.rmtree(repo)
        starts_at_retire = len(starts)
        retired = retire_login_startup_registration(repo, scheduler=scheduler)
        unscheduled_ok = (
            had_task
            and retired.get("started") is False
            and retired.get("action") == "retire"
            and retired.get("retire_reason") == "repo_deleted"
            and retired.get("scheduled") is False
            and retired.get("unscheduled") is True
            and scheduler.tasks == {}
            and len(starts) == starts_at_retire
        )

    with tempfile.TemporaryDirectory(prefix="accept-login-retire-dispatch-", ignore_cleanup_errors=True) as tmp:
        parent = Path(tmp)
        repo = parent / "deleted-repo"
        repo.mkdir()
        durable = parent / "durable-root"
        (repo / "mission.json").write_text('{"status":"active"}\n', encoding="utf-8")
        _seed_orphaned(repo, pid=dead_pid)
        register_loop_restore_at_login(repo, durable)
        registration_file = login_startup_registration_path(repo, durable)
        shutil.rmtree(repo)
        starts_at_retire = len(starts)
        retired = dispatch_login_startup(repo, durable, controller_starter=starter)
        second = dispatch_login_startup(repo, durable, controller_starter=starter)
        dispatch_ok = (
            retired.get("started") is False
            and retired.get("action") == "retire"
            and retired.get("restore_reason") == "repo_deleted"
            and retired.get("scheduled") is False
            and not registration_file.exists()
            and second.get("started") is False
            and second.get("restore_reason") == "not_registered"
            and len(starts) == starts_at_retire
        )

    with tempfile.TemporaryDirectory(prefix="accept-login-retire-live-", ignore_cleanup_errors=True) as tmp:
        parent = Path(tmp)
        dead_repo = parent / "deleted-repo"
        dead_repo.mkdir()
        dead_durable = parent / "dead-durable"
        (dead_repo / "mission.json").write_text('{"status":"active"}\n', encoding="utf-8")
        _seed_orphaned(dead_repo, pid=dead_pid)
        register_loop_restore_at_login(dead_repo, dead_durable)
        surviving = parent / "surviving-repo"
        surviving.mkdir()
        (surviving / "mission.json").write_text('{"status":"active"}\n', encoding="utf-8")
        state_path = _seed_orphaned(surviving, pid=live_pid, status="running_mission")
        continuous_loop_lock_path(surviving).write_text(f"{live_pid}\n", encoding="utf-8")
        register_loop_restore_at_login(surviving)
        surviving_registration = load_login_startup_registration(surviving)
        before = state_path.read_bytes()
        starts_at_retire = len(starts)
        shutil.rmtree(dead_repo)
        retired = retire_login_startup_registration(dead_repo, dead_durable)
        result = dispatch_login_startup(surviving, controller_starter=starter)
        live_ok = (
            retired.get("action") == "retire"
            and retired.get("scheduled") is False
            and surviving_registration is not None
            and load_login_startup_registration(surviving) == surviving_registration
            and result.get("started") is False
            and result.get("restore_reason") == "live_owner"
            and result.get("scheduled") is True
            and state_path.read_bytes() == before
            and len(starts) == starts_at_retire
            and pid_is_running(live_pid)
        )

    observed.update(
        {
            "dead_pid": dead_pid,
            "live_pid": live_pid,
            "dead_repo_task_unscheduled": unscheduled_ok,
            "surviving_record_retired_on_dispatch": dispatch_ok,
            "live_owner_not_disturbed": live_ok,
            "controller_starts": len(starts),
            "sentinel": "BH-LOOP-LOGIN-RETIRE-OK" if unscheduled_ok and dispatch_ok and live_ok else "",
            "error": "",
        }
    )
    passed = bool(unscheduled_ok and dispatch_ok and live_ok)
except Exception as error:  # pragma: no cover - fixture or helper failure
    observed["error"] = type(error).__name__
    observed["detail"] = str(error)
    passed = False

print(json.dumps({"passed": passed, "observed": observed}, sort_keys=True))
sys.exit(0)
