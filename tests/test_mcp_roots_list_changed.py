from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.mcp_client import (
    DEFAULT_MCP_ROOTS,
    McpStdioSession,
    _extract_text,
    extract_root_uris,
)
from blackhole_agent.mcp_resource_subscribe import MCP_SUBSCRIBE_GOAL, MCP_SUBSCRIBE_ID
from blackhole_agent.mcp_reverse_channel import MCP_REVERSE_GOAL, MCP_REVERSE_ID
from blackhole_agent.mcp_roots_list_changed import (
    CHECKOUT_URI,
    MCP_ROOTS_CHANGED_DONE_WHEN,
    MCP_ROOTS_CHANGED_GOAL,
    MCP_ROOTS_CHANGED_ID,
    MISSING_ERROR,
    UNLOCK_TOKEN,
    WORKTREE_ROOTS,
    WORKTREE_URI,
    builtin_mcp_roots_list_changed_proof,
    gated_command,
)
from blackhole_agent.mission_selection import (
    assess_mission_selection,
    capability_family,
    semantic_signature,
    semantic_similarity,
)


def test_goal_binds_worktree_roots_plane() -> None:
    assert leftover_marker_ids(MCP_ROOTS_CHANGED_GOAL) == (MCP_ROOTS_CHANGED_ID,)
    assert MCP_ROOTS_CHANGED_ID in LOCAL_DENYLIST
    assert leftover_marker_ids(MCP_REVERSE_GOAL) == (MCP_REVERSE_ID,)
    assert leftover_marker_ids(MCP_SUBSCRIBE_GOAL) == (MCP_SUBSCRIBE_ID,)
    assert MCP_ROOTS_CHANGED_ID not in leftover_marker_ids(MCP_REVERSE_GOAL)
    assert MCP_ROOTS_CHANGED_ID not in leftover_marker_ids(MCP_SUBSCRIBE_GOAL)
    assert MCP_REVERSE_ID not in leftover_marker_ids(MCP_ROOTS_CHANGED_GOAL)
    assert MCP_SUBSCRIBE_ID not in leftover_marker_ids(MCP_ROOTS_CHANGED_GOAL)
    assert (
        semantic_similarity(
            semantic_signature(MCP_ROOTS_CHANGED_GOAL),
            semantic_signature(MCP_REVERSE_GOAL),
        )
        < 0.82
    )
    assert (
        semantic_similarity(
            semantic_signature(MCP_ROOTS_CHANGED_GOAL),
            semantic_signature(MCP_SUBSCRIBE_GOAL),
        )
        < 0.82
    )


def test_naive_session_errors_when_root_change_is_skipped() -> None:
    session = McpStdioSession(gated_command(), timeout_seconds=8)
    try:
        session.start()
        session.replace_roots(WORKTREE_ROOTS)
        assert WORKTREE_URI in extract_root_uris(session.roots)
        result = session.call_tool("echo", {"text": "nope"})
        assert result.get("isError") is True
        assert MISSING_ERROR in _extract_text(result)
        assert session.roots_list_changed_sent == []
    finally:
        session.kill()


def test_roots_list_changed_unlocks_gated_tool() -> None:
    session = McpStdioSession(gated_command(), timeout_seconds=8)
    try:
        session.start()
        advertised = session.client_capabilities.get("roots")
        assert isinstance(advertised, dict)
        assert advertised.get("listChanged") is True
        assert CHECKOUT_URI in extract_root_uris(session.roots)
        session.notify_roots_list_changed(WORKTREE_ROOTS)
        assert session.roots_list_changed_sent == [(WORKTREE_URI,)]
        result = session.call_tool("echo", {"text": "gate-me"})
        assert result.get("isError") is not True
        assert _extract_text(result) == f"gate-me|{UNLOCK_TOKEN}"
    finally:
        session.kill()


def test_checkout_notify_re_locks_gated_tool() -> None:
    session = McpStdioSession(gated_command(), timeout_seconds=8)
    try:
        session.start()
        session.notify_roots_list_changed(WORKTREE_ROOTS)
        assert _extract_text(session.call_tool("echo", {"text": "open"})) == f"open|{UNLOCK_TOKEN}"
        session.notify_roots_list_changed(DEFAULT_MCP_ROOTS)
        relocked = session.call_tool("echo", {"text": "closed"})
        assert relocked.get("isError") is True
        assert MISSING_ERROR in _extract_text(relocked)
    finally:
        session.kill()


def test_empty_roots_after_notify_is_fail_closed() -> None:
    session = McpStdioSession(gated_command(), timeout_seconds=8)
    try:
        session.start()
        session.notify_roots_list_changed(())
        unread = session.call_tool("echo", {"text": "still-locked"})
        assert unread.get("isError") is True
        assert MISSING_ERROR in _extract_text(unread)
    finally:
        session.kill()


def test_builtin_proof_speaks_worktree_roots_plane() -> None:
    report = builtin_mcp_roots_list_changed_proof()
    assert report["ok"] is True, report.get("checks")
    assert report["action"] == "mcp_roots_list_changed"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["passed_count"] >= 12
    assert report["checks"]["naive_skip_notify_is_error"]
    assert report["checks"]["naive_local_roots_are_worktree"]
    assert report["checks"]["worktree_gated_call_succeeds"]
    assert report["checks"]["checkout_re_locks_tool"]
    assert report["checks"]["empty_roots_fail_closed"]
    assert report["checks"]["sibling_echo_still_serves"]
    assert report["checks"]["skip_notify_stays_on_plane"]
    assert report["checks"]["exhausted_catalog_binds_roots_changed"]
    assert report["mission_goal"] == MCP_ROOTS_CHANGED_GOAL
    assert report["done_when"] == MCP_ROOTS_CHANGED_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[MCP_ROOTS_CHANGED_ID]
    assert capability.last_proof_exit_code == 0
    assert "roots" in capability.tags
    assert "worktree" in capability.tags
    assert "mcp" in capability.tags


def test_selection_gate_accepts_worktree_family(tmp_path: Path) -> None:
    gate = assess_mission_selection(
        tmp_path,
        MCP_ROOTS_CHANGED_GOAL,
        MCP_ROOTS_CHANGED_DONE_WHEN,
        history=(),
    )
    assert gate.accepted is True
    assert gate.scalar_extension is False
    family = capability_family(MCP_ROOTS_CHANGED_GOAL)
    assert "worktree" in family
    assert "timeout" not in family
    assert "subscription" not in family
    assert not family.startswith("kernel-runtime")
