import json
import os
import shutil
from pathlib import Path

from typer.testing import CliRunner

from blackhole_agent import unbound
from blackhole_agent.loop_login_retire import (
    LOOP_LOGIN_RETIRE_DONE_WHEN,
    LOOP_LOGIN_RETIRE_GOAL,
    LOOP_LOGIN_RETIRE_ID,
    builtin_loop_login_retire_proof,
    retire_login_startup_registration,
)
from blackhole_agent.loop_login_sweep import LOOP_LOGIN_SWEEP_GOAL, LOOP_LOGIN_SWEEP_ID
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

    def __call__(self, payload: dict) -> dict:
        name = str(payload.get("name") or "")
        if payload.get("action") == "unschedule":
            self.tasks.pop(name, None)
            return {"backend": "test", "unscheduled": True}
        self.tasks[name] = dict(payload)
        return {"backend": "test", "applied": True}


def seed_orphaned(repo: Path, *, pid: int, status: str = "orphaned") -> Path:
    path = unbound.continuous_loop_state_path(repo)
    unbound.save_continuous_loop_state(
        path,
        {
            "loop_id": "login-retire-test",
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


def test_builtin_proof_retires_deleted_repo_without_disturbing_live_owner():
    report = builtin_loop_login_retire_proof()
    assert report["ok"] is True
    assert report["action"] == "loop_login_retire"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == report["check_count"]
    assert report["checks"]["deleted_repo_record_gone_is_unscheduled"]
    assert report["checks"]["deleted_repo_surviving_record_is_retired"]
    assert report["checks"]["retire_does_not_disturb_surviving_live_owner"]
    assert report["checks"]["catalog_names_login_sweep"]


def test_selection_accepts_login_retire_and_next_family(tmp_path: Path):
    gate = assess_mission_selection(
        tmp_path,
        LOOP_LOGIN_RETIRE_GOAL,
        LOOP_LOGIN_RETIRE_DONE_WHEN,
        history=[],
    )
    assert gate.accepted is True
    assert LOOP_LOGIN_RETIRE_ID not in gate.capability_family
    nxt = assess_mission_selection(
        tmp_path,
        LOOP_LOGIN_SWEEP_GOAL,
        "A scheduled login task whose registration record is gone is removed.",
        history=[],
    )
    assert nxt.accepted is True
    assert LOOP_LOGIN_SWEEP_ID not in nxt.capability_family


def test_deleted_repo_registration_is_unscheduled(tmp_path: Path):
    starts: list[int] = []

    def starter(repo, output_dir=None, payload=None):
        starts.append(os.getpid())
        unbound.save_continuous_loop_state(
            unbound.continuous_loop_state_path(repo),
            {**(payload or {}), "status": "running_mission", "pid": os.getpid()},
        )
        return {"started": True, "pid": os.getpid()}

    dead_pid = 1_000_133
    while unbound.pid_is_running(dead_pid):
        dead_pid += 2
    repo = tmp_path / "deleted-repo"
    repo.mkdir()
    seed_orphaned(repo, pid=dead_pid)
    scheduler = RecordingScheduler()
    register_loop_restore_at_login(repo, scheduler=scheduler)
    assert LOGIN_TASK_NAME in scheduler.tasks
    shutil.rmtree(repo)

    retired = retire_login_startup_registration(repo, scheduler=scheduler)
    assert retired["started"] is False
    assert retired["action"] == "retire"
    assert retired["retire_reason"] == "repo_deleted"
    assert retired["scheduled"] is False
    assert retired["unscheduled"] is True
    assert scheduler.tasks == {}
    assert starts == []

    durable = tmp_path / "durable-root"
    repo2 = tmp_path / "durable-deleted"
    repo2.mkdir()
    seed_orphaned(repo2, pid=dead_pid)
    register_loop_restore_at_login(repo2, durable)
    registration_file = login_startup_registration_path(repo2, durable)
    assert registration_file.is_file()
    shutil.rmtree(repo2)
    dispatched = dispatch_login_startup(repo2, durable, controller_starter=starter)
    assert dispatched["started"] is False
    assert dispatched["action"] == "retire"
    assert dispatched["restore_reason"] == "repo_deleted"
    assert dispatched["scheduled"] is False
    assert not registration_file.exists()
    second = dispatch_login_startup(repo2, durable, controller_starter=starter)
    assert second["restore_reason"] == "not_registered"
    assert second["scheduled"] is False
    assert starts == []


def test_live_repo_retire_is_noop_and_dispatch_still_restores(tmp_path: Path):
    dead_pid = 1_000_135
    while unbound.pid_is_running(dead_pid):
        dead_pid += 2
    seed_orphaned(tmp_path, pid=dead_pid)
    scheduler = RecordingScheduler()
    register_loop_restore_at_login(tmp_path, scheduler=scheduler)
    kept = retire_login_startup_registration(tmp_path, scheduler=scheduler)
    assert kept["action"] == "keep"
    assert kept["scheduled"] is True
    assert LOGIN_TASK_NAME in scheduler.tasks
    assert load_login_startup_registration(tmp_path) is not None


def test_cli_login_retire_unschedules_dead_repo_and_keeps_live_owner(tmp_path: Path):
    dead = tmp_path / "deleted-repo"
    dead.mkdir()
    dead_pid = 1_000_137
    while unbound.pid_is_running(dead_pid):
        dead_pid += 2
    seed_orphaned(dead, pid=dead_pid)
    durable = tmp_path / "durable-root"
    register_loop_restore_at_login(dead, durable)
    surviving = tmp_path / "surviving-repo"
    surviving.mkdir()
    state_path = seed_orphaned(surviving, pid=os.getpid(), status="running_mission")
    unbound.continuous_loop_lock_path(surviving).write_text(f"{os.getpid()}\n", encoding="utf-8")
    register_loop_restore_at_login(surviving)
    before = state_path.read_bytes()
    shutil.rmtree(dead)

    retire = CliRunner().invoke(
        unbound.app,
        ["loop-login-retire", "--repo-path", str(dead), "--output-dir", str(durable)],
    )
    assert retire.exit_code == 0, retire.output
    retired = json.loads(retire.stdout)
    assert retired["action"] == "retire"
    assert retired["retire_reason"] == "repo_deleted"
    assert retired["scheduled"] is False
    assert retired["started"] is False

    result = CliRunner().invoke(unbound.app, ["loop-login-run", "--repo-path", str(surviving)])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["started"] is False
    assert payload["restore_reason"] == "live_owner"
    assert state_path.read_bytes() == before
    assert load_login_startup_registration(surviving) is not None
