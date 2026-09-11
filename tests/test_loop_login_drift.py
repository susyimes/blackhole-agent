import json
import os
from pathlib import Path

from typer.testing import CliRunner

from blackhole_agent import unbound
from blackhole_agent.loop_login_drift import (
    LOOP_LOGIN_DRIFT_DONE_WHEN,
    LOOP_LOGIN_DRIFT_GOAL,
    LOOP_LOGIN_DRIFT_ID,
    builtin_loop_login_drift_proof,
    repair_login_startup_drift,
)
from blackhole_agent.loop_login_stale import LOOP_LOGIN_STALE_GOAL, LOOP_LOGIN_STALE_ID
from blackhole_agent.loop_login_task import (
    LOGIN_TRIGGER,
    RESTORE_HELPER,
    dispatch_login_startup,
    load_login_startup_registration,
    login_startup_registration_path,
    register_loop_restore_at_login,
)
from blackhole_agent.mission_selection import assess_mission_selection


def seed_orphaned(repo: Path, *, pid: int, status: str = "orphaned") -> Path:
    path = unbound.continuous_loop_state_path(repo)
    unbound.save_continuous_loop_state(
        path,
        {
            "loop_id": "login-drift-test",
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


def drift_registration(repo: Path, **changes) -> None:
    path = login_startup_registration_path(repo)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.update(changes)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_builtin_proof_repairs_drift_without_doubling():
    report = builtin_loop_login_drift_proof()
    assert report["ok"] is True
    assert report["action"] == "loop_login_drift"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == report["check_count"]
    assert report["checks"]["wrong_trigger_is_repaired_without_start"]
    assert report["checks"]["wrong_helper_is_repaired_without_start"]
    assert report["checks"]["drift_repair_does_not_double_live_owner"]
    assert report["checks"]["catalog_names_login_stale"]


def test_selection_accepts_login_drift_and_next_family(tmp_path: Path):
    gate = assess_mission_selection(
        tmp_path,
        LOOP_LOGIN_DRIFT_GOAL,
        LOOP_LOGIN_DRIFT_DONE_WHEN,
        history=[],
    )
    assert gate.accepted is True
    assert LOOP_LOGIN_DRIFT_ID not in gate.capability_family
    nxt = assess_mission_selection(
        tmp_path,
        LOOP_LOGIN_STALE_GOAL,
        "A stale login startup registration whose command or launcher points at a moved repo is repaired.",
        history=[],
    )
    assert nxt.accepted is True
    assert LOOP_LOGIN_STALE_ID not in nxt.capability_family


def test_wrong_trigger_and_helper_are_repaired_without_starting(tmp_path):
    starts: list[int] = []

    def starter(repo, output_dir=None, payload=None):
        starts.append(os.getpid())
        unbound.save_continuous_loop_state(
            unbound.continuous_loop_state_path(repo),
            {**(payload or {}), "status": "running_mission", "pid": os.getpid()},
        )
        return {"started": True, "pid": os.getpid()}

    dead_pid = 1_000_093
    while unbound.pid_is_running(dead_pid):
        dead_pid += 2
    seed_orphaned(tmp_path, pid=dead_pid)
    register_loop_restore_at_login(tmp_path)
    drift_registration(tmp_path, trigger="on_schedule")
    drifted = dispatch_login_startup(tmp_path, controller_starter=starter)
    repaired = repair_login_startup_drift(tmp_path)
    spec = load_login_startup_registration(tmp_path)
    first = dispatch_login_startup(tmp_path, controller_starter=starter)
    assert drifted["restore_reason"] == "wrong_trigger"
    assert repaired["started"] is False
    assert repaired["repair_reason"] == "wrong_trigger"
    assert repaired["scheduled"] is True
    assert spec is not None
    assert spec["trigger"] == LOGIN_TRIGGER
    assert spec["helper"] == RESTORE_HELPER
    assert first["started"] is True
    assert first["dispatched_from"] == "login_startup"
    assert starts == [os.getpid()]

    drift_registration(tmp_path, helper="blackhole_agent.unbound:noop")
    helper_dispatch = dispatch_login_startup(tmp_path, controller_starter=starter)
    again = repair_login_startup_drift(tmp_path)
    loaded = load_login_startup_registration(tmp_path)
    assert helper_dispatch["restore_reason"] == "wrong_helper"
    assert again["started"] is False
    assert again["repair_reason"] == "wrong_helper"
    assert again["scheduled"] is True
    assert loaded is not None
    assert loaded["helper"] == RESTORE_HELPER
    assert starts == [os.getpid()]


def test_cli_login_drift_refuses_to_start_beside_live_owner(tmp_path):
    seed_orphaned(tmp_path, pid=os.getpid(), status="running_mission")
    unbound.continuous_loop_lock_path(tmp_path).write_text(f"{os.getpid()}\n", encoding="utf-8")
    register_loop_restore_at_login(tmp_path)
    drift_registration(tmp_path, trigger="at_startup", helper="other.module:helper")
    before = unbound.continuous_loop_state_path(tmp_path).read_bytes()
    repair = CliRunner().invoke(unbound.app, ["loop-login-drift", "--repo-path", str(tmp_path)])
    assert repair.exit_code == 0, repair.output
    repaired = json.loads(repair.stdout)
    assert repaired["scheduled"] is True
    assert repaired["started"] is False
    assert repaired["repair_reason"] == "wrong_trigger"
    result = CliRunner().invoke(unbound.app, ["loop-login-run", "--repo-path", str(tmp_path)])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["started"] is False
    assert payload["restore_reason"] == "live_owner"
    assert unbound.continuous_loop_state_path(tmp_path).read_bytes() == before
