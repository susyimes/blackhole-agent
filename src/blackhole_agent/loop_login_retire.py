"""Retire a login startup registration whose repo was deleted.

Login-task staleness repair can re-point a command or launcher at a moved
repo, but a registration whose repo was deleted has nothing to re-point to:
the logon task keeps firing a dead launcher until an operator unschedules it
by hand. This helper unschedules that dead registration. Retirement never
starts a controller, and it removes only the dead repo's registration, so a
live owner pid in any surviving repo is not disturbed. Dispatch still
refuses a second controller because it reuses the restore helper.
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
from blackhole_agent.loop_login_sweep import (
    LOOP_LOGIN_SWEEP_DONE_WHEN,
    LOOP_LOGIN_SWEEP_GOAL,
    LOOP_LOGIN_SWEEP_ID,
    LOOP_LOGIN_SWEEP_LEFTOVER,
)

SCHEMA_VERSION = 1
LOOP_LOGIN_RETIRE_ID = "capability.loop-login-retire"
LOOP_LOGIN_RETIRE_DONE_WHEN = (
    "A login startup registration whose repo was deleted is unscheduled so "
    "logon stops firing a dead launcher without disturbing a live owner pid "
    "in any surviving repo."
)
LOOP_LOGIN_RETIRE_GOAL = (
    "Repair login-task retirement: a registration whose repo was deleted "
    "keeps the logon task firing a dead launcher until an operator "
    "unschedules it by hand."
)
LOOP_LOGIN_RETIRE_LEFTOVER = (
    "Later genesis can take login-task retirement so a deleted repo's "
    "registration is unscheduled without an operator doing it by hand."
)
REPO_ROOT = Path(__file__).resolve().parents[2]
LoginScheduler = Callable[[dict[str, Any]], dict[str, Any]]


def login_startup_retire_reason(
    registration: dict[str, Any] | None,
    repo_path: Path,
    output_dir: Path | None = None,
) -> str | None:
    """Return why an enabled on-spec login registration must be retired, or None.

    A registration is retired when the repo it serves no longer exists on
    disk: there is no current location to re-point at, so logon would fire a
    dead launcher. A moved repo still exists at its new location and stays
    with the staleness repair instead.
    """

    if registration is None:
        return None
    if registration.get("enabled") is not True:
        return None
    from blackhole_agent.loop_login_drift import login_startup_drift_reason

    if login_startup_drift_reason(registration) is not None:
        return None
    if not Path(repo_path).is_dir():
        return "repo_deleted"
    return None


def _remove_registration_artifacts(
    repo_path: Path,
    output_dir: Path,
) -> list[str]:
    from blackhole_agent.loop_login_task import (
        login_startup_launcher_path,
        login_startup_registration_path,
        login_startup_task_xml_path,
    )

    removed: list[str] = []
    for path in (
        login_startup_registration_path(repo_path, output_dir),
        login_startup_task_xml_path(repo_path, output_dir),
        login_startup_launcher_path(repo_path, output_dir),
    ):
        if not path.exists():
            continue
        try:
            path.unlink()
        except OSError:
            continue
        removed.append(str(path))
    return removed


def retire_login_startup_registration(
    repo_path: Path,
    output_dir: Path | None = None,
    *,
    scheduler: LoginScheduler | None = None,
) -> dict[str, Any]:
    """Unschedule a logon registration whose repo was deleted.

    This only unschedules. It never starts a controller, and it touches only
    the deleted repo's registration artifacts and scheduler entry, so a live
    owner pid in any surviving repo is never disturbed. A live repo keeps
    its registration untouched.
    """

    from blackhole_agent.loop_login_task import (
        LOGIN_TASK_NAME,
        load_login_startup_registration,
    )
    from blackhole_agent.unbound import DEFAULT_OUTPUT_DIR

    output = DEFAULT_OUTPUT_DIR if output_dir is None else output_dir
    repo = Path(repo_path)
    existing = load_login_startup_registration(repo, output)
    reason = login_startup_retire_reason(existing, repo, output)
    if existing is None and not repo.is_dir():
        reason = "repo_deleted"
    if existing is None:
        if reason is None:
            return {
                "started": False,
                "action": "skip",
                "restore_reason": "not_registered",
                "scheduled": False,
            }
        existing = {}
    if reason is None:
        return {
            **existing,
            "started": False,
            "action": "keep",
            "retire_reason": "repo_alive",
            "scheduled": True,
        }
    removed = _remove_registration_artifacts(repo, output)
    unschedule = {
        **existing,
        "name": str(existing.get("name") or LOGIN_TASK_NAME),
        "repo_path": str(existing.get("repo_path") or repo),
        "action": "unschedule",
        "scheduled": False,
    }
    applied = (
        scheduler(unschedule)
        if scheduler is not None
        else {"backend": "file", "unscheduled": True}
    )
    return {
        **existing,
        **applied,
        "started": False,
        "action": "retire",
        "retire_reason": reason,
        "retired_from": reason,
        "retired": True,
        "scheduled": False,
        "removed": removed,
        "previous_repo_path": existing.get("repo_path"),
        "retired_at": utc_now_iso(),
    }


def loop_login_retire_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.loop_login_retire import "
        "builtin_loop_login_retire_proof; r=builtin_loop_login_retire_proof(); "
        "assert r['ok'] and r.get('action')=='loop_login_retire' "
        "and r.get('passed_count',0) >= 16 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_loop_login_retire_capability(*, repo_path: Path | None = None) -> Capability:
    """Register login-task retirement on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=LOOP_LOGIN_RETIRE_ID,
        name="Continuous-loop login-task retirement",
        description=(
            "A login startup registration whose repo was deleted is "
            "unscheduled so logon stops firing a dead launcher without "
            "disturbing a live owner pid in any surviving repo."
        ),
        kind="python",
        entry="blackhole_agent.loop_login_retire:builtin_loop_login_retire_proof",
        proof_command=loop_login_retire_proof_command(),
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
        ),
        behavior_paths=(
            "src/blackhole_agent/loop_login_retire.py",
            "src/blackhole_agent/loop_login_stale.py",
            "src/blackhole_agent/loop_login_repair.py",
            "src/blackhole_agent/loop_login_task.py",
            "src/blackhole_agent/loop_login_sweep.py",
            "src/blackhole_agent/unbound.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A deleted repo's login registration is unscheduled: logon stops "
            "firing the dead launcher, the scheduler entry and registration "
            "artifacts are removed, and a live owner pid in any surviving "
            "repo is left untouched."
        ),
        tags=("continuous-loop", "login", "startup", "restore", "retire"),
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
            "loop_id": "login-retire-proof",
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

    def __call__(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = str(payload.get("name") or "")
        if payload.get("action") == "unschedule":
            self.tasks.pop(name, None)
            return {"backend": "proof", "unscheduled": True}
        self.tasks[name] = dict(payload)
        return {"backend": "proof", "applied": True}


def builtin_loop_login_retire_proof() -> dict[str, Any]:
    """Hermetic proof: a deleted repo's login registration is unscheduled."""

    import shutil

    from blackhole_agent.evolution_quality import behavior_family
    from blackhole_agent.kernel_genesis_diversify import DIVERSITY_CATALOG
    from blackhole_agent.kernel_leftover import leftover_marker_ids
    from blackhole_agent.loop_login_stale import LOOP_LOGIN_STALE_ID
    from blackhole_agent.loop_login_task import (
        LOGIN_TASK_NAME,
        dispatch_login_startup,
        load_login_startup_registration,
        login_startup_registration_path,
        register_loop_restore_at_login,
    )
    from blackhole_agent.unbound import pid_is_running

    checks: dict[str, bool] = {}
    checks["denylists_self"] = LOOP_LOGIN_RETIRE_ID in LOCAL_DENYLIST
    checks["denylists_next_family"] = LOOP_LOGIN_SWEEP_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(LOOP_LOGIN_RETIRE_GOAL) == (
        LOOP_LOGIN_RETIRE_ID,
    )
    checks["leftover_text_binds_next_family"] = leftover_marker_ids(
        LOOP_LOGIN_SWEEP_LEFTOVER
    ) == (LOOP_LOGIN_SWEEP_ID,)
    checks["next_family_goal_is_login_sweep"] = leftover_marker_ids(LOOP_LOGIN_SWEEP_GOAL) == (
        LOOP_LOGIN_SWEEP_ID,
    )
    checks["prior_family_markers_stay"] = leftover_marker_ids(LOOP_LOGIN_RETIRE_LEFTOVER) == (
        LOOP_LOGIN_RETIRE_ID,
    )
    catalog = DIVERSITY_CATALOG
    checks["catalog_names_login_retire"] = (
        len(catalog) > 246
        and catalog[246]["id"] == LOOP_LOGIN_RETIRE_ID
        and catalog[246]["goal"] == LOOP_LOGIN_RETIRE_GOAL
        and catalog[246]["done_when"] == LOOP_LOGIN_RETIRE_DONE_WHEN
        and catalog[246]["source"] == "genesis_bind_loop_login_retire"
    )
    checks["catalog_names_login_sweep"] = (
        len(catalog) > 247
        and catalog[247]["id"] == LOOP_LOGIN_SWEEP_ID
        and catalog[247]["goal"] == LOOP_LOGIN_SWEEP_GOAL
        and catalog[247]["done_when"] == LOOP_LOGIN_SWEEP_DONE_WHEN
        and catalog[247]["source"] == "genesis_bind_loop_login_sweep"
    )
    checks["login_stale_stays_ahead"] = (
        len(catalog) > 245 and catalog[245]["id"] == LOOP_LOGIN_STALE_ID
    )

    dead_pid = 1_000_131
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

    with tempfile.TemporaryDirectory(prefix="loop-login-retire-scheduler-") as tmp:
        repo = Path(tmp) / "deleted-repo"
        repo.mkdir()
        (repo / "mission.json").write_text('{"status":"active"}\n', encoding="utf-8")
        _seed_orphaned(repo, pid=dead_pid)
        scheduler = _ProofScheduler()
        register_loop_restore_at_login(repo, scheduler=scheduler)
        scheduled_before_delete = dict(scheduler.tasks)
        shutil.rmtree(repo)
        starts_before = len(starts)
        retired = retire_login_startup_registration(repo, scheduler=scheduler)
        again = retire_login_startup_registration(repo, scheduler=scheduler)
        checks["deleted_repo_record_gone_is_unscheduled"] = (
            LOGIN_TASK_NAME in scheduled_before_delete
            and retired.get("started") is False
            and retired.get("action") == "retire"
            and retired.get("retire_reason") == "repo_deleted"
            and retired.get("retired") is True
            and retired.get("scheduled") is False
            and retired.get("unscheduled") is True
            and retired.get("previous_repo_path") is None
            and scheduler.tasks == {}
            and again.get("action") == "retire"
            and again.get("scheduled") is False
            and len(starts) == starts_before
        )

    with tempfile.TemporaryDirectory(prefix="loop-login-retire-durable-") as tmp:
        parent = Path(tmp)
        repo = parent / "deleted-repo"
        repo.mkdir()
        durable = parent / "durable-root"
        (repo / "mission.json").write_text('{"status":"active"}\n', encoding="utf-8")
        _seed_orphaned(repo, pid=dead_pid)
        register_loop_restore_at_login(repo, durable)
        registration_file = login_startup_registration_path(repo, durable)
        recorded_before_delete = registration_file.read_text(encoding="utf-8")
        shutil.rmtree(repo)
        starts_before = len(starts)
        retired = dispatch_login_startup(repo, durable, controller_starter=starter)
        second = dispatch_login_startup(repo, durable, controller_starter=starter)
        checks["deleted_repo_surviving_record_is_retired"] = (
            "BlackholeUnboundLoopRestore" in recorded_before_delete
            and retired.get("started") is False
            and retired.get("action") == "retire"
            and retired.get("restore_reason") == "repo_deleted"
            and retired.get("retired") is True
            and retired.get("scheduled") is False
            and retired.get("dispatched_from") == "login_startup"
            and str(registration_file) in [str(path) for path in retired.get("removed") or []]
            and not registration_file.exists()
            and second.get("started") is False
            and second.get("restore_reason") == "not_registered"
            and second.get("scheduled") is False
            and len(starts) == starts_before
        )

    with tempfile.TemporaryDirectory(prefix="loop-login-retire-live-") as tmp:
        parent = Path(tmp)
        dead_repo = parent / "deleted-repo"
        dead_repo.mkdir()
        dead_durable = parent / "dead-durable"
        (dead_repo / "mission.json").write_text('{"status":"active"}\n', encoding="utf-8")
        _seed_orphaned(dead_repo, pid=dead_pid)
        register_loop_restore_at_login(dead_repo, dead_durable)
        surviving = parent / "surviving-repo"
        surviving.mkdir()
        (surviving / "mission.json").write_text('{"status":"active"}\n', encoding="utf-8")
        state_path = _seed_orphaned(surviving, pid=live_pid, status="running_mission")
        from blackhole_agent.unbound import continuous_loop_lock_path

        continuous_loop_lock_path(surviving).write_text(f"{live_pid}\n", encoding="utf-8")
        register_loop_restore_at_login(surviving)
        surviving_registration = load_login_startup_registration(surviving)
        before = state_path.read_bytes()
        starts_before = len(starts)
        shutil.rmtree(dead_repo)
        retired = retire_login_startup_registration(dead_repo, dead_durable)
        result = dispatch_login_startup(surviving, controller_starter=starter)
        checks["retire_does_not_disturb_surviving_live_owner"] = (
            retired.get("action") == "retire"
            and retired.get("scheduled") is False
            and surviving_registration is not None
            and load_login_startup_registration(surviving) == surviving_registration
            and result.get("started") is False
            and result.get("restore_reason") == "live_owner"
            and result.get("scheduled") is True
            and state_path.read_bytes() == before
            and len(starts) == starts_before
            and pid_is_running(live_pid)
        )

    with tempfile.TemporaryDirectory(prefix="loop-login-retire-keep-") as tmp:
        repo = Path(tmp)
        (repo / "mission.json").write_text('{"status":"active"}\n', encoding="utf-8")
        _seed_orphaned(repo, pid=dead_pid)
        scheduler = _ProofScheduler()
        register_loop_restore_at_login(repo, scheduler=scheduler)
        starts_before = len(starts)
        kept = retire_login_startup_registration(repo, scheduler=scheduler)
        missing = retire_login_startup_registration(repo.parent / "never-existed")
        loaded = load_login_startup_registration(repo)
        checks["live_repo_retire_is_noop"] = (
            kept.get("started") is False
            and kept.get("action") == "keep"
            and kept.get("retire_reason") == "repo_alive"
            and kept.get("scheduled") is True
            and LOGIN_TASK_NAME in scheduler.tasks
            and loaded is not None
            and loaded.get("enabled") is True
            and missing.get("started") is False
            and missing.get("action") == "retire"
            and missing.get("retire_reason") == "repo_deleted"
            and missing.get("scheduled") is False
            and len(starts) == starts_before
        )

    checks["next_family_is_not_handshake"] = (
        behavior_family(LOOP_LOGIN_SWEEP_GOAL) != "network/handshake-digest-demo"
        and LOOP_LOGIN_SWEEP_DONE_WHEN != ""
    )
    checks["contract_is_outcome_level"] = (
        "capability_exists:" not in LOOP_LOGIN_RETIRE_DONE_WHEN
        and "capability_proved:" not in LOOP_LOGIN_RETIRE_DONE_WHEN
    )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_loop_login_retire_capability()
    return {
        "ok": ok,
        "action": "loop_login_retire",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": LOOP_LOGIN_RETIRE_GOAL,
        "done_when": LOOP_LOGIN_RETIRE_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
