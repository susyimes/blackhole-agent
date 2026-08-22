from blackhole_agent.kernel_health import LOCAL_KERNEL
from blackhole_agent.kernel_mission_plane import (
    builtin_kernel_mission_plane_proof,
    is_mission_plane_capability,
    succession_leaves_exhausted,
)
from blackhole_agent.kernel_salvage import HARVESTED_GROK_402, classify_run_artifact
from blackhole_agent.kernel_succession import is_succession_capability
from blackhole_agent.local_capability_kernel import is_safe_local_capability
from blackhole_agent.local_mission_sovereignty import LocalCampaign


def test_harvested_402_is_still_quota_exhausted():
    failure = classify_run_artifact(HARVESTED_GROK_402, error="Grok CLI failed with exit code 1")
    assert failure.class_id == "quota_exhausted"
    assert failure.retryable is False


def test_builtin_proof_escalates_past_succession():
    report = builtin_kernel_mission_plane_proof()
    assert report["ok"] is True
    assert report["action"] == "kernel_mission_plane"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["checks"]["local_tick_escalates_after_succession"]
    assert report["checks"]["recovered_resume_attaches_mission_plane"]
    assert report["checks"]["execute_402_then_mission_plane"]
    assert report["checks"]["mission_plane_ok_predicate_met"]
    assert LOCAL_KERNEL == "local"
    assert callable(is_mission_plane_capability)
    assert callable(is_succession_capability)
    assert callable(is_safe_local_capability)
    assert callable(succession_leaves_exhausted)
    assert LocalCampaign(tick_count=0).completed_ids == []
