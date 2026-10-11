"""Expose opted-in hosted MCP plugin tools on the live invocation plane.

GET /capabilities and POST /invoke currently list and run only vendored
absorbed Python tools. A live stdio MCP plugin — Gmail, a reference echo
server, any spec-compliant command — never appears as an invocable
capability, so an operator cannot POST /invoke its tools.

This module closes that hole:

- ``--mcp-plugin`` (or ``BLACKHOLE_MCP_PLUGIN``) opts a stdio MCP server in
- the plane lists each plugin tool as ``capability.mcp-plugin-{name}``
- ``POST /invoke`` (and MCP ``tools/call``) executes the plugin's
  ``tools/call``
- a plane with no plugin stays fail-closed: the id is unknown (HTTP 404)
- sibling absorbed tools keep serving
- HTTP disconnect cancel is forwarded as ``notifications/cancelled``
- hosted plugin processes start under a scrubbed environment, an isolated
  scratch cwd, and a resource job so they cannot read operator secrets or
  write the repository
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import sys
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from blackhole_agent.mcp_client import (
    McpProtocolError,
    McpStdioSession,
    _extract_text,
    echo_server_command,
)
from blackhole_agent.mcp_plugin_sandbox import (
    SandboxedPluginProcess,
    spawn_sandboxed_plugin,
)
from blackhole_agent.process_capture import ProcessCancelled

SCHEMA_VERSION = 1
PLUGIN_ID_PREFIX = "capability.mcp-plugin-"
PLUGIN_KIND = "mcp-plugin"
MCP_PLUGIN_ENV = "BLACKHOLE_MCP_PLUGIN"
_TOOL_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class PluginStartError(RuntimeError):
    """Raised when an opted-in MCP plugin cannot complete initialize."""

    def __init__(self, detail: str) -> None:
        self.payload = {
            "ok": False,
            "error": "mcp_plugin_start_failed",
            "detail": str(detail),
        }
        super().__init__(detail)


def parse_mcp_plugin_command(raw: str) -> list[str]:
    """Parse one ``--mcp-plugin`` value: JSON argv or a shell command string."""

    text = str(raw or "").strip()
    if not text:
        raise ValueError("mcp plugin command is empty")
    if text.startswith("["):
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"mcp plugin command is not JSON argv: {exc}") from exc
        if not isinstance(payload, list) or not payload:
            raise ValueError("mcp plugin command JSON must be a non-empty argv list")
        return [str(part) for part in payload]
    posix = os.name != "nt"
    parts = shlex.split(text, posix=posix)
    if not parts:
        raise ValueError("mcp plugin command is empty")
    return parts


def resolve_mcp_plugin_commands(
    raw_commands: Sequence[str] | None = None,
    *,
    env: Mapping[str, str] | None = None,
) -> list[list[str]]:
    """Collect opted-in plugin argv lists from CLI flags and the process env."""

    commands: list[list[str]] = []
    for raw in raw_commands or ():
        commands.append(parse_mcp_plugin_command(str(raw)))
    if commands:
        return commands
    source = env if env is not None else os.environ
    text = str(source.get(MCP_PLUGIN_ENV) or "").strip()
    if not text:
        return []
    if text.startswith("[["):
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{MCP_PLUGIN_ENV} is not JSON: {exc}") from exc
        if not isinstance(payload, list) or not payload:
            raise ValueError(f"{MCP_PLUGIN_ENV} must be a non-empty list of argv lists")
        resolved: list[list[str]] = []
        for item in payload:
            if not isinstance(item, list) or not item:
                raise ValueError(f"{MCP_PLUGIN_ENV} entries must be non-empty argv lists")
            resolved.append([str(part) for part in item])
        return resolved
    return [parse_mcp_plugin_command(text)]


def _normalized_plugin_command(command: Sequence[str]) -> list[str]:
    parts = [str(part) for part in command]
    if parts and parts[0] in {"python", "python3", "python.exe"}:
        parts[0] = sys.executable
    return parts


def capability_id_for_plugin_tool(name: str, *, taken: set[str]) -> str:
    """Stable capability id; digest suffix only when a name collides."""

    slug = str(name or "").strip()
    if not _TOOL_NAME_RE.match(slug):
        slug = re.sub(r"[^A-Za-z0-9_-]+", "-", slug).strip("-")[:64] or "tool"
    candidate = f"{PLUGIN_ID_PREFIX}{slug}"
    if candidate not in taken:
        return candidate
    digest = __import__("hashlib").sha256(slug.encode("utf-8")).hexdigest()[:8]
    return f"{PLUGIN_ID_PREFIX}{slug[:48]}-{digest}"


def _requires_from_schema(schema: Mapping[str, Any] | None) -> list[str]:
    payload = dict(schema or {})
    required = payload.get("required")
    if isinstance(required, list) and required:
        return [str(key) for key in required]
    properties = payload.get("properties")
    if isinstance(properties, Mapping) and properties:
        return sorted(str(key) for key in properties)
    return ["text"]


@dataclass
class PluginTool:
    """One MCP plugin tool bound as an invocable capability."""

    capability_id: str
    tool_name: str
    session: McpStdioSession
    schema: dict[str, Any] = field(default_factory=dict)
    description: str = ""

    @property
    def requires(self) -> list[str]:
        return _requires_from_schema(self.schema)

    def listing_item(self) -> dict[str, Any]:
        slug = self.capability_id[len(PLUGIN_ID_PREFIX) :]
        return {
            "id": self.capability_id,
            "slug": slug,
            "name": self.description or self.tool_name,
            "requires": self.requires,
            "provides": ["text"],
            "kind": PLUGIN_KIND,
            "plugin_tool": self.tool_name,
            "sandboxed": True,
            "command": [],
            "tool_root": "",
            "input_schema": dict(self.schema) if self.schema else None,
            "quarantine": None,
            "limits_override": None,
        }


class McpPluginPlane:
    """Live stdio MCP sessions whose tools are invocable on POST /invoke."""

    def __init__(self, commands: Sequence[Sequence[str]]) -> None:
        self.commands = [_normalized_plugin_command(item) for item in commands]
        self.sessions: list[McpStdioSession] = []
        self.tools: dict[str, PluginTool] = {}
        self._lock = threading.Lock()
        self.ready = False
        self.sandboxed = False
        self._spawned: list[SandboxedPluginProcess] = []
        self._scratch_root: Path | None = None

    @property
    def tool_count(self) -> int:
        return len(self.tools)

    def start(self) -> "McpPluginPlane":
        if not self.commands:
            self.sandboxed = True
            return self
        try:
            self._scratch_root = Path(tempfile.mkdtemp(prefix="bh-mcp-plugin-"))
            for index, command in enumerate(self.commands):
                plugin_scratch = self._scratch_root / f"p{index}"
                spawned = spawn_sandboxed_plugin(command, plugin_scratch)
                self._spawned.append(spawned)
                session = McpStdioSession(
                    command,
                    timeout_seconds=30.0,
                    process=spawned.process,
                    env=None,
                    cwd=str(plugin_scratch),
                )
                session.start()
                payload = session.paginate_tools()
                tools = payload.get("tools") if isinstance(payload, Mapping) else None
                if not isinstance(tools, list) or not tools:
                    raise PluginStartError(f"plugin listed no tools: {command!r}")
                self.sessions.append(session)
                taken = set(self.tools)
                for raw in tools:
                    if not isinstance(raw, Mapping):
                        continue
                    name = str(raw.get("name") or "").strip()
                    if not name:
                        continue
                    schema = raw.get("inputSchema")
                    capability_id = capability_id_for_plugin_tool(name, taken=taken)
                    taken.add(capability_id)
                    self.tools[capability_id] = PluginTool(
                        capability_id=capability_id,
                        tool_name=name,
                        session=session,
                        schema=dict(schema) if isinstance(schema, Mapping) else {},
                        description=str(raw.get("description") or name),
                    )
            if not self.tools:
                raise PluginStartError("opted-in plugins listed no invocable tools")
            self.ready = True
            self.sandboxed = True
            return self
        except (McpProtocolError, OSError, PluginStartError) as exc:
            self.close()
            if isinstance(exc, PluginStartError):
                raise
            raise PluginStartError(str(exc)) from exc

    def close(self) -> None:
        self.ready = False
        self.sandboxed = False
        sessions = list(self.sessions)
        self.sessions.clear()
        self.tools.clear()
        for session in sessions:
            try:
                session.close()
            except Exception:
                try:
                    session.kill()
                except Exception:
                    pass
        spawned = list(self._spawned)
        self._spawned.clear()
        for item in spawned:
            try:
                item.close_aux()
            except Exception:
                pass
        scratch = self._scratch_root
        self._scratch_root = None
        if scratch is not None:
            shutil.rmtree(scratch, ignore_errors=True)

    def invocable_items(self) -> dict[str, dict[str, Any]]:
        if not self.ready:
            return {}
        return {item.capability_id: item.listing_item() for item in self.tools.values()}

    def invoke(
        self,
        capability_id: str,
        provided_input: Mapping[str, Any],
        *,
        timeout: int | None = None,
        cancel_event: threading.Event | None = None,
        output_listener: Callable[[str, str], None] | None = None,
    ) -> dict[str, Any]:
        """Execute one plugin tool and return the invocation-plane payload."""

        del output_listener  # plugin stdio is JSON-RPC; live chunks ride MCP logs
        if cancel_event is not None and cancel_event.is_set():
            raise ProcessCancelled()
        with self._lock:
            tool = self.tools.get(str(capability_id))
        if tool is None or not self.ready:
            raise KeyError(capability_id)
        if timeout is not None:
            tool.session.timeout_seconds = float(timeout)
        result = tool.session.call_tool(
            tool.tool_name,
            dict(provided_input),
            cancel_event=cancel_event,
        )
        if result.get("isError"):
            detail = _extract_text(result) or "plugin tool returned isError"
            raise McpProtocolError(detail)
        text = _extract_text(result)
        output: dict[str, Any] = {"text": text}
        structured = result.get("structuredContent")
        if isinstance(structured, Mapping) and "text" in structured:
            output["text"] = structured.get("text")
        return {
            "ok": True,
            "capability_id": capability_id,
            "output": output,
            "plugin_tool": tool.tool_name,
        }


_PLANE_LOCK = threading.Lock()
_PLANE: McpPluginPlane | None = None


def configure_mcp_plugin_plane(plane: McpPluginPlane | None) -> None:
    """Install or clear the process-wide plugin plane; close the previous one."""

    global _PLANE
    with _PLANE_LOCK:
        previous = _PLANE
        _PLANE = plane
    if previous is not None and previous is not plane:
        previous.close()


def active_mcp_plugin_plane() -> McpPluginPlane | None:
    with _PLANE_LOCK:
        return _PLANE


def mcp_plugin_health() -> dict[str, Any]:
    plane = active_mcp_plugin_plane()
    ready = bool(plane is not None and plane.ready)
    return {
        "mcp_plugin_invoke": ready,
        "mcp_plugin_count": int(plane.tool_count) if ready and plane is not None else 0,
        "mcp_plugin_sandbox": True,
    }


def start_mcp_plugin_plane(commands: Sequence[Sequence[str]]) -> McpPluginPlane:
    plane = McpPluginPlane(commands)
    plane.start()
    configure_mcp_plugin_plane(plane)
    return plane


def default_echo_plugin_command() -> list[str]:
    return echo_server_command()
