from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Barrier

import pytest

from blackhole_agent.kernel_health import (
    LOCAL_KERNEL,
    KernelHealth,
    apply_health_reroute,
    breaker_status,
    builtin_kernel_circuit_breaker_proof,
    kernel_dispatch_admission,
    kernel_is_available,
    load_kernel_health,
    mark_kernel_success,
    persist_half_open_kernel_health,
    recorded_kernel_state,
    save_kernel_health,
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
    tripped = datetime.fromisoformat(later.tripped_at.replace("Z", "+00:00"))
    assert kernel_is_available(health, "grok", now=tripped + timedelta(hours=7))

    later_at = tripped + timedelta(hours=7)
    persist_half_open_kernel_health(tmp_path, health, now=later_at)
    assert recorded_kernel_state(tmp_path, "grok") == "half_open"
    assert load_kernel_health(tmp_path).kernels["grok"].state == "half_open"

    mark_kernel_success(health, "grok")
    assert kernel_is_available(health, "grok")

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


def test_simultaneous_provider_failures_all_survive_restart(tmp_path):
    names = ("codex", "kimi", "grok", "cursor")
    ready = Barrier(len(names))

    def fail(name):
        health = load_kernel_health(tmp_path)
        trip_kernel(health, name, "quota_exhausted")
        ready.wait(timeout=10)
        save_kernel_health(tmp_path, health)

    with ThreadPoolExecutor(len(names)) as pool:
        list(pool.map(fail, names))
    restarted = load_kernel_health(tmp_path)
    assert all(apply_health_reroute(name, restarted, names) == LOCAL_KERNEL for name in names)


def test_failed_replace_preserves_legacy_health_and_allows_retry(tmp_path, monkeypatch):
    from blackhole_agent import file_guard
    from blackhole_agent.kernel_health import health_path

    path = health_path(tmp_path)
    path.parent.mkdir(parents=True)
    legacy = b'{"schema_version":1,"kernels":{"kimi":{"state":"open","trip_count":3}}}'
    path.write_bytes(legacy)
    pending = load_kernel_health(tmp_path)
    trip_kernel(pending, "grok", "quota_exhausted")

    def fail_replace(*args):
        raise OSError("interrupted replacement")

    with monkeypatch.context() as patch:
        patch.setattr(file_guard.os, "replace", fail_replace)
        with pytest.raises(OSError, match="interrupted replacement"):
            save_kernel_health(tmp_path, pending)
    assert path.read_bytes() == legacy
    save_kernel_health(tmp_path, pending)
    restarted = load_kernel_health(tmp_path)
    assert {name: row.trip_count for name, row in restarted.kernels.items()} == {"kimi": 3, "grok": 1}


def test_login_trial_rechecks_a_cooldown_committed_after_route_selection(tmp_path):
    now = datetime(2026, 11, 28)
    legacy = {"kernels": {"cursor": {"state": "half_open", "class_id": "auth_failed", "trip_count": 1}}}
    stale = KernelHealth.from_dict(legacy)
    health = KernelHealth.from_dict(legacy)
    trip_kernel(health, "cursor", "auth_failed", now=now)
    save_kernel_health(tmp_path, health, now=now)
    with kernel_dispatch_admission(tmp_path, stale, now=now) as admit:
        assert not admit("cursor")
        assert admit("codex")
