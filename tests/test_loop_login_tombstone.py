import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from typer.testing import CliRunner

from blackhole_agent import unbound
from blackhole_agent.loop_login_audit import (
    login_audit_log_path,
    read_login_scrub_audit,
)
from blackhole_agent.loop_login_compact import (
    LOOP_LOGIN_COMPACT_GOAL,
    LOOP_LOGIN_COMPACT_ID,
)
from blackhole_agent.loop_login_prune import (
    DEFAULT_PRUNE_RETENTION_DAYS,
    prune_login_scrub_audit,
)
from blackhole_agent.loop_login_tombstone import (
    LOGIN_AUDIT_TOMBSTONE_EVENT,
    LOOP_LOGIN_TOMBSTONE_DONE_WHEN,
    LOOP_LOGIN_TOMBSTONE_GOAL,
    LOOP_LOGIN_TOMBSTONE_ID,
    builtin_loop_login_tombstone_proof,
    is_login_audit_tombstone,
    login_audit_tombstone_for,
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
from blackhole_agent.loop_login_sweep import sweep_login_tasks_missing_registration
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
            "loop_id": "login-tombstone-test",
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


def fresh_dead_pid(start: int = 1_000_233) -> int:
    pid = start
    while unbound.pid_is_running(pid):
        pid += 2
    return pid


def aged_iso(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat().replace("+00:00", "Z")


def test_builtin_proof_leaves_tombstones_without_disturbing_live_owner():
    report = builtin_loop_login_tombstone_proof()
    assert report["ok"] is True
    assert report["action"] == "loop_login_tombstone"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == report["check_count"]
    assert report["checks"]["pruned_record_leaves_durable_tombstone"]
    assert report["checks"]["tombstone_names_what_aged_out"]
    assert report["checks"]["tombstone_is_never_pruned"]
    assert report["checks"]["standalone_prune_writes_tombstone"]
    assert report["checks"]["live_owner_not_disturbed"]
    assert report["checks"]["catalog_names_login_compact"]


def test_selection_accepts_login_tombstone_and_next_family(tmp_path: Path):
    gate = assess_mission_selection(
        tmp_path,
        LOOP_LOGIN_TOMBSTONE_GOAL,
        LOOP_LOGIN_TOMBSTONE_DONE_WHEN,
        history=[],
    )
    assert gate.accepted is True
    assert LOOP_LOGIN_TOMBSTONE_ID not in gate.capability_family
    nxt = assess_mission_selection(
        tmp_path,
        LOOP_LOGIN_COMPACT_GOAL,
        "A durable login-scrub audit trail's tombstones are compacted.",
        history=[],
    )
    assert nxt.accepted is True
    assert LOOP_LOGIN_COMPACT_ID not in nxt.capability_family


def test_tombstone_names_what_aged_out(tmp_path: Path):
    scrubbed_at = aged_iso(DEFAULT_PRUNE_RETENTION_DAYS + 30)
    stale = {
        "event": "login_task_artifacts_scrubbed",
        "task_name": "aged-task",
        "repo_path": str(tmp_path / "repo"),
        "reason": "registration_gone",
        "scrubbed_paths": ["a", "b"],
        "scrubbed_at": scrubbed_at,
    }
    path = login_audit_log_path(tmp_path)
    path.write_text(json.dumps(stale, sort_keys=True) + "\n", encoding="utf-8")

    report = prune_login_scrub_audit(tmp_path)
    assert report["pruned"] is True
    assert report["pruned_count"] == 1
    assert report["tombstones_written"] == 1

    trail = read_login_scrub_audit(tmp_path)
    assert trail["entry_count"] == 1
    assert trail["tombstone_count"] == 1
    tombstone = trail["entries"][0]
    assert tombstone["event"] == LOGIN_AUDIT_TOMBSTONE_EVENT
    assert tombstone["tombstone"] is True
    assert tombstone["task_name"] == "aged-task"
    assert tombstone["repo_path"] == str(tmp_path / "repo")
    assert tombstone["reason"] == "registration_gone"
    assert tombstone["aged_out_scrubbed_at"] == scrubbed_at
    assert tombstone["retention_days"] == DEFAULT_PRUNE_RETENTION_DAYS
    assert tombstone["pruned_at"]


def test_tombstone_is_never_pruned_again(tmp_path: Path):
    tombstone = login_audit_tombstone_for(
        {
            "task_name": "old-task",
            "repo_path": str(tmp_path / "repo"),
            "scrubbed_at": aged_iso(DEFAULT_PRUNE_RETENTION_DAYS + 365),
        },
        pruned_at=aged_iso(200),
        retention_days=DEFAULT_PRUNE_RETENTION_DAYS,
    )
    path = login_audit_log_path(tmp_path)
    path.write_text(json.dumps(tombstone, sort_keys=True) + "\n", encoding="utf-8")

    before = path.read_bytes()
    report = prune_login_scrub_audit(tmp_path)
    assert report["pruned"] is False
    assert report["reason"] == "nothing_stale"
    assert report["pruned_count"] == 0
    assert report["tombstone_count"] == 1
    assert path.read_bytes() == before
    trail = read_login_scrub_audit(tmp_path)
    assert trail["tombstone_count"] == 1
    assert trail["entries"][0]["task_name"] == "old-task"


def test_sweep_prune_leaves_tombstone_and_keeps_live_owner(tmp_path: Path):
    starts: list[int] = []

    def starter(repo, output_dir=None, payload=None):
        starts.append(os.getpid())
        unbound.save_continuous_loop_state(
            unbound.continuous_loop_state_path(repo),
            {**(payload or {}), "status": "running_mission", "pid": os.getpid()},
        )
        return {"started": True, "pid": os.getpid()}

    orphan = tmp_path / "orphan-repo"
    orphan.mkdir()
    seed_orphaned(orphan, pid=fresh_dead_pid())
    surviving = tmp_path / "surviving-repo"
    surviving.mkdir()
    state_path = seed_orphaned(surviving, pid=os.getpid(), status="running_mission")
    unbound.continuous_loop_lock_path(surviving).write_text(f"{os.getpid()}\n", encoding="utf-8")
    scheduler = RecordingScheduler()
    register_loop_restore_at_login(orphan, scheduler=scheduler)
    register_loop_restore_at_login(surviving, scheduler=scheduler)
    surviving_launcher = login_startup_launcher_path(surviving)
    surviving_xml = login_startup_task_xml_path(surviving)
    orphan_audit_root = login_startup_registration_path(orphan).parent
    surviving_audit_root = login_startup_registration_path(surviving).parent
    stale = {
        "event": "login_task_artifacts_scrubbed",
        "task_name": "stale-task",
        "repo_path": str(orphan),
        "scrubbed_at": aged_iso(DEFAULT_PRUNE_RETENTION_DAYS + 90),
    }
    login_audit_log_path(orphan_audit_root).write_text(
        json.dumps(stale, sort_keys=True) + "\n", encoding="utf-8"
    )
    login_startup_registration_path(orphan).unlink()

    before = state_path.read_bytes()
    swept = sweep_login_tasks_missing_registration(scheduler=scheduler)
    assert swept["swept"] == [LOGIN_TASK_NAME]
    assert swept["audit_recorded"] == 1
    trail = read_login_scrub_audit(orphan_audit_root)
    assert trail["entry_count"] == 2
    assert trail["tombstone_count"] == 1
    tombstones = [entry for entry in trail["entries"] if is_login_audit_tombstone(entry)]
    assert tombstones[0]["task_name"] == "stale-task"
    assert tombstones[0]["repo_path"] == str(orphan)
    scrub_entries = [entry for entry in trail["entries"] if not is_login_audit_tombstone(entry)]
    assert scrub_entries[0]["task_name"] == LOGIN_TASK_NAME

    result = dispatch_login_startup(surviving, controller_starter=starter)
    assert result["started"] is False
    assert result["restore_reason"] == "live_owner"
    assert surviving_launcher.is_file()
    assert surviving_xml.is_file()
    assert load_login_startup_registration(surviving) is not None
    assert state_path.read_bytes() == before
    assert not login_audit_log_path(surviving_audit_root).exists()
    assert starts == []


def test_cli_login_prune_reports_tombstones(tmp_path: Path):
    stale = {
        "event": "login_task_artifacts_scrubbed",
        "task_name": "stale-task",
        "scrubbed_at": aged_iso(DEFAULT_PRUNE_RETENTION_DAYS + 5),
    }
    login_audit_log_path(tmp_path).write_text(
        json.dumps(stale, sort_keys=True) + "\n", encoding="utf-8"
    )
    result = CliRunner().invoke(
        unbound.app,
        ["loop-login-prune", "--repo-path", str(tmp_path), "--output-dir", str(tmp_path)],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["pruned"] is True
    assert payload["pruned_count"] == 1
    assert payload["tombstones_written"] == 1
    trail = read_login_scrub_audit(tmp_path)
    assert trail["tombstone_count"] == 1
    assert trail["entries"][0]["task_name"] == "stale-task"
    assert trail["entries"][0]["event"] == LOGIN_AUDIT_TOMBSTONE_EVENT
