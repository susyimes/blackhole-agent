"""Sandbox hosted MCP plugin processes on the live invocation plane.

Opted-in stdio plugins currently start via bare ``Popen`` with the plane
environment, a writable repository cwd, and no job bounds, so a plugin can
read operator secrets such as ``BLACKHOLE_INVOCATION_TOKEN`` and write the
workspace. This module closes that hole:

- scrub the plugin environment to the absorbed-tool allowlist
- run each plugin in an isolated scratch cwd (not the repository)
- own the process tree with a Windows job when available
- leave ``POST /invoke`` of a well-behaved echo plugin working
- keep a fail-closed plane without ``--mcp-plugin``

The module is also a hermetic stdio MCP fixture (``echo``, ``env_probe``,
``write_probe``) used by the live acceptance probe.
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

_INTERPRETER_ENV = (
    "PYTHONPATH",
    "PYTHONHOME",
    "VIRTUAL_ENV",
    "PYTHONUTF8",
    "PYTHONEXECUTABLE",
    "PYTHONIOENCODING",
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
        drive, tail = os.path.splitdrive(folder)
        if drive:
            env["HOMEDRIVE"] = drive
            env["HOMEPATH"] = tail or "\\"
    return env


@dataclass
class SandboxedPluginProcess:
    """Live plugin Popen plus the job/stderr/scratch that outlive handshake."""

    process: subprocess.Popen[str]
    job: Any = None
    stderr: TextIO | None = None
    scratch: Path | None = None

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
    """Start one stdio MCP plugin under scrubbed env, isolated cwd, and a job."""

    folder = Path(scratch).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    env = plugin_sandbox_env(folder)
    stderr_path = folder / "plugin-stderr.txt"
    stderr = stderr_path.open("w", encoding="utf-8", errors="replace")
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
    process = subprocess.Popen([str(part) for part in command], **kwargs)
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
    return SandboxedPluginProcess(process=process, job=job, stderr=stderr, scratch=folder)


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


def main() -> int:
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
