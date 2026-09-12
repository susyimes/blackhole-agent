"""Bounded controller subprocesses, including Windows Git wrapper trees.

PIPE capture can outlive a timed-out parent when a descendant inherits a pipe.
Capture to files instead, so reaping the owned process never waits for pipe EOF.
On every exit, stop that invocation's descendants before returning. Windows
uses a gated job so even descendants of an already-exited launcher stay owned.
POSIX commands and their ordinary descendants share a new process group.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import tempfile
from pathlib import Path


def _terminate_owned_tree(process: subprocess.Popen, job=None) -> str:
    errors = []
    if job is not None:
        try:
            job.terminate()
        except OSError as exc:
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
    # Capture handles and the bootstrap's startup-error channel are temporary.
    with (
        tempfile.TemporaryFile() as stdout,
        tempfile.TemporaryFile() as stderr,
        tempfile.TemporaryDirectory(prefix="blackhole-command-") as scratch,
    ):
        job = None
        startup_error = Path(scratch) / "startup-error.json"
        timed_out = False
        cleanup_error = ""
        try:
            if os.name == "nt":
                from blackhole_agent._windows_job import WindowsJob

                job = WindowsJob()
                process = job.start(command, cwd=cwd, stdout=stdout, stderr=stderr, error_path=startup_error)
            else:
                process = subprocess.Popen(
                    command, cwd=cwd, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                    start_new_session=True,
                )
            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
            finally:
                cleanup_error = _terminate_owned_tree(process, job)
        finally:
            if job is not None:
                job.close()
        stdout.seek(0)
        stderr.seek(0)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        if cleanup_error:
            err += f"\nProcess cleanup: {cleanup_error}"
        if timed_out:
            raise subprocess.TimeoutExpired(command, timeout, output=out, stderr=err)
        if cleanup_error:
            raise RuntimeError(f"Command descendants could not be stopped: {cleanup_error}")
        if startup_error.is_file():
            failure = json.loads(startup_error.read_text(encoding="utf-8"))
            raise OSError(failure["errno"], failure["message"], failure["filename"], failure["winerror"])
        return subprocess.CompletedProcess(command, process.returncode, out, err)
