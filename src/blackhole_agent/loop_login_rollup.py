"""Leave a durable rollup when long-gone login-audit tombstones are compacted.

Login-tombstone compact drops tombstones whose named records are long gone
so the durable trail stays small, but a compacted tombstone used to vanish
without a trace: an operator reconciling a compacted trail could not tell a
compacted tombstone from a record that was never written.

This module is the rollup path: every compaction merges one durable rollup
entry into the trail naming how many tombstones were compacted and the span
they covered — the total compacted count, the number of compaction runs, and
the oldest and newest prune times covered. The rollup is merged in place, so
a trail that compacts for years still holds exactly one rollup line and the
trail stays small. The merge rides the compact's atomic temp-file-and-
replace, touches only the audit trail, and never touches a scheduler entry,
launcher, or task XML, so a live owner pid in any surviving repo is never
disturbed.
"""

from __future__ import annotations

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
from blackhole_agent.loop_login_verify import (
    LOOP_LOGIN_VERIFY_DONE_WHEN,
    LOOP_LOGIN_VERIFY_GOAL,
    LOOP_LOGIN_VERIFY_ID,
    LOOP_LOGIN_VERIFY_LEFTOVER,
)

SCHEMA_VERSION = 1
LOOP_LOGIN_ROLLUP_ID = "capability.loop-login-rollup"
LOOP_LOGIN_ROLLUP_DONE_WHEN = (
    "A compacted login-scrub audit trail leaves a durable rollup naming how "
    "many tombstones were compacted and the span they covered so the trail "
    "stays reconcilable without disturbing a live owner pid in any "
    "surviving repo."
)
LOOP_LOGIN_ROLLUP_GOAL = (
    "Repair login-compact silence: every compaction erases aged tombstones "
    "without a trace, so an operator reconciling a compacted trail cannot "
    "tell a compacted tombstone from a record that was never written."
)
LOOP_LOGIN_ROLLUP_LEFTOVER = (
    "Later genesis can take login-compact silence so a compacted trail "
    "leaves a durable rollup without an operator reconstructing compacted "
    "tombstones by hand."
)
LOGIN_AUDIT_ROLLUP_EVENT = "login_audit_tombstones_compacted"
REPO_ROOT = Path(__file__).resolve().parents[2]


def is_login_audit_rollup(record: dict[str, Any]) -> bool:
    """True when an audit-trail record is a compaction rollup."""

    return (
        isinstance(record, dict)
        and record.get("event") == LOGIN_AUDIT_ROLLUP_EVENT
        and record.get("rollup") is True
    )


def _span_edge(current: str, candidate: str, *, pick_min: bool) -> str:
    """Pick the min/max of two ISO prune times, preferring the provable one."""

    from blackhole_agent.loop_login_prune import _parse_audit_time

    current_dt = _parse_audit_time(current)
    candidate_dt = _parse_audit_time(candidate)
    if current_dt is None:
        return candidate
    if candidate_dt is None:
        return current
    if pick_min:
        return current if current_dt <= candidate_dt else candidate
    return current if current_dt >= candidate_dt else candidate


def login_audit_rollup_batch(
    compacted: list[dict[str, Any]],
    *,
    compacted_at: str,
) -> dict[str, Any]:
    """Build the per-compaction batch: how many tombstones and their span."""

    pruned_ats = sorted(str(entry.get("pruned_at") or "") for entry in compacted)
    return {
        "compacted_count": len(compacted),
        "oldest_pruned_at": pruned_ats[0] if pruned_ats else "",
        "newest_pruned_at": pruned_ats[-1] if pruned_ats else "",
        "compacted_at": compacted_at,
    }


def merge_login_audit_rollup(
    existing: dict[str, Any] | None,
    batch: dict[str, Any],
) -> dict[str, Any]:
    """Merge one compaction batch into the trail's single durable rollup.

    The merged rollup accumulates the total compacted count and compaction
    runs and widens the covered span, so a trail that compacts for years
    keeps exactly one rollup line: an operator reconciling the compacted
    trail can tell how much was compacted, and over which prune-time span,
    without reconstructing compacted tombstones by hand.
    """

    prior = existing if isinstance(existing, dict) else {}
    count = int(prior.get("compacted_count") or 0) + int(batch.get("compacted_count") or 0)
    runs = int(prior.get("compaction_runs") or 0) + int(batch.get("compaction_runs") or 1)
    oldest = _span_edge(
        str(prior.get("oldest_pruned_at") or ""),
        str(batch.get("oldest_pruned_at") or ""),
        pick_min=True,
    )
    newest = _span_edge(
        str(prior.get("newest_pruned_at") or ""),
        str(batch.get("newest_pruned_at") or ""),
        pick_min=False,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "event": LOGIN_AUDIT_ROLLUP_EVENT,
        "rollup": True,
        "compacted_count": count,
        "compaction_runs": runs,
        "oldest_pruned_at": oldest,
        "newest_pruned_at": newest,
        "last_compacted_at": str(batch.get("compacted_at") or batch.get("last_compacted_at") or ""),
    }


def loop_login_rollup_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.loop_login_rollup import "
        "builtin_loop_login_rollup_proof; r=builtin_loop_login_rollup_proof(); "
        "assert r['ok'] and r.get('action')=='loop_login_rollup' "
        "and r.get('passed_count',0) >= 18 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_loop_login_rollup_capability(*, repo_path: Path | None = None) -> Capability:
    """Register login-tombstone rollup on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=LOOP_LOGIN_ROLLUP_ID,
        name="Continuous-loop login-tombstone rollup",
        description=(
            "A compacted login-scrub audit trail leaves a durable rollup "
            "naming how many tombstones were compacted and the span they "
            "covered so the trail stays reconcilable without disturbing a "
            "live owner pid in any surviving repo."
        ),
        kind="python",
        entry="blackhole_agent.loop_login_rollup:builtin_loop_login_rollup_proof",
        proof_command=loop_login_rollup_proof_command(),
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
        ),
        behavior_paths=(
            "src/blackhole_agent/loop_login_rollup.py",
            "src/blackhole_agent/loop_login_compact.py",
            "src/blackhole_agent/loop_login_audit.py",
            "src/blackhole_agent/loop_login_tombstone.py",
            "src/blackhole_agent/loop_login_prune.py",
            "src/blackhole_agent/unbound.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A compacted login-scrub audit trail stays reconcilable: every "
            "compaction merges one durable rollup naming how many tombstones "
            "were compacted and the prune-time span they covered, the trail "
            "keeps exactly one rollup line so it stays small, the audit read "
            "surfaces the rollup, and a live owner pid is never disturbed."
        ),
        tags=("continuous-loop", "login", "startup", "restore", "audit", "prune", "tombstone", "compact", "rollup"),
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
            "loop_id": "login-rollup-proof",
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


def builtin_loop_login_rollup_proof() -> dict[str, Any]:
    """Hermetic proof: compaction leaves a durable merged rollup; live owners kept."""

    import json
    import os
    import tempfile

    from blackhole_agent.evolution_quality import behavior_family
    from blackhole_agent.kernel_genesis_diversify import DIVERSITY_CATALOG
    from blackhole_agent.kernel_leftover import leftover_marker_ids
    from blackhole_agent.loop_login_audit import (
        login_audit_log_path,
        read_login_scrub_audit,
        record_login_task_scrub,
    )
    from blackhole_agent.loop_login_compact import (
        DEFAULT_COMPACT_RETENTION_DAYS,
        LOOP_LOGIN_COMPACT_ID,
        LOOP_LOGIN_COMPACT_LEFTOVER,
        compact_login_audit_tombstones,
    )
    from blackhole_agent.loop_login_prune import (
        DEFAULT_PRUNE_RETENTION_DAYS,
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
    from blackhole_agent.loop_login_tombstone import LOGIN_AUDIT_TOMBSTONE_EVENT
    from blackhole_agent.unbound import continuous_loop_lock_path, pid_is_running

    checks: dict[str, bool] = {}
    checks["denylists_self"] = LOOP_LOGIN_ROLLUP_ID in LOCAL_DENYLIST
    checks["denylists_next_family"] = LOOP_LOGIN_VERIFY_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(LOOP_LOGIN_ROLLUP_GOAL) == (
        LOOP_LOGIN_ROLLUP_ID,
    )
    checks["leftover_text_binds_next_family"] = leftover_marker_ids(
        LOOP_LOGIN_VERIFY_LEFTOVER
    ) == (LOOP_LOGIN_VERIFY_ID,)
    checks["next_family_goal_is_login_verify"] = leftover_marker_ids(
        LOOP_LOGIN_VERIFY_GOAL
    ) == (LOOP_LOGIN_VERIFY_ID,)
    checks["prior_family_markers_stay"] = leftover_marker_ids(LOOP_LOGIN_COMPACT_LEFTOVER) == (
        LOOP_LOGIN_COMPACT_ID,
    )
    catalog = DIVERSITY_CATALOG
    checks["catalog_names_login_rollup"] = (
        len(catalog) > 253
        and catalog[253]["id"] == LOOP_LOGIN_ROLLUP_ID
        and catalog[253]["goal"] == LOOP_LOGIN_ROLLUP_GOAL
        and catalog[253]["done_when"] == LOOP_LOGIN_ROLLUP_DONE_WHEN
        and catalog[253]["source"] == "genesis_bind_loop_login_rollup"
    )
    checks["catalog_names_login_verify"] = (
        len(catalog) > 254
        and catalog[254]["id"] == LOOP_LOGIN_VERIFY_ID
        and catalog[254]["goal"] == LOOP_LOGIN_VERIFY_GOAL
        and catalog[254]["done_when"] == LOOP_LOGIN_VERIFY_DONE_WHEN
        and catalog[254]["source"] == "genesis_bind_loop_login_verify"
    )
    checks["login_compact_stays_ahead"] = (
        len(catalog) > 252 and catalog[252]["id"] == LOOP_LOGIN_COMPACT_ID
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

    dead_pid = 1_000_271
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

    with tempfile.TemporaryDirectory(prefix="loop-login-rollup-sweep-") as tmp:
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
        result = dispatch_login_startup(surviving, controller_starter=starter)
        trail = read_login_scrub_audit(orphan_audit_root)
        entries = trail.get("entries") or []
        rollups = [entry for entry in entries if is_login_audit_rollup(entry)]
        rollup = rollups[0] if rollups else {}
        names = [str(entry.get("task_name") or "") for entry in entries]
        checks["sweep_compaction_leaves_durable_rollup"] = (
            swept.get("action") == "sweep"
            and swept.get("swept") == [LOGIN_TASK_NAME]
            and swept.get("audit_recorded") == 1
            and trail.get("entry_count") == 3
            and trail.get("tombstone_count") == 1
            and len(rollups) == 1
            and rollup.get("event") == LOGIN_AUDIT_ROLLUP_EVENT
            and rollup.get("rollup") is True
            and rollup.get("compacted_count") == 2
            and rollup.get("compaction_runs") == 1
            and "ancient-a" not in names
            and "ancient-b" not in names
            and "recent-task" in names
            and LOGIN_TASK_NAME in names
            and len(starts) == starts_before
        )
        checks["rollup_names_count_and_span"] = (
            bool(rollup.get("oldest_pruned_at"))
            and bool(rollup.get("newest_pruned_at"))
            and rollup.get("oldest_pruned_at") < rollup.get("newest_pruned_at")
            and bool(rollup.get("last_compacted_at"))
            and rollup.get("schema_version") == SCHEMA_VERSION
            and (trail.get("tombstone_rollup") or {}).get("compacted_count") == 2
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

    with tempfile.TemporaryDirectory(prefix="loop-login-rollup-merge-") as tmp:
        root = Path(tmp)
        path = login_audit_log_path(root)
        path.write_text(
            json.dumps(tombstone("first-old", pruned_days=DEFAULT_COMPACT_RETENTION_DAYS + 50), sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        first = compact_login_audit_tombstones(root)
        first_trail = read_login_scrub_audit(root)
        first_rollup = first_trail.get("tombstone_rollup") or {}
        with path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(tombstone("second-old", pruned_days=DEFAULT_COMPACT_RETENTION_DAYS + 5), sort_keys=True)
                + "\n"
            )
        second = compact_login_audit_tombstones(root)
        second_trail = read_login_scrub_audit(root)
        second_entries = second_trail.get("entries") or []
        second_rollups = [entry for entry in second_entries if is_login_audit_rollup(entry)]
        merged = second_rollups[0] if second_rollups else {}
        checks["later_compactions_merge_one_rollup_line"] = (
            first.get("compacted") is True
            and first.get("compacted_count") == 1
            and first_rollup.get("compacted_count") == 1
            and first_rollup.get("compaction_runs") == 1
            and second.get("compacted") is True
            and second.get("compacted_count") == 1
            and len(second_rollups) == 1
            and merged.get("compacted_count") == 2
            and merged.get("compaction_runs") == 2
            and merged.get("oldest_pruned_at") == first_rollup.get("oldest_pruned_at")
            and merged.get("newest_pruned_at") > first_rollup.get("newest_pruned_at")
            and second_trail.get("entry_count") == 1
        )
        raw_before = path.read_bytes()
        again = compact_login_audit_tombstones(root)
        checks["rollup_trail_stays_byte_identical_without_compaction"] = (
            again.get("compacted") is False
            and again.get("reason") == "nothing_compactable"
            and path.read_bytes() == raw_before
            and len([e for e in (read_login_scrub_audit(root).get("entries") or []) if is_login_audit_rollup(e)]) == 1
        )
        pruned = prune_login_scrub_audit(root)
        checks["prune_never_drops_rollup"] = (
            pruned.get("pruned") is False
            and pruned.get("reason") == "nothing_stale"
            and path.read_bytes() == raw_before
            and is_login_audit_rollup((read_login_scrub_audit(root).get("entries") or [{}])[0])
        )

    with tempfile.TemporaryDirectory(prefix="loop-login-rollup-append-") as tmp:
        root = Path(tmp)
        task = {"name": LOGIN_TASK_NAME, "repo_path": str(root / "repo")}
        report = {
            "reason": "registration_gone",
            "scrubbed_paths": [str(root / "a.py"), str(root / "b.xml")],
            "kept_foreign": [],
        }
        login_audit_log_path(root).write_text(
            json.dumps(tombstone("ancient-task", pruned_days=DEFAULT_COMPACT_RETENTION_DAYS + 5), sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        starts_before = len(starts)
        recorded = record_login_task_scrub(task, report, audit_root=root)
        trail = read_login_scrub_audit(root)
        entries = trail.get("entries") or []
        rollups = [entry for entry in entries if is_login_audit_rollup(entry)]
        checks["recorded_scrub_compaction_leaves_rollup"] = (
            recorded.get("recorded") is True
            and recorded.get("audit_tombstones_compacted") is True
            and recorded.get("audit_tombstones_compacted_count") == 1
            and trail.get("entry_count") == 2
            and trail.get("tombstone_count") == 0
            and len(rollups) == 1
            and rollups[0].get("compacted_count") == 1
            and len(starts) == starts_before
        )

    checks["next_family_is_not_handshake"] = (
        behavior_family(LOOP_LOGIN_VERIFY_GOAL) != "network/handshake-digest-demo"
        and LOOP_LOGIN_VERIFY_DONE_WHEN != ""
    )
    checks["contract_is_outcome_level"] = (
        "capability_exists:" not in LOOP_LOGIN_ROLLUP_DONE_WHEN
        and "capability_proved:" not in LOOP_LOGIN_ROLLUP_DONE_WHEN
    )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_loop_login_rollup_capability()
    return {
        "ok": ok,
        "action": "loop_login_rollup",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": LOOP_LOGIN_ROLLUP_GOAL,
        "done_when": LOOP_LOGIN_ROLLUP_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
