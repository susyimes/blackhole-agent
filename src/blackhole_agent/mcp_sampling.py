"""Answer MCP sampling/createMessage so sample-gated plugins stay on the live plane.

Ping and roots/list keep a probing plugin live. A plugin that sends
``sampling/createMessage`` before returning ``tools/call`` is still treated
as hung: the client ignores inbound sampling, the plugin waits for a model
completion, and isolation kills a spec-compliant sample-gated server.

This module closes that hole:

- advertise the sampling client capability on initialize
- answer ``sampling/createMessage`` with a deterministic completion
- keep sibling plugins serving
- leave the unanswered sampling path so the hole stays falsifiable
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
    DEFAULT_SAMPLING_MODEL,
    McpProtocolError,
    McpStdioSession,
    _extract_text,
    echo_server_command,
    is_mcp_transport_failure,
    sampling_reply,
    sampling_user_text,
)
from blackhole_agent.mcp_handshake_isolation import (
    DEAD_HANDSHAKE_TIMEOUT_SECONDS,
    LIVE_HANDSHAKE_TIMEOUT_SECONDS,
    McpPluginSpec,
    connect_mcp_plane,
)
from blackhole_agent.mcp_reverse_channel import MCP_REVERSE_GOAL, MCP_REVERSE_ID

SCHEMA_VERSION = 1
MCP_SAMPLING_ID = "capability.mcp-sampling"
REPO_ROOT = Path(__file__).resolve().parents[2]
PROBE_TIMEOUT_SECONDS = DEAD_HANDSHAKE_TIMEOUT_SECONDS
GATED_TOOL_NAME = "echo"

MCP_SAMPLING_DONE_WHEN = (
    f"capability_exists:{MCP_SAMPLING_ID};"
    f"capability_proved:{MCP_SAMPLING_ID};"
    "no_skill_route"
)
MCP_SAMPLING_GOAL = (
    "Repair MCP sampling reverse channel: a hosted plugin that sends "
    "sampling/createMessage never receives a model completion, so a "
    "sample-gated tool stalls on the live plane. Answer the inbound sampling "
    "request and keep sibling plugins serving."
)

_ECHO_TOOL = {
    "name": GATED_TOOL_NAME,
    "description": "Return the supplied text plus a sampled completion.",
    "inputSchema": {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    },
    "annotations": {"readOnlyHint": True},
}


def gated_command() -> list[str]:
    """Plugin that requests sampling/createMessage before answering tools/call."""

    return [sys.executable, "-u", "-m", "blackhole_agent.mcp_sampling", "gated"]


def mcp_sampling_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.mcp_sampling import "
        "builtin_mcp_sampling_proof; r=builtin_mcp_sampling_proof(); "
        "assert r['ok'] and r.get('action')=='mcp_sampling' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_mcp_sampling_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=MCP_SAMPLING_ID,
        name="MCP sampling reverse-channel",
        description=(
            "An MCP stdio session advertises sampling and answers "
            "sampling/createMessage so a sample-gated plugin receives a model "
            "completion and returns its tool result instead of stalling."
        ),
        kind="python",
        entry="blackhole_agent.mcp_sampling:builtin_mcp_sampling_proof",
        proof_command=mcp_sampling_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.mcp-reverse-channel",
        ),
        behavior_paths=(
            "src/blackhole_agent/mcp_client.py",
            "src/blackhole_agent/mcp_sampling.py",
            "src/blackhole_agent/mcp_handshake_isolation.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A hosted plugin that sends sampling/createMessage is no longer "
            "isolated as hung: Unbound advertises the sampling client capability, "
            "answers the inbound sampling request with a model completion, and "
            "lets the sample-gated tool return beside live siblings."
        ),
        tags=("mcp", "sampling", "reverse-channel", "createMessage", "jsonrpc"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260831T044547Z-1255468f",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def _echo_text(plane: Any, server: str, text: str) -> str:
    return _extract_text(plane.call_tool(server, GATED_TOOL_NAME, {"text": text}))


def _sampling_spec(name: str, *, answer: bool) -> McpPluginSpec:
    return McpPluginSpec(
        name,
        gated_command(),
        timeout_seconds=LIVE_HANDSHAKE_TIMEOUT_SECONDS if answer else PROBE_TIMEOUT_SECONDS,
        answer_sampling=answer,
    )


def builtin_mcp_sampling_proof() -> dict[str, Any]:
    """Hermetic proof: answering sampling/createMessage unblocks a gated plugin."""

    from blackhole_agent.kernel_genesis_bind import _register_proved as register_catalog_proved
    from blackhole_agent.kernel_genesis_diversify import (
        DIVERSITY_CATALOG,
        _prepare_exhausted_catalog,
        bind_gate_passing_successor,
    )
    from blackhole_agent.kernel_half_open_probe import HALF_OPEN_PROBE_GOAL, HALF_OPEN_PROBE_ID
    from blackhole_agent.mcp_call_isolation import MCP_CALL_GOAL

    catalog = DIVERSITY_CATALOG
    checks: dict[str, bool] = {}
    checks["denylists_self"] = MCP_SAMPLING_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(MCP_SAMPLING_GOAL) == (MCP_SAMPLING_ID,)
    checks["reverse_goal_is_not_sampling"] = leftover_marker_ids(MCP_REVERSE_GOAL) == (
        MCP_REVERSE_ID,
    )
    checks["reverse_marker_stays_reverse"] = MCP_SAMPLING_ID not in leftover_marker_ids(
        MCP_REVERSE_GOAL
    )
    checks["call_goal_is_not_sampling"] = leftover_marker_ids(MCP_CALL_GOAL) != (MCP_SAMPLING_ID,)
    checks["probe_goal_is_not_sampling"] = leftover_marker_ids(HALF_OPEN_PROBE_GOAL) == (
        HALF_OPEN_PROBE_ID,
    )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["catalog_names_sampling"] = (
        len(catalog) > 14
        and catalog[14]["id"] == MCP_SAMPLING_ID
        and catalog[13]["id"] == HALF_OPEN_PROBE_ID
    )

    request = {
        "jsonrpc": "2.0",
        "id": 11,
        "method": "sampling/createMessage",
        "params": {
            "messages": [
                {"role": "user", "content": {"type": "text", "text": "gate-me"}},
            ],
            "maxTokens": 32,
        },
    }
    reply = sampling_reply(request)
    checks["sampling_user_text_reads_last"] = sampling_user_text(request) == "gate-me"
    checks["sampling_reply_is_assistant_completion"] = (
        reply.get("id") == 11
        and (reply.get("result") or {}).get("role") == "assistant"
        and ((reply.get("result") or {}).get("content") or {}).get("text") == "sampled:gate-me"
        and (reply.get("result") or {}).get("model") == DEFAULT_SAMPLING_MODEL
    )
    empty = sampling_reply({"jsonrpc": "2.0", "id": 12, "method": "sampling/createMessage"})
    checks["empty_sampling_reply_has_default_text"] = (
        ((empty.get("result") or {}).get("content") or {}).get("text") == "sampled"
    )

    naive = McpStdioSession(
        gated_command(),
        timeout_seconds=PROBE_TIMEOUT_SECONDS,
        answer_reverse_channel=True,
        answer_sampling=False,
    )
    try:
        naive.start()
        stalled = False
        try:
            naive.call_tool(GATED_TOOL_NAME, {"text": "nope"})
        except McpProtocolError as exc:
            stalled = is_mcp_transport_failure(exc)
        checks["naive_sampling_stalls"] = stalled and naive.answered_requests == []
    finally:
        naive.kill()

    live = McpStdioSession(
        gated_command(),
        timeout_seconds=LIVE_HANDSHAKE_TIMEOUT_SECONDS,
        answer_reverse_channel=True,
        answer_sampling=True,
    )
    try:
        live.start()
        served = _extract_text(live.call_tool(GATED_TOOL_NAME, {"text": "gate-me"}))
        methods = tuple(item.get("method") for item in live.answered_requests)
        checks["sampling_call_succeeds"] = served == "gate-me|sampled:gate-me"
        checks["sampling_answered_create_message"] = "sampling/createMessage" in methods
        checks["sampling_did_not_error"] = all(
            not item.get("error")
            for item in live.answered_requests
            if item.get("method") == "sampling/createMessage"
        )
    finally:
        live.kill()

    mixed = connect_mcp_plane(
        [_sampling_spec("sample", answer=True), McpPluginSpec("live", echo_server_command())],
        isolate_dead=True,
        isolate_hung_calls=True,
    )
    try:
        sampled = _echo_text(mixed, "sample", "from-sample")
        echoed = _echo_text(mixed, "live", "from-echo")
        checks["sibling_echo_still_serves"] = (
            mixed.plane_failed is False
            and mixed.live_names == ("live", "sample")
            and sampled == "from-sample|sampled:from-sample"
            and echoed == "from-echo"
        )
    finally:
        mixed.close()

    unanswered = connect_mcp_plane(
        [_sampling_spec("sample", answer=False), McpPluginSpec("live", echo_server_command())],
        isolate_dead=True,
        isolate_hung_calls=True,
    )
    try:
        hung = False
        try:
            unanswered.call_tool("sample", GATED_TOOL_NAME, {"text": "nope"})
        except McpProtocolError as exc:
            hung = is_mcp_transport_failure(exc)
        sibling = _echo_text(unanswered, "live", "still-here")
        checks["unanswered_sampling_is_isolated"] = (
            hung
            and unanswered.plane_failed is False
            and "sample" in unanswered.isolated_names
            and unanswered.live_names == ("live",)
            and sibling == "still-here"
        )
    finally:
        unanswered.close()

    with tempfile.TemporaryDirectory(prefix="mcp-sampling-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != MCP_SAMPLING_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_sampling"] = (
        live_goal == MCP_SAMPLING_GOAL
        and MCP_SAMPLING_ID in live_done
        and live_source == "genesis_bind_sampling"
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_mcp_sampling_capability()
    return {
        "ok": ok,
        "action": "mcp_sampling",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": MCP_SAMPLING_GOAL,
        "done_when": MCP_SAMPLING_DONE_WHEN,
    }


def _write(message: Mapping[str, Any]) -> None:
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def run_stub_server() -> int:
    """Plugin that samples the client before answering tools/call."""

    sampling_id = 9101
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
                        "serverInfo": {"name": "blackhole-sampling-gated", "version": "0"},
                    },
                }
            )
            continue
        if method == "tools/list":
            _write({"jsonrpc": "2.0", "id": request_id, "result": {"tools": [_ECHO_TOOL]}})
            continue
        if method == "tools/call":
            pending_call = message
            arguments = (message.get("params") or {}).get("arguments") or {}
            user_text = str(arguments.get("text") or "")
            _write(
                {
                    "jsonrpc": "2.0",
                    "id": sampling_id,
                    "method": "sampling/createMessage",
                    "params": {
                        "messages": [
                            {
                                "role": "user",
                                "content": {"type": "text", "text": user_text},
                            }
                        ],
                        "maxTokens": 32,
                        "modelPreferences": {"hints": [{"name": DEFAULT_SAMPLING_MODEL}]},
                    },
                }
            )
            continue
        if pending_call is not None and request_id == sampling_id and "method" not in message:
            if "error" in message:
                continue
            result = message.get("result") if isinstance(message.get("result"), dict) else {}
            content = result.get("content") if isinstance(result.get("content"), dict) else {}
            sampled = str(content.get("text") or "")
            if not sampled:
                continue
            arguments = (pending_call.get("params") or {}).get("arguments") or {}
            user_text = str(arguments.get("text") or "")
            _write(
                {
                    "jsonrpc": "2.0",
                    "id": pending_call.get("id"),
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": f"{user_text}|{sampled}",
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
        raise SystemExit(f"unknown MCP sampling stub mode: {args[:1]}")
    return run_stub_server()


if __name__ == "__main__":
    raise SystemExit(main())
