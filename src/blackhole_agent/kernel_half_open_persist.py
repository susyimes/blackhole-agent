"""Persist half-open kernel health after cooldown so reports do not treat a probe as dead.

``breaker_status`` already computes ``half_open`` once cooldown elapses, but
``trip_kernel`` records ``state=open`` and that field is what operators and
reports read from ``kernel-health.json``. Until a later success or re-trip,
the on-disk record stays ``open``, so a half-open probe looks still dead.

This module closes that hole:

- refresh recorded ``state`` from computed breaker status
- persist ``half_open`` when cooldown has elapsed, before the probe runs
- keep naive ``state=open`` reports from listing a probe-ready kernel as dead
- leave breakers ``open`` until cooldown actually elapses
"""

from __future__ import annotations

import json
import tempfile
from datetime import timedelta
from pathlib import Path
from typing import Any

from blackhole_agent.capability_compounder import (
    Capability,
    default_ledger_path,
    legacy_pipeline_was_used,
    load_ledger,
    register_capability,
    save_ledger,
    utc_now_iso,
)
from blackhole_agent.kernel_health import (
    LOCAL_KERNEL,
    KernelHealth,
    _utc_now,
    breaker_status,
    kernel_health_report,
    kernel_health_snapshot,
    kernel_is_available,
    load_kernel_health,
    mark_kernel_success,
    persist_half_open_kernel_health,
    recorded_kernel_state,
    recorded_open_kernels,
    refresh_kernel_breakers,
    save_kernel_health,
    trip_kernel,
)
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST

SCHEMA_VERSION = 1
HALF_OPEN_PERSIST_ID = "capability.kernel-half-open-persist"
REPO_ROOT = Path(__file__).resolve().parents[2]

HALF_OPEN_PERSIST_DONE_WHEN = (
    f"capability_exists:{HALF_OPEN_PERSIST_ID};"
    f"capability_proved:{HALF_OPEN_PERSIST_ID};"
    "no_skill_route"
)
HALF_OPEN_PERSIST_GOAL = (
    "Repair kernel health persistence: a peer kernel whose cooldown has elapsed "
    "still records state=open, so operators and reports treat a half-open probe as "
    "still dead."
)


def half_open_persist_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.kernel_half_open_persist import "
        "builtin_kernel_half_open_persist_proof; r=builtin_kernel_half_open_persist_proof(); "
        "assert r['ok'] and r.get('action')=='kernel_half_open_persist' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_kernel_half_open_persist_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=HALF_OPEN_PERSIST_ID,
        name="Kernel half-open health persist",
        description=(
            "When a peer kernel's cooldown elapses, recorded breaker state is "
            "persisted as half_open instead of remaining open, so operators and "
            "reports treat the window as a probe rather than a still-dead kernel."
        ),
        kind="python",
        entry="blackhole_agent.kernel_half_open_persist:builtin_kernel_half_open_persist_proof",
        proof_command=half_open_persist_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.kernel-circuit-breaker",
            "capability.kernel-decision-salvage",
        ),
        behavior_paths=(
            "src/blackhole_agent/kernel_health.py",
            "src/blackhole_agent/kernel_salvage.py",
            "src/blackhole_agent/kernel_half_open_persist.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/kernel_leftover.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A peer kernel whose cooldown has elapsed is persisted as half_open "
            "before the probe, so operators and reports no longer treat that "
            "window as still dead from a stale state=open record."
        ),
        tags=("unbound", "kernel", "resilience", "circuit-breaker", "persistence", "half-open"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260830T011301Z-d65108c8",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def _trip_and_persist(root: Path, kernel: str, *, now=None) -> KernelHealth:
    health = KernelHealth()
    trip_kernel(health, kernel, "quota_exhausted", "402", now=now)
    save_kernel_health(root, health, now=now)
    return health


def builtin_kernel_half_open_persist_proof() -> dict[str, Any]:
    """Hermetic proof: elapsed cooldown persists half-open, not still-dead open."""

    from blackhole_agent.kernel_health import empty_local_decision
    from blackhole_agent.kernel_salvage import execute_kernel_turn_with_salvage
    from blackhole_agent.unbound import KernelTurnResult

    checks: dict[str, bool] = {}
    checks["denylists_self"] = HALF_OPEN_PERSIST_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(HALF_OPEN_PERSIST_GOAL) == (
        HALF_OPEN_PERSIST_ID,
    )
    checks["schema_version"] = SCHEMA_VERSION == 1

    with tempfile.TemporaryDirectory(prefix="kernel-half-open-hole-") as tmp:
        root = Path(tmp)
        tripped_at = _utc_now()
        health = _trip_and_persist(root, "grok", now=tripped_at)
        grok = health.kernels["grok"]
        before_cooldown = tripped_at + timedelta(minutes=5)
        probe_at = tripped_at + timedelta(hours=7)

        stale = load_kernel_health(root)
        hole_report = kernel_health_report(stale, now=probe_at)
        checks["trip_records_open"] = grok.state == "open" and recorded_kernel_state(root, "grok") == "open"
        checks["still_open_before_cooldown"] = (
            recorded_kernel_state(root, "grok") == "open"
            and "grok" in recorded_open_kernels(stale)
            and not kernel_is_available(stale, "grok", now=before_cooldown)
            and breaker_status(stale.kernels["grok"], now=before_cooldown) == "open"
        )
        save_kernel_health(root, load_kernel_health(root), now=before_cooldown)
        checks["persist_before_cooldown_stays_open"] = recorded_kernel_state(root, "grok") == "open"
        checks["hole_recorded_open_after_cooldown"] = (
            recorded_kernel_state(root, "grok") == "open"
            and "grok" in recorded_open_kernels(stale)
            and breaker_status(stale.kernels["grok"], now=probe_at) == "half_open"
            and kernel_is_available(stale, "grok", now=probe_at)
        )
        checks["naive_report_treats_probe_as_dead"] = "grok" in recorded_open_kernels(stale)

        path, refreshed, changed = persist_half_open_kernel_health(root, now=probe_at)
        persisted = json.loads(path.read_text(encoding="utf-8"))
        report = kernel_health_report(refreshed, now=probe_at)
        snapshot = kernel_health_snapshot(root, now=probe_at, persist=True)
        checks["persist_writes_half_open"] = (
            "grok" in changed
            and refreshed.kernels["grok"].state == "half_open"
            and persisted["kernels"]["grok"]["state"] == "half_open"
            and recorded_kernel_state(root, "grok") == "half_open"
        )
        checks["report_does_not_treat_half_open_as_dead"] = (
            "grok" not in recorded_open_kernels(refreshed)
            and "grok" in report["half_open"]
            and "grok" not in report["dead"]
            and report["kernels"]["grok"]["available"] is True
            and report["kernels"]["grok"]["recorded_state"] == "half_open"
            and hole_report["kernels"]["grok"]["available"] is True
            and snapshot["kernels"]["grok"]["state"] == "half_open"
            and "grok" in snapshot["half_open"]
            and snapshot.get("persisted") is True
        )

    with tempfile.TemporaryDirectory(prefix="kernel-half-open-peer-") as tmp:
        root = Path(tmp)
        tripped_at = _utc_now()
        health = KernelHealth()
        trip_kernel(health, "kimi", "quota_exhausted", "402", now=tripped_at)
        trip_kernel(health, "grok", "auth_failed", "401", now=tripped_at)
        save_kernel_health(root, health, now=tripped_at)
        probe_at = tripped_at + timedelta(hours=7)
        persist_half_open_kernel_health(root, now=probe_at)
        peer_report = kernel_health_report(load_kernel_health(root), now=probe_at)
        checks["peer_kimi_persists_half_open"] = (
            recorded_kernel_state(root, "kimi") == "half_open"
            and recorded_kernel_state(root, "grok") == "half_open"
            and "kimi" in peer_report["half_open"]
            and "grok" in peer_report["half_open"]
            and not peer_report["dead"]
        )
        mark_kernel_success(health, "kimi", now=probe_at)
        save_kernel_health(root, health, now=probe_at)
        checks["success_closes_after_half_open"] = (
            recorded_kernel_state(root, "kimi") == "closed"
            and kernel_is_available(load_kernel_health(root), "kimi")
        )

    with tempfile.TemporaryDirectory(prefix="kernel-half-open-probe-") as tmp:
        root = Path(tmp)
        tripped_at = _utc_now()
        health = _trip_and_persist(root, "grok", now=tripped_at)
        probe_at = tripped_at + timedelta(hours=7)
        seen: list[str] = []

        class _State:
            def __init__(self) -> None:
                self.kernel = "grok"
                self.session_id = "sess"
                self.session_started = True
                self.repo_path = str(root)
                self.workspace_path = str(root)
                self.goal = HALF_OPEN_PERSIST_GOAL
                self.done_when = HALF_OPEN_PERSIST_DONE_WHEN

        def runner(state: Any, prompt: str, turn_dir: Path, **kwargs: Any) -> Any:
            seen.append(recorded_kernel_state(root, "grok"))
            return KernelTurnResult(
                kernel=state.kernel,
                last_message=json.dumps(
                    empty_local_decision(status="continue", summary=f"{state.kernel} probed")
                ),
                session_id="peer",
                command=(state.kernel,),
                result_path="",
            )

        state = _State()
        execute_kernel_turn_with_salvage(
            state,
            "prompt",
            root / "turn-probe",
            kernel_runner=runner,
            installed_kernels={"grok", "kimi"},
            health=health,
            now=probe_at,
            persist_health=True,
        )
        checks["salvage_records_half_open_before_probe"] = seen == ["half_open"]
        checks["probe_success_closes"] = recorded_kernel_state(root, "grok") == "closed"
        checks["local_stays_available"] = kernel_is_available(health, LOCAL_KERNEL)

    from blackhole_agent.kernel_genesis_diversify import DIVERSITY_CATALOG

    checks["refresh_is_idempotent"] = refresh_kernel_breakers(KernelHealth()) == ()
    checks["catalog_names_half_open"] = DIVERSITY_CATALOG[2]["id"] == HALF_OPEN_PERSIST_ID
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_kernel_half_open_persist_capability()
    return {
        "ok": ok,
        "action": "kernel_half_open_persist",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": HALF_OPEN_PERSIST_GOAL,
        "done_when": HALF_OPEN_PERSIST_DONE_WHEN,
    }
