from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.mcp_call_isolation import MCP_CALL_GOAL, MCP_CALL_ID
from blackhole_agent.mcp_cancellation import (
    MCP_CANCELLATION_DONE_WHEN,
    MCP_CANCELLATION_GOAL,
    MCP_CANCELLATION_ID,
    SLOW_TOOL_NAME,
    UNLOCK_TOKEN,
    builtin_mcp_cancellation_proof,
    gated_command,
)
from blackhole_agent.mcp_client import (
    McpProtocolError,
    McpStdioSession,
    is_mcp_cancelled,
    is_mcp_transport_failure,
)
from blackhole_agent.mcp_elicitation import MCP_ELICITATION_GOAL, MCP_ELICITATION_ID
from blackhole_agent.mission_selection import (
    assess_mission_selection,
    capability_family,
    semantic_signature,
    semantic_similarity,
)


def test_goal_binds_cancellation_catalog() -> None:
    assert leftover_marker_ids(MCP_CANCELLATION_GOAL) == (MCP_CANCELLATION_ID,)
    assert MCP_CANCELLATION_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(MCP_ELICITATION_GOAL) == (MCP_ELICITATION_ID,)
    assert leftover_marker_ids(MCP_CALL_GOAL) == (MCP_CALL_ID,)
    assert MCP_CANCELLATION_ID not in leftover_marker_ids(MCP_ELICITATION_GOAL)
    assert MCP_CANCELLATION_ID not in leftover_marker_ids(MCP_CALL_GOAL)
    assert MCP_ELICITATION_ID not in leftover_marker_ids(MCP_CANCELLATION_GOAL)
    assert MCP_CALL_ID not in leftover_marker_ids(MCP_CANCELLATION_GOAL)
    assert (
        semantic_similarity(
            semantic_signature(MCP_CANCELLATION_GOAL),
            semantic_signature(MCP_ELICITATION_GOAL),
        )
        < 0.82
    )
    assert (
        semantic_similarity(
            semantic_signature(MCP_CANCELLATION_GOAL),
            semantic_signature(MCP_CALL_GOAL),
        )
        < 0.82
    )


def test_naive_session_times_out_when_cancel_is_skipped() -> None:
    session = McpStdioSession(gated_command(), timeout_seconds=1.25)
    try:
        session.start()
        try:
            session.call_tool(SLOW_TOOL_NAME, {})
            raise AssertionError("skip-cancel slow tools/call should time out")
        except McpProtocolError as exc:
            assert is_mcp_transport_failure(exc)
            assert not is_mcp_cancelled(exc)
        assert session.cancelled_request_ids == []
    finally:
        session.kill()


def test_cancelled_slow_call_releases_same_session() -> None:
    session = McpStdioSession(gated_command(), timeout_seconds=8)
    try:
        session.start()
        try:
            session.call_tool(SLOW_TOOL_NAME, {}, cancel_after=0.25)
            raise AssertionError("slow tools/call should abort with -32800")
        except McpProtocolError as exc:
            assert is_mcp_cancelled(exc)
            assert UNLOCK_TOKEN in str(exc)
        result = session.call_tool("echo", {"text": "after-cancel"})
        assert result.get("isError") is not True
        assert result["content"][0]["text"] == "after-cancel"
        assert session.cancelled_request_ids
    finally:
        session.kill()


def test_builtin_proof_cancels_in_flight_tools_call() -> None:
    report = builtin_mcp_cancellation_proof()
    assert report["ok"] is True, report.get("checks")
    assert report["action"] == "mcp_cancellation"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_slow_call_times_out"]
    assert report["checks"]["naive_did_not_send_cancel"]
    assert report["checks"]["cancel_returns_request_cancelled"]
    assert report["checks"]["same_session_echo_after_cancel"]
    assert report["checks"]["sibling_echo_still_serves"]
    assert report["checks"]["skip_cancel_is_isolated"]
    assert report["checks"]["exhausted_catalog_binds_cancellation"]
    assert report["mission_goal"] == MCP_CANCELLATION_GOAL
    assert report["done_when"] == MCP_CANCELLATION_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[MCP_CANCELLATION_ID]
    assert capability.last_proof_exit_code == 0
    assert "cancellation" in capability.tags
    assert "timeout" in capability.tags


def test_selection_gate_accepts_cancellation_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        MCP_CANCELLATION_GOAL,
        MCP_CANCELLATION_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(MCP_CANCELLATION_GOAL)
    assert "timeout" in family
    assert "elicitation" not in family
    assert "sampling" not in family
    assert not family.startswith("kernel-runtime")
