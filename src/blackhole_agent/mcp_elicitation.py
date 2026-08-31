"""Answer MCP elicitation/create on stdio so form-gated plugins stay live.

HTTP GET SSE already answers ``elicitation/create``. A plugin that sends the
same operator-form request on stdio is still treated as unknown: Unbound
JSON-RPC-errors method not found, the plugin waits for an accept, and a
form-gated tool stalls (or isolation kills it) instead of returning a sealed
payload.

This module closes that hole:

- advertise the elicitation client capability on initialize
- answer ``elicitation/create`` on the live stdio session
- keep a skip-elicitation path so the unset hole stays falsifiable
- let a form-gated plugin and a tools-only sibling serve together
- bind this family as the next diversity-catalog successor after logging
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
from blackhole_agent.mcp_client import (
    DEFAULT_ELICITATION_CONTENT,
    McpProtocolError,
    McpStdioSession,
    _extract_text,
    echo_server_command,
    elicitation_reply,
    is_mcp_transport_failure,
)
from blackhole_agent.mcp_handshake_isolation import (
    DEAD_HANDSHAKE_TIMEOUT_SECONDS,
    LIVE_HANDSHAKE_TIMEOUT_SECONDS,
    McpPluginSpec,
    connect_mcp_plane,
)
from blackhole_agent.mcp_logging import MCP_LOGGING_GOAL, MCP_LOGGING_ID

SCHEMA_VERSION = 1
MCP_ELICITATION_ID = "capability.mcp-elicitation"
REPO_ROOT = Path(__file__).resolve().parents[2]
PROBE_TIMEOUT_SECONDS = DEAD_HANDSHAKE_TIMEOUT_SECONDS
GATED_TOOL_NAME = "echo"
UNLOCK_TOKEN = "BH-ELICIT-OK"
DECLINE_ERROR = "elicitation declined"

MCP_ELICITATION_DONE_WHEN = (
    f"capability_exists:{MCP_ELICITATION_ID};"
    f"capability_proved:{MCP_ELICITATION_ID};"
    "no_skill_route"
)
MCP_ELICITATION_GOAL = (
    "Repair MCP stdio elicitation reverse channel: a hosted plugin that sends "
    "elicitation/create over stdio never receives an operator form, so a "
    "form-gated stdio tool stalls on the live plane. Fail-closed sessions that "
    "skip the elicitation reply stay forbidden."
)

_ECHO_TOOL = {
    "name": GATED_TOOL_NAME,
    "description": "Return the supplied text plus the unlock token after the operator form is accepted.",
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
            "description": "Allow the gated stdio tool to run.",
        }
    },
    "required": ["approved"],
}


def gated_command() -> list[str]:
    """Plugin that requests elicitation/create before answering tools/call."""

    return [sys.executable, "-u", "-m", "blackhole_agent.mcp_elicitation", "gated"]


def mcp_elicitation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.mcp_elicitation import "
        "builtin_mcp_elicitation_proof; r=builtin_mcp_elicitation_proof(); "
        "assert r['ok'] and r.get('action')=='mcp_elicitation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_mcp_elicitation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=MCP_ELICITATION_ID,
        name="MCP stdio elicitation reverse-channel",
        description=(
            "An MCP stdio session advertises elicitation and answers "
            "elicitation/create so a form-gated plugin receives an operator "
            "form and returns its tool result instead of stalling. Skip-"
            "elicitation sessions stay fail-closed."
        ),
        kind="python",
        entry="blackhole_agent.mcp_elicitation:builtin_mcp_elicitation_proof",
        proof_command=mcp_elicitation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.mcp-reverse-channel",
            "capability.mcp-logging",
        ),
        behavior_paths=(
            "src/blackhole_agent/mcp_client.py",
            "src/blackhole_agent/mcp_elicitation.py",
            "src/blackhole_agent/mcp_handshake_isolation.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A hosted plugin that sends elicitation/create over stdio is "
            "first-class: Unbound advertises the elicitation client capability, "
            "answers the inbound operator form, and a form-gated tool returns "
            "the sealed payload instead of stalling, while skip-elicitation "
            "sessions stay fail-closed and siblings keep serving."
        ),
        tags=("mcp", "elicitation", "stdio", "reverse-channel", "jsonrpc"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260831T073354Z-08ec5762",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def _echo_text(plane: Any, server: str, text: str) -> str:
    return _extract_text(plane.call_tool(server, GATED_TOOL_NAME, {"text": text}))


def _elicitation_spec(name: str, *, answer: bool) -> McpPluginSpec:
    return McpPluginSpec(
        name,
        gated_command(),
        timeout_seconds=LIVE_HANDSHAKE_TIMEOUT_SECONDS if answer else PROBE_TIMEOUT_SECONDS,
        answer_elicitation=answer,
    )


def builtin_mcp_elicitation_proof() -> dict[str, Any]:
    """Hermetic proof: answering elicitation/create unblocks a gated stdio plugin."""

    from blackhole_agent.kernel_genesis_bind import _register_proved as register_catalog_proved
    from blackhole_agent.kernel_genesis_diversify import (
        DIVERSITY_CATALOG,
        _prepare_exhausted_catalog,
        bind_gate_passing_successor,
    )
    from blackhole_agent.mcp_call_isolation import MCP_CALL_GOAL
    from blackhole_agent.mcp_http_event_stream import MCP_HTTP_EVENT_GOAL, MCP_HTTP_EVENT_ID
    from blackhole_agent.mcp_sampling import MCP_SAMPLING_GOAL, MCP_SAMPLING_ID

    catalog = DIVERSITY_CATALOG
    checks: dict[str, bool] = {}
    checks["denylists_self"] = MCP_ELICITATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(MCP_ELICITATION_GOAL) == (MCP_ELICITATION_ID,)
    checks["logging_goal_is_not_elicitation"] = leftover_marker_ids(MCP_LOGGING_GOAL) == (
        MCP_LOGGING_ID,
    )
    checks["logging_marker_stays_logging"] = MCP_ELICITATION_ID not in leftover_marker_ids(
        MCP_LOGGING_GOAL
    )
    checks["sampling_goal_is_not_elicitation"] = leftover_marker_ids(MCP_SAMPLING_GOAL) == (
        MCP_SAMPLING_ID,
    )
    checks["http_event_goal_is_not_elicitation"] = leftover_marker_ids(MCP_HTTP_EVENT_GOAL) == (
        MCP_HTTP_EVENT_ID,
    )
    checks["call_goal_is_not_elicitation"] = leftover_marker_ids(MCP_CALL_GOAL) != (
        MCP_ELICITATION_ID,
    )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["catalog_names_elicitation"] = (
        len(catalog) > 19
        and catalog[19]["id"] == MCP_ELICITATION_ID
        and catalog[18]["id"] == MCP_LOGGING_ID
    )

    request = {
        "jsonrpc": "2.0",
        "id": 21,
        "method": "elicitation/create",
        "params": {
            "message": "Approve the gated stdio tool?",
            "requestedSchema": ELICITATION_SCHEMA,
        },
    }
    reply = elicitation_reply(request)
    checks["elicitation_reply_accepts"] = (
        reply.get("id") == 21
        and (reply.get("result") or {}).get("action") == "accept"
        and (reply.get("result") or {}).get("content") == dict(DEFAULT_ELICITATION_CONTENT)
    )
    decline = elicitation_reply(request, action="decline")
    checks["elicitation_reply_declines"] = (
        decline.get("id") == 21
        and (decline.get("result") or {}).get("action") == "decline"
        and "content" not in (decline.get("result") or {})
    )

    naive = McpStdioSession(
        gated_command(),
        timeout_seconds=PROBE_TIMEOUT_SECONDS,
        answer_reverse_channel=True,
        answer_elicitation=False,
    )
    try:
        naive.start()
        stalled = False
        try:
            naive.call_tool(GATED_TOOL_NAME, {"text": "nope"})
        except McpProtocolError as exc:
            stalled = is_mcp_transport_failure(exc)
        methods = tuple(item.get("method") for item in naive.answered_requests)
        checks["naive_elicitation_stalls"] = stalled and "elicitation/create" in methods
    finally:
        naive.kill()

    live = McpStdioSession(
        gated_command(),
        timeout_seconds=LIVE_HANDSHAKE_TIMEOUT_SECONDS,
        answer_reverse_channel=True,
        answer_elicitation=True,
    )
    try:
        live.start()
        advertised = live.client_capabilities.get("elicitation")
        served = _extract_text(live.call_tool(GATED_TOOL_NAME, {"text": "gate-me"}))
        methods = tuple(item.get("method") for item in live.answered_requests)
        checks["elicitation_capability_advertised"] = isinstance(advertised, Mapping)
        checks["elicitation_call_succeeds"] = served == f"gate-me|{UNLOCK_TOKEN}"
        checks["elicitation_answered_create"] = "elicitation/create" in methods
        checks["elicitation_did_not_error"] = all(
            not item.get("error")
            for item in live.answered_requests
            if item.get("method") == "elicitation/create"
        )
    finally:
        live.kill()

    declined = McpStdioSession(
        gated_command(),
        timeout_seconds=LIVE_HANDSHAKE_TIMEOUT_SECONDS,
        answer_reverse_channel=True,
        answer_elicitation=True,
        elicitation_action="decline",
    )
    try:
        declined.start()
        unread = declined.call_tool(GATED_TOOL_NAME, {"text": "nope"})
        checks["decline_stays_fail_closed"] = (
            unread.get("isError") is True and DECLINE_ERROR in _extract_text(unread)
        )
    finally:
        declined.kill()

    mixed = connect_mcp_plane(
        [_elicitation_spec("elicit", answer=True), McpPluginSpec("live", echo_server_command())],
        isolate_dead=True,
        isolate_hung_calls=True,
    )
    try:
        elicited = _echo_text(mixed, "elicit", "from-elicit")
        echoed = _echo_text(mixed, "live", "from-echo")
        checks["sibling_echo_still_serves"] = (
            mixed.plane_failed is False
            and mixed.live_names == ("elicit", "live")
            and elicited == f"from-elicit|{UNLOCK_TOKEN}"
            and echoed == "from-echo"
        )
    finally:
        mixed.close()

    unanswered = connect_mcp_plane(
        [_elicitation_spec("elicit", answer=False), McpPluginSpec("live", echo_server_command())],
        isolate_dead=True,
        isolate_hung_calls=True,
    )
    try:
        hung = False
        try:
            unanswered.call_tool("elicit", GATED_TOOL_NAME, {"text": "nope"})
        except McpProtocolError as exc:
            hung = is_mcp_transport_failure(exc)
        sibling = _echo_text(unanswered, "live", "still-here")
        checks["unanswered_elicitation_is_isolated"] = (
            hung
            and unanswered.plane_failed is False
            and "elicit" in unanswered.isolated_names
            and unanswered.live_names == ("live",)
            and sibling == "still-here"
        )
    finally:
        unanswered.close()

    with tempfile.TemporaryDirectory(prefix="mcp-elicitation-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != MCP_ELICITATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_elicitation"] = (
        live_goal == MCP_ELICITATION_GOAL
        and MCP_ELICITATION_ID in live_done
        and live_source == "genesis_bind_elicitation"
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_mcp_elicitation_capability()
    return {
        "ok": ok,
        "action": "mcp_elicitation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": MCP_ELICITATION_GOAL,
        "done_when": MCP_ELICITATION_DONE_WHEN,
    }


def _write(message: Mapping[str, Any]) -> None:
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def run_stub_server() -> int:
    """Plugin that elicits an operator form before answering tools/call."""

    elicit_id = 9201
    pending_call: dict[str, Any] | None = None

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
                        "serverInfo": {"name": "blackhole-elicitation-gated", "version": "0"},
                    },
                }
            )
            continue
        if method == "tools/list":
            _write({"jsonrpc": "2.0", "id": request_id, "result": {"tools": [_ECHO_TOOL]}})
            continue
        if method == "tools/call":
            pending_call = message
            _write(
                {
                    "jsonrpc": "2.0",
                    "id": elicit_id,
                    "method": "elicitation/create",
                    "params": {
                        "message": "Approve the gated stdio tool?",
                        "requestedSchema": ELICITATION_SCHEMA,
                    },
                }
            )
            continue
        if pending_call is not None and request_id == elicit_id and "method" not in message:
            if "error" in message:
                continue
            result = message.get("result") if isinstance(message.get("result"), dict) else {}
            action = str(result.get("action") or "")
            content = result.get("content") if isinstance(result.get("content"), dict) else {}
            arguments = (pending_call.get("params") or {}).get("arguments") or {}
            user_text = str(arguments.get("text") or "")
            if action != "accept" or content.get("approved") is not True:
                _write(
                    {
                        "jsonrpc": "2.0",
                        "id": pending_call.get("id"),
                        "result": {
                            "content": [{"type": "text", "text": DECLINE_ERROR}],
                            "isError": True,
                        },
                    }
                )
                pending_call = None
                continue
            _write(
                {
                    "jsonrpc": "2.0",
                    "id": pending_call.get("id"),
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": f"{user_text}|{UNLOCK_TOKEN}",
                            }
                        ],
                        "isError": False,
                    },
                }
            )
            pending_call = None
            continue
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] != "gated":
        raise SystemExit(f"unknown MCP elicitation stub mode: {args[:1]}")
    return run_stub_server()


if __name__ == "__main__":
    raise SystemExit(main())
