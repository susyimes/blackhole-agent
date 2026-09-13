"""Serve the compounded capability ledger as a real MCP stdio server.

Every MCP surface in this repository so far is client-side: the agent
consumes external MCP servers. This module inverts the direction. Any
standard MCP host (Claude Desktop, Cursor, the official SDKs, or this
repository's own ``McpStdioSession``) can spawn the server and drive the
compounded ledger over newline-delimited JSON-RPC 2.0:

- ``initialize`` advertises protocol ``2025-03-26`` and a ``tools``
  capability; ``ping`` answers ``{}``.
- ``tools/list`` exposes one tool per proved, invocable absorbed
  capability, paginated with opaque cursors. Each tool carries an
  ``inputSchema`` derived from the vendored manifest's ``requires``
  contract and, when the frozen cases agree on value types, an
  ``outputSchema`` the client can validate ``structuredContent``
  against. The catalog tracks ``capabilities/ledger.json`` mtime, so
  newly proved capabilities appear without a server restart.
- ``tools/call`` executes the capability through the governed
  invocation plane (:func:`invoke_capability`), returning the real
  output as ``structuredContent`` plus a JSON text block. Invocation
  failures (unknown input keys, tool exit errors, resource-limit
  quarantine) come back as ``isError`` results; unknown tool names are
  protocol-level JSON-RPC errors.

Tool names are derived from the absorption slug, sanitized to the MCP
name grammar (``^[A-Za-z0-9_-]{1,64}$``) with a digest suffix when a
truncation or collision needs disambiguation.

Run with ``python -m blackhole_agent.mcp_capability_server [--root PATH]``.
Only JSON-RPC traffic is written to stdout; diagnostics go to stderr.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from blackhole_agent.capability_service import (
    InvocationError,
    invoke_capability,
    load_invocable_capabilities,
)

SCHEMA_VERSION = 1
PROTOCOL_VERSION = "2025-03-26"
SERVER_INFO = {"name": "blackhole-capability-mcp", "version": "1.0.0"}
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PAGE_SIZE = 128
MAX_PAGE_SIZE = 512
TOOL_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
TOOL_NAME_LIMIT = 64
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
PARSE_ERROR = -32700


class ToolCallError(KeyError):
    """Raised when a tools/call names a tool outside the live catalog."""


def _json_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    if value is None:
        return "null"
    return ""


def _case_property_types(manifest: Mapping[str, Any], field: str) -> dict[str, str]:
    """Per-key JSON types consistent across every frozen case, else ''."""

    types: dict[str, str] = {}
    for case in manifest.get("cases") or []:
        if not isinstance(case, Mapping):
            continue
        block = case.get(field)
        if not isinstance(block, Mapping):
            continue
        for key, value in block.items():
            name = str(key)
            detected = _json_type(value)
            if name not in types:
                types[name] = detected
            elif types[name] != detected:
                types[name] = ""
    return types


def tool_name_for_slug(slug: str, taken: set[str]) -> str:
    """Map an absorption slug to a unique spec-legal MCP tool name."""

    base = re.sub(r"[^A-Za-z0-9_-]", "-", slug).strip("-") or "capability"
    candidate = base[:TOOL_NAME_LIMIT]
    if candidate not in taken and len(base) <= TOOL_NAME_LIMIT:
        taken.add(candidate)
        return candidate
    suffix = hashlib.sha256(slug.encode("utf-8")).hexdigest()[:8]
    candidate = f"{base[: TOOL_NAME_LIMIT - 9]}-{suffix}"
    while candidate in taken:
        suffix = hashlib.sha256(f"{slug}:{len(taken)}".encode("utf-8")).hexdigest()[:8]
        candidate = f"{base[: TOOL_NAME_LIMIT - 9]}-{suffix}"
    taken.add(candidate)
    return candidate


def _tool_descriptor(capability_id: str, item: Mapping[str, Any], tool_name: str) -> dict[str, Any]:
    requires = [str(key) for key in item["requires"]]
    provides = [str(key) for key in item["provides"]]
    manifest_path = Path(str(item["tool_root"])) / "absorption.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        manifest = {}
    input_types = _case_property_types(manifest, "input")
    output_types = _case_property_types(manifest, "expect")
    input_properties: dict[str, Any] = {}
    for key in requires:
        detected = input_types.get(key) or ""
        input_properties[key] = {"type": detected} if detected else {}
    descriptor: dict[str, Any] = {
        "name": tool_name,
        "description": (
            f"{item['name']} [{capability_id}] — provides: {', '.join(provides)}"
        ),
        "inputSchema": {
            "type": "object",
            "properties": input_properties,
            "required": requires,
            "additionalProperties": False,
        },
    }
    output_properties: dict[str, Any] = {}
    typed = bool(provides)
    for key in provides:
        detected = output_types.get(key) or ""
        if not detected:
            typed = False
            break
        # A tool proved against integer cases may legitimately emit a float
        # at runtime (division, means); advertise the wider numeric type.
        output_properties[key] = {"type": "number" if detected == "integer" else detected}
    if typed:
        descriptor["outputSchema"] = {
            "type": "object",
            "properties": output_properties,
            "required": provides,
        }
    return descriptor


class CapabilityCatalog:
    """Live view of the invocable ledger, rebuilt when ledger.json changes."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self._ledger_mtime_ns: int | None = None
        self.tools: list[dict[str, Any]] = []
        self.by_name: dict[str, str] = {}
        self.refresh()

    def refresh(self) -> None:
        ledger_path = self.root / "capabilities" / "ledger.json"
        try:
            mtime_ns = ledger_path.stat().st_mtime_ns
        except OSError:
            mtime_ns = None
        if mtime_ns == self._ledger_mtime_ns and self.tools:
            return
        invocable = load_invocable_capabilities(self.root)
        tools: list[dict[str, Any]] = []
        by_name: dict[str, str] = {}
        taken: set[str] = set()
        for capability_id in sorted(invocable):
            item = invocable[capability_id]
            tool_name = tool_name_for_slug(str(item["slug"]), taken)
            tools.append(_tool_descriptor(capability_id, item, tool_name))
            by_name[tool_name] = capability_id
        self.tools = tools
        self.by_name = by_name
        self._ledger_mtime_ns = mtime_ns

    def list_page(self, cursor: str, page_size: int) -> dict[str, Any]:
        self.refresh()
        offset = 0
        if cursor:
            try:
                offset = int(cursor)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"invalid cursor: {cursor!r}") from exc
            if offset < 0 or offset > len(self.tools):
                raise ValueError(f"invalid cursor: {cursor!r}")
        size = max(1, min(int(page_size), MAX_PAGE_SIZE))
        page = self.tools[offset : offset + size]
        result: dict[str, Any] = {"tools": page}
        if offset + size < len(self.tools):
            result["nextCursor"] = str(offset + size)
        return result

    def call(self, name: str, arguments: Any) -> dict[str, Any]:
        self.refresh()
        capability_id = self.by_name.get(name)
        if capability_id is None:
            raise ToolCallError(name)
        if not isinstance(arguments, Mapping):
            arguments = {}
        try:
            result = invoke_capability(self.root, capability_id, dict(arguments))
        except InvocationError as exc:
            return {
                "content": [{"type": "text", "text": f"invocation refused ({exc.status}): {exc.error}"}],
                "isError": True,
            }
        output = result["output"]
        return {
            "content": [
                {"type": "text", "text": json.dumps(output, sort_keys=True, ensure_ascii=True)}
            ],
            "structuredContent": output,
            "isError": False,
        }


def handle_message(catalog: CapabilityCatalog, message: Mapping[str, Any]) -> dict[str, Any] | None:
    """Handle one JSON-RPC message; return the response or None for notifications."""

    method = message.get("method")
    if method == "notifications/initialized" or method is None and "id" not in message:
        return None
    if "id" not in message:
        return None

    request_id = message["id"]
    params = message.get("params") if isinstance(message.get("params"), Mapping) else {}
    try:
        if method == "initialize":
            result: Any = {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": SERVER_INFO,
            }
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = catalog.list_page(str(params.get("cursor") or ""), DEFAULT_PAGE_SIZE)
        elif method == "tools/call":
            name = str(params.get("name") or "")
            arguments = params.get("arguments")
            try:
                result = catalog.call(name, arguments)
            except ToolCallError:
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": INVALID_PARAMS, "message": f"unknown tool: {name}"},
                }
        else:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": METHOD_NOT_FOUND, "message": f"unknown method: {method}"},
            }
    except ValueError as exc:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": INVALID_PARAMS, "message": str(exc)},
        }
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def serve_stdio(root: Path) -> int:
    """Serve NDJSON JSON-RPC on stdin/stdout until EOF; never prints to stdout."""

    catalog = CapabilityCatalog(Path(root))
    stdin = sys.stdin
    stdout = sys.stdout
    for raw_line in stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            stdout.write(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {"code": PARSE_ERROR, "message": "line is not valid JSON"},
                    }
                )
                + "\n"
            )
            stdout.flush()
            continue
        if not isinstance(message, dict):
            stdout.write(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {"code": PARSE_ERROR, "message": "message is not a JSON object"},
                    }
                )
                + "\n"
            )
            stdout.flush()
            continue
        response = handle_message(catalog, message)
        if response is not None:
            stdout.write(json.dumps(response) + "\n")
            stdout.flush()
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        help="repository root holding capabilities/ledger.json (default: this checkout)",
    )
    args = parser.parse_args(argv)
    try:
        sys.stdin.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except (AttributeError, OSError):
        pass
    return serve_stdio(args.root)


if __name__ == "__main__":
    raise SystemExit(main())
