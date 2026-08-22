from blackhole_agent.kernel_finality import (
    builtin_kernel_finality_proof,
    can_finalize_local_campaign,
    waive_git_milestone_for_local_finality,
)
from blackhole_agent.kernel_health import LOCAL_KERNEL
from blackhole_agent.kernel_salvage import HARVESTED_GROK_402, classify_run_artifact
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.local_mission_sovereignty import LocalCampaign


def test_harvested_402_is_still_quota_exhausted():
    failure = classify_run_artifact(HARVESTED_GROK_402, error="Grok CLI failed with exit code 1")
    assert failure.class_id == "quota_exhausted"
    assert failure.retryable is False


def test_builtin_proof_closes_met_campaign_contract():
    report = builtin_kernel_finality_proof()
    assert report["ok"] is True
    assert report["action"] == "kernel_finality"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["checks"]["plane_tick_completes_when_met"]
    assert report["checks"]["ledger_static_contract_does_not_complete"]
    assert report["checks"]["execute_402_then_complete"]
    assert report["checks"]["controller_accepts_local_complete_without_git"]
    assert report["checks"]["controller_closes_without_commit"]
    assert LOCAL_KERNEL == "local"
    assert "capability.kernel-finality" in LOCAL_DENYLIST
    assert callable(can_finalize_local_campaign)
    assert callable(waive_git_milestone_for_local_finality)
    assert LocalCampaign(tick_count=0).completed_ids == []
