"""Probe half_open peer kernels so cooldown recovery cannot stall behind a healthy requested kernel.

Half-open persist records ``state=half_open`` once cooldown elapses, and the
requested kernel's mission turn is the probe for that kernel. Peer CLI
kernels recorded as half_open are never invoked while a healthy requested
kernel serves, so Codex and Kimi stay half_open forever.

This module closes that hole:

- ping half_open peers on a bounded check before the mission kernel runs
- recover a peer to closed on a healthy ping
- re-trip quota/auth deaths so cooldown starts again
- leave other ping failures half_open
- never hijack the requested mission kernel
- never ping a still-open (cooldown) kernel, the requested kernel, or local
- leave the no-ping path so the hole stays falsifiable
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from datetime import timedelta
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

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
    CLI_FAILOVER_ORDER,
    LOCAL_KERNEL,
    TRIP_CLASSES,
    KernelHealth,
    _utc_now,
    breaker_status,
    kernel_is_available,
    load_kernel_health,
    mark_kernel_success,
    recorded_kernel_state,
    refresh_kernel_breakers,
    save_kernel_health,
    trip_kernel,
)
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST

SCHEMA_VERSION = 1
HALF_OPEN_PROBE_ID = "capability.kernel-half-open-probe"
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROBE_TIMEOUT_SECONDS = 15.0

HALF_OPEN_PROBE_DONE_WHEN = (
    f"capability_exists:{HALF_OPEN_PROBE_ID};"
    f"capability_proved:{HALF_OPEN_PROBE_ID};"
    "no_skill_route"
)
HALF_OPEN_PROBE_GOAL = (
    "Repair peer kernel recovery after cooldown: a peer CLI kernel recorded as "
    "half_open is never invoked while a healthy requested kernel serves, so "
    "Codex and Kimi stay half_open forever and never recover to closed or re-trip. "
    "Ping half_open peers on a bounded check without hijacking the mission kernel."
)

PeerProbe = Callable[[str], Mapping[str, Any]]


def half_open_probe_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.kernel_half_open_probe import "
        "builtin_kernel_half_open_probe_proof; r=builtin_kernel_half_open_probe_proof(); "
        "assert r['ok'] and r.get('action')=='kernel_half_open_probe' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_kernel_half_open_probe_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=HALF_OPEN_PROBE_ID,
        name="Half-open peer kernel ping",
        description=(
            "Peer CLI kernels recorded as half_open after cooldown are pinged on "
            "a bounded check while a healthy requested kernel still serves the "
            "mission, recovering them to closed or re-tripping quota/auth "
            "without hijacking the mission kernel."
        ),
        kind="python",
        entry="blackhole_agent.kernel_half_open_probe:builtin_kernel_half_open_probe_proof",
        proof_command=half_open_probe_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.kernel-half-open-persist",
        ),
        behavior_paths=(
            "src/blackhole_agent/kernel_half_open_probe.py",
            "src/blackhole_agent/kernel_salvage.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A peer CLI kernel recorded as half_open is no longer ignored while "
            "a healthy requested kernel serves: Unbound pings half_open peers on "
            "a bounded check, recovers them to closed or re-trips quota/auth, "
            "and leaves unrecoverable peers half_open without hijacking the "
            "mission kernel."
        ),
        tags=("unbound", "kernel", "resilience", "circuit-breaker", "probe", "peer"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260831T041048Z-bf9623da",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def half_open_peer_names(
    health: KernelHealth,
    *,
    requested: str,
    installed: Iterable[str],
    now: Any = None,
) -> tuple[str, ...]:
    """Installed CLI peers that are half_open and are not the requested kernel."""

    present = {name for name in installed if name}
    names: list[str] = []
    for name in CLI_FAILOVER_ORDER:
        if name == requested or name == LOCAL_KERNEL:
            continue
        if name not in present:
            continue
        if breaker_status(health.kernels.get(name), now=now) != "half_open":
            continue
        names.append(name)
    return tuple(names)


def default_peer_kernel_probe(name: str) -> dict[str, Any]:
    """Bounded CLI ping used when a caller does not inject a probe."""

    binary = shutil.which(name)
    if not binary:
        return {"ok": False, "class_id": "missing", "evidence": f"{name} not installed"}
    try:
        proc = subprocess.run(
            [binary, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=DEFAULT_PROBE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as error:
        return {"ok": False, "class_id": "timeout", "evidence": str(error)[:400]}
    except OSError as error:
        return {"ok": False, "class_id": "cli_error", "evidence": str(error)[:400]}
    from blackhole_agent.kernel_salvage import classify_kernel_failure

    failure = classify_kernel_failure(
        returncode=int(proc.returncode or 0),
        stdout_tail=proc.stdout or "",
        stderr_tail=proc.stderr or "",
    )
    if failure.class_id in TRIP_CLASSES:
        return {"ok": False, "class_id": failure.class_id, "evidence": failure.evidence}
    if int(proc.returncode or 0) == 0:
        evidence = (proc.stdout or proc.stderr or f"{name} --version")[:400]
        return {"ok": True, "class_id": "", "evidence": evidence}
    return {"ok": False, "class_id": failure.class_id, "evidence": failure.evidence}


def apply_peer_probe_outcome(
    health: KernelHealth,
    name: str,
    outcome: Mapping[str, Any],
    *,
    now: Any = None,
) -> str:
    """Apply one ping result. Returns recovered, retripped, or left_half_open."""

    ok = bool(outcome.get("ok"))
    class_id = str(outcome.get("class_id") or "")
    evidence = str(outcome.get("evidence") or "")[:400]
    if ok:
        mark_kernel_success(health, name, now=now)
        return "recovered"
    if class_id in TRIP_CLASSES:
        trip_kernel(health, name, class_id, evidence, now=now)
        return "retripped"
    current = health.kernels.get(name)
    if current is not None and evidence:
        current.last_evidence = evidence
    return "left_half_open"


def probe_half_open_peer_kernels(
    health: KernelHealth,
    *,
    requested: str,
    installed: Iterable[str],
    probe: PeerProbe | None = None,
    now: Any = None,
    persist: Callable[[], None] | None = None,
) -> dict[str, Any]:
    """Ping half_open peers without changing the requested mission kernel."""

    refresh_kernel_breakers(health, now=now)
    ping = probe or default_peer_kernel_probe
    peers = half_open_peer_names(
        health,
        requested=requested,
        installed=installed,
        now=now,
    )
    rows: list[dict[str, Any]] = []
    recovered: list[str] = []
    retripped: list[str] = []
    left: list[str] = []
    for name in peers:
        try:
            outcome = dict(ping(name) or {})
        except Exception as error:  # noqa: BLE001 - a peer ping must not stall the mission
            outcome = {
                "ok": False,
                "class_id": "cli_error",
                "evidence": f"{type(error).__name__}: {error}"[:400],
            }
        action = apply_peer_probe_outcome(health, name, outcome, now=now)
        row = {
            "kernel": name,
            "ok": bool(outcome.get("ok")),
            "action": action,
            "class_id": str(outcome.get("class_id") or ""),
            "evidence": str(outcome.get("evidence") or "")[:400],
        }
        rows.append(row)
        if action == "recovered":
            recovered.append(name)
        elif action == "retripped":
            retripped.append(name)
        else:
            left.append(name)
    if persist is not None and rows:
        persist()
    return {
        "ok": True,
        "skipped": False,
        "requested": requested,
        "candidates": list(peers),
        "probed": rows,
        "recovered": recovered,
        "retripped": retripped,
        "left_half_open": left,
    }


def disabled_peer_probe_report(requested: str = "") -> dict[str, Any]:
    """Falsifiable no-ping path: peers stay half_open while the requested kernel serves."""

    return {
        "ok": True,
        "skipped": True,
        "reason": "disabled",
        "requested": requested,
        "candidates": [],
        "probed": [],
        "recovered": [],
        "retripped": [],
        "left_half_open": [],
    }


def _trip_and_persist(root: Path, kernel: str, *, now=None) -> KernelHealth:
    health = load_kernel_health(root)
    trip_kernel(health, kernel, "quota_exhausted", "402", now=now)
    save_kernel_health(root, health, now=now)
    return health


def _continue_runner(state: Any, prompt: str, turn_dir: Path, **kwargs: Any) -> Any:
    from blackhole_agent.kernel_health import empty_local_decision
    from blackhole_agent.unbound import KernelTurnResult

    return KernelTurnResult(
        kernel=state.kernel,
        last_message=json.dumps(
            empty_local_decision(status="continue", summary=f"{state.kernel} served")
        ),
        session_id="mission",
        command=(state.kernel,),
        result_path="",
    )


class _State:
    def __init__(self, root: Path, kernel: str = "grok") -> None:
        self.kernel = kernel
        self.session_id = "sess"
        self.session_started = True
        self.repo_path = str(root)
        self.workspace_path = str(root)
        self.goal = HALF_OPEN_PROBE_GOAL
        self.done_when = HALF_OPEN_PROBE_DONE_WHEN


def builtin_kernel_half_open_probe_proof() -> dict[str, Any]:
    """Hermetic proof: half_open peers are pinged without hijacking the mission kernel."""

    import json

    from blackhole_agent.kernel_genesis_bind import _register_proved as register_catalog_proved
    from blackhole_agent.kernel_genesis_diversify import (
        DIVERSITY_CATALOG,
        _prepare_exhausted_catalog,
        bind_gate_passing_successor,
    )
    from blackhole_agent.kernel_half_open_persist import (
        HALF_OPEN_PERSIST_GOAL,
        HALF_OPEN_PERSIST_ID,
    )
    from blackhole_agent.kernel_salvage import execute_kernel_turn_with_salvage
    from blackhole_agent.mcp_plugin_reconnect import MCP_RECONNECT_GOAL, MCP_RECONNECT_ID

    catalog = DIVERSITY_CATALOG
    checks: dict[str, bool] = {}
    checks["denylists_self"] = HALF_OPEN_PROBE_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(HALF_OPEN_PROBE_GOAL) == (
        HALF_OPEN_PROBE_ID,
    )
    checks["persist_goal_is_not_probe"] = leftover_marker_ids(HALF_OPEN_PERSIST_GOAL) == (
        HALF_OPEN_PERSIST_ID,
    )
    checks["reconnect_goal_is_not_probe"] = leftover_marker_ids(MCP_RECONNECT_GOAL) == (
        MCP_RECONNECT_ID,
    )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["catalog_names_probe"] = (
        len(catalog) > 13
        and catalog[13]["id"] == HALF_OPEN_PROBE_ID
        and catalog[12]["id"] == MCP_RECONNECT_ID
    )

    with tempfile.TemporaryDirectory(prefix="kernel-half-open-probe-hole-") as tmp:
        root = Path(tmp)
        tripped_at = _utc_now()
        probe_at = tripped_at + timedelta(hours=7)
        health = _trip_and_persist(root, "kimi", now=tripped_at)
        save_kernel_health(root, health, now=probe_at)
        naive = execute_kernel_turn_with_salvage(
            _State(root),
            "prompt",
            root / "turn-hole",
            kernel_runner=_continue_runner,
            installed_kernels={"grok", "kimi", "codex"},
            health=health,
            now=probe_at,
            persist_health=True,
            probe_peers=False,
        )
        hole_state = recorded_kernel_state(root, "kimi")
        checks["naive_leaves_peer_half_open"] = (
            hole_state == "half_open"
            and recorded_kernel_state(root, "grok") == "closed"
            and naive[2].get("peer_probe", {}).get("skipped") is True
            and naive[0].kernel == "grok"
        )
        checks["mission_kernel_unchanged_without_ping"] = naive[0].kernel == "grok"

    with tempfile.TemporaryDirectory(prefix="kernel-half-open-probe-recover-") as tmp:
        root = Path(tmp)
        tripped_at = _utc_now()
        probe_at = tripped_at + timedelta(hours=7)
        health = KernelHealth()
        trip_kernel(health, "kimi", "quota_exhausted", "402", now=tripped_at)
        trip_kernel(health, "codex", "quota_exhausted", "402", now=tripped_at)
        save_kernel_health(root, health, now=probe_at)
        pinged: list[str] = []

        def recover_or_trip(name: str) -> dict[str, Any]:
            pinged.append(name)
            if name == "kimi":
                return {"ok": True, "class_id": "", "evidence": "kimi ping ok"}
            return {
                "ok": False,
                "class_id": "quota_exhausted",
                "evidence": "codex 402",
            }

        result, _decision, meta = execute_kernel_turn_with_salvage(
            _State(root),
            "prompt",
            root / "turn-recover",
            kernel_runner=_continue_runner,
            installed_kernels={"grok", "kimi", "codex"},
            health=health,
            now=probe_at,
            persist_health=True,
            peer_probe=recover_or_trip,
        )
        report = meta.get("peer_probe") or {}
        checks["recovers_healthy_peer"] = (
            recorded_kernel_state(root, "kimi") == "closed"
            and "kimi" in report.get("recovered", [])
            and kernel_is_available(load_kernel_health(root), "kimi", now=probe_at)
        )
        checks["retrips_quota_peer"] = (
            recorded_kernel_state(root, "codex") == "open"
            and "codex" in report.get("retripped", [])
            and not kernel_is_available(load_kernel_health(root), "codex", now=probe_at)
        )
        checks["does_not_hijack_requested_kernel"] = (
            result.kernel == "grok"
            and pinged == ["codex", "kimi"]
            and report.get("requested") == "grok"
            and recorded_kernel_state(root, "grok") == "closed"
        )

    with tempfile.TemporaryDirectory(prefix="kernel-half-open-probe-leave-") as tmp:
        root = Path(tmp)
        tripped_at = _utc_now()
        probe_at = tripped_at + timedelta(hours=7)
        health = _trip_and_persist(root, "kimi", now=tripped_at)
        save_kernel_health(root, health, now=probe_at)

        def noisy_probe(name: str) -> dict[str, Any]:
            return {"ok": False, "class_id": "cli_error", "evidence": f"{name} timeout"}

        _result, _decision, meta = execute_kernel_turn_with_salvage(
            _State(root),
            "prompt",
            root / "turn-leave",
            kernel_runner=_continue_runner,
            installed_kernels={"grok", "kimi"},
            health=health,
            now=probe_at,
            persist_health=True,
            peer_probe=noisy_probe,
        )
        checks["non_trip_failure_leaves_half_open"] = (
            recorded_kernel_state(root, "kimi") == "half_open"
            and "kimi" in (meta.get("peer_probe") or {}).get("left_half_open", [])
        )

    with tempfile.TemporaryDirectory(prefix="kernel-half-open-probe-skip-") as tmp:
        root = Path(tmp)
        tripped_at = _utc_now()
        before_cooldown = tripped_at + timedelta(minutes=5)
        probe_at = tripped_at + timedelta(hours=7)
        health = KernelHealth()
        trip_kernel(health, "kimi", "quota_exhausted", "402", now=tripped_at)
        trip_kernel(health, "grok", "quota_exhausted", "402", now=tripped_at)
        save_kernel_health(root, health, now=tripped_at)
        skipped: list[str] = []

        def must_not_run(name: str) -> dict[str, Any]:
            skipped.append(name)
            return {"ok": True, "class_id": "", "evidence": name}

        open_report = probe_half_open_peer_kernels(
            health,
            requested="grok",
            installed={"grok", "kimi", "codex"},
            probe=must_not_run,
            now=before_cooldown,
        )
        checks["open_cooldown_peers_are_not_pinged"] = (
            skipped == []
            and open_report["candidates"] == []
            and breaker_status(health.kernels["kimi"], now=before_cooldown) == "open"
            and breaker_status(health.kernels["grok"], now=before_cooldown) == "open"
        )

        requested_hits: list[str] = []

        def track(name: str) -> dict[str, Any]:
            requested_hits.append(name)
            return {"ok": True, "class_id": "", "evidence": name}

        execute_kernel_turn_with_salvage(
            _State(root, kernel="grok"),
            "prompt",
            root / "turn-skip-requested",
            kernel_runner=_continue_runner,
            installed_kernels={"grok", "kimi"},
            health=health,
            now=probe_at,
            persist_health=True,
            peer_probe=track,
        )
        checks["requested_half_open_is_mission_not_peer_ping"] = (
            "grok" not in requested_hits
            and requested_hits == ["kimi"]
            and recorded_kernel_state(root, "grok") == "closed"
            and recorded_kernel_state(root, "kimi") == "closed"
        )
        checks["local_is_never_a_peer_candidate"] = LOCAL_KERNEL not in half_open_peer_names(
            health,
            requested="grok",
            installed={"local", "grok", "kimi"},
            now=probe_at,
        )

    with tempfile.TemporaryDirectory(prefix="kernel-half-open-probe-direct-") as tmp:
        root = Path(tmp)
        tripped_at = _utc_now()
        probe_at = tripped_at + timedelta(hours=7)
        health = KernelHealth()
        trip_kernel(health, "kimi", "auth_failed", "401", now=tripped_at)
        save_kernel_health(root, health, now=probe_at)
        refresh_kernel_breakers(health, now=probe_at)
        direct = probe_half_open_peer_kernels(
            health,
            requested="grok",
            installed={"grok", "kimi"},
            probe=lambda name: {"ok": True, "class_id": "", "evidence": name},
            now=probe_at,
        )
        checks["direct_probe_recovers_peer"] = (
            health.kernels["kimi"].state == "closed"
            and direct["recovered"] == ["kimi"]
            and direct["requested"] == "grok"
        )
        empty = probe_half_open_peer_kernels(
            KernelHealth(),
            requested="grok",
            installed={"grok", "kimi"},
            probe=lambda name: (_ for _ in ()).throw(AssertionError("closed peers must not ping")),
            now=probe_at,
        )
        checks["closed_peers_are_not_pinged"] = empty["probed"] == [] and empty["candidates"] == []
        missing = default_peer_kernel_probe("not-a-real-kernel-bin")
        checks["missing_binary_does_not_trip"] = (
            missing.get("ok") is False and missing.get("class_id") == "missing"
        )

    with tempfile.TemporaryDirectory(prefix="kernel-half-open-probe-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != HALF_OPEN_PROBE_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_probe"] = (
        live_goal == HALF_OPEN_PROBE_GOAL
        and HALF_OPEN_PROBE_ID in live_done
        and live_source == "genesis_bind_half_open_probe"
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()
    checks["disabled_report_is_skipped"] = disabled_peer_probe_report("grok")["skipped"] is True

    ok = all(checks.values())
    if ok:
        ensure_kernel_half_open_probe_capability()
    return {
        "ok": ok,
        "action": "kernel_half_open_probe",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": HALF_OPEN_PROBE_GOAL,
        "done_when": HALF_OPEN_PROBE_DONE_WHEN,
        "disabled_report": disabled_peer_probe_report("grok"),
        "trace": json.dumps(sorted(name for name, passed in checks.items() if passed)),
    }
