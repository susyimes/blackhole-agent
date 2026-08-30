from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.kernel_class_closure import CLASS_CLOSURE_REQUIREMENTS
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.mcp_http_event_stream import MCP_HTTP_EVENT_GOAL, MCP_HTTP_EVENT_ID
from blackhole_agent.publication_resilience import (
    PUBLICATION_FAILED,
    PUBLICATION_RESILIENCE_DONE_WHEN,
    PUBLICATION_RESILIENCE_GOAL,
    PUBLICATION_RESILIENCE_ID,
    builtin_publication_resilience_proof,
)


def test_goal_binds_publication_resilience_plane() -> None:
    assert leftover_marker_ids(PUBLICATION_RESILIENCE_GOAL) == (PUBLICATION_RESILIENCE_ID,)
    assert CLASS_CLOSURE_REQUIREMENTS[PUBLICATION_FAILED] == (PUBLICATION_RESILIENCE_ID,)
    assert PUBLICATION_RESILIENCE_ID in LOCAL_DENYLIST
    assert PUBLICATION_RESILIENCE_ID not in leftover_marker_ids(MCP_HTTP_EVENT_GOAL)
    assert leftover_marker_ids(MCP_HTTP_EVENT_GOAL) == (MCP_HTTP_EVENT_ID,)


def test_builtin_proof_refuses_diverged_remote_head() -> None:
    report = builtin_publication_resilience_proof()
    assert report["ok"] is True, report.get("checks")
    assert report["action"] == "publication_resilience"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["checks"]["diverged_remote_is_refused"]
    assert report["checks"]["diverged_remote_is_unchanged"]
    assert report["checks"]["same_sha_republication_is_idempotent"]
    assert report["checks"]["ancestor_fast_forward_publishes"]
    assert report["checks"]["terminal_mismatch_drops_pending"]
    assert report["checks"]["transient_error_keeps_pending"]
    assert report["checks"]["harvests_sticky_publish_error"]
    assert report["checks"]["proved_closer_drops_class"]
    assert report["checks"]["exhausted_catalog_binds_publication"]
    assert report["mission_goal"] == PUBLICATION_RESILIENCE_GOAL
    assert report["done_when"] == PUBLICATION_RESILIENCE_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[PUBLICATION_RESILIENCE_ID]
    assert capability.last_proof_exit_code == 0
    assert "publication" in capability.tags
    assert "git" in capability.tags
