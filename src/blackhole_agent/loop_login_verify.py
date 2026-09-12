"""Verify a login-scrub audit trail's compaction rollup against the trail.

Login-tombstone compact merges one durable rollup into the trail naming how
many tombstones were compacted and the prune-time span they covered, but
the rollup is never checked against the trail it summarizes: a drifted or
forged rollup silently misstates what was compacted until an operator
reconciles the rollup by hand.

This module is the verify path: the durable rollup is checked against the
trail it summarizes, so a drifted rollup is detected. Verification is pure
read: the merge keeps exactly one rollup line, so a second rollup line is
drift; the compacted count must cover the compaction runs; the claimed
prune-time span must be parseable and ordered; and because every compaction
drops every tombstone provably long gone at that moment, any tombstone
still in the trail whose prune time falls inside the rollup's claimed span
proves the rollup misstates what was compacted. A trail without a rollup
has nothing to verify, and a missing trail is reported, never created.
Nothing here touches a scheduler entry, launcher, or task XML, so a live
owner pid in any surviving repo is never disturbed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

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
from blackhole_agent.loop_login_rollup_repair import (
    LOOP_LOGIN_ROLLUP_REPAIR_DONE_WHEN,
    LOOP_LOGIN_ROLLUP_REPAIR_GOAL,
    LOOP_LOGIN_ROLLUP_REPAIR_ID,
    LOOP_LOGIN_ROLLUP_REPAIR_LEFTOVER,
)

SCHEMA_VERSION = 1
LOOP_LOGIN_VERIFY_ID = "capability.loop-login-verify"
LOOP_LOGIN_VERIFY_DONE_WHEN = (
    "A durable login-scrub audit trail's compaction rollup is verified "
    "against the trail it summarizes so a drifted rollup is detected "
    "without disturbing a live owner pid in any surviving repo."
)
LOOP_LOGIN_VERIFY_GOAL = (
    "Repair login-rollup trust: the durable compaction rollup is never "
    "checked against the trail it summarizes, so a drifted or forged rollup "
    "silently misstates what was compacted until an operator reconciles the "
    "rollup by hand."
)
LOOP_LOGIN_VERIFY_LEFTOVER = (
    "Later genesis can take login-rollup trust so a compaction rollup is "
    "verified against the trail without an operator reconciling the rollup "
    "by hand."
)
REPO_ROOT = Path(__file__).resolve().parents[2]


def _as_count(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _audit_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    record: dict[str, Any] = {}
    for key, value in pairs:
        if key in record:
            raise ValueError(f"duplicate audit field: {key}")
        record[key] = value
    return record


def _invalid_json_constant(value: str) -> Any:
    raise ValueError(f"invalid JSON constant: {value}")


def _read_login_audit_snapshot(path: Path) -> dict[str, Any]:
    """Read once, retaining evidence of anything that cannot be interpreted.

    Ignoring a broken line could hide either the rollup or a contradicting
    tombstone. Duplicate JSON keys are ambiguous evidence, too.
    """

    snapshot: dict[str, Any] = {
        "lines": [], "records": [], "malformed_lines": [], "reason": "read",
    }
    try:
        snapshot["lines"] = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        snapshot["reason"] = "no_trail"
        return snapshot
    except (OSError, UnicodeError) as error:
        snapshot.update(reason="audit_read_failed", error=str(error))
        return snapshot
    for number, line in enumerate(snapshot["lines"], start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(
                line, object_pairs_hook=_audit_json_object, parse_constant=_invalid_json_constant,
            )
        except (ValueError, RecursionError):
            snapshot["malformed_lines"].append(number)
            continue
        if not isinstance(record, dict):
            snapshot["malformed_lines"].append(number)
            continue
        snapshot["records"].append(record)
    return snapshot


def _verify_login_audit_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    verdict = verify_login_audit_rollup_records(
        snapshot["records"], malformed_count=len(snapshot["malformed_lines"]),
    )
    verdict["malformed_lines"] = snapshot["malformed_lines"]
    if snapshot["reason"] != "read":
        verdict.update(verified=False, reason=snapshot["reason"])
        if "error" in snapshot:
            verdict["error"] = snapshot["error"]
    return verdict


def verify_login_audit_rollup_records(
    records: Iterable[Any], *, malformed_count: int = 0,
) -> dict[str, Any]:
    """Check a trail's rollup lines against the records they summarize.

    Every check is derivable from the surviving trail alone: the merge
    invariant keeps exactly one rollup line, the count must cover the runs,
    the span must be parseable and ordered, and no surviving tombstone may
    carry a prune time inside the claimed span — compaction drops every
    tombstone that old, so such a survivor proves the rollup misstates what
    was compacted. The result names each drift found so an operator sees
    exactly how the rollup drifts, without reconciling the rollup by hand.
    """

    from blackhole_agent.loop_login_prune import _parse_audit_time
    from blackhole_agent.loop_login_rollup import LOGIN_AUDIT_ROLLUP_EVENT, is_login_audit_rollup
    from blackhole_agent.loop_login_tombstone import LOGIN_AUDIT_TOMBSTONE_EVENT, is_login_audit_tombstone

    drift: list[str] = []
    span_survivors: list[str] = []
    rollups: list[dict[str, Any]] = []
    tombstones: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict):
            malformed_count += 1
            continue
        if record.get("event") == LOGIN_AUDIT_ROLLUP_EVENT or record.get("rollup") is True:
            rollups.append(record)
            if not is_login_audit_rollup(record) and "rollup_identity_invalid" not in drift:
                drift.append("rollup_identity_invalid")
        elif record.get("event") == LOGIN_AUDIT_TOMBSTONE_EVENT or record.get("tombstone") is True:
            tombstones.append(record)
            if not is_login_audit_tombstone(record) and "tombstone_identity_invalid" not in drift:
                drift.append("tombstone_identity_invalid")
    if malformed_count:
        drift.append("trail_malformed")
    result: dict[str, Any] = {
        "verified": False,
        "reason": "no_rollup",
        "rollup_present": bool(rollups),
        "rollup_count": len(rollups),
        "tombstones_checked": len(tombstones),
        "drift": drift,
        "span_survivors": span_survivors,
        "rollup": rollups[0] if rollups else None,
        "malformed_count": malformed_count,
    }
    if not rollups:
        result["verified"] = not drift
        if drift:
            result["reason"] = "drift_detected"
        return result
    if len(rollups) > 1:
        drift.append("duplicate_rollup")
    rollup = rollups[0]
    count = _as_count(rollup.get("compacted_count"))
    runs = _as_count(rollup.get("compaction_runs"))
    if count is None or count < 1:
        drift.append("compacted_count_invalid")
    if runs is None or runs < 1:
        drift.append("compaction_runs_invalid")
    if count is not None and runs is not None and count < runs:
        drift.append("count_below_runs")
    oldest = str(rollup.get("oldest_pruned_at") or "")
    newest = str(rollup.get("newest_pruned_at") or "")
    oldest_dt = _parse_audit_time(oldest)
    newest_dt = _parse_audit_time(newest)
    if not oldest or oldest_dt is None:
        drift.append("oldest_pruned_at_unparseable")
    if not newest or newest_dt is None:
        drift.append("newest_pruned_at_unparseable")
    if oldest_dt is not None and newest_dt is not None and oldest_dt > newest_dt:
        drift.append("span_inverted")
    if newest_dt is not None:
        for tombstone in tombstones:
            pruned_dt = _parse_audit_time(tombstone.get("pruned_at"))
            if pruned_dt is not None and pruned_dt <= newest_dt:
                if "span_survivor" not in drift:
                    drift.append("span_survivor")
                span_survivors.append(str(tombstone.get("task_name") or ""))
    result["verified"] = not drift
    result["reason"] = "verified" if not drift else "drift_detected"
    return result


def verify_login_audit_rollup(root: Path | None = None) -> dict[str, Any]:
    """Verify a durable audit trail's rollup against the trail on disk.

    The trail is only read — a drifted rollup is reported, never rewritten —
    so verification can run against any repo's trail without disturbing a
    live owner pid in any surviving repo. A missing trail is reported as
    ``no_trail`` and never created.
    """

    from blackhole_agent.loop_login_audit import login_audit_log_path

    path = login_audit_log_path(root)
    report: dict[str, Any] = {
        "action": "rollup_verify",
        "audit_path": str(path),
        "verified": False,
        "reason": "no_trail",
        "rollup_present": False,
        "rollup_count": 0,
        "tombstones_checked": 0,
        "drift": [],
        "span_survivors": [],
        "rollup": None,
        "verified_at": utc_now_iso(),
    }
    report.update(_verify_login_audit_snapshot(_read_login_audit_snapshot(path)))
    return report


def loop_login_verify_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.loop_login_verify import "
        "builtin_loop_login_verify_proof; r=builtin_loop_login_verify_proof(); "
        "assert r['ok'] and r.get('action')=='loop_login_verify' "
        "and r.get('passed_count',0) >= 18 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_loop_login_verify_capability(*, repo_path: Path | None = None) -> Capability:
    """Register login-rollup verify on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=LOOP_LOGIN_VERIFY_ID,
        name="Continuous-loop login-rollup verify",
        description=(
            "A durable login-scrub audit trail's compaction rollup is "
            "verified against the trail it summarizes so a drifted rollup "
            "is detected without disturbing a live owner pid in any "
            "surviving repo."
        ),
        kind="python",
        entry="blackhole_agent.loop_login_verify:builtin_loop_login_verify_proof",
        proof_command=loop_login_verify_proof_command(),
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
        ),
        behavior_paths=(
            "src/blackhole_agent/loop_login_verify.py",
            "src/blackhole_agent/loop_login_rollup.py",
            "src/blackhole_agent/loop_login_compact.py",
            "src/blackhole_agent/loop_login_audit.py",
            "src/blackhole_agent/unbound.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A durable login-scrub audit trail's compaction rollup is "
            "verified against the trail it summarizes: duplicate rollup "
            "lines, invalid counts, an inverted or unparseable span, and any "
            "surviving tombstone inside the claimed span are reported as "
            "drift, the audit read surfaces the verification, verification "
            "is pure read, and a live owner pid is never disturbed."
        ),
        tags=("continuous-loop", "login", "startup", "restore", "audit", "prune", "tombstone", "compact", "rollup", "verify"),
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
            "loop_id": "login-verify-proof",
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


def builtin_loop_login_verify_proof() -> dict[str, Any]:
    """Hermetic proof: a drifted rollup is detected; live owners kept."""

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
        LOOP_LOGIN_ROLLUP_ID,
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
    from blackhole_agent.unbound import continuous_loop_lock_path, pid_is_running

    checks: dict[str, bool] = {}
    checks["denylists_self"] = LOOP_LOGIN_VERIFY_ID in LOCAL_DENYLIST
    checks["denylists_next_family"] = LOOP_LOGIN_ROLLUP_REPAIR_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(LOOP_LOGIN_VERIFY_GOAL) == (
        LOOP_LOGIN_VERIFY_ID,
    )
    checks["leftover_text_binds_next_family"] = leftover_marker_ids(
        LOOP_LOGIN_ROLLUP_REPAIR_LEFTOVER
    ) == (LOOP_LOGIN_ROLLUP_REPAIR_ID,)
    checks["next_family_goal_is_rollup_repair"] = leftover_marker_ids(
        LOOP_LOGIN_ROLLUP_REPAIR_GOAL
    ) == (LOOP_LOGIN_ROLLUP_REPAIR_ID,)
    checks["prior_family_markers_stay"] = leftover_marker_ids(LOOP_LOGIN_VERIFY_LEFTOVER) == (
        LOOP_LOGIN_VERIFY_ID,
    )
    catalog = DIVERSITY_CATALOG
    checks["catalog_names_login_verify"] = (
        len(catalog) > 254
        and catalog[254]["id"] == LOOP_LOGIN_VERIFY_ID
        and catalog[254]["goal"] == LOOP_LOGIN_VERIFY_GOAL
        and catalog[254]["done_when"] == LOOP_LOGIN_VERIFY_DONE_WHEN
        and catalog[254]["source"] == "genesis_bind_loop_login_verify"
    )
    checks["catalog_names_login_rollup_repair"] = (
        len(catalog) > 255
        and catalog[255]["id"] == LOOP_LOGIN_ROLLUP_REPAIR_ID
        and catalog[255]["goal"] == LOOP_LOGIN_ROLLUP_REPAIR_GOAL
        and catalog[255]["done_when"] == LOOP_LOGIN_ROLLUP_REPAIR_DONE_WHEN
        and catalog[255]["source"] == "genesis_bind_loop_login_rollup_repair"
    )
    checks["login_rollup_stays_ahead"] = (
        len(catalog) > 253 and catalog[253]["id"] == LOOP_LOGIN_ROLLUP_ID
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

    dead_pid = 1_000_291
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

    with tempfile.TemporaryDirectory(prefix="loop-login-verify-sweep-") as tmp:
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
        verified = verify_login_audit_rollup(orphan_audit_root)
        trail = read_login_scrub_audit(orphan_audit_root)
        surfaced = trail.get("tombstone_rollup_verification") or {}
        result = dispatch_login_startup(surviving, controller_starter=starter)
        checks["compacted_trail_rollup_verifies_against_trail"] = (
            swept.get("action") == "sweep"
            and swept.get("swept") == [LOGIN_TASK_NAME]
            and verified.get("action") == "rollup_verify"
            and verified.get("verified") is True
            and verified.get("reason") == "verified"
            and verified.get("rollup_present") is True
            and verified.get("rollup_count") == 1
            and verified.get("tombstones_checked") == 1
            and verified.get("drift") == []
            and (verified.get("rollup") or {}).get("compacted_count") == 2
            and len(starts) == starts_before
        )
        checks["audit_read_surfaces_rollup_verification"] = (
            surfaced.get("verified") is True
            and surfaced.get("reason") == "verified"
            and surfaced.get("drift") == []
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
        drifted_lines = []
        for line in raw_before.decode("utf-8").splitlines():
            record = json.loads(line)
            if is_login_audit_rollup(record):
                record["newest_pruned_at"] = _aged_iso(0)
                record["compacted_count"] = 99
            drifted_lines.append(json.dumps(record, sort_keys=True))
        audit_path.write_text("\n".join(drifted_lines) + "\n", encoding="utf-8")
        drifted = verify_login_audit_rollup(orphan_audit_root)
        checks["forged_span_is_detected"] = (
            drifted.get("verified") is False
            and drifted.get("reason") == "drift_detected"
            and "span_survivor" in drifted.get("drift")
            and "recent-task" in drifted.get("span_survivors")
            and (trail.get("entries") or [])
        )
        raw_drifted = audit_path.read_bytes()
        again = verify_login_audit_rollup(orphan_audit_root)
        checks["verify_is_pure_read"] = (
            audit_path.read_bytes() == raw_drifted
            and again.get("verified") is False
            and surviving_state.read_bytes() == before
            and len(starts) == starts_before
        )

    with tempfile.TemporaryDirectory(prefix="loop-login-verify-drift-") as tmp:
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
        merged = verify_login_audit_rollup(root)
        checks["merged_rollup_verifies"] = (
            merged.get("verified") is True
            and merged.get("reason") == "verified"
            and (merged.get("rollup") or {}).get("compacted_count") == 2
            and (merged.get("rollup") or {}).get("compaction_runs") == 2
        )
        merged_rollup = dict(merged.get("rollup") or {})
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(merged_rollup, sort_keys=True) + "\n")
        duplicate = verify_login_audit_rollup(root)
        checks["duplicate_rollup_line_is_drift"] = (
            duplicate.get("verified") is False
            and duplicate.get("rollup_count") == 2
            and "duplicate_rollup" in duplicate.get("drift")
        )
        path.write_text(
            json.dumps(tombstone("kept-task", pruned_days=30), sort_keys=True) + "\n",
            encoding="utf-8",
        )

        def with_rollup(**overrides: Any) -> dict[str, Any]:
            rollup = {
                "schema_version": SCHEMA_VERSION,
                "event": LOGIN_AUDIT_ROLLUP_EVENT,
                "rollup": True,
                "compacted_count": 2,
                "compaction_runs": 2,
                "oldest_pruned_at": _aged_iso(400),
                "newest_pruned_at": _aged_iso(380),
                "last_compacted_at": _aged_iso(15),
            }
            rollup.update(overrides)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(rollup, sort_keys=True) + "\n")
            outcome = verify_login_audit_rollup(root)
            path.write_text(
                json.dumps(tombstone("kept-task", pruned_days=30), sort_keys=True) + "\n",
                encoding="utf-8",
            )
            return outcome

        inverted = with_rollup(oldest_pruned_at=_aged_iso(300), newest_pruned_at=_aged_iso(320))
        checks["inverted_span_is_drift"] = (
            inverted.get("verified") is False and "span_inverted" in inverted.get("drift")
        )
        zeroed = with_rollup(compacted_count=0)
        checks["invalid_count_is_drift"] = (
            zeroed.get("verified") is False and "compacted_count_invalid" in zeroed.get("drift")
        )
        undercounted = with_rollup(compacted_count=1, compaction_runs=3)
        checks["count_below_runs_is_drift"] = (
            undercounted.get("verified") is False and "count_below_runs" in undercounted.get("drift")
        )
        undated = with_rollup(newest_pruned_at="not-a-timestamp")
        checks["unparseable_span_is_drift"] = (
            undated.get("verified") is False and "newest_pruned_at_unparseable" in undated.get("drift")
        )
        honest = with_rollup()
        checks["recent_tombstone_outside_span_is_not_drift"] = (
            honest.get("verified") is True
            and honest.get("reason") == "verified"
            and honest.get("tombstones_checked") == 1
        )
        missing = verify_login_audit_rollup(root / "no-such-dir")
        path.write_text(
            json.dumps(tombstone("kept-task", pruned_days=30), sort_keys=True) + "\n",
            encoding="utf-8",
        )
        no_rollup = verify_login_audit_rollup(root)
        checks["trail_without_rollup_has_nothing_to_verify"] = (
            missing.get("reason") == "no_trail"
            and not (root / "no-such-dir").exists()
            and no_rollup.get("verified") is True
            and no_rollup.get("reason") == "no_rollup"
            and no_rollup.get("rollup_present") is False
        )

    checks["next_family_is_not_handshake"] = (
        behavior_family(LOOP_LOGIN_ROLLUP_REPAIR_GOAL) != "network/handshake-digest-demo"
        and LOOP_LOGIN_ROLLUP_REPAIR_DONE_WHEN != ""
    )
    checks["contract_is_outcome_level"] = (
        "capability_exists:" not in LOOP_LOGIN_VERIFY_DONE_WHEN
        and "capability_proved:" not in LOOP_LOGIN_VERIFY_DONE_WHEN
    )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_loop_login_verify_capability()
    return {
        "ok": ok,
        "action": "loop_login_verify",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": LOOP_LOGIN_VERIFY_GOAL,
        "done_when": LOOP_LOGIN_VERIFY_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
