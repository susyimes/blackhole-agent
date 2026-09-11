"""Record a durable audit trail of swept login tasks' scrubbed artifacts.

Login-task scrub deletes a swept task's leftover launcher and task XML
artifacts, but the deletion itself leaves no durable record: an operator
reconciling deletions by hand cannot tell a scrubbed task from one that
was never scheduled.

This module is the audit path: every scrub that removes a swept task's
artifacts appends one JSONL entry to a durable audit trail naming the
task, its repo, the scrubbed launcher and task XML paths, and the scrub
time, so an operator can see exactly what was scrubbed. Each append prunes
aged-out records so the trail stays bounded without an operator pruning
stale entries by hand, and every pruned record leaves a durable tombstone
naming what aged out so an operator reconciling the bounded trail can tell
an aged-out record from one that was never written. Only tasks whose
registration record is gone are ever scrubbed, so only those scrubs are
recorded: a task whose record still exists belongs to a surviving repo,
its artifacts are kept, nothing is written for it, and a live owner pid
in any surviving repo is never disturbed.
"""

from __future__ import annotations

import json
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
from blackhole_agent.loop_login_prune import (
    LOOP_LOGIN_PRUNE_DONE_WHEN,
    LOOP_LOGIN_PRUNE_GOAL,
    LOOP_LOGIN_PRUNE_ID,
    LOOP_LOGIN_PRUNE_LEFTOVER,
)
from blackhole_agent.loop_login_tombstone import is_login_audit_tombstone

SCHEMA_VERSION = 1
LOOP_LOGIN_AUDIT_ID = "capability.loop-login-audit"
LOOP_LOGIN_AUDIT_DONE_WHEN = (
    "A swept login task's scrubbed launcher and task XML removal is recorded "
    "in a durable audit trail so an operator can see what was scrubbed "
    "without disturbing a live owner pid in any surviving repo."
)
LOOP_LOGIN_AUDIT_GOAL = (
    "Repair login-scrub audit: a swept login task's scrubbed on-disk "
    "artifacts leave no durable record, so an operator reconciling deletions "
    "by hand cannot tell a scrubbed task from one that was never scheduled."
)
LOOP_LOGIN_AUDIT_LEFTOVER = (
    "Later genesis can take login-scrub audit so a swept task's scrubbed "
    "artifacts are recorded durably without an operator reconciling "
    "deletions by hand."
)
LOGIN_AUDIT_LOG_NAME = "login-scrub-audit.jsonl"
REPO_ROOT = Path(__file__).resolve().parents[2]


def login_audit_log_path(root: Path | None = None) -> Path:
    """Durable audit trail location under a repo's login state root."""

    from blackhole_agent.unbound import DEFAULT_OUTPUT_DIR

    base = DEFAULT_OUTPUT_DIR if root is None else Path(root)
    return base / LOGIN_AUDIT_LOG_NAME


def record_login_task_scrub(
    task: dict[str, Any],
    report: dict[str, Any],
    *,
    audit_root: Path | None = None,
) -> dict[str, Any]:
    """Append one durable audit entry for a swept task's scrubbed artifacts.

    Nothing is appended when the scrub removed nothing — a kept live-owner
    or foreign task must stay indistinguishable from before, and a live
    owner pid in any surviving repo is never disturbed.
    """

    root = audit_root if audit_root is not None else (task.get("output_dir") or None)
    path = login_audit_log_path(root)
    scrubbed = [str(p) for p in (report.get("scrubbed_paths") or [])]
    if not scrubbed:
        return {
            "action": "audit_record",
            "recorded": False,
            "reason": "nothing_scrubbed",
            "audit_path": str(path),
        }
    entry = {
        "schema_version": SCHEMA_VERSION,
        "event": "login_task_artifacts_scrubbed",
        "task_name": str(task.get("name") or ""),
        "repo_path": str(task.get("repo_path") or ""),
        "reason": str(report.get("reason") or ""),
        "scrubbed_paths": scrubbed,
        "kept_foreign": [str(p) for p in (report.get("kept_foreign") or [])],
        "scrubbed_at": utc_now_iso(),
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")
    except OSError as error:
        return {
            "action": "audit_record",
            "recorded": False,
            "reason": "audit_write_failed",
            "audit_path": str(path),
            "error": str(error),
        }
    from blackhole_agent.loop_login_prune import prune_login_scrub_audit

    prune = prune_login_scrub_audit(root)
    return {
        "action": "audit_record",
        "recorded": True,
        "audit_path": str(path),
        "entry": entry,
        "audit_pruned": bool(prune.get("pruned")),
        "audit_pruned_count": int(prune.get("pruned_count") or 0),
    }


def read_login_scrub_audit(root: Path | None = None) -> dict[str, Any]:
    """Read the durable audit trail so an operator can reconcile deletions.

    Malformed lines are counted and skipped rather than failing the read,
    so a partially written trail still shows every intact scrub record.
    Prune tombstones are surfaced in ``tombstone_count`` so an operator
    reconciling the bounded trail can see what aged out.
    """

    path = login_audit_log_path(root)
    entries: list[dict[str, Any]] = []
    malformed = 0
    tombstones = 0
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
            if isinstance(record, dict):
                entries.append(record)
                if is_login_audit_tombstone(record):
                    tombstones += 1
            else:
                malformed += 1
    return {
        "action": "audit_read",
        "audit_path": str(path),
        "entries": entries,
        "entry_count": len(entries),
        "tombstone_count": tombstones,
        "malformed_count": malformed,
    }


def loop_login_audit_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.loop_login_audit import "
        "builtin_loop_login_audit_proof; r=builtin_loop_login_audit_proof(); "
        "assert r['ok'] and r.get('action')=='loop_login_audit' "
        "and r.get('passed_count',0) >= 19 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_loop_login_audit_capability(*, repo_path: Path | None = None) -> Capability:
    """Register login-scrub audit on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=LOOP_LOGIN_AUDIT_ID,
        name="Continuous-loop login-scrub audit",
        description=(
            "A swept login task's scrubbed launcher and task XML removal is "
            "recorded in a durable audit trail so an operator can see what "
            "was scrubbed without disturbing a live owner pid in any "
            "surviving repo."
        ),
        kind="python",
        entry="blackhole_agent.loop_login_audit:builtin_loop_login_audit_proof",
        proof_command=loop_login_audit_proof_command(),
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
        ),
        behavior_paths=(
            "src/blackhole_agent/loop_login_audit.py",
            "src/blackhole_agent/loop_login_scrub.py",
            "src/blackhole_agent/loop_login_sweep.py",
            "src/blackhole_agent/loop_login_prune.py",
            "src/blackhole_agent/unbound.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A swept login task's scrub is reconcilable: the durable audit "
            "trail records the task, its repo, the scrubbed launcher and "
            "task XML paths, and the scrub time, kept and foreign artifacts "
            "record nothing, and a live owner pid is never disturbed."
        ),
        tags=("continuous-loop", "login", "startup", "restore", "audit"),
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
            "loop_id": "login-audit-proof",
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


def builtin_loop_login_audit_proof() -> dict[str, Any]:
    """Hermetic proof: a swept task's scrub is recorded; live owners kept."""

    from blackhole_agent.evolution_quality import behavior_family
    from blackhole_agent.kernel_genesis_diversify import DIVERSITY_CATALOG
    from blackhole_agent.kernel_leftover import leftover_marker_ids
    from blackhole_agent.loop_login_scrub import LOOP_LOGIN_SCRUB_ID, scrub_login_task_artifacts
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
    checks["denylists_self"] = LOOP_LOGIN_AUDIT_ID in LOCAL_DENYLIST
    checks["denylists_next_family"] = LOOP_LOGIN_PRUNE_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(LOOP_LOGIN_AUDIT_GOAL) == (
        LOOP_LOGIN_AUDIT_ID,
    )
    checks["leftover_text_binds_next_family"] = leftover_marker_ids(
        LOOP_LOGIN_PRUNE_LEFTOVER
    ) == (LOOP_LOGIN_PRUNE_ID,)
    checks["next_family_goal_is_login_prune"] = leftover_marker_ids(LOOP_LOGIN_PRUNE_GOAL) == (
        LOOP_LOGIN_PRUNE_ID,
    )
    checks["prior_family_markers_stay"] = leftover_marker_ids(LOOP_LOGIN_AUDIT_LEFTOVER) == (
        LOOP_LOGIN_AUDIT_ID,
    )
    catalog = DIVERSITY_CATALOG
    checks["catalog_names_login_audit"] = (
        len(catalog) > 249
        and catalog[249]["id"] == LOOP_LOGIN_AUDIT_ID
        and catalog[249]["goal"] == LOOP_LOGIN_AUDIT_GOAL
        and catalog[249]["done_when"] == LOOP_LOGIN_AUDIT_DONE_WHEN
        and catalog[249]["source"] == "genesis_bind_loop_login_audit"
    )
    checks["catalog_names_login_prune"] = (
        len(catalog) > 250
        and catalog[250]["id"] == LOOP_LOGIN_PRUNE_ID
        and catalog[250]["goal"] == LOOP_LOGIN_PRUNE_GOAL
        and catalog[250]["done_when"] == LOOP_LOGIN_PRUNE_DONE_WHEN
        and catalog[250]["source"] == "genesis_bind_loop_login_prune"
    )
    checks["login_scrub_stays_ahead"] = (
        len(catalog) > 248 and catalog[248]["id"] == LOOP_LOGIN_SCRUB_ID
    )

    dead_pid = 1_000_191
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

    with tempfile.TemporaryDirectory(prefix="loop-login-audit-sweep-") as tmp:
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
        orphan_launcher = login_startup_launcher_path(orphan)
        orphan_xml = login_startup_task_xml_path(orphan)
        surviving_launcher = login_startup_launcher_path(surviving)
        surviving_xml = login_startup_task_xml_path(surviving)
        surviving_registration = load_login_startup_registration(surviving)
        orphan_audit_root = login_startup_registration_path(orphan).parent
        surviving_audit_root = login_startup_registration_path(surviving).parent
        login_startup_registration_path(orphan).unlink()
        before = surviving_state.read_bytes()
        starts_before = len(starts)
        swept = sweep_login_tasks_missing_registration(scheduler=scheduler)
        again = sweep_login_tasks_missing_registration(scheduler=scheduler)
        result = dispatch_login_startup(surviving, controller_starter=starter)
        trail = read_login_scrub_audit(orphan_audit_root)
        entries = trail.get("entries") or []
        entry = entries[0] if entries else {}
        checks["swept_scrub_is_recorded_durably"] = (
            swept.get("action") == "sweep"
            and swept.get("swept") == [LOGIN_TASK_NAME]
            and swept.get("scrubbed_count") == 2
            and swept.get("audit_recorded") == 1
            and login_audit_log_path(orphan_audit_root).is_file()
            and trail.get("entry_count") == 1
            and entry.get("event") == "login_task_artifacts_scrubbed"
            and entry.get("task_name") == LOGIN_TASK_NAME
            and str(orphan_launcher) in (entry.get("scrubbed_paths") or [])
            and str(orphan_xml) in (entry.get("scrubbed_paths") or [])
            and not orphan_launcher.exists()
            and not orphan_xml.exists()
            and again.get("swept") == []
            and again.get("scrubbed_count") == 0
            and again.get("audit_recorded") == 0
            and read_login_scrub_audit(orphan_audit_root).get("entry_count") == 1
            and len(starts) == starts_before
        )
        checks["operator_can_reconcile_from_trail"] = (
            entry.get("reason") == "registration_gone"
            and bool(entry.get("repo_path"))
            and len(entry.get("scrubbed_paths") or []) == 2
            and entry.get("kept_foreign") == []
            and bool(entry.get("scrubbed_at"))
            and trail.get("malformed_count") == 0
        )
        checks["live_owner_not_disturbed"] = (
            LOGIN_TASK_NAME in swept.get("kept")
            and surviving_registration is not None
            and load_login_startup_registration(surviving) == surviving_registration
            and surviving_launcher.is_file()
            and surviving_xml.is_file()
            and read_login_scrub_audit(surviving_audit_root).get("entry_count") == 0
            and not login_audit_log_path(surviving_audit_root).exists()
            and result.get("started") is False
            and result.get("restore_reason") == "live_owner"
            and result.get("scheduled") is True
            and surviving_state.read_bytes() == before
            and len(starts) == starts_before
            and pid_is_running(live_pid)
        )

    with tempfile.TemporaryDirectory(prefix="loop-login-audit-residue-") as tmp:
        from blackhole_agent.loop_login_scrub import scrub_swept_login_task_artifacts

        parent = Path(tmp)
        repo = parent / "already-swept-repo"
        repo.mkdir()
        (repo / "mission.json").write_text('{"status":"active"}\n', encoding="utf-8")
        _seed_orphaned(repo, pid=dead_pid)
        scheduler = _ProofScheduler()
        register_loop_restore_at_login(repo, scheduler=scheduler)
        launcher = login_startup_launcher_path(repo)
        xml = login_startup_task_xml_path(repo)
        login_startup_registration_path(repo).unlink()
        scheduler.tasks.clear()
        starts_before = len(starts)
        residue = scrub_swept_login_task_artifacts(parent)
        again = scrub_swept_login_task_artifacts(parent)
        trail = read_login_scrub_audit(parent)
        entries = trail.get("entries") or []
        entry = entries[0] if entries else {}
        checks["residue_scrub_is_recorded"] = (
            residue.get("action") == "scrub_residue"
            and residue.get("scrubbed_count") == 2
            and residue.get("audit_recorded") == 1
            and login_audit_log_path(parent).is_file()
            and trail.get("entry_count") == 1
            and str(launcher) in (entry.get("scrubbed_paths") or [])
            and str(xml) in (entry.get("scrubbed_paths") or [])
            and not launcher.exists()
            and not xml.exists()
            and again.get("scrubbed_count") == 0
            and again.get("audit_recorded") == 0
            and read_login_scrub_audit(parent).get("entry_count") == 1
            and len(starts) == starts_before
        )

    with tempfile.TemporaryDirectory(prefix="loop-login-audit-foreign-") as tmp:
        parent = Path(tmp)
        repo = parent / "orphan-repo"
        repo.mkdir()
        (repo / "mission.json").write_text('{"status":"active"}\n', encoding="utf-8")
        _seed_orphaned(repo, pid=dead_pid)
        scheduler = _ProofScheduler()
        register_loop_restore_at_login(repo, scheduler=scheduler)
        launcher = login_startup_launcher_path(repo)
        xml = login_startup_task_xml_path(repo)
        launcher.write_text("print('another application')\n", encoding="utf-8")
        xml.write_text("<other>not a task</other>\n", encoding="utf-8")
        task = load_login_startup_registration(repo) or {}
        login_startup_registration_path(repo).unlink()
        starts_before = len(starts)
        report = scrub_login_task_artifacts(task)
        checks["foreign_content_records_nothing"] = (
            report.get("reason") == "registration_gone"
            and report.get("scrubbed_count") == 0
            and report.get("audit_recorded") is False
            and launcher.is_file()
            and xml.is_file()
            and not login_audit_log_path(login_startup_registration_path(repo).parent).exists()
            and len(starts) == starts_before
        )

    with tempfile.TemporaryDirectory(prefix="loop-login-audit-malformed-") as tmp:
        path = login_audit_log_path(Path(tmp))
        path.write_text(
            '{"event": "login_task_artifacts_scrubbed", "task_name": "T"}\n'
            "not json at all\n"
            '["a", "list"]\n',
            encoding="utf-8",
        )
        trail = read_login_scrub_audit(Path(tmp))
        checks["audit_read_tolerates_malformed"] = (
            trail.get("entry_count") == 1
            and trail.get("malformed_count") == 2
            and (trail.get("entries") or [{}])[0].get("task_name") == "T"
        )

    checks["next_family_is_not_handshake"] = (
        behavior_family(LOOP_LOGIN_PRUNE_GOAL) != "network/handshake-digest-demo"
        and LOOP_LOGIN_PRUNE_DONE_WHEN != ""
    )
    checks["contract_is_outcome_level"] = (
        "capability_exists:" not in LOOP_LOGIN_AUDIT_DONE_WHEN
        and "capability_proved:" not in LOOP_LOGIN_AUDIT_DONE_WHEN
    )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_loop_login_audit_capability()
    return {
        "ok": ok,
        "action": "loop_login_audit",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": LOOP_LOGIN_AUDIT_GOAL,
        "done_when": LOOP_LOGIN_AUDIT_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
