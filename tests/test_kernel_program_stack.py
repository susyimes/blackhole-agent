from pathlib import Path

from blackhole_agent.kernel_class_closure import class_closure_ids
from blackhole_agent.kernel_consumed_growth import is_cheap_inventory_id
from blackhole_agent.kernel_genesis_bind import (
    GENESIS_SELECTION_BLOCKED,
    KERNEL_GENESIS_BIND_ID,
    PROGRAM_STACK_DONE_WHEN,
    PROGRAM_STACK_GOAL,
    PROGRAM_STACK_ID,
    PROGRAM_TOWER_GOAL,
)
from blackhole_agent.kernel_health import LOCAL_KERNEL
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.kernel_program_stack import (
    PROGRAM_STACK_UNIT_PREFIX,
    builtin_kernel_program_stack_proof,
    is_program_stack_id,
)
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.local_mission_sovereignty import LocalCampaign, save_campaign
from blackhole_agent.unbound import UnboundMission, build_turn_prompt


def test_program_stack_units_are_not_cheap():
    first = f"{PROGRAM_STACK_UNIT_PREFIX}-1-2__2-3___2-3__3-4"
    assert is_program_stack_id(first) is True
    assert is_cheap_inventory_id(first) is False
    assert is_cheap_inventory_id(PROGRAM_STACK_ID) is False
    assert is_program_stack_id(PROGRAM_STACK_ID) is False


def test_hydrate_consumed_campaign_binds_stack_after_program(tmp_path: Path):
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
            last_summary="Local composed-program promoted and proved capability.composed-program-1-2__2-3 in-process so recovered kernels keep stacking programs instead of blocking.",
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
    assert PROGRAM_STACK_GOAL in prompt or KERNEL_GENESIS_BIND_ID in (state.done_when or prompt)
    assert state.stage == "execution"


def test_builtin_proof_promotes_program_stack():
    report = builtin_kernel_program_stack_proof()
    assert report["ok"] is True, report.get("checks")
    assert report["action"] == "kernel_program_stack"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["checks"]["promote_registers_unique_stack_coverage"]
    assert report["checks"]["second_promote_expands_stack_coverage"]
    assert report["checks"]["tick_after_saturated_programs_runs_stack"]
    assert report["checks"]["proved_stack_skips_to_tower"]
    assert PROGRAM_STACK_ID in LOCAL_DENYLIST
    assert class_closure_ids(GENESIS_SELECTION_BLOCKED) == (KERNEL_GENESIS_BIND_ID,)
    assert PROGRAM_STACK_ID in leftover_marker_ids(PROGRAM_STACK_GOAL)
    assert PROGRAM_STACK_DONE_WHEN in report["done_when"]
    assert PROGRAM_TOWER_GOAL
    assert LOCAL_KERNEL == "local"
    assert report["checks"]["hydrate_fills_program_stack"]
    assert report["checks"]["unscoped_remaining_still_wins"]
    assert report["checks"]["preserves_operator_bind"]
    assert report["checks"]["novelty_ranks_pair_first"]
