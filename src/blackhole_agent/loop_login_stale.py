"""Repair a stale login startup registration.

Login-task drift repair can rewrite a wrong trigger or helper, but a
registration whose command or launcher points at a moved repo stays broken
until an operator re-points it by hand. This helper re-points that stale
registration so the restore helper is scheduled again. Repair never starts
a controller, so a live owner pid is not doubled. Dispatch still refuses a
second controller because it reuses the restore helper.
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
from blackhole_agent.loop_login_retire import (
    LOOP_LOGIN_RETIRE_DONE_WHEN,
    LOOP_LOGIN_RETIRE_GOAL,
    LOOP_LOGIN_RETIRE_ID,
    LOOP_LOGIN_RETIRE_LEFTOVER,
)

SCHEMA_VERSION = 1
LOOP_LOGIN_STALE_ID = "capability.loop-login-stale"
LOOP_LOGIN_STALE_DONE_WHEN = (
    "A stale login startup registration whose command or launcher points at "
    "a moved repo is repaired so the restore helper is scheduled again "
    "without starting a second controller beside a live owner pid."
)
LOOP_LOGIN_STALE_GOAL = (
    "Repair login-task staleness: a registration whose command or launcher "
    "points at a moved repo stays broken until an operator re-points it by "
    "hand."
)
LOOP_LOGIN_STALE_LEFTOVER = (
    "Later genesis can take login-task staleness so a stale command or "
    "launcher is re-pointed without an operator re-pointing it by hand."
)
REPO_ROOT = Path(__file__).resolve().parents[2]
LoginScheduler = Callable[[dict[str, Any]], dict[str, Any]]


def login_startup_stale_reason(
    registration: dict[str, Any] | None,
    repo_path: Path,
    output_dir: Path | None = None,
) -> str | None:
    """Return why an enabled on-spec login registration is stale, or None.

    A registration is stale when its recorded command argv or repo path
    still points at the location the repo had at registration time, or when
    the launcher script still embeds that moved location.
    """

    if registration is None:
        return None
    if registration.get("enabled") is not True:
        return None
    from blackhole_agent.loop_login_drift import login_startup_drift_reason

    if login_startup_drift_reason(registration) is not None:
        return None
    from blackhole_agent.loop_login_task import (
        build_login_restore_command,
        login_startup_launcher_path,
        render_login_restore_launcher,
    )
    from blackhole_agent.unbound import DEFAULT_OUTPUT_DIR, mission_root

    repo = Path(repo_path).resolve()
    output = DEFAULT_OUTPUT_DIR if output_dir is None else output_dir
    recorded_command = [str(part) for part in registration.get("command") or []]
    expected_command = [str(part) for part in build_login_restore_command(repo, output)]
    if recorded_command != expected_command:
        return "stale_command"
    if str(registration.get("repo_path") or "") != str(repo):
        return "stale_command"
    launcher_path = login_startup_launcher_path(repo, output)
    try:
        content = launcher_path.read_text(encoding="utf-8")
    except OSError:
        return "stale_launcher"
    if content != render_login_restore_launcher(repo, mission_root(repo, output)):
        return "stale_launcher"
    return None


def repair_login_startup_stale(
    repo_path: Path,
    output_dir: Path | None = None,
    *,
    scheduler: LoginScheduler | None = None,
) -> dict[str, Any]:
    """Re-point a stale logon registration at the current repo location.

    This only schedules. It does not start a controller, so a live owner pid
    is never doubled at repair time. Missing, disabled, or drifted
    registrations fall through to the drift repair.
    """

    from blackhole_agent.loop_login_drift import repair_login_startup_drift
    from blackhole_agent.loop_login_task import load_login_startup_registration
    from blackhole_agent.unbound import DEFAULT_OUTPUT_DIR

    output = DEFAULT_OUTPUT_DIR if output_dir is None else output_dir
    existing = load_login_startup_registration(repo_path, output)
    reason = login_startup_stale_reason(existing, repo_path, output)
    repaired = repair_login_startup_drift(repo_path, output, scheduler=scheduler)
    if reason is None:
        return repaired
    return {
        **repaired,
        "action": "repair",
        "repair_reason": reason,
        "repaired_from": reason,
        "stale_repair": True,
        "previous_command": None if existing is None else existing.get("command"),
        "previous_repo_path": None if existing is None else existing.get("repo_path"),
    }


def loop_login_stale_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.loop_login_stale import "
        "builtin_loop_login_stale_proof; r=builtin_loop_login_stale_proof(); "
        "assert r['ok'] and r.get('action')=='loop_login_stale' "
        "and r.get('passed_count',0) >= 16 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_loop_login_stale_capability(*, repo_path: Path | None = None) -> Capability:
    """Register login-task staleness repair on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=LOOP_LOGIN_STALE_ID,
        name="Continuous-loop login-task staleness repair",
        description=(
            "A stale login startup registration whose command or launcher "
            "points at a moved repo is repaired so the restore helper is "
            "scheduled again without starting a second controller beside a "
            "live owner pid."
        ),
        kind="python",
        entry="blackhole_agent.loop_login_stale:builtin_loop_login_stale_proof",
        proof_command=loop_login_stale_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.orphan-loop-reap",
            "capability.loop-reboot-restore",
            "capability.loop-login-task",
            "capability.loop-login-repair",
            "capability.loop-login-drift",
        ),
        behavior_paths=(
            "src/blackhole_agent/loop_login_stale.py",
            "src/blackhole_agent/loop_login_drift.py",
            "src/blackhole_agent/loop_login_repair.py",
            "src/blackhole_agent/loop_login_task.py",
            "src/blackhole_agent/loop_login_retire.py",
            "src/blackhole_agent/unbound.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A stale login registration is re-pointed: a command or launcher "
            "that still targets the repo's old location is rewritten at the "
            "current path and a live owner pid is not doubled by a second "
            "controller."
        ),
        tags=("continuous-loop", "login", "startup", "restore", "stale", "repair"),
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
            "loop_id": "login-stale-proof",
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


def _stale_login_registration(repo: Path, **changes: Any) -> dict[str, Any]:
    import json

    from blackhole_agent.loop_login_task import login_startup_registration_path

    path = login_startup_registration_path(repo)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.update(changes)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def builtin_loop_login_stale_proof() -> dict[str, Any]:
    """Hermetic proof: stale login is re-pointed; live owner is not doubled."""

    from blackhole_agent.evolution_quality import behavior_family
    from blackhole_agent.kernel_genesis_diversify import DIVERSITY_CATALOG
    from blackhole_agent.kernel_leftover import leftover_marker_ids
    from blackhole_agent.loop_login_drift import LOOP_LOGIN_DRIFT_ID
    from blackhole_agent.loop_login_task import (
        LOGIN_TRIGGER,
        RESTORE_HELPER,
        build_login_restore_command,
        dispatch_login_startup,
        load_login_startup_registration,
        login_startup_launcher_path,
        login_startup_registration_path,
        login_startup_task_xml_path,
        register_loop_restore_at_login,
        render_login_restore_launcher,
    )
    from blackhole_agent.unbound import mission_root, pid_is_running

    checks: dict[str, bool] = {}
    checks["denylists_self"] = LOOP_LOGIN_STALE_ID in LOCAL_DENYLIST
    checks["denylists_next_family"] = LOOP_LOGIN_RETIRE_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(LOOP_LOGIN_STALE_GOAL) == (
        LOOP_LOGIN_STALE_ID,
    )
    checks["leftover_text_binds_next_family"] = leftover_marker_ids(
        LOOP_LOGIN_RETIRE_LEFTOVER
    ) == (LOOP_LOGIN_RETIRE_ID,)
    checks["next_family_goal_is_login_retire"] = leftover_marker_ids(LOOP_LOGIN_RETIRE_GOAL) == (
        LOOP_LOGIN_RETIRE_ID,
    )
    checks["prior_family_markers_stay"] = leftover_marker_ids(LOOP_LOGIN_STALE_LEFTOVER) == (
        LOOP_LOGIN_STALE_ID,
    )
    catalog = DIVERSITY_CATALOG
    checks["catalog_names_login_stale"] = (
        len(catalog) > 245
        and catalog[245]["id"] == LOOP_LOGIN_STALE_ID
        and catalog[245]["goal"] == LOOP_LOGIN_STALE_GOAL
        and catalog[245]["done_when"] == LOOP_LOGIN_STALE_DONE_WHEN
        and catalog[245]["source"] == "genesis_bind_loop_login_stale"
    )
    checks["catalog_names_login_retire"] = (
        len(catalog) > 246
        and catalog[246]["id"] == LOOP_LOGIN_RETIRE_ID
        and catalog[246]["goal"] == LOOP_LOGIN_RETIRE_GOAL
        and catalog[246]["done_when"] == LOOP_LOGIN_RETIRE_DONE_WHEN
        and catalog[246]["source"] == "genesis_bind_loop_login_retire"
    )
    checks["login_drift_stays_ahead"] = (
        len(catalog) > 244 and catalog[244]["id"] == LOOP_LOGIN_DRIFT_ID
    )

    dead_pid = 1_000_111
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

    with tempfile.TemporaryDirectory(prefix="loop-login-stale-command-") as tmp:
        parent = Path(tmp)
        repo = parent / "before-move"
        repo.mkdir()
        (repo / "mission.json").write_text('{"status":"active"}\n', encoding="utf-8")
        _seed_orphaned(repo, pid=dead_pid)
        register_loop_restore_at_login(repo)
        moved = parent / "after-move"
        repo.rename(moved)
        repo = moved
        stale_dispatch = dispatch_login_startup(repo, controller_starter=starter)
        starts_before_repair = list(starts)
        applied: list[str] = []

        def scheduler(registration: dict[str, Any]) -> dict[str, Any]:
            applied.append(str(registration.get("name") or ""))
            return {"backend": "proof", "applied": True}

        repaired = repair_login_startup_stale(repo, scheduler=scheduler)
        already = repair_login_startup_stale(repo, scheduler=scheduler)
        xml_text = login_startup_task_xml_path(repo).read_text(encoding="utf-8")
        launcher = login_startup_launcher_path(repo).read_text(encoding="utf-8")
        loaded = load_login_startup_registration(repo)
        first = dispatch_login_startup(repo, controller_starter=starter)
        second = dispatch_login_startup(repo, controller_starter=starter)
        checks["stale_command_is_repaired_without_start"] = (
            stale_dispatch.get("started") is False
            and stale_dispatch.get("restore_reason") == "stale_command"
            and starts_before_repair == []
            and repaired.get("started") is False
            and repaired.get("action") == "repair"
            and repaired.get("repair_reason") == "stale_command"
            and repaired.get("stale_repair") is True
            and repaired.get("scheduled") is True
            and repaired.get("trigger") == LOGIN_TRIGGER
            and repaired.get("helper") == RESTORE_HELPER
            and [str(part) for part in repaired.get("command") or []]
            == [str(part) for part in build_login_restore_command(repo)]
            and str(repaired.get("previous_repo_path") or "").endswith("before-move")
            and loaded is not None
            and loaded.get("repo_path") == str(repo.resolve())
            and loaded.get("trigger") == LOGIN_TRIGGER
            and loaded.get("helper") == RESTORE_HELPER
            and loaded.get("enabled") is True
            and launcher == render_login_restore_launcher(repo, mission_root(repo))
            and "<LogonTrigger>" in xml_text
            and "IgnoreNew" in xml_text
            and applied == ["BlackholeUnboundLoopRestore"]
        )
        checks["already_repaired_is_noop"] = (
            already.get("action") == "already_scheduled"
            and already.get("started") is False
            and already.get("scheduled") is True
            and applied == ["BlackholeUnboundLoopRestore"]
        )
        checks["repaired_stale_restores_orphan_once"] = (
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

    with tempfile.TemporaryDirectory(prefix="loop-login-stale-launcher-") as tmp:
        repo = Path(tmp)
        (repo / "mission.json").write_text('{"status":"active"}\n', encoding="utf-8")
        _seed_orphaned(repo, pid=dead_pid)
        register_loop_restore_at_login(repo)
        launcher_path = login_startup_launcher_path(repo)
        launcher_path.write_text(
            render_login_restore_launcher(repo.parent / "moved-away", mission_root(repo)),
            encoding="utf-8",
        )
        stale_dispatch = dispatch_login_startup(repo, controller_starter=starter)
        starts_before = len(starts)
        repaired = repair_login_startup_stale(repo)
        loaded = load_login_startup_registration(repo)
        checks["stale_launcher_is_repaired_without_start"] = (
            stale_dispatch.get("started") is False
            and stale_dispatch.get("restore_reason") == "stale_launcher"
            and repaired.get("started") is False
            and repaired.get("action") == "repair"
            and repaired.get("repair_reason") == "stale_launcher"
            and repaired.get("stale_repair") is True
            and repaired.get("scheduled") is True
            and loaded is not None
            and loaded.get("helper") == RESTORE_HELPER
            and loaded.get("enabled") is True
            and launcher_path.read_text(encoding="utf-8")
            == render_login_restore_launcher(repo, mission_root(repo))
            and login_startup_registration_path(repo).is_file()
            and len(starts) == starts_before
        )

    with tempfile.TemporaryDirectory(prefix="loop-login-stale-live-") as tmp:
        repo = Path(tmp)
        path = _seed_orphaned(repo, pid=live_pid, status="running_mission")
        from blackhole_agent.unbound import continuous_loop_lock_path

        continuous_loop_lock_path(repo).write_text(f"{live_pid}\n", encoding="utf-8")
        register_loop_restore_at_login(repo)
        moved_repo = repo.parent / f"{repo.name}-moved"
        _stale_login_registration(
            repo,
            command=[
                str(part)
                for part in build_login_restore_command(moved_repo)
            ],
            repo_path=str(moved_repo.resolve()),
        )
        before = path.read_bytes()
        starts_before = len(starts)
        stale_dispatch = dispatch_login_startup(repo, controller_starter=starter)
        repaired = repair_login_startup_stale(repo)
        result = dispatch_login_startup(repo, controller_starter=starter)
        checks["stale_repair_does_not_double_live_owner"] = (
            stale_dispatch.get("started") is False
            and stale_dispatch.get("restore_reason") == "stale_command"
            and repaired.get("started") is False
            and repaired.get("repair_reason") == "stale_command"
            and repaired.get("scheduled") is True
            and result.get("started") is False
            and result.get("restore_reason") == "live_owner"
            and result.get("scheduled") is True
            and path.read_bytes() == before
            and len(starts) == starts_before
        )

    with tempfile.TemporaryDirectory(prefix="loop-login-stale-missing-") as tmp:
        repo = Path(tmp)
        (repo / "mission.json").write_text('{"status":"active"}\n', encoding="utf-8")
        _seed_orphaned(repo, pid=dead_pid)
        starts_before = len(starts)
        repaired = repair_login_startup_stale(repo)
        loaded = load_login_startup_registration(repo)
        checks["missing_registration_falls_through_to_repair"] = (
            repaired.get("started") is False
            and repaired.get("action") == "repair"
            and repaired.get("repair_reason") == "missing"
            and "stale_repair" not in repaired
            and repaired.get("scheduled") is True
            and loaded is not None
            and loaded.get("trigger") == LOGIN_TRIGGER
            and loaded.get("helper") == RESTORE_HELPER
            and len(starts) == starts_before
        )

    checks["next_family_is_not_handshake"] = (
        behavior_family(LOOP_LOGIN_RETIRE_GOAL) != "network/handshake-digest-demo"
        and LOOP_LOGIN_RETIRE_DONE_WHEN != ""
    )
    checks["contract_is_outcome_level"] = (
        "capability_exists:" not in LOOP_LOGIN_STALE_DONE_WHEN
        and "capability_proved:" not in LOOP_LOGIN_STALE_DONE_WHEN
    )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_loop_login_stale_capability()
    return {
        "ok": ok,
        "action": "loop_login_stale",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": LOOP_LOGIN_STALE_GOAL,
        "done_when": LOOP_LOGIN_STALE_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
