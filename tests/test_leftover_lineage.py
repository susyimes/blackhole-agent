from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.experience_fuel import leftover_next_step
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.leftover_lineage import (
    HARVESTED_MCP_RECOVERY_LEFTOVER,
    LEFTOVER_LINEAGE_DONE_WHEN,
    LEFTOVER_LINEAGE_GOAL,
    LEFTOVER_LINEAGE_ID,
    MCP_RECOVERY_ID,
    builtin_leftover_lineage_proof,
)
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST


def test_leftover_lineage_goal_binds_origin_plane() -> None:
    assert leftover_marker_ids(LEFTOVER_LINEAGE_GOAL) == (LEFTOVER_LINEAGE_ID,)
    assert leftover_marker_ids(HARVESTED_MCP_RECOVERY_LEFTOVER) == (MCP_RECOVERY_ID,)
    prefixed = "None. Mission complete. " + LEFTOVER_LINEAGE_GOAL
    assert leftover_next_step(prefixed).startswith("Repair leftover harvest isolation")


def test_builtin_proof_consumes_origin_closed_leftovers() -> None:
    report = builtin_leftover_lineage_proof()
    assert report["ok"] is True
    assert report["action"] == "leftover_lineage"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["checks"]["checkout_lag_keeps_leftover_open"]
    assert report["checks"]["origin_ledger_consumes_recovery_leftover"]
    assert report["checks"]["harvest_drops_origin_closed_leftover"]
    assert report["checks"]["unrelated_leftover_stays_open"]
    assert report["checks"]["prefixed_state_goal_consumes_claim"]
    assert report["mission_goal"] == LEFTOVER_LINEAGE_GOAL
    assert report["done_when"] == LEFTOVER_LINEAGE_DONE_WHEN
    assert LEFTOVER_LINEAGE_ID in LOCAL_DENYLIST
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[LEFTOVER_LINEAGE_ID]
    assert capability.last_proof_exit_code == 0
    assert "leftover" in capability.tags
    assert "origin" in capability.tags
