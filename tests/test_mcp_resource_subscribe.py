from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.mcp_cancellation import MCP_CANCELLATION_GOAL, MCP_CANCELLATION_ID
from blackhole_agent.mcp_client import (
    McpProtocolError,
    McpStdioSession,
    _extract_text,
    extract_resource_text,
    extract_resource_updated,
)
from blackhole_agent.mcp_resource_subscribe import (
    LOCKED_TOKEN,
    MCP_SUBSCRIBE_DONE_WHEN,
    MCP_SUBSCRIBE_GOAL,
    MCP_SUBSCRIBE_ID,
    UNLOCK_TOKEN,
    UNSUBSCRIBED_ERROR,
    WATCH_URI,
    builtin_mcp_resource_subscribe_proof,
    gated_command,
)
from blackhole_agent.mcp_resources import MCP_RESOURCES_GOAL, MCP_RESOURCES_ID
from blackhole_agent.mission_selection import (
    assess_mission_selection,
    capability_family,
    semantic_signature,
    semantic_similarity,
)


def test_goal_binds_subscribe_watch_plane() -> None:
    assert leftover_marker_ids(MCP_SUBSCRIBE_GOAL) == (MCP_SUBSCRIBE_ID,)
    assert MCP_SUBSCRIBE_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(MCP_RESOURCES_GOAL) == (MCP_RESOURCES_ID,)
    assert leftover_marker_ids(MCP_CANCELLATION_GOAL) == (MCP_CANCELLATION_ID,)
    assert MCP_SUBSCRIBE_ID not in leftover_marker_ids(MCP_RESOURCES_GOAL)
    assert MCP_SUBSCRIBE_ID not in leftover_marker_ids(MCP_CANCELLATION_GOAL)
    assert MCP_RESOURCES_ID not in leftover_marker_ids(MCP_SUBSCRIBE_GOAL)
    assert MCP_CANCELLATION_ID not in leftover_marker_ids(MCP_SUBSCRIBE_GOAL)
    assert (
        semantic_similarity(
            semantic_signature(MCP_SUBSCRIBE_GOAL),
            semantic_signature(MCP_RESOURCES_GOAL),
        )
        < 0.82
    )
    assert (
        semantic_similarity(
            semantic_signature(MCP_SUBSCRIBE_GOAL),
            semantic_signature(MCP_CANCELLATION_GOAL),
        )
        < 0.82
    )


def test_naive_session_errors_when_subscription_is_skipped() -> None:
    session = McpStdioSession(gated_command(), timeout_seconds=8)
    try:
        session.start()
        assert extract_resource_text(session.read_resource(WATCH_URI)) == LOCKED_TOKEN
        result = session.call_tool("echo", {"text": "nope"})
        assert result.get("isError") is True
        assert UNSUBSCRIBED_ERROR in _extract_text(result)
        assert session.subscribed_uris == []
    finally:
        session.kill()


def test_subscribe_unlocks_gated_tool_and_emits_updated() -> None:
    session = McpStdioSession(gated_command(), timeout_seconds=8)
    try:
        session.start()
        session.subscribe_resource(WATCH_URI)
        assert WATCH_URI in session.subscribed_uris
        assert WATCH_URI in extract_resource_updated(session.server_notifications)
        assert extract_resource_text(session.read_resource(WATCH_URI)) == UNLOCK_TOKEN
        result = session.call_tool("echo", {"text": "gate-me"})
        assert result.get("isError") is not True
        assert _extract_text(result) == f"gate-me|{UNLOCK_TOKEN}"
    finally:
        session.kill()


def test_unsubscribe_re_locks_gated_tool() -> None:
    session = McpStdioSession(gated_command(), timeout_seconds=8)
    try:
        session.start()
        session.subscribe_resource(WATCH_URI)
        assert _extract_text(session.call_tool("echo", {"text": "open"})) == f"open|{UNLOCK_TOKEN}"
        session.unsubscribe_resource(WATCH_URI)
        assert WATCH_URI not in session.subscribed_uris
        relocked = session.call_tool("echo", {"text": "closed"})
        assert relocked.get("isError") is True
        assert UNSUBSCRIBED_ERROR in _extract_text(relocked)
    finally:
        session.kill()


def test_unknown_subscribe_uri_is_fail_closed() -> None:
    session = McpStdioSession(gated_command(), timeout_seconds=8)
    try:
        session.start()
        try:
            session.subscribe_resource("resource://blackhole/watch/missing")
            raise AssertionError("unknown subscribe URI should raise")
        except McpProtocolError as exc:
            assert "unknown resource" in str(exc).lower()
        unread = session.call_tool("echo", {"text": "still-locked"})
        assert unread.get("isError") is True
    finally:
        session.kill()


def test_builtin_proof_speaks_resource_subscription_watch_plane() -> None:
    report = builtin_mcp_resource_subscribe_proof()
    assert report["ok"] is True, report.get("checks")
    assert report["action"] == "mcp_resource_subscribe"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_skip_subscribe_is_error"]
    assert report["checks"]["naive_read_stays_locked"]
    assert report["checks"]["updated_notification_was_received"]
    assert report["checks"]["update_gated_call_succeeds"]
    assert report["checks"]["unsubscribe_re_locks_tool"]
    assert report["checks"]["sibling_echo_still_serves"]
    assert report["checks"]["skip_subscribe_stays_on_plane"]
    assert report["checks"]["exhausted_catalog_binds_subscribe"]
    assert report["mission_goal"] == MCP_SUBSCRIBE_GOAL
    assert report["done_when"] == MCP_SUBSCRIBE_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[MCP_SUBSCRIBE_ID]
    assert capability.last_proof_exit_code == 0
    assert "subscribe" in capability.tags
    assert "watch" in capability.tags
    assert "mcp" in capability.tags


def test_selection_gate_accepts_subscribe_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        MCP_SUBSCRIBE_GOAL,
        MCP_SUBSCRIBE_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(MCP_SUBSCRIBE_GOAL)
    assert "subscription" in family or "watch" in family
    assert "timeout" not in family
    assert "elicitation" not in family
    assert not family.startswith("kernel-runtime")
