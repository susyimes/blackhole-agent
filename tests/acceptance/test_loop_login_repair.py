"""Acceptance probe: a missing or disabled login registration is repaired.

The repair schedules the restore helper again without starting a second
controller beside a live owner pid. Prints JSON with boolean passed and
nonempty observed. Exits 0 for both met and unmet outcomes so the
controller can replay the same probe on baseline and candidate source
trees.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

observed: dict[str, object] = {"family": "loop-login-repair"}
passed = False

try:
    from blackhole_agent.loop_login_repair import repair_login_startup_registration
    from blackhole_agent.loop_login_task import (
        dispatch_login_startup,
        load_login_startup_registration,
        login_startup_launcher_path,
        login_startup_registration_path,
        login_startup_task_xml_path,
        register_loop_restore_at_login,
    )
    from blackhole_agent.unbound import (
        continuous_loop_lock_path,
        continuous_loop_state_path,
        pid_is_running,
        save_continuous_loop_state,
    )
except Exception as error:  # pragma: no cover - baseline missing login repair
    observed["error"] = type(error).__name__
    observed["detail"] = str(error)
    print(json.dumps({"passed": False, "observed": observed}, sort_keys=True))
    raise SystemExit(0)


def _seed_orphaned(repo: Path, *, pid: int, status: str = "orphaned") -> Path:
    path = continuous_loop_state_path(repo)
    save_continuous_loop_state(
        path,
        {
            "loop_id": "acceptance-login-repair",
            "status": status,
            "pid": pid,
            "orphaned_from_status": "running_mission" if status == "orphaned" else "",
            "current_mission_id": "unfinished-mission",
            "current_state_path": str(repo / "mission.json"),
            "last_error": "retained diagnostic",
            "stop_reason": "controller_process_missing" if status == "orphaned" else "operator_stop",
        },
    )
    return path


try:
    dead_pid = 1_000_097
    while pid_is_running(dead_pid):
        dead_pid += 2
    live_pid = os.getpid()
    starts: list[int] = []

    def starter(repo: Path, output_dir=None, payload=None):
        pid = os.getpid()
        starts.append(pid)
        save_continuous_loop_state(
            continuous_loop_state_path(repo),
            {**(payload or {}), "status": "running_mission", "pid": pid, "stop_reason": ""},
        )
        return {"started": True, "pid": pid}

    missing_ok = False
    disabled_ok = False
    live_ok = False

    with tempfile.TemporaryDirectory(prefix="accept-login-repair-missing-", ignore_cleanup_errors=True) as tmp:
        repo = Path(tmp)
        (repo / "mission.json").write_text('{"status":"active"}\n', encoding="utf-8")
        _seed_orphaned(repo, pid=dead_pid)
        before = dispatch_login_startup(repo, controller_starter=starter)
        starts_at_repair = len(starts)
        repaired = repair_login_startup_registration(repo)
        no_start_at_repair = len(starts) == starts_at_repair
        spec = load_login_startup_registration(repo)
        xml_text = login_startup_task_xml_path(repo).read_text(encoding="utf-8")
        launcher = login_startup_launcher_path(repo).read_text(encoding="utf-8")
        first = dispatch_login_startup(repo, controller_starter=starter)
        second = dispatch_login_startup(repo, controller_starter=starter)
        missing_ok = (
            before.get("started") is False
            and before.get("restore_reason") == "not_registered"
            and repaired.get("started") is False
            and repaired.get("repair_reason") == "missing"
            and repaired.get("scheduled") is True
            and spec is not None
            and spec.get("enabled") is True
            and spec.get("trigger") == "at_logon"
            and "<LogonTrigger>" in xml_text
            and "restore_orphaned_loop_on_startup" in launcher
            and no_start_at_repair
            and first.get("started") is True
            and first.get("dispatched_from") == "login_startup"
            and second.get("started") is False
            and second.get("restore_reason") == "live_owner"
            and len(starts) == starts_at_repair + 1
        )

    with tempfile.TemporaryDirectory(prefix="accept-login-repair-disabled-", ignore_cleanup_errors=True) as tmp:
        repo = Path(tmp)
        (repo / "mission.json").write_text('{"status":"active"}\n', encoding="utf-8")
        _seed_orphaned(repo, pid=dead_pid)
        register_loop_restore_at_login(repo)
        path = login_startup_registration_path(repo)
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["enabled"] = False
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        before = dispatch_login_startup(repo, controller_starter=starter)
        starts_at_repair = len(starts)
        repaired = repair_login_startup_registration(repo)
        spec = load_login_startup_registration(repo)
        disabled_ok = (
            before.get("started") is False
            and before.get("restore_reason") == "not_enabled"
            and repaired.get("started") is False
            and repaired.get("repair_reason") == "disabled"
            and repaired.get("scheduled") is True
            and spec is not None
            and spec.get("enabled") is True
            and len(starts) == starts_at_repair
        )

    with tempfile.TemporaryDirectory(prefix="accept-login-repair-live-", ignore_cleanup_errors=True) as tmp:
        repo = Path(tmp)
        path = _seed_orphaned(repo, pid=live_pid, status="running_mission")
        continuous_loop_lock_path(repo).write_text(f"{live_pid}\n", encoding="utf-8")
        login_startup_registration_path(repo).unlink(missing_ok=True)
        before = path.read_bytes()
        starts_at_repair = len(starts)
        repaired = repair_login_startup_registration(repo)
        result = dispatch_login_startup(repo, controller_starter=starter)
        live_ok = (
            repaired.get("started") is False
            and repaired.get("repair_reason") == "missing"
            and repaired.get("scheduled") is True
            and result.get("started") is False
            and result.get("restore_reason") == "live_owner"
            and path.read_bytes() == before
            and len(starts) == starts_at_repair
            and pid_is_running(live_pid)
        )

    observed.update(
        {
            "dead_pid": dead_pid,
            "live_pid": live_pid,
            "missing_registration_repaired": missing_ok,
            "disabled_registration_repaired": disabled_ok,
            "live_owner_not_doubled": live_ok,
            "controller_starts": len(starts),
            "sentinel": "BH-LOOP-LOGIN-REPAIR-OK" if missing_ok and disabled_ok and live_ok else "",
            "error": "",
        }
    )
    passed = bool(missing_ok and disabled_ok and live_ok)
except Exception as error:  # pragma: no cover - fixture or helper failure
    observed["error"] = type(error).__name__
    observed["detail"] = str(error)
    passed = False

print(json.dumps({"passed": passed, "observed": observed}, sort_keys=True))
sys.exit(0)
