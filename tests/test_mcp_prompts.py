from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.mcp_client import (
    McpProtocolError,
    McpStdioSession,
    _extract_text,
    extract_prompt_text,
)
from blackhole_agent.mcp_echo_server import ABOUT_PROMPT
from blackhole_agent.mcp_prompts import (
    MCP_PROMPTS_DONE_WHEN,
    MCP_PROMPTS_GOAL,
    MCP_PROMPTS_ID,
    UNGET_ERROR,
    UNLOCK_PROMPT,
    UNLOCK_TOKEN,
    builtin_mcp_prompts_proof,
    gated_command,
)
from blackhole_agent.mcp_resources import MCP_RESOURCES_GOAL, MCP_RESOURCES_ID
from blackhole_agent.mission_selection import (
    assess_mission_selection,
    capability_family,
    semantic_signature,
    semantic_similarity,
)


def test_goal_binds_prompts_catalog() -> None:
    assert leftover_marker_ids(MCP_PROMPTS_GOAL) == (MCP_PROMPTS_ID,)
    assert MCP_PROMPTS_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(MCP_RESOURCES_GOAL) == (MCP_RESOURCES_ID,)
    assert MCP_PROMPTS_ID not in leftover_marker_ids(MCP_RESOURCES_GOAL)
    assert MCP_RESOURCES_ID not in leftover_marker_ids(MCP_PROMPTS_GOAL)
    assert (
        semantic_similarity(
            semantic_signature(MCP_PROMPTS_GOAL),
            semantic_signature(MCP_RESOURCES_GOAL),
        )
        < 0.82
    )


def test_naive_session_errors_when_prompt_is_unfetched() -> None:
    session = McpStdioSession(gated_command(), timeout_seconds=8)
    try:
        session.start()
        result = session.call_tool("echo", {"text": "nope"})
        assert result.get("isError") is True
        assert UNGET_ERROR in _extract_text(result)
    finally:
        session.kill()


def test_fetching_unlock_prompt_unblocks_gated_tool() -> None:
    session = McpStdioSession(gated_command(), timeout_seconds=8)
    try:
        session.start()
        listed = session.list_prompts()
        names = {item["name"] for item in listed["prompts"]}
        assert UNLOCK_PROMPT in names
        assert extract_prompt_text(session.get_prompt(UNLOCK_PROMPT)) == UNLOCK_TOKEN
        result = session.call_tool("echo", {"text": "gate-me"})
        assert result.get("isError") is not True
        assert _extract_text(result) == f"gate-me|{UNLOCK_TOKEN}"
    finally:
        session.kill()


def test_unknown_gated_prompt_is_fail_closed() -> None:
    session = McpStdioSession(gated_command(), timeout_seconds=8)
    try:
        session.start()
        try:
            session.get_prompt("missing-prompt")
            raise AssertionError("unknown prompt should raise")
        except McpProtocolError as exc:
            assert "unknown prompt" in str(exc).lower()
        unread = session.call_tool("echo", {"text": "still-locked"})
        assert unread.get("isError") is True
    finally:
        session.kill()


def test_builtin_proof_speaks_prompt_catalog() -> None:
    report = builtin_mcp_prompts_proof()
    assert report["ok"] is True, report.get("checks")
    assert report["action"] == "mcp_prompts"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["echo_gets_about_prompt"]
    assert report["checks"]["echo_gets_templated_prompt"]
    assert report["checks"]["naive_skip_get_is_error"]
    assert report["checks"]["prompt_gated_call_succeeds"]
    assert report["checks"]["sibling_echo_still_serves"]
    assert report["checks"]["skip_get_stays_on_plane"]
    assert report["checks"]["exhausted_catalog_binds_prompts"]
    assert report["mission_goal"] == MCP_PROMPTS_GOAL
    assert report["done_when"] == MCP_PROMPTS_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[MCP_PROMPTS_ID]
    assert capability.last_proof_exit_code == 0
    assert "prompts" in capability.tags
    assert "mcp" in capability.tags


def test_selection_gate_accepts_prompts_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        MCP_PROMPTS_GOAL,
        MCP_PROMPTS_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(MCP_PROMPTS_GOAL)
    assert "prompt" in family
    assert "failure" not in family
    assert "sampling" not in family
    assert not family.startswith("kernel-runtime")
    assert ABOUT_PROMPT == "about"
