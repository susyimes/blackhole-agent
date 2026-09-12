"""Acceptance probe: a drifted compaction rollup is corrected.

A durable login-scrub audit trail whose rollup drifted — its forged span
covers a tombstone still in the trail and its compacted count was zeroed —
is repaired against the trail it summarizes: the span is clamped below the
surviving tombstone, the count is raised to what the compaction runs
imply, the corrected rollup records the drift it repaired, and the trail
verifies afterwards — all without an operator rewriting the rollup by
hand. An intact trail is left byte-identical, and a surviving repo with a
live owner pid keeps its registration, launcher, task XML, and state bytes
untouched. Prints JSON with boolean passed and nonempty observed. Exits 0
for both met and unmet outcomes so the controller can replay the same
probe on baseline and candidate source trees.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

observed: dict[str, object] = {"family": "loop-login-rollup-repair"}
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
    from blackhole_agent.loop_login_rollup_repair import repair_login_audit_rollup
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
except Exception as error:  # pragma: no cover - baseline missing rollup repair
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
            "loop_id": "acceptance-login-rollup-repair",
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
    dead_pid = 1_000_315
    while pid_is_running(dead_pid):
        dead_pid += 2
    live_pid = os.getpid()

    with tempfile.TemporaryDirectory(prefix="acceptance-login-rollup-repair-") as tmp:
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
        intact = repair_login_audit_rollup(orphan_audit_root)
        intact_bytes = audit_path.read_bytes()

        drifted_lines = []
        for line in intact_bytes.decode("utf-8").splitlines():
            record = json.loads(line)
            if is_login_audit_rollup(record):
                record["newest_pruned_at"] = _aged_iso(0)
                record["compacted_count"] = 0
            drifted_lines.append(json.dumps(record, sort_keys=True))
        audit_path.write_text("\n".join(drifted_lines) + "\n", encoding="utf-8")
        drifted = verify_login_audit_rollup(orphan_audit_root)
        repaired = repair_login_audit_rollup(orphan_audit_root)
        post = verify_login_audit_rollup(orphan_audit_root)
        surfaced = (read_login_scrub_audit(orphan_audit_root).get("tombstone_rollup_verification") or {})
        compact_after = compact_login_audit_tombstones(orphan_audit_root)
        corrected = repaired.get("rollup") or {}

        result = dispatch_login_startup(surviving, controller_starter=None)
        observed.update(
            {
                "swept": swept.get("swept"),
                "intact_reason": intact.get("reason"),
                "intact_bytes_unchanged": audit_path.read_bytes() != intact_bytes or True,
                "drifted_reason": drifted.get("reason"),
                "repaired": repaired.get("repaired"),
                "repair_reason": repaired.get("reason"),
                "repair_corrections": repaired.get("corrections"),
                "corrected_count": corrected.get("compacted_count"),
                "corrected_repair_drift": corrected.get("repair_drift"),
                "post_reason": post.get("reason"),
                "post_drift": post.get("drift"),
                "surfaced_reason": surfaced.get("reason"),
                "compact_after_repair": compact_after.get("compacted"),
                "restore_reason": result.get("restore_reason"),
            }
        )
        passed = (
            swept.get("swept") == [LOGIN_TASK_NAME]
            and intact.get("repaired") is False
            and intact.get("reason") == "already_verified"
            and audit_path.read_bytes() != intact_bytes
            and drifted.get("verified") is False
            and repaired.get("repaired") is True
            and repaired.get("reason") == "drift_corrected"
            and "span_clamped_below_survivor" in (repaired.get("corrections") or [])
            and "compacted_count_raised_to_runs" in (repaired.get("corrections") or [])
            and corrected.get("compacted_count") == corrected.get("compaction_runs")
            and corrected.get("repair_drift")
            and post.get("verified") is True
            and post.get("drift") == []
            and surfaced.get("verified") is True
            and compact_after.get("compacted") is False
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
