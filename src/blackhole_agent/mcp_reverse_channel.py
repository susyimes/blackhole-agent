"""Answer server-originated JSON-RPC so spec-compliant MCP plugins stay live.

Handshake and tool-call isolation keep sibling plugins serving when a
peer hangs. A plugin that speaks the reverse channel — ``ping`` or
``roots/list`` — before returning ``tools/call`` is still treated as hung:
the client ignores inbound requests, the plugin waits, and isolation
kills a spec-compliant server.

This module closes that hole:

- answer ``ping`` and ``roots/list`` on the same stdio session
- JSON-RPC-error unknown inbound methods without stalling
- leave the fail-open ignore path so the hole stays falsifiable
- keep sibling plugins serving
"""

from __future__ import annotations

import json
import sys
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
from blackhole_agent.mcp_client import (
    DEFAULT_MCP_ROOTS,
    McpProtocolError,
    McpStdioSession,
    _extract_text,
    echo_server_command,
    is_jsonrpc_server_request,
    is_mcp_transport_failure,
    reverse_channel_reply,
)
from blackhole_agent.mcp_handshake_isolation import (
    DEAD_HANDSHAKE_TIMEOUT_SECONDS,
    LIVE_HANDSHAKE_TIMEOUT_SECONDS,
    McpPluginSpec,
    connect_mcp_plane,
)

SCHEMA_VERSION = 1
MCP_REVERSE_ID = "capability.mcp-reverse-channel"
REPO_ROOT = Path(__file__).resolve().parents[2]
PROBE_TIMEOUT_SECONDS = DEAD_HANDSHAKE_TIMEOUT_SECONDS

MCP_REVERSE_DONE_WHEN = (
    f"capability_exists:{MCP_REVERSE_ID};"
    f"capability_proved:{MCP_REVERSE_ID};"
    "no_skill_route"
)
MCP_REVERSE_GOAL = (
    "Answer server-originated JSON-RPC requests on the MCP stdio session "
    "(ping and roots/list) so a spec-compliant plugin that probes the client "
    "before returning a tool result stays live instead of stalling."
)

_ECHO_TOOL = {
    "name": "echo",
    "description": "Return the supplied text unchanged.",
    "inputSchema": {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    },
    "annotations": {"readOnlyHint": True},
}


def probe_command() -> list[str]:
    """Plugin that pings and lists roots before answering tools/call."""

    return [sys.executable, "-u", "-m", "blackhole_agent.mcp_reverse_channel", "probe"]


def unknown_command() -> list[str]:
    """Plugin that sends an unknown reverse-channel method before tools/call."""

    return [sys.executable, "-u", "-m", "blackhole_agent.mcp_reverse_channel", "unknown"]


def mcp_reverse_channel_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.mcp_reverse_channel import "
        "builtin_mcp_reverse_channel_proof; r=builtin_mcp_reverse_channel_proof(); "
        "assert r['ok'] and r.get('action')=='mcp_reverse_channel' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_mcp_reverse_channel_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=MCP_REVERSE_ID,
        name="MCP reverse-channel",
        description=(
            "An MCP stdio session answers server-originated JSON-RPC ping and "
            "roots/list requests so a spec-compliant plugin that probes the "
            "client before returning a tool result stays live instead of stalling."
        ),
        kind="python",
        entry="blackhole_agent.mcp_reverse_channel:builtin_mcp_reverse_channel_proof",
        proof_command=mcp_reverse_channel_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.mcp-call-isolation",
        ),
        behavior_paths=(
            "src/blackhole_agent/mcp_client.py",
            "src/blackhole_agent/mcp_reverse_channel.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "Spec-compliant MCP plugins that send ping or roots/list before a "
            "tool result stay live: the client answers those inbound JSON-RPC "
            "requests on the same stdio session instead of ignoring them until "
            "the plugin stalls."
        ),
        tags=("mcp", "reverse-channel", "ping", "roots", "jsonrpc"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260830T024351Z-f6ae66be",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def _echo_text(plane: Any, server: str, text: str) -> str:
    return _extract_text(plane.call_tool(server, "echo", {"text": text}))


def builtin_mcp_reverse_channel_proof() -> dict[str, Any]:
    """Hermetic proof: answering ping/roots keeps a probing plugin live."""

    from blackhole_agent.kernel_genesis_diversify import DIVERSITY_CATALOG
    from blackhole_agent.mcp_call_isolation import MCP_CALL_GOAL
    from blackhole_agent.mcp_handshake_isolation import MCP_HANDSHAKE_GOAL

    catalog = DIVERSITY_CATALOG

    checks: dict[str, bool] = {}
    checks["denylists_self"] = MCP_REVERSE_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(MCP_REVERSE_GOAL) == (MCP_REVERSE_ID,)
    checks["call_goal_is_not_reverse"] = leftover_marker_ids(MCP_CALL_GOAL) != (MCP_REVERSE_ID,)
    checks["handshake_goal_is_not_reverse"] = leftover_marker_ids(MCP_HANDSHAKE_GOAL) != (
        MCP_REVERSE_ID,
    )
    checks["schema_version"] = SCHEMA_VERSION == 1
    ping = reverse_channel_reply({"jsonrpc": "2.0", "id": 7, "method": "ping"})
    checks["ping_reply_is_empty_result"] = ping.get("result") == {} and ping.get("id") == 7
    roots = reverse_channel_reply({"jsonrpc": "2.0", "id": 8, "method": "roots/list"})
    checks["roots_reply_lists_default"] = (roots.get("result") or {}).get("roots") == list(
        DEFAULT_MCP_ROOTS
    )
    unknown = reverse_channel_reply({"jsonrpc": "2.0", "id": 9, "method": "elicitation/create"})
    checks["unknown_reply_is_method_not_found"] = (
        (unknown.get("error") or {}).get("code") == -32601 and unknown.get("id") == 9
    )
    checks["response_is_not_a_server_request"] = not is_jsonrpc_server_request(
        {"jsonrpc": "2.0", "id": 1, "result": {}}
    )
    checks["notification_is_not_a_server_request"] = not is_jsonrpc_server_request(
        {"jsonrpc": "2.0", "method": "notifications/progress", "params": {}}
    )
    checks["inbound_ping_is_a_server_request"] = is_jsonrpc_server_request(
        {"jsonrpc": "2.0", "id": 1, "method": "ping"}
    )

    naive = McpStdioSession(
        probe_command(),
        timeout_seconds=PROBE_TIMEOUT_SECONDS,
        answer_reverse_channel=False,
    )
    try:
        naive.start()
        stalled = False
        try:
            naive.call_tool("echo", {"text": "nope"})
        except McpProtocolError as exc:
            stalled = is_mcp_transport_failure(exc)
        checks["naive_probe_stalls"] = stalled and naive.answered_requests == []
    finally:
        naive.kill()

    live = McpStdioSession(
        probe_command(),
        timeout_seconds=LIVE_HANDSHAKE_TIMEOUT_SECONDS,
        answer_reverse_channel=True,
    )
    try:
        live.start()
        served = _extract_text(live.call_tool("echo", {"text": "probe-ok"}))
        methods = tuple(item.get("method") for item in live.answered_requests)
        checks["reverse_channel_call_succeeds"] = served.startswith("probe-ok")
        checks["reverse_channel_answered_ping"] = "ping" in methods
        checks["reverse_channel_answered_roots"] = "roots/list" in methods
        checks["reverse_channel_embeds_roots"] = "file:///workspace" in served
    finally:
        live.kill()

    unknown_session = McpStdioSession(
        unknown_command(),
        timeout_seconds=LIVE_HANDSHAKE_TIMEOUT_SECONDS,
        answer_reverse_channel=True,
    )
    try:
        unknown_session.start()
        served = _extract_text(unknown_session.call_tool("echo", {"text": "still-ok"}))
        methods = tuple(item.get("method") for item in unknown_session.answered_requests)
        errors = tuple(bool(item.get("error")) for item in unknown_session.answered_requests)
        checks["unknown_server_method_does_not_stall"] = (
            served == "still-ok"
            and "elicitation/create" in methods
            and True in errors
        )
    finally:
        unknown_session.kill()

    mixed = connect_mcp_plane(
        [
            McpPluginSpec("probe", probe_command(), timeout_seconds=LIVE_HANDSHAKE_TIMEOUT_SECONDS),
            McpPluginSpec("live", echo_server_command(), timeout_seconds=LIVE_HANDSHAKE_TIMEOUT_SECONDS),
        ],
        isolate_dead=True,
        isolate_hung_calls=True,
    )
    try:
        probed = _echo_text(mixed, "probe", "from-probe")
        echoed = _echo_text(mixed, "live", "from-echo")
        checks["sibling_echo_still_serves"] = (
            mixed.plane_failed is False
            and mixed.live_names == ("live", "probe")
            and probed.startswith("from-probe")
            and echoed == "from-echo"
        )
    finally:
        mixed.close()

    checks["catalog_names_reverse"] = catalog[5]["id"] == MCP_REVERSE_ID
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_mcp_reverse_channel_capability()
    return {
        "ok": ok,
        "action": "mcp_reverse_channel",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": MCP_REVERSE_GOAL,
        "done_when": MCP_REVERSE_DONE_WHEN,
    }


def _write(message: Mapping[str, Any]) -> None:
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def run_stub_server(mode: str) -> int:
    """Plugin that probes the client on the reverse channel before tools/call."""

    ping_id = 9001
    roots_id = 9002
    unknown_id = 9003
    pending_call: dict[str, Any] | None = None
    probe_stage = ""
    roots_payload = ""

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
                        "serverInfo": {"name": f"blackhole-reverse-{mode}", "version": "0"},
                    },
                }
            )
            continue
        if method == "tools/list":
            _write({"jsonrpc": "2.0", "id": request_id, "result": {"tools": [_ECHO_TOOL]}})
            continue
        if method == "tools/call":
            pending_call = message
            if mode == "unknown":
                _write(
                    {
                        "jsonrpc": "2.0",
                        "id": unknown_id,
                        "method": "elicitation/create",
                        "params": {"message": "unused"},
                    }
                )
                arguments = (message.get("params") or {}).get("arguments") or {}
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
                pending_call = None
                continue
            probe_stage = "ping"
            _write({"jsonrpc": "2.0", "id": ping_id, "method": "ping", "params": {}})
            continue
        if pending_call is not None and request_id == ping_id and "method" not in message:
            if "error" in message:
                continue
            probe_stage = "roots"
            _write({"jsonrpc": "2.0", "id": roots_id, "method": "roots/list", "params": {}})
            continue
        if pending_call is not None and request_id == roots_id and "method" not in message:
            result = message.get("result") if isinstance(message.get("result"), dict) else {}
            roots = result.get("roots") if isinstance(result.get("roots"), list) else []
            uris = [str(item.get("uri") or "") for item in roots if isinstance(item, dict)]
            roots_payload = ",".join(uris)
            arguments = (pending_call.get("params") or {}).get("arguments") or {}
            text = str(arguments.get("text") or "")
            _write(
                {
                    "jsonrpc": "2.0",
                    "id": pending_call.get("id"),
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": f"{text}|ping:{probe_stage}|roots:{roots_payload}",
                            }
                        ],
                        "isError": False,
                    },
                }
            )
            pending_call = None
            continue
        if method:
            _write(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32601, "message": f"method not found: {method}"},
                }
            )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    mode = str(args[0] if args else "probe")
    if mode not in {"probe", "unknown"}:
        raise SystemExit(f"unknown MCP reverse-channel stub mode: {mode}")
    return run_stub_server(mode)


if __name__ == "__main__":
    raise SystemExit(main())
