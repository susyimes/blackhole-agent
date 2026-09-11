"""Acceptance probe: login registration resumes an orphan and does not double a live owner.

Prints JSON with boolean passed and nonempty observed. Exits 0 for both
met and unmet outcomes so the controller can replay the same probe on
baseline and candidate source trees.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

observed: dict[str, object] = {"family": "loop-login-task"}
passed = False
children: list[subprocess.Popen[str]] = []
owner_pids: list[int] = []

try:
    from blackhole_agent.loop_login_task import (
        dispatch_login_startup,
        login_startup_launcher_path,
        login_startup_task_xml_path,
        register_loop_restore_at_login,
    )
    from blackhole_agent.unbound import (
        continuous_loop_events_path,
        continuous_loop_lock_path,
        continuous_loop_state_path,
        pid_is_running,
        save_continuous_loop_state,
    )
except Exception as error:  # pragma: no cover - baseline missing login enablement
    observed["error"] = type(error).__name__
    observed["detail"] = str(error)
    print(json.dumps({"passed": False, "observed": observed}, sort_keys=True))
    raise SystemExit(0)


CONTROLLER = """
import os, sys, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from blackhole_agent.unbound import (
    continuous_loop_lock, continuous_loop_lock_path,
    continuous_loop_state_path, save_continuous_loop_state,
)
repo = Path(sys.argv[2])
with continuous_loop_lock(continuous_loop_lock_path(repo)):
    save_continuous_loop_state(continuous_loop_state_path(repo), {
        'loop_id': 'login-restored-controller', 'pid': os.getpid(),
        'status': 'running_mission', 'current_mission_id': 'unfinished-mission',
        'current_state_path': str(repo / 'mission.json'),
        'lineage_ref': 'proven-commit', 'pending_publish_ref': 'pending-commit',
        'restored_from_status': 'orphaned', 'last_error': 'retained diagnostic',
    })
    (repo / 'ready').write_text(str(os.getpid()), encoding='utf-8')
    time.sleep(60)
"""


def _seed_orphaned(repo: Path, *, pid: int) -> Path:
    path = continuous_loop_state_path(repo)
    save_continuous_loop_state(
        path,
        {
            "loop_id": "acceptance-login",
            "status": "orphaned",
            "pid": pid,
            "orphaned_from_status": "running_mission",
            "current_mission_id": "unfinished-mission",
            "current_state_path": str(repo / "mission.json"),
            "lineage_ref": "proven-commit",
            "pending_publish_ref": "pending-commit",
            "last_error": "retained diagnostic",
            "stop_reason": "controller_process_missing",
            "reaped_at": "2026-09-11T00:00:00Z",
        },
    )
    return path


def _wait_ready(repo: Path, child: subprocess.Popen[str], timeout: float = 15) -> int:
    deadline = time.monotonic() + timeout
    while not (repo / "ready").exists():
        if child.poll() is not None or time.monotonic() >= deadline:
            raise RuntimeError("login-restored controller did not become ready")
        time.sleep(0.02)
    return int((repo / "ready").read_text(encoding="utf-8").strip())


def _starter_for(src: Path):
    def starter(repo: Path, output_dir=None, payload=None):
        child = subprocess.Popen(
            [sys.executable, "-I", "-c", CONTROLLER, str(src), str(repo)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        children.append(child)
        owner_pid = _wait_ready(repo, child)
        owner_pids.append(owner_pid)
        return {"started": True, "pid": owner_pid}

    return starter


def _stop_controllers() -> None:
    for owner in list(owner_pids):
        if pid_is_running(owner):
            try:
                os.kill(owner, signal.SIGTERM)
            except OSError:
                pass
    for child in list(children):
        if child.poll() is None:
            child.kill()
        try:
            child.communicate(timeout=5)
        except Exception:
            pass
    deadline = time.monotonic() + 5
    while any(pid_is_running(owner) for owner in owner_pids) and time.monotonic() < deadline:
        time.sleep(0.02)
    owner_pids.clear()
    children.clear()


try:
    from blackhole_agent import unbound

    src = Path(unbound.__file__).resolve().parents[1]
    dead_pid = 1_000_061
    while pid_is_running(dead_pid):
        dead_pid += 2
    live_pid = os.getpid()
    owner_pid = 0
    scheduled_ok = False
    orphan_ok = False
    live_ok = False

    with tempfile.TemporaryDirectory(prefix="accept-login-orphan-", ignore_cleanup_errors=True) as tmp:
        repo = Path(tmp)
        (repo / "mission.json").write_text('{"status":"active","work":"preserve"}\n', encoding="utf-8")
        mission_before = (repo / "mission.json").read_bytes()
        _seed_orphaned(repo, pid=dead_pid)
        starter = _starter_for(src)
        before = dispatch_login_startup(repo, controller_starter=starter)
        registered = register_loop_restore_at_login(repo)
        xml_text = login_startup_task_xml_path(repo).read_text(encoding="utf-8")
        launcher = login_startup_launcher_path(repo).read_text(encoding="utf-8")
        scheduled_ok = (
            before.get("started") is False
            and before.get("restore_reason") == "not_registered"
            and registered.get("scheduled") is True
            and registered.get("started") is False
            and registered.get("trigger") == "at_logon"
            and registered.get("helper") == (
                "blackhole_agent.loop_reboot_restore:restore_orphaned_loop_on_startup"
            )
            and registered.get("enabled") is True
            and "<LogonTrigger>" in xml_text
            and "IgnoreNew" in xml_text
            and "restore_orphaned_loop_on_startup" in launcher
            and login_startup_launcher_path(repo).is_file()
        )
        first = dispatch_login_startup(repo, controller_starter=starter)
        owner_pid = int(first.get("restored_pid") or 0)
        persisted = json.loads(continuous_loop_state_path(repo).read_text(encoding="utf-8"))
        events_path = continuous_loop_events_path(repo)
        events = (
            [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()]
            if events_path.exists()
            else []
        )
        second = dispatch_login_startup(repo, controller_starter=starter)
        orphan_ok = (
            scheduled_ok
            and first.get("started") is True
            and first.get("action") == "restore"
            and first.get("restore_reason") == "orphaned_no_live_owner"
            and first.get("dispatched_from") == "login_startup"
            and owner_pid != dead_pid
            and pid_is_running(owner_pid)
            and persisted.get("status") == "running_mission"
            and persisted.get("pid") == owner_pid
            and persisted.get("current_mission_id") == "unfinished-mission"
            and persisted.get("lineage_ref") == "proven-commit"
            and persisted.get("pending_publish_ref") == "pending-commit"
            and (repo / "mission.json").read_bytes() == mission_before
            and any(item.get("event") == "continuous_loop.restored" for item in events)
            and second.get("started") is False
            and second.get("restore_reason") == "live_owner"
            and len(children) == 1
            and children[0].poll() is None
        )
        _stop_controllers()

    with tempfile.TemporaryDirectory(prefix="accept-login-live-", ignore_cleanup_errors=True) as tmp:
        repo = Path(tmp)
        path = _seed_orphaned(repo, pid=live_pid)
        save_continuous_loop_state(
            path,
            {
                **json.loads(path.read_text(encoding="utf-8")),
                "status": "running_mission",
                "pid": live_pid,
            },
        )
        continuous_loop_lock_path(repo).write_text(f"{live_pid}\n", encoding="utf-8")
        register_loop_restore_at_login(repo)
        before = path.read_bytes()
        live_starts = len(children)
        result = dispatch_login_startup(repo, controller_starter=_starter_for(src))
        live_ok = (
            result.get("started") is False
            and result.get("restore_reason") == "live_owner"
            and result.get("scheduled") is True
            and path.read_bytes() == before
            and len(children) == live_starts
            and continuous_loop_lock_path(repo).read_text(encoding="utf-8") == f"{live_pid}\n"
        )

    observed.update(
        {
            "dead_pid": dead_pid,
            "live_pid": live_pid,
            "restored_pid": owner_pid,
            "login_scheduled_restore": scheduled_ok,
            "orphaned_resumed_after_login": orphan_ok,
            "live_owner_not_doubled": live_ok,
            "controller_count": len(children),
            "sentinel": "BH-LOOP-LOGIN-TASK-OK" if orphan_ok and live_ok else "",
            "error": "",
        }
    )
    passed = bool(orphan_ok and live_ok)
except Exception as error:  # pragma: no cover - fixture or helper failure
    observed["error"] = type(error).__name__
    observed["detail"] = str(error)
    passed = False
finally:
    _stop_controllers()

print(json.dumps({"passed": passed, "observed": observed}, sort_keys=True))
