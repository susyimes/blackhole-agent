"""Speak MCP HTTP GET event streams so hosted plugins can elicit on the live plane.

Streamable HTTP POST completes initialize. A spec-compliant hosted plugin that
sends ``elicitation/create`` on the GET SSE stream after initialize still
stalls: the client never GETs, the approval never reaches an operator, and
the gated ``tools/call`` never returns. Stdio reverse-channel siblings that
only ping stay live.

This module closes that hole:

- GET ``text/event-stream`` with ``Mcp-Session-Id`` after initialize
- answer ``elicitation/create`` on that reverse channel
- keep the no-GET path so the hole stays falsifiable
- let an elicitation-gated HTTP plugin and a stdio sibling serve together
"""

from __future__ import annotations

import json
import queue
import sys
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterator, Mapping

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
    DEFAULT_PROTOCOL_VERSION,
    McpProtocolError,
    _extract_text,
    echo_server_command,
    elicitation_reply,
    is_mcp_transport_failure,
)
from blackhole_agent.mcp_echo_server import TOOLS, handle_message
from blackhole_agent.mcp_handshake_isolation import (
    DEAD_HANDSHAKE_TIMEOUT_SECONDS,
    LIVE_HANDSHAKE_TIMEOUT_SECONDS,
    McpPluginSpec,
    connect_mcp_plane,
)
from blackhole_agent.mcp_http_transport import (
    MCP_HTTP_GOAL,
    MCP_HTTP_ID,
    McpHttpSession,
    encode_sse_jsonrpc,
)
from blackhole_agent.mcp_reverse_channel import MCP_REVERSE_GOAL, MCP_REVERSE_ID

SCHEMA_VERSION = 1
MCP_HTTP_EVENT_ID = "capability.mcp-http-event-stream"
REPO_ROOT = Path(__file__).resolve().parents[2]
GATED_TOOL_NAME = "echo_gated"
ELICIT_PARK_SECONDS = 2.0
STREAM_WAIT_SECONDS = 0.75

MCP_HTTP_EVENT_DONE_WHEN = (
    f"capability_exists:{MCP_HTTP_EVENT_ID};"
    f"capability_proved:{MCP_HTTP_EVENT_ID};"
    "no_skill_route"
)
MCP_HTTP_EVENT_GOAL = (
    "Repair MCP HTTP GET event-stream reverse channel: a hosted plugin that "
    "elicits operator input over the GET SSE stream after initialize never "
    "reaches the client, so approval-gated tools stall on the live HTTP plane "
    "while stdio siblings keep serving."
)

GATED_TOOL = {
    "name": GATED_TOOL_NAME,
    "description": "Echo text after the operator approves via elicitation.",
    "inputSchema": {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    },
    "annotations": {"readOnlyHint": False},
}

ELICITATION_SCHEMA = {
    "type": "object",
    "properties": {
        "approved": {
            "type": "boolean",
            "title": "Approve",
            "description": "Allow the gated tool to run.",
        }
    },
    "required": ["approved"],
}


class HttpEventHandle:
    """Loopback streamable-HTTP MCP server that elicits over GET SSE."""

    def __init__(self, url: str, server: ThreadingHTTPServer, thread: threading.Thread) -> None:
        self.url = url
        self.server = server
        self.thread = thread


class _EventSessionState:
    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.event_queue: queue.Queue[dict[str, Any] | None] = queue.Queue()
        self.stream_connected = threading.Event()
        self.pending: dict[Any, threading.Event] = {}
        self.replies: dict[Any, dict[str, Any]] = {}
        self.closed = False


class _McpHttpEventServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], handler: type[BaseHTTPRequestHandler]) -> None:
        super().__init__(address, handler)
        self.lock = threading.Lock()
        self.sessions: dict[str, _EventSessionState] = {}

    def close_sessions(self) -> None:
        with self.lock:
            states = list(self.sessions.values())
        for state in states:
            state.closed = True
            state.stream_connected.set()
            for pending in list(state.pending.values()):
                pending.set()
            try:
                state.event_queue.put_nowait(None)
            except Exception:
                pass


def _text_result(text: str, *, is_error: bool = False) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "isError": bool(is_error)}


def _session_state(handler: BaseHTTPRequestHandler) -> _EventSessionState | None:
    session_id = str(handler.headers.get("Mcp-Session-Id") or "")
    server = handler.server
    if not isinstance(server, _McpHttpEventServer) or not session_id:
        return None
    with server.lock:
        return server.sessions.get(session_id)


class _McpHttpEventHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    disable_nagle_algorithm = True
    wbufsize = 0

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003 - stdlib signature
        return

    def do_GET(self) -> None:  # noqa: N802 - stdlib
        if self.path.rstrip("/") not in {"", "/mcp"}:
            self.send_error(404, "not an MCP endpoint")
            return
        accept = (self.headers.get("Accept") or "").lower()
        if "text/event-stream" not in accept:
            self.send_error(406, "GET requires text/event-stream")
            return
        state = _session_state(self)
        if state is None:
            self.send_error(400, "missing or unknown Mcp-Session-Id")
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Mcp-Session-Id", state.session_id)
        self.end_headers()
        try:
            self.wfile.flush()
        except OSError:
            return
        state.stream_connected.set()
        try:
            while not state.closed:
                try:
                    item = state.event_queue.get(timeout=0.25)
                except queue.Empty:
                    continue
                if item is None:
                    break
                try:
                    self.wfile.write(encode_sse_jsonrpc(item))
                    self.wfile.flush()
                except OSError:
                    break
        finally:
            state.stream_connected.clear()

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
        if "method" not in message and "id" in message:
            self._accept_client_reply(message)
            return
        method = str(message.get("method") or "")
        if method == "initialize":
            self._handle_initialize(message)
            return
        if method == "tools/list":
            self._write_rpc(
                {
                    "jsonrpc": "2.0",
                    "id": message.get("id"),
                    "result": {"tools": [*TOOLS, dict(GATED_TOOL)]},
                },
                session=str(self.headers.get("Mcp-Session-Id") or ""),
            )
            return
        if method == "tools/call":
            params = message.get("params") or {}
            name = str(params.get("name") or "")
            if name == GATED_TOOL_NAME:
                self._handle_gated_call(message)
                return
        response = handle_message(message)
        session = str(self.headers.get("Mcp-Session-Id") or "")
        if response is None:
            self.send_response(202)
            if session:
                self.send_header("Mcp-Session-Id", session)
            self.end_headers()
            return
        self._write_rpc(response, session=session)

    def _handle_initialize(self, message: Mapping[str, Any]) -> None:
        session_id = uuid.uuid4().hex
        state = _EventSessionState(session_id)
        server = self.server
        if isinstance(server, _McpHttpEventServer):
            with server.lock:
                server.sessions[session_id] = state
        response = handle_message(message)
        if isinstance(response, dict) and isinstance(response.get("result"), dict):
            result = dict(response["result"])
            info = dict(result.get("serverInfo") or {})
            info["name"] = "blackhole-elicit-http"
            result["serverInfo"] = info
            result["capabilities"] = {"tools": {}, "elicitation": {}}
            response = {**response, "result": result}
        self._write_rpc(response or {}, session=session_id)

    def _accept_client_reply(self, message: Mapping[str, Any]) -> None:
        state = _session_state(self)
        session = str(self.headers.get("Mcp-Session-Id") or "")
        if state is not None:
            reply_id = message.get("id")
            state.replies[reply_id] = dict(message)
            pending = state.pending.get(reply_id)
            if pending is not None:
                pending.set()
        self.send_response(202)
        if session:
            self.send_header("Mcp-Session-Id", session)
        self.end_headers()

    def _handle_gated_call(self, message: Mapping[str, Any]) -> None:
        state = _session_state(self)
        session = str(self.headers.get("Mcp-Session-Id") or "")
        request_id = message.get("id")
        params = message.get("params") or {}
        arguments = params.get("arguments") or {}
        text = str(arguments.get("text") or "")
        if state is None:
            self._write_rpc(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32000, "message": "missing MCP session"},
                },
                session=session,
            )
            return
        if not state.stream_connected.wait(timeout=STREAM_WAIT_SECONDS):
            parked = time.monotonic() + ELICIT_PARK_SECONDS
            while time.monotonic() < parked and not state.closed:
                time.sleep(0.05)
            return
        elicit_id = f"elicit-{uuid.uuid4().hex}"
        done = threading.Event()
        state.pending[elicit_id] = done
        state.event_queue.put(
            {
                "jsonrpc": "2.0",
                "method": "notifications/progress",
                "params": {
                    "progressToken": GATED_TOOL_NAME,
                    "progress": 0.5,
                    "total": 1,
                },
            }
        )
        state.event_queue.put(
            {
                "jsonrpc": "2.0",
                "id": elicit_id,
                "method": "elicitation/create",
                "params": {
                    "message": "Approve the gated echo tool?",
                    "requestedSchema": ELICITATION_SCHEMA,
                },
            }
        )
        if not done.wait(timeout=LIVE_HANDSHAKE_TIMEOUT_SECONDS) or state.closed:
            return
        reply = state.replies.get(elicit_id) or {}
        result = reply.get("result") if isinstance(reply.get("result"), dict) else {}
        content = result.get("content") if isinstance(result.get("content"), dict) else {}
        approved = result.get("action") == "accept" and content.get("approved") is True
        payload = _text_result(f"{text}|approved" if approved else "declined", is_error=not approved)
        self._write_rpc({"jsonrpc": "2.0", "id": request_id, "result": payload}, session=session)

    def _write_rpc(
        self,
        payload: Mapping[str, Any],
        *,
        status: int = 200,
        session: str = "",
    ) -> None:
        body = json.dumps(dict(payload), separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        if session:
            self.send_header("Mcp-Session-Id", session)
        self.end_headers()
        self.wfile.write(body)


@contextmanager
def start_http_elicitation_server() -> Iterator[HttpEventHandle]:
    """Serve gated echo over loopback streamable HTTP with a GET event stream."""

    server = _McpHttpEventServer(("127.0.0.1", 0), _McpHttpEventHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    handle = HttpEventHandle(url=f"http://{host}:{port}/mcp", server=server, thread=thread)
    try:
        yield handle
    finally:
        server.close_sessions()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def mcp_http_event_stream_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.mcp_http_event_stream import "
        "builtin_mcp_http_event_stream_proof; r=builtin_mcp_http_event_stream_proof(); "
        "assert r['ok'] and r.get('action')=='mcp_http_event_stream' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_mcp_http_event_stream_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=MCP_HTTP_EVENT_ID,
        name="MCP HTTP GET event-stream reverse channel",
        description=(
            "A hosted MCP plugin that elicits operator approval over the GET "
            "SSE stream completes the gated tools/call on the live plane "
            "beside stdio siblings; skipping GET keeps the stall falsifiable."
        ),
        kind="python",
        entry="blackhole_agent.mcp_http_event_stream:builtin_mcp_http_event_stream_proof",
        proof_command=mcp_http_event_stream_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.mcp-http-transport",
            "capability.mcp-reverse-channel",
        ),
        behavior_paths=(
            "src/blackhole_agent/mcp_http_event_stream.py",
            "src/blackhole_agent/mcp_http_transport.py",
            "src/blackhole_agent/mcp_client.py",
            "src/blackhole_agent/mcp_handshake_isolation.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "Hosted MCP plugins that elicit operator input over the GET SSE "
            "stream stay on the live plane: the client opens the event stream "
            "after initialize and answers elicitation/create instead of "
            "leaving approval-gated tools stalled."
        ),
        tags=("mcp", "http", "sse", "elicitation", "event-stream"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260830T034600Z-cc81e116",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_mcp_http_event_stream_proof() -> dict[str, Any]:
    """Hermetic proof: GET SSE elicitation unblocks a gated HTTP plugin."""

    from blackhole_agent.kernel_genesis_bind import _register_proved
    from blackhole_agent.kernel_genesis_diversify import (
        DIVERSITY_CATALOG,
        _prepare_exhausted_catalog,
        bind_gate_passing_successor,
    )
    from blackhole_agent.mcp_call_isolation import MCP_CALL_GOAL
    from blackhole_agent.mcp_handshake_isolation import MCP_HANDSHAKE_GOAL

    catalog = DIVERSITY_CATALOG
    checks: dict[str, bool] = {}
    checks["denylists_self"] = MCP_HTTP_EVENT_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(MCP_HTTP_EVENT_GOAL) == (MCP_HTTP_EVENT_ID,)
    checks["http_goal_is_not_event_stream"] = leftover_marker_ids(MCP_HTTP_GOAL) != (
        MCP_HTTP_EVENT_ID,
    )
    checks["reverse_goal_is_not_event_stream"] = leftover_marker_ids(MCP_REVERSE_GOAL) != (
        MCP_HTTP_EVENT_ID,
    )
    checks["http_marker_stays_http"] = leftover_marker_ids(MCP_HTTP_GOAL) == (MCP_HTTP_ID,)
    checks["reverse_marker_stays_reverse"] = leftover_marker_ids(MCP_REVERSE_GOAL) == (
        MCP_REVERSE_ID,
    )
    checks["handshake_goal_is_not_event_stream"] = leftover_marker_ids(MCP_HANDSHAKE_GOAL) != (
        MCP_HTTP_EVENT_ID,
    )
    checks["call_goal_is_not_event_stream"] = leftover_marker_ids(MCP_CALL_GOAL) != (
        MCP_HTTP_EVENT_ID,
    )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["catalog_names_event_stream"] = (
        len(catalog) > 7
        and catalog[7]["id"] == MCP_HTTP_EVENT_ID
        and catalog[6]["id"] == MCP_HTTP_ID
    )
    accept = elicitation_reply({"jsonrpc": "2.0", "id": "elicit-1", "method": "elicitation/create"})
    checks["elicitation_reply_accepts"] = (
        accept.get("id") == "elicit-1"
        and (accept.get("result") or {}).get("action") == "accept"
        and (accept.get("result") or {}).get("content") == {"approved": True}
    )
    decline = elicitation_reply(
        {"jsonrpc": "2.0", "id": "elicit-2", "method": "elicitation/create"},
        action="decline",
    )
    checks["elicitation_reply_decline_has_no_content"] = (
        (decline.get("result") or {}).get("action") == "decline"
        and "content" not in (decline.get("result") or {})
    )

    with start_http_elicitation_server() as hosted:
        naive = McpHttpSession(
            hosted.url,
            timeout_seconds=DEAD_HANDSHAKE_TIMEOUT_SECONDS,
            listen_event_stream=False,
        )
        try:
            naive.start()
            stalled = False
            try:
                naive.call_tool(GATED_TOOL_NAME, {"text": "nope"})
            except McpProtocolError as exc:
                stalled = is_mcp_transport_failure(exc)
            checks["naive_without_get_stalls"] = stalled and not naive.event_stream_open
        finally:
            naive.kill()

        live = McpHttpSession(hosted.url, timeout_seconds=LIVE_HANDSHAKE_TIMEOUT_SECONDS)
        try:
            live.start()
            tools = live.list_tools()
            names = tuple(
                str(item.get("name") or "")
                for item in (tools.get("tools") or [])
                if isinstance(item, Mapping)
            )
            gated_text = ""
            gated_error = ""
            try:
                gated = live.call_tool(GATED_TOOL_NAME, {"text": "via-get"})
                gated_text = _extract_text(gated)
            except McpProtocolError as exc:
                gated_error = str(exc)
            methods = tuple(item.get("method") for item in live.answered_requests)
            notifications = tuple(item.get("method") for item in live.server_notifications)
            checks["event_stream_opens"] = live.event_stream_open is True and not live.event_stream_error
            checks["gated_tool_is_advertised"] = GATED_TOOL_NAME in names
            checks["elicitation_call_succeeds"] = gated_text == "via-get|approved" and not gated_error
            checks["elicitation_was_answered"] = "elicitation/create" in methods
            checks["progress_notification_on_get_stream"] = (
                "notifications/progress" in notifications
            )
        finally:
            live.kill()

        declined = McpHttpSession(
            hosted.url,
            timeout_seconds=LIVE_HANDSHAKE_TIMEOUT_SECONDS,
            elicitation_action="decline",
        )
        try:
            declined.start()
            declined_ok = False
            try:
                result = declined.call_tool(GATED_TOOL_NAME, {"text": "blocked"})
                declined_ok = result.get("isError") is True and _extract_text(result) == "declined"
            except McpProtocolError:
                declined_ok = False
            checks["declined_elicitation_is_error"] = declined_ok
        finally:
            declined.kill()

        mixed = connect_mcp_plane(
            [
                McpPluginSpec(
                    "hosted",
                    timeout_seconds=LIVE_HANDSHAKE_TIMEOUT_SECONDS,
                    url=hosted.url,
                ),
                McpPluginSpec(
                    "live",
                    echo_server_command(),
                    timeout_seconds=LIVE_HANDSHAKE_TIMEOUT_SECONDS,
                ),
            ],
            isolate_dead=True,
            isolate_hung_calls=True,
        )
        try:
            hosted_echo = _extract_text(
                mixed.call_tool("hosted", GATED_TOOL_NAME, {"text": "hosted-ok"})
            )
            live_echo = _extract_text(mixed.call_tool("live", "echo", {"text": "live-ok"}))
            hosted_session = mixed._sessions.get("hosted")
            checks["mixed_http_event_stream_and_stdio_serve"] = (
                mixed.plane_failed is False
                and mixed.live_names == ("hosted", "live")
                and hosted_echo == "hosted-ok|approved"
                and live_echo == "live-ok"
                and bool(getattr(hosted_session, "event_stream_open", False))
            )
        finally:
            mixed.close()

    with tempfile.TemporaryDirectory(prefix="mcp-http-event-stream-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != MCP_HTTP_EVENT_ID:
                _register_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_event_stream"] = (
        live_goal == MCP_HTTP_EVENT_GOAL
        and MCP_HTTP_EVENT_ID in live_done
        and live_source == "genesis_bind_http_event_stream"
        and live_goal != MCP_HTTP_GOAL
        and live_goal != MCP_REVERSE_GOAL
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_mcp_http_event_stream_capability()
    return {
        "ok": ok,
        "action": "mcp_http_event_stream",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": MCP_HTTP_EVENT_GOAL,
        "done_when": MCP_HTTP_EVENT_DONE_WHEN,
    }


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    mode = args[0] if args else "serve"
    if mode in {"serve", "elicit"}:
        with start_http_elicitation_server():
            while True:
                time.sleep(3600)
    raise SystemExit(f"unknown mcp_http_event_stream mode: {mode}")


if __name__ == "__main__":
    raise SystemExit(main())
