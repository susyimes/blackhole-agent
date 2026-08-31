from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.mcp_client import (
    McpProtocolError,
    McpStdioSession,
    _extract_text,
    extract_resource_text,
)
from blackhole_agent.mcp_echo_server import ABOUT_URI
from blackhole_agent.mcp_resources import (
    MCP_RESOURCES_DONE_WHEN,
    MCP_RESOURCES_GOAL,
    MCP_RESOURCES_ID,
    UNLOCK_TOKEN,
    UNLOCK_URI,
    UNREAD_ERROR,
    builtin_mcp_resources_proof,
    gated_command,
)
from blackhole_agent.mcp_sampling import MCP_SAMPLING_GOAL, MCP_SAMPLING_ID
from blackhole_agent.mission_selection import (
    assess_mission_selection,
    capability_family,
    semantic_signature,
    semantic_similarity,
)


def test_goal_binds_resources_plane() -> None:
    assert leftover_marker_ids(MCP_RESOURCES_GOAL) == (MCP_RESOURCES_ID,)
    assert MCP_RESOURCES_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(MCP_SAMPLING_GOAL) == (MCP_SAMPLING_ID,)
    assert MCP_RESOURCES_ID not in leftover_marker_ids(MCP_SAMPLING_GOAL)
    assert MCP_SAMPLING_ID not in leftover_marker_ids(MCP_RESOURCES_GOAL)
    assert (
        semantic_similarity(
            semantic_signature(MCP_RESOURCES_GOAL),
            semantic_signature(MCP_SAMPLING_GOAL),
        )
        < 0.82
    )


def test_naive_session_errors_when_resource_is_unread() -> None:
    session = McpStdioSession(gated_command(), timeout_seconds=8)
    try:
        session.start()
        result = session.call_tool("echo", {"text": "nope"})
        assert result.get("isError") is True
        assert UNREAD_ERROR in _extract_text(result)
    finally:
        session.kill()


def test_reading_unlock_resource_unblocks_gated_tool() -> None:
    session = McpStdioSession(gated_command(), timeout_seconds=8)
    try:
        session.start()
        listed = session.list_resources()
        uris = {item["uri"] for item in listed["resources"]}
        assert UNLOCK_URI in uris
        assert extract_resource_text(session.read_resource(UNLOCK_URI)) == UNLOCK_TOKEN
        result = session.call_tool("echo", {"text": "gate-me"})
        assert result.get("isError") is not True
        assert _extract_text(result) == f"gate-me|{UNLOCK_TOKEN}"
    finally:
        session.kill()


def test_unknown_gated_resource_is_fail_closed() -> None:
    session = McpStdioSession(gated_command(), timeout_seconds=8)
    try:
        session.start()
        try:
            session.read_resource("resource://blackhole/missing")
            raise AssertionError("unknown resource should raise")
        except McpProtocolError as exc:
            assert "unknown resource" in str(exc).lower()
        unread = session.call_tool("echo", {"text": "still-locked"})
        assert unread.get("isError") is True
    finally:
        session.kill()


def test_builtin_proof_speaks_resource_data_plane() -> None:
    report = builtin_mcp_resources_proof()
    assert report["ok"] is True, report.get("checks")
    assert report["action"] == "mcp_resources"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["echo_reads_about_resource"]
    assert report["checks"]["echo_reads_template_uri"]
    assert report["checks"]["naive_skip_read_is_error"]
    assert report["checks"]["resource_gated_call_succeeds"]
    assert report["checks"]["sibling_echo_still_serves"]
    assert report["checks"]["skip_read_stays_on_plane"]
    assert report["checks"]["exhausted_catalog_binds_resources"]
    assert report["mission_goal"] == MCP_RESOURCES_GOAL
    assert report["done_when"] == MCP_RESOURCES_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[MCP_RESOURCES_ID]
    assert capability.last_proof_exit_code == 0
    assert "resources" in capability.tags
    assert "mcp" in capability.tags


def test_selection_gate_accepts_resources_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        MCP_RESOURCES_GOAL,
        MCP_RESOURCES_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(MCP_RESOURCES_GOAL)
    assert "failure" in family
    assert "sampling" not in family
    assert not family.startswith("kernel-runtime")
    assert ABOUT_URI.startswith("resource://")
