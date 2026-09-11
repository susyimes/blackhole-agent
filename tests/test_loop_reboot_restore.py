import json
import os
from pathlib import Path

from typer.testing import CliRunner

from blackhole_agent import unbound
from blackhole_agent.loop_login_task import LOOP_LOGIN_TASK_GOAL, LOOP_LOGIN_TASK_ID
from blackhole_agent.loop_reboot_restore import (
    LOOP_REBOOT_RESTORE_DONE_WHEN,
    LOOP_REBOOT_RESTORE_GOAL,
    LOOP_REBOOT_RESTORE_ID,
    builtin_loop_reboot_restore_proof,
    health_automation_paths,
    restore_orphaned_loop_on_startup,
)
from blackhole_agent.mission_selection import assess_mission_selection


def seed_orphaned(repo: Path, *, pid: int, status: str = "orphaned") -> Path:
    path = unbound.continuous_loop_state_path(repo)
    unbound.save_continuous_loop_state(
        path,
        {
            "loop_id": "restore-test",
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


def test_builtin_proof_restores_orphan_and_spares_live_owner():
    report = builtin_loop_reboot_restore_proof()
    assert report["ok"] is True
    assert report["action"] == "loop_reboot_restore"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == report["check_count"]
    assert report["checks"]["orphaned_without_live_owner_starts"]
    assert report["checks"]["live_owner_does_not_start_second"]
    assert report["checks"]["existing_live_owner_untouched"]
    assert report["checks"]["catalog_names_login_task"]


def test_selection_accepts_restore_and_next_family(tmp_path: Path):
    gate = assess_mission_selection(
        tmp_path,
        LOOP_REBOOT_RESTORE_GOAL,
        LOOP_REBOOT_RESTORE_DONE_WHEN,
        history=[],
    )
    assert gate.accepted is True
    assert LOOP_REBOOT_RESTORE_ID not in gate.capability_family
    nxt = assess_mission_selection(
        tmp_path,
        LOOP_LOGIN_TASK_GOAL,
        "A login startup registration schedules the restore helper.",
        history=[],
    )
    assert nxt.accepted is True
    assert LOOP_LOGIN_TASK_ID not in nxt.capability_family


def test_restore_starts_only_when_orphaned_and_owner_is_gone(tmp_path):
    starts: list[int] = []

    def starter(repo, output_dir=None, payload=None):
        starts.append(os.getpid())
        unbound.save_continuous_loop_state(
            unbound.continuous_loop_state_path(repo),
            {**(payload or {}), "status": "running_mission", "pid": os.getpid()},
        )
        return {"started": True, "pid": os.getpid()}

    dead_pid = 1_000_021
    while unbound.pid_is_running(dead_pid):
        dead_pid += 2
    seed_orphaned(tmp_path, pid=dead_pid)
    health = health_automation_paths(tmp_path)[0]
    health.parent.mkdir(parents=True, exist_ok=True)
    health.write_text('{"enabled": false, "paused": true}\n', encoding="utf-8")
    health_before = health.read_bytes()
    mission_before = (tmp_path / "mission.json").read_bytes()
    first = restore_orphaned_loop_on_startup(tmp_path, controller_starter=starter)
    second = restore_orphaned_loop_on_startup(tmp_path, controller_starter=starter)
    assert first["started"] is True
    assert first["restored_pid"] == os.getpid()
    assert second["started"] is False
    assert second["restore_reason"] == "live_owner"
    assert starts == [os.getpid()]
    assert health.read_bytes() == health_before
    assert (tmp_path / "mission.json").read_bytes() == mission_before


def test_cli_restore_refuses_live_owner(tmp_path):
    seed_orphaned(tmp_path, pid=os.getpid(), status="running_mission")
    unbound.continuous_loop_lock_path(tmp_path).write_text(f"{os.getpid()}\n", encoding="utf-8")
    before = unbound.continuous_loop_state_path(tmp_path).read_bytes()
    result = CliRunner().invoke(unbound.app, ["loop-restore", "--repo-path", str(tmp_path)])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["started"] is False
    assert payload["restore_reason"] == "live_owner"
    assert unbound.continuous_loop_state_path(tmp_path).read_bytes() == before
