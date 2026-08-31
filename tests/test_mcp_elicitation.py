from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.mcp_client import McpProtocolError, McpStdioSession, is_mcp_transport_failure
from blackhole_agent.mcp_elicitation import (
    DECLINE_ERROR,
    MCP_ELICITATION_DONE_WHEN,
    MCP_ELICITATION_GOAL,
    MCP_ELICITATION_ID,
    UNLOCK_TOKEN,
    builtin_mcp_elicitation_proof,
    gated_command,
)
from blackhole_agent.mcp_http_event_stream import MCP_HTTP_EVENT_GOAL, MCP_HTTP_EVENT_ID
from blackhole_agent.mcp_logging import MCP_LOGGING_GOAL, MCP_LOGGING_ID
from blackhole_agent.mcp_sampling import MCP_SAMPLING_GOAL, MCP_SAMPLING_ID
from blackhole_agent.mission_selection import (
    assess_mission_selection,
    capability_family,
    semantic_signature,
    semantic_similarity,
)


def test_goal_binds_elicitation_catalog() -> None:
    assert leftover_marker_ids(MCP_ELICITATION_GOAL) == (MCP_ELICITATION_ID,)
    assert MCP_ELICITATION_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(MCP_LOGGING_GOAL) == (MCP_LOGGING_ID,)
    assert leftover_marker_ids(MCP_SAMPLING_GOAL) == (MCP_SAMPLING_ID,)
    assert leftover_marker_ids(MCP_HTTP_EVENT_GOAL) == (MCP_HTTP_EVENT_ID,)
    assert MCP_ELICITATION_ID not in leftover_marker_ids(MCP_LOGGING_GOAL)
    assert MCP_ELICITATION_ID not in leftover_marker_ids(MCP_SAMPLING_GOAL)
    assert MCP_ELICITATION_ID not in leftover_marker_ids(MCP_HTTP_EVENT_GOAL)
    assert MCP_LOGGING_ID not in leftover_marker_ids(MCP_ELICITATION_GOAL)
    assert MCP_HTTP_EVENT_ID not in leftover_marker_ids(MCP_ELICITATION_GOAL)
    assert (
        semantic_similarity(
            semantic_signature(MCP_ELICITATION_GOAL),
            semantic_signature(MCP_LOGGING_GOAL),
        )
        < 0.82
    )
    assert (
        semantic_similarity(
            semantic_signature(MCP_ELICITATION_GOAL),
            semantic_signature(MCP_SAMPLING_GOAL),
        )
        < 0.82
    )
    assert (
        semantic_similarity(
            semantic_signature(MCP_ELICITATION_GOAL),
            semantic_signature(MCP_HTTP_EVENT_GOAL),
        )
        < 0.82
    )


def test_naive_session_stalls_when_elicitation_is_unanswered() -> None:
    session = McpStdioSession(
        gated_command(),
        timeout_seconds=1.25,
        answer_reverse_channel=True,
        answer_elicitation=False,
    )
    try:
        session.start()
        try:
            session.call_tool("echo", {"text": "nope"})
            raise AssertionError("unanswered elicitation should stall tools/call")
        except McpProtocolError as exc:
            assert is_mcp_transport_failure(exc)
        assert any(item.get("method") == "elicitation/create" for item in session.answered_requests)
    finally:
        session.kill()


def test_accepting_elicitation_unblocks_gated_tool() -> None:
    session = McpStdioSession(
        gated_command(),
        timeout_seconds=8,
        answer_reverse_channel=True,
        answer_elicitation=True,
    )
    try:
        session.start()
        assert isinstance(session.client_capabilities.get("elicitation"), dict)
        result = session.call_tool("echo", {"text": "gate-me"})
        assert result.get("isError") is not True
        assert result["content"][0]["text"] == f"gate-me|{UNLOCK_TOKEN}"
        assert any(
            item.get("method") == "elicitation/create" and not item.get("error")
            for item in session.answered_requests
        )
    finally:
        session.kill()


def test_declined_elicitation_stays_fail_closed() -> None:
    session = McpStdioSession(
        gated_command(),
        timeout_seconds=8,
        answer_reverse_channel=True,
        answer_elicitation=True,
        elicitation_action="decline",
    )
    try:
        session.start()
        result = session.call_tool("echo", {"text": "nope"})
        assert result.get("isError") is True
        assert DECLINE_ERROR in result["content"][0]["text"]
    finally:
        session.kill()


def test_builtin_proof_answers_stdio_elicitation() -> None:
    report = builtin_mcp_elicitation_proof()
    assert report["ok"] is True, report.get("checks")
    assert report["action"] == "mcp_elicitation"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_elicitation_stalls"]
    assert report["checks"]["elicitation_call_succeeds"]
    assert report["checks"]["elicitation_answered_create"]
    assert report["checks"]["decline_stays_fail_closed"]
    assert report["checks"]["sibling_echo_still_serves"]
    assert report["checks"]["unanswered_elicitation_is_isolated"]
    assert report["checks"]["exhausted_catalog_binds_elicitation"]
    assert report["mission_goal"] == MCP_ELICITATION_GOAL
    assert report["done_when"] == MCP_ELICITATION_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[MCP_ELICITATION_ID]
    assert capability.last_proof_exit_code == 0
    assert "elicitation" in capability.tags
    assert "mcp" in capability.tags


def test_selection_gate_accepts_elicitation_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        MCP_ELICITATION_GOAL,
        MCP_ELICITATION_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(MCP_ELICITATION_GOAL)
    assert "elicitation" in family or "stdio" in family or "form" in family
    assert "logging" not in family
    assert "sampling" not in family
    assert not family.startswith("kernel-runtime")
