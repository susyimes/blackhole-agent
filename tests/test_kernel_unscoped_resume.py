from pathlib import Path

from blackhole_agent.kernel_class_closure import class_closure_ids
from blackhole_agent.kernel_health import LOCAL_KERNEL
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.kernel_resume import campaign_is_resumable, hydrate_mission_from_campaign
from blackhole_agent.kernel_unscoped_resume import (
    KERNEL_UNSCOPED_RESUME_ID,
    builtin_kernel_unscoped_resume_proof,
    remaining_program_steps,
    scope_unscoped_campaign,
)
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.local_mission_sovereignty import LocalCampaign, save_campaign
from blackhole_agent.unbound import UnboundMission, build_turn_prompt


def test_unscoped_remaining_is_resumable():
    campaign = LocalCampaign(
        tick_count=3,
        goal="",
        done_when="",
        program=["capability.ledger-attestation"],
        cursor=0,
        last_contract_met=None,
    )
    assert remaining_program_steps(campaign) == ["capability.ledger-attestation"]
    assert campaign_is_resumable(campaign) is True
    assert scope_unscoped_campaign(campaign) is True
    assert "capability.ledger-attestation" in campaign.goal
    assert campaign.done_when == "program_passes:capability.ledger-attestation;no_skill_route"


def test_hydrate_scopes_empty_genesis(tmp_path: Path):
    save_campaign(
        tmp_path,
        LocalCampaign(
            mission_id="prior",
            goal="",
            done_when="",
            bound_from="class_closed",
            program=["capability.ledger-inventory", "capability.ledger-attestation"],
            cursor=1,
            completed_ids=["capability.ledger-inventory"],
            tick_count=3,
            last_contract_met=None,
        ),
    )

    class _State:
        def __init__(self) -> None:
            self.goal = ""
            self.done_when = ""
            self.repo_path = str(tmp_path)
            self.workspace_path = str(tmp_path)
            self.mission_id = "recovered"
            self.stage = "genesis"

    state = _State()
    report = hydrate_mission_from_campaign(state, persist=True)
    assert report["applied"] is True
    assert "capability.ledger-attestation" in state.goal
    assert "program_passes:capability.ledger-attestation" in state.done_when
    assert state.stage == "execution"


def test_prompt_skips_genesis_when_unscoped_remaining_exists(tmp_path: Path):
    save_campaign(
        tmp_path,
        LocalCampaign(
            mission_id="mission-1",
            goal="",
            done_when="",
            bound_from="class_closed",
            tick_count=3,
            program=["capability.ledger-attestation"],
            cursor=0,
            last_summary="bound genesis after class_closed",
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
    assert "capability.ledger-attestation" in prompt
    assert state.stage == "execution"


def test_builtin_proof_scopes_class_closed_remaining_work():
    report = builtin_kernel_unscoped_resume_proof()
    assert report["ok"] is True
    assert report["action"] == "kernel_unscoped_resume"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["checks"]["hydrate_fills_empty_genesis"]
    assert report["checks"]["class_closed_bind_fills_remaining"]
    assert report["checks"]["class_closed_stays_empty_without_campaign"]
    assert report["checks"]["tick_preserves_remaining_across_mission"]
    assert KERNEL_UNSCOPED_RESUME_ID in LOCAL_DENYLIST
    assert class_closure_ids("mission_blocked") == (KERNEL_UNSCOPED_RESUME_ID,)
    assert KERNEL_UNSCOPED_RESUME_ID in leftover_marker_ids(
        "Local mission sovereignty executed capability.goal-stack-health toward "
        "the bound mission without a first-class CLI kernel."
    )
    assert LOCAL_KERNEL == "local"
