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
    DEFAULT_COMPACT_RETENTION_DAYS,
    compact_login_audit_tombstones,
)
from blackhole_agent.loop_login_prune import (
    DEFAULT_PRUNE_RETENTION_DAYS,
    prune_login_scrub_audit,
)
from blackhole_agent.loop_login_rollup import (
    LOGIN_AUDIT_ROLLUP_EVENT,
    LOOP_LOGIN_ROLLUP_DONE_WHEN,
    LOOP_LOGIN_ROLLUP_GOAL,
    LOOP_LOGIN_ROLLUP_ID,
    builtin_loop_login_rollup_proof,
    is_login_audit_rollup,
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
from blackhole_agent.loop_login_tombstone import LOGIN_AUDIT_TOMBSTONE_EVENT
from blackhole_agent.loop_login_verify import (
    LOOP_LOGIN_VERIFY_GOAL,
    LOOP_LOGIN_VERIFY_ID,
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
            "loop_id": "login-rollup-test",
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


def fresh_dead_pid(start: int = 1_000_283) -> int:
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


def test_builtin_proof_leaves_durable_rollup_without_disturbing_live_owner():
    report = builtin_loop_login_rollup_proof()
    assert report["ok"] is True
    assert report["action"] == "loop_login_rollup"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == report["check_count"]
    assert report["checks"]["sweep_compaction_leaves_durable_rollup"]
    assert report["checks"]["rollup_names_count_and_span"]
    assert report["checks"]["later_compactions_merge_one_rollup_line"]
    assert report["checks"]["rollup_trail_stays_byte_identical_without_compaction"]
    assert report["checks"]["prune_never_drops_rollup"]
    assert report["checks"]["recorded_scrub_compaction_leaves_rollup"]
    assert report["checks"]["live_owner_not_disturbed"]
    assert report["checks"]["catalog_names_login_verify"]


def test_selection_accepts_login_rollup_and_next_family(tmp_path: Path):
    gate = assess_mission_selection(
        tmp_path,
        LOOP_LOGIN_ROLLUP_GOAL,
        LOOP_LOGIN_ROLLUP_DONE_WHEN,
        history=[],
    )
    assert gate.accepted is True
    assert LOOP_LOGIN_ROLLUP_ID not in gate.capability_family
    nxt = assess_mission_selection(
        tmp_path,
        LOOP_LOGIN_VERIFY_GOAL,
        "A durable login-scrub audit trail's compaction rollup is verified.",
        history=[],
    )
    assert nxt.accepted is True
    assert LOOP_LOGIN_VERIFY_ID not in nxt.capability_family


def test_compaction_writes_rollup_naming_count_and_span(tmp_path: Path):
    older = ancient_tombstone("older-task", pruned_days=DEFAULT_COMPACT_RETENTION_DAYS + 60)
    newer = ancient_tombstone("newer-task", pruned_days=DEFAULT_COMPACT_RETENTION_DAYS + 5)
    path = login_audit_log_path(tmp_path)
    path.write_text(
        json.dumps(older, sort_keys=True) + "\n" + json.dumps(newer, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    report = compact_login_audit_tombstones(tmp_path)
    assert report["compacted"] is True
    assert report["compacted_count"] == 2
    assert report["rollup_updated"] is True

    trail = read_login_scrub_audit(tmp_path)
    assert trail["entry_count"] == 1
    assert trail["tombstone_count"] == 0
    rollup = trail["tombstone_rollup"]
    assert rollup["event"] == LOGIN_AUDIT_ROLLUP_EVENT
    assert rollup["rollup"] is True
    assert rollup["compacted_count"] == 2
    assert rollup["compaction_runs"] == 1
    assert rollup["oldest_pruned_at"] == older["pruned_at"]
    assert rollup["newest_pruned_at"] == newer["pruned_at"]
    assert rollup["last_compacted_at"]


def test_later_compactions_merge_into_single_rollup_line(tmp_path: Path):
    path = login_audit_log_path(tmp_path)
    path.write_text(
        json.dumps(ancient_tombstone("first", pruned_days=DEFAULT_COMPACT_RETENTION_DAYS + 30), sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    compact_login_audit_tombstones(tmp_path)
    first_rollup = read_login_scrub_audit(tmp_path)["tombstone_rollup"]

    with path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(ancient_tombstone("second", pruned_days=DEFAULT_COMPACT_RETENTION_DAYS + 2), sort_keys=True)
            + "\n"
        )
    compact_login_audit_tombstones(tmp_path)

    trail = read_login_scrub_audit(tmp_path)
    rollups = [entry for entry in trail["entries"] if is_login_audit_rollup(entry)]
    assert len(rollups) == 1
    merged = rollups[0]
    assert merged["compacted_count"] == 2
    assert merged["compaction_runs"] == 2
    assert merged["oldest_pruned_at"] == first_rollup["oldest_pruned_at"]
    assert merged["newest_pruned_at"] > first_rollup["newest_pruned_at"]


def test_rollup_survives_prune_and_idle_compact(tmp_path: Path):
    path = login_audit_log_path(tmp_path)
    path.write_text(
        json.dumps(ancient_tombstone("gone", pruned_days=DEFAULT_COMPACT_RETENTION_DAYS + 10), sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    compact_login_audit_tombstones(tmp_path)
    before = path.read_bytes()

    pruned = prune_login_scrub_audit(tmp_path)
    assert pruned["pruned"] is False
    assert pruned["reason"] == "nothing_stale"
    compacted = compact_login_audit_tombstones(tmp_path)
    assert compacted["compacted"] is False
    assert compacted["reason"] == "nothing_compactable"
    assert path.read_bytes() == before
    assert read_login_scrub_audit(tmp_path)["tombstone_rollup"]["compacted_count"] == 1


def test_sweep_compaction_leaves_rollup_and_keeps_live_owner(tmp_path: Path):
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
    trail = read_login_scrub_audit(orphan_audit_root)
    assert trail["entry_count"] == 2
    assert trail["tombstone_count"] == 0
    rollup = trail["tombstone_rollup"]
    assert rollup["compacted_count"] == 1
    assert rollup["compaction_runs"] == 1

    result = dispatch_login_startup(surviving, controller_starter=starter)
    assert result["started"] is False
    assert result["restore_reason"] == "live_owner"
    assert surviving_launcher.is_file()
    assert surviving_xml.is_file()
    assert load_login_startup_registration(surviving) is not None
    assert state_path.read_bytes() == before
    assert not login_audit_log_path(surviving_audit_root).exists()
    assert starts == []


def test_cli_login_compact_reports_rollup(tmp_path: Path):
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
    assert payload["rollup_updated"] is True
    assert payload["rollup"]["compacted_count"] == 1
    assert payload["rollup"]["event"] == LOGIN_AUDIT_ROLLUP_EVENT
    trail = read_login_scrub_audit(tmp_path)
    assert trail["tombstone_rollup"]["compacted_count"] == 1
