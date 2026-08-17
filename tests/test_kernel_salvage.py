import json

from blackhole_agent.kernel_health import LOCAL_KERNEL
from blackhole_agent.kernel_salvage import (
    HARVESTED_GROK_402,
    builtin_kernel_decision_salvage_proof,
    classify_run_artifact,
    salvage_kernel_failure,
    select_failover_kernel,
)


def test_harvested_402_is_quota_and_failsover_to_local_without_peer():
    failure = classify_run_artifact(HARVESTED_GROK_402, error="Grok CLI failed with exit code 1")
    assert failure.class_id == "quota_exhausted"
    assert failure.retryable is False

    salvaged = salvage_kernel_failure(
        error="Grok CLI failed with exit code 1",
        current_kernel="grok",
        artifact=HARVESTED_GROK_402,
        installed_kernels=set(),
    )
    assert salvaged.decision["status"] == "continue"
    assert salvaged.failover_kernel == LOCAL_KERNEL

    blocked = salvage_kernel_failure(
        error="Grok CLI failed with exit code 1",
        current_kernel="grok",
        artifact=HARVESTED_GROK_402,
        installed_kernels=set(),
        allow_failover=False,
    )
    assert blocked.decision["status"] == "blocked"
    assert blocked.failover_kernel == ""


def test_quota_failsover_to_installed_peer_and_salvages_embedded_decision():
    salvaged = salvage_kernel_failure(
        error="Grok CLI failed with exit code 1",
        current_kernel="grok",
        artifact=HARVESTED_GROK_402,
        installed_kernels={"codex", "kimi"},
    )
    assert salvaged.failover_kernel == "codex"
    assert salvaged.decision["status"] == "continue"
    assert select_failover_kernel("grok", {"kimi"}) == "kimi"

    embedded = salvage_kernel_failure(
        error="exit 1",
        current_kernel="grok",
        last_message=json.dumps({"status": "continue", "summary": "partial"}),
        installed_kernels=set(),
    )
    assert embedded.source == "message"
    assert embedded.decision["summary"] == "partial"


def test_builtin_proof_replays_harvested_failure():
    report = builtin_kernel_decision_salvage_proof()
    assert report["ok"] is True
    assert report["action"] == "kernel_decision_salvage"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
