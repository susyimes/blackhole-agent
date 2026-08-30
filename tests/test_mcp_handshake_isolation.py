from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.mcp_client import McpProtocolError, echo_server_command
from blackhole_agent.mcp_handshake_isolation import (
    MCP_HANDSHAKE_DONE_WHEN,
    MCP_HANDSHAKE_GOAL,
    MCP_HANDSHAKE_ID,
    McpPluginSpec,
    builtin_mcp_handshake_isolation_proof,
    connect_mcp_plane,
    hang_initialize_command,
)


def test_goal_binds_handshake_isolation_plane() -> None:
    assert leftover_marker_ids(MCP_HANDSHAKE_GOAL) == (MCP_HANDSHAKE_ID,)
    assert MCP_HANDSHAKE_ID in LOCAL_DENYLIST


def test_isolated_plane_keeps_live_server_when_initialize_never_arrives() -> None:
    specs = [
        McpPluginSpec("dead", hang_initialize_command(), timeout_seconds=1.25),
        McpPluginSpec("live", echo_server_command(), timeout_seconds=20.0),
    ]
    naive = connect_mcp_plane(specs, isolate_dead=False)
    try:
        assert naive.plane_failed is True
        assert naive.serving() is False
        assert naive.live_names == ()
    finally:
        naive.close()

    isolated = connect_mcp_plane(specs, isolate_dead=True)
    try:
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


def test_builtin_proof_isolates_dead_handshake() -> None:
    report = builtin_mcp_handshake_isolation_proof()
    assert report["ok"] is True, report.get("checks")
    assert report["action"] == "mcp_handshake_isolation"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["checks"]["naive_hang_first_fails_plane"]
    assert report["checks"]["naive_live_first_tears_down"]
    assert report["checks"]["isolated_hang_keeps_live"]
    assert report["checks"]["isolated_mixed_two_live"]
    assert report["checks"]["isolated_closed_initialize_keeps_live"]
    assert report["mission_goal"] == MCP_HANDSHAKE_GOAL
    assert report["done_when"] == MCP_HANDSHAKE_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[MCP_HANDSHAKE_ID]
    assert capability.last_proof_exit_code == 0
    assert "handshake" in capability.tags
    assert "isolation" in capability.tags
