import json
import os
from pathlib import Path

from typer.testing import CliRunner

from blackhole_agent import unbound
from blackhole_agent.loop_login_retire import LOOP_LOGIN_RETIRE_GOAL, LOOP_LOGIN_RETIRE_ID
from blackhole_agent.loop_login_stale import (
    LOOP_LOGIN_STALE_DONE_WHEN,
    LOOP_LOGIN_STALE_GOAL,
    LOOP_LOGIN_STALE_ID,
    builtin_loop_login_stale_proof,
    repair_login_startup_stale,
)
from blackhole_agent.loop_login_task import (
    LOGIN_TRIGGER,
    RESTORE_HELPER,
    build_login_restore_command,
    dispatch_login_startup,
    load_login_startup_registration,
    login_startup_launcher_path,
    login_startup_registration_path,
    register_loop_restore_at_login,
    render_login_restore_launcher,
)
from blackhole_agent.mission_selection import assess_mission_selection


def seed_orphaned(repo: Path, *, pid: int, status: str = "orphaned") -> Path:
    path = unbound.continuous_loop_state_path(repo)
    unbound.save_continuous_loop_state(
        path,
        {
            "loop_id": "login-stale-test",
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


def stale_registration(repo: Path, **changes) -> None:
    path = login_startup_registration_path(repo)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.update(changes)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_builtin_proof_repoints_stale_without_doubling():
    report = builtin_loop_login_stale_proof()
    assert report["ok"] is True
    assert report["action"] == "loop_login_stale"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == report["check_count"]
    assert report["checks"]["stale_command_is_repaired_without_start"]
    assert report["checks"]["stale_launcher_is_repaired_without_start"]
    assert report["checks"]["stale_repair_does_not_double_live_owner"]
    assert report["checks"]["catalog_names_login_retire"]


def test_selection_accepts_login_stale_and_next_family(tmp_path: Path):
    gate = assess_mission_selection(
        tmp_path,
        LOOP_LOGIN_STALE_GOAL,
        LOOP_LOGIN_STALE_DONE_WHEN,
        history=[],
    )
    assert gate.accepted is True
    assert LOOP_LOGIN_STALE_ID not in gate.capability_family
    nxt = assess_mission_selection(
        tmp_path,
        LOOP_LOGIN_RETIRE_GOAL,
        "A login startup registration whose repo was deleted is unscheduled.",
        history=[],
    )
    assert nxt.accepted is True
    assert LOOP_LOGIN_RETIRE_ID not in nxt.capability_family


def test_moved_repo_command_and_launcher_are_repointed_without_starting(tmp_path):
    starts: list[int] = []

    def starter(repo, output_dir=None, payload=None):
        starts.append(os.getpid())
        unbound.save_continuous_loop_state(
            unbound.continuous_loop_state_path(repo),
            {**(payload or {}), "status": "running_mission", "pid": os.getpid()},
        )
        return {"started": True, "pid": os.getpid()}

    dead_pid = 1_000_113
    while unbound.pid_is_running(dead_pid):
        dead_pid += 2
    repo = tmp_path / "before-move"
    repo.mkdir()
    seed_orphaned(repo, pid=dead_pid)
    register_loop_restore_at_login(repo)
    moved = tmp_path / "after-move"
    repo.rename(moved)
    repo = moved
    stale = dispatch_login_startup(repo, controller_starter=starter)
    repaired = repair_login_startup_stale(repo)
    spec = load_login_startup_registration(repo)
    launcher = login_startup_launcher_path(repo).read_text(encoding="utf-8")
    first = dispatch_login_startup(repo, controller_starter=starter)
    assert stale["started"] is False
    assert stale["restore_reason"] == "stale_command"
    assert repaired["started"] is False
    assert repaired["repair_reason"] == "stale_command"
    assert repaired["stale_repair"] is True
    assert repaired["scheduled"] is True
    assert spec is not None
    assert spec["trigger"] == LOGIN_TRIGGER
    assert spec["helper"] == RESTORE_HELPER
    assert spec["repo_path"] == str(repo.resolve())
    assert launcher == render_login_restore_launcher(repo, unbound.mission_root(repo))
    assert first["started"] is True
    assert first["dispatched_from"] == "login_startup"
    assert starts == [os.getpid()]

    stale_registration(
        repo,
        command=[str(part) for part in build_login_restore_command(tmp_path / "elsewhere")],
        repo_path=str((tmp_path / "elsewhere").resolve()),
    )
    again_stale = dispatch_login_startup(repo, controller_starter=starter)
    again = repair_login_startup_stale(repo)
    loaded = load_login_startup_registration(repo)
    assert again_stale["restore_reason"] == "stale_command"
    assert again["started"] is False
    assert again["repair_reason"] == "stale_command"
    assert again["scheduled"] is True
    assert loaded is not None
    assert loaded["repo_path"] == str(repo.resolve())
    assert starts == [os.getpid()]


def test_cli_login_stale_refuses_to_start_beside_live_owner(tmp_path):
    seed_orphaned(tmp_path, pid=os.getpid(), status="running_mission")
    unbound.continuous_loop_lock_path(tmp_path).write_text(f"{os.getpid()}\n", encoding="utf-8")
    register_loop_restore_at_login(tmp_path)
    moved_repo = tmp_path.parent / f"{tmp_path.name}-moved"
    stale_registration(
        tmp_path,
        command=[str(part) for part in build_login_restore_command(moved_repo)],
        repo_path=str(moved_repo.resolve()),
    )
    before = unbound.continuous_loop_state_path(tmp_path).read_bytes()
    repair = CliRunner().invoke(unbound.app, ["loop-login-stale", "--repo-path", str(tmp_path)])
    assert repair.exit_code == 0, repair.output
    repaired = json.loads(repair.stdout)
    assert repaired["scheduled"] is True
    assert repaired["started"] is False
    assert repaired["repair_reason"] == "stale_command"
    result = CliRunner().invoke(unbound.app, ["loop-login-run", "--repo-path", str(tmp_path)])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["started"] is False
    assert payload["restore_reason"] == "live_owner"
    assert unbound.continuous_loop_state_path(tmp_path).read_bytes() == before
