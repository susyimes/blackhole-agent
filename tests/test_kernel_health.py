from datetime import timedelta

from blackhole_agent.kernel_health import (
    LOCAL_KERNEL,
    KernelHealth,
    apply_health_reroute,
    breaker_status,
    builtin_kernel_circuit_breaker_proof,
    kernel_is_available,
    load_kernel_health,
    mark_kernel_success,
    persist_half_open_kernel_health,
    recorded_kernel_state,
    trip_kernel,
)
from blackhole_agent.kernel_salvage import HARVESTED_GROK_402, classify_run_artifact


def test_quota_trip_skips_grok_and_prefers_peer_then_local():
    health = KernelHealth()
    failure = classify_run_artifact(HARVESTED_GROK_402, error="Grok CLI failed with exit code 1")
    trip_kernel(health, "grok", failure.class_id, failure.evidence)

    assert breaker_status(health.kernels["grok"]) == "open"
    assert kernel_is_available(health, LOCAL_KERNEL)
    assert apply_health_reroute("grok", health, installed=()) == LOCAL_KERNEL
    assert apply_health_reroute("grok", health, installed={"kimi", "grok"}) == "kimi"


def test_success_closes_breaker_and_cooldown_half_opens(tmp_path):
    health = KernelHealth()
    trip_kernel(health, "grok", "quota_exhausted", "402")
    assert not kernel_is_available(health, "grok")

    later = health.kernels["grok"]
    from datetime import datetime, timezone

    tripped = datetime.fromisoformat(later.tripped_at.replace("Z", "+00:00"))
    assert kernel_is_available(health, "grok", now=tripped + timedelta(hours=7))

    later_at = tripped + timedelta(hours=7)
    persist_half_open_kernel_health(tmp_path, health, now=later_at)
    assert recorded_kernel_state(tmp_path, "grok") == "half_open"
    assert load_kernel_health(tmp_path).kernels["grok"].state == "half_open"

    mark_kernel_success(health, "grok")
    assert kernel_is_available(health, "grok")

    from blackhole_agent.kernel_health import save_kernel_health

    save_kernel_health(tmp_path, health)
    loaded = load_kernel_health(tmp_path)
    assert kernel_is_available(loaded, "grok")
    assert loaded.kernels["grok"].state == "closed"


def test_builtin_proof_replays_harvested_402_storm():
    report = builtin_kernel_circuit_breaker_proof()
    assert report["ok"] is True
    assert report["action"] == "kernel_circuit_breaker"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["checks"]["storm_invokes_grok_once"]
    assert report["checks"]["storm_finishes_on_local"]
