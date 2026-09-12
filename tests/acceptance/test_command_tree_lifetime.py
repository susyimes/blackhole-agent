"""Observe real descendant writers across command success, failure and timeout."""

from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from blackhole_agent.process_capture import run_captured_process


WORKER = """
import json, os, subprocess, sys, time
from pathlib import Path
root, role = Path(sys.argv[1]), sys.argv[2]
if role == 'child':
    subprocess.Popen([sys.executable, __file__, str(root), 'grandchild'])
(root / (role + '.pid')).write_text(str(os.getpid()))
deadline = time.monotonic() + 15
while not (root / 'stop').exists() and time.monotonic() < deadline:
    with (root / (role + '.writes')).open('ab') as stream:
        stream.write(b'x')
    time.sleep(0.02)
"""

LAUNCHER = """
import subprocess, sys, time
from pathlib import Path
root, mode = Path(sys.argv[1]), sys.argv[2]
subprocess.Popen([sys.executable, str(root / 'worker.py'), str(root), 'child'])
deadline = time.monotonic() + 5
while not all((root / (role + '.writes')).exists() for role in ('child', 'grandchild')):
    if time.monotonic() > deadline:
        raise RuntimeError('writers failed to start')
    time.sleep(0.01)
print('owned command ready', flush=True)
print('owned diagnostic', file=sys.stderr, flush=True)
if mode == 'timeout':
    time.sleep(30)
sys.exit(7 if mode == 'failure' else 0)
"""


def alive(pid: int) -> bool:
    if os.name == "nt":
        from ctypes import wintypes

        api = ctypes.WinDLL("kernel32", use_last_error=True)
        api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        api.OpenProcess.restype = wintypes.HANDLE
        api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        api.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = api.OpenProcess(0x100000, False, pid)  # SYNCHRONIZE
        if not handle:
            return False
        try:
            return api.WaitForSingleObject(handle, 0) == 258  # WAIT_TIMEOUT
        finally:
            api.CloseHandle(handle)
    # Linux zombies have exited; their parent/init may reap them asynchronously.
    stat = Path(f"/proc/{pid}/stat")
    if stat.is_file() and stat.read_text().rsplit(")", 1)[-1].strip().startswith("Z"):
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def observe_case(root: Path, mode: str, unrelated: subprocess.Popen) -> dict:
    root.mkdir()
    (root / "worker.py").write_text(WORKER, encoding="utf-8")
    (root / "launcher.py").write_text(LAUNCHER, encoding="utf-8")
    command = [sys.executable, "-u", str(root / "launcher.py"), str(root), mode]
    began = time.monotonic()
    try:
        try:
            result = run_captured_process(command, cwd=root, timeout=2 if mode == "timeout" else 8)
            out, err, exit_code = result.stdout, result.stderr, result.returncode
            timed_out = False
        except subprocess.TimeoutExpired as error:
            out, err, exit_code = error.stdout, error.stderr, None
            timed_out = True
        elapsed = time.monotonic() - began
        pids = [int((root / (role + ".pid")).read_text()) for role in ("child", "grandchild")]
        paths = [root / (role + ".writes") for role in ("child", "grandchild")]
        before = [path.stat().st_size for path in paths]
        alive_at_return = [alive(pid) for pid in pids]
        time.sleep(0.25)
        after = [path.stat().st_size for path in paths]
        observed = {
            "mode": mode, "writers_started": all(before),
            "owned_alive_at_return": alive_at_return,
            "post_return_writes": [end - start for start, end in zip(before, after)],
            "stdout_preserved": out.splitlines() == ["owned command ready"],
            "stderr_preserved": err.splitlines() == ["owned diagnostic"],
            "exit_code": exit_code, "timed_out": timed_out,
            "elapsed_seconds": round(elapsed, 3), "unrelated_alive": unrelated.poll() is None,
        }
        observed["passed"] = bool(
            observed["writers_started"] and not any(alive_at_return) and before == after
            and observed["stdout_preserved"] and observed["stderr_preserved"]
            and observed["unrelated_alive"] and timed_out == (mode == "timeout")
            and exit_code == {"success": 0, "failure": 7, "timeout": None}[mode]
            and elapsed < 12
        )
        return observed
    finally:
        # The baseline deliberately leaves writers; stop them cooperatively so
        # baseline acceptance is also safe to run repeatedly.
        (root / "stop").touch()
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            pids = [int(path.read_text()) for path in root.glob("*.pid")]
            if not any(alive(pid) for pid in pids):
                break
            time.sleep(0.02)


def main() -> dict:
    unrelated = subprocess.Popen(
        [sys.executable, "-c", "import time;time.sleep(60)"],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        with tempfile.TemporaryDirectory(prefix="accept-command-tree-") as directory:
            root = Path(directory)
            cases = [observe_case(root / mode, mode, unrelated) for mode in ("success", "failure", "timeout")]
            return {"passed": all(case["passed"] for case in cases), "observed": cases}
    finally:
        unrelated.kill()
        unrelated.wait(timeout=5)


if __name__ == "__main__":
    print(json.dumps(main(), sort_keys=True))
