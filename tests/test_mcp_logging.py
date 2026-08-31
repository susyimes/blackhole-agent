from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.mcp_client import (
    McpProtocolError,
    McpStdioSession,
    _extract_text,
    extract_log_messages,
)
from blackhole_agent.mcp_completions import MCP_COMPLETIONS_GOAL, MCP_COMPLETIONS_ID
from blackhole_agent.mcp_logging import (
    MCP_LOGGING_DONE_WHEN,
    MCP_LOGGING_GOAL,
    MCP_LOGGING_ID,
    UNLOCK_LEVEL,
    UNLOCK_TOKEN,
    UNSET_ERROR,
    builtin_mcp_logging_proof,
    gated_command,
)
from blackhole_agent.mission_selection import (
    assess_mission_selection,
    capability_family,
    semantic_signature,
    semantic_similarity,
)


def test_goal_binds_logging_catalog() -> None:
    assert leftover_marker_ids(MCP_LOGGING_GOAL) == (MCP_LOGGING_ID,)
    assert MCP_LOGGING_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(MCP_COMPLETIONS_GOAL) == (MCP_COMPLETIONS_ID,)
    assert MCP_LOGGING_ID not in leftover_marker_ids(MCP_COMPLETIONS_GOAL)
    assert MCP_COMPLETIONS_ID not in leftover_marker_ids(MCP_LOGGING_GOAL)
    assert (
        semantic_similarity(
            semantic_signature(MCP_LOGGING_GOAL),
            semantic_signature(MCP_COMPLETIONS_GOAL),
        )
        < 0.82
    )


def test_naive_session_errors_when_log_level_is_skipped() -> None:
    session = McpStdioSession(gated_command(), timeout_seconds=8)
    try:
        session.start()
        result = session.call_tool("echo", {"text": "nope"})
        assert result.get("isError") is True
        assert UNSET_ERROR in _extract_text(result)
        assert extract_log_messages(session.server_notifications) == ()
    finally:
        session.kill()


def test_set_log_level_unblocks_gated_tool() -> None:
    session = McpStdioSession(gated_command(), timeout_seconds=8)
    try:
        session.start()
        session.set_log_level(UNLOCK_LEVEL)
        logs = extract_log_messages(session.server_notifications)
        assert any(item.get("data") == UNLOCK_TOKEN for item in logs)
        result = session.call_tool("echo", {"text": "gate-me"})
        assert result.get("isError") is not True
        assert _extract_text(result) == f"gate-me|{UNLOCK_TOKEN}"
    finally:
        session.kill()


def test_unknown_log_level_is_fail_closed() -> None:
    session = McpStdioSession(gated_command(), timeout_seconds=8)
    try:
        session.start()
        try:
            session.set_log_level("not-a-level")
            raise AssertionError("unknown log level should raise")
        except McpProtocolError as exc:
            assert "unknown log level" in str(exc).lower()
        unread = session.call_tool("echo", {"text": "still-locked"})
        assert unread.get("isError") is True
    finally:
        session.kill()


def test_builtin_proof_speaks_log_stream() -> None:
    report = builtin_mcp_logging_proof()
    assert report["ok"] is True, report.get("checks")
    assert report["action"] == "mcp_logging"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["echo_emits_log_after_set_level"]
    assert report["checks"]["naive_skip_set_level_is_error"]
    assert report["checks"]["log_gated_call_succeeds"]
    assert report["checks"]["sibling_echo_still_serves"]
    assert report["checks"]["skip_set_level_stays_on_plane"]
    assert report["checks"]["exhausted_catalog_binds_logging"]
    assert report["mission_goal"] == MCP_LOGGING_GOAL
    assert report["done_when"] == MCP_LOGGING_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[MCP_LOGGING_ID]
    assert capability.last_proof_exit_code == 0
    assert "logging" in capability.tags
    assert "mcp" in capability.tags


def test_selection_gate_accepts_logging_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        MCP_LOGGING_GOAL,
        MCP_LOGGING_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(MCP_LOGGING_GOAL)
    assert "stream" in family or "log" in family or "consumption" in family
    assert "completion" not in family
    assert "prompt" not in family
    assert "sampling" not in family
    assert not family.startswith("kernel-runtime")
