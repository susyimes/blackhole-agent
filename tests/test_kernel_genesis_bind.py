from pathlib import Path

from blackhole_agent.kernel_class_closure import class_closure_ids
from blackhole_agent.kernel_genesis_bind import (
    CONSUMED_GROWTH_GOAL,
    GENESIS_SELECTION_BLOCKED,
    KERNEL_GENESIS_BIND_DONE_WHEN,
    KERNEL_GENESIS_BIND_GOAL,
    KERNEL_GENESIS_BIND_ID,
    builtin_kernel_genesis_bind_proof,
    genesis_bind_is_needed,
)
from blackhole_agent.kernel_health import LOCAL_KERNEL
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.local_mission_sovereignty import LocalCampaign, save_campaign
from blackhole_agent.pattern_register import blocked_class_id, classify_unbound_turn
from blackhole_agent.unbound import UnboundMission, build_turn_prompt


def test_consumed_campaign_needs_genesis_bind():
    consumed = LocalCampaign(
        tick_count=3,
        last_contract_met=True,
        consumed_at="2026-08-29T08:32:38Z",
        goal="old",
        done_when="program_passes:capability.ledger-attestation;no_skill_route",
    )
    remaining = LocalCampaign(
        tick_count=3,
        goal="",
        done_when="",
        program=["capability.ledger-attestation"],
        cursor=0,
        last_contract_met=None,
    )
    assert genesis_bind_is_needed(consumed) is True
    assert genesis_bind_is_needed(remaining) is False


def test_hydrate_consumed_campaign_skips_genesis(tmp_path: Path):
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
    assert KERNEL_GENESIS_BIND_GOAL in prompt
    assert state.stage == "execution"


def test_classify_selection_rejection_is_genesis_selection_blocked():
    events = classify_unbound_turn(
        {
            "iteration": 3,
            "effective_status": "blocked",
            "summary": "Autonomous mission selection rejected (3/3): capability_diversity_gate",
            "selection_gate": {"accepted": False, "reasons": ["capability_diversity_gate: family saturated"]},
        }
    )
    assert events[0]["class_id"] == GENESIS_SELECTION_BLOCKED
    assert blocked_class_id({"status": "blocked", "last_summary": "kernel timeout"}) == "mission_blocked"


def test_builtin_proof_binds_gate_passing_successor():
    report = builtin_kernel_genesis_bind_proof()
    assert report["ok"] is True
    assert report["action"] == "kernel_genesis_bind"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["checks"]["hydrate_fills_empty_genesis"]
    assert report["checks"]["class_closed_bind_fills_successor"]
    assert report["checks"]["unscoped_remaining_still_wins"]
    assert report["checks"]["proved_catalog_item_skips_to_next"]
    assert KERNEL_GENESIS_BIND_ID in LOCAL_DENYLIST
    assert class_closure_ids(GENESIS_SELECTION_BLOCKED) == (KERNEL_GENESIS_BIND_ID,)
    assert KERNEL_GENESIS_BIND_ID in leftover_marker_ids(KERNEL_GENESIS_BIND_GOAL)
    assert KERNEL_GENESIS_BIND_DONE_WHEN in report["done_when"]
    assert CONSUMED_GROWTH_GOAL
    assert LOCAL_KERNEL == "local"
