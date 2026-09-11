"""Prune aged-out records from the durable login-scrub audit trail.

Login-task scrub records every swept task's scrubbed artifacts in a durable
JSONL audit trail so an operator can reconcile deletions. But every sweep
appends and nothing ever removes: the trail grows without bound until an
operator prunes stale entries by hand.

This module is the prune path: audit records whose scrub time is older than
the retention window have aged out and are pruned so the trail stays
bounded. Pruning runs automatically on every recorded scrub (prune-on-append,
so each sweep keeps the trail bounded) and is also exposed as a standalone
prune for trails that no longer receive scrubs. Every pruned record is
replaced in place by a durable tombstone naming what aged out — the task,
its repo, and the original scrub time — so an operator reconciling the
bounded trail can tell an aged-out record from one that was never written.
A tombstone is never stale itself, so later prunes keep it byte-identical.
The prune only rewrites the
audit trail file: records it cannot prove stale — fresh records, records
with an unparseable scrub time, and malformed lines — are kept, and the
scheduler, launcher, and task XML of any surviving repo are never touched,
so a live owner pid in any surviving repo is never disturbed.
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
from blackhole_agent.loop_login_tombstone import (
    LOOP_LOGIN_TOMBSTONE_DONE_WHEN,
    LOOP_LOGIN_TOMBSTONE_GOAL,
    LOOP_LOGIN_TOMBSTONE_ID,
    LOOP_LOGIN_TOMBSTONE_LEFTOVER,
    is_login_audit_tombstone,
    login_audit_tombstone_for,
)

SCHEMA_VERSION = 1
LOOP_LOGIN_PRUNE_ID = "capability.loop-login-prune"
LOOP_LOGIN_PRUNE_DONE_WHEN = (
    "A durable login-scrub audit trail's stale records are pruned once they "
    "age out so the trail stays bounded without disturbing a live owner pid "
    "in any surviving repo."
)
LOOP_LOGIN_PRUNE_GOAL = (
    "Repair login-audit prune: the durable scrub audit trail grows without "
    "bound as every sweep appends, until an operator prunes stale entries "
    "by hand."
)
LOOP_LOGIN_PRUNE_LEFTOVER = (
    "Later genesis can take login-audit prune so a durable scrub audit "
    "trail's stale records age out without an operator who prunes stale "
    "entries by hand."
)
DEFAULT_PRUNE_RETENTION_DAYS = 30
REPO_ROOT = Path(__file__).resolve().parents[2]


def _parse_audit_time(value: Any) -> datetime | None:
    """Parse a record's scrub time; None when it cannot be proven."""

    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def login_audit_record_is_stale(
    entry: dict[str, Any],
    *,
    now: datetime,
    retention_days: int = DEFAULT_PRUNE_RETENTION_DAYS,
) -> bool:
    """True only when the record's scrub time provably aged out.

    A record whose scrub time is missing or unparseable is never stale: the
    prune must not drop what it cannot prove aged out. A tombstone is never
    stale either: it is the durable trace of an earlier prune, so dropping
    it would reopen the hole the tombstone closed.
    """

    if is_login_audit_tombstone(entry):
        return False
    scrubbed_at = _parse_audit_time(entry.get("scrubbed_at"))
    if scrubbed_at is None:
        return False
    return now - scrubbed_at > timedelta(days=retention_days)


def prune_login_scrub_audit(
    root: Path | None = None,
    *,
    retention_days: int = DEFAULT_PRUNE_RETENTION_DAYS,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Prune aged-out records from a durable login-scrub audit trail.

    Records older than the retention window are dropped so the trail stays
    bounded, and each dropped record is replaced in place by a durable
    tombstone naming what aged out — the task, its repo, and the original
    scrub time — so an operator reconciling the bounded trail can tell an
    aged-out record from one that was never written. Tombstones are never
    stale, so a re-prune keeps them byte-identical. Fresh records, records
    with an unparseable scrub time, and malformed lines are kept; the rewrite
    is atomic (temp file + replace) and only happens when something actually
    aged out, so an intact trail is left byte-identical. A missing trail is
    reported, never created. Nothing here touches a scheduler entry,
    launcher, or task XML, so a live owner pid in any surviving repo is
    never disturbed.
    """

    from blackhole_agent.loop_login_audit import login_audit_log_path

    path = login_audit_log_path(root)
    moment = now or datetime.now(timezone.utc)
    report: dict[str, Any] = {
        "action": "audit_prune",
        "audit_path": str(path),
        "pruned": False,
        "pruned_count": 0,
        "kept_count": 0,
        "undated_count": 0,
        "malformed_count": 0,
        "tombstones_written": 0,
        "tombstone_count": 0,
        "retention_days": retention_days,
        "pruned_at": utc_now_iso(),
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
        if login_audit_record_is_stale(record, now=moment, retention_days=retention_days):
            tombstone = login_audit_tombstone_for(
                record,
                pruned_at=report["pruned_at"],
                retention_days=retention_days,
            )
            kept_lines.append(json.dumps(tombstone, sort_keys=True))
            report["pruned_count"] += 1
            report["tombstones_written"] += 1
            continue
        if is_login_audit_tombstone(record):
            report["tombstone_count"] += 1
        elif _parse_audit_time(record.get("scrubbed_at")) is None:
            report["undated_count"] += 1
        else:
            report["kept_count"] += 1
        kept_lines.append(line)
    if report["pruned_count"] == 0:
        report["reason"] = "nothing_stale"
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
    report["pruned"] = True
    report["reason"] = "aged_out"
    return report


def loop_login_prune_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.loop_login_prune import "
        "builtin_loop_login_prune_proof; r=builtin_loop_login_prune_proof(); "
        "assert r['ok'] and r.get('action')=='loop_login_prune' "
        "and r.get('passed_count',0) >= 18 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_loop_login_prune_capability(*, repo_path: Path | None = None) -> Capability:
    """Register login-audit prune on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=LOOP_LOGIN_PRUNE_ID,
        name="Continuous-loop login-audit prune",
        description=(
            "A durable login-scrub audit trail's stale records are pruned "
            "once they age out so the trail stays bounded without disturbing "
            "a live owner pid in any surviving repo."
        ),
        kind="python",
        entry="blackhole_agent.loop_login_prune:builtin_loop_login_prune_proof",
        proof_command=loop_login_prune_proof_command(),
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
        ),
        behavior_paths=(
            "src/blackhole_agent/loop_login_prune.py",
            "src/blackhole_agent/loop_login_audit.py",
            "src/blackhole_agent/loop_login_tombstone.py",
            "src/blackhole_agent/unbound.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A durable login-scrub audit trail stays bounded: records whose "
            "scrub time aged out are pruned automatically on every recorded "
            "scrub and on demand, fresh, undated, and malformed lines are "
            "kept, the rewrite is atomic, and a live owner pid is never "
            "disturbed."
        ),
        tags=("continuous-loop", "login", "startup", "restore", "audit", "prune"),
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
            "loop_id": "login-prune-proof",
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


def builtin_loop_login_prune_proof() -> dict[str, Any]:
    """Hermetic proof: aged-out audit records are pruned; live owners kept."""

    from blackhole_agent.evolution_quality import behavior_family
    from blackhole_agent.kernel_genesis_diversify import DIVERSITY_CATALOG
    from blackhole_agent.kernel_leftover import leftover_marker_ids
    from blackhole_agent.loop_login_audit import (
        LOOP_LOGIN_AUDIT_ID,
        login_audit_log_path,
        read_login_scrub_audit,
        record_login_task_scrub,
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
    checks["denylists_self"] = LOOP_LOGIN_PRUNE_ID in LOCAL_DENYLIST
    checks["denylists_next_family"] = LOOP_LOGIN_TOMBSTONE_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(LOOP_LOGIN_PRUNE_GOAL) == (
        LOOP_LOGIN_PRUNE_ID,
    )
    checks["leftover_text_binds_next_family"] = leftover_marker_ids(
        LOOP_LOGIN_TOMBSTONE_LEFTOVER
    ) == (LOOP_LOGIN_TOMBSTONE_ID,)
    checks["next_family_goal_is_login_tombstone"] = leftover_marker_ids(
        LOOP_LOGIN_TOMBSTONE_GOAL
    ) == (LOOP_LOGIN_TOMBSTONE_ID,)
    checks["prior_family_markers_stay"] = leftover_marker_ids(LOOP_LOGIN_PRUNE_LEFTOVER) == (
        LOOP_LOGIN_PRUNE_ID,
    )
    catalog = DIVERSITY_CATALOG
    checks["catalog_names_login_prune"] = (
        len(catalog) > 250
        and catalog[250]["id"] == LOOP_LOGIN_PRUNE_ID
        and catalog[250]["goal"] == LOOP_LOGIN_PRUNE_GOAL
        and catalog[250]["done_when"] == LOOP_LOGIN_PRUNE_DONE_WHEN
        and catalog[250]["source"] == "genesis_bind_loop_login_prune"
    )
    checks["catalog_names_login_tombstone"] = (
        len(catalog) > 251
        and catalog[251]["id"] == LOOP_LOGIN_TOMBSTONE_ID
        and catalog[251]["goal"] == LOOP_LOGIN_TOMBSTONE_GOAL
        and catalog[251]["done_when"] == LOOP_LOGIN_TOMBSTONE_DONE_WHEN
        and catalog[251]["source"] == "genesis_bind_loop_login_tombstone"
    )
    checks["login_audit_stays_ahead"] = (
        len(catalog) > 249 and catalog[249]["id"] == LOOP_LOGIN_AUDIT_ID
    )

    dead_pid = 1_000_211
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

    with tempfile.TemporaryDirectory(prefix="loop-login-prune-sweep-") as tmp:
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
        undated_entry = {
            "event": "login_task_artifacts_scrubbed",
            "task_name": "undated-task",
            "scrubbed_at": "not-a-timestamp",
        }
        audit_path = login_audit_log_path(orphan_audit_root)
        audit_path.write_text(
            json.dumps(stale_entry, sort_keys=True) + "\n"
            + json.dumps(fresh_entry, sort_keys=True) + "\n"
            + json.dumps(undated_entry, sort_keys=True) + "\n"
            + "not json at all\n",
            encoding="utf-8",
        )
        login_startup_registration_path(orphan).unlink()
        before = surviving_state.read_bytes()
        starts_before = len(starts)
        swept = sweep_login_tasks_missing_registration(scheduler=scheduler)
        result = dispatch_login_startup(surviving, controller_starter=starter)
        trail = read_login_scrub_audit(orphan_audit_root)
        entries = trail.get("entries") or []
        names = [str(entry.get("task_name") or "") for entry in entries]
        scrub_names = [
            str(entry.get("task_name") or "")
            for entry in entries
            if not is_login_audit_tombstone(entry)
        ]
        raw_lines = [
            line
            for line in audit_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        checks["sweep_append_prunes_aged_out_records"] = (
            swept.get("action") == "sweep"
            and swept.get("swept") == [LOGIN_TASK_NAME]
            and swept.get("scrubbed_count") == 2
            and swept.get("audit_recorded") == 1
            and "stale-task" not in scrub_names
            and "fresh-task" in names
            and LOGIN_TASK_NAME in names
            and trail.get("entry_count") == 4
            and trail.get("tombstone_count") == 1
            and len(raw_lines) == 5
            and len(starts) == starts_before
        )
        checks["malformed_and_undated_records_survive_prune"] = (
            "undated-task" in names
            and trail.get("malformed_count") == 1
            and "not json at all" in raw_lines
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

    with tempfile.TemporaryDirectory(prefix="loop-login-prune-trail-") as tmp:
        root = Path(tmp)
        task = {"name": LOGIN_TASK_NAME, "repo_path": str(root / "repo")}
        report = {
            "reason": "registration_gone",
            "scrubbed_paths": [str(root / "a.py"), str(root / "b.xml")],
            "kept_foreign": [],
        }
        path = login_audit_log_path(root)
        stale = {
            "event": "login_task_artifacts_scrubbed",
            "task_name": "aged-task",
            "scrubbed_at": _aged_iso(DEFAULT_PRUNE_RETENTION_DAYS + 30),
        }
        path.write_text(json.dumps(stale, sort_keys=True) + "\n", encoding="utf-8")
        starts_before = len(starts)
        recorded = record_login_task_scrub(task, report, audit_root=root)
        trail = read_login_scrub_audit(root)
        entries = trail.get("entries") or []
        names = [str(entry.get("task_name") or "") for entry in entries]
        scrub_names = [
            str(entry.get("task_name") or "")
            for entry in entries
            if not is_login_audit_tombstone(entry)
        ]
        checks["recorded_scrub_prunes_on_append"] = (
            recorded.get("recorded") is True
            and recorded.get("audit_pruned_count") == 1
            and trail.get("entry_count") == 2
            and trail.get("tombstone_count") == 1
            and "aged-task" not in scrub_names
            and LOGIN_TASK_NAME in names
            and len(starts) == starts_before
        )
        first_bytes = path.read_bytes()
        again = prune_login_scrub_audit(root)
        checks["prune_is_idempotent"] = (
            again.get("action") == "audit_prune"
            and again.get("pruned") is False
            and again.get("pruned_count") == 0
            and again.get("kept_count") == 1
            and again.get("reason") == "nothing_stale"
            and path.read_bytes() == first_bytes
            and len(starts) == starts_before
        )

    with tempfile.TemporaryDirectory(prefix="loop-login-prune-standalone-") as tmp:
        root = Path(tmp)
        missing = prune_login_scrub_audit(root)
        path = login_audit_log_path(root)
        stale = {
            "event": "login_task_artifacts_scrubbed",
            "task_name": "old-task",
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
        scrub_names = [
            str(entry.get("task_name") or "")
            for entry in entries
            if not is_login_audit_tombstone(entry)
        ]
        checks["standalone_prune_ages_out_stale_records"] = (
            missing.get("pruned") is False
            and missing.get("reason") == "no_trail"
            and pruned.get("pruned") is True
            and pruned.get("pruned_count") == 1
            and pruned.get("kept_count") == 1
            and pruned.get("tombstones_written") == 1
            and pruned.get("reason") == "aged_out"
            and trail.get("entry_count") == 2
            and trail.get("tombstone_count") == 1
            and scrub_names == ["new-task"]
        )

    checks["next_family_is_not_handshake"] = (
        behavior_family(LOOP_LOGIN_TOMBSTONE_GOAL) != "network/handshake-digest-demo"
        and LOOP_LOGIN_TOMBSTONE_DONE_WHEN != ""
    )
    checks["contract_is_outcome_level"] = (
        "capability_exists:" not in LOOP_LOGIN_PRUNE_DONE_WHEN
        and "capability_proved:" not in LOOP_LOGIN_PRUNE_DONE_WHEN
    )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_loop_login_prune_capability()
    return {
        "ok": ok,
        "action": "loop_login_prune",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": LOOP_LOGIN_PRUNE_GOAL,
        "done_when": LOOP_LOGIN_PRUNE_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
