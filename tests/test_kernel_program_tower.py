from pathlib import Path

from blackhole_agent.kernel_class_closure import class_closure_ids
from blackhole_agent.kernel_consumed_growth import is_cheap_inventory_id
from blackhole_agent.kernel_genesis_bind import (
    GENESIS_SELECTION_BLOCKED,
    KERNEL_GENESIS_BIND_ID,
    PROGRAM_LATTICE_GOAL,
    PROGRAM_STACK_GOAL,
    PROGRAM_STACK_ID,
    PROGRAM_TOWER_DONE_WHEN,
    PROGRAM_TOWER_GOAL,
    PROGRAM_TOWER_ID,
)
from blackhole_agent.kernel_health import LOCAL_KERNEL
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.kernel_program_tower import (
    PROGRAM_TOWER_UNIT_PREFIX,
    builtin_kernel_program_tower_proof,
    is_program_tower_id,
)
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.local_mission_sovereignty import LocalCampaign, save_campaign
from blackhole_agent.mission_selection import semantic_signature, semantic_similarity
from blackhole_agent.unbound import UnboundMission, build_turn_prompt


def test_program_tower_units_are_not_cheap():
    first = (
        f"{PROGRAM_TOWER_UNIT_PREFIX}-1-2__2-3___2-3__3-4"
        "____2-3__3-4___3-4__4-5"
    )
    assert is_program_tower_id(first) is True
    assert is_cheap_inventory_id(first) is False
    assert is_cheap_inventory_id(PROGRAM_TOWER_ID) is False
    assert is_program_tower_id(PROGRAM_TOWER_ID) is False


def test_tower_goal_is_not_a_stack_near_duplicate():
    similarity = semantic_similarity(
        semantic_signature(PROGRAM_STACK_GOAL),
        semantic_signature(PROGRAM_TOWER_GOAL),
    )
    assert similarity < 0.82
    assert PROGRAM_TOWER_ID in leftover_marker_ids(PROGRAM_TOWER_GOAL)
    assert PROGRAM_STACK_ID not in leftover_marker_ids(PROGRAM_TOWER_GOAL)
    assert PROGRAM_TOWER_ID not in leftover_marker_ids(PROGRAM_STACK_GOAL)


def test_hydrate_consumed_campaign_binds_tower_after_stack(tmp_path: Path):
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
            last_summary="Local program-stack promoted and proved capability.program-stack-1-2__2-3___2-3__3-4 in-process so recovered kernels keep compounding towers instead of blocking.",
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
    assert (
        PROGRAM_TOWER_GOAL in prompt
        or PROGRAM_STACK_GOAL in prompt
        or KERNEL_GENESIS_BIND_ID in (state.done_when or prompt)
    )
    assert state.stage == "execution"


def test_builtin_proof_promotes_program_tower():
    report = builtin_kernel_program_tower_proof()
    assert report["ok"] is True, report.get("checks")
    assert report["action"] == "kernel_program_tower"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["checks"]["promote_registers_unique_tower_coverage"]
    assert report["checks"]["second_promote_expands_tower_coverage"]
    assert report["checks"]["tick_after_saturated_stacks_runs_tower"]
    assert report["checks"]["proved_tower_skips_to_lattice"]
    assert PROGRAM_TOWER_ID in LOCAL_DENYLIST
    assert class_closure_ids(GENESIS_SELECTION_BLOCKED) == (KERNEL_GENESIS_BIND_ID,)
    assert PROGRAM_TOWER_ID in leftover_marker_ids(PROGRAM_TOWER_GOAL)
    assert PROGRAM_TOWER_DONE_WHEN in report["done_when"]
    assert PROGRAM_LATTICE_GOAL
    assert LOCAL_KERNEL == "local"
    assert report["checks"]["hydrate_fills_program_tower"]
    assert report["checks"]["unscoped_remaining_still_wins"]
    assert report["checks"]["preserves_operator_bind"]
    assert report["checks"]["novelty_ranks_pair_first"]
