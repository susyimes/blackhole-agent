"""Acceptance probe: a drifted compaction rollup is detected.

A durable login-scrub audit trail whose long-gone tombstones are compacted
keeps a durable rollup; verifying the rollup against the trail it
summarizes reports the intact rollup as verified, and forging the rollup —
extending its claimed span so it covers a tombstone still in the trail —
is detected as drift naming the surviving tombstone, without an operator
reconciling the rollup by hand. Verification is pure read, and a surviving
repo with a live owner pid keeps its registration, launcher, task XML, and
state bytes untouched. Prints JSON with boolean passed and nonempty
observed. Exits 0 for both met and unmet outcomes so the controller can
replay the same probe on baseline and candidate source trees.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

observed: dict[str, object] = {"family": "loop-login-verify"}
passed = False

try:
    from blackhole_agent.loop_login_audit import (
        login_audit_log_path,
        read_login_scrub_audit,
    )
    from blackhole_agent.loop_login_compact import (
        DEFAULT_COMPACT_RETENTION_DAYS,
        compact_login_audit_tombstones,
    )
    from blackhole_agent.loop_login_prune import DEFAULT_PRUNE_RETENTION_DAYS
    from blackhole_agent.loop_login_rollup import is_login_audit_rollup
    from blackhole_agent.loop_login_sweep import sweep_login_tasks_missing_registration
    from blackhole_agent.loop_login_task import (
        LOGIN_TASK_NAME,
        dispatch_login_startup,
        load_login_startup_registration,
        login_startup_launcher_path,
        login_startup_registration_path,
        login_startup_task_xml_path,
        register_loop_restore_at_login,
    )
    from blackhole_agent.loop_login_tombstone import LOGIN_AUDIT_TOMBSTONE_EVENT
    from blackhole_agent.loop_login_verify import verify_login_audit_rollup
    from blackhole_agent.unbound import (
        continuous_loop_lock_path,
        continuous_loop_state_path,
        pid_is_running,
        save_continuous_loop_state,
    )
except Exception as error:  # pragma: no cover - baseline missing login verify
    observed["error"] = type(error).__name__
    observed["detail"] = str(error)
    print(json.dumps({"passed": False, "observed": observed}, sort_keys=True))
    raise SystemExit(0)


class _Scheduler:
    def __init__(self) -> None:
        self.tasks: dict[str, dict] = {}

    @staticmethod
    def _key(payload: dict) -> str:
        return f"{payload.get('name') or ''}|{payload.get('repo_path') or ''}"

    def __call__(self, payload: dict) -> dict:
        action = payload.get("action")
        if action == "list":
            return {
                "backend": "acceptance",
                "listed": True,
                "tasks": [dict(task) for task in self.tasks.values()],
            }
        key = self._key(payload)
        if action == "unschedule":
            self.tasks.pop(key, None)
            return {"backend": "acceptance", "unscheduled": True}
        self.tasks[key] = dict(payload)
        return {"backend": "acceptance", "applied": True}


def _seed_orphaned(repo: Path, *, pid: int, status: str = "orphaned") -> Path:
    path = continuous_loop_state_path(repo)
    save_continuous_loop_state(
        path,
        {
            "loop_id": "acceptance-login-verify",
            "status": status,
            "pid": pid,
            "orphaned_from_status": "running_mission" if status == "orphaned" else "",
            "current_mission_id": "unfinished-mission",
            "current_state_path": str(repo / "mission.json"),
            "last_error": "retained diagnostic",
            "stop_reason": "controller_process_missing" if status == "orphaned" else "operator_stop",
        },
    )
    return path


def _aged_iso(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat().replace("+00:00", "Z")


def _tombstone(task_name: str, repo_path: str, *, pruned_days: int) -> dict:
    return {
        "schema_version": 1,
        "event": LOGIN_AUDIT_TOMBSTONE_EVENT,
        "tombstone": True,
        "task_name": task_name,
        "repo_path": repo_path,
        "reason": "registration_gone",
        "aged_out_scrubbed_at": _aged_iso(pruned_days + DEFAULT_PRUNE_RETENTION_DAYS),
        "pruned_at": _aged_iso(pruned_days),
        "retention_days": DEFAULT_PRUNE_RETENTION_DAYS,
    }


try:
    dead_pid = 1_000_295
    while pid_is_running(dead_pid):
        dead_pid += 2
    live_pid = os.getpid()

    with tempfile.TemporaryDirectory(prefix="acceptance-login-verify-") as tmp:
        parent = Path(tmp)
        orphan = parent / "orphan-repo"
        orphan.mkdir()
        (orphan / "mission.json").write_text('{"status":"active"}\n', encoding="utf-8")
        _seed_orphaned(orphan, pid=dead_pid)
        surviving = parent / "surviving-repo"
        surviving.mkdir()
        (surviving / "mission.json").write_text('{"status":"active"}\n', encoding="utf-8")
        surviving_state = _seed_orphaned(surviving, pid=live_pid, status="running_mission")
        continuous_loop_lock_path(surviving).write_text(f"{live_pid}\n", encoding="utf-8")
        scheduler = _Scheduler()
        register_loop_restore_at_login(orphan, scheduler=scheduler)
        register_loop_restore_at_login(surviving, scheduler=scheduler)
        surviving_registration = load_login_startup_registration(surviving)
        orphan_audit_root = login_startup_registration_path(orphan).parent
        surviving_audit_root = login_startup_registration_path(surviving).parent
        audit_path = login_audit_log_path(orphan_audit_root)
        audit_path.write_text(
            json.dumps(_tombstone("ancient-a", str(orphan), pruned_days=DEFAULT_COMPACT_RETENTION_DAYS + 40), sort_keys=True)
            + "\n"
            + json.dumps(_tombstone("ancient-b", str(orphan), pruned_days=DEFAULT_COMPACT_RETENTION_DAYS + 10), sort_keys=True)
            + "\n"
            + json.dumps(_tombstone("recent-task", str(orphan), pruned_days=90), sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        login_startup_registration_path(orphan).unlink()
        before = surviving_state.read_bytes()

        swept = sweep_login_tasks_missing_registration(scheduler=scheduler)
        verified = verify_login_audit_rollup(orphan_audit_root)
        surfaced = (read_login_scrub_audit(orphan_audit_root).get("tombstone_rollup_verification") or {})
        compact_standalone = compact_login_audit_tombstones(orphan_audit_root)

        raw_before_drift = audit_path.read_bytes()
        drifted_lines = []
        for line in raw_before_drift.decode("utf-8").splitlines():
            record = json.loads(line)
            if is_login_audit_rollup(record):
                record["newest_pruned_at"] = _aged_iso(0)
                record["compacted_count"] = 99
            drifted_lines.append(json.dumps(record, sort_keys=True))
        audit_path.write_text("\n".join(drifted_lines) + "\n", encoding="utf-8")
        drifted = verify_login_audit_rollup(orphan_audit_root)
        raw_after_verify = audit_path.read_bytes()
        surfaced_drift = (
            read_login_scrub_audit(orphan_audit_root).get("tombstone_rollup_verification") or {}
        )

        result = dispatch_login_startup(surviving, controller_starter=None)
        observed.update(
            {
                "swept": swept.get("swept"),
                "verified_reason": verified.get("reason"),
                "verified_drift": verified.get("drift"),
                "surfaced_reason": surfaced.get("reason"),
                "drifted_reason": drifted.get("reason"),
                "drifted_drift": drifted.get("drift"),
                "drifted_span_survivors": drifted.get("span_survivors"),
                "surfaced_drift_reason": surfaced_drift.get("reason"),
                "standalone_compact_after_verify": compact_standalone.get("compacted"),
                "restore_reason": result.get("restore_reason"),
            }
        )
        passed = (
            swept.get("swept") == [LOGIN_TASK_NAME]
            and verified.get("verified") is True
            and verified.get("reason") == "verified"
            and verified.get("drift") == []
            and (verified.get("rollup") or {}).get("compacted_count") == 2
            and surfaced.get("verified") is True
            and compact_standalone.get("compacted") is False
            and drifted.get("verified") is False
            and drifted.get("reason") == "drift_detected"
            and "span_survivor" in (drifted.get("drift") or [])
            and "recent-task" in (drifted.get("span_survivors") or [])
            and surfaced_drift.get("verified") is False
            and raw_after_verify == audit_path.read_bytes()
            and result.get("started") is False
            and result.get("restore_reason") == "live_owner"
            and load_login_startup_registration(surviving) == surviving_registration
            and login_startup_launcher_path(surviving).is_file()
            and login_startup_task_xml_path(surviving).is_file()
            and not login_audit_log_path(surviving_audit_root).exists()
            and surviving_state.read_bytes() == before
            and pid_is_running(live_pid)
        )
except Exception as error:  # pragma: no cover - defensive: probe must exit 0
    observed["error"] = type(error).__name__
    observed["detail"] = str(error)
    passed = False

print(json.dumps({"passed": bool(passed), "observed": observed}, sort_keys=True))
sys.exit(0)
