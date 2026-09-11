"""Sweep scheduled login tasks whose registration record is gone.

Login-task retirement unschedules a deleted repo's registration while the
record can still be reached from the repo's own dispatch path. But a
registration record can disappear while the scheduler entry survives: an
operator cleans a mission directory, or a retired repo's unschedule call
never reached the scheduler. The logon task then keeps firing a dead
launcher until an operator deletes the task by hand.

This module is the sweep path: it enumerates the scheduler, and any task
that targets the restore helper whose registration record is gone is
unscheduled so logon stops firing it. A swept task's dead launcher and task
XML artifacts are scrubbed alongside so a record-gone task leaves no
on-disk residue. The sweep never starts a controller, and a task whose
record still exists belongs to a surviving repo and is kept untouched, so
a live owner pid in any surviving repo is never disturbed.
"""

from __future__ import annotations

import hashlib
import json
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
from blackhole_agent.loop_login_scrub import (
    LOOP_LOGIN_SCRUB_DONE_WHEN,
    LOOP_LOGIN_SCRUB_GOAL,
    LOOP_LOGIN_SCRUB_ID,
    LOOP_LOGIN_SCRUB_LEFTOVER,
)

SCHEMA_VERSION = 1
LOOP_LOGIN_SWEEP_ID = "capability.loop-login-sweep"
LOOP_LOGIN_SWEEP_DONE_WHEN = (
    "A scheduled login task whose registration record is gone is removed "
    "from the scheduler so logon stops firing it without disturbing a live "
    "owner pid in any surviving repo."
)
LOOP_LOGIN_SWEEP_GOAL = (
    "Repair login-task sweep: a scheduled logon task whose registration "
    "record is gone keeps firing until an operator deletes the task by hand."
)
LOOP_LOGIN_SWEEP_LEFTOVER = (
    "Later genesis can take login-task sweep so a scheduled task whose "
    "registration record is gone is removed without an operator deleting "
    "the task by hand."
)
REPO_ROOT = Path(__file__).resolve().parents[2]
LoginScheduler = Callable[[dict[str, Any]], dict[str, Any]]


class FileLoginScheduler:
    """File-backed login scheduler: one JSON record per scheduled task.

    The store sits beside the durable Unbound state so the sweep can
    enumerate scheduled login tasks even when no OS scheduler is wired in.
    Tasks are keyed by name and repo path so two repos sharing the well-known
    login task name never overwrite each other.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    @property
    def store_dir(self) -> Path:
        return self.root / "login-scheduler"

    def _task_path(self, name: str, repo_path: str) -> Path:
        key = hashlib.sha1(f"{name}|{repo_path}".encode("utf-8")).hexdigest()[:16]
        return self.store_dir / f"{key}.json"

    def __call__(self, payload: dict[str, Any]) -> dict[str, Any]:
        action = payload.get("action")
        if action == "list":
            tasks: list[dict[str, Any]] = []
            store = self.store_dir
            if store.is_dir():
                for path in sorted(store.glob("*.json")):
                    try:
                        record = json.loads(path.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError):
                        continue
                    if isinstance(record, dict):
                        tasks.append(record)
            return {"backend": "file", "listed": True, "tasks": tasks}
        name = str(payload.get("name") or "")
        repo_path = str(payload.get("repo_path") or "")
        path = self._task_path(name, repo_path)
        if action == "unschedule":
            existed = path.is_file()
            try:
                path.unlink(missing_ok=True)
            except OSError:
                return {"backend": "file", "unscheduled": False}
            return {"backend": "file", "unscheduled": True, "existed": existed}
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(path)
        return {"backend": "file", "applied": True}


def _task_registration_candidates(task: dict[str, Any]) -> list[Path]:
    """Paths where the task's registration record should live, best first."""

    candidates: list[Path] = []
    recorded = str(task.get("registration_path") or "")
    if recorded:
        candidates.append(Path(recorded))
    output = str(task.get("output_dir") or "")
    if output:
        from blackhole_agent.loop_login_task import REGISTRATION_NAME

        candidates.append(Path(output) / REGISTRATION_NAME)
    repo = str(task.get("repo_path") or "")
    if repo:
        from blackhole_agent.loop_login_task import login_startup_registration_path

        candidates.append(login_startup_registration_path(Path(repo)))
    return candidates


def login_task_sweep_reason(task: dict[str, Any]) -> str | None:
    """Return why a scheduled login task must be swept, or None.

    A task is swept when it is a restore-helper logon task whose registration
    record is gone: logon would keep firing a dead launcher until an operator
    deletes the task by hand. A task whose record still exists belongs to a
    surviving repo and is kept untouched, as is any task that is not a
    restore-helper logon task.
    """

    from blackhole_agent.loop_login_task import LOGIN_TASK_NAME, RESTORE_HELPER

    if str(task.get("name") or "") != LOGIN_TASK_NAME:
        return None
    if str(task.get("helper") or "") != RESTORE_HELPER:
        return None
    candidates = _task_registration_candidates(task)
    if not candidates:
        return None
    if any(path.is_file() for path in candidates):
        return None
    return "registration_gone"


def sweep_login_tasks_missing_registration(
    output_dir: Path | None = None,
    *,
    scheduler: LoginScheduler | None = None,
) -> dict[str, Any]:
    """Unschedule logon tasks whose registration record is gone.

    This enumerates, unschedules, and scrubs the swept task's dead launcher
    and task XML artifacts. It never starts a controller, and it removes
    only tasks whose registration record is gone, so a live owner pid in any
    surviving repo is never disturbed: a surviving repo's task still has its
    record and is kept.
    """

    from blackhole_agent.unbound import DEFAULT_OUTPUT_DIR

    if scheduler is None:
        output = DEFAULT_OUTPUT_DIR if output_dir is None else Path(output_dir)
        scheduler = FileLoginScheduler(output)
    listing = scheduler({"action": "list"})
    tasks = listing.get("tasks") or []
    swept: list[str] = []
    kept: list[str] = []
    reasons: dict[str, str] = {}
    scrubbed_artifacts: dict[str, list[str]] = {}
    kept_foreign: dict[str, list[str]] = {}
    for task in tasks:
        if not isinstance(task, dict):
            continue
        name = str(task.get("name") or "")
        reason = login_task_sweep_reason(task)
        if reason is None:
            kept.append(name)
            continue
        applied = scheduler(
            {
                **task,
                "action": "unschedule",
                "scheduled": False,
                "sweep_reason": reason,
            }
        )
        if applied.get("unscheduled") is not False:
            swept.append(name)
            reasons[name] = reason
            from blackhole_agent.loop_login_scrub import scrub_login_task_artifacts

            scrub = scrub_login_task_artifacts(task)
            scrubbed_artifacts[name] = list(scrub.get("scrubbed_paths") or [])
            foreign = list(scrub.get("kept_foreign") or [])
            if foreign:
                kept_foreign[name] = foreign
        else:
            kept.append(name)
    return {
        "started": False,
        "action": "sweep",
        "backend": listing.get("backend", "file"),
        "swept": swept,
        "swept_reasons": reasons,
        "kept": kept,
        "swept_count": len(swept),
        "scheduled": bool(kept),
        "unscheduled": bool(swept),
        "listed_count": len(tasks),
        "scrubbed_artifacts": scrubbed_artifacts,
        "kept_foreign_artifacts": kept_foreign,
        "scrubbed_count": sum(len(paths) for paths in scrubbed_artifacts.values()),
        "swept_at": utc_now_iso(),
    }


def loop_login_sweep_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.loop_login_sweep import "
        "builtin_loop_login_sweep_proof; r=builtin_loop_login_sweep_proof(); "
        "assert r['ok'] and r.get('action')=='loop_login_sweep' "
        "and r.get('passed_count',0) >= 17 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_loop_login_sweep_capability(*, repo_path: Path | None = None) -> Capability:
    """Register login-task sweep on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=LOOP_LOGIN_SWEEP_ID,
        name="Continuous-loop login-task sweep",
        description=(
            "A scheduled login task whose registration record is gone is "
            "removed from the scheduler so logon stops firing it without "
            "disturbing a live owner pid in any surviving repo."
        ),
        kind="python",
        entry="blackhole_agent.loop_login_sweep:builtin_loop_login_sweep_proof",
        proof_command=loop_login_sweep_proof_command(),
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
        ),
        behavior_paths=(
            "src/blackhole_agent/loop_login_sweep.py",
            "src/blackhole_agent/loop_login_retire.py",
            "src/blackhole_agent/loop_login_task.py",
            "src/blackhole_agent/loop_login_scrub.py",
            "src/blackhole_agent/unbound.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A record-gone login task is swept from the scheduler: logon "
            "stops firing the dead launcher, a task whose registration "
            "record still exists is kept, and a live owner pid in any "
            "surviving repo is left untouched."
        ),
        tags=("continuous-loop", "login", "startup", "restore", "sweep"),
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
            "loop_id": "login-sweep-proof",
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


def builtin_loop_login_sweep_proof() -> dict[str, Any]:
    """Hermetic proof: a record-gone login task is swept; live owners kept."""

    from blackhole_agent.evolution_quality import behavior_family
    from blackhole_agent.kernel_genesis_diversify import DIVERSITY_CATALOG
    from blackhole_agent.kernel_leftover import leftover_marker_ids
    from blackhole_agent.loop_login_retire import LOOP_LOGIN_RETIRE_ID
    from blackhole_agent.loop_login_task import (
        LOGIN_TASK_NAME,
        dispatch_login_startup,
        load_login_startup_registration,
        login_startup_registration_path,
        register_loop_restore_at_login,
    )
    from blackhole_agent.unbound import continuous_loop_lock_path, pid_is_running

    checks: dict[str, bool] = {}
    checks["denylists_self"] = LOOP_LOGIN_SWEEP_ID in LOCAL_DENYLIST
    checks["denylists_next_family"] = LOOP_LOGIN_SCRUB_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(LOOP_LOGIN_SWEEP_GOAL) == (
        LOOP_LOGIN_SWEEP_ID,
    )
    checks["leftover_text_binds_next_family"] = leftover_marker_ids(
        LOOP_LOGIN_SCRUB_LEFTOVER
    ) == (LOOP_LOGIN_SCRUB_ID,)
    checks["next_family_goal_is_login_scrub"] = leftover_marker_ids(LOOP_LOGIN_SCRUB_GOAL) == (
        LOOP_LOGIN_SCRUB_ID,
    )
    checks["prior_family_markers_stay"] = leftover_marker_ids(LOOP_LOGIN_SWEEP_LEFTOVER) == (
        LOOP_LOGIN_SWEEP_ID,
    )
    catalog = DIVERSITY_CATALOG
    checks["catalog_names_login_sweep"] = (
        len(catalog) > 247
        and catalog[247]["id"] == LOOP_LOGIN_SWEEP_ID
        and catalog[247]["goal"] == LOOP_LOGIN_SWEEP_GOAL
        and catalog[247]["done_when"] == LOOP_LOGIN_SWEEP_DONE_WHEN
        and catalog[247]["source"] == "genesis_bind_loop_login_sweep"
    )
    checks["catalog_names_login_scrub"] = (
        len(catalog) > 248
        and catalog[248]["id"] == LOOP_LOGIN_SCRUB_ID
        and catalog[248]["goal"] == LOOP_LOGIN_SCRUB_GOAL
        and catalog[248]["done_when"] == LOOP_LOGIN_SCRUB_DONE_WHEN
        and catalog[248]["source"] == "genesis_bind_loop_login_scrub"
    )
    checks["login_retire_stays_ahead"] = (
        len(catalog) > 246 and catalog[246]["id"] == LOOP_LOGIN_RETIRE_ID
    )

    dead_pid = 1_000_151
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

    with tempfile.TemporaryDirectory(prefix="loop-login-sweep-orphan-") as tmp:
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
        surviving_registration = load_login_startup_registration(surviving)
        orphan_record = login_startup_registration_path(orphan)
        orphan_record.unlink()
        before = surviving_state.read_bytes()
        starts_before = len(starts)
        swept = sweep_login_tasks_missing_registration(scheduler=scheduler)
        again = sweep_login_tasks_missing_registration(scheduler=scheduler)
        result = dispatch_login_startup(surviving, controller_starter=starter)
        checks["record_gone_task_is_unscheduled"] = (
            len(scheduler.tasks) == 2 - 1
            and swept.get("started") is False
            and swept.get("action") == "sweep"
            and swept.get("swept") == [LOGIN_TASK_NAME]
            and swept.get("swept_reasons") == {LOGIN_TASK_NAME: "registration_gone"}
            and swept.get("unscheduled") is True
            and swept.get("listed_count") == 2
            and again.get("swept") == []
            and again.get("unscheduled") is False
            and len(starts) == starts_before
        )
        checks["live_owner_task_is_kept"] = (
            LOGIN_TASK_NAME in swept.get("kept")
            and surviving_registration is not None
            and load_login_startup_registration(surviving) == surviving_registration
            and result.get("started") is False
            and result.get("restore_reason") == "live_owner"
            and result.get("scheduled") is True
            and surviving_state.read_bytes() == before
            and len(starts) == starts_before
            and pid_is_running(live_pid)
        )

    with tempfile.TemporaryDirectory(prefix="loop-login-sweep-foreign-") as tmp:
        scheduler = _ProofScheduler()
        scheduler(
            {
                "name": "OtherAppLogon",
                "repo_path": str(Path(tmp) / "other-app"),
                "trigger": "at_logon",
            }
        )
        drifted = scheduler(
            {
                "name": LOGIN_TASK_NAME,
                "repo_path": str(Path(tmp) / "drifted-repo"),
                "helper": "blackhole_agent.other:helper",
            }
        )
        starts_before = len(starts)
        swept = sweep_login_tasks_missing_registration(scheduler=scheduler)
        checks["foreign_and_drifted_tasks_are_kept"] = (
            drifted.get("applied") is True
            and swept.get("swept") == []
            and swept.get("unscheduled") is False
            and sorted(swept.get("kept") or []) == [LOGIN_TASK_NAME, "OtherAppLogon"]
            and len(scheduler.tasks) == 2
            and len(starts) == starts_before
        )

    with tempfile.TemporaryDirectory(prefix="loop-login-sweep-file-") as tmp:
        parent = Path(tmp)
        repo = parent / "file-backend-repo"
        repo.mkdir()
        (repo / "mission.json").write_text('{"status":"active"}\n', encoding="utf-8")
        _seed_orphaned(repo, pid=dead_pid)
        store_root = parent / "scheduler-root"
        file_scheduler = FileLoginScheduler(store_root)
        register_loop_restore_at_login(repo, scheduler=file_scheduler)
        listed = file_scheduler({"action": "list"})
        record = login_startup_registration_path(repo)
        record.unlink()
        starts_before = len(starts)
        swept = sweep_login_tasks_missing_registration(scheduler=file_scheduler)
        after = file_scheduler({"action": "list"})
        checks["file_backend_sweeps_record_gone_task"] = (
            listed.get("listed") is True
            and len(listed.get("tasks") or []) == 1
            and swept.get("action") == "sweep"
            and swept.get("backend") == "file"
            and swept.get("swept") == [LOGIN_TASK_NAME]
            and after.get("tasks") == []
            and len(starts) == starts_before
        )

    checks["next_family_is_not_handshake"] = (
        behavior_family(LOOP_LOGIN_SCRUB_GOAL) != "network/handshake-digest-demo"
        and LOOP_LOGIN_SCRUB_DONE_WHEN != ""
    )
    checks["contract_is_outcome_level"] = (
        "capability_exists:" not in LOOP_LOGIN_SWEEP_DONE_WHEN
        and "capability_proved:" not in LOOP_LOGIN_SWEEP_DONE_WHEN
    )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_loop_login_sweep_capability()
    return {
        "ok": ok,
        "action": "loop_login_sweep",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": LOOP_LOGIN_SWEEP_GOAL,
        "done_when": LOOP_LOGIN_SWEEP_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
