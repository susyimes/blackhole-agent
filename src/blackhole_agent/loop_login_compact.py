"""Compact long-gone tombstones from the durable login-scrub audit trail.

Login-audit prune drops aged-out records and replaces each with a durable
tombstone naming what aged out, so an operator reconciling the bounded
trail can tell an aged-out record from one that was never written. But a
tombstone is never stale itself: every prune adds a permanent tombstone,
so a trail that prunes for years piles tombstones up without bound until
an operator compacts tombstones by hand.

This module is the compact path: a tombstone whose named record is long
gone — the tombstone's own prune time is older than the compact retention
window, far past the prune retention that aged the named record out — is
dropped so the trail stays small, while recent tombstones stay so the
trail remains reconcilable. A tombstone whose prune time is missing or
unparseable is never compacted: the compact must not drop what it cannot
prove long gone. Compaction runs automatically on every recorded scrub
(compact-on-append, right after prune-on-append, so each sweep keeps the
trail small) and is also exposed as a standalone compact for trails that
no longer receive scrubs. The compact rewrite rides the same atomic
temp-file-and-replace, touches only the audit trail, and never touches a
scheduler entry, launcher, or task XML, so a live owner pid in any
surviving repo is never disturbed.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
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
from blackhole_agent.loop_login_rollup import (
    LOOP_LOGIN_ROLLUP_DONE_WHEN,
    LOOP_LOGIN_ROLLUP_GOAL,
    LOOP_LOGIN_ROLLUP_ID,
    LOOP_LOGIN_ROLLUP_LEFTOVER,
)

SCHEMA_VERSION = 1
LOOP_LOGIN_COMPACT_ID = "capability.loop-login-compact"
LOOP_LOGIN_COMPACT_DONE_WHEN = (
    "A durable login-scrub audit trail's tombstones are compacted once the "
    "records they name are long gone so the trail stays small and "
    "reconcilable without disturbing a live owner pid in any surviving repo."
)
LOOP_LOGIN_COMPACT_GOAL = (
    "Repair login-tombstone bloat: every prune adds a permanent tombstone, "
    "so a trail that prunes for years piles tombstones up without bound "
    "until an operator compacts tombstones by hand."
)
LOOP_LOGIN_COMPACT_LEFTOVER = (
    "Later genesis can take login-tombstone bloat so a trail's tombstones "
    "are compacted without an operator compacting tombstones by hand."
)
DEFAULT_COMPACT_RETENTION_DAYS = 365
REPO_ROOT = Path(__file__).resolve().parents[2]


def login_audit_tombstone_is_compactable(
    entry: dict[str, Any],
    *,
    now: datetime,
    retention_days: int = DEFAULT_COMPACT_RETENTION_DAYS,
) -> bool:
    """True only when a tombstone's named record is provably long gone.

    A tombstone is the durable trace of an earlier prune, so only a
    tombstone whose own prune time aged past the compact retention window —
    far beyond the prune retention that already aged the named record out —
    may be compacted. A non-tombstone record is never compacted here (that
    is the prune's job), and a tombstone whose prune time is missing or
    unparseable is kept: the compact must not drop what it cannot prove
    long gone.
    """

    from blackhole_agent.loop_login_prune import _parse_audit_time
    from blackhole_agent.loop_login_tombstone import is_login_audit_tombstone

    if not is_login_audit_tombstone(entry):
        return False
    pruned_at = _parse_audit_time(entry.get("pruned_at"))
    if pruned_at is None:
        return False
    return now - pruned_at > timedelta(days=retention_days)


def compact_login_audit_tombstones(
    root: Path | None = None,
    *,
    retention_days: int = DEFAULT_COMPACT_RETENTION_DAYS,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Compact long-gone tombstones from a durable login-scrub audit trail.

    Tombstones whose prune time is older than the compact retention window
    are dropped so the trail stays small; recent tombstones stay so an
    operator reconciling the trail can still tell an aged-out record from
    one that was never written. The report names the compacted tombstones'
    tasks so the compaction itself leaves immediate evidence. Scrub records
    (fresh or stale — pruning them is the prune's job), tombstones with an
    unparseable prune time, and malformed lines are kept; the rewrite is
    atomic (temp file + replace) and only happens when a tombstone actually
    compacted, so an intact trail is left byte-identical. A missing trail
    is reported, never created. Nothing here touches a scheduler entry,
    launcher, or task XML, so a live owner pid in any surviving repo is
    never disturbed.
    """

    from blackhole_agent.loop_login_audit import login_audit_log_path
    from blackhole_agent.loop_login_tombstone import is_login_audit_tombstone

    path = login_audit_log_path(root)
    moment = now or datetime.now(timezone.utc)
    report: dict[str, Any] = {
        "action": "tombstone_compact",
        "audit_path": str(path),
        "compacted": False,
        "compacted_count": 0,
        "compacted_tasks": [],
        "tombstone_count": 0,
        "kept_count": 0,
        "malformed_count": 0,
        "retention_days": retention_days,
        "compacted_at": utc_now_iso(),
    }
    if not path.is_file():
        report["reason"] = "no_trail"
        return report
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        report["reason"] = "audit_read_failed"
        report["error"] = str(error)
        return report
    kept_lines: list[str] = []
    for line in lines:
        text = line.strip()
        if not text:
            continue
        try:
            record = json.loads(text)
        except json.JSONDecodeError:
            kept_lines.append(line)
            report["malformed_count"] += 1
            continue
        if not isinstance(record, dict):
            kept_lines.append(line)
            report["malformed_count"] += 1
            continue
        if login_audit_tombstone_is_compactable(record, now=moment, retention_days=retention_days):
            report["compacted_count"] += 1
            report["compacted_tasks"].append(str(record.get("task_name") or ""))
            continue
        if is_login_audit_tombstone(record):
            report["tombstone_count"] += 1
        else:
            report["kept_count"] += 1
        kept_lines.append(line)
    if report["compacted_count"] == 0:
        report["reason"] = "nothing_compactable"
        return report
    try:
        handle, tmp_name = tempfile.mkstemp(
            prefix=path.name + ".", suffix=".tmp", dir=str(path.parent)
        )
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                for line in kept_lines:
                    stream.write(line.rstrip("\n") + "\n")
            os.replace(tmp_name, path)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
    except OSError as error:
        report["reason"] = "audit_write_failed"
        report["error"] = str(error)
        return report
    report["compacted"] = True
    report["reason"] = "long_gone"
    return report


def loop_login_compact_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.loop_login_compact import "
        "builtin_loop_login_compact_proof; r=builtin_loop_login_compact_proof(); "
        "assert r['ok'] and r.get('action')=='loop_login_compact' "
        "and r.get('passed_count',0) >= 18 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_loop_login_compact_capability(*, repo_path: Path | None = None) -> Capability:
    """Register login-tombstone compact on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=LOOP_LOGIN_COMPACT_ID,
        name="Continuous-loop login-tombstone compact",
        description=(
            "A durable login-scrub audit trail's tombstones are compacted "
            "once the records they name are long gone so the trail stays "
            "small and reconcilable without disturbing a live owner pid in "
            "any surviving repo."
        ),
        kind="python",
        entry="blackhole_agent.loop_login_compact:builtin_loop_login_compact_proof",
        proof_command=loop_login_compact_proof_command(),
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
            "capability.loop-login-tombstone",
        ),
        behavior_paths=(
            "src/blackhole_agent/loop_login_compact.py",
            "src/blackhole_agent/loop_login_tombstone.py",
            "src/blackhole_agent/loop_login_prune.py",
            "src/blackhole_agent/loop_login_audit.py",
            "src/blackhole_agent/unbound.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A durable login-scrub audit trail stays small: tombstones whose "
            "named records are long gone are compacted automatically on "
            "every recorded scrub and on demand, recent and unproven "
            "tombstones are kept so the trail stays reconcilable, the "
            "rewrite is atomic, and a live owner pid is never disturbed."
        ),
        tags=("continuous-loop", "login", "startup", "restore", "audit", "prune", "tombstone", "compact"),
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
            "loop_id": "login-compact-proof",
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
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat().replace("+00:00", "Z")


def builtin_loop_login_compact_proof() -> dict[str, Any]:
    """Hermetic proof: long-gone tombstones are compacted; live owners kept."""

    from blackhole_agent.evolution_quality import behavior_family
    from blackhole_agent.kernel_genesis_diversify import DIVERSITY_CATALOG
    from blackhole_agent.kernel_leftover import leftover_marker_ids
    from blackhole_agent.loop_login_audit import (
        login_audit_log_path,
        read_login_scrub_audit,
        record_login_task_scrub,
    )
    from blackhole_agent.loop_login_prune import DEFAULT_PRUNE_RETENTION_DAYS
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
    from blackhole_agent.loop_login_tombstone import (
        LOGIN_AUDIT_TOMBSTONE_EVENT,
        LOOP_LOGIN_TOMBSTONE_ID,
        is_login_audit_tombstone,
    )
    from blackhole_agent.unbound import continuous_loop_lock_path, pid_is_running

    checks: dict[str, bool] = {}
    checks["denylists_self"] = LOOP_LOGIN_COMPACT_ID in LOCAL_DENYLIST
    checks["denylists_next_family"] = LOOP_LOGIN_ROLLUP_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(LOOP_LOGIN_COMPACT_GOAL) == (
        LOOP_LOGIN_COMPACT_ID,
    )
    checks["leftover_text_binds_next_family"] = leftover_marker_ids(
        LOOP_LOGIN_ROLLUP_LEFTOVER
    ) == (LOOP_LOGIN_ROLLUP_ID,)
    checks["next_family_goal_is_login_rollup"] = leftover_marker_ids(
        LOOP_LOGIN_ROLLUP_GOAL
    ) == (LOOP_LOGIN_ROLLUP_ID,)
    checks["prior_family_markers_stay"] = leftover_marker_ids(LOOP_LOGIN_COMPACT_LEFTOVER) == (
        LOOP_LOGIN_COMPACT_ID,
    )
    catalog = DIVERSITY_CATALOG
    checks["catalog_names_login_compact"] = (
        len(catalog) > 252
        and catalog[252]["id"] == LOOP_LOGIN_COMPACT_ID
        and catalog[252]["goal"] == LOOP_LOGIN_COMPACT_GOAL
        and catalog[252]["done_when"] == LOOP_LOGIN_COMPACT_DONE_WHEN
        and catalog[252]["source"] == "genesis_bind_loop_login_compact"
    )
    checks["catalog_names_login_rollup"] = (
        len(catalog) > 253
        and catalog[253]["id"] == LOOP_LOGIN_ROLLUP_ID
        and catalog[253]["goal"] == LOOP_LOGIN_ROLLUP_GOAL
        and catalog[253]["done_when"] == LOOP_LOGIN_ROLLUP_DONE_WHEN
        and catalog[253]["source"] == "genesis_bind_loop_login_rollup"
    )
    checks["login_tombstone_stays_ahead"] = (
        len(catalog) > 251 and catalog[251]["id"] == LOOP_LOGIN_TOMBSTONE_ID
    )

    dead_pid = 1_000_251
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

    with tempfile.TemporaryDirectory(prefix="loop-login-compact-sweep-") as tmp:
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
        ancient_tombstone = {
            "schema_version": SCHEMA_VERSION,
            "event": LOGIN_AUDIT_TOMBSTONE_EVENT,
            "tombstone": True,
            "task_name": "ancient-task",
            "repo_path": str(orphan),
            "reason": "registration_gone",
            "aged_out_scrubbed_at": _aged_iso(DEFAULT_COMPACT_RETENTION_DAYS + 120),
            "pruned_at": _aged_iso(DEFAULT_COMPACT_RETENTION_DAYS + 30),
            "retention_days": DEFAULT_PRUNE_RETENTION_DAYS,
        }
        recent_tombstone = dict(
            ancient_tombstone,
            task_name="recent-task",
            aged_out_scrubbed_at=_aged_iso(130),
            pruned_at=_aged_iso(100),
        )
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
        audit_path = login_audit_log_path(orphan_audit_root)
        audit_path.write_text(
            json.dumps(ancient_tombstone, sort_keys=True) + "\n"
            + json.dumps(stale_entry, sort_keys=True) + "\n"
            + json.dumps(recent_tombstone, sort_keys=True) + "\n",
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
        tombstone_names = sorted(str(entry.get("task_name") or "") for entry in tombstones)
        names = [str(entry.get("task_name") or "") for entry in entries]
        checks["sweep_append_compacts_long_gone_tombstones"] = (
            swept.get("action") == "sweep"
            and swept.get("swept") == [LOGIN_TASK_NAME]
            and swept.get("scrubbed_count") == 2
            and swept.get("audit_recorded") == 1
            and trail.get("entry_count") == 3
            and trail.get("tombstone_count") == 2
            and tombstone_names == ["recent-task", "stale-task"]
            and "ancient-task" not in names
            and LOGIN_TASK_NAME in names
            and len(starts) == starts_before
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

    with tempfile.TemporaryDirectory(prefix="loop-login-compact-standalone-") as tmp:
        root = Path(tmp)
        missing = compact_login_audit_tombstones(root)
        path = login_audit_log_path(root)
        ancient = {
            "event": LOGIN_AUDIT_TOMBSTONE_EVENT,
            "tombstone": True,
            "task_name": "ancient-task",
            "repo_path": str(root / "repo"),
            "aged_out_scrubbed_at": _aged_iso(DEFAULT_COMPACT_RETENTION_DAYS + 60),
            "pruned_at": _aged_iso(DEFAULT_COMPACT_RETENTION_DAYS + 10),
            "retention_days": DEFAULT_PRUNE_RETENTION_DAYS,
        }
        recent = dict(ancient, task_name="recent-task", pruned_at=_aged_iso(200))
        undated = dict(ancient, task_name="undated-task", pruned_at="not-a-timestamp")
        stale_record = {
            "event": "login_task_artifacts_scrubbed",
            "task_name": "stale-record",
            "scrubbed_at": _aged_iso(DEFAULT_PRUNE_RETENTION_DAYS + 10),
        }
        path.write_text(
            json.dumps(ancient, sort_keys=True) + "\n"
            + json.dumps(recent, sort_keys=True) + "\n"
            + json.dumps(undated, sort_keys=True) + "\n"
            + json.dumps(stale_record, sort_keys=True) + "\n"
            + "not json at all\n",
            encoding="utf-8",
        )
        compacted = compact_login_audit_tombstones(root)
        trail = read_login_scrub_audit(root)
        entries = trail.get("entries") or []
        names = [str(entry.get("task_name") or "") for entry in entries]
        checks["standalone_compact_drops_long_gone_tombstones"] = (
            missing.get("compacted") is False
            and missing.get("reason") == "no_trail"
            and compacted.get("compacted") is True
            and compacted.get("compacted_count") == 1
            and compacted.get("compacted_tasks") == ["ancient-task"]
            and compacted.get("reason") == "long_gone"
            and trail.get("entry_count") == 3
            and trail.get("tombstone_count") == 2
            and "ancient-task" not in names
            and "recent-task" in names
        )
        checks["compact_keeps_unproven_tombstones_records_and_malformed"] = (
            "undated-task" in names
            and "stale-record" in names
            and compacted.get("kept_count") == 1
            and compacted.get("malformed_count") == 1
            and trail.get("malformed_count") == 1
            and "not json at all" in path.read_text(encoding="utf-8")
        )
        raw_before = path.read_bytes()
        again = compact_login_audit_tombstones(root)
        checks["compact_is_idempotent"] = (
            again.get("compacted") is False
            and again.get("compacted_count") == 0
            and again.get("reason") == "nothing_compactable"
            and path.read_bytes() == raw_before
            and read_login_scrub_audit(root).get("tombstone_count") == 2
        )

    with tempfile.TemporaryDirectory(prefix="loop-login-compact-append-") as tmp:
        root = Path(tmp)
        task = {"name": LOGIN_TASK_NAME, "repo_path": str(root / "repo")}
        report = {
            "reason": "registration_gone",
            "scrubbed_paths": [str(root / "a.py"), str(root / "b.xml")],
            "kept_foreign": [],
        }
        ancient = {
            "event": LOGIN_AUDIT_TOMBSTONE_EVENT,
            "tombstone": True,
            "task_name": "ancient-task",
            "pruned_at": _aged_iso(DEFAULT_COMPACT_RETENTION_DAYS + 5),
            "retention_days": DEFAULT_PRUNE_RETENTION_DAYS,
        }
        path = login_audit_log_path(root)
        path.write_text(json.dumps(ancient, sort_keys=True) + "\n", encoding="utf-8")
        starts_before = len(starts)
        recorded = record_login_task_scrub(task, report, audit_root=root)
        trail = read_login_scrub_audit(root)
        entries = trail.get("entries") or []
        names = [str(entry.get("task_name") or "") for entry in entries]
        checks["recorded_scrub_compacts_on_append"] = (
            recorded.get("recorded") is True
            and recorded.get("audit_tombstones_compacted") is True
            and recorded.get("audit_tombstones_compacted_count") == 1
            and trail.get("entry_count") == 1
            and trail.get("tombstone_count") == 0
            and names == [LOGIN_TASK_NAME]
            and len(starts) == starts_before
        )

    checks["next_family_is_not_handshake"] = (
        behavior_family(LOOP_LOGIN_ROLLUP_GOAL) != "network/handshake-digest-demo"
        and LOOP_LOGIN_ROLLUP_DONE_WHEN != ""
    )
    checks["contract_is_outcome_level"] = (
        "capability_exists:" not in LOOP_LOGIN_COMPACT_DONE_WHEN
        and "capability_proved:" not in LOOP_LOGIN_COMPACT_DONE_WHEN
    )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_loop_login_compact_capability()
    return {
        "ok": ok,
        "action": "loop_login_compact",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": LOOP_LOGIN_COMPACT_GOAL,
        "done_when": LOOP_LOGIN_COMPACT_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
