"""Bounded controller subprocesses, including Windows Git wrapper trees.

PIPE capture can outlive a timed-out parent when a descendant inherits a pipe.
Capture to files instead, so reaping the owned process never waits for pipe EOF.
On timeout, terminate only that invocation's process tree before returning.
"""

from __future__ import annotations

import os
import signal
import subprocess
import tempfile
from pathlib import Path


def _terminate_owned_tree(process: subprocess.Popen) -> str:
    errors = []
    if os.name == "nt":
        if process.poll() is None:
            # The retained Popen handle identifies our still-live invocation.
            # No image-name kill or scan of unrelated CLI processes is used.
            killer = Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32" / "taskkill.exe"
            try:
                result = subprocess.run(
                    [str(killer), "/PID", str(process.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10, check=False,
                )
                if result.returncode:
                    errors.append(f"tree termination exited {result.returncode}")
            except (OSError, subprocess.TimeoutExpired) as exc:
                errors.append(str(exc))
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if process.poll() is None:
        process.kill()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        errors.append("owned parent did not exit within cleanup grace")
    return "; ".join(errors)


def run_captured_process(command: list[str], *, cwd: Path, timeout: float) -> subprocess.CompletedProcess[str]:
    """Return UTF-8 output, or raise TimeoutExpired within timeout + cleanup grace."""
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    # Named files are unnecessary; temporary handles are removed on context exit.
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        process = subprocess.Popen(
            command, cwd=cwd, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
            start_new_session=os.name != "nt",
        )
        timed_out = False
        cleanup_error = ""
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            cleanup_error = _terminate_owned_tree(process)
        except BaseException:
            _terminate_owned_tree(process)
            raise
        stdout.seek(0)
        stderr.seek(0)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        if cleanup_error:
            err += f"\nProcess cleanup: {cleanup_error}"
        if timed_out:
            raise subprocess.TimeoutExpired(command, timeout, output=out, stderr=err)
        return subprocess.CompletedProcess(command, process.returncode, out, err)
