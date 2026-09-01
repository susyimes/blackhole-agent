from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.mcp_cancellation import MCP_CANCELLATION_GOAL, MCP_CANCELLATION_ID
from blackhole_agent.mcp_client import (
    McpStdioSession,
    _extract_text,
    echo_server_command,
    extract_progress_notifications,
    progress_is_monotonic,
)
from blackhole_agent.mcp_logging import MCP_LOGGING_GOAL, MCP_LOGGING_ID
from blackhole_agent.mcp_progress import (
    DEFAULT_TOKEN,
    MCP_PROGRESS_DONE_WHEN,
    MCP_PROGRESS_GOAL,
    MCP_PROGRESS_ID,
    MISSING_ERROR,
    UNLOCK_TOKEN,
    builtin_mcp_progress_proof,
    gated_command,
)
from blackhole_agent.mission_selection import (
    assess_mission_selection,
    capability_family,
    semantic_signature,
    semantic_similarity,
)
from blackhole_agent.webhook_actuation import WEBHOOK_ACTUATION_GOAL, WEBHOOK_ACTUATION_ID


def test_goal_binds_progress_catalog() -> None:
    assert leftover_marker_ids(MCP_PROGRESS_GOAL) == (MCP_PROGRESS_ID,)
    assert MCP_PROGRESS_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(WEBHOOK_ACTUATION_GOAL) == (WEBHOOK_ACTUATION_ID,)
    assert leftover_marker_ids(MCP_CANCELLATION_GOAL) == (MCP_CANCELLATION_ID,)
    assert leftover_marker_ids(MCP_LOGGING_GOAL) == (MCP_LOGGING_ID,)
    assert MCP_PROGRESS_ID not in leftover_marker_ids(WEBHOOK_ACTUATION_GOAL)
    assert MCP_PROGRESS_ID not in leftover_marker_ids(MCP_CANCELLATION_GOAL)
    assert WEBHOOK_ACTUATION_ID not in leftover_marker_ids(MCP_PROGRESS_GOAL)
    assert MCP_CANCELLATION_ID not in leftover_marker_ids(MCP_PROGRESS_GOAL)
    assert MCP_LOGGING_ID not in leftover_marker_ids(MCP_PROGRESS_GOAL)
    assert (
        semantic_similarity(
            semantic_signature(MCP_PROGRESS_GOAL),
            semantic_signature(WEBHOOK_ACTUATION_GOAL),
        )
        < 0.82
    )
    assert (
        semantic_similarity(
            semantic_signature(MCP_PROGRESS_GOAL),
            semantic_signature(MCP_CANCELLATION_GOAL),
        )
        < 0.82
    )


def test_naive_session_errors_when_progress_token_is_skipped() -> None:
    session = McpStdioSession(gated_command(), timeout_seconds=8)
    try:
        session.start()
        result = session.call_tool("echo", {"text": "nope"})
        assert result.get("isError") is True
        assert MISSING_ERROR in _extract_text(result)
        assert extract_progress_notifications(session.server_notifications) == ()
    finally:
        session.kill()


def test_progress_token_unblocks_gated_tool() -> None:
    session = McpStdioSession(gated_command(), timeout_seconds=8)
    try:
        session.start()
        result = session.call_tool("echo", {"text": "gate-me"}, progress_token=DEFAULT_TOKEN)
        assert result.get("isError") is not True
        assert _extract_text(result) == f"gate-me|{UNLOCK_TOKEN}"
        events = extract_progress_notifications(
            session.server_notifications, token=DEFAULT_TOKEN
        )
        assert progress_is_monotonic(events)
        assert events[0]["progressToken"] == DEFAULT_TOKEN
        assert events[-1]["progress"] == events[-1]["total"]
        assert DEFAULT_TOKEN in session.progress_tokens
    finally:
        session.kill()


def test_empty_progress_token_is_fail_closed() -> None:
    session = McpStdioSession(gated_command(), timeout_seconds=8)
    try:
        session.start()
        result = session.call_tool("echo", {"text": "blank"}, progress_token="")
        assert result.get("isError") is True
        assert MISSING_ERROR in _extract_text(result)
    finally:
        session.kill()


def test_echo_server_emits_progress_only_when_token_attached() -> None:
    with McpStdioSession(echo_server_command()) as session:
        plain = session.call_tool("echo", {"text": "plain"})
        assert _extract_text(plain) == "plain"
        assert extract_progress_notifications(session.server_notifications) == ()
        tokened = session.call_tool("echo", {"text": "tokened"}, progress_token=DEFAULT_TOKEN)
        assert _extract_text(tokened) == "tokened"
        events = extract_progress_notifications(
            session.server_notifications, token=DEFAULT_TOKEN
        )
        assert progress_is_monotonic(events)
        assert events[-1]["progress"] == events[-1]["total"]


def test_builtin_proof_speaks_progress_token() -> None:
    report = builtin_mcp_progress_proof()
    assert report["ok"] is True, report.get("checks")
    assert report["action"] == "mcp_progress"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_skip_token_is_error"]
    assert report["checks"]["progress_gated_call_succeeds"]
    assert report["checks"]["live_progress_is_monotonic"]
    assert report["checks"]["echo_with_token_emits_monotonic_progress"]
    assert report["checks"]["sibling_echo_still_serves"]
    assert report["checks"]["skip_token_stays_on_plane"]
    assert report["checks"]["exhausted_catalog_binds_progress"]
    assert report["mission_goal"] == MCP_PROGRESS_GOAL
    assert report["done_when"] == MCP_PROGRESS_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[MCP_PROGRESS_ID]
    assert capability.last_proof_exit_code == 0
    assert "progress" in capability.tags
    assert "mcp" in capability.tags


def test_selection_gate_accepts_progress_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        MCP_PROGRESS_GOAL,
        MCP_PROGRESS_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(MCP_PROGRESS_GOAL)
    assert "progress" in family
    assert "webhook" not in family
    assert "timeout" not in family
    assert "browser" not in family
    assert "worktree" not in family
    assert "git-publication" not in family
