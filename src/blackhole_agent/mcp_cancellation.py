"""Cancel in-flight MCP tools/call so a hung stdio plugin releases the session.

Call isolation already tears a hung plugin off the plane. A plugin that
occupies stdio with a long ``tools/call`` still never receives
``notifications/cancelled``: the client waits until timeout, the abandoned
request leaves the session blocked, and sibling tools on the same session
cannot serve. Isolation kills the process instead of aborting the request.

This module closes that hole:

- send ``notifications/cancelled`` for an in-flight JSON-RPC request
- keep a skip-cancel path so the occupied-session hole stays falsifiable
- reuse the same stdio session after the server acknowledges -32800
- let a cancel-gated plugin and a tools-only sibling serve together
- bind this family as the next diversity-catalog successor after elicitation
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping

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
from blackhole_agent.mcp_call_isolation import MCP_CALL_GOAL, MCP_CALL_ID
from blackhole_agent.mcp_client import (
    JSONRPC_REQUEST_CANCELLED,
    McpProtocolError,
    McpStdioSession,
    _extract_text,
    echo_server_command,
    is_mcp_cancelled,
    is_mcp_transport_failure,
)
from blackhole_agent.mcp_elicitation import MCP_ELICITATION_GOAL, MCP_ELICITATION_ID
from blackhole_agent.mcp_handshake_isolation import (
    DEAD_HANDSHAKE_TIMEOUT_SECONDS,
    LIVE_HANDSHAKE_TIMEOUT_SECONDS,
    McpPluginSpec,
    connect_mcp_plane,
)

SCHEMA_VERSION = 1
MCP_CANCELLATION_ID = "capability.mcp-cancellation"
REPO_ROOT = Path(__file__).resolve().parents[2]
PROBE_TIMEOUT_SECONDS = DEAD_HANDSHAKE_TIMEOUT_SECONDS
CANCEL_AFTER_SECONDS = 0.25
SLOW_TOOL_NAME = "slow"
ECHO_TOOL_NAME = "echo"
UNLOCK_TOKEN = "BH-CANCEL-OK"

MCP_CANCELLATION_DONE_WHEN = (
    f"capability_exists:{MCP_CANCELLATION_ID};"
    f"capability_proved:{MCP_CANCELLATION_ID};"
    "no_skill_route"
)
MCP_CANCELLATION_GOAL = (
    "Repair MCP in-flight timeout cancellation: a hosted plugin that occupies "
    "stdio with a long tools/call never receives notifications/cancelled, so the "
    "abandoned request leaves the session blocked until the client times out and "
    "sibling tools on the same session cannot serve. Sessions that skip cancel "
    "stay occupied."
)

_SLOW_TOOL = {
    "name": SLOW_TOOL_NAME,
    "description": "Occupy stdio until notifications/cancelled arrives, then abort.",
    "inputSchema": {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": [],
    },
    "annotations": {"readOnlyHint": False},
}
_ECHO_TOOL = {
    "name": ECHO_TOOL_NAME,
    "description": "Return the supplied text unchanged.",
    "inputSchema": {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    },
    "annotations": {"readOnlyHint": True},
}


def gated_command() -> list[str]:
    """Plugin that occupies tools/call until notifications/cancelled arrives."""

    return [sys.executable, "-u", "-m", "blackhole_agent.mcp_cancellation", "gated"]


def mcp_cancellation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.mcp_cancellation import "
        "builtin_mcp_cancellation_proof; r=builtin_mcp_cancellation_proof(); "
        "assert r['ok'] and r.get('action')=='mcp_cancellation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_mcp_cancellation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=MCP_CANCELLATION_ID,
        name="MCP in-flight request cancellation",
        description=(
            "An MCP stdio session sends notifications/cancelled for an in-flight "
            "tools/call so a plugin occupying the stream aborts with JSON-RPC "
            "-32800 and the same session keeps serving sibling tools. Skip-cancel "
            "sessions stay occupied until timeout."
        ),
        kind="python",
        entry="blackhole_agent.mcp_cancellation:builtin_mcp_cancellation_proof",
        proof_command=mcp_cancellation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.mcp-call-isolation",
            "capability.mcp-elicitation",
        ),
        behavior_paths=(
            "src/blackhole_agent/mcp_client.py",
            "src/blackhole_agent/mcp_cancellation.py",
            "src/blackhole_agent/mcp_handshake_isolation.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A hosted plugin that occupies stdio with a long tools/call is "
            "first-class: Unbound sends notifications/cancelled, the server "
            "acknowledges JSON-RPC -32800, and sibling tools on the same "
            "session return instead of waiting for timeout, while skip-cancel "
            "sessions stay occupied and isolated."
        ),
        tags=("mcp", "cancellation", "timeout", "stdio", "jsonrpc"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260831T080836Z-b519a063",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def _echo_text(plane: Any, server: str, text: str) -> str:
    return _extract_text(plane.call_tool(server, ECHO_TOOL_NAME, {"text": text}))


def _slow_spec(name: str, *, timeout_seconds: float) -> McpPluginSpec:
    return McpPluginSpec(name, gated_command(), timeout_seconds=timeout_seconds)


def builtin_mcp_cancellation_proof() -> dict[str, Any]:
    """Hermetic proof: notifications/cancelled unblocks an occupied stdio session."""

    from blackhole_agent.kernel_genesis_bind import _register_proved as register_catalog_proved
    from blackhole_agent.kernel_genesis_diversify import (
        DIVERSITY_CATALOG,
        _prepare_exhausted_catalog,
        bind_gate_passing_successor,
    )
    from blackhole_agent.mcp_http_event_stream import MCP_HTTP_EVENT_GOAL, MCP_HTTP_EVENT_ID

    catalog = DIVERSITY_CATALOG
    checks: dict[str, bool] = {}
    checks["denylists_self"] = MCP_CANCELLATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(MCP_CANCELLATION_GOAL) == (
        MCP_CANCELLATION_ID,
    )
    checks["elicitation_goal_is_not_cancellation"] = leftover_marker_ids(
        MCP_ELICITATION_GOAL
    ) == (MCP_ELICITATION_ID,)
    checks["call_goal_is_not_cancellation"] = leftover_marker_ids(MCP_CALL_GOAL) == (
        MCP_CALL_ID,
    )
    checks["elicitation_marker_stays_elicitation"] = (
        MCP_CANCELLATION_ID not in leftover_marker_ids(MCP_ELICITATION_GOAL)
    )
    checks["call_marker_stays_isolation"] = MCP_CANCELLATION_ID not in leftover_marker_ids(
        MCP_CALL_GOAL
    )
    checks["http_event_goal_is_not_cancellation"] = leftover_marker_ids(
        MCP_HTTP_EVENT_GOAL
    ) == (MCP_HTTP_EVENT_ID,)
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["catalog_names_cancellation"] = (
        len(catalog) > 20
        and catalog[20]["id"] == MCP_CANCELLATION_ID
        and catalog[19]["id"] == MCP_ELICITATION_ID
    )

    naive = McpStdioSession(gated_command(), timeout_seconds=PROBE_TIMEOUT_SECONDS)
    try:
        naive.start()
        stalled = False
        try:
            naive.call_tool(SLOW_TOOL_NAME, {})
        except McpProtocolError as exc:
            stalled = is_mcp_transport_failure(exc) and not is_mcp_cancelled(exc)
        checks["naive_slow_call_times_out"] = stalled
        checks["naive_did_not_send_cancel"] = naive.cancelled_request_ids == []
    finally:
        naive.kill()

    live = McpStdioSession(
        gated_command(), timeout_seconds=LIVE_HANDSHAKE_TIMEOUT_SECONDS
    )
    try:
        live.start()
        cancelled = False
        try:
            live.call_tool(SLOW_TOOL_NAME, {}, cancel_after=CANCEL_AFTER_SECONDS)
        except McpProtocolError as exc:
            cancelled = is_mcp_cancelled(exc) and UNLOCK_TOKEN in str(exc)
        echoed = _extract_text(live.call_tool(ECHO_TOOL_NAME, {"text": "after-cancel"}))
        checks["cancel_returns_request_cancelled"] = cancelled
        checks["cancel_notification_was_sent"] = bool(live.cancelled_request_ids)
        checks["same_session_echo_after_cancel"] = echoed == "after-cancel"
        checks["cancelled_session_stays_live"] = live.cancelled_request_ids != []
    finally:
        live.kill()

    mixed = connect_mcp_plane(
        [
            _slow_spec("slow", timeout_seconds=LIVE_HANDSHAKE_TIMEOUT_SECONDS),
            McpPluginSpec("live", echo_server_command()),
        ],
        isolate_dead=True,
        isolate_hung_calls=True,
    )
    try:
        cancelled = False
        try:
            mixed.call_tool("slow", SLOW_TOOL_NAME, {}, cancel_after=CANCEL_AFTER_SECONDS)
        except McpProtocolError as exc:
            cancelled = is_mcp_cancelled(exc) and UNLOCK_TOKEN in str(exc)
        sibling = _echo_text(mixed, "live", "from-echo")
        same = _extract_text(mixed.call_tool("slow", ECHO_TOOL_NAME, {"text": "still-slow"}))
        checks["sibling_echo_still_serves"] = (
            mixed.plane_failed is False
            and mixed.live_names == ("live", "slow")
            and cancelled
            and sibling == "from-echo"
            and same == "still-slow"
        )
    finally:
        mixed.close()

    unanswered = connect_mcp_plane(
        [
            _slow_spec("slow", timeout_seconds=PROBE_TIMEOUT_SECONDS),
            McpPluginSpec("live", echo_server_command()),
        ],
        isolate_dead=True,
        isolate_hung_calls=True,
    )
    try:
        hung = False
        try:
            unanswered.call_tool("slow", SLOW_TOOL_NAME, {})
        except McpProtocolError as exc:
            hung = is_mcp_transport_failure(exc)
        sibling = _echo_text(unanswered, "live", "still-here")
        checks["skip_cancel_is_isolated"] = (
            hung
            and unanswered.plane_failed is False
            and "slow" in unanswered.isolated_names
            and unanswered.live_names == ("live",)
            and sibling == "still-here"
        )
    finally:
        unanswered.close()

    with tempfile.TemporaryDirectory(prefix="mcp-cancellation-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != MCP_CANCELLATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_cancellation"] = (
        live_goal == MCP_CANCELLATION_GOAL
        and MCP_CANCELLATION_ID in live_done
        and live_source == "genesis_bind_cancellation"
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_mcp_cancellation_capability()
    return {
        "ok": ok,
        "action": "mcp_cancellation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": MCP_CANCELLATION_GOAL,
        "done_when": MCP_CANCELLATION_DONE_WHEN,
    }


def _write(message: Mapping[str, Any]) -> None:
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def run_stub_server() -> int:
    """Plugin that holds tools/call until notifications/cancelled arrives."""

    pending_slow: dict[str, Any] | None = None

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
        method = message.get("method")
        if method == "notifications/cancelled":
            params = message.get("params") if isinstance(message.get("params"), dict) else {}
            if pending_slow is not None and params.get("requestId") == pending_slow.get("id"):
                _write(
                    {
                        "jsonrpc": "2.0",
                        "id": pending_slow.get("id"),
                        "error": {
                            "code": JSONRPC_REQUEST_CANCELLED,
                            "message": f"Request cancelled:{UNLOCK_TOKEN}",
                        },
                    }
                )
                pending_slow = None
            continue
        if method == "notifications/initialized" or (
            "id" not in message and method is not None
        ):
            continue
        request_id = message.get("id")
        if method == "initialize":
            _write(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "blackhole-cancellation-gated", "version": "0"},
                    },
                }
            )
            continue
        if method == "tools/list":
            _write(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {"tools": [_SLOW_TOOL, _ECHO_TOOL]},
                }
            )
            continue
        if method == "tools/call":
            params = message.get("params") if isinstance(message.get("params"), dict) else {}
            name = str(params.get("name") or "")
            arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
            if name == SLOW_TOOL_NAME:
                pending_slow = message
                continue
            if name == ECHO_TOOL_NAME:
                _write(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": str(arguments.get("text") or ""),
                                }
                            ],
                            "isError": False,
                        },
                    }
                )
                continue
            _write(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32601, "message": f"unknown tool: {name}"},
                }
            )
            continue
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] != "gated":
        raise SystemExit(f"unknown MCP cancellation stub mode: {args[:1]}")
    return run_stub_server()


if __name__ == "__main__":
    raise SystemExit(main())
