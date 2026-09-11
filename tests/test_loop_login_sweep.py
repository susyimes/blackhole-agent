import json
import os
from pathlib import Path

from typer.testing import CliRunner

from blackhole_agent import unbound
from blackhole_agent.loop_login_scrub import LOOP_LOGIN_SCRUB_GOAL, LOOP_LOGIN_SCRUB_ID
from blackhole_agent.loop_login_sweep import (
    LOOP_LOGIN_SWEEP_DONE_WHEN,
    LOOP_LOGIN_SWEEP_GOAL,
    LOOP_LOGIN_SWEEP_ID,
    FileLoginScheduler,
    builtin_loop_login_sweep_proof,
    login_task_sweep_reason,
    sweep_login_tasks_missing_registration,
)
from blackhole_agent.loop_login_task import (
    LOGIN_TASK_NAME,
    dispatch_login_startup,
    load_login_startup_registration,
    login_startup_registration_path,
    register_loop_restore_at_login,
)
from blackhole_agent.mission_selection import assess_mission_selection


class RecordingScheduler:
    def __init__(self) -> None:
        self.tasks: dict[str, dict] = {}

    @staticmethod
    def _key(payload: dict) -> str:
        return f"{payload.get('name') or ''}|{payload.get('repo_path') or ''}"

    def __call__(self, payload: dict) -> dict:
        action = payload.get("action")
        if action == "list":
            return {
                "backend": "test",
                "listed": True,
                "tasks": [dict(task) for task in self.tasks.values()],
            }
        key = self._key(payload)
        if action == "unschedule":
            self.tasks.pop(key, None)
            return {"backend": "test", "unscheduled": True}
        self.tasks[key] = dict(payload)
        return {"backend": "test", "applied": True}


def seed_orphaned(repo: Path, *, pid: int, status: str = "orphaned") -> Path:
    path = unbound.continuous_loop_state_path(repo)
    unbound.save_continuous_loop_state(
        path,
        {
            "loop_id": "login-sweep-test",
            "status": status,
            "pid": pid,
            "orphaned_from_status": "running_mission" if status == "orphaned" else "",
            "current_mission_id": "unfinished",
            "current_state_path": str(repo / "mission.json"),
            "last_error": "preserve diagnostic",
            "stop_reason": "controller_process_missing" if status == "orphaned" else "operator_stop",
        },
    )
    (repo / "mission.json").write_text('{"status":"active"}\n', encoding="utf-8")
    return path


def test_builtin_proof_sweeps_record_gone_task_without_disturbing_live_owner():
    report = builtin_loop_login_sweep_proof()
    assert report["ok"] is True
    assert report["action"] == "loop_login_sweep"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == report["check_count"]
    assert report["checks"]["record_gone_task_is_unscheduled"]
    assert report["checks"]["live_owner_task_is_kept"]
    assert report["checks"]["foreign_and_drifted_tasks_are_kept"]
    assert report["checks"]["catalog_names_login_scrub"]


def test_selection_accepts_login_sweep_and_next_family(tmp_path: Path):
    gate = assess_mission_selection(
        tmp_path,
        LOOP_LOGIN_SWEEP_GOAL,
        LOOP_LOGIN_SWEEP_DONE_WHEN,
        history=[],
    )
    assert gate.accepted is True
    assert LOOP_LOGIN_SWEEP_ID not in gate.capability_family
    nxt = assess_mission_selection(
        tmp_path,
        LOOP_LOGIN_SCRUB_GOAL,
        "A swept login task's leftover launcher and task XML artifacts are scrubbed.",
        history=[],
    )
    assert nxt.accepted is True
    assert LOOP_LOGIN_SCRUB_ID not in nxt.capability_family


def test_record_gone_task_is_unscheduled_and_surviving_repo_kept(tmp_path: Path):
    starts: list[int] = []

    def starter(repo, output_dir=None, payload=None):
        starts.append(os.getpid())
        unbound.save_continuous_loop_state(
            unbound.continuous_loop_state_path(repo),
            {**(payload or {}), "status": "running_mission", "pid": os.getpid()},
        )
        return {"started": True, "pid": os.getpid()}

    dead_pid = 1_000_153
    while unbound.pid_is_running(dead_pid):
        dead_pid += 2
    orphan = tmp_path / "orphan-repo"
    orphan.mkdir()
    seed_orphaned(orphan, pid=dead_pid)
    surviving = tmp_path / "surviving-repo"
    surviving.mkdir()
    state_path = seed_orphaned(surviving, pid=os.getpid(), status="running_mission")
    unbound.continuous_loop_lock_path(surviving).write_text(f"{os.getpid()}\n", encoding="utf-8")
    scheduler = RecordingScheduler()
    register_loop_restore_at_login(orphan, scheduler=scheduler)
    register_loop_restore_at_login(surviving, scheduler=scheduler)
    assert len(scheduler.tasks) == 2
    login_startup_registration_path(orphan).unlink()

    before = state_path.read_bytes()
    swept = sweep_login_tasks_missing_registration(scheduler=scheduler)
    assert swept["started"] is False
    assert swept["action"] == "sweep"
    assert swept["swept"] == [LOGIN_TASK_NAME]
    assert swept["swept_reasons"] == {LOGIN_TASK_NAME: "registration_gone"}
    assert swept["unscheduled"] is True
    assert LOGIN_TASK_NAME in swept["kept"]
    assert len(scheduler.tasks) == 1
    assert load_login_startup_registration(surviving) is not None
    assert state_path.read_bytes() == before

    result = dispatch_login_startup(surviving, controller_starter=starter)
    assert result["started"] is False
    assert result["restore_reason"] == "live_owner"
    assert starts == []

    again = sweep_login_tasks_missing_registration(scheduler=scheduler)
    assert again["swept"] == []
    assert again["unscheduled"] is False
    assert len(scheduler.tasks) == 1


def test_sweep_reason_only_for_restore_task_whose_record_is_gone(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    seed_orphaned(repo, pid=1_000_155)
    register_loop_restore_at_login(repo)
    task = load_login_startup_registration(repo)
    assert task is not None
    assert login_task_sweep_reason(task) is None
    login_startup_registration_path(repo).unlink()
    assert login_task_sweep_reason(task) == "registration_gone"
    assert login_task_sweep_reason({"name": "OtherAppLogon", "repo_path": str(repo)}) is None
    assert login_task_sweep_reason({**task, "helper": "blackhole_agent.other:helper"}) is None


def test_file_login_scheduler_roundtrip_and_sweep(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    dead_pid = 1_000_157
    while unbound.pid_is_running(dead_pid):
        dead_pid += 2
    seed_orphaned(repo, pid=dead_pid)
    scheduler = FileLoginScheduler(tmp_path / "scheduler-root")
    register_loop_restore_at_login(repo, scheduler=scheduler)
    listed = scheduler({"action": "list"})
    assert listed["listed"] is True
    assert len(listed["tasks"]) == 1
    login_startup_registration_path(repo).unlink()
    swept = sweep_login_tasks_missing_registration(scheduler=scheduler)
    assert swept["backend"] == "file"
    assert swept["swept"] == [LOGIN_TASK_NAME]
    assert scheduler({"action": "list"})["tasks"] == []


def test_cli_login_sweep_removes_record_gone_task(tmp_path: Path):
    repo = tmp_path / "orphan-repo"
    repo.mkdir()
    dead_pid = 1_000_159
    while unbound.pid_is_running(dead_pid):
        dead_pid += 2
    seed_orphaned(repo, pid=dead_pid)
    store_root = tmp_path / "scheduler-root"
    register_loop_restore_at_login(repo, scheduler=FileLoginScheduler(store_root))
    login_startup_registration_path(repo).unlink()

    swept = CliRunner().invoke(
        unbound.app,
        ["loop-login-sweep", "--output-dir", str(store_root)],
    )
    assert swept.exit_code == 0, swept.output
    payload = json.loads(swept.stdout)
    assert payload["action"] == "sweep"
    assert payload["swept"] == [LOGIN_TASK_NAME]
    assert payload["unscheduled"] is True
    assert payload["started"] is False
    assert FileLoginScheduler(store_root)({"action": "list"})["tasks"] == []
