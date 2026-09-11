import json
import os
from pathlib import Path

from typer.testing import CliRunner

from blackhole_agent import unbound
from blackhole_agent.loop_login_repair import LOOP_LOGIN_REPAIR_GOAL, LOOP_LOGIN_REPAIR_ID
from blackhole_agent.loop_login_task import (
    LOOP_LOGIN_TASK_DONE_WHEN,
    LOOP_LOGIN_TASK_GOAL,
    LOOP_LOGIN_TASK_ID,
    LOGIN_TRIGGER,
    RESTORE_HELPER,
    builtin_loop_login_task_proof,
    dispatch_login_startup,
    login_startup_registration_path,
    register_loop_restore_at_login,
)
from blackhole_agent.mission_selection import assess_mission_selection


def seed_orphaned(repo: Path, *, pid: int, status: str = "orphaned") -> Path:
    path = unbound.continuous_loop_state_path(repo)
    unbound.save_continuous_loop_state(
        path,
        {
            "loop_id": "login-task-test",
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


def test_builtin_proof_schedules_restore_and_spares_live_owner():
    report = builtin_loop_login_task_proof()
    assert report["ok"] is True
    assert report["action"] == "loop_login_task"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == report["check_count"]
    assert report["checks"]["registration_schedules_restore_at_logon"]
    assert report["checks"]["login_restores_orphan_once"]
    assert report["checks"]["login_does_not_double_live_owner"]
    assert report["checks"]["catalog_names_login_repair"]


def test_selection_accepts_login_task_and_next_family(tmp_path: Path):
    gate = assess_mission_selection(
        tmp_path,
        LOOP_LOGIN_TASK_GOAL,
        LOOP_LOGIN_TASK_DONE_WHEN,
        history=[],
    )
    assert gate.accepted is True
    assert LOOP_LOGIN_TASK_ID not in gate.capability_family
    nxt = assess_mission_selection(
        tmp_path,
        LOOP_LOGIN_REPAIR_GOAL,
        "A missing or disabled login startup registration is repaired.",
        history=[],
    )
    assert nxt.accepted is True
    assert LOOP_LOGIN_REPAIR_ID not in nxt.capability_family


def test_login_registration_restores_orphan_and_refuses_live_owner(tmp_path):
    starts: list[int] = []

    def starter(repo, output_dir=None, payload=None):
        starts.append(os.getpid())
        unbound.save_continuous_loop_state(
            unbound.continuous_loop_state_path(repo),
            {**(payload or {}), "status": "running_mission", "pid": os.getpid()},
        )
        return {"started": True, "pid": os.getpid()}

    dead_pid = 1_000_051
    while unbound.pid_is_running(dead_pid):
        dead_pid += 2
    seed_orphaned(tmp_path, pid=dead_pid)
    before_enable = dispatch_login_startup(tmp_path, controller_starter=starter)
    registered = register_loop_restore_at_login(tmp_path)
    spec = json.loads(login_startup_registration_path(tmp_path).read_text(encoding="utf-8"))
    first = dispatch_login_startup(tmp_path, controller_starter=starter)
    second = dispatch_login_startup(tmp_path, controller_starter=starter)
    assert before_enable["restore_reason"] == "not_registered"
    assert registered["started"] is False
    assert registered["trigger"] == LOGIN_TRIGGER
    assert registered["helper"] == RESTORE_HELPER
    assert spec["helper"] == RESTORE_HELPER
    assert first["started"] is True
    assert first["dispatched_from"] == "login_startup"
    assert first["restored_pid"] == os.getpid()
    assert second["started"] is False
    assert second["restore_reason"] == "live_owner"
    assert starts == [os.getpid()]


def test_cli_login_run_refuses_live_owner(tmp_path):
    seed_orphaned(tmp_path, pid=os.getpid(), status="running_mission")
    unbound.continuous_loop_lock_path(tmp_path).write_text(f"{os.getpid()}\n", encoding="utf-8")
    before = unbound.continuous_loop_state_path(tmp_path).read_bytes()
    enable = CliRunner().invoke(unbound.app, ["loop-login-enable", "--repo-path", str(tmp_path)])
    assert enable.exit_code == 0, enable.output
    enabled = json.loads(enable.stdout)
    assert enabled["scheduled"] is True
    assert enabled["started"] is False
    result = CliRunner().invoke(unbound.app, ["loop-login-run", "--repo-path", str(tmp_path)])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["started"] is False
    assert payload["restore_reason"] == "live_owner"
    assert unbound.continuous_loop_state_path(tmp_path).read_bytes() == before
