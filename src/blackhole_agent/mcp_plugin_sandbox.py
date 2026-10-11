"""Sandbox hosted MCP plugin processes on the live invocation plane.

Opted-in stdio plugins start under a scrubbed environment, an isolated
scratch cwd, and a resource job. That still left the plugin outside the OS
filesystem sandbox used for absorbed tools, so a plugin that opened an
absolute host path could read operator files and a plugin that opened a
TCP socket could exfiltrate tool arguments.

This module closes that hole:

- scrub the plugin environment to the absorbed-tool allowlist
- run each plugin in an isolated scratch cwd (not the repository)
- own the process tree with a Windows job when available
- wrap the plugin in the AppContainer / Landlock envelope (scratch
  writable, interpreter and plugin code read/execute, host files denied)
- on Windows, use a dedicated AppContainer profile with no network
  capabilities so loopback exfil is blocked the same way absorbed tools are
- leave ``POST /invoke`` of a well-behaved echo plugin working
- keep a fail-closed plane without ``--mcp-plugin``

The module is also a hermetic stdio MCP fixture (``echo``, ``env_probe``,
``write_probe``, ``read_probe``, ``net_probe``) used by the live acceptance
probes. ``python -m blackhole_agent.mcp_plugin_sandbox launch CONFIG``
is the Windows AppContainer stdio trampoline.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence, TextIO

from blackhole_agent.capability_absorption import tool_execution_env

SCHEMA_VERSION = 1
CANARY_ENV_KEY = "BH_PROBE_PLUGIN_SECRET"
WRITE_MARKER = "plugin-sandbox-pwned-20d13648.txt"
PLUGIN_MEMORY_LIMIT_BYTES = 256 << 20
PLUGIN_MAX_PROCESSES = 32
PROTOCOL_VERSION = "2025-03-26"
SERVER_INFO = {"name": "blackhole-plugin-sandbox-mcp", "version": "1.0.0"}
LAUNCH_CONFIG_NAME = "os-sandbox.json"
NET_PROBE_TIMEOUT_SECONDS = 1.5

_INTERPRETER_ENV = (
    "PYTHONPATH",
    "PYTHONHOME",
    "VIRTUAL_ENV",
    "PYTHONUTF8",
    "PYTHONEXECUTABLE",
    "PYTHONIOENCODING",
)
# AppContainer CreateProcess looks up identity/profile variables and fails
# with ERROR_ENVVAR_NOT_FOUND (203) when they are absent. Same allowlist as
# process_capture.run_captured_process for sandboxed tools.
_APPCONTAINER_IDENTITY_ENV = (
    "PATH",
    "PATHEXT",
    "SYSTEMROOT",
    "SYSTEMDRIVE",
    "WINDIR",
    "COMSPEC",
    "HOME",
    "HOMEDRIVE",
    "HOMEPATH",
    "USERPROFILE",
    "USERNAME",
    "USERDOMAIN",
    "APPDATA",
    "LOCALAPPDATA",
    "ALLUSERSPROFILE",
    "PROGRAMDATA",
    "PUBLIC",
    "COMPUTERNAME",
    "OS",
    "PROCESSOR_ARCHITECTURE",
    "NUMBER_OF_PROCESSORS",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
)

TOOLS: list[dict[str, Any]] = [
    {
        "name": "echo",
        "description": "Return the supplied text unchanged.",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "env_probe",
        "description": "Report whether operator secrets leaked into the plugin environment.",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "write_probe",
        "description": "Try to write a marker file in the plugin working directory.",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
        "annotations": {"readOnlyHint": False},
    },
    {
        "name": "read_probe",
        "description": "Try to read an absolute host path from the plugin process.",
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "net_probe",
        "description": "Try to TCP-connect from the plugin process and send a payload.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "host": {"type": "string"},
                "port": {"type": "integer"},
                "payload": {"type": "string"},
            },
            "required": ["host", "port", "payload"],
        },
        "annotations": {"readOnlyHint": False},
    },
]


def plugin_sandbox_env(scratch: Path) -> dict[str, str]:
    """Scrubbed env: runtime PATH plus interpreter path, never operator secrets."""

    extra: dict[str, str] = {}
    for key in _INTERPRETER_ENV:
        value = os.environ.get(key)
        if value:
            extra[key] = value
    extra["PYTHONNOUSERSITE"] = "1"
    extra["PYTHONDONTWRITEBYTECODE"] = "1"
    extra["PYTHONIOENCODING"] = "utf-8"
    extra["PYTHONUNBUFFERED"] = "1"
    folder = str(Path(scratch).resolve())
    extra["TEMP"] = folder
    extra["TMP"] = folder
    extra["TMPDIR"] = folder
    extra["HOME"] = folder
    extra["USERPROFILE"] = folder
    env = tool_execution_env(extra)
    env["TEMP"] = folder
    env["TMP"] = folder
    env["TMPDIR"] = folder
    env["HOME"] = folder
    env["USERPROFILE"] = folder
    if os.name == "nt":
        for key in _APPCONTAINER_IDENTITY_ENV:
            if key not in env and key in os.environ:
                env[key] = os.environ[key]
        drive, tail = os.path.splitdrive(folder)
        if drive:
            env["HOMEDRIVE"] = drive
            env["HOMEPATH"] = tail or "\\"
        env["TEMP"] = folder
        env["TMP"] = folder
        env["TMPDIR"] = folder
        env["HOME"] = folder
        env["USERPROFILE"] = folder
    return env


def plugin_command_rx_paths(
    command: Sequence[str],
    env: Mapping[str, str],
) -> list[Path]:
    """Host paths the contained plugin must be able to read to start."""

    paths: list[Path] = []
    for part in command:
        candidate = Path(str(part))
        try:
            if candidate.exists():
                resolved = candidate.resolve()
                paths.append(resolved)
                if resolved.is_file():
                    paths.append(resolved.parent)
        except OSError:
            continue
    for key in ("PYTHONPATH", "PYTHONHOME"):
        raw = str(env.get(key) or "")
        for entry in raw.split(os.pathsep):
            if not entry.strip():
                continue
            candidate = Path(entry)
            try:
                if candidate.exists():
                    paths.append(candidate.resolve())
            except OSError:
                continue
    try:
        import blackhole_agent as package

        package_root = Path(package.__file__).resolve().parent
        paths.append(package_root)
        paths.append(package_root.parent)
    except Exception:
        pass
    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path).lower() if os.name == "nt" else str(path)
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def _posix_unshare_net() -> None:
    """Best-effort empty network namespace so host loopback is unreachable."""

    try:
        import ctypes

        libc = ctypes.CDLL(None, use_errno=True)
        clone_newnet = 0x40000000
        libc.unshare.argtypes = [ctypes.c_int]
        libc.unshare.restype = ctypes.c_int
        libc.unshare(clone_newnet)
    except Exception:
        return


def _posix_plugin_preexec(rw_paths: Sequence[str], rx_paths: Sequence[str]):
    from blackhole_agent.process_capture import _posix_sandbox_preexec

    landlock = _posix_sandbox_preexec(rw_paths, rx_paths)

    def apply() -> None:
        _posix_unshare_net()
        landlock()

    return apply


def _contained_plugin_argv(command: Sequence[str]) -> list[str]:
    from blackhole_agent.process_capture import _resolve_sandbox_command

    resolved = _resolve_sandbox_command([str(part) for part in command])
    if isinstance(resolved, str):
        return [resolved]
    return [str(part) for part in resolved]


def launch_os_sandboxed_plugin(config_path: str) -> int:
    """Windows trampoline: inherit stdio, spawn the plugin inside AppContainer."""

    payload = json.loads(Path(config_path).read_text(encoding="utf-8"))
    command = payload.get("command")
    if not isinstance(command, list) or not command:
        raise ValueError("os-sandbox config command must be a non-empty argv list")
    from blackhole_agent._windows_appcontainer import PLUGIN_PROFILE_NAME, spawn_and_wait

    return spawn_and_wait(
        [str(part) for part in command],
        cwd=Path(str(payload.get("cwd") or Path.cwd())),
        stdin_path=None,
        shell=False,
        rw_paths=[str(path) for path in (payload.get("rw_paths") or [])],
        rx_paths=[str(path) for path in (payload.get("rx_paths") or [])],
        profile_name=str(payload.get("profile_name") or PLUGIN_PROFILE_NAME),
    )


@dataclass
class SandboxedPluginProcess:
    """Live plugin Popen plus the job/stderr/scratch that outlive handshake."""

    process: subprocess.Popen[str]
    job: Any = None
    stderr: TextIO | None = None
    scratch: Path | None = None
    os_sandboxed: bool = False

    def close_aux(self) -> None:
        if self.job is not None:
            try:
                self.job.terminate()
            except Exception:
                pass
            try:
                self.job.close()
            except Exception:
                pass
            self.job = None
        if self.stderr is not None:
            try:
                self.stderr.close()
            except Exception:
                pass
            self.stderr = None


def spawn_sandboxed_plugin(
    command: Sequence[str],
    scratch: Path,
) -> SandboxedPluginProcess:
    """Start one stdio MCP plugin under scrubbed env, isolated cwd, job, and OS sandbox."""

    folder = Path(scratch).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    env = plugin_sandbox_env(folder)
    stderr_path = folder / "plugin-stderr.txt"
    stderr = stderr_path.open("w", encoding="utf-8", errors="replace")
    argv = [str(part) for part in command]
    kwargs: dict[str, Any] = {
        "stdin": subprocess.PIPE,
        "stdout": subprocess.PIPE,
        "stderr": stderr,
        "text": True,
        "encoding": "utf-8",
        "cwd": str(folder),
        "env": env,
    }
    if os.name == "nt":
        kwargs["creationflags"] = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
    else:
        kwargs["start_new_session"] = True

    os_sandboxed = False
    spawn_argv = argv
    from blackhole_agent.process_capture import (
        _sandbox_path_payload,
        filesystem_sandbox_available,
    )

    if filesystem_sandbox_available():
        contained = _contained_plugin_argv(argv)
        extra_rx = plugin_command_rx_paths(contained, env)
        if contained:
            try:
                extra_rx.append(Path(contained[0]).resolve().parent)
            except OSError:
                pass
        payload = _sandbox_path_payload(
            folder,
            extra_rx,
            folder,
        )
        if os.name == "nt":
            from blackhole_agent._windows_appcontainer import PLUGIN_PROFILE_NAME

            config_path = folder / LAUNCH_CONFIG_NAME
            config_path.write_text(
                json.dumps(
                    {
                        "command": contained,
                        "cwd": str(folder),
                        "rw_paths": payload["rw_paths"],
                        "rx_paths": payload["rx_paths"],
                        "profile_name": PLUGIN_PROFILE_NAME,
                    }
                ),
                encoding="utf-8",
            )
            spawn_argv = [
                sys.executable,
                "-u",
                "-m",
                "blackhole_agent.mcp_plugin_sandbox",
                "launch",
                str(config_path),
            ]
            os_sandboxed = True
        else:
            kwargs["preexec_fn"] = _posix_plugin_preexec(
                payload["rw_paths"], payload["rx_paths"]
            )
            spawn_argv = contained
            os_sandboxed = True

    try:
        process = subprocess.Popen(spawn_argv, **kwargs)
    except Exception:
        stderr.close()
        raise
    job = None
    if os.name == "nt":
        try:
            from blackhole_agent._windows_job import WindowsJob

            job = WindowsJob(
                memory_bytes=PLUGIN_MEMORY_LIMIT_BYTES,
                max_processes=PLUGIN_MAX_PROCESSES,
            )
            handle = getattr(process, "_handle", None)
            if handle is None:
                raise OSError("plugin process has no Windows handle")
            if not job.api.AssignProcessToJobObject(job.handle, int(handle)):
                raise OSError("AssignProcessToJobObject failed")
        except Exception:
            if job is not None:
                try:
                    job.close()
                except Exception:
                    pass
            job = None
    return SandboxedPluginProcess(
        process=process,
        job=job,
        stderr=stderr,
        scratch=folder,
        os_sandboxed=os_sandboxed,
    )


def sandbox_plugin_command() -> list[str]:
    return [sys.executable, "-u", "-m", "blackhole_agent.mcp_plugin_sandbox"]


def _text_content(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "isError": False}


def _call_tool(name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
    text = str(arguments.get("text") or "")
    if name == "echo":
        return _text_content(text)
    if name == "env_probe":
        payload = {
            "blackhole_keys": sorted(
                key
                for key in os.environ
                if key.startswith("BLACKHOLE_") or key.startswith("BH_PROBE_")
            ),
            "cwd": os.getcwd(),
            "has_path": bool(os.environ.get("PATH")),
            "observed_secret": os.environ.get(CANARY_ENV_KEY),
        }
        return _text_content(json.dumps(payload, sort_keys=True))
    if name == "write_probe":
        cwd = Path.cwd()
        marker = cwd / WRITE_MARKER
        wrote = False
        error = ""
        try:
            marker.write_text("pwned", encoding="utf-8")
            wrote = marker.is_file()
        except OSError as exc:
            error = f"{type(exc).__name__}: {exc}"
        payload = {
            "cwd": str(cwd),
            "error": error,
            "marker": str(marker),
            "wrote": wrote,
        }
        return _text_content(json.dumps(payload, sort_keys=True))
    if name == "read_probe":
        target = Path(str(arguments.get("path") or ""))
        payload = {"path": str(target), "readable": False, "text": "", "error": ""}
        try:
            payload["text"] = target.read_text(encoding="utf-8")
            payload["readable"] = True
        except Exception as exc:
            payload["error"] = type(exc).__name__
        return _text_content(json.dumps(payload, sort_keys=True))
    if name == "net_probe":
        import socket

        host = str(arguments.get("host") or "")
        try:
            port = int(arguments.get("port"))
        except (TypeError, ValueError):
            port = -1
        data = str(arguments.get("payload") or "").encode("utf-8")
        payload = {"connected": False, "error": ""}
        try:
            with socket.create_connection((host, port), timeout=NET_PROBE_TIMEOUT_SECONDS) as sock:
                sock.sendall(data)
                payload["connected"] = True
        except Exception as exc:
            payload["error"] = type(exc).__name__
        return _text_content(json.dumps(payload, sort_keys=True))
    raise KeyError(name)


def handle_message(message: Mapping[str, Any]) -> dict[str, Any] | None:
    """Handle one JSON-RPC message; return the response or None for notifications."""

    method = message.get("method")
    if method == "notifications/initialized" or method is None and "id" not in message:
        return None
    if "id" not in message:
        return None
    request_id = message["id"]
    params = message.get("params") or {}
    try:
        if method == "initialize":
            result: Any = {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": True}},
                "serverInfo": SERVER_INFO,
            }
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            result = _call_tool(str(params.get("name") or ""), params.get("arguments") or {})
        else:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32601, "message": f"method not found: {method}"},
            }
    except KeyError as error:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32602, "message": f"unknown tool: {error.args[0]}"},
        }
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) >= 2 and args[0] == "launch":
        try:
            return int(launch_os_sandboxed_plugin(args[1]))
        except Exception as exc:
            sys.stderr.write(f"plugin os-sandbox launch failed: {type(exc).__name__}: {exc}\n")
            return 1
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(message, dict):
            continue
        response = handle_message(message)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
