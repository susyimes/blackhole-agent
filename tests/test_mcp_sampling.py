from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.kernel_half_open_probe import HALF_OPEN_PROBE_GOAL, HALF_OPEN_PROBE_ID
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.mcp_client import McpProtocolError, McpStdioSession, is_mcp_transport_failure
from blackhole_agent.mcp_reverse_channel import MCP_REVERSE_GOAL, MCP_REVERSE_ID
from blackhole_agent.mcp_sampling import (
    MCP_SAMPLING_DONE_WHEN,
    MCP_SAMPLING_GOAL,
    MCP_SAMPLING_ID,
    builtin_mcp_sampling_proof,
    gated_command,
)
from blackhole_agent.mission_selection import (
    assess_mission_selection,
    capability_family,
    semantic_signature,
    semantic_similarity,
)


def test_goal_binds_sampling_plane() -> None:
    assert leftover_marker_ids(MCP_SAMPLING_GOAL) == (MCP_SAMPLING_ID,)
    assert MCP_SAMPLING_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(MCP_REVERSE_GOAL) == (MCP_REVERSE_ID,)
    assert leftover_marker_ids(HALF_OPEN_PROBE_GOAL) == (HALF_OPEN_PROBE_ID,)
    assert MCP_SAMPLING_ID not in leftover_marker_ids(MCP_REVERSE_GOAL)
    assert MCP_SAMPLING_ID not in leftover_marker_ids(HALF_OPEN_PROBE_GOAL)
    assert (
        semantic_similarity(
            semantic_signature(MCP_SAMPLING_GOAL),
            semantic_signature(MCP_REVERSE_GOAL),
        )
        < 0.82
    )
    assert (
        semantic_similarity(
            semantic_signature(MCP_SAMPLING_GOAL),
            semantic_signature(HALF_OPEN_PROBE_GOAL),
        )
        < 0.82
    )


def test_naive_session_stalls_when_sampling_is_ignored() -> None:
    session = McpStdioSession(
        gated_command(),
        timeout_seconds=1.25,
        answer_reverse_channel=True,
        answer_sampling=False,
    )
    try:
        session.start()
        try:
            session.call_tool("echo", {"text": "nope"})
            raise AssertionError("unanswered sampling should stall tools/call")
        except McpProtocolError as exc:
            assert is_mcp_transport_failure(exc)
        assert session.answered_requests == []
    finally:
        session.kill()


def test_builtin_proof_answers_sampling_create_message() -> None:
    report = builtin_mcp_sampling_proof()
    assert report["ok"] is True, report.get("checks")
    assert report["action"] == "mcp_sampling"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_sampling_stalls"]
    assert report["checks"]["sampling_call_succeeds"]
    assert report["checks"]["sampling_answered_create_message"]
    assert report["checks"]["sibling_echo_still_serves"]
    assert report["checks"]["unanswered_sampling_is_isolated"]
    assert report["checks"]["exhausted_catalog_binds_sampling"]
    assert report["mission_goal"] == MCP_SAMPLING_GOAL
    assert report["done_when"] == MCP_SAMPLING_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[MCP_SAMPLING_ID]
    assert capability.last_proof_exit_code == 0
    assert "sampling" in capability.tags
    assert "mcp" in capability.tags


def test_selection_gate_accepts_sampling_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        MCP_SAMPLING_GOAL,
        MCP_SAMPLING_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(MCP_SAMPLING_GOAL)
    assert "sampling" in family
    assert not family.startswith("kernel-runtime")
