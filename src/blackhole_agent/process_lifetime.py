"""Inspect process liveness and the earliest credible time a PID's current occupant started."""

import os
import re
import subprocess
import time


def _windows_start_time(pid: int) -> float | None:
    import _winapi
    import ctypes

    try:
        handle = _winapi.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    except OSError as error:
        if error.winerror == 87:  # ERROR_INVALID_PARAMETER for a missing PID
            return None
        raise
    try:
        if _winapi.GetExitCodeProcess(handle) != _winapi.STILL_ACTIVE:
            return None
        times = [ctypes.c_uint64() for _ in range(4)]  # creation, exit, kernel, user FILETIMEs
        query = ctypes.WinDLL("kernel32", use_last_error=True).GetProcessTimes
        if not query(ctypes.c_void_p(handle), *(ctypes.byref(value) for value in times)):
            raise ctypes.WinError(ctypes.get_last_error())
        return (times[0].value - 116444736000000000) / 10_000_000  # 1601 to Unix epoch
    finally:
        _winapi.CloseHandle(handle)


def pid_is_running(pid: int) -> bool:
    if pid < 1:
        return False
    if pid == os.getpid():
        return True
    if os.name == "nt":
        return _windows_start_time(pid) is not None
    try:
        os.kill(pid, 0)
    except OverflowError as error:
        raise ValueError(f"PID {pid} is outside the platform range") from error
    except ProcessLookupError:
        return False
    except PermissionError:
        pass
    return True


def process_started_after(pid: int, recorded_at: float) -> bool:
    if os.name == "nt":
        birth = _windows_start_time(pid)
    else:
        # POSIX etime is [[days-]hours:]minutes:seconds, truncated to a second.
        before = time.time()
        try:
            result = subprocess.run(["ps", "-p", str(pid), "-o", "etime="], capture_output=True, timeout=5)
        except subprocess.TimeoutExpired as exc:
            raise OSError(f"Timed out inspecting PID {pid}") from exc
        parts = re.fullmatch(rb"(?:(\d+)-)?(?:(\d+):)?(\d+):(\d+)", result.stdout.strip())
        if result.returncode or not parts:
            raise OSError(f"Unable to read elapsed time for PID {pid}")
        days, hours, minutes, seconds = (int(part or 0) for part in parts.groups())
        birth = before - (((days * 24 + hours) * 60 + minutes) * 60 + seconds + 1)
    # Legacy PID lock mtimes can have two-second filesystem resolution.
    return birth is not None and birth > recorded_at + 2
