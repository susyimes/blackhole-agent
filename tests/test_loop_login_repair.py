import json
import os
from pathlib import Path

from typer.testing import CliRunner

from blackhole_agent import unbound
from blackhole_agent.loop_login_drift import LOOP_LOGIN_DRIFT_GOAL, LOOP_LOGIN_DRIFT_ID
from blackhole_agent.loop_login_repair import (
    LOOP_LOGIN_REPAIR_DONE_WHEN,
    LOOP_LOGIN_REPAIR_GOAL,
    LOOP_LOGIN_REPAIR_ID,
    builtin_loop_login_repair_proof,
    repair_login_startup_registration,
)
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
            "loop_id": "login-repair-test",
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


def disable_registration(repo: Path) -> None:
    path = login_startup_registration_path(repo)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["enabled"] = False
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_builtin_proof_repairs_missing_and_disabled_without_doubling():
    report = builtin_loop_login_repair_proof()
    assert report["ok"] is True
    assert report["action"] == "loop_login_repair"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == report["check_count"]
    assert report["checks"]["missing_registration_is_repaired_without_start"]
    assert report["checks"]["disabled_registration_is_repaired_without_start"]
    assert report["checks"]["repair_does_not_double_live_owner"]
    assert report["checks"]["catalog_names_login_drift"]


def test_selection_accepts_login_repair_and_next_family(tmp_path: Path):
    gate = assess_mission_selection(
        tmp_path,
        LOOP_LOGIN_REPAIR_GOAL,
        LOOP_LOGIN_REPAIR_DONE_WHEN,
        history=[],
    )
    assert gate.accepted is True
    assert LOOP_LOGIN_REPAIR_ID not in gate.capability_family
    nxt = assess_mission_selection(
        tmp_path,
        LOOP_LOGIN_DRIFT_GOAL,
        "A drifted login startup registration with the wrong trigger or helper is repaired.",
        history=[],
    )
    assert nxt.accepted is True
    assert LOOP_LOGIN_DRIFT_ID not in nxt.capability_family


def test_missing_and_disabled_login_are_repaired_without_starting(tmp_path):
    starts: list[int] = []

    def starter(repo, output_dir=None, payload=None):
        starts.append(os.getpid())
        unbound.save_continuous_loop_state(
            unbound.continuous_loop_state_path(repo),
            {**(payload or {}), "status": "running_mission", "pid": os.getpid()},
        )
        return {"started": True, "pid": os.getpid()}

    dead_pid = 1_000_081
    while unbound.pid_is_running(dead_pid):
        dead_pid += 2
    seed_orphaned(tmp_path, pid=dead_pid)
    missing = dispatch_login_startup(tmp_path, controller_starter=starter)
    repaired = repair_login_startup_registration(tmp_path)
    spec = load_login_startup_registration(tmp_path)
    first = dispatch_login_startup(tmp_path, controller_starter=starter)
    assert missing["restore_reason"] == "not_registered"
    assert repaired["started"] is False
    assert repaired["repair_reason"] == "missing"
    assert repaired["scheduled"] is True
    assert spec is not None
    assert spec["enabled"] is True
    assert spec["trigger"] == LOGIN_TRIGGER
    assert spec["helper"] == RESTORE_HELPER
    assert first["started"] is True
    assert first["dispatched_from"] == "login_startup"
    assert starts == [os.getpid()]

    disable_registration(tmp_path)
    disabled = dispatch_login_startup(tmp_path, controller_starter=starter)
    again = repair_login_startup_registration(tmp_path)
    loaded = load_login_startup_registration(tmp_path)
    assert disabled["restore_reason"] == "not_enabled"
    assert again["started"] is False
    assert again["repair_reason"] == "disabled"
    assert again["scheduled"] is True
    assert loaded is not None
    assert loaded["enabled"] is True
    assert starts == [os.getpid()]


def test_cli_login_repair_refuses_to_start_beside_live_owner(tmp_path):
    seed_orphaned(tmp_path, pid=os.getpid(), status="running_mission")
    unbound.continuous_loop_lock_path(tmp_path).write_text(f"{os.getpid()}\n", encoding="utf-8")
    register_loop_restore_at_login(tmp_path)
    disable_registration(tmp_path)
    before = unbound.continuous_loop_state_path(tmp_path).read_bytes()
    repair = CliRunner().invoke(unbound.app, ["loop-login-repair", "--repo-path", str(tmp_path)])
    assert repair.exit_code == 0, repair.output
    repaired = json.loads(repair.stdout)
    assert repaired["scheduled"] is True
    assert repaired["started"] is False
    assert repaired["repair_reason"] == "disabled"
    result = CliRunner().invoke(unbound.app, ["loop-login-run", "--repo-path", str(tmp_path)])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["started"] is False
    assert payload["restore_reason"] == "live_owner"
    assert unbound.continuous_loop_state_path(tmp_path).read_bytes() == before
