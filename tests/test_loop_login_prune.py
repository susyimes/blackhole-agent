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
from blackhole_agent.loop_login_prune import (
    DEFAULT_PRUNE_RETENTION_DAYS,
    LOOP_LOGIN_PRUNE_DONE_WHEN,
    LOOP_LOGIN_PRUNE_GOAL,
    LOOP_LOGIN_PRUNE_ID,
    builtin_loop_login_prune_proof,
    prune_login_scrub_audit,
)
from blackhole_agent.loop_login_tombstone import (
    LOOP_LOGIN_TOMBSTONE_GOAL,
    LOOP_LOGIN_TOMBSTONE_ID,
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
            "loop_id": "login-prune-test",
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


def fresh_dead_pid(start: int = 1_000_213) -> int:
    pid = start
    while unbound.pid_is_running(pid):
        pid += 2
    return pid


def aged_iso(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat().replace("+00:00", "Z")


def write_trail(root: Path, entries: list[dict], extra_lines: list[str] | None = None) -> Path:
    path = login_audit_log_path(root)
    lines = [json.dumps(entry, sort_keys=True) for entry in entries]
    lines.extend(extra_lines or [])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_builtin_proof_prunes_aged_records_without_disturbing_live_owner():
    report = builtin_loop_login_prune_proof()
    assert report["ok"] is True
    assert report["action"] == "loop_login_prune"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == report["check_count"]
    assert report["checks"]["sweep_append_prunes_aged_out_records"]
    assert report["checks"]["malformed_and_undated_records_survive_prune"]
    assert report["checks"]["live_owner_not_disturbed"]
    assert report["checks"]["recorded_scrub_prunes_on_append"]
    assert report["checks"]["prune_is_idempotent"]
    assert report["checks"]["standalone_prune_ages_out_stale_records"]
    assert report["checks"]["catalog_names_login_tombstone"]


def test_selection_accepts_login_prune_and_next_family(tmp_path: Path):
    gate = assess_mission_selection(
        tmp_path,
        LOOP_LOGIN_PRUNE_GOAL,
        LOOP_LOGIN_PRUNE_DONE_WHEN,
        history=[],
    )
    assert gate.accepted is True
    assert LOOP_LOGIN_PRUNE_ID not in gate.capability_family
    nxt = assess_mission_selection(
        tmp_path,
        LOOP_LOGIN_TOMBSTONE_GOAL,
        "A pruned login-scrub audit record leaves a durable tombstone naming what aged out.",
        history=[],
    )
    assert nxt.accepted is True
    assert LOOP_LOGIN_TOMBSTONE_ID not in nxt.capability_family


def test_prune_drops_aged_records_and_keeps_the_rest(tmp_path: Path):
    stale = {
        "event": "login_task_artifacts_scrubbed",
        "task_name": "stale-task",
        "scrubbed_at": aged_iso(DEFAULT_PRUNE_RETENTION_DAYS + 45),
    }
    boundary = {
        "event": "login_task_artifacts_scrubbed",
        "task_name": "boundary-task",
        "scrubbed_at": aged_iso(DEFAULT_PRUNE_RETENTION_DAYS - 1),
    }
    undated = {"event": "login_task_artifacts_scrubbed", "task_name": "undated-task"}
    path = write_trail(tmp_path, [stale, boundary, undated], extra_lines=["broken line"])

    report = prune_login_scrub_audit(tmp_path)
    assert report["action"] == "audit_prune"
    assert report["pruned"] is True
    assert report["reason"] == "aged_out"
    assert report["pruned_count"] == 1
    assert report["kept_count"] == 1
    assert report["undated_count"] == 1
    assert report["malformed_count"] == 1
    assert report["audit_path"] == str(path)

    trail = read_login_scrub_audit(tmp_path)
    assert trail["entry_count"] == 2
    assert trail["malformed_count"] == 1
    names = [entry["task_name"] for entry in trail["entries"]]
    assert names == ["boundary-task", "undated-task"]
    raw = path.read_text(encoding="utf-8")
    assert "broken line" in raw

    before_bytes = path.read_bytes()
    again = prune_login_scrub_audit(tmp_path)
    assert again["pruned"] is False
    assert again["reason"] == "nothing_stale"
    assert again["pruned_count"] == 0
    assert path.read_bytes() == before_bytes


def test_prune_missing_trail_creates_nothing(tmp_path: Path):
    report = prune_login_scrub_audit(tmp_path / "nope")
    assert report["pruned"] is False
    assert report["reason"] == "no_trail"
    assert report["pruned_count"] == 0
    assert not login_audit_log_path(tmp_path / "nope").exists()


def test_recorded_scrub_prunes_aged_records_on_append(tmp_path: Path):
    stale = {
        "event": "login_task_artifacts_scrubbed",
        "task_name": "aged-task",
        "scrubbed_at": aged_iso(DEFAULT_PRUNE_RETENTION_DAYS + 10),
    }
    write_trail(tmp_path, [stale])
    task = {"name": LOGIN_TASK_NAME, "repo_path": str(tmp_path / "repo")}
    report = {
        "reason": "registration_gone",
        "scrubbed_paths": [str(tmp_path / "a.py"), str(tmp_path / "b.xml")],
        "kept_foreign": [],
    }
    recorded = record_login_task_scrub(task, report, audit_root=tmp_path)
    assert recorded["recorded"] is True
    assert recorded["audit_pruned"] is True
    assert recorded["audit_pruned_count"] == 1
    trail = read_login_scrub_audit(tmp_path)
    assert trail["entry_count"] == 1
    assert trail["entries"][0]["task_name"] == LOGIN_TASK_NAME


def test_sweep_keeps_trail_bounded_without_disturbing_live_owner(tmp_path: Path):
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
        "scrubbed_at": aged_iso(DEFAULT_PRUNE_RETENTION_DAYS + 90),
    }
    write_trail(orphan_audit_root, [stale])
    login_startup_registration_path(orphan).unlink()

    before = state_path.read_bytes()
    swept = sweep_login_tasks_missing_registration(scheduler=scheduler)
    assert swept["swept"] == [LOGIN_TASK_NAME]
    assert swept["audit_recorded"] == 1
    trail = read_login_scrub_audit(orphan_audit_root)
    assert trail["entry_count"] == 1
    assert trail["entries"][0]["task_name"] == LOGIN_TASK_NAME

    result = dispatch_login_startup(surviving, controller_starter=starter)
    assert result["started"] is False
    assert result["restore_reason"] == "live_owner"
    assert surviving_launcher.is_file()
    assert surviving_xml.is_file()
    assert load_login_startup_registration(surviving) is not None
    assert state_path.read_bytes() == before
    assert not login_audit_log_path(surviving_audit_root).exists()
    assert starts == []


def test_cli_login_prune_reports_aged_out_records(tmp_path: Path):
    stale = {
        "event": "login_task_artifacts_scrubbed",
        "task_name": "stale-task",
        "scrubbed_at": aged_iso(DEFAULT_PRUNE_RETENTION_DAYS + 5),
    }
    fresh = {
        "event": "login_task_artifacts_scrubbed",
        "task_name": "fresh-task",
        "scrubbed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    write_trail(tmp_path, [stale, fresh])

    result = CliRunner().invoke(
        unbound.app,
        ["loop-login-prune", "--repo-path", str(tmp_path), "--output-dir", str(tmp_path)],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["action"] == "audit_prune"
    assert payload["pruned"] is True
    assert payload["pruned_count"] == 1
    assert payload["kept_count"] == 1
    trail = read_login_scrub_audit(tmp_path)
    assert [entry["task_name"] for entry in trail["entries"]] == ["fresh-task"]
