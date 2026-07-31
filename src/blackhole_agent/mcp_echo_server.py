"""Reference MCP stdio server used for hermetic live-execution proofs.

Implements just enough of the Model Context Protocol (newline-delimited
JSON-RPC 2.0 over stdio) to exercise a real client session without network
or third-party servers: ``initialize``, ``notifications/initialized``,
``ping``, ``tools/list``, and ``tools/call``.

Tools exposed:

- ``echo`` (readOnlyHint): returns the supplied text back as content.
- ``sha256`` (readOnlyHint): returns the hex digest of the supplied text.

Run with ``python -m blackhole_agent.mcp_echo_server``. Only JSON-RPC
responses are written to stdout; protocol noise goes to stderr never, so the
transport stays clean.
"""

from __future__ import annotations

import hashlib
import json
import sys
from typing import Any, Mapping

PROTOCOL_VERSION = "2025-03-26"
SERVER_INFO = {"name": "blackhole-echo-mcp", "version": "1.0.0"}

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
        "name": "sha256",
        "description": "Return the SHA-256 hex digest of the supplied text.",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
        "annotations": {"readOnlyHint": True},
    },
]


def _text_content(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "isError": False}


def _call_tool(name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
    text = str(arguments.get("text") or "")
    if name == "echo":
        return _text_content(text)
    if name == "sha256":
        return _text_content(hashlib.sha256(text.encode("utf-8")).hexdigest())
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
                "capabilities": {"tools": {}},
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
        response = handle_message(message)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
