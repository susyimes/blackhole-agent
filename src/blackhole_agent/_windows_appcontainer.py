"""Launch an untrusted Windows command inside an AppContainer.

AppContainer tokens cannot open host files unless the container SID is on
the path's ACL. The invocation plane grants only the vendored tool tree, a
per-invocation scratch directory, and the interpreter prefix; everything
else — operator secrets, SSH keys, the served checkout, sibling temp
files — stays PermissionError. The profile name is versioned so leftover
NTFS ACEs from an earlier allowlist that included the workspace root do
not keep the checkout writable.

This module is imported by the job bootstrap (``python -I _windows_job.py``)
after the bootstrap inserts its own directory on ``sys.path``. It also
imports as ``blackhole_agent._windows_appcontainer`` from tests.
"""

from __future__ import annotations

import ctypes
import subprocess
import sys
from ctypes import wintypes
from pathlib import Path

HRESULT = ctypes.c_long
PSID = ctypes.c_void_p
PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES = 0x00020009
EXTENDED_STARTUPINFO_PRESENT = 0x00080000
CREATE_NO_WINDOW = 0x08000000
ERROR_ALREADY_EXISTS = 0x800700B7
STARTF_USESTDHANDLES = 0x00000100
STD_INPUT_HANDLE = wintypes.DWORD(-10).value
STD_OUTPUT_HANDLE = wintypes.DWORD(-11).value
STD_ERROR_HANDLE = wintypes.DWORD(-12).value
HANDLE_FLAG_INHERIT = 0x00000001
INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value

PROFILE_NAME = "bh.unbound.tool.v2"

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
userenv = ctypes.WinDLL("userenv", use_last_error=True)
advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)

userenv.CreateAppContainerProfile.restype = HRESULT
userenv.CreateAppContainerProfile.argtypes = [
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.POINTER(PSID),
]
userenv.DeriveAppContainerSidFromAppContainerName.restype = HRESULT
userenv.DeriveAppContainerSidFromAppContainerName.argtypes = [
    wintypes.LPCWSTR,
    ctypes.POINTER(PSID),
]
advapi32.ConvertSidToStringSidW.restype = wintypes.BOOL
advapi32.ConvertSidToStringSidW.argtypes = [PSID, ctypes.POINTER(wintypes.LPWSTR)]
kernel32.LocalFree.restype = ctypes.c_void_p
kernel32.LocalFree.argtypes = [ctypes.c_void_p]
kernel32.InitializeProcThreadAttributeList.restype = wintypes.BOOL
kernel32.InitializeProcThreadAttributeList.argtypes = [
    ctypes.c_void_p,
    wintypes.DWORD,
    wintypes.DWORD,
    ctypes.POINTER(ctypes.c_size_t),
]
kernel32.UpdateProcThreadAttribute.restype = wintypes.BOOL
kernel32.UpdateProcThreadAttribute.argtypes = [
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_size_t,
    ctypes.c_void_p,
    ctypes.c_void_p,
]
kernel32.DeleteProcThreadAttributeList.restype = None
kernel32.DeleteProcThreadAttributeList.argtypes = [ctypes.c_void_p]
kernel32.WaitForSingleObject.restype = wintypes.DWORD
kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
kernel32.GetExitCodeProcess.restype = wintypes.BOOL
kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.GetStdHandle.restype = wintypes.HANDLE
kernel32.GetStdHandle.argtypes = [wintypes.DWORD]
kernel32.SetHandleInformation.restype = wintypes.BOOL
kernel32.SetHandleInformation.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD]


class SECURITY_CAPABILITIES(ctypes.Structure):
    _fields_ = [
        ("AppContainerSid", PSID),
        ("Capabilities", ctypes.c_void_p),
        ("CapabilityCount", wintypes.DWORD),
        ("Reserved", wintypes.DWORD),
    ]


class STARTUPINFOW(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("lpReserved", wintypes.LPWSTR),
        ("lpDesktop", wintypes.LPWSTR),
        ("lpTitle", wintypes.LPWSTR),
        ("dwX", wintypes.DWORD),
        ("dwY", wintypes.DWORD),
        ("dwXSize", wintypes.DWORD),
        ("dwYSize", wintypes.DWORD),
        ("dwXCountChars", wintypes.DWORD),
        ("dwYCountChars", wintypes.DWORD),
        ("dwFillAttribute", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("wShowWindow", wintypes.WORD),
        ("cbReserved2", wintypes.WORD),
        ("lpReserved2", ctypes.c_void_p),
        ("hStdInput", wintypes.HANDLE),
        ("hStdOutput", wintypes.HANDLE),
        ("hStdError", wintypes.HANDLE),
    ]


class STARTUPINFOEXW(ctypes.Structure):
    _fields_ = [
        ("StartupInfo", STARTUPINFOW),
        ("lpAttributeList", ctypes.c_void_p),
    ]


class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("hProcess", wintypes.HANDLE),
        ("hThread", wintypes.HANDLE),
        ("dwProcessId", wintypes.DWORD),
        ("dwThreadId", wintypes.DWORD),
    ]


kernel32.CreateProcessW.restype = wintypes.BOOL
kernel32.CreateProcessW.argtypes = [
    wintypes.LPCWSTR,
    wintypes.LPWSTR,
    ctypes.c_void_p,
    ctypes.c_void_p,
    wintypes.BOOL,
    wintypes.DWORD,
    ctypes.c_void_p,
    wintypes.LPCWSTR,
    ctypes.c_void_p,
    ctypes.POINTER(PROCESS_INFORMATION),
]


_granted: set[tuple[str, str, str]] = set()


def _hresult_code(hr: int) -> int:
    return hr & 0xFFFFFFFF


def ensure_profile_sid() -> PSID:
    sid = PSID()
    hr = userenv.CreateAppContainerProfile(
        PROFILE_NAME, PROFILE_NAME, PROFILE_NAME, None, 0, ctypes.byref(sid)
    )
    code = _hresult_code(hr)
    if code == 0:
        return sid
    if code == ERROR_ALREADY_EXISTS or hr == -2147024713:
        sid = PSID()
        derived = userenv.DeriveAppContainerSidFromAppContainerName(
            PROFILE_NAME, ctypes.byref(sid)
        )
        if _hresult_code(derived) != 0:
            raise OSError(
                f"DeriveAppContainerSidFromAppContainerName failed hr=0x{_hresult_code(derived):08X}"
            )
        return sid
    raise OSError(f"CreateAppContainerProfile failed hr=0x{code:08X}")


def sid_string(sid: PSID) -> str:
    text = wintypes.LPWSTR()
    if not advapi32.ConvertSidToStringSidW(sid, ctypes.byref(text)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return str(text.value)
    finally:
        kernel32.LocalFree(text)


def grant_path(sid: str, path: Path, spec: str) -> None:
    resolved = Path(path).resolve()
    if not resolved.exists():
        return
    key = (sid, str(resolved).lower(), spec)
    if key in _granted:
        return
    completed = subprocess.run(
        ["icacls", str(resolved), "/grant", f"*{sid}:{spec}", "/Q"],
        capture_output=True,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or b"").decode("mbcs", errors="replace")
        raise OSError(f"icacls grant failed on {resolved}: {detail.strip()}")
    _granted.add(key)


def _inherit(handle: int) -> None:
    if not handle or handle == INVALID_HANDLE_VALUE:
        return
    kernel32.SetHandleInformation(handle, HANDLE_FLAG_INHERIT, HANDLE_FLAG_INHERIT)


def spawn_and_wait(
    command: list[str] | str,
    *,
    cwd: Path,
    stdin_path: str | None,
    shell: bool,
    rw_paths: list[str],
    rx_paths: list[str],
) -> int:
    """Create an AppContainer child, wait, and return its exit code.

    Standard output/error are the calling process's current handles (the job
    bootstrap's capture files). Standard input is ``stdin_path`` when given.
    The child inherits the bootstrap environment; do not pass a custom block
    (CreateProcess rejects some constructed Unicode blocks with error 203).
    """

    sid = ensure_profile_sid()
    sid_text = sid_string(sid)
    for raw in rw_paths:
        grant_path(sid_text, Path(raw), "(OI)(CI)(F)")
    for raw in rx_paths:
        grant_path(sid_text, Path(raw), "(OI)(CI)(RX)")

    if shell:
        comspec = str(Path(r"C:\Windows\System32\cmd.exe"))
        argv = [comspec, "/c", command if isinstance(command, str) else subprocess.list2cmdline(command)]
    else:
        argv = [str(part) for part in command]
    if not argv:
        raise OSError("sandboxed command is empty")
    exe = argv[0]
    cmdline = subprocess.list2cmdline(argv)
    cmd_buf = ctypes.create_unicode_buffer(cmdline)

    stdin_file = open(stdin_path, "rb") if stdin_path else None
    try:
        import msvcrt

        if stdin_file is not None:
            h_in = msvcrt.get_osfhandle(stdin_file.fileno())
        else:
            h_in = kernel32.GetStdHandle(STD_INPUT_HANDLE)
        h_out = kernel32.GetStdHandle(STD_OUTPUT_HANDLE)
        h_err = kernel32.GetStdHandle(STD_ERROR_HANDLE)
        for handle in (h_in, h_out, h_err):
            _inherit(handle)

        caps = SECURITY_CAPABILITIES()
        caps.AppContainerSid = sid
        size = ctypes.c_size_t(0)
        kernel32.InitializeProcThreadAttributeList(None, 1, 0, ctypes.byref(size))
        buf = ctypes.create_string_buffer(size.value)
        if not kernel32.InitializeProcThreadAttributeList(buf, 1, 0, ctypes.byref(size)):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            if not kernel32.UpdateProcThreadAttribute(
                buf,
                0,
                PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES,
                ctypes.byref(caps),
                ctypes.sizeof(caps),
                None,
                None,
            ):
                raise ctypes.WinError(ctypes.get_last_error())
            si = STARTUPINFOEXW()
            si.StartupInfo.cb = ctypes.sizeof(STARTUPINFOEXW)
            si.StartupInfo.dwFlags = STARTF_USESTDHANDLES
            si.StartupInfo.hStdInput = h_in
            si.StartupInfo.hStdOutput = h_out
            si.StartupInfo.hStdError = h_err
            si.lpAttributeList = ctypes.cast(buf, ctypes.c_void_p)
            pi = PROCESS_INFORMATION()
            ok = kernel32.CreateProcessW(
                exe,
                cmd_buf,
                None,
                None,
                True,
                EXTENDED_STARTUPINFO_PRESENT | CREATE_NO_WINDOW,
                None,
                str(cwd),
                ctypes.byref(si),
                ctypes.byref(pi),
            )
            if not ok:
                raise ctypes.WinError(ctypes.get_last_error())
            try:
                kernel32.WaitForSingleObject(pi.hProcess, 0xFFFFFFFF)
                code = wintypes.DWORD()
                kernel32.GetExitCodeProcess(pi.hProcess, ctypes.byref(code))
                return int(code.value)
            finally:
                kernel32.CloseHandle(pi.hThread)
                kernel32.CloseHandle(pi.hProcess)
        finally:
            kernel32.DeleteProcThreadAttributeList(buf)
    finally:
        if stdin_file is not None:
            stdin_file.close()


def interpreter_rx_paths() -> list[Path]:
    """Directories the AppContainer must be able to read to start Python."""

    base = Path(getattr(sys, "_base_executable", None) or sys.executable).resolve()
    paths = [base.parent]
    prefix = Path(getattr(sys, "base_prefix", sys.prefix) or sys.prefix)
    if prefix.exists():
        paths.append(prefix.resolve())
    exe = Path(sys.executable).resolve()
    if exe.parent not in {p.resolve() for p in paths}:
        paths.append(exe.parent)
    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path).lower()
        if key in seen or not path.exists():
            continue
        seen.add(key)
        unique.append(path)
    return unique
