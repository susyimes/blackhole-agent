from blackhole_agent.kernel_health import LOCAL_KERNEL
from blackhole_agent.kernel_salvage import HARVESTED_GROK_402, classify_run_artifact
from blackhole_agent.local_capability_kernel import builtin_local_capability_kernel_proof


def test_harvested_402_is_still_quota_exhausted():
    failure = classify_run_artifact(HARVESTED_GROK_402, error="Grok CLI failed with exit code 1")
    assert failure.class_id == "quota_exhausted"
    assert failure.retryable is False


def test_builtin_proof_failsover_402_into_ledger_work():
    report = builtin_local_capability_kernel_proof()
    assert report["ok"] is True
    assert report["action"] == "local_capability_kernel"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["checks"]["execute_402_invokes"]
    assert report["checks"]["rotates_next_tick"]
    assert report["checks"]["prefers_cheap_anchor"]
    assert LOCAL_KERNEL == "local"
