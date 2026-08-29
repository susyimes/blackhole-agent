from pathlib import Path

from blackhole_agent.kernel_class_closure import class_closure_ids
from blackhole_agent.kernel_consumed_growth import (
    CONSUMED_GROWTH_LEAF_ID,
    builtin_kernel_consumed_growth_proof,
    is_cheap_inventory_id,
)
from blackhole_agent.kernel_genesis_bind import (
    COMPOUND_LOOP_GOAL,
    CONSUMED_GROWTH_DONE_WHEN,
    CONSUMED_GROWTH_GOAL,
    CONSUMED_GROWTH_ID,
    GENESIS_SELECTION_BLOCKED,
    KERNEL_GENESIS_BIND_ID,
)
from blackhole_agent.kernel_health import LOCAL_KERNEL
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST, PREFERRED_LOCAL_IDS
from blackhole_agent.local_mission_sovereignty import LocalCampaign, save_campaign
from blackhole_agent.unbound import UnboundMission, build_turn_prompt


def test_cheap_inventory_ids_are_preferred_anchors():
    for item in PREFERRED_LOCAL_IDS:
        assert is_cheap_inventory_id(item) is True
    assert is_cheap_inventory_id("capability.fixture-local-a") is True
    assert is_cheap_inventory_id(CONSUMED_GROWTH_LEAF_ID) is False
    assert is_cheap_inventory_id(CONSUMED_GROWTH_ID) is False


def test_hydrate_consumed_campaign_binds_growth(tmp_path: Path):
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
            last_summary="Local mission sovereignty executed capability.goal-stack-health toward the bound mission without a first-class CLI kernel.",
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
    assert CONSUMED_GROWTH_GOAL in prompt or KERNEL_GENESIS_BIND_ID in (state.done_when or prompt)
    assert state.stage == "execution"


def test_builtin_proof_absorbs_and_proves_growth_leaf():
    report = builtin_kernel_consumed_growth_proof()
    assert report["ok"] is True, report.get("checks")
    assert report["action"] == "kernel_consumed_growth"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["checks"]["absorb_registers_and_proves_new_leaf"]
    assert report["checks"]["tick_invokes_absorbed_leaf"]
    assert report["checks"]["proved_growth_skips_to_compound_loop"]
    assert CONSUMED_GROWTH_ID in LOCAL_DENYLIST
    assert class_closure_ids(GENESIS_SELECTION_BLOCKED) == (KERNEL_GENESIS_BIND_ID,)
    assert CONSUMED_GROWTH_ID in leftover_marker_ids(CONSUMED_GROWTH_GOAL)
    assert CONSUMED_GROWTH_DONE_WHEN in report["done_when"]
    assert COMPOUND_LOOP_GOAL
    assert LOCAL_KERNEL == "local"
    assert report["checks"]["hydrate_fills_consumed_growth"]
    assert report["checks"]["unscoped_remaining_still_wins"]
    assert report["checks"]["preserves_operator_bind"]
