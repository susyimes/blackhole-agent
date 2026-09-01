from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.mcp_client import (
    McpStdioSession,
    _extract_text,
    echo_server_command,
    extract_next_cursor,
    extract_tools_list_changed,
)
from blackhole_agent.mcp_cursor_pagination import (
    BOOTSTRAP_TOOL_NAME,
    GATED_TOOL_NAME,
    MCP_CURSOR_DONE_WHEN,
    MCP_CURSOR_GOAL,
    MCP_CURSOR_ID,
    PAGE_TWO_CURSOR,
    TRUNCATED_ERROR,
    UNLOCK_TOKEN,
    builtin_mcp_cursor_pagination_proof,
    gated_command,
)
from blackhole_agent.mcp_tools_list_changed import (
    MCP_TOOLS_CHANGED_GOAL,
    MCP_TOOLS_CHANGED_ID,
)
from blackhole_agent.mission_selection import (
    assess_mission_selection,
    capability_family,
    semantic_signature,
    semantic_similarity,
)
from blackhole_agent.watch_actuation import WATCH_ACTUATION_GOAL, WATCH_ACTUATION_ID


def test_goal_binds_cursor_pagination_catalog() -> None:
    assert leftover_marker_ids(MCP_CURSOR_GOAL) == (MCP_CURSOR_ID,)
    assert MCP_CURSOR_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(WATCH_ACTUATION_GOAL) == (WATCH_ACTUATION_ID,)
    assert leftover_marker_ids(MCP_TOOLS_CHANGED_GOAL) == (MCP_TOOLS_CHANGED_ID,)
    assert MCP_CURSOR_ID not in leftover_marker_ids(WATCH_ACTUATION_GOAL)
    assert MCP_CURSOR_ID not in leftover_marker_ids(MCP_TOOLS_CHANGED_GOAL)
    assert WATCH_ACTUATION_ID not in leftover_marker_ids(MCP_CURSOR_GOAL)
    assert MCP_TOOLS_CHANGED_ID not in leftover_marker_ids(MCP_CURSOR_GOAL)
    assert (
        semantic_similarity(
            semantic_signature(MCP_CURSOR_GOAL),
            semantic_signature(WATCH_ACTUATION_GOAL),
        )
        < 0.82
    )
    assert (
        semantic_similarity(
            semantic_signature(MCP_CURSOR_GOAL),
            semantic_signature(MCP_TOOLS_CHANGED_GOAL),
        )
        < 0.82
    )


def test_naive_session_errors_when_cursor_is_not_followed() -> None:
    session = McpStdioSession(gated_command(), timeout_seconds=8)
    try:
        session.start()
        listed = session.list_tools()
        names = [str(item.get("name") or "") for item in listed.get("tools") or []]
        assert BOOTSTRAP_TOOL_NAME in names
        assert GATED_TOOL_NAME not in names
        assert extract_next_cursor(listed) == PAGE_TWO_CURSOR
        refreshed = session.refresh_tools()
        refresh_names = [str(item.get("name") or "") for item in refreshed.get("tools") or []]
        assert GATED_TOOL_NAME not in refresh_names
        result = session.call_tool(GATED_TOOL_NAME, {"text": "nope"})
        assert result.get("isError") is True
        assert TRUNCATED_ERROR in _extract_text(result)
        assert extract_tools_list_changed(session.server_notifications) == ()
        assert session.tool_names == [BOOTSTRAP_TOOL_NAME]
    finally:
        session.kill()


def test_paginate_tools_unblocks_page_two_gated_tool() -> None:
    session = McpStdioSession(gated_command(), timeout_seconds=8)
    try:
        session.start()
        first = session.list_tools()
        assert extract_next_cursor(first) == PAGE_TWO_CURSOR
        paged = session.paginate_tools()
        names = [str(item.get("name") or "") for item in paged.get("tools") or []]
        assert BOOTSTRAP_TOOL_NAME in names
        assert GATED_TOOL_NAME in names
        result = session.call_tool(GATED_TOOL_NAME, {"text": "gate-me"})
        assert result.get("isError") is not True
        assert _extract_text(result) == f"gate-me|{UNLOCK_TOKEN}"
        assert GATED_TOOL_NAME in session.tool_names
        assert session.tool_list_count >= 3
        assert extract_next_cursor(paged) == ""
    finally:
        session.kill()


def test_echo_server_paginate_is_single_page() -> None:
    with McpStdioSession(echo_server_command()) as session:
        listed = session.list_tools()
        assert extract_next_cursor(listed) == ""
        paged = session.paginate_tools()
        names = [str(item.get("name") or "") for item in paged.get("tools") or []]
        assert "echo" in names
        assert _extract_text(session.call_tool("echo", {"text": "plain"})) == "plain"
        assert extract_tools_list_changed(session.server_notifications) == ()


def test_builtin_proof_speaks_cursor_pagination() -> None:
    report = builtin_mcp_cursor_pagination_proof()
    assert report["ok"] is True, report.get("failed") or report.get("checks")
    assert report["action"] == "mcp_cursor_pagination"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_skip_cursor_is_error"]
    assert report["checks"]["refresh_tools_cannot_substitute"]
    assert report["checks"]["published_tool_call_succeeds"]
    assert report["checks"]["live_paginate_publishes_echo"]
    assert report["checks"]["echo_paginate_is_single_page"]
    assert report["checks"]["sibling_echo_still_serves"]
    assert report["checks"]["skip_cursor_stays_on_plane"]
    assert report["checks"]["exhausted_catalog_binds_cursor"]
    assert report["mission_goal"] == MCP_CURSOR_GOAL
    assert report["done_when"] == MCP_CURSOR_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[MCP_CURSOR_ID]
    assert capability.last_proof_exit_code == 0
    assert "nextCursor" in capability.tags
    assert "mcp" in capability.tags
    assert "pagination" in capability.tags


def test_selection_gate_accepts_cursor_pagination_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        MCP_CURSOR_GOAL,
        MCP_CURSOR_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(MCP_CURSOR_GOAL)
    assert "cursor" in family
    assert "paginated" in family
    assert "catalog" in family
    assert "watch" not in family
    assert "path" not in family
    assert "progress" not in family
    assert "timeout" not in family
    assert "browser" not in family
    assert "worktree" not in family
    assert "git-publication" not in family
