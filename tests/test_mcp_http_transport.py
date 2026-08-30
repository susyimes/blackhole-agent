from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.mcp_call_isolation import MCP_CALL_GOAL
from blackhole_agent.mcp_client import (
    McpProtocolError,
    McpStdioSession,
    echo_server_command,
    is_mcp_transport_failure,
)
from blackhole_agent.mcp_handshake_isolation import (
    DEAD_HANDSHAKE_TIMEOUT_SECONDS,
    MCP_HANDSHAKE_GOAL,
    McpPluginSpec,
    connect_mcp_plane,
)
from blackhole_agent.mcp_http_transport import (
    MCP_HTTP_DONE_WHEN,
    MCP_HTTP_GOAL,
    MCP_HTTP_ID,
    builtin_mcp_http_transport_proof,
    http_stdio_silent_command,
    start_http_echo_server,
)
from blackhole_agent.mcp_reverse_channel import MCP_REVERSE_GOAL


def test_goal_binds_http_transport_plane() -> None:
    assert leftover_marker_ids(MCP_HTTP_GOAL) == (MCP_HTTP_ID,)
    assert MCP_HTTP_ID in LOCAL_DENYLIST
    assert MCP_HTTP_ID not in leftover_marker_ids(MCP_REVERSE_GOAL)
    assert MCP_HTTP_ID not in leftover_marker_ids(MCP_HANDSHAKE_GOAL)
    assert MCP_HTTP_ID not in leftover_marker_ids(MCP_CALL_GOAL)


def test_stdio_session_cannot_handshake_http_only_plugin() -> None:
    session = McpStdioSession(
        http_stdio_silent_command(),
        timeout_seconds=DEAD_HANDSHAKE_TIMEOUT_SECONDS,
    )
    try:
        try:
            session.start()
            raise AssertionError("stdio client should not complete HTTP-only initialize")
        except McpProtocolError as exc:
            assert is_mcp_transport_failure(exc)
    finally:
        session.kill()


def test_http_plugin_serves_beside_stdio_sibling() -> None:
    with start_http_echo_server() as hosted:
        plane = connect_mcp_plane(
            [
                McpPluginSpec("hosted", url=hosted.url, timeout_seconds=20.0),
                McpPluginSpec("live", echo_server_command(), timeout_seconds=20.0),
            ],
            isolate_dead=True,
            isolate_hung_calls=True,
        )
        try:
            assert plane.plane_failed is False
            assert plane.live_names == ("hosted", "live")
            hosted_echo = plane.call_tool("hosted", "echo", {"text": "hosted-ok"})
            live_echo = plane.call_tool("live", "echo", {"text": "live-ok"})
            assert hosted_echo["content"][0]["text"] == "hosted-ok"
            assert live_echo["content"][0]["text"] == "live-ok"
        finally:
            plane.close()


def test_builtin_proof_serves_streamable_http() -> None:
    report = builtin_mcp_http_transport_proof()
    assert report["ok"] is True, report.get("checks")
    assert report["action"] == "mcp_http_transport"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["stdio_cannot_handshake_http_plugin"]
    assert report["checks"]["http_json_initialize_serves"]
    assert report["checks"]["http_sse_initialize_serves"]
    assert report["checks"]["mixed_http_and_stdio_serve"]
    assert report["checks"]["exhausted_catalog_binds_http"]
    assert report["mission_goal"] == MCP_HTTP_GOAL
    assert report["done_when"] == MCP_HTTP_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[MCP_HTTP_ID]
    assert capability.last_proof_exit_code == 0
    assert "http" in capability.tags
    assert "transport" in capability.tags
