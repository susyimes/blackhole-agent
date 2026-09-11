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
from blackhole_agent.loop_login_rollup_repair import (
    LOOP_LOGIN_ROLLUP_REPAIR_GOAL,
    LOOP_LOGIN_ROLLUP_REPAIR_ID,
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
    LOOP_LOGIN_VERIFY_DONE_WHEN,
    LOOP_LOGIN_VERIFY_GOAL,
    LOOP_LOGIN_VERIFY_ID,
    builtin_loop_login_verify_proof,
    verify_login_audit_rollup,
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
            "loop_id": "login-verify-test",
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
    pid = 1_000_293
    while unbound.pid_is_running(pid):
        pid += 2
    return pid


def test_builtin_proof_verifies_rollup_and_detects_drift_without_disturbing_live_owner():
    report = builtin_loop_login_verify_proof()
    assert report["ok"] is True
    assert report["action"] == "loop_login_verify"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == report["check_count"]
    assert report["checks"]["compacted_trail_rollup_verifies_against_trail"]
    assert report["checks"]["audit_read_surfaces_rollup_verification"]
    assert report["checks"]["forged_span_is_detected"]
    assert report["checks"]["verify_is_pure_read"]
    assert report["checks"]["duplicate_rollup_line_is_drift"]
    assert report["checks"]["inverted_span_is_drift"]
    assert report["checks"]["invalid_count_is_drift"]
    assert report["checks"]["count_below_runs_is_drift"]
    assert report["checks"]["unparseable_span_is_drift"]
    assert report["checks"]["recent_tombstone_outside_span_is_not_drift"]
    assert report["checks"]["live_owner_not_disturbed"]
    assert report["checks"]["catalog_names_login_rollup_repair"]


def test_selection_accepts_login_verify_and_next_family(tmp_path: Path):
    gate = assess_mission_selection(
        tmp_path,
        LOOP_LOGIN_VERIFY_GOAL,
        LOOP_LOGIN_VERIFY_DONE_WHEN,
        history=[],
    )
    assert gate.accepted is True
    assert LOOP_LOGIN_VERIFY_ID not in gate.capability_family
    nxt = assess_mission_selection(
        tmp_path,
        LOOP_LOGIN_ROLLUP_REPAIR_GOAL,
        "A drifted login-scrub audit trail rollup is corrected.",
        history=[],
    )
    assert nxt.accepted is True
    assert LOOP_LOGIN_ROLLUP_REPAIR_ID not in nxt.capability_family


def test_compacted_trail_rollup_verifies(tmp_path: Path):
    path = login_audit_log_path(tmp_path)
    path.write_text(
        json.dumps(tombstone("first-old", pruned_days=DEFAULT_COMPACT_RETENTION_DAYS + 30), sort_keys=True)
        + "\n"
        + json.dumps(tombstone("recent-task", pruned_days=60), sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    compacted = compact_login_audit_tombstones(tmp_path)
    result = verify_login_audit_rollup(tmp_path)
    assert compacted["compacted"] is True
    assert result["action"] == "rollup_verify"
    assert result["verified"] is True
    assert result["reason"] == "verified"
    assert result["rollup_present"] is True
    assert result["rollup_count"] == 1
    assert result["drift"] == []
    assert result["rollup"]["compacted_count"] == 1
    trail = read_login_scrub_audit(tmp_path)
    surfaced = trail["tombstone_rollup_verification"]
    assert surfaced["verified"] is True
    assert surfaced["reason"] == "verified"


def test_forged_span_covering_surviving_tombstone_is_detected(tmp_path: Path):
    path = login_audit_log_path(tmp_path)
    path.write_text(
        json.dumps(tombstone("old-task", pruned_days=DEFAULT_COMPACT_RETENTION_DAYS + 20), sort_keys=True)
        + "\n"
        + json.dumps(tombstone("kept-task", pruned_days=45), sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    compact_login_audit_tombstones(tmp_path)
    lines = [
        json.dumps(
            json.loads(line) if not is_login_audit_rollup(json.loads(line)) else
            dict(json.loads(line), newest_pruned_at=aged_iso(0), compacted_count=50),
            sort_keys=True,
        )
        for line in path.read_text(encoding="utf-8").splitlines()
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    result = verify_login_audit_rollup(tmp_path)
    assert result["verified"] is False
    assert result["reason"] == "drift_detected"
    assert "span_survivor" in result["drift"]
    assert result["span_survivors"] == ["kept-task"]
    surfaced = read_login_scrub_audit(tmp_path)["tombstone_rollup_verification"]
    assert surfaced["verified"] is False
    assert "span_survivor" in surfaced["drift"]


def test_malformed_rollup_fields_are_drift(tmp_path: Path):
    path = login_audit_log_path(tmp_path)
    base = json.dumps(tombstone("kept-task", pruned_days=45), sort_keys=True) + "\n"

    def verify_with(**overrides):
        path.write_text(base + json.dumps(rollup(**overrides), sort_keys=True) + "\n", encoding="utf-8")
        return verify_login_audit_rollup(tmp_path)

    duplicate = verify_with()
    path.write_text(
        base
        + json.dumps(rollup(), sort_keys=True)
        + "\n"
        + json.dumps(rollup(compacted_count=3), sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    duplicate = verify_login_audit_rollup(tmp_path)
    assert duplicate["verified"] is False
    assert duplicate["rollup_count"] == 2
    assert "duplicate_rollup" in duplicate["drift"]

    inverted = verify_with(oldest_pruned_at=aged_iso(300), newest_pruned_at=aged_iso(320))
    assert inverted["verified"] is False
    assert "span_inverted" in inverted["drift"]

    zeroed = verify_with(compacted_count=0)
    assert zeroed["verified"] is False
    assert "compacted_count_invalid" in zeroed["drift"]

    undercounted = verify_with(compacted_count=1, compaction_runs=3)
    assert undercounted["verified"] is False
    assert "count_below_runs" in undercounted["drift"]

    undated = verify_with(newest_pruned_at="not-a-timestamp")
    assert undated["verified"] is False
    assert "newest_pruned_at_unparseable" in undated["drift"]

    honest = verify_with()
    assert honest["verified"] is True
    assert honest["reason"] == "verified"
    assert honest["tombstones_checked"] == 1


def test_verify_is_read_only_and_reports_missing_or_rollup_free_trails(tmp_path: Path):
    missing = verify_login_audit_rollup(tmp_path / "no-such-dir")
    assert missing["verified"] is False
    assert missing["reason"] == "no_trail"
    assert not (tmp_path / "no-such-dir").exists()

    path = login_audit_log_path(tmp_path)
    path.write_text(
        json.dumps(tombstone("kept-task", pruned_days=45), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    no_rollup = verify_login_audit_rollup(tmp_path)
    assert no_rollup["verified"] is True
    assert no_rollup["reason"] == "no_rollup"
    assert no_rollup["rollup_present"] is False

    path.write_text(
        path.read_text(encoding="utf-8") + json.dumps(rollup(compacted_count=0), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    raw = path.read_bytes()
    drifted = verify_login_audit_rollup(tmp_path)
    assert drifted["verified"] is False
    assert path.read_bytes() == raw


def test_sweep_verify_detects_drift_and_keeps_live_owner(tmp_path: Path):
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
    verified = verify_login_audit_rollup(orphan_audit_root)
    assert swept["swept"] == [LOGIN_TASK_NAME]
    assert verified["verified"] is True
    assert verified["rollup"]["compacted_count"] == 1

    lines = []
    for line in audit_path.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if is_login_audit_rollup(record):
            record["newest_pruned_at"] = aged_iso(0)
        lines.append(json.dumps(record, sort_keys=True))
    audit_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    drifted = verify_login_audit_rollup(orphan_audit_root)
    assert drifted["verified"] is False
    assert "span_survivor" in drifted["drift"]
    assert "recent-task" in drifted["span_survivors"]

    result = dispatch_login_startup(surviving, controller_starter=None)
    assert result["started"] is False
    assert result["restore_reason"] == "live_owner"
    assert load_login_startup_registration(surviving) == surviving_registration
    assert login_startup_launcher_path(surviving).is_file()
    assert login_startup_task_xml_path(surviving).is_file()
    assert not login_audit_log_path(login_startup_registration_path(surviving).parent).exists()
    assert surviving_state.read_bytes() == before


def test_cli_login_verify_reports_verification(tmp_path: Path):
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
    ok = runner.invoke(unbound.app, ["loop-login-verify", "--repo-path", str(tmp_path), "--output-dir", str(root)])
    assert ok.exit_code == 0
    payload = json.loads(ok.stdout)
    assert payload["action"] == "rollup_verify"
    assert payload["verified"] is True
    assert payload["reason"] == "verified"

    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if is_login_audit_rollup(record):
            record["compacted_count"] = 0
        lines.append(json.dumps(record, sort_keys=True))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    drifted = runner.invoke(
        unbound.app, ["loop-login-verify", "--repo-path", str(tmp_path), "--output-dir", str(root)]
    )
    assert drifted.exit_code == 0
    payload = json.loads(drifted.stdout)
    assert payload["verified"] is False
    assert payload["reason"] == "drift_detected"
    assert "compacted_count_invalid" in payload["drift"]
