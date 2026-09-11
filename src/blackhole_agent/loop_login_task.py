"""Schedule the continuous-loop restore helper at login.

The restore helper already starts a reaped orphan when no live owner pid
exists. This module is the missing enablement path: a login startup
registration points at that helper so logon dispatches it. Registration
never starts a controller. Dispatch refuses to start a second controller
beside a live owner pid because it reuses the restore helper.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Callable
from xml.sax.saxutils import escape

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
from blackhole_agent.loop_login_repair import (
    LOOP_LOGIN_REPAIR_DONE_WHEN,
    LOOP_LOGIN_REPAIR_GOAL,
    LOOP_LOGIN_REPAIR_ID,
    LOOP_LOGIN_REPAIR_LEFTOVER,
)

SCHEMA_VERSION = 1
LOOP_LOGIN_TASK_ID = "capability.loop-login-task"
LOOP_LOGIN_TASK_DONE_WHEN = (
    "A login startup registration schedules the restore helper so an orphaned "
    "loop resumes after login without starting a second controller beside a "
    "live owner pid."
)
LOOP_LOGIN_TASK_GOAL = (
    "Repair login-task enablement: the restore helper exists but is not "
    "scheduled at login, so an operator must still invoke the helper by hand."
)
LOOP_LOGIN_TASK_LEFTOVER = (
    "Later genesis can take login-task enablement so the restore helper is "
    "scheduled at login without an operator invoking it by hand."
)
LOGIN_TASK_NAME = "BlackholeUnboundLoopRestore"
LOGIN_TRIGGER = "at_logon"
RESTORE_HELPER = "blackhole_agent.loop_reboot_restore:restore_orphaned_loop_on_startup"
REGISTRATION_NAME = "login-startup.json"
TASK_XML_NAME = "login-restore-task.xml"
LAUNCHER_NAME = "BlackholeUnboundLoopRestore.py"
REPO_ROOT = Path(__file__).resolve().parents[2]
LoginScheduler = Callable[[dict[str, Any]], dict[str, Any]]
ControllerStarter = Callable[..., dict[str, Any]]


def login_startup_registration_path(repo_path: Path, output_dir: Path | None = None) -> Path:
    from blackhole_agent.unbound import DEFAULT_OUTPUT_DIR, mission_root

    output = DEFAULT_OUTPUT_DIR if output_dir is None else output_dir
    return mission_root(Path(repo_path), output) / REGISTRATION_NAME


def login_startup_task_xml_path(repo_path: Path, output_dir: Path | None = None) -> Path:
    return login_startup_registration_path(repo_path, output_dir).with_name(TASK_XML_NAME)


def login_startup_launcher_path(repo_path: Path, output_dir: Path | None = None) -> Path:
    return login_startup_registration_path(repo_path, output_dir).with_name(LAUNCHER_NAME)


def build_login_restore_command(repo_path: Path, output_dir: Path | None = None) -> list[str]:
    """Argv a logon task runs: the restore helper, not a second controller spawn."""

    from blackhole_agent import unbound
    from blackhole_agent.unbound import DEFAULT_OUTPUT_DIR

    output = DEFAULT_OUTPUT_DIR if output_dir is None else output_dir
    src = Path(unbound.__file__).resolve().parents[1]
    launcher = login_startup_launcher_path(repo_path, output)
    return [sys.executable, "-I", str(launcher)]


def render_login_restore_launcher(repo_path: Path, output_dir: Path) -> str:
    from blackhole_agent import unbound

    src = Path(unbound.__file__).resolve().parents[1]
    return (
        "import sys\n"
        "from pathlib import Path\n"
        f"sys.path.insert(0, {str(src)!r})\n"
        "from blackhole_agent.loop_reboot_restore import restore_orphaned_loop_on_startup\n"
        "result = restore_orphaned_loop_on_startup("
        f"Path({str(Path(repo_path).resolve())!r}), "
        f"Path({str(Path(output_dir).resolve())!r}))\n"
        "raise SystemExit(0 if result.get('restore_reason') != 'start_failed' else 1)\n"
    )


def render_login_restore_task_xml(registration: dict[str, Any]) -> str:
    command = [str(part) for part in registration.get("command") or []]
    executable = command[0] if command else sys.executable
    arguments = " ".join(command[1:])
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">\n'
        f"  <RegistrationInfo><URI>\\{escape(str(registration.get('name') or LOGIN_TASK_NAME))}</URI></RegistrationInfo>\n"
        "  <Triggers>\n"
        "    <LogonTrigger>\n"
        "      <Enabled>true</Enabled>\n"
        "    </LogonTrigger>\n"
        "  </Triggers>\n"
        "  <Principals><Principal id=\"Author\"><LogonType>InteractiveToken</LogonType></Principal></Principals>\n"
        "  <Settings>\n"
        "    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>\n"
        "    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>\n"
        "    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>\n"
        "    <Enabled>true</Enabled>\n"
        "  </Settings>\n"
        "  <Actions Context=\"Author\">\n"
        "    <Exec>\n"
        f"      <Command>{escape(executable)}</Command>\n"
        f"      <Arguments>{escape(arguments)}</Arguments>\n"
        "    </Exec>\n"
        "  </Actions>\n"
        "</Task>\n"
    )


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def build_login_startup_registration(
    repo_path: Path,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    from blackhole_agent.unbound import DEFAULT_OUTPUT_DIR, mission_root

    repo = Path(repo_path).resolve()
    output = DEFAULT_OUTPUT_DIR if output_dir is None else output_dir
    resolved_output = mission_root(repo, output)
    command = build_login_restore_command(repo, output)
    return {
        "schema_version": SCHEMA_VERSION,
        "name": LOGIN_TASK_NAME,
        "trigger": LOGIN_TRIGGER,
        "enabled": True,
        "helper": RESTORE_HELPER,
        "command": command,
        "repo_path": str(repo),
        "output_dir": str(resolved_output),
        "multiple_instances": "ignore_new",
    }


def load_login_startup_registration(
    repo_path: Path,
    output_dir: Path | None = None,
) -> dict[str, Any] | None:
    path = login_startup_registration_path(repo_path, output_dir)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def register_loop_restore_at_login(
    repo_path: Path,
    output_dir: Path | None = None,
    *,
    scheduler: LoginScheduler | None = None,
) -> dict[str, Any]:
    """Create or replace a logon-triggered registration for the restore helper.

    This only schedules. It does not start a controller, so a live owner pid
    is never doubled at enablement time.
    """

    from blackhole_agent.unbound import DEFAULT_OUTPUT_DIR, mission_root

    output = DEFAULT_OUTPUT_DIR if output_dir is None else output_dir
    repo = Path(repo_path)
    resolved_output = mission_root(repo, output)
    spec = build_login_startup_registration(repo, output)
    registration_path = login_startup_registration_path(repo, output)
    xml_path = login_startup_task_xml_path(repo, output)
    launcher_path = login_startup_launcher_path(repo, output)
    _atomic_write(launcher_path, render_login_restore_launcher(repo, resolved_output))
    _atomic_write(xml_path, render_login_restore_task_xml(spec))
    recorded = {
        **spec,
        "registration_path": str(registration_path),
        "task_xml_path": str(xml_path),
        "launcher_path": str(launcher_path),
        "scheduled": True,
        "action": "register",
        "started": False,
        "registered_at": utc_now_iso(),
    }
    _atomic_write(registration_path, json.dumps(recorded, indent=2, sort_keys=True) + "\n")
    applied = scheduler(recorded) if scheduler is not None else {"backend": "file", "applied": True}
    return {**recorded, **applied}


def dispatch_login_startup(
    repo_path: Path,
    output_dir: Path | None = None,
    *,
    controller_starter: ControllerStarter | None = None,
) -> dict[str, Any]:
    """Run the helper the login registration scheduled.

    Missing, disabled, or non-logon registrations are left alone. A live
    owner pid is not doubled because restore_orphaned_loop_on_startup refuses
    to start a second controller.
    """

    from blackhole_agent.loop_reboot_restore import restore_orphaned_loop_on_startup
    from blackhole_agent.unbound import DEFAULT_OUTPUT_DIR

    output = DEFAULT_OUTPUT_DIR if output_dir is None else output_dir
    registration = load_login_startup_registration(repo_path, output)
    if registration is None:
        return {
            "started": False,
            "action": "skip",
            "restore_reason": "not_registered",
            "scheduled": False,
        }
    if registration.get("enabled") is not True:
        return {
            **registration,
            "started": False,
            "action": "skip",
            "restore_reason": "not_enabled",
            "scheduled": False,
        }
    if registration.get("trigger") != LOGIN_TRIGGER:
        return {
            **registration,
            "started": False,
            "action": "skip",
            "restore_reason": "wrong_trigger",
            "scheduled": True,
        }
    if registration.get("helper") != RESTORE_HELPER:
        return {
            **registration,
            "started": False,
            "action": "skip",
            "restore_reason": "wrong_helper",
            "scheduled": True,
        }
    result = restore_orphaned_loop_on_startup(
        repo_path,
        output,
        controller_starter=controller_starter,
    )
    return {
        **result,
        "scheduled": True,
        "login_task": registration.get("name", LOGIN_TASK_NAME),
        "login_trigger": registration.get("trigger", ""),
        "login_helper": registration.get("helper", ""),
        "dispatched_from": "login_startup",
    }


def loop_login_task_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.loop_login_task import "
        "builtin_loop_login_task_proof; r=builtin_loop_login_task_proof(); "
        "assert r['ok'] and r.get('action')=='loop_login_task' "
        "and r.get('passed_count',0) >= 10 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_loop_login_task_capability(*, repo_path: Path | None = None) -> Capability:
    """Register login-task enablement on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=LOOP_LOGIN_TASK_ID,
        name="Continuous-loop login-task enablement",
        description=(
            "A login startup registration schedules the restore helper so an "
            "orphaned loop resumes after login without starting a second "
            "controller beside a live owner pid."
        ),
        kind="python",
        entry="blackhole_agent.loop_login_task:builtin_loop_login_task_proof",
        proof_command=loop_login_task_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.orphan-loop-reap",
            "capability.loop-reboot-restore",
        ),
        behavior_paths=(
            "src/blackhole_agent/loop_login_task.py",
            "src/blackhole_agent/loop_login_repair.py",
            "src/blackhole_agent/unbound.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "Login schedules the restore helper: an orphaned loop resumes after "
            "logon and a live owner pid is not doubled by a second controller."
        ),
        tags=("continuous-loop", "login", "startup", "restore", "schedule"),
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
            "loop_id": "login-task-proof",
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


def builtin_loop_login_task_proof() -> dict[str, Any]:
    """Hermetic proof: login registration schedules restore; live owner is not doubled."""

    from blackhole_agent.evolution_quality import behavior_family
    from blackhole_agent.kernel_genesis_diversify import DIVERSITY_CATALOG
    from blackhole_agent.kernel_leftover import leftover_marker_ids
    from blackhole_agent.loop_reboot_restore import LOOP_REBOOT_RESTORE_ID
    from blackhole_agent.unbound import pid_is_running

    checks: dict[str, bool] = {}
    checks["denylists_self"] = LOOP_LOGIN_TASK_ID in LOCAL_DENYLIST
    checks["denylists_next_family"] = LOOP_LOGIN_REPAIR_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(LOOP_LOGIN_TASK_GOAL) == (
        LOOP_LOGIN_TASK_ID,
    )
    checks["leftover_text_binds_next_family"] = leftover_marker_ids(
        LOOP_LOGIN_REPAIR_LEFTOVER
    ) == (LOOP_LOGIN_REPAIR_ID,)
    checks["next_family_goal_is_login_repair"] = leftover_marker_ids(LOOP_LOGIN_REPAIR_GOAL) == (
        LOOP_LOGIN_REPAIR_ID,
    )
    checks["prior_family_markers_stay"] = leftover_marker_ids(LOOP_LOGIN_TASK_LEFTOVER) == (
        LOOP_LOGIN_TASK_ID,
    )
    catalog = DIVERSITY_CATALOG
    checks["catalog_names_login_task"] = (
        len(catalog) > 242
        and catalog[242]["id"] == LOOP_LOGIN_TASK_ID
        and catalog[242]["goal"] == LOOP_LOGIN_TASK_GOAL
        and catalog[242]["done_when"] == LOOP_LOGIN_TASK_DONE_WHEN
        and catalog[242]["source"] == "genesis_bind_loop_login"
    )
    checks["catalog_names_login_repair"] = (
        len(catalog) > 243
        and catalog[243]["id"] == LOOP_LOGIN_REPAIR_ID
        and catalog[243]["goal"] == LOOP_LOGIN_REPAIR_GOAL
        and catalog[243]["done_when"] == LOOP_LOGIN_REPAIR_DONE_WHEN
        and catalog[243]["source"] == "genesis_bind_loop_login_repair"
    )
    checks["restore_stays_ahead"] = (
        len(catalog) > 241 and catalog[241]["id"] == LOOP_REBOOT_RESTORE_ID
    )

    dead_pid = 1_000_041
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

    with tempfile.TemporaryDirectory(prefix="loop-login-task-orphan-") as tmp:
        repo = Path(tmp)
        (repo / "mission.json").write_text('{"status":"active"}\n', encoding="utf-8")
        _seed_orphaned(repo, pid=dead_pid)
        unregistered = dispatch_login_startup(repo, controller_starter=starter)
        unregistered_starts = list(starts)
        applied: list[str] = []

        def scheduler(registration: dict[str, Any]) -> dict[str, Any]:
            applied.append(str(registration.get("name") or ""))
            return {"backend": "proof", "applied": True}

        registered = register_loop_restore_at_login(repo, scheduler=scheduler)
        xml_text = Path(registered["task_xml_path"]).read_text(encoding="utf-8")
        launcher = Path(registered["launcher_path"]).read_text(encoding="utf-8")
        first = dispatch_login_startup(repo, controller_starter=starter)
        second = dispatch_login_startup(repo, controller_starter=starter)
        checks["unregistered_login_does_not_start"] = (
            unregistered.get("started") is False
            and unregistered.get("restore_reason") == "not_registered"
            and unregistered_starts == []
        )
        checks["registration_schedules_restore_at_logon"] = (
            registered.get("scheduled") is True
            and registered.get("started") is False
            and registered.get("trigger") == LOGIN_TRIGGER
            and registered.get("helper") == RESTORE_HELPER
            and registered.get("enabled") is True
            and RESTORE_HELPER.split(":")[-1] in launcher
            and "<LogonTrigger>" in xml_text
            and "IgnoreNew" in xml_text
            and applied == [LOGIN_TASK_NAME]
        )
        checks["login_restores_orphan_once"] = (
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

    with tempfile.TemporaryDirectory(prefix="loop-login-task-live-") as tmp:
        repo = Path(tmp)
        path = _seed_orphaned(repo, pid=live_pid, status="running_mission")
        from blackhole_agent.unbound import continuous_loop_lock_path

        continuous_loop_lock_path(repo).write_text(f"{live_pid}\n", encoding="utf-8")
        register_loop_restore_at_login(repo)
        before = path.read_bytes()
        starts_before = len(starts)
        result = dispatch_login_startup(repo, controller_starter=starter)
        checks["login_does_not_double_live_owner"] = (
            result.get("started") is False
            and result.get("restore_reason") == "live_owner"
            and result.get("scheduled") is True
            and path.read_bytes() == before
            and len(starts) == starts_before
        )

    checks["next_family_is_not_handshake"] = (
        behavior_family(LOOP_LOGIN_REPAIR_GOAL) != "network/handshake-digest-demo"
        and LOOP_LOGIN_REPAIR_DONE_WHEN != ""
    )
    checks["contract_is_outcome_level"] = (
        "capability_exists:" not in LOOP_LOGIN_TASK_DONE_WHEN
        and "capability_proved:" not in LOOP_LOGIN_TASK_DONE_WHEN
    )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_loop_login_task_capability()
    return {
        "ok": ok,
        "action": "loop_login_task",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": LOOP_LOGIN_TASK_GOAL,
        "done_when": LOOP_LOGIN_TASK_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
