import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.kernel_half_open_persist import (
    HALF_OPEN_PERSIST_DONE_WHEN,
    HALF_OPEN_PERSIST_GOAL,
    HALF_OPEN_PERSIST_ID,
    builtin_kernel_half_open_persist_proof,
)
from blackhole_agent.kernel_health import (
    KernelHealth,
    persist_half_open_kernel_health,
    recorded_kernel_state,
    recorded_open_kernels,
    save_kernel_health,
    trip_kernel,
)
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST


def test_goal_binds_half_open_persist_plane() -> None:
    assert leftover_marker_ids(HALF_OPEN_PERSIST_GOAL) == (HALF_OPEN_PERSIST_ID,)
    assert HALF_OPEN_PERSIST_ID in LOCAL_DENYLIST


def test_persist_after_cooldown_records_half_open(tmp_path: Path) -> None:
    health = KernelHealth()
    tripped = datetime(2026, 8, 30, 1, 0, tzinfo=timezone.utc)
    trip_kernel(health, "grok", "quota_exhausted", "402", now=tripped)
    save_kernel_health(tmp_path, health, now=tripped)
    assert recorded_kernel_state(tmp_path, "grok") == "open"
    assert "grok" in recorded_open_kernels(health)

    persist_half_open_kernel_health(tmp_path, now=tripped + timedelta(hours=7))
    assert recorded_kernel_state(tmp_path, "grok") == "half_open"
    payload = json.loads(
        (tmp_path / ".blackhole-agent" / "unbound" / "kernel-health.json").read_text(encoding="utf-8")
    )
    loaded = KernelHealth.from_dict(payload)
    assert loaded.kernels["grok"].state == "half_open"
    assert "grok" not in recorded_open_kernels(loaded)


def test_builtin_proof_persists_half_open_instead_of_dead_open() -> None:
    report = builtin_kernel_half_open_persist_proof()
    assert report["ok"] is True, report.get("checks")
    assert report["action"] == "kernel_half_open_persist"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["checks"]["hole_recorded_open_after_cooldown"]
    assert report["checks"]["persist_writes_half_open"]
    assert report["checks"]["report_does_not_treat_half_open_as_dead"]
    assert report["checks"]["salvage_records_half_open_before_probe"]
    assert report["mission_goal"] == HALF_OPEN_PERSIST_GOAL
    assert report["done_when"] == HALF_OPEN_PERSIST_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[HALF_OPEN_PERSIST_ID]
    assert capability.last_proof_exit_code == 0
    assert "half-open" in capability.tags
    assert "persistence" in capability.tags
