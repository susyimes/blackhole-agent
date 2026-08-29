from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.kernel_genesis_bind import KERNEL_GENESIS_BIND_GOAL, PROGRAM_WEAVE_GOAL
from blackhole_agent.kernel_genesis_diversify import (
    GENESIS_DIVERSIFY_DONE_WHEN,
    GENESIS_DIVERSIFY_GOAL,
    GENESIS_DIVERSIFY_ID,
    MISSION_MEMORY_GOAL,
    MISSION_MEMORY_ID,
    builtin_kernel_genesis_diversify_proof,
)
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.mission_selection import semantic_signature, semantic_similarity


def test_goal_binds_genesis_diversify_plane() -> None:
    assert leftover_marker_ids(GENESIS_DIVERSIFY_GOAL) == (GENESIS_DIVERSIFY_ID,)
    assert leftover_marker_ids(MISSION_MEMORY_GOAL) == (MISSION_MEMORY_ID,)
    assert GENESIS_DIVERSIFY_ID in LOCAL_DENYLIST
    assert (
        semantic_similarity(
            semantic_signature(GENESIS_DIVERSIFY_GOAL),
            semantic_signature(PROGRAM_WEAVE_GOAL),
        )
        < 0.82
    )
    assert (
        semantic_similarity(
            semantic_signature(GENESIS_DIVERSIFY_GOAL),
            semantic_signature(KERNEL_GENESIS_BIND_GOAL),
        )
        < 0.82
    )


def test_builtin_proof_binds_diversity_after_catalog_exhaustion() -> None:
    report = builtin_kernel_genesis_diversify_proof()
    assert report["ok"] is True, report.get("checks")
    assert report["action"] == "kernel_genesis_diversify"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["checks"]["live_history_rejects_weave"]
    assert report["checks"]["exhausted_catalog_binds_diversity"]
    assert report["checks"]["forage_history_still_binds_weave"]
    assert report["checks"]["proved_diversity_skips_to_memory"]
    assert report["mission_goal"] == GENESIS_DIVERSIFY_GOAL
    assert report["done_when"] == GENESIS_DIVERSIFY_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[GENESIS_DIVERSIFY_ID]
    assert capability.last_proof_exit_code == 0
    assert "diversity" in capability.tags
    assert "genesis" in capability.tags
