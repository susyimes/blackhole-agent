from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.kernel_class_closure import CLASS_CLOSURE_REQUIREMENTS
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.worktree_gc_resilience import (
    WORKTREE_GC_FAILED,
    WORKTREE_GC_RESILIENCE_DONE_WHEN,
    WORKTREE_GC_RESILIENCE_GOAL,
    WORKTREE_GC_RESILIENCE_ID,
    builtin_worktree_gc_resilience_proof,
)


def test_goal_binds_worktree_gc_resilience_plane() -> None:
    assert leftover_marker_ids(WORKTREE_GC_RESILIENCE_GOAL) == (WORKTREE_GC_RESILIENCE_ID,)
    assert CLASS_CLOSURE_REQUIREMENTS[WORKTREE_GC_FAILED] == (WORKTREE_GC_RESILIENCE_ID,)
    assert WORKTREE_GC_RESILIENCE_ID in LOCAL_DENYLIST


def test_builtin_proof_reclaims_stale_not_a_working_tree() -> None:
    report = builtin_worktree_gc_resilience_proof()
    assert report["ok"] is True, report.get("checks")
    assert report["action"] == "worktree_gc_resilience"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["checks"]["stale_dir_reclaimed"]
    assert report["checks"]["registered_worktree_still_removed"]
    assert report["checks"]["genuine_error_stays_error"]
    assert report["checks"]["harvests_sticky_gc_error"]
    assert report["checks"]["proved_closer_drops_class"]
    assert report["mission_goal"] == WORKTREE_GC_RESILIENCE_GOAL
    assert report["done_when"] == WORKTREE_GC_RESILIENCE_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[WORKTREE_GC_RESILIENCE_ID]
    assert capability.last_proof_exit_code == 0
    assert "worktree" in capability.tags
    assert "gc" in capability.tags
