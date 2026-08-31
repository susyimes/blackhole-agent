from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.godot_actuation import GODOT_ACTUATION_GOAL, GODOT_ACTUATION_ID
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.mcp_client import McpProtocolError, echo_server_command
from blackhole_agent.mcp_handshake_isolation import (
    MCP_HANDSHAKE_GOAL,
    MCP_HANDSHAKE_ID,
    McpPluginSpec,
    closed_initialize_command,
    connect_mcp_plane,
)
from blackhole_agent.mcp_plugin_reconnect import (
    MCP_RECONNECT_DONE_WHEN,
    MCP_RECONNECT_GOAL,
    MCP_RECONNECT_ID,
    builtin_mcp_plugin_reconnect_proof,
    flaky_initialize_command,
)


def test_goal_binds_plugin_reconnect_plane() -> None:
    assert leftover_marker_ids(MCP_RECONNECT_GOAL) == (MCP_RECONNECT_ID,)
    assert MCP_RECONNECT_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(MCP_HANDSHAKE_GOAL) == (MCP_HANDSHAKE_ID,)
    assert leftover_marker_ids(GODOT_ACTUATION_GOAL) == (GODOT_ACTUATION_ID,)
    assert MCP_RECONNECT_ID not in leftover_marker_ids(MCP_HANDSHAKE_GOAL)
    assert MCP_RECONNECT_ID not in leftover_marker_ids(GODOT_ACTUATION_GOAL)


def test_closed_initialize_reconnects_flaky_plugin_without_restarting_sibling(
    tmp_path: Path,
) -> None:
    state = tmp_path / "starts"
    specs = [
        McpPluginSpec("flaky", flaky_initialize_command(state, fail_count=1), timeout_seconds=1.25),
        McpPluginSpec("live", echo_server_command(), timeout_seconds=20.0),
    ]
    plane = connect_mcp_plane(specs, isolate_dead=True)
    try:
        assert plane.live_names == ("live",)
        assert plane.isolated_names == ("flaky",)
        token = plane.session_token("live")
        report = plane.reconnect_plugin("flaky", max_attempts=3, backoff_seconds=0.0)
        assert report["ok"] is True
        assert report["already_live"] is False
        assert plane.live_names == ("flaky", "live")
        assert plane.isolated_names == ()
        result = plane.call_tool("flaky", "echo", {"text": "restored"})
        assert result["content"][0]["text"] == "restored"
        sibling = plane.call_tool("live", "echo", {"text": "sibling"})
        assert sibling["content"][0]["text"] == "sibling"
        assert plane.session_token("live") == token
    finally:
        plane.close()


def test_permanently_dead_plugin_stays_isolated_after_bounded_reconnect() -> None:
    specs = [
        McpPluginSpec("dead", closed_initialize_command(), timeout_seconds=1.25),
        McpPluginSpec("live", echo_server_command(), timeout_seconds=20.0),
    ]
    plane = connect_mcp_plane(specs, isolate_dead=True)
    try:
        token = plane.session_token("live")
        report = plane.reconnect_plugin("dead", max_attempts=2, backoff_seconds=0.0)
        assert report["ok"] is False
        assert report["attempts"] == 2
        assert plane.isolated_names == ("dead",)
        assert plane.live_names == ("live",)
        try:
            plane.call_tool("dead", "echo", {"text": "nope"})
            raise AssertionError("dead plugin should not serve")
        except McpProtocolError:
            pass
        sibling = plane.call_tool("live", "echo", {"text": "keep"})
        assert sibling["content"][0]["text"] == "keep"
        assert plane.session_token("live") == token
    finally:
        plane.close()


def test_builtin_proof_reconnects_closed_initialize() -> None:
    report = builtin_mcp_plugin_reconnect_proof()
    assert report["ok"] is True, report.get("checks")
    assert report["action"] == "mcp_plugin_reconnect"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["isolated_closed_stays_dead_without_reconnect"]
    assert report["checks"]["flaky_reconnect_restores_plugin"]
    assert report["checks"]["sibling_session_token_unchanged"]
    assert report["checks"]["always_dead_reconnect_stays_isolated"]
    assert report["checks"]["exhausted_catalog_binds_reconnect"]
    assert report["mission_goal"] == MCP_RECONNECT_GOAL
    assert report["done_when"] == MCP_RECONNECT_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[MCP_RECONNECT_ID]
    assert capability.last_proof_exit_code == 0
    assert "reconnect" in capability.tags
    assert "recovery" in capability.tags
