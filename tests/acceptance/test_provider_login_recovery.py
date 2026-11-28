"""Replay the recorded Cursor refusal and observe task delivery across independent dispatchers."""

import json
import os
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from blackhole_agent.kernel_salvage import execute_kernel_turn_with_salvage
from blackhole_agent.unbound import KernelTurnResult, invoke_kernel_turn


SIGN_IN = "Error: Authentication required. Please run 'agent login' first, or set CURSOR_API_KEY environment variable."
START = datetime(2026, 11, 28, tzinfo=timezone.utc)


def deliver(root, label, minute, *, requested="cursor", mode="serve"):
    state = SimpleNamespace(kernel=requested, repo_path=str(root), workspace_path=str(root), goal=label,
                            session_id="", session_started=False, model=None, timeout_seconds=10)
    trace = []

    def transport(argv, *, input, **kwargs):
        trace.append("cursor")
        if mode == "refuse":
            return subprocess.CompletedProcess(argv, 1, "", SIGN_IN)
        if mode == "disconnected":
            error = "Client network socket disconnected before secure TLS connection was established"
            return subprocess.CompletedProcess(argv, 1, "", error)
        if mode == "hold":
            (root / (label + ".entered")).touch()
            deadline = time.monotonic() + 12
            while not (root / (label + ".release")).exists():
                if time.monotonic() >= deadline:
                    return subprocess.CompletedProcess(argv, 1, "", "fixture hold expired")
                time.sleep(0.02)
        message = "incomplete reply" if mode == "malformed" else json.dumps({"status": "continue", "summary": input})
        result = {"type": "result", "subtype": "success", "session_id": "fixture", "result": message}
        return subprocess.CompletedProcess(argv, 0, json.dumps(result), "")

    def dispatch(state, prompt, attempt, **kwargs):
        if state.kernel == "cursor":
            return invoke_kernel_turn(state, prompt, attempt, command_runner=transport)
        trace.append(state.kernel)
        if mode == "peer_failed":
            raise RuntimeError("peer process unavailable")
        return KernelTurnResult(state.kernel, json.dumps({"status": "continue", "summary": prompt}), "peer", (), "")

    def local_tick(state, workspace):
        trace.append("local")
        return {"summary": state.goal}

    def ping(name):
        return {"ok": True, "evidence": f"{name} version 1.0"}

    _, decision, _ = execute_kernel_turn_with_salvage(
        state, label, root / label, kernel_runner=dispatch, installed_kernels={"cursor", "codex"},
        local_action=local_tick, peer_probe=ping, now=START + timedelta(minutes=minute),
    )
    return {"calls": trace, "delivered_by": state.kernel, "reply": decision.summary}


@contextmanager
def holding(root, label, minute):
    # The OS closes this dispatcher's handles on kill. The witness never deletes a lock.
    with subprocess.Popen(
        [sys.executable, __file__, str(root), label, str(minute), "hold"],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    ) as process:
        try:
            deadline = time.monotonic() + 12
            while not (root / (label + ".entered")).exists():
                if process.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError(f"{label} did not reach the provider")
                time.sleep(0.02)
            yield process
        finally:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)


def observe(root):
    rows = {}

    def run(label, minute, **options):
        rows[label] = deliver(root, label, minute, **options)

    run("refused", 0, mode="refuse")
    fresh = subprocess.run(
        [sys.executable, __file__, str(root), "fresh_wake", "5", "refuse"],
        capture_output=True, text=True, check=True, timeout=12,
    )
    rows["fresh_wake"] = json.loads(fresh.stdout)
    run("background_ping", 61, requested="codex")
    with holding(root, "aborted_trial", 62):
        run("overlapping_request", 63)
        run("overlapping_failover", 63, requested="codex", mode="peer_failed")
    run("trial_after_crash", 64, mode="refuse")
    run("renewed_cooldown", 65, mode="refuse")
    run("malformed_trial", 190, mode="malformed")
    run("disconnected_trial", 191, mode="disconnected")
    run("after_transport_cooldown", 372, requested="codex")
    with holding(root, "successful_trial", 373) as owner:
        run("before_recovery", 374)
        (root / "successful_trial.release").touch()
        stdout, _ = owner.communicate(timeout=8)
        rows["successful_trial"] = json.loads(stdout)
    with holding(root, "healthy_overlap", 375) as healthy:
        run("after_recovery", 376)
        (root / "healthy_overlap.release").touch()
        stdout, _ = healthy.communicate(timeout=8)
        rows["healthy_overlap"] = json.loads(stdout)

    expected = {
        "refused": ["cursor", "codex"], "fresh_wake": ["codex"], "background_ping": ["codex"],
        "overlapping_request": ["codex"], "overlapping_failover": ["codex", "local"],
        "trial_after_crash": ["cursor", "codex"], "renewed_cooldown": ["codex"],
        "malformed_trial": ["cursor", "codex"], "disconnected_trial": ["cursor", "codex"],
        "after_transport_cooldown": ["codex"], "before_recovery": ["codex"],
        "successful_trial": ["cursor"], "after_recovery": ["cursor"], "healthy_overlap": ["cursor"],
    }
    passed = all(
        rows[label] == {"calls": calls, "delivered_by": calls[-1], "reply": label} for label, calls in expected.items()
    )
    return {"passed": passed, "observed": rows}


if __name__ == "__main__":
    # The real Cursor adapter uses the deterministic wire transcript above for its process I/O.
    os.environ["CURSOR_AGENT_BIN"] = sys.executable
    if len(sys.argv) == 5:
        print(json.dumps(deliver(Path(sys.argv[1]), sys.argv[2], int(sys.argv[3]), mode=sys.argv[4])))
    else:
        with tempfile.TemporaryDirectory() as directory:
            try:
                result = observe(Path(directory))
            except Exception as error:
                result = {"passed": False, "observed": {"error": f"{type(error).__name__}: {error}"}}
            print(json.dumps(result))
