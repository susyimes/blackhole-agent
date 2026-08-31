from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.mcp_client import (
    McpProtocolError,
    McpStdioSession,
    _extract_text,
    extract_completion_values,
)
from blackhole_agent.mcp_completions import (
    MCP_COMPLETIONS_DONE_WHEN,
    MCP_COMPLETIONS_GOAL,
    MCP_COMPLETIONS_ID,
    UNCOMPLETE_ERROR,
    UNLOCK_ARGUMENT,
    UNLOCK_PROMPT_REF,
    UNLOCK_TOKEN,
    builtin_mcp_completions_proof,
    gated_command,
)
from blackhole_agent.mcp_prompts import MCP_PROMPTS_GOAL, MCP_PROMPTS_ID
from blackhole_agent.mission_selection import (
    assess_mission_selection,
    capability_family,
    semantic_signature,
    semantic_similarity,
)


def test_goal_binds_completions_catalog() -> None:
    assert leftover_marker_ids(MCP_COMPLETIONS_GOAL) == (MCP_COMPLETIONS_ID,)
    assert MCP_COMPLETIONS_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(MCP_PROMPTS_GOAL) == (MCP_PROMPTS_ID,)
    assert MCP_COMPLETIONS_ID not in leftover_marker_ids(MCP_PROMPTS_GOAL)
    assert MCP_PROMPTS_ID not in leftover_marker_ids(MCP_COMPLETIONS_GOAL)
    assert (
        semantic_similarity(
            semantic_signature(MCP_COMPLETIONS_GOAL),
            semantic_signature(MCP_PROMPTS_GOAL),
        )
        < 0.82
    )


def test_naive_session_errors_when_completion_is_skipped() -> None:
    session = McpStdioSession(gated_command(), timeout_seconds=8)
    try:
        session.start()
        result = session.call_tool("echo", {"text": "nope"})
        assert result.get("isError") is True
        assert UNCOMPLETE_ERROR in _extract_text(result)
    finally:
        session.kill()


def test_completing_unlock_argument_unblocks_gated_tool() -> None:
    session = McpStdioSession(gated_command(), timeout_seconds=8)
    try:
        session.start()
        values = extract_completion_values(
            session.complete(UNLOCK_PROMPT_REF, UNLOCK_ARGUMENT, "BH-COMPLETE-O")
        )
        assert values == (UNLOCK_TOKEN,)
        result = session.call_tool("echo", {"text": "gate-me"})
        assert result.get("isError") is not True
        assert _extract_text(result) == f"gate-me|{UNLOCK_TOKEN}"
    finally:
        session.kill()


def test_unknown_gated_completion_is_fail_closed() -> None:
    session = McpStdioSession(gated_command(), timeout_seconds=8)
    try:
        session.start()
        try:
            session.complete({"type": "ref/prompt", "name": "missing-prompt"}, "token", "")
            raise AssertionError("unknown completion should raise")
        except McpProtocolError as exc:
            assert "unknown completion" in str(exc).lower()
        unread = session.call_tool("echo", {"text": "still-locked"})
        assert unread.get("isError") is True
    finally:
        session.kill()


def test_builtin_proof_speaks_argument_completion() -> None:
    report = builtin_mcp_completions_proof()
    assert report["ok"] is True, report.get("checks")
    assert report["action"] == "mcp_completions"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["echo_completes_note_prompt_prefix"]
    assert report["checks"]["echo_completes_resource_template"]
    assert report["checks"]["naive_skip_complete_is_error"]
    assert report["checks"]["completion_gated_call_succeeds"]
    assert report["checks"]["sibling_echo_still_serves"]
    assert report["checks"]["skip_complete_stays_on_plane"]
    assert report["checks"]["exhausted_catalog_binds_completions"]
    assert report["mission_goal"] == MCP_COMPLETIONS_GOAL
    assert report["done_when"] == MCP_COMPLETIONS_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[MCP_COMPLETIONS_ID]
    assert capability.last_proof_exit_code == 0
    assert "completions" in capability.tags
    assert "mcp" in capability.tags


def test_selection_gate_accepts_completions_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        MCP_COMPLETIONS_GOAL,
        MCP_COMPLETIONS_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(MCP_COMPLETIONS_GOAL)
    assert "completion" in family
    assert "prompt" not in family
    assert "sampling" not in family
    assert not family.startswith("kernel-runtime")
