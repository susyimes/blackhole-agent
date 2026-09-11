"""Observe durable recovery after an actual controller owner process is killed."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from typer.testing import CliRunner

from blackhole_agent import unbound


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
        'loop_id': 'interrupted-controller', 'pid': os.getpid(),
        'status': 'running_mission', 'current_mission_id': 'unfinished-mission',
        'current_state_path': str(repo / 'mission.json'),
        'lineage_ref': 'proven-commit', 'pending_publish_ref': 'pending-commit',
        'next_wake_at': '2099-01-01T00:00:00Z', 'last_error': 'retained diagnostic',
    })
    (repo / 'ready').write_text('ready')
    time.sleep(60)
"""


def observe_reaping() -> dict:
    runner = CliRunner()
    with tempfile.TemporaryDirectory(prefix="blackhole-orphan-outcome-") as directory:
        repo = Path(directory)
        mission = repo / "mission.json"
        mission.write_text('{"status":"active","work":"preserve this mission"}\n', encoding="utf-8")
        mission_before = mission.read_bytes()
        child = subprocess.Popen(
            [sys.executable, "-I", "-c", CONTROLLER, str(Path(unbound.__file__).resolve().parents[1]), str(repo)],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
        )
        owner_pid = None
        try:
            deadline = time.monotonic() + 15
            while not (repo / "ready").exists():
                if child.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError("controller fixture did not become ready")
                time.sleep(0.02)
            state_path = unbound.continuous_loop_state_path(repo)
            original = state_path.read_bytes()
            # A Windows venv launcher can have a different PID from its interpreter.
            owner_pid = json.loads(original)["pid"]
            live = runner.invoke(unbound.app, ["loop-status", "--repo-path", str(repo)])
            live_payload = json.loads(live.stdout)
            live_preserved = (
                live.exit_code == 0 and live_payload["pid_alive"] is True
                and live_payload["status"] == "running_mission" and state_path.read_bytes() == original
            )
            os.kill(owner_pid, signal.SIGTERM)
            child.wait(timeout=10)
            dead_confirmed = not unbound.pid_is_running(owner_pid)
            first = runner.invoke(unbound.app, ["loop-status", "--repo-path", str(repo)])
            shown = json.loads(first.stdout)
            persisted = json.loads(state_path.read_text(encoding="utf-8"))
            events_path = unbound.continuous_loop_events_path(repo)
            events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()] \
                if events_path.exists() else []
            after = state_path.read_bytes()
            second = runner.invoke(unbound.app, ["loop-status", "--repo-path", str(repo)])
            events_after = events_path.read_text(encoding="utf-8").splitlines() if events_path.exists() else []
            observed = {
                "controller_pid": owner_pid,
                "controller_dead": dead_confirmed,
                "live_owner_preserved": live_preserved,
                "reported_status": shown.get("status"),
                "durable_status": persisted.get("status"),
                "previous_status": persisted.get("orphaned_from_status"),
                "stale_pid_lock_removed": not unbound.continuous_loop_lock_path(repo).exists(),
                "mission_preserved": mission.read_bytes() == mission_before,
                "recovery_context_preserved": all(persisted.get(key) == json.loads(original)[key] for key in (
                    "pid", "current_mission_id", "current_state_path", "lineage_ref", "pending_publish_ref", "last_error",
                )),
                "reaping_event_count": len(events),
                "event_matches_owner": bool(events) and events[0].get("pid") == owner_pid
                and events[0].get("event") == "continuous_loop.orphaned"
                and events[0].get("previous_status") == "running_mission",
                "idempotent": state_path.read_bytes() == after and len(events_after) == len(events),
                "cli_exit_codes": [live.exit_code, first.exit_code, second.exit_code],
            }
            passed = (
                dead_confirmed and live_preserved and shown.get("status") == "orphaned"
                and persisted.get("status") == "orphaned" and persisted.get("orphaned_from_status") == "running_mission"
                and persisted.get("next_wake_at") == "" and bool(persisted.get("reaped_at"))
                and observed["stale_pid_lock_removed"] and observed["mission_preserved"]
                and observed["recovery_context_preserved"] and len(events) == 1 and observed["event_matches_owner"]
                and observed["idempotent"] and observed["cli_exit_codes"] == [0, 0, 0]
            )
            return {"passed": bool(passed), "observed": observed}
        finally:
            if owner_pid is not None and unbound.pid_is_running(owner_pid):
                os.kill(owner_pid, signal.SIGTERM)
            if child.poll() is None:
                child.kill()
            child.communicate(timeout=10)


if __name__ == "__main__":
    print(json.dumps(observe_reaping(), sort_keys=True))
