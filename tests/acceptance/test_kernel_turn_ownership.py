"""Observe kernel-turn process ownership on the production invocation path.

Drives the real Kimi CLI kernel with its default command runner (the
production path used by the Unbound controller) against a scripted CLI that
streams a session id, spawns a grandchild writer, and then outlives a short
turn timeout. A passing kernel invocation raises its timeout error within the
turn budget plus a bounded cleanup grace instead of waiting for the
grandchild's inherited-pipe EOF, leaves no descendant writing afterward, and
still persists durable run artifacts carrying the streamed session id so the
next turn can resume the session.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

SESSION_ID = "probe-session-kernel-turn-ownership"
TIMEOUT_SECONDS = 3
GRANDCHILD_LIFETIME_SECONDS = 25
JOIN_BUDGET_SECONDS = 20.0
RETURN_BUDGET_SECONDS = 14.0  # turn timeout + bounded cleanup grace
REAP_WATCH_SECONDS = 4.0

WRITER = """\
import os, sys, time
from pathlib import Path
heartbeat = Path(sys.argv[1])
Path(sys.argv[2]).write_text(str(os.getpid()), encoding="utf-8")
deadline = time.monotonic() + %(lifetime)r
while time.monotonic() < deadline:
    with heartbeat.open("a", encoding="utf-8") as handle:
        handle.write("beat\\n")
    time.sleep(0.3)
"""

FAKE_CLI = """\
import json, subprocess, sys, time
from pathlib import Path
print(json.dumps({"role": "meta", "type": "session.resume_hint", "session_id": %(session)r}), flush=True)
root = Path(__file__).parent
subprocess.Popen([sys.executable, str(root / "writer.py"), str(root / "heartbeat.log"), str(root / "grandchild.pid")])
time.sleep(60)
"""


def beats(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines()) if path.exists() else 0


def main() -> dict:
    try:
        from blackhole_agent.kernels.kimi_cli import KimiCliConfig, KimiCliKernel
    except ImportError as error:
        return {"passed": False, "observed": f"kimi kernel unavailable: {error}"}

    root = Path(tempfile.mkdtemp(prefix="accept-kernel-turn-ownership-"))
    try:
        (root / "writer.py").write_text(
            WRITER % {"lifetime": GRANDCHILD_LIFETIME_SECONDS}, encoding="utf-8"
        )
        fake_cli = root / "fake_kimi.py"
        fake_cli.write_text(FAKE_CLI % {"session": SESSION_ID}, encoding="utf-8")
        heartbeat = root / "heartbeat.log"
        pid_file = root / "grandchild.pid"
        output_dir = root / "kernel-out"

        config = KimiCliConfig(kimi_bin=sys.executable, extra_args=(str(fake_cli),))
        kernel = KimiCliKernel(config)  # default command runner: the production path

        outcome: dict = {}
        started = time.monotonic()

        def invoke() -> None:
            try:
                kernel.run("probe task", cwd=root, output_dir=output_dir, timeout_seconds=TIMEOUT_SECONDS)
                outcome["returned_normally"] = True
            except BaseException as exc:  # noqa: BLE001 - reported, not raised
                outcome["error"] = f"{type(exc).__name__}"
            outcome["elapsed"] = time.monotonic() - started

        worker = threading.Thread(target=invoke, daemon=True)
        worker.start()
        worker.join(JOIN_BUDGET_SECONDS)
        if worker.is_alive():
            # Best-effort hygiene: stop the stray grandchild this run leaked.
            try:
                if pid_file.exists():
                    os.kill(int(pid_file.read_text().strip()), 9)
            except (OSError, ValueError):
                pass
            return {
                "passed": False,
                "observed": (
                    f"kernel invocation still blocked {JOIN_BUDGET_SECONDS:.0f}s after start with a "
                    f"{TIMEOUT_SECONDS}s turn timeout: the turn is waiting on inherited-pipe EOF "
                    "held by a surviving descendant instead of returning within a bounded grace"
                ),
            }

        elapsed = float(outcome.get("elapsed", RETURN_BUDGET_SECONDS + 1))
        bounded_timeout = outcome.get("error") == "TimeoutError" and elapsed <= RETURN_BUDGET_SECONDS

        before = beats(heartbeat)
        time.sleep(REAP_WATCH_SECONDS)
        after = beats(heartbeat)
        descendant_reaped = before == after

        session_id = ""
        latest = output_dir / "latest-kimi-run.json"
        if latest.is_file():
            try:
                session_id = str(json.loads(latest.read_text(encoding="utf-8")).get("session_id") or "")
            except (OSError, json.JSONDecodeError):
                session_id = ""
        session_salvaged = session_id == SESSION_ID

        passed = bounded_timeout and descendant_reaped and session_salvaged
        return {
            "passed": passed,
            "observed": (
                f"kernel turn timeout at {TIMEOUT_SECONDS}s returned "
                f"{outcome.get('error') or 'normally'} after {elapsed:.1f}s "
                f"(budget {RETURN_BUDGET_SECONDS:.0f}s); grandchild heartbeats {before}->{after} "
                f"over {REAP_WATCH_SECONDS:.0f}s after return; salvaged session id {session_id!r}"
            ),
        }
    finally:
        import shutil

        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    print(json.dumps(main()))
