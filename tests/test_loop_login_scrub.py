import json
import os
from pathlib import Path

from typer.testing import CliRunner

from blackhole_agent import unbound
from blackhole_agent.loop_login_audit import LOOP_LOGIN_AUDIT_GOAL, LOOP_LOGIN_AUDIT_ID
from blackhole_agent.loop_login_scrub import (
    LOOP_LOGIN_SCRUB_DONE_WHEN,
    LOOP_LOGIN_SCRUB_GOAL,
    LOOP_LOGIN_SCRUB_ID,
    builtin_loop_login_scrub_proof,
    scrub_login_task_artifacts,
    scrub_swept_login_task_artifacts,
)
from blackhole_agent.loop_login_sweep import (
    FileLoginScheduler,
    sweep_login_tasks_missing_registration,
)
from blackhole_agent.loop_login_task import (
    LOGIN_TASK_NAME,
    dispatch_login_startup,
    load_login_startup_registration,
    login_startup_launcher_path,
    login_startup_registration_path,
    login_startup_task_xml_path,
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
            "loop_id": "login-scrub-test",
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


def test_builtin_proof_scrubs_swept_artifacts_without_disturbing_live_owner():
    report = builtin_loop_login_scrub_proof()
    assert report["ok"] is True
    assert report["action"] == "loop_login_scrub"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == report["check_count"]
    assert report["checks"]["swept_task_artifacts_are_scrubbed"]
    assert report["checks"]["live_owner_artifacts_are_kept"]
    assert report["checks"]["foreign_content_artifacts_are_kept"]
    assert report["checks"]["already_swept_residue_is_scrubbed"]
    assert report["checks"]["catalog_names_login_audit"]


def test_selection_accepts_login_scrub_and_next_family(tmp_path: Path):
    gate = assess_mission_selection(
        tmp_path,
        LOOP_LOGIN_SCRUB_GOAL,
        LOOP_LOGIN_SCRUB_DONE_WHEN,
        history=[],
    )
    assert gate.accepted is True
    assert LOOP_LOGIN_SCRUB_ID not in gate.capability_family
    nxt = assess_mission_selection(
        tmp_path,
        LOOP_LOGIN_AUDIT_GOAL,
        "A swept login task's scrubbed artifacts are recorded durably.",
        history=[],
    )
    assert nxt.accepted is True
    assert LOOP_LOGIN_AUDIT_ID not in nxt.capability_family


def test_sweep_scrubs_record_gone_artifacts_and_keeps_surviving_repo(tmp_path: Path):
    starts: list[int] = []

    def starter(repo, output_dir=None, payload=None):
        starts.append(os.getpid())
        unbound.save_continuous_loop_state(
            unbound.continuous_loop_state_path(repo),
            {**(payload or {}), "status": "running_mission", "pid": os.getpid()},
        )
        return {"started": True, "pid": os.getpid()}

    dead_pid = 1_000_173
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
    orphan_launcher = login_startup_launcher_path(orphan)
    orphan_xml = login_startup_task_xml_path(orphan)
    surviving_launcher = login_startup_launcher_path(surviving)
    surviving_xml = login_startup_task_xml_path(surviving)
    assert orphan_launcher.is_file() and orphan_xml.is_file()
    login_startup_registration_path(orphan).unlink()

    before = state_path.read_bytes()
    swept = sweep_login_tasks_missing_registration(scheduler=scheduler)
    assert swept["action"] == "sweep"
    assert swept["swept"] == [LOGIN_TASK_NAME]
    assert swept["scrubbed_count"] == 2
    assert not orphan_launcher.exists()
    assert not orphan_xml.exists()
    assert str(orphan_launcher) in swept["scrubbed_artifacts"][LOGIN_TASK_NAME]
    assert str(orphan_xml) in swept["scrubbed_artifacts"][LOGIN_TASK_NAME]
    assert surviving_launcher.is_file()
    assert surviving_xml.is_file()
    assert load_login_startup_registration(surviving) is not None
    assert state_path.read_bytes() == before

    result = dispatch_login_startup(surviving, controller_starter=starter)
    assert result["started"] is False
    assert result["restore_reason"] == "live_owner"
    assert starts == []

    again = sweep_login_tasks_missing_registration(scheduler=scheduler)
    assert again["swept"] == []
    assert again["scrubbed_count"] == 0


def test_scrub_refuses_task_whose_registration_record_still_exists(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    seed_orphaned(repo, pid=1_000_175)
    register_loop_restore_at_login(repo)
    task = load_login_startup_registration(repo)
    assert task is not None
    report = scrub_login_task_artifacts(task)
    assert report["skipped"] is True
    assert report["reason"] == "not_swept"
    assert report["scrubbed_count"] == 0
    assert login_startup_launcher_path(repo).is_file()
    assert login_startup_task_xml_path(repo).is_file()


def test_scrub_keeps_foreign_content_under_well_known_names(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    dead_pid = 1_000_177
    while unbound.pid_is_running(dead_pid):
        dead_pid += 2
    seed_orphaned(repo, pid=dead_pid)
    scheduler = RecordingScheduler()
    register_loop_restore_at_login(repo, scheduler=scheduler)
    task = load_login_startup_registration(repo)
    assert task is not None
    launcher = login_startup_launcher_path(repo)
    xml = login_startup_task_xml_path(repo)
    launcher.write_text("print('another application')\n", encoding="utf-8")
    xml.write_text("<other>not ours</other>\n", encoding="utf-8")
    login_startup_registration_path(repo).unlink()
    report = scrub_login_task_artifacts(task)
    assert report["reason"] == "registration_gone"
    assert report["scrubbed_count"] == 0
    assert set(report["kept_foreign"]) == {str(launcher), str(xml)}
    assert launcher.is_file() and xml.is_file()


def test_scrub_residue_removes_artifacts_of_already_swept_task(tmp_path: Path):
    repo = tmp_path / "already-swept-repo"
    repo.mkdir()
    dead_pid = 1_000_179
    while unbound.pid_is_running(dead_pid):
        dead_pid += 2
    seed_orphaned(repo, pid=dead_pid)
    scheduler = RecordingScheduler()
    register_loop_restore_at_login(repo, scheduler=scheduler)
    launcher = login_startup_launcher_path(repo)
    xml = login_startup_task_xml_path(repo)
    login_startup_registration_path(repo).unlink()
    scheduler.tasks.clear()

    residue = scrub_swept_login_task_artifacts(tmp_path)
    assert residue["action"] == "scrub_residue"
    assert residue["started"] is False
    assert residue["scrubbed"] is True
    assert residue["scrubbed_count"] == 2
    assert not launcher.exists()
    assert not xml.exists()
    again = scrub_swept_login_task_artifacts(tmp_path)
    assert again["scrubbed_count"] == 0


def test_cli_login_scrub_removes_residue_artifacts(tmp_path: Path):
    repo = tmp_path / "orphan-repo"
    repo.mkdir()
    dead_pid = 1_000_181
    while unbound.pid_is_running(dead_pid):
        dead_pid += 2
    seed_orphaned(repo, pid=dead_pid)
    register_loop_restore_at_login(repo, scheduler=FileLoginScheduler(tmp_path / "scheduler-root"))
    launcher = login_startup_launcher_path(repo)
    xml = login_startup_task_xml_path(repo)
    login_startup_registration_path(repo).unlink()

    result = CliRunner().invoke(
        unbound.app,
        ["loop-login-scrub", "--repo-path", str(repo)],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["action"] == "scrub_residue"
    assert payload["started"] is False
    assert payload["scrubbed"] is True
    assert payload["scrubbed_count"] == 2
    assert not launcher.exists()
    assert not xml.exists()
