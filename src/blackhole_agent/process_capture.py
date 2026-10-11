"""Bounded controller subprocesses, including Windows Git wrapper trees.

PIPE capture can outlive a timed-out parent when a descendant inherits a pipe.
Capture to files instead, so reaping the owned process never waits for pipe EOF.
On every exit, stop that invocation's descendants before returning. Windows
uses a gated job so even descendants of an already-exited launcher stay owned.
POSIX commands and their ordinary descendants share a new process group.

Untrusted tool trees on the invocation plane also pass ``max_output_bytes``:
the parent never loads an oversized stdout/stderr blob into RAM, and a tree
that keeps writing is reaped as soon as the capture files exceed the cap.
Kernel and git callers omit the argument so their output stays unlimited.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


class ProcessCancelled(RuntimeError):
    """Raised when a caller-supplied cancel event stops the owned tree."""


MAX_OUTPUT_BYTES_ENV = "BLACKHOLE_MAX_OUTPUT_BYTES"
DEFAULT_MAX_OUTPUT_BYTES = 1 << 20
MIN_MAX_OUTPUT_BYTES = 256
MAX_MAX_OUTPUT_BYTES = 32 << 20
OUTPUT_LIMIT_VIOLATION = "output_limited"

_configured_max_output_bytes: int | None = None
_output_config_lock = threading.Lock()


class OutputLimitExceeded(Exception):
    """The owned tree wrote more stdout/stderr than the parent will load."""

    def __init__(self, max_output_bytes: int, captured_bytes: int, stream: str) -> None:
        self.max_output_bytes = int(max_output_bytes)
        self.captured_bytes = int(captured_bytes)
        self.stream = str(stream)
        super().__init__(
            f"captured {self.stream} exceeded {self.max_output_bytes} bytes "
            f"(observed {self.captured_bytes})"
        )

    def payload(self) -> dict[str, object]:
        return {
            "violation": OUTPUT_LIMIT_VIOLATION,
            "max_output_bytes": self.max_output_bytes,
            "captured_bytes": self.captured_bytes,
            "stream": self.stream,
        }


def parse_max_output_bytes(raw: str | None) -> int:
    """Return a host-safe capture cap; invalid values fall back to the default."""

    text = str(raw or "").strip()
    if not text.isdigit():
        return DEFAULT_MAX_OUTPUT_BYTES
    value = int(text)
    if value < MIN_MAX_OUTPUT_BYTES or value > MAX_MAX_OUTPUT_BYTES:
        return DEFAULT_MAX_OUTPUT_BYTES
    return value


def configure_max_output_bytes(max_output_bytes: int | None) -> None:
    """Pin the invocation-plane cap (or clear the pin so the process env is read)."""

    global _configured_max_output_bytes
    with _output_config_lock:
        if max_output_bytes is None:
            _configured_max_output_bytes = None
            return
        _configured_max_output_bytes = parse_max_output_bytes(str(int(max_output_bytes)))


def current_max_output_bytes() -> int:
    """Cap used by the invocation plane: CLI pin, else ``BLACKHOLE_MAX_OUTPUT_BYTES``."""

    with _output_config_lock:
        configured = _configured_max_output_bytes
    if configured is not None:
        return configured
    return parse_max_output_bytes(os.environ.get(MAX_OUTPUT_BYTES_ENV))


def _file_size(handle) -> int:
    try:
        return int(os.fstat(handle.fileno()).st_size)
    except OSError:
        return 0


def _output_exceeded(stdout, stderr, max_output_bytes: int | None) -> str:
    """Return ``stdout`` or ``stderr`` when that capture file is over the cap."""

    if not max_output_bytes:
        return ""
    if _file_size(stdout) > max_output_bytes:
        return "stdout"
    if _file_size(stderr) > max_output_bytes:
        return "stderr"
    return ""


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


def _resolve_sandbox_command(command: list[str] | str) -> list[str] | str:
    """Prefer the base interpreter so the sandbox does not need venv trampolines."""

    if isinstance(command, str):
        return command
    parts = [str(part) for part in command]
    if not parts:
        return parts
    name = Path(parts[0]).name.lower()
    aliases = {"python", "python.exe", "python3", "python3.exe"}
    try:
        same_exe = Path(parts[0]).resolve() == Path(sys.executable).resolve()
    except OSError:
        same_exe = False
    if name in aliases or same_exe:
        parts[0] = getattr(sys, "_base_executable", None) or sys.executable
    return parts


def _sandbox_path_payload(cwd: Path, sandbox_roots: Sequence[Path], scratch: Path) -> dict[str, list[str]]:
    rw: list[Path] = [Path(cwd).resolve(), Path(scratch).resolve()]
    rw.extend(Path(root).resolve() for root in sandbox_roots)
    rx: list[Path] = []
    if os.name == "nt":
        from blackhole_agent._windows_appcontainer import interpreter_rx_paths

        rx.extend(interpreter_rx_paths())
    else:
        for raw in (
            getattr(sys, "base_prefix", "") or sys.prefix,
            sys.prefix,
            "/usr",
            "/lib",
            "/lib64",
            "/usr/lib",
            "/usr/lib64",
            "/usr/local/lib",
        ):
            path = Path(raw)
            if path.exists():
                rx.append(path.resolve())
        rx.append(Path(getattr(sys, "_base_executable", None) or sys.executable).resolve().parent)

    def _unique(paths: list[Path]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for path in paths:
            key = str(path)
            folded = key.lower() if os.name == "nt" else key
            if folded in seen:
                continue
            seen.add(folded)
            out.append(key)
        return out

    return {"rw_paths": _unique(rw), "rx_paths": _unique(rx)}


def _landlock_supported() -> bool:
    if not sys.platform.startswith("linux"):
        return False
    try:
        import ctypes

        libc = ctypes.CDLL(None, use_errno=True)
        # landlock_create_ruleset syscall number is 444 on x86_64/aarch64 Linux.
        attr = ctypes.c_uint64(1)
        result = libc.syscall(444, ctypes.byref(attr), ctypes.c_size_t(8), ctypes.c_uint32(1 << 0))
        if result >= 0:
            os.close(int(result))
            return True
        return ctypes.get_errno() != 38  # ENOSYS
    except (OSError, AttributeError):
        return False


def _posix_sandbox_preexec(rw_paths: Sequence[str], rx_paths: Sequence[str]):
    """Apply Landlock ABI so the child can only use the granted trees."""

    import ctypes

    SYS_CREATE = 444
    SYS_ADD = 445
    SYS_RESTRICT = 446
    PR_SET_NO_NEW_PRIVS = 38
    LANDLOCK_RULE_PATH_BENEATH = 1
    ACCESS_FS_ALL = (1 << 15) - 1
    ACCESS_FS_READ = (1 << 0) | (1 << 2) | (1 << 3)  # execute, read file, read dir

    class RulesetAttr(ctypes.Structure):
        _fields_ = [("handled_access_fs", ctypes.c_uint64)]

    class PathBeneath(ctypes.Structure):
        _fields_ = [("allowed_access", ctypes.c_uint64), ("parent_fd", ctypes.c_int32)]

    libc = ctypes.CDLL(None, use_errno=True)

    def apply() -> None:
        libc.prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0)
        attr = RulesetAttr(ACCESS_FS_ALL)
        ruleset = libc.syscall(SYS_CREATE, ctypes.byref(attr), ctypes.c_size_t(ctypes.sizeof(attr)), 0)
        if ruleset < 0:
            raise OSError(ctypes.get_errno(), "landlock_create_ruleset failed")

        def add(path: str, access: int) -> None:
            try:
                flags = getattr(os, "O_PATH", 0)
                fd = os.open(path, flags | os.O_RDONLY | getattr(os, "O_CLOEXEC", 0))
            except OSError:
                return
            try:
                rule = PathBeneath(access, fd)
                added = libc.syscall(
                    SYS_ADD, int(ruleset), LANDLOCK_RULE_PATH_BENEATH,
                    ctypes.byref(rule), ctypes.c_size_t(ctypes.sizeof(rule)),
                )
                if added < 0:
                    raise OSError(ctypes.get_errno(), f"landlock_add_rule failed for {path}")
            finally:
                os.close(fd)

        for path in rx_paths:
            add(path, ACCESS_FS_READ)
        for path in rw_paths:
            add(path, ACCESS_FS_ALL)
        restricted = libc.syscall(SYS_RESTRICT, int(ruleset), 0)
        os.close(int(ruleset))
        if restricted < 0:
            raise OSError(ctypes.get_errno(), "landlock_restrict_self failed")

    return apply


def filesystem_sandbox_available() -> bool:
    if os.name == "nt":
        return True
    return _landlock_supported()


def run_captured_process(
    command: list[str] | str,
    *,
    cwd: Path,
    timeout: float,
    input: str | None = None,
    env: dict[str, str] | None = None,
    resource_limits: ResourceLimits | None = None,
    shell: bool = False,
    cancel_event: threading.Event | None = None,
    sandbox_roots: Sequence[Path] | None = None,
    max_output_bytes: int | None = None,
) -> subprocess.CompletedProcess[str]:
    """Return UTF-8 output, or raise TimeoutExpired within timeout + cleanup grace.

    When ``resource_limits`` is given, the whole command tree runs under hard
    bounds; on Windows the returned CompletedProcess carries a ``job_stats``
    attribute with peak committed memory and job termination accounting.
    ``shell=True`` passes a raw command string to the platform shell exactly
    like ``subprocess.run(shell=True)`` — required for embedded quoting on
    Windows. When ``cancel_event`` is given and becomes set while the tree
    runs, the owned tree is terminated and :class:`ProcessCancelled` is raised
    instead of waiting for the command to finish.
    When ``sandbox_roots`` is given, the command is filesystem-sandboxed:
    Windows AppContainer or Linux Landlock, allowlisted to those roots, the
    working directory, a per-invocation scratch directory, and the interpreter
    prefix. Host paths outside the allowlist are unreadable and unwritable.
    When ``max_output_bytes`` is given, stdout and stderr capture files are
    size-capped: the tree is reaped once either stream exceeds the cap, and
    the parent never decodes the oversized blob. Kernel callers omit this
    argument so their output stays unlimited.
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
        cancelled = False
        exceeded_stream = ""
        cleanup_error = ""
        job_stats = None
        sandbox_payload = None
        spawn_command = command
        spawn_env = dict(env) if env is not None else None
        cap_bytes = int(max_output_bytes) if max_output_bytes else 0
        if sandbox_roots is not None:
            if not filesystem_sandbox_available():
                raise RuntimeError("filesystem sandbox is not available on this host")
            spawn_command = _resolve_sandbox_command(command)
            sandbox_payload = _sandbox_path_payload(Path(cwd), sandbox_roots, Path(scratch))
            if isinstance(spawn_command, list) and spawn_command:
                exe_parent = Path(spawn_command[0]).resolve().parent
                exe_key = str(exe_parent).lower() if os.name == "nt" else str(exe_parent)
                existing = {p.lower() if os.name == "nt" else p for p in sandbox_payload["rx_paths"]}
                if exe_parent.exists() and exe_key not in existing:
                    sandbox_payload["rx_paths"].append(str(exe_parent))
            spawn_env = dict(env) if env is not None else {}
            # AppContainer CreateProcess looks up identity/profile variables and
            # fails with ERROR_ENVVAR_NOT_FOUND (203) when they are absent.
            for key in (
                "PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC",
                "HOME", "HOMEDRIVE", "HOMEPATH", "USERPROFILE", "USERNAME", "USERDOMAIN",
                "APPDATA", "LOCALAPPDATA", "ALLUSERSPROFILE", "PROGRAMDATA", "PUBLIC",
                "COMPUTERNAME", "OS", "PROCESSOR_ARCHITECTURE", "NUMBER_OF_PROCESSORS",
                "LANG", "LC_ALL", "LC_CTYPE",
            ):
                if key not in spawn_env and key in os.environ:
                    spawn_env[key] = os.environ[key]
            spawn_env["TEMP"] = scratch
            spawn_env["TMP"] = scratch
            spawn_env["TMPDIR"] = scratch
            spawn_env["PYTHONDONTWRITEBYTECODE"] = "1"
            spawn_env["PYTHONIOENCODING"] = "utf-8"
            spawn_env["PYTHONNOUSERSITE"] = "1"
        try:
            if os.name == "nt":
                from blackhole_agent._windows_job import WindowsJob

                job = WindowsJob(
                    memory_bytes=(resource_limits.memory_bytes if resource_limits else None),
                    max_processes=(resource_limits.max_processes if resource_limits else None),
                    cpu_seconds=(resource_limits.cpu_seconds if resource_limits else None),
                )
                process = job.start(
                    spawn_command,
                    cwd=cwd,
                    stdout=stdout,
                    stderr=stderr,
                    error_path=startup_error,
                    stdin_path=stdin_path if input is not None else None,
                    env=spawn_env,
                    shell=shell,
                    sandbox=sandbox_payload,
                )
            else:
                posix_hooks = []
                if os.name == "posix" and resource_limits and resource_limits.enabled():
                    posix_hooks.append(_posix_limit_preexec(resource_limits))
                if sandbox_payload is not None:
                    posix_hooks.append(
                        _posix_sandbox_preexec(
                            sandbox_payload["rw_paths"], sandbox_payload["rx_paths"]
                        )
                    )

                def _posix_preexec() -> None:
                    for hook in posix_hooks:
                        hook()

                stdin = open(stdin_path, "rb") if input is not None else subprocess.DEVNULL
                try:
                    process = subprocess.Popen(
                        spawn_command, cwd=cwd, stdin=stdin, stdout=stdout, stderr=stderr,
                        start_new_session=True,
                        env=spawn_env,
                        shell=shell,
                        preexec_fn=_posix_preexec if posix_hooks else None,
                    )
                finally:
                    if input is not None:
                        stdin.close()
            try:
                if cancel_event is None and not cap_bytes:
                    try:
                        process.wait(timeout=timeout)
                    except subprocess.TimeoutExpired:
                        timed_out = True
                else:
                    deadline = time.monotonic() + timeout
                    while True:
                        remaining = deadline - time.monotonic()
                        if cancel_event is not None and cancel_event.is_set():
                            cancelled = True
                            break
                        if remaining <= 0:
                            timed_out = True
                            break
                        exceeded_stream = _output_exceeded(stdout, stderr, cap_bytes)
                        if exceeded_stream:
                            break
                        try:
                            process.wait(timeout=min(0.2, max(remaining, 0.0)))
                            exceeded_stream = _output_exceeded(stdout, stderr, cap_bytes)
                            break
                        except subprocess.TimeoutExpired:
                            continue
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
        if cap_bytes:
            exceeded_stream = exceeded_stream or _output_exceeded(stdout, stderr, cap_bytes)
        if cancelled:
            raise ProcessCancelled(
                f"command tree cancelled by caller (exit {process.returncode}): {command!r}"
            )
        if exceeded_stream:
            observed = _file_size(stdout if exceeded_stream == "stdout" else stderr)
            raise OutputLimitExceeded(cap_bytes, observed, exceeded_stream)
        if cap_bytes:
            out = stdout.read(cap_bytes).decode("utf-8", errors="replace")
            err = stderr.read(cap_bytes).decode("utf-8", errors="replace")
        else:
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
