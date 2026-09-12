"""Own a Windows command tree before allowing its first tool process to run.

The bootstrap waits for stdin EOF. The controller assigns it to a non-inherited
kill-on-close job, then sends the command. An exited launcher cannot detach its
descendants from that job; controller death also closes the last job handle.
See https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects.
"""

from __future__ import annotations

import ctypes
import json
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path


class _BasicLimits(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _ExtendedLimits(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BasicLimits),
        ("IoInfo", ctypes.c_ulonglong * 6),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class _Accounting(ctypes.Structure):
    _fields_ = [
        ("TotalUserTime", ctypes.c_longlong),
        ("TotalKernelTime", ctypes.c_longlong),
        ("ThisPeriodTotalUserTime", ctypes.c_longlong),
        ("ThisPeriodTotalKernelTime", ctypes.c_longlong),
        ("TotalPageFaultCount", wintypes.DWORD),
        ("TotalProcesses", wintypes.DWORD),
        ("ActiveProcesses", wintypes.DWORD),
        ("TotalTerminatedProcesses", wintypes.DWORD),
    ]


class WindowsJob:
    def __init__(self) -> None:
        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        signatures = {
            "CreateJobObjectW": ([ctypes.c_void_p, wintypes.LPCWSTR], wintypes.HANDLE),
            "SetInformationJobObject": (
                [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD], wintypes.BOOL,
            ),
            "AssignProcessToJobObject": ([wintypes.HANDLE, wintypes.HANDLE], wintypes.BOOL),
            "TerminateJobObject": ([wintypes.HANDLE, wintypes.UINT], wintypes.BOOL),
            "QueryInformationJobObject": (
                [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p], wintypes.BOOL,
            ),
            "CloseHandle": ([wintypes.HANDLE], wintypes.BOOL),
            "OpenProcess": ([wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
            "WaitForSingleObject": ([wintypes.HANDLE, wintypes.DWORD], wintypes.DWORD),
        }
        for name, (args, result) in signatures.items():
            function = getattr(self.api, name)
            function.argtypes = args
            function.restype = result
        self.handle = self.api.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = _ExtendedLimits()
        limits.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.api.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            error = ctypes.WinError(ctypes.get_last_error())
            self.close()
            raise error

    def start(
        self,
        command: list[str],
        *,
        cwd: Path,
        stdout,
        stderr,
        error_path: Path,
        stdin_path: Path | None = None,
    ) -> subprocess.Popen:
        # A venv redirector can spawn the real interpreter before assignment.
        # Start the base interpreter directly; the bootstrap needs only stdlib.
        interpreter = getattr(sys, "_base_executable", None) or sys.executable
        process = subprocess.Popen(
            [interpreter, "-I", str(Path(__file__).resolve()), str(error_path)],
            cwd=cwd, stdin=subprocess.PIPE, stdout=stdout, stderr=stderr,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        try:
            if not self.api.AssignProcessToJobObject(self.handle, int(process._handle)):
                raise ctypes.WinError(ctypes.get_last_error())
            # Nothing in the requested command runs before job membership exists.
            payload = {"command": command, "stdin": str(stdin_path) if stdin_path is not None else None}
            process.stdin.write(json.dumps(payload).encode("utf-8"))
            process.stdin.close()
        except BaseException:
            process.kill()
            process.wait(timeout=5)
            process.stdin.close()
            raise
        return process

    def terminate(self) -> None:
        handles = self._member_handles()
        deadline = time.monotonic() + 5
        try:
            if not self.api.TerminateJobObject(self.handle, 1):
                raise ctypes.WinError(ctypes.get_last_error())
            # ActiveProcesses reaches zero before all process handles become
            # signaled. Wait for member teardown as well as job accounting.
            for handle in handles:
                remaining_ms = max(0, int((deadline - time.monotonic()) * 1000))
                if self.api.WaitForSingleObject(handle, remaining_ms) != 0:
                    raise TimeoutError("owned process did not exit within cleanup grace")
            while True:
                accounting = _Accounting()
                if not self.api.QueryInformationJobObject(
                    self.handle, 1, ctypes.byref(accounting), ctypes.sizeof(accounting), None,
                ):
                    raise ctypes.WinError(ctypes.get_last_error())
                if not accounting.ActiveProcesses:
                    return
                if time.monotonic() >= deadline:
                    raise TimeoutError("owned job did not empty within cleanup grace")
                time.sleep(0.01)
        finally:
            for handle in handles:
                self.api.CloseHandle(handle)

    def _member_handles(self) -> list:
        capacity = 32
        while True:
            class ProcessIds(ctypes.Structure):
                _fields_ = [
                    ("assigned", wintypes.DWORD), ("count", wintypes.DWORD),
                    ("ids", ctypes.c_size_t * capacity),
                ]

            members = ProcessIds()
            if self.api.QueryInformationJobObject(
                self.handle, 3, ctypes.byref(members), ctypes.sizeof(members), None,
            ):
                break
            error = ctypes.get_last_error()
            if error != 234:  # ERROR_MORE_DATA
                raise ctypes.WinError(error)
            capacity = max(capacity * 2, members.assigned)
        handles = []
        for pid in members.ids[:members.count]:
            handle = self.api.OpenProcess(0x100000, False, pid)  # SYNCHRONIZE
            if handle:
                handles.append(handle)
        return handles

    def close(self) -> None:
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None


def _bootstrap() -> int:
    raw = sys.stdin.buffer.read()
    if not raw:  # Controller disappeared before granting ownership.
        return 1
    payload = json.loads(raw.decode("utf-8"))
    if isinstance(payload, list):  # Legacy payload: bare command list.
        command, stdin_source = payload, None
    else:
        command, stdin_source = payload["command"], payload.get("stdin")
    stdin = open(stdin_source, "rb") if stdin_source else subprocess.DEVNULL
    try:
        child = subprocess.Popen(command, stdin=stdin)
    except OSError as error:
        if stdin is not subprocess.DEVNULL:
            stdin.close()
        Path(sys.argv[1]).write_text(json.dumps({
            "errno": error.errno, "message": error.strerror,
            "filename": error.filename, "winerror": error.winerror,
        }), encoding="utf-8")
        return 1
    if stdin is not subprocess.DEVNULL:
        stdin.close()
    return child.wait()


if __name__ == "__main__":
    # sys.exit converts to a signed C long on some Python builds. Preserve
    # Windows DWORD statuses, including tool crash codes such as 0xC0000005.
    exit_code = _bootstrap()
    api = ctypes.WinDLL("kernel32")
    api.ExitProcess.argtypes = [wintypes.UINT]
    api.ExitProcess(exit_code & 0xFFFFFFFF)
