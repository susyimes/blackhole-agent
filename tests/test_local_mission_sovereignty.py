from pathlib import Path

from blackhole_agent.kernel_health import LOCAL_KERNEL
from blackhole_agent.kernel_salvage import HARVESTED_GROK_402, classify_run_artifact
from blackhole_agent.local_mission_sovereignty import (
    HARVESTED_KERNEL_FAILURE_DONE_WHEN,
    HARVESTED_KERNEL_FAILURE_GOAL,
    bind_local_mission,
    builtin_local_mission_sovereignty_proof,
    render_local_campaign_for_prompt,
    save_campaign,
    LocalCampaign,
)
from blackhole_agent.unbound import UnboundMission, build_turn_prompt


def test_harvested_402_is_still_quota_exhausted():
    failure = classify_run_artifact(HARVESTED_GROK_402, error="Grok CLI failed with exit code 1")
    assert failure.class_id == "quota_exhausted"
    assert failure.retryable is False


def test_bind_preserves_operator_fields_independently():
    class _State:
        goal = "Keep the operator goal."
        done_when = ""
        repo_path = "."
        workspace_path = "."

    binding = bind_local_mission(_State(), harvest=False)
    assert binding.goal == "Keep the operator goal."
    assert binding.done_when == HARVESTED_KERNEL_FAILURE_DONE_WHEN
    assert "state.goal" in binding.source


def test_builtin_proof_binds_402_genesis_and_advances_campaign():
    report = builtin_local_mission_sovereignty_proof()
    assert report["ok"] is True
    assert report["action"] == "local_mission_sovereignty"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["checks"]["execute_402_binds_genesis"]
    assert report["checks"]["campaign_advances"]
    assert report["checks"]["preserves_operator_goal"]
    assert report["checks"]["contract_met_when_capability_present"]
    assert LOCAL_KERNEL == "local"
    assert "kernel_turn_failed" in HARVESTED_KERNEL_FAILURE_GOAL


def test_prompt_includes_local_campaign_handoff(tmp_path: Path):
    save_campaign(
        tmp_path,
        LocalCampaign(
            mission_id="mission-1",
            goal=HARVESTED_KERNEL_FAILURE_GOAL,
            done_when=HARVESTED_KERNEL_FAILURE_DONE_WHEN,
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
        goal=HARVESTED_KERNEL_FAILURE_GOAL,
        done_when=HARVESTED_KERNEL_FAILURE_DONE_WHEN,
        stage="execution",
        base_head="abc",
        last_milestone_head="abc",
    )
    prompt = build_turn_prompt(
        state,
        {"head": "abc", "status": "", "diff_stat": "", "recent_commits": "abc seed"},
        state_path=tmp_path / "state.json",
    )
    assert "Local-kernel campaign handoff" in prompt
    assert render_local_campaign_for_prompt(tmp_path).startswith("Local-kernel campaign handoff")
