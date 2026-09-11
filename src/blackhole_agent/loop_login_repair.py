"""Repair a missing, disabled, drifted, or stale login startup registration.

Login-task enablement can schedule the restore helper, but a deleted,
disabled, drifted, or stale registration stays broken. This helper rewrites
that registration so the restore helper is scheduled again; a registration
whose repo was deleted is retired instead of recreated. Repair never starts
a controller, so a live owner pid is not doubled. Dispatch still refuses a
second controller because it reuses the restore helper.
"""

from __future__ import annotations

import json
import os
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
from blackhole_agent.loop_login_drift import (
    LOOP_LOGIN_DRIFT_DONE_WHEN,
    LOOP_LOGIN_DRIFT_GOAL,
    LOOP_LOGIN_DRIFT_ID,
    LOOP_LOGIN_DRIFT_LEFTOVER,
)

SCHEMA_VERSION = 1
LOOP_LOGIN_REPAIR_ID = "capability.loop-login-repair"
LOOP_LOGIN_REPAIR_DONE_WHEN = (
    "A missing or disabled login startup registration is repaired so the "
    "restore helper is scheduled again without starting a second controller "
    "beside a live owner pid."
)
LOOP_LOGIN_REPAIR_GOAL = (
    "Repair login-task durability: a missing or disabled login registration "
    "stays gone until an operator re-registers it by hand."
)
LOOP_LOGIN_REPAIR_LEFTOVER = (
    "Later genesis can take login-task repair so a missing or disabled login "
    "registration is restored without an operator re-registering it by hand."
)
REPO_ROOT = Path(__file__).resolve().parents[2]
LoginScheduler = Callable[[dict[str, Any]], dict[str, Any]]
ControllerStarter = Callable[..., dict[str, Any]]


def login_startup_repair_reason(registration: dict[str, Any] | None) -> str | None:
    """Return why the login registration needs repair, or None when healthy."""

    if registration is None:
        return "missing"
    if registration.get("enabled") is not True:
        return "disabled"
    from blackhole_agent.loop_login_drift import login_startup_drift_reason

    return login_startup_drift_reason(registration)


def repair_login_startup_registration(
    repo_path: Path,
    output_dir: Path | None = None,
    *,
    scheduler: LoginScheduler | None = None,
) -> dict[str, Any]:
    """Recreate a missing, disabled, drifted, or stale logon registration for the helper.

    This only schedules. It does not start a controller, so a live owner pid
    is never doubled at repair time. A repo that was deleted is retired
    instead of recreated.
    """

    from blackhole_agent.loop_login_task import (
        load_login_startup_registration,
        register_loop_restore_at_login,
    )
    from blackhole_agent.unbound import DEFAULT_OUTPUT_DIR

    output = DEFAULT_OUTPUT_DIR if output_dir is None else output_dir
    if not Path(repo_path).is_dir():
        from blackhole_agent.loop_login_retire import retire_login_startup_registration

        return retire_login_startup_registration(repo_path, output, scheduler=scheduler)
    existing = load_login_startup_registration(repo_path, output)
    reason = login_startup_repair_reason(existing)
    if reason is None:
        from blackhole_agent.loop_login_stale import login_startup_stale_reason

        reason = login_startup_stale_reason(existing, repo_path, output)
    if reason is None:
        return {
            **existing,
            "started": False,
            "action": "already_scheduled",
            "repair_reason": "already_scheduled",
            "scheduled": True,
        }
    registered = register_loop_restore_at_login(repo_path, output, scheduler=scheduler)
    return {
        **registered,
        "started": False,
        "action": "repair",
        "repair_reason": reason,
        "scheduled": True,
        "repaired_from": reason,
        "previous_enabled": None if existing is None else existing.get("enabled"),
        "previous_trigger": None if existing is None else existing.get("trigger"),
        "previous_helper": None if existing is None else existing.get("helper"),
        "previous_command": None if existing is None else existing.get("command"),
        "previous_repo_path": None if existing is None else existing.get("repo_path"),
    }


def loop_login_repair_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.loop_login_repair import "
        "builtin_loop_login_repair_proof; r=builtin_loop_login_repair_proof(); "
        "assert r['ok'] and r.get('action')=='loop_login_repair' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_loop_login_repair_capability(*, repo_path: Path | None = None) -> Capability:
    """Register login-task repair on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=LOOP_LOGIN_REPAIR_ID,
        name="Continuous-loop login-task repair",
        description=(
            "A missing or disabled login startup registration is repaired so "
            "the restore helper is scheduled again without starting a second "
            "controller beside a live owner pid."
        ),
        kind="python",
        entry="blackhole_agent.loop_login_repair:builtin_loop_login_repair_proof",
        proof_command=loop_login_repair_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.orphan-loop-reap",
            "capability.loop-reboot-restore",
            "capability.loop-login-task",
        ),
        behavior_paths=(
            "src/blackhole_agent/loop_login_repair.py",
            "src/blackhole_agent/loop_login_drift.py",
            "src/blackhole_agent/loop_login_task.py",
            "src/blackhole_agent/unbound.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A missing or disabled login registration is rewritten: the restore "
            "helper is scheduled again and a live owner pid is not doubled by a "
            "second controller."
        ),
        tags=("continuous-loop", "login", "startup", "restore", "repair"),
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
            "loop_id": "login-repair-proof",
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


def _disable_login_registration(repo: Path) -> dict[str, Any]:
    from blackhole_agent.loop_login_task import login_startup_registration_path

    path = login_startup_registration_path(repo)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["enabled"] = False
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def builtin_loop_login_repair_proof() -> dict[str, Any]:
    """Hermetic proof: missing/disabled login is repaired; live owner is not doubled."""

    from blackhole_agent.evolution_quality import behavior_family
    from blackhole_agent.kernel_genesis_diversify import DIVERSITY_CATALOG
    from blackhole_agent.kernel_leftover import leftover_marker_ids
    from blackhole_agent.loop_login_task import (
        LOOP_LOGIN_TASK_ID,
        LOGIN_TRIGGER,
        RESTORE_HELPER,
        dispatch_login_startup,
        load_login_startup_registration,
        login_startup_launcher_path,
        login_startup_registration_path,
        login_startup_task_xml_path,
        register_loop_restore_at_login,
    )
    from blackhole_agent.unbound import pid_is_running

    checks: dict[str, bool] = {}
    checks["denylists_self"] = LOOP_LOGIN_REPAIR_ID in LOCAL_DENYLIST
    checks["denylists_next_family"] = LOOP_LOGIN_DRIFT_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(LOOP_LOGIN_REPAIR_GOAL) == (
        LOOP_LOGIN_REPAIR_ID,
    )
    checks["leftover_text_binds_next_family"] = leftover_marker_ids(
        LOOP_LOGIN_DRIFT_LEFTOVER
    ) == (LOOP_LOGIN_DRIFT_ID,)
    checks["next_family_goal_is_login_drift"] = leftover_marker_ids(LOOP_LOGIN_DRIFT_GOAL) == (
        LOOP_LOGIN_DRIFT_ID,
    )
    checks["prior_family_markers_stay"] = leftover_marker_ids(LOOP_LOGIN_REPAIR_LEFTOVER) == (
        LOOP_LOGIN_REPAIR_ID,
    )
    catalog = DIVERSITY_CATALOG
    checks["catalog_names_login_repair"] = (
        len(catalog) > 243
        and catalog[243]["id"] == LOOP_LOGIN_REPAIR_ID
        and catalog[243]["goal"] == LOOP_LOGIN_REPAIR_GOAL
        and catalog[243]["done_when"] == LOOP_LOGIN_REPAIR_DONE_WHEN
        and catalog[243]["source"] == "genesis_bind_loop_login_repair"
    )
    checks["catalog_names_login_drift"] = (
        len(catalog) > 244
        and catalog[244]["id"] == LOOP_LOGIN_DRIFT_ID
        and catalog[244]["goal"] == LOOP_LOGIN_DRIFT_GOAL
        and catalog[244]["done_when"] == LOOP_LOGIN_DRIFT_DONE_WHEN
        and catalog[244]["source"] == "genesis_bind_loop_login_drift"
    )
    checks["login_task_stays_ahead"] = (
        len(catalog) > 242 and catalog[242]["id"] == LOOP_LOGIN_TASK_ID
    )

    dead_pid = 1_000_071
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

    import tempfile

    with tempfile.TemporaryDirectory(prefix="loop-login-repair-missing-") as tmp:
        repo = Path(tmp)
        (repo / "mission.json").write_text('{"status":"active"}\n', encoding="utf-8")
        _seed_orphaned(repo, pid=dead_pid)
        missing_dispatch = dispatch_login_startup(repo, controller_starter=starter)
        starts_before_repair = list(starts)
        applied: list[str] = []

        def scheduler(registration: dict[str, Any]) -> dict[str, Any]:
            applied.append(str(registration.get("name") or ""))
            return {"backend": "proof", "applied": True}

        repaired = repair_login_startup_registration(repo, scheduler=scheduler)
        already = repair_login_startup_registration(repo, scheduler=scheduler)
        xml_text = login_startup_task_xml_path(repo).read_text(encoding="utf-8")
        launcher = login_startup_launcher_path(repo).read_text(encoding="utf-8")
        loaded = load_login_startup_registration(repo)
        first = dispatch_login_startup(repo, controller_starter=starter)
        second = dispatch_login_startup(repo, controller_starter=starter)
        checks["missing_registration_is_repaired_without_start"] = (
            missing_dispatch.get("started") is False
            and missing_dispatch.get("restore_reason") == "not_registered"
            and starts_before_repair == []
            and repaired.get("started") is False
            and repaired.get("action") == "repair"
            and repaired.get("repair_reason") == "missing"
            and repaired.get("scheduled") is True
            and repaired.get("trigger") == LOGIN_TRIGGER
            and repaired.get("helper") == RESTORE_HELPER
            and repaired.get("enabled") is True
            and loaded is not None
            and loaded.get("enabled") is True
            and RESTORE_HELPER.split(":")[-1] in launcher
            and "<LogonTrigger>" in xml_text
            and "IgnoreNew" in xml_text
            and applied == ["BlackholeUnboundLoopRestore"]
        )
        checks["already_scheduled_is_noop"] = (
            already.get("action") == "already_scheduled"
            and already.get("started") is False
            and already.get("scheduled") is True
            and applied == ["BlackholeUnboundLoopRestore"]
        )
        checks["repaired_login_restores_orphan_once"] = (
            first.get("started") is True
            and first.get("action") == "restore"
            and first.get("restore_reason") == "orphaned_no_live_owner"
            and first.get("dispatched_from") == "login_startup"
            and first.get("restored_pid") == live_pid
            and first.get("previous_pid") == dead_pid
            and second.get("started") is False
            and second.get("restore_reason") == "live_owner"
            and len(starts) == 1
        )

    with tempfile.TemporaryDirectory(prefix="loop-login-repair-disabled-") as tmp:
        repo = Path(tmp)
        (repo / "mission.json").write_text('{"status":"active"}\n', encoding="utf-8")
        _seed_orphaned(repo, pid=dead_pid)
        register_loop_restore_at_login(repo)
        _disable_login_registration(repo)
        disabled_dispatch = dispatch_login_startup(repo, controller_starter=starter)
        starts_before = len(starts)
        repaired = repair_login_startup_registration(repo)
        loaded = load_login_startup_registration(repo)
        checks["disabled_registration_is_repaired_without_start"] = (
            disabled_dispatch.get("started") is False
            and disabled_dispatch.get("restore_reason") == "not_enabled"
            and repaired.get("started") is False
            and repaired.get("action") == "repair"
            and repaired.get("repair_reason") == "disabled"
            and repaired.get("scheduled") is True
            and repaired.get("enabled") is True
            and loaded is not None
            and loaded.get("enabled") is True
            and login_startup_registration_path(repo).is_file()
            and len(starts) == starts_before
        )

    with tempfile.TemporaryDirectory(prefix="loop-login-repair-live-") as tmp:
        repo = Path(tmp)
        path = _seed_orphaned(repo, pid=live_pid, status="running_mission")
        from blackhole_agent.unbound import continuous_loop_lock_path

        continuous_loop_lock_path(repo).write_text(f"{live_pid}\n", encoding="utf-8")
        login_startup_registration_path(repo).unlink(missing_ok=True)
        before = path.read_bytes()
        starts_before = len(starts)
        repaired = repair_login_startup_registration(repo)
        result = dispatch_login_startup(repo, controller_starter=starter)
        checks["repair_does_not_double_live_owner"] = (
            repaired.get("started") is False
            and repaired.get("repair_reason") == "missing"
            and repaired.get("scheduled") is True
            and result.get("started") is False
            and result.get("restore_reason") == "live_owner"
            and result.get("scheduled") is True
            and path.read_bytes() == before
            and len(starts) == starts_before
        )

    checks["next_family_is_not_handshake"] = (
        behavior_family(LOOP_LOGIN_DRIFT_GOAL) != "network/handshake-digest-demo"
        and LOOP_LOGIN_DRIFT_DONE_WHEN != ""
    )
    checks["contract_is_outcome_level"] = (
        "capability_exists:" not in LOOP_LOGIN_REPAIR_DONE_WHEN
        and "capability_proved:" not in LOOP_LOGIN_REPAIR_DONE_WHEN
    )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_loop_login_repair_capability()
    return {
        "ok": ok,
        "action": "loop_login_repair",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": LOOP_LOGIN_REPAIR_GOAL,
        "done_when": LOOP_LOGIN_REPAIR_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
