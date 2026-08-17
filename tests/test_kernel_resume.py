from pathlib import Path

from blackhole_agent.kernel_health import LOCAL_KERNEL
from blackhole_agent.kernel_salvage import HARVESTED_GROK_402, classify_run_artifact
from blackhole_agent.kernel_resume import (
    bind_create_fields,
    builtin_kernel_resume_proof,
    campaign_is_resumable,
    hydrate_mission_from_campaign,
)
from blackhole_agent.local_mission_sovereignty import LocalCampaign, save_campaign
from blackhole_agent.unbound import UnboundMission, build_turn_prompt


def test_harvested_402_is_still_quota_exhausted():
    failure = classify_run_artifact(HARVESTED_GROK_402, error="Grok CLI failed with exit code 1")
    assert failure.class_id == "quota_exhausted"
    assert failure.retryable is False


def test_hydrate_preserves_operator_fields(tmp_path: Path):
    save_campaign(
        tmp_path,
        LocalCampaign(
            goal="Campaign goal",
            done_when="capability_exists:repo.import-health",
            tick_count=1,
            last_contract_met=False,
        ),
    )

    class _State:
        def __init__(self) -> None:
            self.goal = "Keep the operator goal."
            self.done_when = ""
            self.repo_path = str(tmp_path)
            self.workspace_path = str(tmp_path)
            self.mission_id = "m1"
            self.stage = "genesis"

    state = _State()
    report = hydrate_mission_from_campaign(state)
    assert state.goal == "Keep the operator goal."
    assert state.done_when == "capability_exists:repo.import-health"
    assert report["applied"] is True
    assert report["source"] == "local_campaign"


def test_create_bind_uses_unfinished_campaign(tmp_path: Path):
    save_campaign(
        tmp_path,
        LocalCampaign(
            goal="Resume this campaign.",
            done_when="capability_exists:repo.import-health;no_skill_route",
            tick_count=2,
            last_contract_met=False,
        ),
    )
    goal, done_when, source = bind_create_fields(tmp_path)
    assert goal == "Resume this campaign."
    assert source == "local_campaign"
    assert "repo.import-health" in done_when
    assert campaign_is_resumable(LocalCampaign(tick_count=2, goal="g", done_when="d")) is True
    assert campaign_is_resumable(LocalCampaign(tick_count=2, goal="g", done_when="d", last_contract_met=True)) is False


def test_builtin_proof_resumes_recovered_kernel_instead_of_genesis():
    report = builtin_kernel_resume_proof()
    assert report["ok"] is True
    assert report["action"] == "kernel_resume"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["checks"]["prompt_skips_genesis_after_hydrate"]
    assert report["checks"]["durable_tick_writes_repo_not_only_worktree"]
    assert report["checks"]["execute_402_then_fresh_genesis_resumes"]
    assert LOCAL_KERNEL == "local"


def test_prompt_skips_genesis_when_campaign_is_unfinished(tmp_path: Path):
    save_campaign(
        tmp_path,
        LocalCampaign(
            mission_id="mission-1",
            goal="Keep growing after a 402.",
            done_when="capability_exists:repo.import-health;no_skill_route",
            bound_from="harvested_kernel_failure",
            tick_count=1,
            completed_ids=["capability.fixture-local-a"],
            last_summary="bound genesis after 402",
        ),
    )
    state = UnboundMission(
        schema_version=1,
        mission_id="mission-1",
        created_at="2026-08-17T00:00:00Z",
        updated_at="2026-08-17T00:00:00Z",
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
    assert "Keep growing after a 402." in prompt
    assert "Local-kernel campaign handoff" in prompt
    assert state.stage == "execution"
