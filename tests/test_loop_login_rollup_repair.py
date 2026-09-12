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
from blackhole_agent.loop_login_prune import DEFAULT_PRUNE_RETENTION_DAYS
from blackhole_agent.loop_login_rollup import (
    LOGIN_AUDIT_ROLLUP_EVENT,
    is_login_audit_rollup,
)
from blackhole_agent.loop_login_rollup_journal import (
    LOOP_LOGIN_ROLLUP_JOURNAL_GOAL,
    LOOP_LOGIN_ROLLUP_JOURNAL_ID,
)
from blackhole_agent.loop_login_rollup_repair import (
    LOOP_LOGIN_ROLLUP_REPAIR_DONE_WHEN,
    LOOP_LOGIN_ROLLUP_REPAIR_GOAL,
    LOOP_LOGIN_ROLLUP_REPAIR_ID,
    builtin_loop_login_rollup_repair_proof,
    repair_login_audit_rollup,
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
from blackhole_agent.loop_login_verify import verify_login_audit_rollup
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
            "loop_id": "login-rollup-repair-test",
            "status": status,
            "pid": pid,
            "orphaned_from_status": "running_mission" if status == "orphaned" else "",
            "current_mission_id": "unfinished",
            "current_state_path": str(repo / "mission.json"),
            "next_wake_at": "",
            "last_error": "preserve diagnostic",
            "stop_reason": "controller_process_missing" if status == "orphaned" else "operator_stop",
        },
    )
    return path


def aged_iso(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat().replace("+00:00", "Z")


def tombstone(task_name: str, *, pruned_days: int) -> dict:
    return {
        "schema_version": 1,
        "event": LOGIN_AUDIT_TOMBSTONE_EVENT,
        "tombstone": True,
        "task_name": task_name,
        "reason": "registration_gone",
        "aged_out_scrubbed_at": aged_iso(pruned_days + DEFAULT_PRUNE_RETENTION_DAYS),
        "pruned_at": aged_iso(pruned_days),
        "retention_days": DEFAULT_PRUNE_RETENTION_DAYS,
    }


def rollup(**overrides) -> dict:
    record = {
        "schema_version": 1,
        "event": LOGIN_AUDIT_ROLLUP_EVENT,
        "rollup": True,
        "compacted_count": 2,
        "compaction_runs": 2,
        "oldest_pruned_at": aged_iso(400),
        "newest_pruned_at": aged_iso(380),
        "last_compacted_at": aged_iso(15),
    }
    record.update(overrides)
    return record


def dead_pid() -> int:
    pid = 1_000_313
    while unbound.pid_is_running(pid):
        pid += 2
    return pid


def test_builtin_proof_corrects_drifted_rollup_without_disturbing_live_owner():
    report = builtin_loop_login_rollup_repair_proof()
    assert report["ok"] is True
    assert report["action"] == "loop_login_rollup_repair"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == report["check_count"]
    assert report["checks"]["drifted_rollup_is_corrected_against_trail"]
    assert report["checks"]["intact_rollup_is_left_byte_identical"]
    assert report["checks"]["duplicate_rollups_merge_back_to_one_line"]
    assert report["checks"]["inverted_span_is_reordered"]
    assert report["checks"]["unparseable_span_edge_is_restored"]
    assert report["checks"]["span_covering_survivor_is_clamped"]
    assert report["checks"]["unrepairable_span_is_reported_never_rewritten"]
    assert report["checks"]["compacted_trail_needs_no_repair"]
    assert report["checks"]["live_owner_not_disturbed"]
    assert report["checks"]["catalog_names_login_rollup_journal"]


def test_selection_accepts_rollup_repair_and_next_family(tmp_path: Path):
    gate = assess_mission_selection(
        tmp_path,
        LOOP_LOGIN_ROLLUP_REPAIR_GOAL,
        LOOP_LOGIN_ROLLUP_REPAIR_DONE_WHEN,
        history=[],
    )
    assert gate.accepted is True
    assert LOOP_LOGIN_ROLLUP_REPAIR_ID not in gate.capability_family
    nxt = assess_mission_selection(
        tmp_path,
        LOOP_LOGIN_ROLLUP_JOURNAL_GOAL,
        "A repaired login-scrub audit trail rollup leaves a durable record of the drifted claims.",
        history=[],
    )
    assert nxt.accepted is True
    assert LOOP_LOGIN_ROLLUP_JOURNAL_ID not in nxt.capability_family


def test_drifted_rollup_is_corrected_and_reverified(tmp_path: Path):
    path = login_audit_log_path(tmp_path)
    path.write_text(
        json.dumps(tombstone("old-task", pruned_days=DEFAULT_COMPACT_RETENTION_DAYS + 20), sort_keys=True)
        + "\n"
        + json.dumps(tombstone("kept-task", pruned_days=45), sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    compact_login_audit_tombstones(tmp_path)
    assert verify_login_audit_rollup(tmp_path)["verified"] is True
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if is_login_audit_rollup(record):
            record["newest_pruned_at"] = aged_iso(0)
            record["compacted_count"] = 0
        lines.append(json.dumps(record, sort_keys=True))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert verify_login_audit_rollup(tmp_path)["verified"] is False

    repaired = repair_login_audit_rollup(tmp_path)
    assert repaired["action"] == "rollup_repair"
    assert repaired["repaired"] is True
    assert repaired["reason"] == "drift_corrected"
    assert "span_survivor" in repaired["drift"]
    assert "span_clamped_below_survivor" in repaired["corrections"]
    assert "compacted_count_raised_to_runs" in repaired["corrections"]
    corrected = repaired["rollup"]
    assert corrected["compacted_count"] == corrected["compaction_runs"]
    assert corrected["repair_drift"]
    assert corrected["repaired_at"]
    post = verify_login_audit_rollup(tmp_path)
    assert post["verified"] is True
    assert post["drift"] == []
    assert post["rollup_count"] == 1
    surfaced = read_login_scrub_audit(tmp_path)["tombstone_rollup_verification"]
    assert surfaced["verified"] is True


def test_repair_merges_duplicate_rollups_and_fixes_counts_and_span(tmp_path: Path):
    path = login_audit_log_path(tmp_path)
    base = json.dumps(tombstone("kept-task", pruned_days=30), sort_keys=True) + "\n"

    def repair_with(lines):
        path.write_text(
            "".join(json.dumps(line, sort_keys=True) + "\n" for line in lines),
            encoding="utf-8",
        )
        return repair_login_audit_rollup(tmp_path)

    duplicate = repair_with([tombstone("kept-task", pruned_days=30), rollup(), rollup(compacted_count=3)])
    assert duplicate["repaired"] is True
    assert "merged_duplicate_rollup" in duplicate["corrections"]
    assert duplicate["rollup"]["compacted_count"] == 5
    assert duplicate["rollup"]["compaction_runs"] == 4
    assert duplicate["post_verification"]["verified"] is True
    assert len(path.read_text(encoding="utf-8").splitlines()) == 2

    inverted = repair_with(
        [tombstone("kept-task", pruned_days=30), rollup(oldest_pruned_at=aged_iso(300), newest_pruned_at=aged_iso(320))]
    )
    assert inverted["repaired"] is True
    assert "span_edges_swapped" in inverted["corrections"]
    assert inverted["post_verification"]["verified"] is True

    undated = repair_with([tombstone("kept-task", pruned_days=30), rollup(newest_pruned_at="not-a-timestamp")])
    assert undated["repaired"] is True
    assert "newest_pruned_at_taken_from_oldest" in undated["corrections"]

    undercounted = repair_with([tombstone("kept-task", pruned_days=30), rollup(compacted_count=1, compaction_runs=3)])
    assert undercounted["repaired"] is True
    assert undercounted["rollup"]["compacted_count"] == 3
    assert undercounted["post_verification"]["verified"] is True


def test_repair_leaves_intact_missing_and_unrepairable_trails_untouched(tmp_path: Path):
    path = login_audit_log_path(tmp_path)
    path.write_text(
        json.dumps(tombstone("old-task", pruned_days=DEFAULT_COMPACT_RETENTION_DAYS + 20), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    compact_login_audit_tombstones(tmp_path)
    raw = path.read_bytes()
    intact = repair_login_audit_rollup(tmp_path)
    assert intact["repaired"] is False
    assert intact["reason"] == "already_verified"
    assert path.read_bytes() == raw

    missing = repair_login_audit_rollup(tmp_path / "no-such-dir")
    assert missing["repaired"] is False
    assert missing["reason"] == "no_trail"
    assert not (tmp_path / "no-such-dir").exists()

    path.write_text(json.dumps(tombstone("kept-task", pruned_days=30), sort_keys=True) + "\n", encoding="utf-8")
    no_rollup = repair_login_audit_rollup(tmp_path)
    assert no_rollup["repaired"] is False
    assert no_rollup["reason"] == "no_rollup"

    unrepairable_rollup = rollup(oldest_pruned_at="", newest_pruned_at="", last_compacted_at="")
    path.write_text(
        json.dumps(tombstone("kept-task", pruned_days=30), sort_keys=True)
        + "\n"
        + json.dumps(unrepairable_rollup, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    raw = path.read_bytes()
    unrepairable = repair_login_audit_rollup(tmp_path)
    assert unrepairable["repaired"] is False
    assert unrepairable["reason"] == "unrepairable_span"
    assert path.read_bytes() == raw


def test_sweep_repair_corrects_drift_and_keeps_live_owner(tmp_path: Path):
    parent = tmp_path
    orphan = parent / "orphan-repo"
    orphan.mkdir()
    (orphan / "mission.json").write_text('{"status":"active"}\n', encoding="utf-8")
    seed_orphaned(orphan, pid=dead_pid())
    surviving = parent / "surviving-repo"
    surviving.mkdir()
    (surviving / "mission.json").write_text('{"status":"active"}\n', encoding="utf-8")
    live_pid = os.getpid()
    surviving_state = seed_orphaned(surviving, pid=live_pid, status="running_mission")
    unbound.continuous_loop_lock_path(surviving).write_text(f"{live_pid}\n", encoding="utf-8")
    scheduler = RecordingScheduler()
    register_loop_restore_at_login(orphan, scheduler=scheduler)
    register_loop_restore_at_login(surviving, scheduler=scheduler)
    surviving_registration = load_login_startup_registration(surviving)
    orphan_audit_root = login_startup_registration_path(orphan).parent
    audit_path = login_audit_log_path(orphan_audit_root)
    audit_path.write_text(
        json.dumps(tombstone("ancient-task", pruned_days=DEFAULT_COMPACT_RETENTION_DAYS + 10), sort_keys=True)
        + "\n"
        + json.dumps(tombstone("recent-task", pruned_days=80), sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    login_startup_registration_path(orphan).unlink()
    before = surviving_state.read_bytes()

    swept = sweep_login_tasks_missing_registration(scheduler=scheduler)
    assert swept["swept"] == [LOGIN_TASK_NAME]
    lines = []
    for line in audit_path.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if is_login_audit_rollup(record):
            record["newest_pruned_at"] = aged_iso(0)
        lines.append(json.dumps(record, sort_keys=True))
    audit_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    repaired = repair_login_audit_rollup(orphan_audit_root)
    assert repaired["repaired"] is True
    assert repaired["reason"] == "drift_corrected"
    post = verify_login_audit_rollup(orphan_audit_root)
    assert post["verified"] is True
    assert post["drift"] == []

    result = dispatch_login_startup(surviving, controller_starter=None)
    assert result["started"] is False
    assert result["restore_reason"] == "live_owner"
    assert load_login_startup_registration(surviving) == surviving_registration
    assert login_startup_launcher_path(surviving).is_file()
    assert login_startup_task_xml_path(surviving).is_file()
    assert not login_audit_log_path(login_startup_registration_path(surviving).parent).exists()
    assert surviving_state.read_bytes() == before


def test_cli_login_rollup_repair_reports_correction(tmp_path: Path):
    runner = CliRunner()
    root = tmp_path / "state"
    path = login_audit_log_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(tombstone("old-task", pruned_days=DEFAULT_COMPACT_RETENTION_DAYS + 20), sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    compact_login_audit_tombstones(root)
    intact = runner.invoke(
        unbound.app, ["loop-login-rollup-repair", "--repo-path", str(tmp_path), "--output-dir", str(root)]
    )
    assert intact.exit_code == 0, intact.output
    payload = json.loads(intact.stdout)
    assert payload["action"] == "rollup_repair"
    assert payload["repaired"] is False
    assert payload["reason"] == "already_verified"

    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if is_login_audit_rollup(record):
            record["compacted_count"] = 0
        lines.append(json.dumps(record, sort_keys=True))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    repaired = runner.invoke(
        unbound.app, ["loop-login-rollup-repair", "--repo-path", str(tmp_path), "--output-dir", str(root)]
    )
    assert repaired.exit_code == 0, repaired.output
    payload = json.loads(repaired.stdout)
    assert payload["repaired"] is True
    assert payload["reason"] == "drift_corrected"
    assert "compacted_count_raised_to_runs" in payload["corrections"]
    verified = runner.invoke(
        unbound.app, ["loop-login-verify", "--repo-path", str(tmp_path), "--output-dir", str(root)]
    )
    assert json.loads(verified.stdout)["verified"] is True
