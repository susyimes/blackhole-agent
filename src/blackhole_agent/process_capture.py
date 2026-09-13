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
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ResourceLimits:
    """Hard resource bounds for an untrusted command tree.

    ``memory_bytes`` caps committed memory for the whole tree (Windows job
    memory limit; POSIX ``RLIMIT_AS`` per process). ``max_processes`` caps the
    number of simultaneously active processes in the tree (Windows job active
    process limit; POSIX ``RLIMIT_NPROC`` best effort). ``cpu_seconds`` caps
    total user-mode CPU time for the tree (Windows job time limit; POSIX
    ``RLIMIT_CPU`` per process).
    """

    memory_bytes: int | None = None
    max_processes: int | None = None
    cpu_seconds: int | None = None

    def enabled(self) -> bool:
        return bool(self.memory_bytes) or bool(self.max_processes) or bool(self.cpu_seconds)


def _posix_limit_preexec(limits: ResourceLimits):
    import resource

    def apply() -> None:
        if limits.memory_bytes:
            resource.setrlimit(resource.RLIMIT_AS, (limits.memory_bytes, limits.memory_bytes))
        if limits.max_processes:
            try:
                resource.setrlimit(resource.RLIMIT_NPROC, (limits.max_processes, limits.max_processes))
            except (ValueError, OSError):
                pass  # RLIMIT_NPROC is unsupported on some POSIX hosts.
        if limits.cpu_seconds:
            resource.setrlimit(resource.RLIMIT_CPU, (limits.cpu_seconds, limits.cpu_seconds))

    return apply


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


def run_captured_process(
    command: list[str],
    *,
    cwd: Path,
    timeout: float,
    input: str | None = None,
    env: dict[str, str] | None = None,
    resource_limits: ResourceLimits | None = None,
) -> subprocess.CompletedProcess[str]:
    """Return UTF-8 output, or raise TimeoutExpired within timeout + cleanup grace.

    When ``resource_limits`` is given, the whole command tree runs under hard
    bounds; on Windows the returned CompletedProcess carries a ``job_stats``
    attribute with peak committed memory and job termination accounting.
    """
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
        stdin_path = Path(scratch) / "stdin.txt"
        if input is not None:
            stdin_path.write_text(input, encoding="utf-8")
        timed_out = False
        cleanup_error = ""
        job_stats = None
        try:
            if os.name == "nt":
                from blackhole_agent._windows_job import WindowsJob

                job = WindowsJob(
                    memory_bytes=(resource_limits.memory_bytes if resource_limits else None),
                    max_processes=(resource_limits.max_processes if resource_limits else None),
                    cpu_seconds=(resource_limits.cpu_seconds if resource_limits else None),
                )
                process = job.start(
                    command,
                    cwd=cwd,
                    stdout=stdout,
                    stderr=stderr,
                    error_path=startup_error,
                    stdin_path=stdin_path if input is not None else None,
                    env=env,
                )
            else:
                stdin = open(stdin_path, "rb") if input is not None else subprocess.DEVNULL
                try:
                    process = subprocess.Popen(
                        command, cwd=cwd, stdin=stdin, stdout=stdout, stderr=stderr,
                        start_new_session=True,
                        env=env,
                        preexec_fn=(
                            _posix_limit_preexec(resource_limits)
                            if os.name == "posix" and resource_limits and resource_limits.enabled()
                            else None
                        ),
                    )
                finally:
                    if input is not None:
                        stdin.close()
            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
            finally:
                if job is not None:
                    try:
                        job_stats = job.stats()
                    except OSError:
                        job_stats = None
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
        completed = subprocess.CompletedProcess(command, process.returncode, out, err)
        if job_stats is not None:
            completed.job_stats = job_stats  # type: ignore[attr-defined]
        return completed
