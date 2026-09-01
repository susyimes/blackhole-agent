"""Reference MCP stdio server used for hermetic live-execution proofs.

Implements just enough of the Model Context Protocol (newline-delimited
JSON-RPC 2.0 over stdio) to exercise a real client session without network
or third-party servers: ``initialize``, ``notifications/initialized``,
``ping``, ``tools/list``, ``tools/call``, ``resources/list``,
``resources/templates/list``, ``resources/read``, ``prompts/list``,
``prompts/get``, ``completion/complete``, and ``logging/setLevel``
(emitting ``notifications/message``). A ``tools/call`` that carries
``_meta.progressToken`` also emits monotonic ``notifications/progress``.
Initialize advertises ``tools.listChanged``; the static catalog never
emits ``notifications/tools/list_changed``.

Tools exposed:

- ``echo`` (readOnlyHint): returns the supplied text back as content.
- ``sha256`` (readOnlyHint): returns the hex digest of the supplied text.

Resources exposed:

- ``resource://blackhole/echo/about``: identity of this server.
- ``resource://blackhole/echo/note/{id}``: template-expanded note body.

Prompts exposed:

- ``about``: identity of this server as a user prompt.
- ``note``: argument ``id`` expands to a ``note:{id}`` user prompt.

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
ABOUT_URI = "resource://blackhole/echo/about"
NOTE_TEMPLATE = "resource://blackhole/echo/note/{id}"
NOTE_PREFIX = "resource://blackhole/echo/note/"
ABOUT_PROMPT = "about"
NOTE_PROMPT = "note"
RESOURCE_NOT_FOUND = -32002
PROMPT_NOT_FOUND = -32602
COMPLETION_NOT_FOUND = -32602
NOTE_COMPLETION_IDS: tuple[str, ...] = ("sentinel", "sensor", "about")
LOG_LEVEL_NOT_FOUND = -32602
LOG_LEVEL_SET = frozenset(
    {
        "debug",
        "info",
        "notice",
        "warning",
        "error",
        "critical",
        "alert",
        "emergency",
    }
)
PENDING_NOTIFICATIONS: list[dict[str, Any]] = []

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

RESOURCES: list[dict[str, Any]] = [
    {
        "uri": ABOUT_URI,
        "name": "about",
        "description": "Identity of the in-repo reference MCP server.",
        "mimeType": "text/plain",
    },
]

RESOURCE_TEMPLATES: list[dict[str, Any]] = [
    {
        "uriTemplate": NOTE_TEMPLATE,
        "name": "note",
        "description": "Read a named note from the echo data plane.",
        "mimeType": "text/plain",
    },
]

PROMPTS: list[dict[str, Any]] = [
    {
        "name": ABOUT_PROMPT,
        "description": "Identity of this server as a user prompt.",
        "arguments": [],
    },
    {
        "name": NOTE_PROMPT,
        "description": "Render a named note as a user prompt.",
        "arguments": [
            {
                "name": "id",
                "description": "Note identifier",
                "required": True,
            }
        ],
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


def _resource_contents(uri: str) -> dict[str, Any] | None:
    """Return MCP resource contents for a known URI, or None if missing."""

    if uri == ABOUT_URI:
        return {
            "contents": [
                {
                    "uri": uri,
                    "mimeType": "text/plain",
                    "text": str(SERVER_INFO["name"]),
                }
            ]
        }
    if uri.startswith(NOTE_PREFIX):
        note_id = uri[len(NOTE_PREFIX) :]
        if note_id:
            return {
                "contents": [
                    {
                        "uri": uri,
                        "mimeType": "text/plain",
                        "text": f"note:{note_id}",
                    }
                ]
            }
    return None


def _complete_argument(params: Mapping[str, Any]) -> dict[str, Any] | None:
    """Return MCP completion values for a known prompt or resource template."""

    ref = params.get("ref") if isinstance(params.get("ref"), Mapping) else {}
    argument = params.get("argument") if isinstance(params.get("argument"), Mapping) else {}
    ref_type = str(ref.get("type") or "")
    arg_name = str(argument.get("name") or "")
    prefix = str(argument.get("value") or "")
    if arg_name != "id":
        return None
    if ref_type == "ref/prompt" and str(ref.get("name") or "") == NOTE_PROMPT:
        candidates = NOTE_COMPLETION_IDS
    elif ref_type == "ref/resource" and str(ref.get("uri") or "") == NOTE_TEMPLATE:
        candidates = NOTE_COMPLETION_IDS
    else:
        return None
    values = [item for item in candidates if item.startswith(prefix)]
    return {
        "completion": {
            "values": values,
            "total": len(values),
            "hasMore": False,
        }
    }


def _prompt_messages(name: str, arguments: Mapping[str, Any]) -> dict[str, Any] | None:
    """Return MCP prompt messages for a known prompt, or None if missing."""

    if name == ABOUT_PROMPT:
        return {
            "description": "Identity of the in-repo reference MCP server.",
            "messages": [
                {
                    "role": "user",
                    "content": {"type": "text", "text": str(SERVER_INFO["name"])},
                }
            ],
        }
    if name == NOTE_PROMPT:
        note_id = str(arguments.get("id") or "")
        if not note_id:
            return None
        return {
            "description": f"Note {note_id}",
            "messages": [
                {
                    "role": "user",
                    "content": {"type": "text", "text": f"note:{note_id}"},
                }
            ],
        }
    return None


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
                "capabilities": {
                    "tools": {"listChanged": True},
                    "resources": {},
                    "prompts": {},
                    "completions": {},
                    "logging": {},
                },
                "serverInfo": SERVER_INFO,
            }
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            meta = params.get("_meta") if isinstance(params.get("_meta"), Mapping) else {}
            token = meta.get("progressToken")
            if token is not None and str(token) != "":
                PENDING_NOTIFICATIONS.extend(
                    (
                        {
                            "jsonrpc": "2.0",
                            "method": "notifications/progress",
                            "params": {
                                "progressToken": token,
                                "progress": 1,
                                "total": 2,
                                "message": "working",
                            },
                        },
                        {
                            "jsonrpc": "2.0",
                            "method": "notifications/progress",
                            "params": {
                                "progressToken": token,
                                "progress": 2,
                                "total": 2,
                                "message": "done",
                            },
                        },
                    )
                )
            result = _call_tool(str(params.get("name") or ""), params.get("arguments") or {})
        elif method == "resources/list":
            result = {"resources": RESOURCES}
        elif method == "resources/templates/list":
            result = {"resourceTemplates": RESOURCE_TEMPLATES}
        elif method == "resources/read":
            contents = _resource_contents(str(params.get("uri") or ""))
            if contents is None:
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": RESOURCE_NOT_FOUND,
                        "message": f"unknown resource: {params.get('uri')}",
                    },
                }
            result = contents
        elif method == "prompts/list":
            result = {"prompts": PROMPTS}
        elif method == "prompts/get":
            prompt_name = str(params.get("name") or "")
            prompt_args = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
            prompt = _prompt_messages(prompt_name, prompt_args)
            if prompt is None:
                missing = (
                    f"missing prompt argument: id"
                    if prompt_name == NOTE_PROMPT
                    else f"unknown prompt: {prompt_name}"
                )
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": PROMPT_NOT_FOUND, "message": missing},
                }
            result = prompt
        elif method == "completion/complete":
            completed = _complete_argument(params if isinstance(params, Mapping) else {})
            if completed is None:
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": COMPLETION_NOT_FOUND,
                        "message": "unknown completion ref",
                    },
                }
            result = completed
        elif method == "logging/setLevel":
            level = str(params.get("level") or "") if isinstance(params, Mapping) else ""
            if level not in LOG_LEVEL_SET:
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": LOG_LEVEL_NOT_FOUND,
                        "message": f"unknown log level: {level}",
                    },
                }
            PENDING_NOTIFICATIONS.append(
                {
                    "jsonrpc": "2.0",
                    "method": "notifications/message",
                    "params": {
                        "level": level,
                        "logger": "blackhole-echo",
                        "data": f"level:{level}",
                    },
                }
            )
            result = {}
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
        pending = list(PENDING_NOTIFICATIONS)
        PENDING_NOTIFICATIONS.clear()
        for notification in pending:
            sys.stdout.write(json.dumps(notification) + "\n")
            sys.stdout.flush()
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
