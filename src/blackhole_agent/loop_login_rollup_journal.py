"""Journal each login-rollup repair so the drifted claims stay auditable.

Login-rollup repair corrects a drifted rollup against the trail it
summarizes, but the repair overwrites the drifted claims: once the
corrected rollup replaces the drifted line, an operator auditing a
repaired trail cannot tell what the drifted rollup claimed without
reconstructing the drifted claims by hand.

This module is the journal path: every repair that rewrites a drifted
rollup appends one durable journal entry to a separate journal log beside
the audit trail, naming the drift that was found, the corrections that
were applied, the drifted rollup's claims, and the corrected rollup that
replaced them. The journal lives outside the audit trail so the trail
stays small, an intact or unrepairable trail journals nothing, and only
the audit root's own files are touched, so a live owner pid in any
surviving repo is never disturbed.
"""

from __future__ import annotations

import json
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
from blackhole_agent.loop_login_journal_prune import (
    LOOP_LOGIN_JOURNAL_PRUNE_DONE_WHEN,
    LOOP_LOGIN_JOURNAL_PRUNE_GOAL,
    LOOP_LOGIN_JOURNAL_PRUNE_ID,
    LOOP_LOGIN_JOURNAL_PRUNE_LEFTOVER,
)

SCHEMA_VERSION = 1
LOOP_LOGIN_ROLLUP_JOURNAL_ID = "capability.loop-login-rollup-journal"
LOOP_LOGIN_ROLLUP_JOURNAL_DONE_WHEN = (
    "A repaired login-scrub audit trail rollup leaves a durable record of "
    "what the drifted rollup claimed and what was corrected so the repair "
    "stays auditable without disturbing a live owner pid in any surviving "
    "repo."
)
LOOP_LOGIN_ROLLUP_JOURNAL_GOAL = (
    "Repair login-rollup repair silence: every repair of a drifted rollup "
    "overwrites the drifted claims without a durable record, so an operator "
    "auditing a repaired trail cannot tell what the drifted rollup claimed "
    "without reconstructing the drifted claims by hand."
)
LOOP_LOGIN_ROLLUP_JOURNAL_LEFTOVER = (
    "Later genesis can take login-rollup repair silence so a repaired "
    "rollup leaves a durable record of the drifted claims without an "
    "operator reconstructing the drifted claims by hand."
)
LOGIN_ROLLUP_REPAIR_JOURNAL_EVENT = "login_audit_rollup_repaired"
LOGIN_ROLLUP_REPAIR_JOURNAL_NAME = "login-rollup-repair-journal.jsonl"
REPO_ROOT = Path(__file__).resolve().parents[2]


def login_rollup_repair_journal_path(root: Path | None = None) -> Path:
    """Durable repair-journal location beside the repo's audit trail."""

    from blackhole_agent.loop_login_audit import login_audit_log_path

    return login_audit_log_path(root).parent / LOGIN_ROLLUP_REPAIR_JOURNAL_NAME


def is_login_rollup_repair_journal_entry(record: dict[str, Any]) -> bool:
    """True when a journal record is a rollup-repair entry."""

    return (
        isinstance(record, dict)
        and record.get("event") == LOGIN_ROLLUP_REPAIR_JOURNAL_EVENT
        and record.get("journal") is True
    )


def record_login_rollup_repair(
    root: Path | None,
    *,
    drift: list[str],
    corrections: list[str],
    prior_rollup: dict[str, Any],
    corrected_rollup: dict[str, Any],
    repaired_at: str,
) -> dict[str, Any]:
    """Append one durable journal entry for a repair of a drifted rollup.

    The entry names the drift that was found, the corrections applied, the
    drifted rollup's claims, and the corrected rollup, so an operator
    auditing a repaired trail can see what the drifted rollup claimed
    without reconstructing the drifted claims by hand. Only the journal
    log is appended; nothing else in any repo is touched, so a live owner
    pid in any surviving repo is never disturbed.
    """

    path = login_rollup_repair_journal_path(root)
    entry = {
        "schema_version": SCHEMA_VERSION,
        "event": LOGIN_ROLLUP_REPAIR_JOURNAL_EVENT,
        "journal": True,
        "drift": [str(code) for code in drift],
        "corrections": [str(correction) for correction in corrections],
        "prior_rollup": dict(prior_rollup),
        "corrected_rollup": dict(corrected_rollup),
        "repaired_at": str(repaired_at),
        "journaled_at": utc_now_iso(),
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")
    except OSError as error:
        return {
            "action": "rollup_repair_journal",
            "journaled": False,
            "reason": "journal_write_failed",
            "journal_path": str(path),
            "error": str(error),
        }
    return {
        "action": "rollup_repair_journal",
        "journaled": True,
        "reason": "repaired",
        "journal_path": str(path),
        "entry": entry,
    }


def read_login_rollup_repair_journal(root: Path | None = None) -> dict[str, Any]:
    """Read the durable repair journal so an operator can audit repairs.

    Malformed lines are counted and skipped rather than failing the read,
    so a partially written journal still shows every intact repair entry.
    A missing journal is reported, never created.
    """

    path = login_rollup_repair_journal_path(root)
    entries: list[dict[str, Any]] = []
    malformed = 0
    if path.is_file():
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            lines = []
        for line in lines:
            text = line.strip()
            if not text:
                continue
            try:
                record = json.loads(text)
            except json.JSONDecodeError:
                malformed += 1
                continue
            if isinstance(record, dict) and is_login_rollup_repair_journal_entry(record):
                entries.append(record)
            else:
                malformed += 1
    return {
        "action": "rollup_repair_journal_read",
        "journal_path": str(path),
        "entries": entries,
        "entry_count": len(entries),
        "malformed_count": malformed,
    }


def loop_login_rollup_journal_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.loop_login_rollup_journal import "
        "builtin_loop_login_rollup_journal_proof; r=builtin_loop_login_rollup_journal_proof(); "
        "assert r['ok'] and r.get('action')=='loop_login_rollup_journal' "
        "and r.get('passed_count',0) >= 18 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_loop_login_rollup_journal_capability(*, repo_path: Path | None = None) -> Capability:
    """Register login-rollup repair journal on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=LOOP_LOGIN_ROLLUP_JOURNAL_ID,
        name="Continuous-loop login-rollup repair journal",
        description=(
            "A repaired login-scrub audit trail rollup leaves a durable "
            "record of what the drifted rollup claimed and what was "
            "corrected so the repair stays auditable without disturbing a "
            "live owner pid in any surviving repo."
        ),
        kind="python",
        entry="blackhole_agent.loop_login_rollup_journal:builtin_loop_login_rollup_journal_proof",
        proof_command=loop_login_rollup_journal_proof_command(),
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
            "capability.loop-login-rollup-repair",
        ),
        behavior_paths=(
            "src/blackhole_agent/loop_login_rollup_journal.py",
            "src/blackhole_agent/loop_login_rollup_repair.py",
            "src/blackhole_agent/loop_login_verify.py",
            "src/blackhole_agent/loop_login_rollup.py",
            "src/blackhole_agent/unbound.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "Every repair of a drifted login-scrub audit trail rollup "
            "appends one durable journal entry beside the trail naming the "
            "drift found, the corrections applied, the drifted rollup's "
            "claims, and the corrected rollup, so a repaired trail stays "
            "auditable, intact and unrepairable trails journal nothing, "
            "and a live owner pid is never disturbed."
        ),
        tags=("continuous-loop", "login", "startup", "restore", "audit", "rollup", "verify", "repair", "journal"),
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
            "loop_id": "login-rollup-journal-proof",
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


def builtin_loop_login_rollup_journal_proof() -> dict[str, Any]:
    """Hermetic proof: every repair journals the drifted claims; live owners kept."""

    import os
    import tempfile

    from blackhole_agent.evolution_quality import behavior_family
    from blackhole_agent.kernel_genesis_diversify import DIVERSITY_CATALOG
    from blackhole_agent.kernel_leftover import leftover_marker_ids
    from blackhole_agent.loop_login_audit import login_audit_log_path
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
        LOOP_LOGIN_ROLLUP_REPAIR_ID,
        repair_login_audit_rollup,
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
    from blackhole_agent.loop_login_verify import verify_login_audit_rollup
    from blackhole_agent.unbound import continuous_loop_lock_path, pid_is_running

    checks: dict[str, bool] = {}
    checks["denylists_self"] = LOOP_LOGIN_ROLLUP_JOURNAL_ID in LOCAL_DENYLIST
    checks["denylists_next_family"] = LOOP_LOGIN_JOURNAL_PRUNE_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(LOOP_LOGIN_ROLLUP_JOURNAL_GOAL) == (
        LOOP_LOGIN_ROLLUP_JOURNAL_ID,
    )
    checks["leftover_text_binds_next_family"] = leftover_marker_ids(
        LOOP_LOGIN_JOURNAL_PRUNE_LEFTOVER
    ) == (LOOP_LOGIN_JOURNAL_PRUNE_ID,)
    checks["next_family_goal_is_journal_prune"] = leftover_marker_ids(
        LOOP_LOGIN_JOURNAL_PRUNE_GOAL
    ) == (LOOP_LOGIN_JOURNAL_PRUNE_ID,)
    checks["prior_family_markers_stay"] = leftover_marker_ids(LOOP_LOGIN_ROLLUP_JOURNAL_LEFTOVER) == (
        LOOP_LOGIN_ROLLUP_JOURNAL_ID,
    )
    catalog = DIVERSITY_CATALOG
    checks["catalog_names_login_rollup_journal"] = (
        len(catalog) > 256
        and catalog[256]["id"] == LOOP_LOGIN_ROLLUP_JOURNAL_ID
        and catalog[256]["goal"] == LOOP_LOGIN_ROLLUP_JOURNAL_GOAL
        and catalog[256]["done_when"] == LOOP_LOGIN_ROLLUP_JOURNAL_DONE_WHEN
        and catalog[256]["source"] == "genesis_bind_loop_login_rollup_journal"
    )
    checks["catalog_names_login_journal_prune"] = (
        len(catalog) > 257
        and catalog[257]["id"] == LOOP_LOGIN_JOURNAL_PRUNE_ID
        and catalog[257]["goal"] == LOOP_LOGIN_JOURNAL_PRUNE_GOAL
        and catalog[257]["done_when"] == LOOP_LOGIN_JOURNAL_PRUNE_DONE_WHEN
        and catalog[257]["source"] == "genesis_bind_loop_login_journal_prune"
    )
    checks["login_rollup_repair_stays_ahead"] = (
        len(catalog) > 255 and catalog[255]["id"] == LOOP_LOGIN_ROLLUP_REPAIR_ID
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

    dead_pid = 1_000_331
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

    def drift_rollup(audit_path: Path, *, count: int) -> dict[str, Any]:
        drifted_lines = []
        prior: dict[str, Any] = {}
        for line in audit_path.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            if is_login_audit_rollup(record):
                prior = dict(record)
                record["newest_pruned_at"] = _aged_iso(0)
                record["compacted_count"] = count
            drifted_lines.append(json.dumps(record, sort_keys=True))
        audit_path.write_text("\n".join(drifted_lines) + "\n", encoding="utf-8")
        return prior

    with tempfile.TemporaryDirectory(prefix="loop-login-rollup-journal-sweep-") as tmp:
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
            + json.dumps(tombstone("recent-task", pruned_days=90), sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        login_startup_registration_path(orphan).unlink()
        before = surviving_state.read_bytes()
        starts_before = len(starts)
        swept = sweep_login_tasks_missing_registration(scheduler=scheduler)
        intact = repair_login_audit_rollup(orphan_audit_root)
        checks["intact_repair_journals_nothing"] = (
            swept.get("action") == "sweep"
            and intact.get("repaired") is False
            and intact.get("reason") == "already_verified"
            and intact.get("repair_journaled") is False
            and not login_rollup_repair_journal_path(orphan_audit_root).exists()
        )
        forged_count = 99
        drift_rollup(audit_path, count=forged_count)
        drifted = verify_login_audit_rollup(orphan_audit_root)
        repaired = repair_login_audit_rollup(orphan_audit_root)
        journal = read_login_rollup_repair_journal(orphan_audit_root)
        entries = journal.get("entries") or []
        entry = entries[0] if entries else {}
        prior_claims = entry.get("prior_rollup") or {}
        corrected_claims = entry.get("corrected_rollup") or {}
        checks["repair_leaves_durable_journal_of_drifted_claims"] = (
            drifted.get("verified") is False
            and repaired.get("repaired") is True
            and repaired.get("repair_journaled") is True
            and journal.get("entry_count") == 1
            and journal.get("malformed_count") == 0
            and entry.get("event") == LOGIN_ROLLUP_REPAIR_JOURNAL_EVENT
            and entry.get("journal") is True
            and "span_survivor" in (entry.get("drift") or [])
            and "span_clamped_below_survivor" in (entry.get("corrections") or [])
            and prior_claims.get("compacted_count") == forged_count
            and prior_claims.get("newest_pruned_at") >= _aged_iso(1)
            and prior_claims.get("newest_pruned_at") != corrected_claims.get("newest_pruned_at")
            and corrected_claims.get("compacted_count") == (repaired.get("rollup") or {}).get("compacted_count")
            and bool(entry.get("repaired_at"))
            and bool(entry.get("journaled_at"))
            and verify_login_audit_rollup(orphan_audit_root).get("verified") is True
        )
        result = dispatch_login_startup(surviving, controller_starter=starter)
        checks["live_owner_not_disturbed"] = (
            LOGIN_TASK_NAME in swept.get("kept")
            and surviving_registration is not None
            and load_login_startup_registration(surviving) == surviving_registration
            and surviving_launcher.is_file()
            and surviving_xml.is_file()
            and not login_audit_log_path(surviving_audit_root).exists()
            and not login_rollup_repair_journal_path(surviving_audit_root).exists()
            and result.get("started") is False
            and result.get("restore_reason") == "live_owner"
            and result.get("scheduled") is True
            and surviving_state.read_bytes() == before
            and len(starts) == starts_before
            and pid_is_running(live_pid)
        )

    with tempfile.TemporaryDirectory(prefix="loop-login-rollup-journal-history-") as tmp:
        root = Path(tmp)
        path = login_audit_log_path(root)
        path.write_text(
            json.dumps(tombstone("first-old", pruned_days=DEFAULT_COMPACT_RETENTION_DAYS + 50), sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        compact_login_audit_tombstones(root)
        drift_rollup(path, count=0)
        first_repair = repair_login_audit_rollup(root)
        drift_rollup(path, count=0)
        second_repair = repair_login_audit_rollup(root)
        journal = read_login_rollup_repair_journal(root)
        entries = journal.get("entries") or []
        checks["later_repairs_append_journal_history"] = (
            first_repair.get("repaired") is True
            and second_repair.get("repaired") is True
            and journal.get("entry_count") == 2
            and (entries[0].get("prior_rollup") or {}).get("compacted_count") == 0
            and (entries[1].get("prior_rollup") or {}).get("compacted_count") == 0
            and (entries[0].get("corrected_rollup") or {}).get("compacted_count")
            == (entries[0].get("corrected_rollup") or {}).get("compaction_runs")
            and "compacted_count_invalid" in (entries[0].get("drift") or [])
            and "compacted_count_raised_to_runs" in (entries[1].get("corrections") or [])
            and verify_login_audit_rollup(root).get("verified") is True
        )
        raw_journal = login_rollup_repair_journal_path(root).read_bytes()
        idle = repair_login_audit_rollup(root)
        checks["verified_trail_appends_no_journal_entry"] = (
            idle.get("repaired") is False
            and idle.get("repair_journaled") is False
            and login_rollup_repair_journal_path(root).read_bytes() == raw_journal
            and read_login_rollup_repair_journal(root).get("entry_count") == 2
        )

    with tempfile.TemporaryDirectory(prefix="loop-login-rollup-journal-malformed-") as tmp:
        root = Path(tmp)
        path = login_rollup_repair_journal_path(root)
        path.parent.mkdir(parents=True, exist_ok=True)
        recorded = record_login_rollup_repair(
            root,
            drift=["span_survivor"],
            corrections=["span_clamped_below_survivor"],
            prior_rollup={"compacted_count": 99},
            corrected_rollup={"compacted_count": 1},
            repaired_at="2026-09-12T00:00:00Z",
        )
        with path.open("a", encoding="utf-8") as handle:
            handle.write("not json at all\n")
            handle.write('["a", "list"]\n')
        journal = read_login_rollup_repair_journal(root)
        checks["journal_read_tolerates_malformed"] = (
            recorded.get("journaled") is True
            and journal.get("entry_count") == 1
            and journal.get("malformed_count") == 2
            and (journal.get("entries") or [{}])[0].get("prior_rollup") == {"compacted_count": 99}
        )
        missing = read_login_rollup_repair_journal(root / "no-such-dir")
        checks["missing_journal_is_reported_never_created"] = (
            missing.get("entry_count") == 0
            and not (root / "no-such-dir").exists()
        )

    checks["next_family_is_not_handshake"] = (
        behavior_family(LOOP_LOGIN_JOURNAL_PRUNE_GOAL) != "network/handshake-digest-demo"
        and LOOP_LOGIN_JOURNAL_PRUNE_DONE_WHEN != ""
    )
    checks["contract_is_outcome_level"] = (
        "capability_exists:" not in LOOP_LOGIN_ROLLUP_JOURNAL_DONE_WHEN
        and "capability_proved:" not in LOOP_LOGIN_ROLLUP_JOURNAL_DONE_WHEN
    )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_loop_login_rollup_journal_capability()
    return {
        "ok": ok,
        "action": "loop_login_rollup_journal",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": LOOP_LOGIN_ROLLUP_JOURNAL_GOAL,
        "done_when": LOOP_LOGIN_ROLLUP_JOURNAL_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
