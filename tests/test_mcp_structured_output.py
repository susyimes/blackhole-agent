from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.mcp_client import (
    McpStdioSession,
    _extract_text,
    echo_server_command,
    extract_output_schema,
    extract_structured_content,
    sealed_structured_text,
    validate_structured_output,
)
from blackhole_agent.mcp_cursor_pagination import MCP_CURSOR_GOAL, MCP_CURSOR_ID
from blackhole_agent.mcp_structured_output import (
    GATED_TOOL_NAME,
    MCP_STRUCTURED_DONE_WHEN,
    MCP_STRUCTURED_GOAL,
    MCP_STRUCTURED_ID,
    OUTPUT_SCHEMA,
    PLACEHOLDER_TEXT,
    UNLOCK_TOKEN,
    builtin_mcp_structured_output_proof,
    gated_command,
    invalid_command,
)
from blackhole_agent.mission_selection import (
    assess_mission_selection,
    capability_family,
    semantic_signature,
    semantic_similarity,
)


def test_goal_binds_structured_output_catalog() -> None:
    assert leftover_marker_ids(MCP_STRUCTURED_GOAL) == (MCP_STRUCTURED_ID,)
    assert MCP_STRUCTURED_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(MCP_CURSOR_GOAL) == (MCP_CURSOR_ID,)
    assert MCP_STRUCTURED_ID not in leftover_marker_ids(MCP_CURSOR_GOAL)
    assert MCP_CURSOR_ID not in leftover_marker_ids(MCP_STRUCTURED_GOAL)
    assert (
        semantic_similarity(
            semantic_signature(MCP_STRUCTURED_GOAL),
            semantic_signature(MCP_CURSOR_GOAL),
        )
        < 0.82
    )


def test_validate_structured_output_subset() -> None:
    valid = {"text": "gate-me", "token": UNLOCK_TOKEN}
    assert validate_structured_output(valid, OUTPUT_SCHEMA) == ""
    assert "missing token" in validate_structured_output({"text": "gate-me"}, OUTPUT_SCHEMA)
    assert "expected object" in validate_structured_output("nope", OUTPUT_SCHEMA)


def test_naive_session_strips_structured_content() -> None:
    session = McpStdioSession(
        gated_command(),
        timeout_seconds=8,
        validate_structured=False,
    )
    try:
        session.start()
        listed = session.list_tools()
        names = [str(item.get("name") or "") for item in listed.get("tools") or []]
        assert GATED_TOOL_NAME in names
        assert extract_output_schema((listed.get("tools") or [{}])[0]) == OUTPUT_SCHEMA
        result = session.call_tool(GATED_TOOL_NAME, {"text": "nope"})
        assert result.get("isError") is not True
        assert _extract_text(result) == PLACEHOLDER_TEXT
        assert UNLOCK_TOKEN not in _extract_text(result)
        assert extract_structured_content(result) is None
        assert sealed_structured_text(result) == ""
    finally:
        session.kill()


def test_live_session_consumes_structured_content() -> None:
    session = McpStdioSession(gated_command(), timeout_seconds=8)
    try:
        session.start()
        listed = session.list_tools()
        assert extract_output_schema((listed.get("tools") or [{}])[0]) == OUTPUT_SCHEMA
        result = session.call_tool(GATED_TOOL_NAME, {"text": "gate-me"})
        assert result.get("isError") is not True
        assert extract_structured_content(result) == {
            "text": "gate-me",
            "token": UNLOCK_TOKEN,
        }
        assert sealed_structured_text(result) == f"gate-me|{UNLOCK_TOKEN}"
        assert _extract_text(result) == PLACEHOLDER_TEXT
    finally:
        session.kill()


def test_invalid_structured_content_is_rejected() -> None:
    session = McpStdioSession(invalid_command(), timeout_seconds=8)
    try:
        session.start()
        session.list_tools()
        result = session.call_tool(GATED_TOOL_NAME, {"text": "nope"})
        assert result.get("isError") is True
        assert "missing token" in _extract_text(result)
        assert sealed_structured_text(result) == ""
    finally:
        session.kill()


def test_echo_server_text_only_still_serves() -> None:
    with McpStdioSession(echo_server_command()) as session:
        listed = session.list_tools()
        names = [str(item.get("name") or "") for item in listed.get("tools") or []]
        assert "echo" in names
        assert "echo" not in session.tool_output_schemas
        assert _extract_text(session.call_tool("echo", {"text": "plain"})) == "plain"


def test_builtin_proof_speaks_structured_output() -> None:
    report = builtin_mcp_structured_output_proof()
    assert report["ok"] is True, report.get("failed") or report.get("checks")
    assert report["action"] == "mcp_structured_output"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_skip_structured_is_untyped"]
    assert report["checks"]["published_structured_call_succeeds"]
    assert report["checks"]["invalid_structured_is_rejected"]
    assert report["checks"]["echo_text_only_still_serves"]
    assert report["checks"]["sibling_echo_still_serves"]
    assert report["checks"]["skip_structured_stays_on_plane"]
    assert report["checks"]["exhausted_catalog_binds_structured"]
    assert report["mission_goal"] == MCP_STRUCTURED_GOAL
    assert report["done_when"] == MCP_STRUCTURED_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[MCP_STRUCTURED_ID]
    assert capability.last_proof_exit_code == 0
    assert "structuredContent" in capability.tags
    assert "outputSchema" in capability.tags
    assert "mcp" in capability.tags


def test_selection_gate_accepts_structured_output_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        MCP_STRUCTURED_GOAL,
        MCP_STRUCTURED_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(MCP_STRUCTURED_GOAL)
    assert "structured" in family
    assert "output" in family
    assert "cursor" not in family
    assert "paginated" not in family
    assert "catalog" not in family
    assert "watch" not in family
    assert "path" not in family
    assert "progress" not in family
    assert "timeout" not in family
    assert "browser" not in family
    assert "worktree" not in family
    assert "git-publication" not in family
