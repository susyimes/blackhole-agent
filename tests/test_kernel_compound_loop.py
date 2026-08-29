from pathlib import Path

from blackhole_agent.kernel_class_closure import class_closure_ids
from blackhole_agent.kernel_compound_loop import (
    COMPOUND_LOOP_LEAF_PREFIX,
    builtin_kernel_compound_loop_proof,
    is_compound_loop_leaf_id,
)
from blackhole_agent.kernel_consumed_growth import is_cheap_inventory_id
from blackhole_agent.kernel_genesis_bind import (
    COMPOUND_LOOP_DONE_WHEN,
    COMPOUND_LOOP_GOAL,
    COMPOUND_LOOP_ID,
    GENESIS_SELECTION_BLOCKED,
    KERNEL_GENESIS_BIND_ID,
    PRIMITIVE_COMPOSE_GOAL,
)
from blackhole_agent.kernel_health import LOCAL_KERNEL
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.local_mission_sovereignty import LocalCampaign, save_campaign
from blackhole_agent.unbound import UnboundMission, build_turn_prompt


def test_compound_loop_leaves_are_not_cheap():
    first = f"{COMPOUND_LOOP_LEAF_PREFIX}-1"
    assert is_compound_loop_leaf_id(first) is True
    assert is_cheap_inventory_id(first) is False
    assert is_cheap_inventory_id(COMPOUND_LOOP_ID) is False


def test_hydrate_consumed_campaign_binds_compound_loop_after_growth(tmp_path: Path):
    save_campaign(
        tmp_path,
        LocalCampaign(
            mission_id="prior",
            goal="Resume remaining durable campaign work after class_closed left genesis unscoped: capability.ledger-attestation",
            done_when="program_passes:capability.ledger-attestation;no_skill_route",
            bound_from="class_closed",
            tick_count=3,
            last_contract_met=True,
            consumed_at="2026-08-29T08:32:38Z",
            last_summary="Local consumed-growth absorbed and proved capability.consumed-growth-leaf in-process so recovered kernels compound capability instead of rotating inventory.",
        ),
    )
    state = UnboundMission(
        schema_version=1,
        mission_id="mission-1",
        created_at="2026-08-29T00:00:00Z",
        updated_at="2026-08-29T00:00:00Z",
        repo_path=str(tmp_path),
        workspace_path=str(tmp_path),
        branch="unbound/test",
        target_branch="main",
        goal="",
        done_when="",
        stage="genesis",
        base_head="abc",
        last_milestone_head="abc",
    )
    prompt = build_turn_prompt(
        state,
        {"head": "abc", "status": "", "diff_stat": "", "recent_commits": "abc seed"},
        state_path=tmp_path / "state.json",
    )
    assert "Mission genesis is still open" not in prompt
    assert COMPOUND_LOOP_GOAL in prompt or KERNEL_GENESIS_BIND_ID in (state.done_when or prompt)
    assert state.stage == "execution"


def test_builtin_proof_runs_novelty_ranked_compound_loop():
    report = builtin_kernel_compound_loop_proof()
    assert report["ok"] is True, report.get("checks")
    assert report["action"] == "kernel_compound_loop"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["checks"]["absorb_registers_and_proves_novel_primitive"]
    assert report["checks"]["second_absorb_expands_coverage"]
    assert report["checks"]["tick_after_growth_leaf_runs_compound_loop"]
    assert report["checks"]["tick_loop_expands_second_primitive"]
    assert report["checks"]["proved_compound_loop_skips_to_compose"]
    assert COMPOUND_LOOP_ID in LOCAL_DENYLIST
    assert class_closure_ids(GENESIS_SELECTION_BLOCKED) == (KERNEL_GENESIS_BIND_ID,)
    assert COMPOUND_LOOP_ID in leftover_marker_ids(COMPOUND_LOOP_GOAL)
    assert COMPOUND_LOOP_DONE_WHEN in report["done_when"]
    assert PRIMITIVE_COMPOSE_GOAL
    assert LOCAL_KERNEL == "local"
    assert report["checks"]["hydrate_fills_compound_loop"]
    assert report["checks"]["unscoped_remaining_still_wins"]
    assert report["checks"]["preserves_operator_bind"]
    assert report["checks"]["novelty_ranks_missing_primitive_first"]
