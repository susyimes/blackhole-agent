"""Scrub leftover launcher and task XML artifacts of swept login tasks.

Login-task sweep unschedules a record-gone logon task so logon stops firing
it, but the sweep only removes the scheduler entry: the dead launcher and
the task XML the registration wrote stay on disk until an operator deletes
the artifacts by hand.

This module is the scrub path: once a task is swept (its registration
record is gone), its launcher and task XML artifacts are deleted so a
record-gone task leaves no on-disk residue. The scrub only deletes files it
can prove are ours — the well-known launcher and task XML names with
restore-helper content — and it never touches a task whose registration
record still exists, so a live owner pid in any surviving repo is never
disturbed. Every scrub that removes artifacts is recorded in the durable
login-scrub audit trail so an operator can reconcile the deletions.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any, Callable

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
from blackhole_agent.loop_login_audit import (
    LOOP_LOGIN_AUDIT_DONE_WHEN,
    LOOP_LOGIN_AUDIT_GOAL,
    LOOP_LOGIN_AUDIT_ID,
    LOOP_LOGIN_AUDIT_LEFTOVER,
    login_audit_log_path,
    record_login_task_scrub,
)

SCHEMA_VERSION = 1
LOOP_LOGIN_SCRUB_ID = "capability.loop-login-scrub"
LOOP_LOGIN_SCRUB_DONE_WHEN = (
    "A swept login task's leftover launcher and task XML artifacts are "
    "scrubbed from disk so a record-gone task leaves no on-disk residue "
    "without disturbing a live owner pid in any surviving repo."
)
LOOP_LOGIN_SCRUB_GOAL = (
    "Repair login-task scrub: a swept scheduler entry leaves its dead "
    "launcher and task XML artifacts on disk until an operator deletes the "
    "artifacts by hand."
)
LOOP_LOGIN_SCRUB_LEFTOVER = (
    "Later genesis can take login-task scrub so a swept task's leftover "
    "launcher and task XML artifacts are scrubbed without an operator "
    "deleting the artifacts by hand."
)
REPO_ROOT = Path(__file__).resolve().parents[2]
LoginScheduler = Callable[[dict[str, Any]], dict[str, Any]]

def _task_artifact_candidates(task: dict[str, Any]) -> dict[str, list[Path]]:
    """Paths where the task's launcher and task XML should live, best first."""

    from blackhole_agent.loop_login_sweep import _task_registration_candidates
    from blackhole_agent.loop_login_task import LAUNCHER_NAME, TASK_XML_NAME

    launcher: list[Path] = []
    xml: list[Path] = []
    recorded_launcher = str(task.get("launcher_path") or "")
    recorded_xml = str(task.get("task_xml_path") or "")
    if recorded_launcher:
        launcher.append(Path(recorded_launcher))
    if recorded_xml:
        xml.append(Path(recorded_xml))
    for registration in _task_registration_candidates(task):
        launcher.append(registration.with_name(LAUNCHER_NAME))
        xml.append(registration.with_name(TASK_XML_NAME))

    def dedupe(paths: list[Path]) -> list[Path]:
        seen: set[str] = set()
        result: list[Path] = []
        for path in paths:
            key = str(path)
            if key not in seen:
                seen.add(key)
                result.append(path)
        return result

    return {"launcher": dedupe(launcher), "task_xml": dedupe(xml)}


def _artifact_is_ours(kind: str, path: Path) -> bool:
    """Only files with restore-helper content may be scrubbed.

    A foreign file that happens to carry the well-known name is kept: the
    scrub must never delete something another application owns.
    """

    from blackhole_agent.loop_login_task import LOGIN_TASK_NAME, RESTORE_HELPER

    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    if kind == "launcher":
        return RESTORE_HELPER.split(":")[-1] in text
    return LOGIN_TASK_NAME in text and "<LogonTrigger>" in text


def scrub_login_task_artifacts(
    task: dict[str, Any],
    *,
    audit_root: Path | None = None,
) -> dict[str, Any]:
    """Delete a swept task's leftover launcher and task XML artifacts.

    Only a task the sweep would remove — a restore-helper logon task whose
    registration record is gone — is scrubbed. A task whose record still
    exists belongs to a surviving repo: its launcher and task XML are kept,
    so a live owner pid in any surviving repo is never disturbed. A scrub
    that removes artifacts is recorded in the durable login-scrub audit
    trail so an operator can reconcile the deletion; a scrub that removes
    nothing records nothing.
    """

    from blackhole_agent.loop_login_sweep import login_task_sweep_reason

    reason = login_task_sweep_reason(task)
    if reason is None:
        return {
            "action": "scrub",
            "scrubbed": False,
            "skipped": True,
            "reason": "not_swept",
            "scrubbed_paths": [],
            "kept_foreign": [],
            "scrubbed_count": 0,
            "audit_recorded": False,
            "audit_path": "",
        }
    scrubbed: list[str] = []
    kept_foreign: list[str] = []
    for kind, candidates in _task_artifact_candidates(task).items():
        removed = False
        for path in candidates:
            if removed or not path.is_file():
                continue
            if not _artifact_is_ours(kind, path):
                kept_foreign.append(str(path))
                removed = True
                continue
            try:
                path.unlink()
            except OSError:
                kept_foreign.append(str(path))
                removed = True
                continue
            scrubbed.append(str(path))
            removed = True
    report = {
        "action": "scrub",
        "scrubbed": bool(scrubbed),
        "skipped": False,
        "reason": reason,
        "scrubbed_paths": scrubbed,
        "kept_foreign": kept_foreign,
        "scrubbed_count": len(scrubbed),
    }
    audit = record_login_task_scrub(task, report, audit_root=audit_root)
    report["audit_recorded"] = bool(audit.get("recorded"))
    report["audit_path"] = str(audit.get("audit_path") or "")
    return report


def scrub_swept_login_task_artifacts(root: Path) -> dict[str, Any]:
    """Scrub residue left by tasks swept before the scrub path existed.

    A sweep run before this capability landed removed the scheduler entry
    but left the launcher and task XML on disk. With both the scheduler
    entry and the registration record gone, the only trace is the artifact
    pair itself: this scans ``root`` for well-known launcher or task XML
    files whose sibling registration record is missing and scrubs the ones
    that carry restore-helper content. Each scrub is recorded in the durable
    login-scrub audit trail under ``root`` so an operator can reconcile the
    deletions.
    """

    from blackhole_agent.loop_login_task import (
        LAUNCHER_NAME,
        LOGIN_TASK_NAME,
        REGISTRATION_NAME,
        RESTORE_HELPER,
        TASK_XML_NAME,
    )

    root = Path(root)
    scrubbed: list[str] = []
    kept_foreign: list[str] = []
    seen_dirs: set[str] = set()
    audit_recorded = 0
    if root.is_dir():
        names = {LAUNCHER_NAME, TASK_XML_NAME}
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.name not in names:
                continue
            directory = str(path.parent)
            if directory in seen_dirs:
                continue
            seen_dirs.add(directory)
            registration = path.with_name(REGISTRATION_NAME)
            task = {
                "name": LOGIN_TASK_NAME,
                "helper": RESTORE_HELPER,
                "registration_path": str(registration),
                "launcher_path": str(path.with_name(LAUNCHER_NAME)),
                "task_xml_path": str(path.with_name(TASK_XML_NAME)),
            }
            report = scrub_login_task_artifacts(task, audit_root=root)
            scrubbed.extend(report.get("scrubbed_paths") or [])
            kept_foreign.extend(report.get("kept_foreign") or [])
            if report.get("audit_recorded"):
                audit_recorded += 1
    return {
        "action": "scrub_residue",
        "started": False,
        "root": str(root),
        "scrubbed": bool(scrubbed),
        "scrubbed_paths": scrubbed,
        "kept_foreign": kept_foreign,
        "scrubbed_count": len(scrubbed),
        "audit_recorded": audit_recorded,
        "audit_path": str(login_audit_log_path(root)),
        "scrubbed_at": utc_now_iso(),
    }


def loop_login_scrub_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.loop_login_scrub import "
        "builtin_loop_login_scrub_proof; r=builtin_loop_login_scrub_proof(); "
        "assert r['ok'] and r.get('action')=='loop_login_scrub' "
        "and r.get('passed_count',0) >= 18 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_loop_login_scrub_capability(*, repo_path: Path | None = None) -> Capability:
    """Register login-task scrub on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=LOOP_LOGIN_SCRUB_ID,
        name="Continuous-loop login-task scrub",
        description=(
            "A swept login task's leftover launcher and task XML artifacts "
            "are scrubbed from disk so a record-gone task leaves no on-disk "
            "residue without disturbing a live owner pid in any surviving "
            "repo."
        ),
        kind="python",
        entry="blackhole_agent.loop_login_scrub:builtin_loop_login_scrub_proof",
        proof_command=loop_login_scrub_proof_command(),
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
        ),
        behavior_paths=(
            "src/blackhole_agent/loop_login_scrub.py",
            "src/blackhole_agent/loop_login_sweep.py",
            "src/blackhole_agent/loop_login_task.py",
            "src/blackhole_agent/loop_login_audit.py",
            "src/blackhole_agent/unbound.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A swept login task leaves no on-disk residue: its dead launcher "
            "and task XML are scrubbed once the registration record is gone, "
            "foreign same-name files and a surviving repo's artifacts are "
            "kept, and a live owner pid is never disturbed."
        ),
        tags=("continuous-loop", "login", "startup", "restore", "scrub"),
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
            "loop_id": "login-scrub-proof",
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


def builtin_loop_login_scrub_proof() -> dict[str, Any]:
    """Hermetic proof: a swept task's artifacts are scrubbed; live owners kept."""

    from blackhole_agent.evolution_quality import behavior_family
    from blackhole_agent.kernel_genesis_diversify import DIVERSITY_CATALOG
    from blackhole_agent.kernel_leftover import leftover_marker_ids
    from blackhole_agent.loop_login_sweep import (
        LOOP_LOGIN_SWEEP_ID,
        FileLoginScheduler,
        sweep_login_tasks_missing_registration,
    )
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
    checks["denylists_self"] = LOOP_LOGIN_SCRUB_ID in LOCAL_DENYLIST
    checks["denylists_next_family"] = LOOP_LOGIN_AUDIT_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(LOOP_LOGIN_SCRUB_GOAL) == (
        LOOP_LOGIN_SCRUB_ID,
    )
    checks["leftover_text_binds_next_family"] = leftover_marker_ids(
        LOOP_LOGIN_AUDIT_LEFTOVER
    ) == (LOOP_LOGIN_AUDIT_ID,)
    checks["next_family_goal_is_login_audit"] = leftover_marker_ids(LOOP_LOGIN_AUDIT_GOAL) == (
        LOOP_LOGIN_AUDIT_ID,
    )
    checks["prior_family_markers_stay"] = leftover_marker_ids(LOOP_LOGIN_SCRUB_LEFTOVER) == (
        LOOP_LOGIN_SCRUB_ID,
    )
    catalog = DIVERSITY_CATALOG
    checks["catalog_names_login_scrub"] = (
        len(catalog) > 248
        and catalog[248]["id"] == LOOP_LOGIN_SCRUB_ID
        and catalog[248]["goal"] == LOOP_LOGIN_SCRUB_GOAL
        and catalog[248]["done_when"] == LOOP_LOGIN_SCRUB_DONE_WHEN
        and catalog[248]["source"] == "genesis_bind_loop_login_scrub"
    )
    checks["catalog_names_login_audit"] = (
        len(catalog) > 249
        and catalog[249]["id"] == LOOP_LOGIN_AUDIT_ID
        and catalog[249]["goal"] == LOOP_LOGIN_AUDIT_GOAL
        and catalog[249]["done_when"] == LOOP_LOGIN_AUDIT_DONE_WHEN
        and catalog[249]["source"] == "genesis_bind_loop_login_audit"
    )
    checks["login_sweep_stays_ahead"] = (
        len(catalog) > 247 and catalog[247]["id"] == LOOP_LOGIN_SWEEP_ID
    )

    dead_pid = 1_000_171
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

    with tempfile.TemporaryDirectory(prefix="loop-login-scrub-sweep-") as tmp:
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
        login_startup_registration_path(orphan).unlink()
        before = surviving_state.read_bytes()
        starts_before = len(starts)
        swept = sweep_login_tasks_missing_registration(scheduler=scheduler)
        again = sweep_login_tasks_missing_registration(scheduler=scheduler)
        result = dispatch_login_startup(surviving, controller_starter=starter)
        checks["swept_task_artifacts_are_scrubbed"] = (
            swept.get("started") is False
            and swept.get("action") == "sweep"
            and swept.get("swept") == [LOGIN_TASK_NAME]
            and swept.get("unscheduled") is True
            and not orphan_launcher.exists()
            and not orphan_xml.exists()
            and str(orphan_launcher) in (swept.get("scrubbed_artifacts") or {}).get(LOGIN_TASK_NAME, [])
            and str(orphan_xml) in (swept.get("scrubbed_artifacts") or {}).get(LOGIN_TASK_NAME, [])
            and swept.get("scrubbed_count") == 2
            and again.get("swept") == []
            and again.get("scrubbed_count") == 0
            and len(starts) == starts_before
        )
        checks["live_owner_artifacts_are_kept"] = (
            LOGIN_TASK_NAME in swept.get("kept")
            and surviving_registration is not None
            and load_login_startup_registration(surviving) == surviving_registration
            and surviving_launcher.is_file()
            and surviving_xml.is_file()
            and result.get("started") is False
            and result.get("restore_reason") == "live_owner"
            and result.get("scheduled") is True
            and surviving_state.read_bytes() == before
            and len(starts) == starts_before
            and pid_is_running(live_pid)
        )

    with tempfile.TemporaryDirectory(prefix="loop-login-scrub-foreign-") as tmp:
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
        login_startup_registration_path(repo).unlink()
        starts_before = len(starts)
        swept = sweep_login_tasks_missing_registration(scheduler=scheduler)
        checks["foreign_content_artifacts_are_kept"] = (
            swept.get("swept") == [LOGIN_TASK_NAME]
            and swept.get("scrubbed_count") == 0
            and launcher.is_file()
            and xml.is_file()
            and launcher.read_text(encoding="utf-8") == "print('another application')\n"
            and len(starts) == starts_before
        )

    with tempfile.TemporaryDirectory(prefix="loop-login-scrub-file-") as tmp:
        parent = Path(tmp)
        repo = parent / "file-backend-repo"
        repo.mkdir()
        (repo / "mission.json").write_text('{"status":"active"}\n', encoding="utf-8")
        _seed_orphaned(repo, pid=dead_pid)
        file_scheduler = FileLoginScheduler(parent / "scheduler-root")
        register_loop_restore_at_login(repo, scheduler=file_scheduler)
        launcher = login_startup_launcher_path(repo)
        xml = login_startup_task_xml_path(repo)
        login_startup_registration_path(repo).unlink()
        starts_before = len(starts)
        swept = sweep_login_tasks_missing_registration(scheduler=file_scheduler)
        checks["file_backend_sweep_scrubs_artifacts"] = (
            swept.get("backend") == "file"
            and swept.get("swept") == [LOGIN_TASK_NAME]
            and swept.get("scrubbed_count") == 2
            and not launcher.exists()
            and not xml.exists()
            and file_scheduler({"action": "list"}).get("tasks") == []
            and len(starts) == starts_before
        )

    with tempfile.TemporaryDirectory(prefix="loop-login-scrub-residue-") as tmp:
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
        checks["already_swept_residue_is_scrubbed"] = (
            residue.get("action") == "scrub_residue"
            and residue.get("started") is False
            and residue.get("scrubbed") is True
            and residue.get("scrubbed_count") == 2
            and not launcher.exists()
            and not xml.exists()
            and again.get("scrubbed_count") == 0
            and len(starts) == starts_before
        )

    checks["next_family_is_not_handshake"] = (
        behavior_family(LOOP_LOGIN_AUDIT_GOAL) != "network/handshake-digest-demo"
        and LOOP_LOGIN_AUDIT_DONE_WHEN != ""
    )
    checks["contract_is_outcome_level"] = (
        "capability_exists:" not in LOOP_LOGIN_SCRUB_DONE_WHEN
        and "capability_proved:" not in LOOP_LOGIN_SCRUB_DONE_WHEN
    )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_loop_login_scrub_capability()
    return {
        "ok": ok,
        "action": "loop_login_scrub",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": LOOP_LOGIN_SCRUB_GOAL,
        "done_when": LOOP_LOGIN_SCRUB_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
