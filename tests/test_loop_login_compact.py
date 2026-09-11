import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from typer.testing import CliRunner

from blackhole_agent import unbound
from blackhole_agent.loop_login_audit import (
    login_audit_log_path,
    read_login_scrub_audit,
    record_login_task_scrub,
)
from blackhole_agent.loop_login_compact import (
    DEFAULT_COMPACT_RETENTION_DAYS,
    LOOP_LOGIN_COMPACT_DONE_WHEN,
    LOOP_LOGIN_COMPACT_GOAL,
    LOOP_LOGIN_COMPACT_ID,
    builtin_loop_login_compact_proof,
    compact_login_audit_tombstones,
)
from blackhole_agent.loop_login_prune import (
    DEFAULT_PRUNE_RETENTION_DAYS,
    prune_login_scrub_audit,
)
from blackhole_agent.loop_login_rollup import (
    LOOP_LOGIN_ROLLUP_GOAL,
    LOOP_LOGIN_ROLLUP_ID,
)
from blackhole_agent.loop_login_tombstone import (
    LOGIN_AUDIT_TOMBSTONE_EVENT,
    is_login_audit_tombstone,
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
            "loop_id": "login-compact-test",
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


def fresh_dead_pid(start: int = 1_000_253) -> int:
    pid = start
    while unbound.pid_is_running(pid):
        pid += 2
    return pid


def aged_iso(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat().replace("+00:00", "Z")


def ancient_tombstone(task_name: str, *, pruned_days: int) -> dict:
    return {
        "schema_version": 1,
        "event": LOGIN_AUDIT_TOMBSTONE_EVENT,
        "tombstone": True,
        "task_name": task_name,
        "repo_path": "repo",
        "reason": "registration_gone",
        "aged_out_scrubbed_at": aged_iso(pruned_days + DEFAULT_PRUNE_RETENTION_DAYS),
        "pruned_at": aged_iso(pruned_days),
        "retention_days": DEFAULT_PRUNE_RETENTION_DAYS,
    }


def test_builtin_proof_compacts_long_gone_tombstones_without_disturbing_live_owner():
    report = builtin_loop_login_compact_proof()
    assert report["ok"] is True
    assert report["action"] == "loop_login_compact"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == report["check_count"]
    assert report["checks"]["sweep_append_compacts_long_gone_tombstones"]
    assert report["checks"]["standalone_compact_drops_long_gone_tombstones"]
    assert report["checks"]["compact_keeps_unproven_tombstones_records_and_malformed"]
    assert report["checks"]["compact_is_idempotent"]
    assert report["checks"]["recorded_scrub_compacts_on_append"]
    assert report["checks"]["live_owner_not_disturbed"]
    assert report["checks"]["catalog_names_login_rollup"]


def test_selection_accepts_login_compact_and_next_family(tmp_path: Path):
    gate = assess_mission_selection(
        tmp_path,
        LOOP_LOGIN_COMPACT_GOAL,
        LOOP_LOGIN_COMPACT_DONE_WHEN,
        history=[],
    )
    assert gate.accepted is True
    assert LOOP_LOGIN_COMPACT_ID not in gate.capability_family
    nxt = assess_mission_selection(
        tmp_path,
        LOOP_LOGIN_ROLLUP_GOAL,
        "A compacted login-scrub audit trail leaves a durable rollup.",
        history=[],
    )
    assert nxt.accepted is True
    assert LOOP_LOGIN_ROLLUP_ID not in nxt.capability_family


def test_compact_drops_tombstone_whose_named_record_is_long_gone(tmp_path: Path):
    tombstone = ancient_tombstone("ancient-task", pruned_days=DEFAULT_COMPACT_RETENTION_DAYS + 10)
    path = login_audit_log_path(tmp_path)
    path.write_text(json.dumps(tombstone, sort_keys=True) + "\n", encoding="utf-8")

    report = compact_login_audit_tombstones(tmp_path)
    assert report["compacted"] is True
    assert report["reason"] == "long_gone"
    assert report["compacted_count"] == 1
    assert report["compacted_tasks"] == ["ancient-task"]

    trail = read_login_scrub_audit(tmp_path)
    assert trail["entry_count"] == 0
    assert trail["tombstone_count"] == 0


def test_compact_keeps_recent_and_unproven_tombstones(tmp_path: Path):
    recent = ancient_tombstone("recent-task", pruned_days=200)
    undated = ancient_tombstone("undated-task", pruned_days=DEFAULT_COMPACT_RETENTION_DAYS + 30)
    undated["pruned_at"] = "not-a-timestamp"
    path = login_audit_log_path(tmp_path)
    path.write_text(
        json.dumps(recent, sort_keys=True) + "\n" + json.dumps(undated, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    before = path.read_bytes()
    report = compact_login_audit_tombstones(tmp_path)
    assert report["compacted"] is False
    assert report["reason"] == "nothing_compactable"
    assert report["compacted_count"] == 0
    assert report["tombstone_count"] == 2
    assert path.read_bytes() == before
    trail = read_login_scrub_audit(tmp_path)
    assert trail["tombstone_count"] == 2


def test_prune_still_never_drops_tombstones(tmp_path: Path):
    tombstone = ancient_tombstone("ancient-task", pruned_days=DEFAULT_COMPACT_RETENTION_DAYS + 400)
    path = login_audit_log_path(tmp_path)
    path.write_text(json.dumps(tombstone, sort_keys=True) + "\n", encoding="utf-8")

    before = path.read_bytes()
    report = prune_login_scrub_audit(tmp_path)
    assert report["pruned"] is False
    assert report["reason"] == "nothing_stale"
    assert path.read_bytes() == before
    assert read_login_scrub_audit(tmp_path)["tombstone_count"] == 1


def test_sweep_append_compacts_long_gone_tombstone_and_keeps_live_owner(tmp_path: Path):
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
    tombstone = ancient_tombstone(
        "ancient-task", pruned_days=DEFAULT_COMPACT_RETENTION_DAYS + 45
    )
    login_audit_log_path(orphan_audit_root).write_text(
        json.dumps(tombstone, sort_keys=True) + "\n", encoding="utf-8"
    )
    login_startup_registration_path(orphan).unlink()

    before = state_path.read_bytes()
    swept = sweep_login_tasks_missing_registration(scheduler=scheduler)
    assert swept["swept"] == [LOGIN_TASK_NAME]
    assert swept["audit_recorded"] == 1
    trail = read_login_scrub_audit(orphan_audit_root)
    assert trail["entry_count"] == 1
    assert trail["tombstone_count"] == 0
    assert trail["entries"][0]["task_name"] == LOGIN_TASK_NAME
    assert not any(is_login_audit_tombstone(entry) for entry in trail["entries"])

    result = dispatch_login_startup(surviving, controller_starter=starter)
    assert result["started"] is False
    assert result["restore_reason"] == "live_owner"
    assert surviving_launcher.is_file()
    assert surviving_xml.is_file()
    assert load_login_startup_registration(surviving) is not None
    assert state_path.read_bytes() == before
    assert not login_audit_log_path(surviving_audit_root).exists()
    assert starts == []


def test_recorded_scrub_reports_compacted_tombstones(tmp_path: Path):
    task = {"name": LOGIN_TASK_NAME, "repo_path": str(tmp_path / "repo")}
    report = {
        "reason": "registration_gone",
        "scrubbed_paths": [str(tmp_path / "a.py"), str(tmp_path / "b.xml")],
        "kept_foreign": [],
    }
    tombstone = ancient_tombstone("ancient-task", pruned_days=DEFAULT_COMPACT_RETENTION_DAYS + 5)
    login_audit_log_path(tmp_path).write_text(
        json.dumps(tombstone, sort_keys=True) + "\n", encoding="utf-8"
    )

    recorded = record_login_task_scrub(task, report, audit_root=tmp_path)
    assert recorded["recorded"] is True
    assert recorded["audit_tombstones_compacted"] is True
    assert recorded["audit_tombstones_compacted_count"] == 1
    trail = read_login_scrub_audit(tmp_path)
    assert trail["entry_count"] == 1
    assert trail["tombstone_count"] == 0
    assert trail["entries"][0]["task_name"] == LOGIN_TASK_NAME


def test_cli_login_compact_reports_compaction(tmp_path: Path):
    tombstone = ancient_tombstone("ancient-task", pruned_days=DEFAULT_COMPACT_RETENTION_DAYS + 10)
    login_audit_log_path(tmp_path).write_text(
        json.dumps(tombstone, sort_keys=True) + "\n", encoding="utf-8"
    )
    result = CliRunner().invoke(
        unbound.app,
        ["loop-login-compact", "--repo-path", str(tmp_path), "--output-dir", str(tmp_path)],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["compacted"] is True
    assert payload["compacted_count"] == 1
    assert payload["compacted_tasks"] == ["ancient-task"]
    assert payload["reason"] == "long_gone"
    trail = read_login_scrub_audit(tmp_path)
    assert trail["tombstone_count"] == 0


def test_cli_login_compact_leaves_intact_trail_byte_identical(tmp_path: Path):
    tombstone = ancient_tombstone("recent-task", pruned_days=90)
    path = login_audit_log_path(tmp_path)
    path.write_text(json.dumps(tombstone, sort_keys=True) + "\n", encoding="utf-8")
    before = path.read_bytes()
    result = CliRunner().invoke(
        unbound.app,
        ["loop-login-compact", "--repo-path", str(tmp_path), "--output-dir", str(tmp_path)],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["compacted"] is False
    assert payload["reason"] == "nothing_compactable"
    assert path.read_bytes() == before
