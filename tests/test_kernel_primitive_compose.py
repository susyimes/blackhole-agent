from pathlib import Path

from blackhole_agent.kernel_class_closure import class_closure_ids
from blackhole_agent.kernel_genesis_bind import (
    COMPOSED_PROGRAM_GOAL,
    GENESIS_SELECTION_BLOCKED,
    KERNEL_GENESIS_BIND_ID,
    PRIMITIVE_COMPOSE_DONE_WHEN,
    PRIMITIVE_COMPOSE_GOAL,
    PRIMITIVE_COMPOSE_ID,
)
from blackhole_agent.kernel_health import LOCAL_KERNEL
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.kernel_primitive_compose import (
    PRIMITIVE_COMPOSE_UNIT_PREFIX,
    builtin_kernel_primitive_compose_proof,
    is_primitive_compose_id,
)
from blackhole_agent.kernel_consumed_growth import is_cheap_inventory_id
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.local_mission_sovereignty import LocalCampaign, save_campaign
from blackhole_agent.unbound import UnboundMission, build_turn_prompt


def test_primitive_compose_units_are_not_cheap():
    first = f"{PRIMITIVE_COMPOSE_UNIT_PREFIX}-1-2"
    assert is_primitive_compose_id(first) is True
    assert is_cheap_inventory_id(first) is False
    assert is_cheap_inventory_id(PRIMITIVE_COMPOSE_ID) is False
    assert is_primitive_compose_id(PRIMITIVE_COMPOSE_ID) is False


def test_hydrate_consumed_campaign_binds_compose_after_compound_loop(tmp_path: Path):
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
            last_summary="Local compound-loop absorbed and proved capability.compound-loop-leaf-1 as a novelty-ranked primitive after consumed-campaign leaves saturated.",
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
    assert PRIMITIVE_COMPOSE_GOAL in prompt or KERNEL_GENESIS_BIND_ID in (state.done_when or prompt)
    assert state.stage == "execution"


def test_builtin_proof_promotes_multi_primitive_composition():
    report = builtin_kernel_primitive_compose_proof()
    assert report["ok"] is True, report.get("checks")
    assert report["action"] == "kernel_primitive_compose"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["checks"]["promote_registers_unique_composed_coverage"]
    assert report["checks"]["second_promote_expands_composed_coverage"]
    assert report["checks"]["tick_after_saturated_primitives_runs_compose"]
    assert report["checks"]["proved_compose_skips_to_program"]
    assert PRIMITIVE_COMPOSE_ID in LOCAL_DENYLIST
    assert class_closure_ids(GENESIS_SELECTION_BLOCKED) == (KERNEL_GENESIS_BIND_ID,)
    assert PRIMITIVE_COMPOSE_ID in leftover_marker_ids(PRIMITIVE_COMPOSE_GOAL)
    assert PRIMITIVE_COMPOSE_DONE_WHEN in report["done_when"]
    assert COMPOSED_PROGRAM_GOAL
    assert LOCAL_KERNEL == "local"
    assert report["checks"]["hydrate_fills_primitive_compose"]
    assert report["checks"]["unscoped_remaining_still_wins"]
    assert report["checks"]["preserves_operator_bind"]
    assert report["checks"]["novelty_ranks_pair_first"]
