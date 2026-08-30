from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.mcp_call_isolation import MCP_CALL_GOAL
from blackhole_agent.mcp_client import McpProtocolError, echo_server_command, is_mcp_transport_failure
from blackhole_agent.mcp_handshake_isolation import (
    DEAD_HANDSHAKE_TIMEOUT_SECONDS,
    MCP_HANDSHAKE_GOAL,
    McpPluginSpec,
    connect_mcp_plane,
)
from blackhole_agent.mcp_http_event_stream import (
    GATED_TOOL_NAME,
    MCP_HTTP_EVENT_DONE_WHEN,
    MCP_HTTP_EVENT_GOAL,
    MCP_HTTP_EVENT_ID,
    builtin_mcp_http_event_stream_proof,
    start_http_elicitation_server,
)
from blackhole_agent.mcp_http_transport import MCP_HTTP_GOAL, MCP_HTTP_ID, McpHttpSession
from blackhole_agent.mcp_reverse_channel import MCP_REVERSE_GOAL, MCP_REVERSE_ID


def test_goal_binds_http_event_stream_plane() -> None:
    assert leftover_marker_ids(MCP_HTTP_EVENT_GOAL) == (MCP_HTTP_EVENT_ID,)
    assert MCP_HTTP_EVENT_ID in LOCAL_DENYLIST
    assert MCP_HTTP_EVENT_ID not in leftover_marker_ids(MCP_HTTP_GOAL)
    assert MCP_HTTP_EVENT_ID not in leftover_marker_ids(MCP_REVERSE_GOAL)
    assert MCP_HTTP_EVENT_ID not in leftover_marker_ids(MCP_HANDSHAKE_GOAL)
    assert MCP_HTTP_EVENT_ID not in leftover_marker_ids(MCP_CALL_GOAL)
    assert leftover_marker_ids(MCP_HTTP_GOAL) == (MCP_HTTP_ID,)
    assert leftover_marker_ids(MCP_REVERSE_GOAL) == (MCP_REVERSE_ID,)


def test_naive_http_session_stalls_without_get_stream() -> None:
    with start_http_elicitation_server() as hosted:
        session = McpHttpSession(
            hosted.url,
            timeout_seconds=DEAD_HANDSHAKE_TIMEOUT_SECONDS,
            listen_event_stream=False,
        )
        try:
            session.start()
            try:
                session.call_tool(GATED_TOOL_NAME, {"text": "nope"})
                raise AssertionError("gated call should stall when GET SSE is skipped")
            except McpProtocolError as exc:
                assert is_mcp_transport_failure(exc)
            assert session.event_stream_open is False
            assert session.answered_requests == []
        finally:
            session.kill()


def test_elicitation_plugin_serves_beside_stdio_sibling() -> None:
    with start_http_elicitation_server() as hosted:
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
            hosted_echo = plane.call_tool("hosted", GATED_TOOL_NAME, {"text": "hosted-ok"})
            live_echo = plane.call_tool("live", "echo", {"text": "live-ok"})
            assert hosted_echo["content"][0]["text"] == "hosted-ok|approved"
            assert live_echo["content"][0]["text"] == "live-ok"
        finally:
            plane.close()


def test_builtin_proof_answers_http_elicitation() -> None:
    report = builtin_mcp_http_event_stream_proof()
    assert report["ok"] is True, report.get("checks")
    assert report["action"] == "mcp_http_event_stream"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_without_get_stalls"]
    assert report["checks"]["elicitation_call_succeeds"]
    assert report["checks"]["elicitation_was_answered"]
    assert report["checks"]["progress_notification_on_get_stream"]
    assert report["checks"]["mixed_http_event_stream_and_stdio_serve"]
    assert report["checks"]["exhausted_catalog_binds_event_stream"]
    assert report["mission_goal"] == MCP_HTTP_EVENT_GOAL
    assert report["done_when"] == MCP_HTTP_EVENT_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[MCP_HTTP_EVENT_ID]
    assert capability.last_proof_exit_code == 0
    assert "elicitation" in capability.tags
    assert "event-stream" in capability.tags
