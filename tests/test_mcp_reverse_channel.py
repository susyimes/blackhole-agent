from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.mcp_call_isolation import MCP_CALL_GOAL
from blackhole_agent.mcp_client import McpProtocolError, McpStdioSession, is_mcp_transport_failure
from blackhole_agent.mcp_handshake_isolation import MCP_HANDSHAKE_GOAL
from blackhole_agent.mcp_reverse_channel import (
    MCP_REVERSE_DONE_WHEN,
    MCP_REVERSE_GOAL,
    MCP_REVERSE_ID,
    builtin_mcp_reverse_channel_proof,
    probe_command,
)


def test_goal_binds_reverse_channel_plane() -> None:
    assert leftover_marker_ids(MCP_REVERSE_GOAL) == (MCP_REVERSE_ID,)
    assert MCP_REVERSE_ID in LOCAL_DENYLIST
    assert MCP_REVERSE_ID not in leftover_marker_ids(MCP_CALL_GOAL)
    assert MCP_REVERSE_ID not in leftover_marker_ids(MCP_HANDSHAKE_GOAL)


def test_naive_session_stalls_when_reverse_channel_is_ignored() -> None:
    session = McpStdioSession(
        probe_command(),
        timeout_seconds=1.25,
        answer_reverse_channel=False,
    )
    try:
        session.start()
        try:
            session.call_tool("echo", {"text": "nope"})
            raise AssertionError("unanswered ping should stall tools/call")
        except McpProtocolError as exc:
            assert is_mcp_transport_failure(exc)
        assert session.answered_requests == []
    finally:
        session.kill()


def test_builtin_proof_answers_ping_and_roots() -> None:
    report = builtin_mcp_reverse_channel_proof()
    assert report["ok"] is True, report.get("checks")
    assert report["action"] == "mcp_reverse_channel"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_probe_stalls"]
    assert report["checks"]["reverse_channel_call_succeeds"]
    assert report["checks"]["reverse_channel_answered_ping"]
    assert report["checks"]["reverse_channel_answered_roots"]
    assert report["checks"]["unknown_server_method_does_not_stall"]
    assert report["checks"]["sibling_echo_still_serves"]
    assert report["mission_goal"] == MCP_REVERSE_GOAL
    assert report["done_when"] == MCP_REVERSE_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[MCP_REVERSE_ID]
    assert capability.last_proof_exit_code == 0
    assert "reverse-channel" in capability.tags
    assert "ping" in capability.tags
