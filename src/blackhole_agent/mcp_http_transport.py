"""Speak MCP streamable HTTP so hosted plugins can serve on the live plane.

Handshake isolation, hung-call isolation, and the stdio reverse channel keep
newline-delimited plugins alive. A spec-compliant server that only speaks
HTTP POST (JSON or SSE) still cannot complete initialize: the stdio client
never POSTs, the hosted process writes no NDJSON, and the plane never sees
its tools.

This module closes that hole:

- POST JSON-RPC to an HTTP MCP endpoint (streamable HTTP subset)
- accept ``application/json`` or ``text/event-stream`` responses
- keep the stdio-only path so the hole stays falsifiable
- let an HTTP plugin and a stdio sibling serve on the same plane
"""

from __future__ import annotations

import json
import select
import socket
import sys
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterator, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import ProxyHandler, Request, build_opener

from blackhole_agent.capability_compounder import (
    Capability,
    default_ledger_path,
    legacy_pipeline_was_used,
    load_ledger,
    register_capability,
    save_ledger,
    utc_now_iso,
)
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.mcp_client import (
    CLIENT_INFO,
    DEFAULT_ELICITATION_CONTENT,
    DEFAULT_PROTOCOL_VERSION,
    McpProtocolError,
    McpStdioSession,
    _extract_text,
    echo_server_command,
    elicitation_reply,
    is_jsonrpc_server_request,
    is_mcp_transport_failure,
    reverse_channel_reply,
)
from blackhole_agent.mcp_echo_server import handle_message
from blackhole_agent.mcp_handshake_isolation import (
    DEAD_HANDSHAKE_TIMEOUT_SECONDS,
    LIVE_HANDSHAKE_TIMEOUT_SECONDS,
    McpPluginSpec,
    connect_mcp_plane,
)

SCHEMA_VERSION = 1
MCP_HTTP_ID = "capability.mcp-http-transport"
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ACCEPT = "application/json, text/event-stream"
SSE_ACCEPT = "text/event-stream"

MCP_HTTP_DONE_WHEN = (
    f"capability_exists:{MCP_HTTP_ID};"
    f"capability_proved:{MCP_HTTP_ID};"
    "no_skill_route"
)
MCP_HTTP_GOAL = (
    "Repair MCP streamable HTTP transport: a spec-compliant plugin that speaks "
    "HTTP POST and SSE instead of stdio never completes initialize, so hosted "
    "MCP servers never serve tools on the live plane."
)


class HttpEchoHandle:
    """Loopback streamable-HTTP MCP echo server."""

    def __init__(self, url: str, server: ThreadingHTTPServer, thread: threading.Thread) -> None:
        self.url = url
        self.server = server
        self.thread = thread


def http_stdio_silent_command() -> list[str]:
    """Process that only speaks HTTP; stdio initialize never arrives."""

    return [sys.executable, "-u", "-m", "blackhole_agent.mcp_http_transport", "silent"]


def encode_sse_jsonrpc(payload: Mapping[str, Any]) -> bytes:
    body = json.dumps(dict(payload), separators=(",", ":"), ensure_ascii=True)
    return f"event: message\ndata: {body}\n\n".encode("utf-8")


def parse_sse_event(raw: bytes | str) -> dict[str, Any] | None:
    """Parse one SSE event into a JSON object, or None when it is not JSON-RPC."""

    text = raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else str(raw)
    data_lines = [
        line[5:].lstrip() for line in text.splitlines() if line.startswith("data:")
    ]
    if not data_lines:
        return None
    try:
        payload = json.loads("\n".join(data_lines))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def parse_sse_jsonrpc(raw: bytes | str, request_id: Any) -> dict[str, Any]:
    text = raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else str(raw)
    for event in text.split("\n\n"):
        payload = parse_sse_event(event)
        if payload is not None and payload.get("id") == request_id:
            return payload
    raise McpProtocolError(f"timeout waiting for response id={request_id}")


class _McpHttpEchoServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class _McpHttpHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003 - stdlib signature
        return

    def do_POST(self) -> None:  # noqa: N802 - stdlib
        if self.path.rstrip("/") not in {"", "/mcp"}:
            self.send_error(404, "not an MCP endpoint")
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length > 0 else b"{}"
        try:
            message = json.loads(raw.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._write_rpc(
                {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}},
                status=400,
            )
            return
        if not isinstance(message, dict):
            self._write_rpc(
                {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "invalid request"}},
                status=400,
            )
            return
        response = handle_message(message)
        session = self.headers.get("Mcp-Session-Id") or ""
        if str(message.get("method") or "") == "initialize":
            session = uuid.uuid4().hex
        if response is None:
            self.send_response(202)
            if session:
                self.send_header("Mcp-Session-Id", session)
            self.end_headers()
            return
        self._write_rpc(response, session=session)

    def _write_rpc(
        self,
        payload: Mapping[str, Any],
        *,
        status: int = 200,
        session: str = "",
    ) -> None:
        accept = (self.headers.get("Accept") or "").lower()
        prefer_sse = "text/event-stream" in accept and "application/json" not in accept
        if prefer_sse:
            body = encode_sse_jsonrpc(payload)
            content_type = "text/event-stream"
        else:
            body = json.dumps(dict(payload), separators=(",", ":"), ensure_ascii=True).encode("utf-8")
            content_type = "application/json"
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if session:
            self.send_header("Mcp-Session-Id", session)
        self.end_headers()
        self.wfile.write(body)


@contextmanager
def start_http_echo_server() -> Iterator[HttpEchoHandle]:
    """Serve the in-repo echo tools over loopback streamable HTTP."""

    server = _McpHttpEchoServer(("127.0.0.1", 0), _McpHttpHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    handle = HttpEchoHandle(url=f"http://{host}:{port}/mcp", server=server, thread=thread)
    try:
        yield handle
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


class McpHttpSession:
    """One live MCP streamable-HTTP session: initialize -> tools/list -> tools/call.

    After initialize the client opens a GET SSE stream so the server can send
    reverse-channel JSON-RPC (elicitation, ping, progress). POST-only servers
    that reject GET stay on the live plane; ``listen_event_stream=False`` is
    the fail-open hole for hosted plugins that elicit over GET.
    """

    def __init__(
        self,
        url: str,
        *,
        timeout_seconds: float = 30.0,
        accept: str = DEFAULT_ACCEPT,
        listen_event_stream: bool = True,
        answer_elicitation: bool = True,
        elicitation_action: str = "accept",
        elicitation_content: Mapping[str, Any] | None = None,
    ) -> None:
        self.url = str(url).rstrip("/")
        self.timeout_seconds = float(timeout_seconds)
        self.accept = str(accept or DEFAULT_ACCEPT)
        self.listen_event_stream = bool(listen_event_stream)
        self.answer_elicitation = bool(answer_elicitation)
        self.elicitation_action = str(elicitation_action or "accept")
        self.elicitation_content = dict(elicitation_content or DEFAULT_ELICITATION_CONTENT)
        self.session_id = ""
        self.server_info: dict[str, Any] = {}
        self.protocol_version = ""
        self.event_stream_open = False
        self.answered_requests: list[dict[str, Any]] = []
        self.server_notifications: list[dict[str, Any]] = []
        self.tool_names: list[str] = []
        self.tool_list_count = 0
        self._next_id = 0
        self._closed = False
        self.event_stream_error = ""
        self._event_sock: socket.socket | None = None
        self._event_rest = b""

    def start(self) -> "McpHttpSession":
        client_capabilities: dict[str, Any] = {}
        if self.listen_event_stream:
            client_capabilities["elicitation"] = {}
            client_capabilities["roots"] = {}
        handshake = self.request(
            "initialize",
            {
                "protocolVersion": DEFAULT_PROTOCOL_VERSION,
                "capabilities": client_capabilities,
                "clientInfo": CLIENT_INFO,
            },
        )
        if not isinstance(handshake, Mapping) or "serverInfo" not in handshake:
            raise McpProtocolError(f"malformed initialize result: {handshake!r}")
        self.server_info = dict(handshake.get("serverInfo") or {})
        self.protocol_version = str(handshake.get("protocolVersion") or "")
        self.notify("notifications/initialized", {})
        if self.listen_event_stream:
            self._try_open_event_stream()
        return self

    def _post(self, payload: Mapping[str, Any], *, expect_response: bool) -> dict[str, Any] | None:
        if self._closed:
            raise McpProtocolError("MCP HTTP session is not running")
        body = json.dumps(dict(payload), separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": self.accept,
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        request = Request(self.url, data=body, headers=headers, method="POST")
        request_id = payload.get("id")
        try:
            # Fresh opener per POST: GET SSE pump and tools/call run concurrently.
            opener = build_opener(ProxyHandler({}))
            with opener.open(request, timeout=self.timeout_seconds) as response:
                session = response.headers.get("Mcp-Session-Id") or ""
                if session:
                    self.session_id = session
                status = getattr(response, "status", 200)
                content_type = str(response.headers.get("Content-Type") or "")
                raw = response.read()
        except HTTPError as error:
            raise McpProtocolError(
                f"http {error.code} waiting for response id={request_id}"
            ) from error
        except (TimeoutError, URLError, OSError) as error:
            raise McpProtocolError(f"timeout waiting for response id={request_id}") from error
        if not expect_response or status == 202:
            return None
        if "text/event-stream" in content_type:
            return parse_sse_jsonrpc(raw, request_id)
        try:
            message = json.loads(raw.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise McpProtocolError(f"malformed HTTP JSON-RPC for id={request_id}") from error
        if not isinstance(message, dict):
            raise McpProtocolError(f"malformed HTTP JSON-RPC for id={request_id}")
        return message

    def request(self, method: str, params: Mapping[str, Any] | None = None) -> Any:
        self._next_id += 1
        request_id = self._next_id
        response = self._post(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": dict(params or {}),
            },
            expect_response=True,
        )
        if not isinstance(response, dict):
            raise McpProtocolError(f"timeout waiting for response id={request_id}")
        if "error" in response:
            error = response["error"] or {}
            raise McpProtocolError(
                f"JSON-RPC error {error.get('code')}: {error.get('message')} for method {method}"
            )
        return response.get("result")

    def notify(self, method: str, params: Mapping[str, Any] | None = None) -> None:
        self._post(
            {"jsonrpc": "2.0", "method": method, "params": dict(params or {})},
            expect_response=False,
        )

    def list_tools(self) -> dict[str, Any]:
        result = self.request("tools/list", {})
        if not isinstance(result, Mapping) or not isinstance(result.get("tools"), list):
            raise McpProtocolError(f"malformed tools/list result: {result!r}")
        payload = dict(result)
        self.tool_names = [
            str(item.get("name") or "")
            for item in payload.get("tools") or []
            if isinstance(item, Mapping) and item.get("name")
        ]
        self.tool_list_count = getattr(self, "tool_list_count", 0) + 1
        return payload

    def refresh_tools(self) -> dict[str, Any]:
        """Re-list after ``notifications/tools/list_changed`` so a dynamic catalog is visible."""

        return self.list_tools()

    def call_tool(self, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        result = self.request("tools/call", {"name": name, "arguments": dict(arguments)})
        if not isinstance(result, Mapping):
            raise McpProtocolError(f"malformed tools/call result: {result!r}")
        return dict(result)

    def list_resources(self) -> dict[str, Any]:
        result = self.request("resources/list", {})
        if not isinstance(result, Mapping) or not isinstance(result.get("resources"), list):
            raise McpProtocolError(f"malformed resources/list result: {result!r}")
        return dict(result)

    def list_resource_templates(self) -> dict[str, Any]:
        result = self.request("resources/templates/list", {})
        if not isinstance(result, Mapping) or not isinstance(
            result.get("resourceTemplates"), list
        ):
            raise McpProtocolError(
                f"malformed resources/templates/list result: {result!r}"
            )
        return dict(result)

    def read_resource(self, uri: str) -> dict[str, Any]:
        result = self.request("resources/read", {"uri": str(uri)})
        if not isinstance(result, Mapping) or not isinstance(result.get("contents"), list):
            raise McpProtocolError(f"malformed resources/read result: {result!r}")
        return dict(result)

    def list_prompts(self) -> dict[str, Any]:
        result = self.request("prompts/list", {})
        if not isinstance(result, Mapping) or not isinstance(result.get("prompts"), list):
            raise McpProtocolError(f"malformed prompts/list result: {result!r}")
        return dict(result)

    def get_prompt(self, name: str, arguments: Mapping[str, Any] | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"name": str(name)}
        if arguments:
            params["arguments"] = dict(arguments)
        result = self.request("prompts/get", params)
        if not isinstance(result, Mapping) or not isinstance(result.get("messages"), list):
            raise McpProtocolError(f"malformed prompts/get result: {result!r}")
        return dict(result)

    def complete(
        self,
        ref: Mapping[str, Any],
        argument_name: str,
        argument_value: str = "",
    ) -> dict[str, Any]:
        result = self.request(
            "completion/complete",
            {
                "ref": dict(ref),
                "argument": {
                    "name": str(argument_name),
                    "value": str(argument_value),
                },
            },
        )
        completion = result.get("completion") if isinstance(result, Mapping) else None
        if not isinstance(result, Mapping) or not isinstance(completion, Mapping):
            raise McpProtocolError(f"malformed completion/complete result: {result!r}")
        if not isinstance(completion.get("values"), list):
            raise McpProtocolError(f"malformed completion/complete result: {result!r}")
        return dict(result)

    def set_log_level(self, level: str) -> dict[str, Any]:
        result = self.request("logging/setLevel", {"level": str(level)})
        if result is None:
            return {}
        if not isinstance(result, Mapping):
            raise McpProtocolError(f"malformed logging/setLevel result: {result!r}")
        return dict(result)

    def _try_open_event_stream(self) -> None:
        """Best-effort GET SSE; POST-only hosted plugins stay on the plane."""

        if self._closed or not self.session_id:
            return
        parsed = urlparse(self.url)
        host = parsed.hostname or "127.0.0.1"
        port = int(parsed.port or (443 if parsed.scheme == "https" else 80))
        path = parsed.path or "/mcp"
        try:
            sock = socket.create_connection((host, port), timeout=min(5.0, self.timeout_seconds))
        except OSError as exc:
            self.event_stream_error = f"GET connect failed: {exc}"
            return
        try:
            sock.sendall(
                (
                    f"GET {path} HTTP/1.1\r\n"
                    f"Host: {host}:{port}\r\n"
                    "Accept: text/event-stream\r\n"
                    f"Mcp-Session-Id: {self.session_id}\r\n"
                    "Cache-Control: no-cache\r\n"
                    "Connection: keep-alive\r\n"
                    "\r\n"
                ).encode("ascii")
            )
            sock.settimeout(2.0)
            header_buf = b""
            while b"\r\n\r\n" not in header_buf:
                chunk = sock.recv(4096)
                if not chunk:
                    raise OSError("GET stream closed during headers")
                header_buf += chunk
            header_text, rest = header_buf.split(b"\r\n\r\n", 1)
            status_line = header_text.split(b"\r\n", 1)[0].decode("ascii", errors="replace")
            parts = status_line.split()
            if len(parts) < 2 or parts[1] != "200":
                sock.close()
                self.event_stream_error = status_line
                return
            self._event_sock = sock
            self._event_rest = rest
            self.event_stream_open = True
            self.event_stream_error = ""
            threading.Thread(target=self._pump_event_stream, daemon=True).start()
        except OSError as exc:
            self.event_stream_error = str(exc)
            try:
                sock.close()
            except OSError:
                pass

    def _pump_event_stream(self) -> None:
        sock = self._event_sock
        buffer = self._event_rest.decode("utf-8", errors="replace")
        try:
            while not self._closed and sock is not None:
                while "\n\n" in buffer:
                    raw, buffer = buffer.split("\n\n", 1)
                    payload = parse_sse_event(raw)
                    if payload is not None:
                        self._handle_event_message(payload)
                try:
                    ready, _, _ = select.select([sock], [], [], 0.25)
                except (OSError, ValueError):
                    break
                if not ready:
                    continue
                try:
                    chunk = sock.recv(4096)
                except TimeoutError:
                    continue
                except OSError:
                    break
                if not chunk:
                    break
                buffer += chunk.decode("utf-8", errors="replace")
        finally:
            self.event_stream_open = False

    def _handle_event_message(self, message: Mapping[str, Any]) -> None:
        if not is_jsonrpc_server_request(message):
            if str(message.get("method") or "").startswith("notifications/"):
                self.server_notifications.append(dict(message))
            return
        method = str(message.get("method") or "")
        if method == "elicitation/create" and self.answer_elicitation:
            reply = elicitation_reply(
                message,
                content=self.elicitation_content,
                action=self.elicitation_action,
            )
            error = False
        else:
            reply = reverse_channel_reply(message)
            error = "error" in reply
        self.answered_requests.append(
            {"method": method, "id": message.get("id"), "error": error}
        )
        try:
            self._post(reply, expect_response=False)
        except McpProtocolError:
            return

    def kill(self) -> None:
        self._closed = True
        sock = self._event_sock
        self._event_sock = None
        self.event_stream_open = False
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass

    def close(self) -> None:
        self.kill()

    def __enter__(self) -> "McpHttpSession":
        return self.start()

    def __exit__(self, *exc: object) -> None:
        self.close()


def mcp_http_transport_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.mcp_http_transport import "
        "builtin_mcp_http_transport_proof; r=builtin_mcp_http_transport_proof(); "
        "assert r['ok'] and r.get('action')=='mcp_http_transport' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_mcp_http_transport_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=MCP_HTTP_ID,
        name="MCP streamable HTTP transport",
        description=(
            "A spec-compliant MCP plugin that speaks HTTP POST and SSE instead "
            "of stdio completes initialize on the live plane and serves tools "
            "beside stdio siblings."
        ),
        kind="python",
        entry="blackhole_agent.mcp_http_transport:builtin_mcp_http_transport_proof",
        proof_command=mcp_http_transport_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.mcp-handshake-isolation",
        ),
        behavior_paths=(
            "src/blackhole_agent/mcp_http_transport.py",
            "src/blackhole_agent/mcp_handshake_isolation.py",
            "src/blackhole_agent/mcp_client.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "Hosted MCP servers that speak streamable HTTP stay on the live "
            "plane: the client POSTs JSON-RPC (JSON or SSE) instead of waiting "
            "for stdio NDJSON that never arrives."
        ),
        tags=("mcp", "http", "transport", "sse", "streamable"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260830T031507Z-7c20446f",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_mcp_http_transport_proof() -> dict[str, Any]:
    """Hermetic proof: HTTP POST/SSE initialize serves hosted MCP tools."""

    from blackhole_agent.kernel_genesis_bind import _register_proved
    from blackhole_agent.kernel_genesis_diversify import (
        DIVERSITY_CATALOG,
        _prepare_exhausted_catalog,
        bind_gate_passing_successor,
    )
    from blackhole_agent.mcp_call_isolation import MCP_CALL_GOAL
    from blackhole_agent.mcp_handshake_isolation import MCP_HANDSHAKE_GOAL
    from blackhole_agent.mcp_reverse_channel import MCP_REVERSE_GOAL

    catalog = DIVERSITY_CATALOG
    checks: dict[str, bool] = {}
    checks["denylists_self"] = MCP_HTTP_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(MCP_HTTP_GOAL) == (MCP_HTTP_ID,)
    checks["reverse_goal_is_not_http"] = leftover_marker_ids(MCP_REVERSE_GOAL) != (MCP_HTTP_ID,)
    checks["handshake_goal_is_not_http"] = leftover_marker_ids(MCP_HANDSHAKE_GOAL) != (MCP_HTTP_ID,)
    checks["call_goal_is_not_http"] = leftover_marker_ids(MCP_CALL_GOAL) != (MCP_HTTP_ID,)
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["catalog_names_http"] = (
        len(catalog) > 6 and catalog[6]["id"] == MCP_HTTP_ID and catalog[5]["id"] != MCP_HTTP_ID
    )

    naive = McpStdioSession(
        http_stdio_silent_command(),
        timeout_seconds=DEAD_HANDSHAKE_TIMEOUT_SECONDS,
    )
    try:
        stalled = False
        try:
            naive.start()
        except McpProtocolError as exc:
            stalled = is_mcp_transport_failure(exc)
        checks["stdio_cannot_handshake_http_plugin"] = stalled
    finally:
        naive.kill()

    isolated = connect_mcp_plane(
        [
            McpPluginSpec(
                "hosted-stdio",
                http_stdio_silent_command(),
                timeout_seconds=DEAD_HANDSHAKE_TIMEOUT_SECONDS,
            ),
            McpPluginSpec("live", echo_server_command(), timeout_seconds=LIVE_HANDSHAKE_TIMEOUT_SECONDS),
        ],
        isolate_dead=True,
        isolate_hung_calls=True,
    )
    try:
        echoed = _extract_text(isolated.call_tool("live", "echo", {"text": "stdio-sibling"}))
        checks["stdio_plane_isolates_http_only_plugin"] = (
            isolated.plane_failed is False
            and isolated.live_names == ("live",)
            and "hosted-stdio" in isolated.isolated_names
            and echoed == "stdio-sibling"
        )
    finally:
        isolated.close()

    with start_http_echo_server() as hosted:
        json_session = McpHttpSession(hosted.url, timeout_seconds=LIVE_HANDSHAKE_TIMEOUT_SECONDS)
        try:
            json_session.start()
            tools = json_session.list_tools()
            names = tuple(
                str(item.get("name") or "")
                for item in (tools.get("tools") or [])
                if isinstance(item, Mapping)
            )
            echoed = _extract_text(json_session.call_tool("echo", {"text": "via-http"}))
            digest = _extract_text(json_session.call_tool("sha256", {"text": "via-http"}))
            checks["http_json_initialize_serves"] = (
                bool(json_session.server_info.get("name"))
                and json_session.protocol_version == DEFAULT_PROTOCOL_VERSION
                and bool(json_session.session_id)
                and "echo" in names
                and "sha256" in names
                and echoed == "via-http"
                and len(digest) == 64
            )
        finally:
            json_session.kill()

        sse_session = McpHttpSession(
            hosted.url,
            timeout_seconds=LIVE_HANDSHAKE_TIMEOUT_SECONDS,
            accept=SSE_ACCEPT,
        )
        try:
            sse_session.start()
            sse_echo = _extract_text(sse_session.call_tool("echo", {"text": "via-sse"}))
            checks["http_sse_initialize_serves"] = (
                sse_echo == "via-sse" and bool(sse_session.session_id)
            )
        finally:
            sse_session.kill()

        mixed = connect_mcp_plane(
            [
                McpPluginSpec(
                    "hosted",
                    timeout_seconds=LIVE_HANDSHAKE_TIMEOUT_SECONDS,
                    url=hosted.url,
                ),
                McpPluginSpec("live", echo_server_command(), timeout_seconds=LIVE_HANDSHAKE_TIMEOUT_SECONDS),
            ],
            isolate_dead=True,
            isolate_hung_calls=True,
        )
        try:
            hosted_echo = _extract_text(mixed.call_tool("hosted", "echo", {"text": "hosted-ok"}))
            live_echo = _extract_text(mixed.call_tool("live", "echo", {"text": "live-ok"}))
            checks["mixed_http_and_stdio_serve"] = (
                mixed.plane_failed is False
                and mixed.live_names == ("hosted", "live")
                and hosted_echo == "hosted-ok"
                and live_echo == "live-ok"
            )
        finally:
            mixed.close()

    with tempfile.TemporaryDirectory(prefix="mcp-http-transport-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != MCP_HTTP_ID:
                _register_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_http"] = (
        live_goal == MCP_HTTP_GOAL
        and MCP_HTTP_ID in live_done
        and live_source == "genesis_bind_http_transport"
        and live_goal != MCP_REVERSE_GOAL
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_mcp_http_transport_capability()
    return {
        "ok": ok,
        "action": "mcp_http_transport",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": MCP_HTTP_GOAL,
        "done_when": MCP_HTTP_DONE_WHEN,
    }


def run_silent_http_server() -> int:
    """Stay alive on HTTP only; write nothing to stdout so stdio initialize dies."""

    with start_http_echo_server():
        while True:
            time.sleep(3600)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    mode = args[0] if args else "silent"
    if mode in {"silent", "serve-stdio-silent"}:
        return run_silent_http_server()
    raise SystemExit(f"unknown mcp_http_transport mode: {mode}")


if __name__ == "__main__":
    raise SystemExit(main())
