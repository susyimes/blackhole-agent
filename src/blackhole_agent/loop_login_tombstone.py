"""Leave a durable tombstone when an aged-out audit record is pruned.

Login-audit prune drops records whose scrub time aged out so the durable
trail stays bounded, but a pruned record used to vanish without a trace:
an operator reconciling the bounded trail could not tell an aged-out
record from one that was never written.

This module is the tombstone path: every record the prune drops is
replaced in place by a durable tombstone entry naming what aged out — the
task, its repo, and the original scrub time — plus the prune time and the
retention window that aged it out. A tombstone is never stale itself, so
later prunes keep it byte-identical and the bounded trail stays
reconcilable; once the record a tombstone names is long gone, the compact
path drops the tombstone so the trail stays small. The tombstone rewrite
rides the prune's atomic
temp-file-and-replace, touches only the audit trail, and never touches a
scheduler entry, launcher, or task XML, so a live owner pid in any
surviving repo is never disturbed.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

from blackhole_agent.capability_compounder import (
    Capability,
    default_ledger_path,
    legacy_pipeline_was_used,
    load_ledger,
    register_capability,
    save_ledger,
    utc_now_iso,
)
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.loop_login_compact import (
    LOOP_LOGIN_COMPACT_DONE_WHEN,
    LOOP_LOGIN_COMPACT_GOAL,
    LOOP_LOGIN_COMPACT_ID,
    LOOP_LOGIN_COMPACT_LEFTOVER,
)

SCHEMA_VERSION = 1
LOOP_LOGIN_TOMBSTONE_ID = "capability.loop-login-tombstone"
LOOP_LOGIN_TOMBSTONE_DONE_WHEN = (
    "A pruned login-scrub audit record leaves a durable tombstone naming what "
    "aged out so the bounded trail stays reconcilable without disturbing a "
    "live owner pid in any surviving repo."
)
LOOP_LOGIN_TOMBSTONE_GOAL = (
    "Repair login-prune tombstone: a pruned audit record vanishes from the "
    "trail without a trace, so an operator reconciling the bounded trail "
    "cannot tell an aged-out record from one that was never written."
)
LOOP_LOGIN_TOMBSTONE_LEFTOVER = (
    "Later genesis can take login-prune tombstone so a pruned audit record "
    "leaves a durable tombstone without an operator reconstructing aged-out "
    "records by hand."
)
LOGIN_AUDIT_TOMBSTONE_EVENT = "login_task_audit_record_pruned"
REPO_ROOT = Path(__file__).resolve().parents[2]


def is_login_audit_tombstone(record: dict[str, Any]) -> bool:
    """True when an audit-trail record is a prune tombstone."""

    return (
        isinstance(record, dict)
        and record.get("event") == LOGIN_AUDIT_TOMBSTONE_EVENT
        and record.get("tombstone") is True
    )


def login_audit_tombstone_for(
    record: dict[str, Any],
    *,
    pruned_at: str,
    retention_days: int,
) -> dict[str, Any]:
    """Build the durable tombstone naming what aged out of the trail.

    The tombstone keeps the pruned record's identity — task, repo, reason,
    and the original scrub time — so an operator reconciling the bounded
    trail can tell an aged-out record from one that was never written.
    """

    return {
        "schema_version": SCHEMA_VERSION,
        "event": LOGIN_AUDIT_TOMBSTONE_EVENT,
        "tombstone": True,
        "task_name": str(record.get("task_name") or ""),
        "repo_path": str(record.get("repo_path") or ""),
        "reason": str(record.get("reason") or ""),
        "aged_out_scrubbed_at": str(record.get("scrubbed_at") or ""),
        "pruned_at": pruned_at,
        "retention_days": retention_days,
    }


def loop_login_tombstone_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.loop_login_tombstone import "
        "builtin_loop_login_tombstone_proof; r=builtin_loop_login_tombstone_proof(); "
        "assert r['ok'] and r.get('action')=='loop_login_tombstone' "
        "and r.get('passed_count',0) >= 18 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_loop_login_tombstone_capability(*, repo_path: Path | None = None) -> Capability:
    """Register login-prune tombstone on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=LOOP_LOGIN_TOMBSTONE_ID,
        name="Continuous-loop login-prune tombstone",
        description=(
            "A pruned login-scrub audit record leaves a durable tombstone "
            "naming what aged out so the bounded trail stays reconcilable "
            "without disturbing a live owner pid in any surviving repo."
        ),
        kind="python",
        entry="blackhole_agent.loop_login_tombstone:builtin_loop_login_tombstone_proof",
        proof_command=loop_login_tombstone_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.orphan-loop-reap",
            "capability.loop-reboot-restore",
            "capability.loop-login-task",
            "capability.loop-login-repair",
            "capability.loop-login-drift",
            "capability.loop-login-stale",
            "capability.loop-login-retire",
            "capability.loop-login-sweep",
            "capability.loop-login-scrub",
            "capability.loop-login-audit",
            "capability.loop-login-prune",
        ),
        behavior_paths=(
            "src/blackhole_agent/loop_login_tombstone.py",
            "src/blackhole_agent/loop_login_prune.py",
            "src/blackhole_agent/loop_login_audit.py",
            "src/blackhole_agent/unbound.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A pruned login-scrub audit record no longer vanishes: the prune "
            "replaces it in place with a durable tombstone naming the task, "
            "its repo, and the original scrub time, tombstones are never "
            "stale so later prunes keep them byte-identical, the audit read "
            "surfaces them, and a live owner pid is never disturbed."
        ),
        tags=("continuous-loop", "login", "startup", "restore", "audit", "prune", "tombstone"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def _seed_orphaned(repo: Path, *, pid: int, status: str = "orphaned") -> Path:
    from blackhole_agent.unbound import (
        continuous_loop_state_path,
        save_continuous_loop_state,
    )

    path = continuous_loop_state_path(repo)
    save_continuous_loop_state(
        path,
        {
            "loop_id": "login-tombstone-proof",
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


class _ProofScheduler:
    def __init__(self) -> None:
        self.tasks: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _key(payload: dict[str, Any]) -> str:
        return f"{payload.get('name') or ''}|{payload.get('repo_path') or ''}"

    def __call__(self, payload: dict[str, Any]) -> dict[str, Any]:
        action = payload.get("action")
        if action == "list":
            return {
                "backend": "proof",
                "listed": True,
                "tasks": [dict(task) for task in self.tasks.values()],
            }
        key = self._key(payload)
        if action == "unschedule":
            self.tasks.pop(key, None)
            return {"backend": "proof", "unscheduled": True}
        self.tasks[key] = dict(payload)
        return {"backend": "proof", "applied": True}


def _aged_iso(days: int) -> str:
    from datetime import datetime, timedelta, timezone

    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat().replace("+00:00", "Z")


def builtin_loop_login_tombstone_proof() -> dict[str, Any]:
    """Hermetic proof: a pruned record leaves a durable tombstone; live owners kept."""

    import json

    from blackhole_agent.evolution_quality import behavior_family
    from blackhole_agent.kernel_genesis_diversify import DIVERSITY_CATALOG
    from blackhole_agent.kernel_leftover import leftover_marker_ids
    from blackhole_agent.loop_login_audit import (
        login_audit_log_path,
        read_login_scrub_audit,
    )
    from blackhole_agent.loop_login_prune import (
        DEFAULT_PRUNE_RETENTION_DAYS,
        LOOP_LOGIN_PRUNE_ID,
        prune_login_scrub_audit,
    )
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
    from blackhole_agent.unbound import continuous_loop_lock_path, pid_is_running

    checks: dict[str, bool] = {}
    checks["denylists_self"] = LOOP_LOGIN_TOMBSTONE_ID in LOCAL_DENYLIST
    checks["denylists_next_family"] = LOOP_LOGIN_COMPACT_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(LOOP_LOGIN_TOMBSTONE_GOAL) == (
        LOOP_LOGIN_TOMBSTONE_ID,
    )
    checks["leftover_text_binds_next_family"] = leftover_marker_ids(
        LOOP_LOGIN_COMPACT_LEFTOVER
    ) == (LOOP_LOGIN_COMPACT_ID,)
    checks["next_family_goal_is_login_compact"] = leftover_marker_ids(
        LOOP_LOGIN_COMPACT_GOAL
    ) == (LOOP_LOGIN_COMPACT_ID,)
    checks["prior_family_markers_stay"] = leftover_marker_ids(LOOP_LOGIN_TOMBSTONE_LEFTOVER) == (
        LOOP_LOGIN_TOMBSTONE_ID,
    )
    catalog = DIVERSITY_CATALOG
    checks["catalog_names_login_tombstone"] = (
        len(catalog) > 251
        and catalog[251]["id"] == LOOP_LOGIN_TOMBSTONE_ID
        and catalog[251]["goal"] == LOOP_LOGIN_TOMBSTONE_GOAL
        and catalog[251]["done_when"] == LOOP_LOGIN_TOMBSTONE_DONE_WHEN
        and catalog[251]["source"] == "genesis_bind_loop_login_tombstone"
    )
    checks["catalog_names_login_compact"] = (
        len(catalog) > 252
        and catalog[252]["id"] == LOOP_LOGIN_COMPACT_ID
        and catalog[252]["goal"] == LOOP_LOGIN_COMPACT_GOAL
        and catalog[252]["done_when"] == LOOP_LOGIN_COMPACT_DONE_WHEN
        and catalog[252]["source"] == "genesis_bind_loop_login_compact"
    )
    checks["login_prune_stays_ahead"] = (
        len(catalog) > 250 and catalog[250]["id"] == LOOP_LOGIN_PRUNE_ID
    )

    dead_pid = 1_000_231
    while pid_is_running(dead_pid):
        dead_pid += 2
    live_pid = os.getpid()
    starts: list[int] = []

    def starter(repo: Path, output_dir: Path | None = None, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        from blackhole_agent.unbound import (
            continuous_loop_lock,
            continuous_loop_lock_path,
            continuous_loop_state_path,
            save_continuous_loop_state,
        )

        pid = os.getpid()
        starts.append(pid)
        with continuous_loop_lock(continuous_loop_lock_path(repo)):
            save_continuous_loop_state(
                continuous_loop_state_path(repo),
                {
                    **(payload or {}),
                    "status": "running_mission",
                    "pid": pid,
                    "restored_from_status": "orphaned",
                    "stop_reason": "",
                },
            )
        return {"started": True, "pid": pid}

    with tempfile.TemporaryDirectory(prefix="loop-login-tombstone-sweep-") as tmp:
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
        scheduler = _ProofScheduler()
        register_loop_restore_at_login(orphan, scheduler=scheduler)
        register_loop_restore_at_login(surviving, scheduler=scheduler)
        surviving_launcher = login_startup_launcher_path(surviving)
        surviving_xml = login_startup_task_xml_path(surviving)
        surviving_registration = load_login_startup_registration(surviving)
        orphan_audit_root = login_startup_registration_path(orphan).parent
        surviving_audit_root = login_startup_registration_path(surviving).parent
        stale_entry = {
            "schema_version": SCHEMA_VERSION,
            "event": "login_task_artifacts_scrubbed",
            "task_name": "stale-task",
            "repo_path": str(orphan),
            "reason": "registration_gone",
            "scrubbed_paths": ["old-launcher", "old-xml"],
            "kept_foreign": [],
            "scrubbed_at": _aged_iso(DEFAULT_PRUNE_RETENTION_DAYS + 60),
        }
        fresh_entry = dict(stale_entry, task_name="fresh-task", scrubbed_at=utc_now_iso())
        audit_path = login_audit_log_path(orphan_audit_root)
        audit_path.write_text(
            json.dumps(stale_entry, sort_keys=True) + "\n"
            + json.dumps(fresh_entry, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        login_startup_registration_path(orphan).unlink()
        before = surviving_state.read_bytes()
        starts_before = len(starts)
        swept = sweep_login_tasks_missing_registration(scheduler=scheduler)
        result = dispatch_login_startup(surviving, controller_starter=starter)
        trail = read_login_scrub_audit(orphan_audit_root)
        entries = trail.get("entries") or []
        tombstones = [entry for entry in entries if is_login_audit_tombstone(entry)]
        tombstone = tombstones[0] if tombstones else {}
        checks["pruned_record_leaves_durable_tombstone"] = (
            swept.get("action") == "sweep"
            and swept.get("swept") == [LOGIN_TASK_NAME]
            and swept.get("scrubbed_count") == 2
            and swept.get("audit_recorded") == 1
            and trail.get("entry_count") == 3
            and trail.get("tombstone_count") == 1
            and len(tombstones) == 1
            and tombstone.get("event") == LOGIN_AUDIT_TOMBSTONE_EVENT
            and tombstone.get("tombstone") is True
            and len(starts) == starts_before
        )
        checks["tombstone_names_what_aged_out"] = (
            tombstone.get("task_name") == "stale-task"
            and tombstone.get("repo_path") == str(orphan)
            and tombstone.get("reason") == "registration_gone"
            and tombstone.get("aged_out_scrubbed_at") == stale_entry["scrubbed_at"]
            and bool(tombstone.get("pruned_at"))
            and tombstone.get("retention_days") == DEFAULT_PRUNE_RETENTION_DAYS
            and tombstone.get("schema_version") == SCHEMA_VERSION
        )
        checks["live_owner_not_disturbed"] = (
            LOGIN_TASK_NAME in swept.get("kept")
            and surviving_registration is not None
            and load_login_startup_registration(surviving) == surviving_registration
            and surviving_launcher.is_file()
            and surviving_xml.is_file()
            and not login_audit_log_path(surviving_audit_root).exists()
            and result.get("started") is False
            and result.get("restore_reason") == "live_owner"
            and result.get("scheduled") is True
            and surviving_state.read_bytes() == before
            and len(starts) == starts_before
            and pid_is_running(live_pid)
        )
        raw_before = audit_path.read_bytes()
        again = prune_login_scrub_audit(orphan_audit_root)
        checks["tombstone_is_never_pruned"] = (
            again.get("pruned") is False
            and again.get("pruned_count") == 0
            and again.get("reason") == "nothing_stale"
            and audit_path.read_bytes() == raw_before
            and read_login_scrub_audit(orphan_audit_root).get("tombstone_count") == 1
        )

    with tempfile.TemporaryDirectory(prefix="loop-login-tombstone-standalone-") as tmp:
        root = Path(tmp)
        path = login_audit_log_path(root)
        stale = {
            "event": "login_task_artifacts_scrubbed",
            "task_name": "old-task",
            "repo_path": str(root / "repo"),
            "scrubbed_at": _aged_iso(DEFAULT_PRUNE_RETENTION_DAYS + 10),
        }
        fresh = {
            "event": "login_task_artifacts_scrubbed",
            "task_name": "new-task",
            "scrubbed_at": utc_now_iso(),
        }
        path.write_text(
            json.dumps(stale, sort_keys=True) + "\n" + json.dumps(fresh, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        pruned = prune_login_scrub_audit(root)
        trail = read_login_scrub_audit(root)
        entries = trail.get("entries") or []
        tombstones = [entry for entry in entries if is_login_audit_tombstone(entry)]
        scrub_names = [
            str(entry.get("task_name") or "")
            for entry in entries
            if not is_login_audit_tombstone(entry)
        ]
        checks["standalone_prune_writes_tombstone"] = (
            pruned.get("pruned") is True
            and pruned.get("pruned_count") == 1
            and pruned.get("tombstones_written") == 1
            and pruned.get("reason") == "aged_out"
            and trail.get("entry_count") == 2
            and trail.get("tombstone_count") == 1
            and len(tombstones) == 1
            and tombstones[0].get("task_name") == "old-task"
            and scrub_names == ["new-task"]
        )

    checks["next_family_is_not_handshake"] = (
        behavior_family(LOOP_LOGIN_COMPACT_GOAL) != "network/handshake-digest-demo"
        and LOOP_LOGIN_COMPACT_DONE_WHEN != ""
    )
    checks["contract_is_outcome_level"] = (
        "capability_exists:" not in LOOP_LOGIN_TOMBSTONE_DONE_WHEN
        and "capability_proved:" not in LOOP_LOGIN_TOMBSTONE_DONE_WHEN
    )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_loop_login_tombstone_capability()
    return {
        "ok": ok,
        "action": "loop_login_tombstone",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": LOOP_LOGIN_TOMBSTONE_GOAL,
        "done_when": LOOP_LOGIN_TOMBSTONE_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
