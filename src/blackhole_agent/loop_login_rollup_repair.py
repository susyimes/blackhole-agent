"""Correct a drifted login-scrub audit trail rollup against the trail.

Login-rollup verify checks a trail's durable compaction rollup against the
trail it summarizes and reports drift, but a drifted rollup keeps
misstating what was compacted until an operator rewrites the drifted
rollup by hand.

This module is the repair path: a drifted rollup is corrected against the
trail so the durable rollup states what was compacted. Corrections stay
provable from the surviving trail alone: duplicate rollup lines are merged
back into the single line the compact merge keeps, counts are raised to
the minimum the runs imply, inverted or unparseable span edges are
reordered, and a claimed span that covers a tombstone still in the trail
is clamped below the survivor's prune time — the rollup may only claim
what no surviving record contradicts. The corrected rollup records the
drift it repaired. Every repair syncs a journal receipt beside the trail
naming all original claims and the correction before replacement,
the trail is re-verified in memory before any write,
the rewrite rides the compact's atomic temp-file-and-replace, and only
the audit trail and its journal are touched, so a live owner pid in any surviving repo is
never disturbed. A trail whose rollup already verifies, has no rollup, or
is missing is left byte-identical; a rollup whose span cannot be repaired
without inventing timestamps is reported, never rewritten.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

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
from blackhole_agent.loop_login_rollup_journal import (
    LOOP_LOGIN_ROLLUP_JOURNAL_DONE_WHEN,
    LOOP_LOGIN_ROLLUP_JOURNAL_GOAL,
    LOOP_LOGIN_ROLLUP_JOURNAL_ID,
    LOOP_LOGIN_ROLLUP_JOURNAL_LEFTOVER,
)

SCHEMA_VERSION = 1
LOOP_LOGIN_ROLLUP_REPAIR_ID = "capability.loop-login-rollup-repair"
LOOP_LOGIN_ROLLUP_REPAIR_DONE_WHEN = (
    "A drifted login-scrub audit trail rollup is corrected against the trail "
    "it summarizes so the durable rollup states what was compacted without "
    "disturbing a live owner pid in any surviving repo."
)
LOOP_LOGIN_ROLLUP_REPAIR_GOAL = (
    "Repair login-rollup drift persistence: a drifted compaction rollup is "
    "detected, but the drifted rollup keeps misstating what was compacted "
    "until an operator rewrites the drifted rollup by hand."
)
LOOP_LOGIN_ROLLUP_REPAIR_LEFTOVER = (
    "Later genesis can take login-rollup drift persistence so a drifted "
    "rollup is corrected without an operator rewriting the drifted rollup "
    "by hand."
)
REPO_ROOT = Path(__file__).resolve().parents[2]


def correct_login_audit_rollup_records(records: list[Any]) -> tuple[dict[str, Any] | None, list[str]]:
    """Return the provable correction for drifted rollups and the corrections.

    Every correction is derivable from the surviving trail: the rollups are
    merged back into the single line the compact merge keeps, counts are
    raised to the minimum the compaction runs imply, inverted or
    unparseable span edges are reordered, and a claimed span covering a
    surviving tombstone is clamped below the survivor's prune time. Returns
    ``(None, [])`` when no rollup exists.
    """

    from blackhole_agent.loop_login_prune import _parse_audit_time
    from blackhole_agent.loop_login_rollup import (
        is_login_audit_rollup,
        merge_login_audit_rollup,
    )
    from blackhole_agent.loop_login_tombstone import is_login_audit_tombstone

    rollups = [record for record in records if isinstance(record, dict) and is_login_audit_rollup(record)]
    if not rollups:
        return None, []
    corrections: list[str] = []
    merged = rollups[0]
    for extra in rollups[1:]:
        merged = merge_login_audit_rollup(merged, extra)
    if len(rollups) > 1:
        corrections.append("merged_duplicate_rollup")
    merged = dict(merged)

    def _count(value: Any) -> int | None:
        if isinstance(value, bool) or not isinstance(value, int):
            return None
        return value

    runs = _count(merged.get("compaction_runs"))
    if runs is None or runs < 1:
        runs = 1
        corrections.append("compaction_runs_floored")
    count = _count(merged.get("compacted_count"))
    if count is None or count < runs:
        count = max(runs, 1)
        corrections.append("compacted_count_raised_to_runs")
    merged["compaction_runs"] = runs
    merged["compacted_count"] = count

    oldest = str(merged.get("oldest_pruned_at") or "")
    newest = str(merged.get("newest_pruned_at") or "")
    oldest_dt = _parse_audit_time(oldest)
    newest_dt = _parse_audit_time(newest)
    if oldest_dt is None and newest_dt is not None:
        oldest_dt = newest_dt
        corrections.append("oldest_pruned_at_taken_from_newest")
    elif newest_dt is None and oldest_dt is not None:
        newest_dt = oldest_dt
        corrections.append("newest_pruned_at_taken_from_oldest")
    if oldest_dt is None or newest_dt is None:
        fallback = _parse_audit_time(merged.get("last_compacted_at"))
        if fallback is None:
            return merged, corrections + ["span_unrepairable"]
        if oldest_dt is None:
            oldest_dt = fallback
            corrections.append("oldest_pruned_at_taken_from_compacted_at")
        if newest_dt is None:
            newest_dt = fallback
            corrections.append("newest_pruned_at_taken_from_compacted_at")
    if oldest_dt > newest_dt:
        oldest_dt, newest_dt = newest_dt, oldest_dt
        corrections.append("span_edges_swapped")
    survivors = [
        _parse_audit_time(record.get("pruned_at"))
        for record in records
        if isinstance(record, dict) and is_login_audit_tombstone(record)
    ]
    survivor_dts = [dt for dt in survivors if dt is not None and dt <= newest_dt]
    if survivor_dts:
        newest_dt = min(survivor_dts) - timedelta(microseconds=1)
        corrections.append("span_clamped_below_survivor")
        if oldest_dt > newest_dt:
            oldest_dt = newest_dt
            corrections.append("oldest_pruned_at_clamped_to_newest")
    merged["oldest_pruned_at"] = oldest_dt.isoformat().replace("+00:00", "Z")
    merged["newest_pruned_at"] = newest_dt.isoformat().replace("+00:00", "Z")
    return merged, corrections


def repair_login_audit_rollup(root: Path | None = None) -> dict[str, Any]:
    """Correct a drifted rollup so the durable rollup states what was compacted.

    The trail's rollup is verified first; drift is corrected in memory and
    re-verified before anything is written, so a trail whose rollup already
    verifies — or cannot be repaired without inventing timestamps — is left
    byte-identical. Every original rollup is synced to the repair journal
    before atomic replacement. A failed receipt write prevents replacement.
    Only the audit trail and its journal are touched; owner state, locks,
    scheduler entries and launch artifacts are never changed.
    """

    from blackhole_agent.loop_login_audit import login_audit_log_path
    from blackhole_agent.loop_login_rollup import is_login_audit_rollup
    from blackhole_agent.loop_login_verify import (
        _read_login_audit_snapshot,
        _verify_login_audit_snapshot,
        verify_login_audit_rollup_records,
    )

    path = login_audit_log_path(root)
    report: dict[str, Any] = {
        "action": "rollup_repair",
        "audit_path": str(path),
        "repaired": False,
        "reason": "no_trail",
        "drift": [],
        "corrections": [],
        "rollup": None,
        "repaired_at": "",
        "repair_journaled": False,
        "repair_journal_completed": False,
    }
    snapshot = _read_login_audit_snapshot(path)
    verdict = _verify_login_audit_snapshot(snapshot)
    report["drift"] = list(verdict.get("drift") or [])
    if snapshot["reason"] != "read":
        report["reason"] = snapshot["reason"]
        if "error" in snapshot:
            report["error"] = snapshot["error"]
        return report
    if verdict["malformed_count"]:
        report.update(reason="audit_incomplete", verification=verdict)
        return report
    lines, records = snapshot["lines"], snapshot["records"]
    if not verdict.get("rollup_present"):
        report["reason"] = "no_rollup"
        return report
    if verdict.get("verified"):
        report["reason"] = "already_verified"
        report["rollup"] = verdict.get("rollup")
        return report
    corrected, corrections = correct_login_audit_rollup_records(records)
    if corrected is None or "span_unrepairable" in corrections:
        report["reason"] = "unrepairable_span"
        report["corrections"] = corrections
        return report
    corrected = dict(
        corrected,
        repaired_at=utc_now_iso(),
        repair_drift=list(verdict.get("drift") or []),
        repair_id=uuid4().hex,
    )
    candidate_records = [corrected if isinstance(record, dict) and is_login_audit_rollup(record) else record for record in records]
    seen_rollup = False
    kept_records: list[Any] = []
    for record in candidate_records:
        if isinstance(record, dict) and is_login_audit_rollup(record):
            if seen_rollup:
                continue
            seen_rollup = True
        kept_records.append(record)
    post = verify_login_audit_rollup_records(kept_records)
    if not post.get("verified"):
        report["reason"] = "repair_failed"
        report["corrections"] = corrections
        report["post_verification"] = post
        return report
    kept_lines: list[str] = []
    written_rollup = False
    for line in lines:
        text = line.strip()
        if not text:
            continue
        try:
            record = json.loads(text)
        except json.JSONDecodeError:
            kept_lines.append(line)
            continue
        if isinstance(record, dict) and is_login_audit_rollup(record):
            if written_rollup:
                continue
            kept_lines.append(json.dumps(corrected, sort_keys=True))
            written_rollup = True
            continue
        kept_lines.append(line)
    from blackhole_agent.loop_login_rollup_journal import (
        complete_login_rollup_repair,
        record_login_rollup_repair,
    )

    prior_rollups = [record for record in records if is_login_audit_rollup(record)]
    report["corrections"] = corrections
    report["repair_id"] = corrected["repair_id"]
    try:
        handle, tmp_name = tempfile.mkstemp(
            prefix=path.name + ".", suffix=".tmp", dir=str(path.parent)
        )
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                for line in kept_lines:
                    stream.write(line.rstrip("\n") + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            journaled = record_login_rollup_repair(
                root,
                drift=report["drift"],
                corrections=corrections,
                prior_rollup=prior_rollups[0],
                prior_rollups=prior_rollups,
                corrected_rollup=corrected,
                repaired_at=corrected["repaired_at"],
                repair_id=corrected["repair_id"],
                state="prepared",
            )
            report["journal_path"] = journaled["journal_path"]
            if not journaled["journaled"]:
                report.update(reason="journal_write_failed", error=journaled["error"])
                return report
            report["repair_journaled"] = True
            os.replace(tmp_name, path)
        finally:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
    except OSError as error:
        report["reason"] = "audit_write_failed"
        report["error"] = str(error)
        return report
    report["repaired"] = True
    report["reason"] = "drift_corrected"
    report["corrections"] = corrections
    report["rollup"] = corrected
    report["repaired_at"] = corrected["repaired_at"]
    report["post_verification"] = post
    completed = complete_login_rollup_repair(root, corrected["repair_id"])
    report["repair_journal_completed"] = completed["journaled"]
    if not completed["journaled"]:
        report["journal_completion_error"] = completed["error"]
    return report


def loop_login_rollup_repair_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.loop_login_rollup_repair import "
        "builtin_loop_login_rollup_repair_proof; r=builtin_loop_login_rollup_repair_proof(); "
        "assert r['ok'] and r.get('action')=='loop_login_rollup_repair' "
        "and r.get('passed_count',0) >= 18 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_loop_login_rollup_repair_capability(*, repo_path: Path | None = None) -> Capability:
    """Register login-rollup repair on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=LOOP_LOGIN_ROLLUP_REPAIR_ID,
        name="Continuous-loop login-rollup repair",
        description=(
            "A drifted login-scrub audit trail rollup is corrected against "
            "the trail it summarizes so the durable rollup states what was "
            "compacted without disturbing a live owner pid in any surviving "
            "repo."
        ),
        kind="python",
        entry="blackhole_agent.loop_login_rollup_repair:builtin_loop_login_rollup_repair_proof",
        proof_command=loop_login_rollup_repair_proof_command(),
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
            "capability.loop-login-compact",
            "capability.loop-login-rollup",
            "capability.loop-login-verify",
        ),
        behavior_paths=(
            "src/blackhole_agent/loop_login_rollup_repair.py",
            "src/blackhole_agent/loop_login_verify.py",
            "src/blackhole_agent/loop_login_rollup.py",
            "src/blackhole_agent/loop_login_audit.py",
            "src/blackhole_agent/unbound.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A drifted login-scrub audit trail rollup is corrected against "
            "the trail it summarizes: duplicate rollup lines are merged, "
            "counts are raised to what the runs imply, inverted or "
            "unparseable span edges are reordered, and a span covering a "
            "surviving tombstone is clamped below the survivor; the "
            "corrected rollup records the drift it repaired, the trail is "
            "re-verified before the atomic rewrite, and a live owner pid is "
            "never disturbed."
        ),
        tags=("continuous-loop", "login", "startup", "restore", "audit", "prune", "tombstone", "compact", "rollup", "verify", "repair"),
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
            "loop_id": "login-rollup-repair-proof",
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


def builtin_loop_login_rollup_repair_proof() -> dict[str, Any]:
    """Hermetic proof: a drifted rollup is corrected; live owners kept."""

    import os
    import tempfile

    from blackhole_agent.evolution_quality import behavior_family
    from blackhole_agent.kernel_genesis_diversify import DIVERSITY_CATALOG
    from blackhole_agent.kernel_leftover import leftover_marker_ids
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
    from blackhole_agent.loop_login_verify import (
        LOOP_LOGIN_VERIFY_ID,
        verify_login_audit_rollup,
    )
    from blackhole_agent.unbound import continuous_loop_lock_path, pid_is_running

    checks: dict[str, bool] = {}
    checks["denylists_self"] = LOOP_LOGIN_ROLLUP_REPAIR_ID in LOCAL_DENYLIST
    checks["denylists_next_family"] = LOOP_LOGIN_ROLLUP_JOURNAL_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(LOOP_LOGIN_ROLLUP_REPAIR_GOAL) == (
        LOOP_LOGIN_ROLLUP_REPAIR_ID,
    )
    checks["leftover_text_binds_next_family"] = leftover_marker_ids(
        LOOP_LOGIN_ROLLUP_JOURNAL_LEFTOVER
    ) == (LOOP_LOGIN_ROLLUP_JOURNAL_ID,)
    checks["next_family_goal_is_rollup_journal"] = leftover_marker_ids(
        LOOP_LOGIN_ROLLUP_JOURNAL_GOAL
    ) == (LOOP_LOGIN_ROLLUP_JOURNAL_ID,)
    checks["prior_family_markers_stay"] = leftover_marker_ids(LOOP_LOGIN_ROLLUP_REPAIR_LEFTOVER) == (
        LOOP_LOGIN_ROLLUP_REPAIR_ID,
    )
    catalog = DIVERSITY_CATALOG
    checks["catalog_names_login_rollup_repair"] = (
        len(catalog) > 255
        and catalog[255]["id"] == LOOP_LOGIN_ROLLUP_REPAIR_ID
        and catalog[255]["goal"] == LOOP_LOGIN_ROLLUP_REPAIR_GOAL
        and catalog[255]["done_when"] == LOOP_LOGIN_ROLLUP_REPAIR_DONE_WHEN
        and catalog[255]["source"] == "genesis_bind_loop_login_rollup_repair"
    )
    checks["catalog_names_login_rollup_journal"] = (
        len(catalog) > 256
        and catalog[256]["id"] == LOOP_LOGIN_ROLLUP_JOURNAL_ID
        and catalog[256]["goal"] == LOOP_LOGIN_ROLLUP_JOURNAL_GOAL
        and catalog[256]["done_when"] == LOOP_LOGIN_ROLLUP_JOURNAL_DONE_WHEN
        and catalog[256]["source"] == "genesis_bind_loop_login_rollup_journal"
    )
    checks["login_verify_stays_ahead"] = (
        len(catalog) > 254 and catalog[254]["id"] == LOOP_LOGIN_VERIFY_ID
    )

    def tombstone(task_name: str, *, pruned_days: int) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "event": LOGIN_AUDIT_TOMBSTONE_EVENT,
            "tombstone": True,
            "task_name": task_name,
            "reason": "registration_gone",
            "aged_out_scrubbed_at": _aged_iso(pruned_days + DEFAULT_PRUNE_RETENTION_DAYS),
            "pruned_at": _aged_iso(pruned_days),
            "retention_days": DEFAULT_PRUNE_RETENTION_DAYS,
        }

    def rollup(**overrides: Any) -> dict[str, Any]:
        record = {
            "schema_version": SCHEMA_VERSION,
            "event": LOGIN_AUDIT_ROLLUP_EVENT,
            "rollup": True,
            "compacted_count": 2,
            "compaction_runs": 2,
            "oldest_pruned_at": _aged_iso(400),
            "newest_pruned_at": _aged_iso(380),
            "last_compacted_at": _aged_iso(15),
        }
        record.update(overrides)
        return record

    dead_pid = 1_000_311
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

    with tempfile.TemporaryDirectory(prefix="loop-login-rollup-repair-sweep-") as tmp:
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
        audit_path = login_audit_log_path(orphan_audit_root)
        audit_path.write_text(
            json.dumps(tombstone("ancient-a", pruned_days=DEFAULT_COMPACT_RETENTION_DAYS + 40), sort_keys=True)
            + "\n"
            + json.dumps(tombstone("ancient-b", pruned_days=DEFAULT_COMPACT_RETENTION_DAYS + 10), sort_keys=True)
            + "\n"
            + json.dumps(tombstone("recent-task", pruned_days=90), sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        login_startup_registration_path(orphan).unlink()
        before = surviving_state.read_bytes()
        starts_before = len(starts)
        swept = sweep_login_tasks_missing_registration(scheduler=scheduler)
        intact = repair_login_audit_rollup(orphan_audit_root)
        intact_bytes = audit_path.read_bytes()
        checks["intact_rollup_is_left_byte_identical"] = (
            swept.get("action") == "sweep"
            and intact.get("repaired") is False
            and intact.get("reason") == "already_verified"
            and audit_path.read_bytes() == intact_bytes
        )
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
        trail = read_login_scrub_audit(orphan_audit_root)
        surfaced = trail.get("tombstone_rollup_verification") or {}
        corrected = repaired.get("rollup") or {}
        rollups_after = [
            entry for entry in (trail.get("entries") or []) if is_login_audit_rollup(entry)
        ]
        result = dispatch_login_startup(surviving, controller_starter=starter)
        checks["drifted_rollup_is_corrected_against_trail"] = (
            drifted.get("verified") is False
            and repaired.get("repaired") is True
            and repaired.get("reason") == "drift_corrected"
            and "span_survivor" in repaired.get("drift")
            and "span_clamped_below_survivor" in repaired.get("corrections")
            and "compacted_count_raised_to_runs" in repaired.get("corrections")
            and len(rollups_after) == 1
            and corrected.get("compacted_count") == 1
            and corrected.get("repair_drift")
            and corrected.get("repaired_at")
            and post.get("verified") is True
            and post.get("drift") == []
            and surfaced.get("verified") is True
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

    with tempfile.TemporaryDirectory(prefix="loop-login-rollup-repair-cases-") as tmp:
        root = Path(tmp)
        path = login_audit_log_path(root)
        base = json.dumps(tombstone("kept-task", pruned_days=30), sort_keys=True) + "\n"

        def repair_with(lines: list[dict[str, Any]]) -> dict[str, Any]:
            path.write_text(
                "".join(json.dumps(line, sort_keys=True) + "\n" for line in lines),
                encoding="utf-8",
            )
            return repair_login_audit_rollup(root)

        duplicate = repair_with([tombstone("kept-task", pruned_days=30), rollup(), rollup(compacted_count=3)])
        corrected = duplicate.get("rollup") or {}
        checks["duplicate_rollups_merge_back_to_one_line"] = (
            duplicate.get("repaired") is True
            and "merged_duplicate_rollup" in duplicate.get("corrections")
            and corrected.get("compacted_count") == 5
            and corrected.get("compaction_runs") == 4
            and (duplicate.get("post_verification") or {}).get("verified") is True
            and len(path.read_text(encoding="utf-8").splitlines()) == 2
        )
        inverted = repair_with([tombstone("kept-task", pruned_days=30), rollup(oldest_pruned_at=_aged_iso(300), newest_pruned_at=_aged_iso(320))])
        corrected = inverted.get("rollup") or {}
        checks["inverted_span_is_reordered"] = (
            inverted.get("repaired") is True
            and "span_edges_swapped" in inverted.get("corrections")
            and corrected.get("oldest_pruned_at") <= corrected.get("newest_pruned_at")
            and (inverted.get("post_verification") or {}).get("verified") is True
        )
        undated = repair_with([tombstone("kept-task", pruned_days=30), rollup(newest_pruned_at="not-a-timestamp")])
        checks["unparseable_span_edge_is_restored"] = (
            undated.get("repaired") is True
            and "newest_pruned_at_taken_from_oldest" in undated.get("corrections")
            and (undated.get("post_verification") or {}).get("verified") is True
        )
        forged_span = repair_with([tombstone("kept-task", pruned_days=30), rollup(newest_pruned_at=_aged_iso(0))])
        corrected = forged_span.get("rollup") or {}
        checks["span_covering_survivor_is_clamped"] = (
            forged_span.get("repaired") is True
            and "span_clamped_below_survivor" in forged_span.get("corrections")
            and corrected.get("newest_pruned_at") < _aged_iso(30)
            and (forged_span.get("post_verification") or {}).get("verified") is True
        )
        unrepairable_rollup = rollup(oldest_pruned_at="", newest_pruned_at="", last_compacted_at="")
        path.write_text(
            base + json.dumps(unrepairable_rollup, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        raw = path.read_bytes()
        unrepairable = repair_login_audit_rollup(root)
        checks["unrepairable_span_is_reported_never_rewritten"] = (
            unrepairable.get("repaired") is False
            and unrepairable.get("reason") == "unrepairable_span"
            and path.read_bytes() == raw
        )
        missing = repair_login_audit_rollup(root / "no-such-dir")
        path.write_text(base, encoding="utf-8")
        no_rollup = repair_login_audit_rollup(root)
        checks["trail_without_rollup_is_left_alone"] = (
            missing.get("repaired") is False
            and missing.get("reason") == "no_trail"
            and not (root / "no-such-dir").exists()
            and no_rollup.get("repaired") is False
            and no_rollup.get("reason") == "no_rollup"
            and path.read_text(encoding="utf-8") == base
        )

    with tempfile.TemporaryDirectory(prefix="loop-login-rollup-repair-compact-") as tmp:
        root = Path(tmp)
        path = login_audit_log_path(root)
        path.write_text(
            json.dumps(tombstone("first-old", pruned_days=DEFAULT_COMPACT_RETENTION_DAYS + 50), sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        compact_login_audit_tombstones(root)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(tombstone("second-old", pruned_days=DEFAULT_COMPACT_RETENTION_DAYS + 5), sort_keys=True)
                + "\n"
            )
        compact_login_audit_tombstones(root)
        starts_before = len(starts)
        idle = repair_login_audit_rollup(root)
        checks["compacted_trail_needs_no_repair"] = (
            idle.get("repaired") is False
            and idle.get("reason") == "already_verified"
            and (idle.get("rollup") or {}).get("compacted_count") == 2
            and len(starts) == starts_before
        )

    checks["next_family_is_not_handshake"] = (
        behavior_family(LOOP_LOGIN_ROLLUP_JOURNAL_GOAL) != "network/handshake-digest-demo"
        and LOOP_LOGIN_ROLLUP_JOURNAL_DONE_WHEN != ""
    )
    checks["contract_is_outcome_level"] = (
        "capability_exists:" not in LOOP_LOGIN_ROLLUP_REPAIR_DONE_WHEN
        and "capability_proved:" not in LOOP_LOGIN_ROLLUP_REPAIR_DONE_WHEN
    )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_loop_login_rollup_repair_capability()
    return {
        "ok": ok,
        "action": "loop_login_rollup_repair",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": LOOP_LOGIN_ROLLUP_REPAIR_GOAL,
        "done_when": LOOP_LOGIN_ROLLUP_REPAIR_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
