from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.mcp_client import McpProtocolError, echo_server_command, is_mcp_transport_failure
from blackhole_agent.mcp_call_isolation import (
    MCP_CALL_DONE_WHEN,
    MCP_CALL_GOAL,
    MCP_CALL_ID,
    builtin_mcp_call_isolation_proof,
    hang_tools_call_command,
)
from blackhole_agent.mcp_handshake_isolation import McpPluginSpec, connect_mcp_plane


def test_goal_binds_call_isolation_plane() -> None:
    assert leftover_marker_ids(MCP_CALL_GOAL) == (MCP_CALL_ID,)
    assert MCP_CALL_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(
        "Repair MCP client handshake isolation: a plugin whose initialize "
        "response never arrives still fails the whole MCP plane; isolate the "
        "dead handshake so live servers keep serving."
    ) != (MCP_CALL_ID,)


def test_isolated_plane_keeps_sibling_when_tools_call_never_returns() -> None:
    specs = [
        McpPluginSpec("dead", hang_tools_call_command(), timeout_seconds=1.25),
        McpPluginSpec("live", echo_server_command(), timeout_seconds=20.0),
    ]
    naive = connect_mcp_plane(specs, isolate_dead=True, isolate_hung_calls=False)
    try:
        try:
            naive.call_tool("dead", "echo", {"text": "nope"})
            raise AssertionError("hung tools/call should time out")
        except McpProtocolError as exc:
            assert is_mcp_transport_failure(exc)
        assert "dead" in naive.live_names
        result = naive.call_tool("live", "echo", {"text": "naive-sibling"})
        assert result["content"][0]["text"] == "naive-sibling"
    finally:
        naive.close()

    isolated = connect_mcp_plane(specs, isolate_dead=True, isolate_hung_calls=True)
    try:
        assert isolated.live_names == ("dead", "live")
        try:
            isolated.call_tool("dead", "echo", {"text": "nope"})
            raise AssertionError("hung tools/call should time out")
        except McpProtocolError as exc:
            assert is_mcp_transport_failure(exc)
        assert isolated.plane_failed is False
        assert isolated.live_names == ("live",)
        assert isolated.isolated_names == ("dead",)
        result = isolated.call_tool("live", "echo", {"text": "still-here"})
        assert result["content"][0]["text"] == "still-here"
        try:
            isolated.call_tool("dead", "echo", {"text": "nope"})
            raise AssertionError("dead plugin should not serve")
        except McpProtocolError:
            pass
    finally:
        isolated.close()


def test_builtin_proof_isolates_hung_tools_call() -> None:
    report = builtin_mcp_call_isolation_proof()
    assert report["ok"] is True, report.get("checks")
    assert report["action"] == "mcp_call_isolation"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_hang_call_keeps_dead_live"]
    assert report["checks"]["isolated_hang_call_keeps_live"]
    assert report["checks"]["isolated_hang_list_keeps_live"]
    assert report["checks"]["isolated_mixed_two_live"]
    assert report["checks"]["jsonrpc_error_does_not_isolate"]
    assert report["mission_goal"] == MCP_CALL_GOAL
    assert report["done_when"] == MCP_CALL_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[MCP_CALL_ID]
    assert capability.last_proof_exit_code == 0
    assert "call" in capability.tags
    assert "isolation" in capability.tags
