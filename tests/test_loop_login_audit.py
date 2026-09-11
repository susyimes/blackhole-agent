import json
import os
from pathlib import Path

from typer.testing import CliRunner

from blackhole_agent import unbound
from blackhole_agent.loop_login_audit import (
    LOOP_LOGIN_AUDIT_DONE_WHEN,
    LOOP_LOGIN_AUDIT_GOAL,
    LOOP_LOGIN_AUDIT_ID,
    builtin_loop_login_audit_proof,
    login_audit_log_path,
    read_login_scrub_audit,
    record_login_task_scrub,
)
from blackhole_agent.loop_login_prune import LOOP_LOGIN_PRUNE_GOAL, LOOP_LOGIN_PRUNE_ID
from blackhole_agent.loop_login_scrub import (
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
            "loop_id": "login-audit-test",
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


def fresh_dead_pid(start: int = 1_000_193) -> int:
    pid = start
    while unbound.pid_is_running(pid):
        pid += 2
    return pid


def test_builtin_proof_records_swept_scrub_without_disturbing_live_owner():
    report = builtin_loop_login_audit_proof()
    assert report["ok"] is True
    assert report["action"] == "loop_login_audit"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == report["check_count"]
    assert report["checks"]["swept_scrub_is_recorded_durably"]
    assert report["checks"]["live_owner_not_disturbed"]
    assert report["checks"]["operator_can_reconcile_from_trail"]
    assert report["checks"]["residue_scrub_is_recorded"]
    assert report["checks"]["foreign_content_records_nothing"]
    assert report["checks"]["catalog_names_login_prune"]


def test_selection_accepts_login_audit_and_next_family(tmp_path: Path):
    gate = assess_mission_selection(
        tmp_path,
        LOOP_LOGIN_AUDIT_GOAL,
        LOOP_LOGIN_AUDIT_DONE_WHEN,
        history=[],
    )
    assert gate.accepted is True
    assert LOOP_LOGIN_AUDIT_ID not in gate.capability_family
    nxt = assess_mission_selection(
        tmp_path,
        LOOP_LOGIN_PRUNE_GOAL,
        "A durable login-scrub audit trail's stale records are pruned once they age out.",
        history=[],
    )
    assert nxt.accepted is True
    assert LOOP_LOGIN_PRUNE_ID not in nxt.capability_family


def test_sweep_records_scrub_in_durable_audit_trail(tmp_path: Path):
    starts: list[int] = []

    def starter(repo, output_dir=None, payload=None):
        starts.append(os.getpid())
        unbound.save_continuous_loop_state(
            unbound.continuous_loop_state_path(repo),
            {**(payload or {}), "status": "running_mission", "pid": os.getpid()},
        )
        return {"started": True, "pid": os.getpid()}

    dead_pid = fresh_dead_pid()
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
    orphan_audit_root = login_startup_registration_path(orphan).parent
    surviving_audit_root = login_startup_registration_path(surviving).parent
    login_startup_registration_path(orphan).unlink()

    before = state_path.read_bytes()
    swept = sweep_login_tasks_missing_registration(scheduler=scheduler)
    assert swept["swept"] == [LOGIN_TASK_NAME]
    assert swept["scrubbed_count"] == 2
    assert swept["audit_recorded"] == 1
    audit_path = login_audit_log_path(orphan_audit_root)
    assert audit_path.is_file()
    assert swept["audit_paths"] == [str(audit_path)]

    trail = read_login_scrub_audit(orphan_audit_root)
    assert trail["entry_count"] == 1
    assert trail["malformed_count"] == 0
    entry = trail["entries"][0]
    assert entry["event"] == "login_task_artifacts_scrubbed"
    assert entry["task_name"] == LOGIN_TASK_NAME
    assert entry["reason"] == "registration_gone"
    assert str(orphan_launcher) in entry["scrubbed_paths"]
    assert str(orphan_xml) in entry["scrubbed_paths"]
    assert entry["kept_foreign"] == []
    assert entry["scrubbed_at"]
    assert not orphan_launcher.exists()
    assert not orphan_xml.exists()

    again = sweep_login_tasks_missing_registration(scheduler=scheduler)
    assert again["swept"] == []
    assert again["audit_recorded"] == 0
    assert read_login_scrub_audit(orphan_audit_root)["entry_count"] == 1

    result = dispatch_login_startup(surviving, controller_starter=starter)
    assert result["started"] is False
    assert result["restore_reason"] == "live_owner"
    assert surviving_launcher.is_file()
    assert surviving_xml.is_file()
    assert load_login_startup_registration(surviving) is not None
    assert state_path.read_bytes() == before
    assert not login_audit_log_path(surviving_audit_root).exists()
    assert starts == []


def test_record_appends_one_jsonl_entry_per_scrub(tmp_path: Path):
    task = {"name": LOGIN_TASK_NAME, "repo_path": str(tmp_path / "repo")}
    report = {
        "reason": "registration_gone",
        "scrubbed_paths": [str(tmp_path / "a.py"), str(tmp_path / "b.xml")],
        "kept_foreign": [],
    }
    first = record_login_task_scrub(task, report, audit_root=tmp_path)
    second = record_login_task_scrub(task, report, audit_root=tmp_path)
    assert first["recorded"] is True
    assert second["recorded"] is True
    trail = read_login_scrub_audit(tmp_path)
    assert trail["entry_count"] == 2
    assert trail["entries"][0]["task_name"] == LOGIN_TASK_NAME

    empty = record_login_task_scrub(
        task, {"reason": "not_swept", "scrubbed_paths": []}, audit_root=tmp_path
    )
    assert empty["recorded"] is False
    assert empty["reason"] == "nothing_scrubbed"
    assert read_login_scrub_audit(tmp_path)["entry_count"] == 2


def test_read_tolerates_missing_and_malformed_trail(tmp_path: Path):
    missing = read_login_scrub_audit(tmp_path / "nope")
    assert missing["entry_count"] == 0
    assert missing["entries"] == []
    path = login_audit_log_path(tmp_path)
    path.write_text(
        '{"event": "login_task_artifacts_scrubbed"}\nbroken line\n[1, 2]\n',
        encoding="utf-8",
    )
    trail = read_login_scrub_audit(tmp_path)
    assert trail["entry_count"] == 1
    assert trail["malformed_count"] == 2


def test_foreign_content_scrub_records_nothing(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    seed_orphaned(repo, pid=fresh_dead_pid(1_000_195))
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
    assert report["scrubbed_count"] == 0
    assert report["audit_recorded"] is False
    assert launcher.is_file() and xml.is_file()
    audit_root = login_startup_registration_path(repo).parent
    assert not login_audit_log_path(audit_root).exists()


def test_residue_scrub_records_audit_entries(tmp_path: Path):
    repo = tmp_path / "already-swept-repo"
    repo.mkdir()
    seed_orphaned(repo, pid=fresh_dead_pid(1_000_197))
    scheduler = RecordingScheduler()
    register_loop_restore_at_login(repo, scheduler=scheduler)
    launcher = login_startup_launcher_path(repo)
    xml = login_startup_task_xml_path(repo)
    login_startup_registration_path(repo).unlink()
    scheduler.tasks.clear()

    residue = scrub_swept_login_task_artifacts(tmp_path)
    assert residue["scrubbed_count"] == 2
    assert residue["audit_recorded"] == 1
    assert residue["audit_path"] == str(login_audit_log_path(tmp_path))
    trail = read_login_scrub_audit(tmp_path)
    assert trail["entry_count"] == 1
    entry = trail["entries"][0]
    assert str(launcher) in entry["scrubbed_paths"]
    assert str(xml) in entry["scrubbed_paths"]
    assert not launcher.exists()
    assert not xml.exists()
    again = scrub_swept_login_task_artifacts(tmp_path)
    assert again["scrubbed_count"] == 0
    assert again["audit_recorded"] == 0
    assert read_login_scrub_audit(tmp_path)["entry_count"] == 1


def test_cli_login_audit_shows_recorded_trail(tmp_path: Path):
    repo = tmp_path / "orphan-repo"
    repo.mkdir()
    seed_orphaned(repo, pid=fresh_dead_pid(1_000_199))
    scheduler = FileLoginScheduler(tmp_path / "scheduler-root")
    register_loop_restore_at_login(repo, scheduler=scheduler)
    launcher = login_startup_launcher_path(repo)
    xml = login_startup_task_xml_path(repo)
    login_startup_registration_path(repo).unlink()

    scrubbed = CliRunner().invoke(
        unbound.app,
        ["loop-login-scrub", "--repo-path", str(repo)],
    )
    assert scrubbed.exit_code == 0, scrubbed.output
    assert json.loads(scrubbed.stdout)["audit_recorded"] == 1

    result = CliRunner().invoke(
        unbound.app,
        ["loop-login-audit", "--repo-path", str(repo)],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["action"] == "audit_read"
    assert payload["entry_count"] == 1
    entry = payload["entries"][0]
    assert entry["task_name"] == LOGIN_TASK_NAME
    assert str(launcher) in entry["scrubbed_paths"]
    assert str(xml) in entry["scrubbed_paths"]
