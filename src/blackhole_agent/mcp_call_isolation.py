"""Isolate a hung MCP tools/call so sibling plugins keep serving.

Handshake isolation keeps the plane up when initialize never arrives. A
plugin that answers initialize but never returns ``tools/list`` is still
accepted as live with no tools, and a live plugin whose ``tools/call``
never returns stays on the plane. Sibling servers look blocked; the hung
subprocess keeps running.

This module closes that hole:

- isolate a plugin whose tools/list never returns after initialize
- isolate a plugin whose tools/call times out or whose stdout closes
- keep sibling servers serving
- leave JSON-RPC tool errors on the live plugin
- leave the fail-open hung-call path available so the hole stays falsifiable
"""

from __future__ import annotations

import json
import sys
import time
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
    McpProtocolError,
    _extract_text,
    echo_server_command,
    is_mcp_transport_failure,
)
from blackhole_agent.mcp_handshake_isolation import (
    DEAD_HANDSHAKE_TIMEOUT_SECONDS,
    LIVE_HANDSHAKE_TIMEOUT_SECONDS,
    McpPluginPlane,
    McpPluginSpec,
    connect_mcp_plane,
)

SCHEMA_VERSION = 1
MCP_CALL_ID = "capability.mcp-call-isolation"
REPO_ROOT = Path(__file__).resolve().parents[2]
DEAD_CALL_TIMEOUT_SECONDS = DEAD_HANDSHAKE_TIMEOUT_SECONDS

MCP_CALL_DONE_WHEN = (
    f"capability_exists:{MCP_CALL_ID};"
    f"capability_proved:{MCP_CALL_ID};"
    "no_skill_route"
)
MCP_CALL_GOAL = (
    "Repair MCP tool-call isolation: a live plugin whose tools/call never "
    "returns still blocks sibling plugins on the same plane; isolate the hung "
    "actuation so remaining servers keep serving."
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


def hang_tools_list_command() -> list[str]:
    """Plugin that answers initialize then never returns tools/list."""

    return [sys.executable, "-m", "blackhole_agent.mcp_call_isolation", "hang-list"]


def hang_tools_call_command() -> list[str]:
    """Plugin that advertises tools then never returns tools/call."""

    return [sys.executable, "-m", "blackhole_agent.mcp_call_isolation", "hang-call"]


def die_on_tools_list_command() -> list[str]:
    """Plugin that answers initialize then exits on tools/list."""

    return [sys.executable, "-m", "blackhole_agent.mcp_call_isolation", "die-on-list"]


def mcp_call_isolation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.mcp_call_isolation import "
        "builtin_mcp_call_isolation_proof; r=builtin_mcp_call_isolation_proof(); "
        "assert r['ok'] and r.get('action')=='mcp_call_isolation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_mcp_call_isolation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=MCP_CALL_ID,
        name="MCP tool-call isolation",
        description=(
            "A multi-plugin MCP plane isolates a plugin whose tools/list or "
            "tools/call never returns so sibling servers keep serving instead "
            "of leaving the hung actuation on the live plane."
        ),
        kind="python",
        entry="blackhole_agent.mcp_call_isolation:builtin_mcp_call_isolation_proof",
        proof_command=mcp_call_isolation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.mcp-handshake-isolation",
        ),
        behavior_paths=(
            "src/blackhole_agent/mcp_client.py",
            "src/blackhole_agent/mcp_handshake_isolation.py",
            "src/blackhole_agent/mcp_call_isolation.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A live plugin whose tools/call never returns is isolated on the "
            "MCP plane; sibling servers keep serving instead of the hung "
            "actuation staying live and blocking the rest of the plane."
        ),
        tags=("mcp", "call", "isolation", "resilience", "timeout"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260830T021106Z-cf45b869",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def _echo_spec(name: str) -> McpPluginSpec:
    return McpPluginSpec(name, echo_server_command(), timeout_seconds=LIVE_HANDSHAKE_TIMEOUT_SECONDS)


def _hang_list_spec(name: str) -> McpPluginSpec:
    return McpPluginSpec(name, hang_tools_list_command(), timeout_seconds=DEAD_CALL_TIMEOUT_SECONDS)


def _hang_call_spec(name: str) -> McpPluginSpec:
    return McpPluginSpec(name, hang_tools_call_command(), timeout_seconds=DEAD_CALL_TIMEOUT_SECONDS)


def _die_list_spec(name: str) -> McpPluginSpec:
    return McpPluginSpec(name, die_on_tools_list_command(), timeout_seconds=DEAD_CALL_TIMEOUT_SECONDS)


def _echo_text(plane: McpPluginPlane, server: str, text: str) -> str:
    return _extract_text(plane.call_tool(server, "echo", {"text": text}))


def _jsonrpc_error_stays_live(plane: McpPluginPlane, server: str) -> bool:
    raised = False
    try:
        plane.call_tool(server, "missing-tool", {"text": "nope"})
    except McpProtocolError as exc:
        raised = "json-rpc error" in str(exc).lower() and not is_mcp_transport_failure(exc)
    return raised and server in plane.live_names


def builtin_mcp_call_isolation_proof() -> dict[str, Any]:
    """Hermetic proof: a hung tools/call is isolated; siblings keep serving."""

    checks: dict[str, bool] = {}
    checks["denylists_self"] = MCP_CALL_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(MCP_CALL_GOAL) == (MCP_CALL_ID,)
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["transport_timeout_is_failure"] = is_mcp_transport_failure(
        McpProtocolError("timeout waiting for response id=2")
    )
    checks["jsonrpc_tool_error_is_not_transport"] = not is_mcp_transport_failure(
        McpProtocolError("JSON-RPC error -32602: unknown tool: missing for method tools/call")
    )

    from blackhole_agent.kernel_genesis_diversify import DIVERSITY_CATALOG

    checks["catalog_names_call"] = DIVERSITY_CATALOG[4]["id"] == MCP_CALL_ID

    naive_list = connect_mcp_plane(
        [_hang_list_spec("dead"), _echo_spec("live")],
        isolate_dead=True,
        isolate_hung_calls=False,
    )
    try:
        checks["naive_hang_list_accepts_dead"] = (
            naive_list.plane_failed is False
            and "dead" in naive_list.live_names
            and "live" in naive_list.live_names
            and naive_list.advertised_tools("dead") == ()
        )
    finally:
        naive_list.close()

    naive_call = connect_mcp_plane(
        [_hang_call_spec("dead"), _echo_spec("live")],
        isolate_dead=True,
        isolate_hung_calls=False,
    )
    try:
        hung = False
        try:
            naive_call.call_tool("dead", "echo", {"text": "nope"})
        except McpProtocolError as exc:
            hung = is_mcp_transport_failure(exc)
        live_after = _echo_text(naive_call, "live", "naive-live")
        checks["naive_hang_call_keeps_dead_live"] = (
            hung
            and "dead" in naive_call.live_names
            and "dead" not in naive_call.isolated_names
            and live_after == "naive-live"
        )
    finally:
        naive_call.close()

    isolated_list = connect_mcp_plane(
        [_hang_list_spec("dead"), _echo_spec("live")],
        isolate_dead=True,
        isolate_hung_calls=True,
    )
    try:
        served = _echo_text(isolated_list, "live", "after-hang-list")
        checks["isolated_hang_list_keeps_live"] = (
            isolated_list.plane_failed is False
            and isolated_list.serving() is True
            and isolated_list.live_names == ("live",)
            and isolated_list.isolated_names == ("dead",)
            and served == "after-hang-list"
            and "echo" in isolated_list.advertised_tools("live")
        )
    finally:
        isolated_list.close()

    isolated_call = connect_mcp_plane(
        [_hang_call_spec("dead"), _echo_spec("live")],
        isolate_dead=True,
        isolate_hung_calls=True,
    )
    try:
        before = isolated_call.live_names
        hung = False
        try:
            isolated_call.call_tool("dead", "echo", {"text": "nope"})
        except McpProtocolError as exc:
            hung = is_mcp_transport_failure(exc)
        served = _echo_text(isolated_call, "live", "after-hang-call")
        dead_raised = False
        try:
            isolated_call.call_tool("dead", "echo", {"text": "still-nope"})
        except McpProtocolError as exc:
            dead_raised = "is not serving" in str(exc)
        checks["isolated_hang_call_before_both_live"] = before == ("dead", "live")
        checks["isolated_hang_call_keeps_live"] = (
            hung
            and isolated_call.plane_failed is False
            and isolated_call.live_names == ("live",)
            and isolated_call.isolated_names == ("dead",)
            and served == "after-hang-call"
            and dead_raised
        )
        checks["isolated_call_on_dead_raises"] = dead_raised
        checks["jsonrpc_error_does_not_isolate"] = _jsonrpc_error_stays_live(isolated_call, "live")
    finally:
        isolated_call.close()

    isolated_die = connect_mcp_plane(
        [_die_list_spec("dead"), _echo_spec("live")],
        isolate_dead=True,
        isolate_hung_calls=True,
    )
    try:
        served = _echo_text(isolated_die, "live", "after-die-list")
        checks["isolated_die_on_list_keeps_live"] = (
            isolated_die.plane_failed is False
            and isolated_die.live_names == ("live",)
            and isolated_die.isolated_names == ("dead",)
            and served == "after-die-list"
        )
    finally:
        isolated_die.close()

    isolated_mixed = connect_mcp_plane(
        [_echo_spec("alpha"), _hang_call_spec("dead"), _echo_spec("beta")],
        isolate_dead=True,
        isolate_hung_calls=True,
    )
    try:
        hung = False
        try:
            isolated_mixed.call_tool("dead", "echo", {"text": "nope"})
        except McpProtocolError as exc:
            hung = is_mcp_transport_failure(exc)
        alpha = _echo_text(isolated_mixed, "alpha", "from-alpha")
        beta = _echo_text(isolated_mixed, "beta", "from-beta")
        checks["isolated_mixed_two_live"] = (
            hung
            and isolated_mixed.plane_failed is False
            and isolated_mixed.live_names == ("alpha", "beta")
            and isolated_mixed.isolated_names == ("dead",)
            and alpha == "from-alpha"
            and beta == "from-beta"
        )
    finally:
        isolated_mixed.close()

    isolated_all_dead = connect_mcp_plane(
        [_hang_call_spec("dead")],
        isolate_dead=True,
        isolate_hung_calls=True,
    )
    try:
        hung = False
        try:
            isolated_all_dead.call_tool("dead", "echo", {"text": "nope"})
        except McpProtocolError as exc:
            hung = is_mcp_transport_failure(exc)
        checks["isolated_all_hang_call_does_not_fail_plane"] = (
            hung
            and isolated_all_dead.plane_failed is False
            and isolated_all_dead.serving() is False
            and isolated_all_dead.isolated_names == ("dead",)
        )
    finally:
        isolated_all_dead.close()

    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_mcp_call_isolation_capability()
    return {
        "ok": ok,
        "action": "mcp_call_isolation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": MCP_CALL_GOAL,
        "done_when": MCP_CALL_DONE_WHEN,
    }


def _write(message: Mapping[str, Any]) -> None:
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def run_stub_server(mode: str) -> int:
    """Minimal stdio MCP plugin used to falsify hung post-handshake requests."""

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
        if method == "notifications/initialized" or "id" not in message:
            continue
        request_id = message["id"]
        if method == "initialize":
            _write(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": f"blackhole-{mode}", "version": "0"},
                    },
                }
            )
            continue
        if method == "tools/list":
            if mode == "hang-list":
                time.sleep(3600)
                return 0
            if mode == "die-on-list":
                return 0
            _write({"jsonrpc": "2.0", "id": request_id, "result": {"tools": [_ECHO_TOOL]}})
            continue
        if method == "tools/call":
            if mode == "hang-call":
                time.sleep(3600)
                return 0
            _write(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "content": [{"type": "text", "text": str((message.get("params") or {}).get("arguments", {}).get("text") or "")}],
                        "isError": False,
                    },
                }
            )
            continue
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
    mode = str(args[0] if args else "hang-call")
    if mode not in {"hang-list", "hang-call", "die-on-list"}:
        raise SystemExit(f"unknown MCP call-isolation stub mode: {mode}")
    return run_stub_server(mode)


if __name__ == "__main__":
    raise SystemExit(main())
