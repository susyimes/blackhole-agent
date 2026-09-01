from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.mcp_client import (
    McpStdioSession,
    _extract_text,
    echo_server_command,
    extract_tools_list_changed,
)
from blackhole_agent.mcp_progress import MCP_PROGRESS_GOAL, MCP_PROGRESS_ID
from blackhole_agent.mcp_roots_list_changed import (
    MCP_ROOTS_CHANGED_GOAL,
    MCP_ROOTS_CHANGED_ID,
)
from blackhole_agent.mcp_tools_list_changed import (
    BOOTSTRAP_TOOL_NAME,
    GATED_TOOL_NAME,
    MCP_TOOLS_CHANGED_DONE_WHEN,
    MCP_TOOLS_CHANGED_GOAL,
    MCP_TOOLS_CHANGED_ID,
    STALE_ERROR,
    UNLOCK_TOKEN,
    builtin_mcp_tools_list_changed_proof,
    gated_command,
)
from blackhole_agent.mission_selection import (
    assess_mission_selection,
    capability_family,
    semantic_signature,
    semantic_similarity,
)


def test_goal_binds_tools_list_changed_catalog() -> None:
    assert leftover_marker_ids(MCP_TOOLS_CHANGED_GOAL) == (MCP_TOOLS_CHANGED_ID,)
    assert MCP_TOOLS_CHANGED_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(MCP_PROGRESS_GOAL) == (MCP_PROGRESS_ID,)
    assert leftover_marker_ids(MCP_ROOTS_CHANGED_GOAL) == (MCP_ROOTS_CHANGED_ID,)
    assert MCP_TOOLS_CHANGED_ID not in leftover_marker_ids(MCP_PROGRESS_GOAL)
    assert MCP_TOOLS_CHANGED_ID not in leftover_marker_ids(MCP_ROOTS_CHANGED_GOAL)
    assert MCP_PROGRESS_ID not in leftover_marker_ids(MCP_TOOLS_CHANGED_GOAL)
    assert MCP_ROOTS_CHANGED_ID not in leftover_marker_ids(MCP_TOOLS_CHANGED_GOAL)
    assert (
        semantic_similarity(
            semantic_signature(MCP_TOOLS_CHANGED_GOAL),
            semantic_signature(MCP_PROGRESS_GOAL),
        )
        < 0.82
    )
    assert (
        semantic_similarity(
            semantic_signature(MCP_TOOLS_CHANGED_GOAL),
            semantic_signature(MCP_ROOTS_CHANGED_GOAL),
        )
        < 0.82
    )


def test_naive_session_errors_when_catalog_is_not_refreshed() -> None:
    session = McpStdioSession(gated_command(), timeout_seconds=8)
    try:
        session.start()
        listed = session.list_tools()
        names = [str(item.get("name") or "") for item in listed.get("tools") or []]
        assert BOOTSTRAP_TOOL_NAME in names
        assert GATED_TOOL_NAME not in names
        result = session.call_tool(GATED_TOOL_NAME, {"text": "nope"})
        assert result.get("isError") is True
        assert STALE_ERROR in _extract_text(result)
        assert extract_tools_list_changed(session.server_notifications)
        assert session.tool_names == [BOOTSTRAP_TOOL_NAME]
    finally:
        session.kill()


def test_refresh_after_list_changed_unblocks_gated_tool() -> None:
    session = McpStdioSession(gated_command(), timeout_seconds=8)
    try:
        session.start()
        session.list_tools()
        refreshed = session.refresh_tools()
        names = [str(item.get("name") or "") for item in refreshed.get("tools") or []]
        assert GATED_TOOL_NAME in names
        result = session.call_tool(GATED_TOOL_NAME, {"text": "gate-me"})
        assert result.get("isError") is not True
        assert _extract_text(result) == f"gate-me|{UNLOCK_TOKEN}"
        assert GATED_TOOL_NAME in session.tool_names
        assert session.tool_list_count >= 2
        assert extract_tools_list_changed(session.server_notifications)
    finally:
        session.kill()


def test_echo_server_advertises_list_changed_without_emitting() -> None:
    with McpStdioSession(echo_server_command()) as session:
        advertised = session.server_capabilities.get("tools")
        assert isinstance(advertised, dict)
        assert advertised.get("listChanged") is True
        listed = session.list_tools()
        names = [str(item.get("name") or "") for item in listed.get("tools") or []]
        assert "echo" in names
        assert _extract_text(session.call_tool("echo", {"text": "plain"})) == "plain"
        assert extract_tools_list_changed(session.server_notifications) == ()


def test_builtin_proof_speaks_tools_list_changed() -> None:
    report = builtin_mcp_tools_list_changed_proof()
    assert report["ok"] is True, report.get("checks")
    assert report["action"] == "mcp_tools_list_changed"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_skip_refresh_is_error"]
    assert report["checks"]["published_tool_call_succeeds"]
    assert report["checks"]["live_refresh_publishes_echo"]
    assert report["checks"]["echo_advertises_list_changed"]
    assert report["checks"]["sibling_echo_still_serves"]
    assert report["checks"]["skip_refresh_stays_on_plane"]
    assert report["checks"]["exhausted_catalog_binds_tools_changed"]
    assert report["mission_goal"] == MCP_TOOLS_CHANGED_GOAL
    assert report["done_when"] == MCP_TOOLS_CHANGED_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[MCP_TOOLS_CHANGED_ID]
    assert capability.last_proof_exit_code == 0
    assert "listChanged" in capability.tags
    assert "mcp" in capability.tags
    assert "catalog" in capability.tags


def test_selection_gate_accepts_tools_list_changed_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        MCP_TOOLS_CHANGED_GOAL,
        MCP_TOOLS_CHANGED_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(MCP_TOOLS_CHANGED_GOAL)
    assert "catalog" in family
    assert "progress" not in family
    assert "webhook" not in family
    assert "timeout" not in family
    assert "browser" not in family
    assert "worktree" not in family
    assert "git-publication" not in family
