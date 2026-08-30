"""Durable kernel circuit breaker and local last-resort capability kernel.

The harvested 2026-08-16 Grok 402 storm retried a dead kernel for twelve
turns. Decision salvage records a structured turn, but without memory the
next turn (and the next mission) still invokes the same exhausted kernel.

This module persists non-retryable kernel deaths (quota/auth), skips
open-circuit kernels on later resolution, and failsover to a local
capability kernel that still emits a structured Unbound decision so the
mission does not block or burn turns.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

LOCAL_KERNEL = "local"
HEALTH_RELATIVE = Path(".blackhole-agent") / "unbound" / "kernel-health.json"
CLI_FAILOVER_ORDER = ("codex", "kimi", "grok")
FAILOVER_ORDER = (*CLI_FAILOVER_ORDER, LOCAL_KERNEL)
TRIP_CLASSES = frozenset({"quota_exhausted", "auth_failed"})
DEFAULT_COOLDOWN_SECONDS = {
    "quota_exhausted": 6 * 3600,
    "auth_failed": 3600,
}
DEFAULT_COOLDOWN_FALLBACK = 1800
MAX_COOLDOWN_SECONDS = 24 * 3600
SCHEMA_VERSION = 1


def _utc_now(now: datetime | None = None) -> datetime:
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def _iso(moment: datetime) -> str:
    return _utc_now(moment).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(value: str) -> datetime | None:
    text = (value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


@dataclass
class KernelBreaker:
    state: str = "closed"
    class_id: str = ""
    tripped_at: str = ""
    cooldown_until: str = ""
    trip_count: int = 0
    last_evidence: str = ""
    last_success_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any] | None) -> "KernelBreaker":
        payload = payload or {}
        return cls(
            state=str(payload.get("state") or "closed"),
            class_id=str(payload.get("class_id") or ""),
            tripped_at=str(payload.get("tripped_at") or ""),
            cooldown_until=str(payload.get("cooldown_until") or ""),
            trip_count=int(payload.get("trip_count") or 0),
            last_evidence=str(payload.get("last_evidence") or ""),
            last_success_at=str(payload.get("last_success_at") or ""),
        )


@dataclass
class KernelHealth:
    schema_version: int = SCHEMA_VERSION
    updated_at: str = ""
    kernels: dict[str, KernelBreaker] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "updated_at": self.updated_at,
            "kernels": {name: breaker.to_dict() for name, breaker in sorted(self.kernels.items())},
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any] | None) -> "KernelHealth":
        payload = payload or {}
        raw = payload.get("kernels") if isinstance(payload.get("kernels"), Mapping) else {}
        return cls(
            schema_version=int(payload.get("schema_version") or SCHEMA_VERSION),
            updated_at=str(payload.get("updated_at") or ""),
            kernels={
                str(name): KernelBreaker.from_dict(value if isinstance(value, Mapping) else {})
                for name, value in raw.items()
            },
        )


def health_path(repo_path: Path) -> Path:
    return Path(repo_path) / HEALTH_RELATIVE


def load_kernel_health(repo_path: Path) -> KernelHealth:
    path = health_path(repo_path)
    if not path.is_file():
        return KernelHealth()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return KernelHealth()
    return KernelHealth.from_dict(payload if isinstance(payload, Mapping) else {})


def save_kernel_health(repo_path: Path, health: KernelHealth, *, now: datetime | None = None) -> Path:
    refresh_kernel_breakers(health, now=now)
    path = health_path(repo_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    health.updated_at = _iso(_utc_now(now))
    path.write_text(json.dumps(health.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def breaker_status(breaker: KernelBreaker | None, *, now: datetime | None = None) -> str:
    if breaker is None or breaker.state in {"", "closed"}:
        return "closed"
    if breaker.state != "open":
        return breaker.state
    until = _parse_iso(breaker.cooldown_until)
    if until is not None and _utc_now(now) >= until:
        return "half_open"
    return "open"


def refresh_kernel_breakers(health: KernelHealth, *, now: datetime | None = None) -> tuple[str, ...]:
    """Write computed breaker status into recorded ``state`` fields."""

    moment = _utc_now(now)
    changed: list[str] = []
    for name, breaker in health.kernels.items():
        status = breaker_status(breaker, now=moment)
        if breaker.state != status:
            breaker.state = status
            changed.append(name)
    if changed:
        health.updated_at = _iso(moment)
    return tuple(changed)


def recorded_kernel_state(repo_path: Path, kernel: str) -> str:
    """Return the raw persisted ``state`` field operators read from disk."""

    path = health_path(repo_path)
    if not path.is_file():
        return ""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(payload, Mapping):
        return ""
    raw = payload.get("kernels") if isinstance(payload.get("kernels"), Mapping) else {}
    row = raw.get(kernel) if isinstance(raw.get(kernel), Mapping) else {}
    return str(row.get("state") or "")


def recorded_open_kernels(health: KernelHealth) -> list[str]:
    """Kernels a naive operator report treats as dead from recorded ``state``."""

    return [name for name, breaker in sorted(health.kernels.items()) if breaker.state == "open"]


def kernel_health_report(health: KernelHealth, *, now: datetime | None = None) -> dict[str, Any]:
    """Operator snapshot: half-open probes are probe-ready, not still dead."""

    moment = _utc_now(now)
    kernels: dict[str, dict[str, Any]] = {}
    dead: list[str] = []
    half_open: list[str] = []
    ready: list[str] = []
    for name, breaker in sorted(health.kernels.items()):
        status = breaker_status(breaker, now=moment)
        available = name == LOCAL_KERNEL or status in {"closed", "half_open"}
        kernels[name] = {
            "state": status,
            "recorded_state": breaker.state,
            "class_id": breaker.class_id,
            "cooldown_until": breaker.cooldown_until,
            "trip_count": breaker.trip_count,
            "available": available,
        }
        if status == "open":
            dead.append(name)
        elif status == "half_open":
            half_open.append(name)
        else:
            ready.append(name)
    return {
        "updated_at": health.updated_at,
        "kernels": kernels,
        "dead": dead,
        "half_open": half_open,
        "ready": ready,
    }


def persist_half_open_kernel_health(
    repo_path: Path,
    health: KernelHealth | None = None,
    *,
    now: datetime | None = None,
) -> tuple[Path, KernelHealth, tuple[str, ...]]:
    """Persist computed half-open status so the on-disk record is not still open."""

    live = health if health is not None else load_kernel_health(repo_path)
    changed = refresh_kernel_breakers(live, now=now)
    path = save_kernel_health(repo_path, live, now=now)
    return path, live, changed


def kernel_health_snapshot(
    repo_path: Path,
    *,
    now: datetime | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """Load, refresh, optionally persist, and report kernel health."""

    health = load_kernel_health(repo_path)
    changed = refresh_kernel_breakers(health, now=now)
    if persist:
        save_kernel_health(repo_path, health, now=now)
    report = kernel_health_report(health, now=now)
    report["persisted"] = persist
    report["state_changes"] = list(changed)
    report["path"] = str(health_path(repo_path))
    return report


def kernel_is_available(health: KernelHealth, kernel: str, *, now: datetime | None = None) -> bool:
    if kernel == LOCAL_KERNEL:
        return True
    return breaker_status(health.kernels.get(kernel), now=now) in {"closed", "half_open"}


def cooldown_seconds(class_id: str, trip_count: int) -> int:
    base = DEFAULT_COOLDOWN_SECONDS.get(class_id, DEFAULT_COOLDOWN_FALLBACK)
    scaled = base * max(1, trip_count)
    return min(MAX_COOLDOWN_SECONDS, scaled)


def trip_kernel(
    health: KernelHealth,
    kernel: str,
    class_id: str,
    evidence: str = "",
    *,
    now: datetime | None = None,
) -> KernelBreaker:
    if kernel == LOCAL_KERNEL:
        return health.kernels.get(kernel) or KernelBreaker()
    moment = _utc_now(now)
    current = health.kernels.get(kernel) or KernelBreaker()
    current.trip_count = int(current.trip_count) + 1
    current.state = "open"
    current.class_id = class_id
    current.tripped_at = _iso(moment)
    current.cooldown_until = _iso(moment + timedelta(seconds=cooldown_seconds(class_id, current.trip_count)))
    current.last_evidence = (evidence or "")[:400]
    health.kernels[kernel] = current
    health.updated_at = _iso(moment)
    return current


def mark_kernel_success(
    health: KernelHealth,
    kernel: str,
    *,
    now: datetime | None = None,
) -> KernelBreaker:
    moment = _utc_now(now)
    current = health.kernels.get(kernel) or KernelBreaker()
    current.state = "closed"
    current.class_id = ""
    current.cooldown_until = ""
    current.last_success_at = _iso(moment)
    health.kernels[kernel] = current
    health.updated_at = _iso(moment)
    return current


def apply_health_reroute(
    requested: str,
    health: KernelHealth,
    installed: Iterable[str] = (),
    *,
    now: datetime | None = None,
) -> str:
    """Skip an open-circuit requested kernel; local is always a last resort."""

    present = {name for name in installed if name}
    present.add(LOCAL_KERNEL)
    if requested and requested != "auto" and kernel_is_available(health, requested, now=now):
        if requested == LOCAL_KERNEL or requested in present or requested in CLI_FAILOVER_ORDER:
            return requested
    for name in FAILOVER_ORDER:
        if name not in present and name != LOCAL_KERNEL:
            continue
        if name == requested:
            continue
        if kernel_is_available(health, name, now=now):
            return name
    return LOCAL_KERNEL


def empty_local_decision(**overrides: Any) -> dict[str, Any]:
    payload = {
        "status": "continue",
        "summary": "",
        "strategy": "",
        "next_step": "",
        "capability_delta": "",
        "outcome_evidence": [],
        "validation": [],
        "done_when_met": False,
        "commit_message": "",
        "mission_goal": "",
        "done_when": "",
    }
    payload.update(overrides)
    return payload


def default_local_capability_tick(state: Any, workspace: Path) -> dict[str, Any]:
    """Bind a mission and execute a local campaign; never stall if a worker cannot load."""

    try:
        from blackhole_agent.local_mission_sovereignty import local_mission_tick

        return dict(local_mission_tick(state, workspace) or {})
    except Exception:
        try:
            from blackhole_agent.local_capability_kernel import local_capability_tick

            return dict(local_capability_tick(state, workspace) or {})
        except Exception as error:  # noqa: BLE001 - failover tick must still emit a decision
            repo_value = getattr(state, "repo_path", None) or workspace
            health = load_kernel_health(Path(repo_value))
            open_kernels = [
                name
                for name, breaker in sorted(health.kernels.items())
                if breaker_status(breaker) == "open"
            ]
            return {
                "ok": True,
                "status": "continue",
                "summary": (
                    f"Local capability kernel tick failed ({error}); "
                    "recorded a structured continue so the mission does not stall."
                ),
                "strategy": "Work locally while open-circuit first-class kernels cool down.",
                "next_step": "Resume on a healthy first-class kernel when a breaker closes.",
                "outcome_evidence": [f"open_circuit={open_kernels}", str(error)[:400]],
                "capability_delta": "",
            }


def invoke_local_kernel(
    state: Any,
    prompt: str,
    turn_dir: Path,
    *,
    action: Callable[[Any, Path], Mapping[str, Any]] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Produce a structured Unbound decision without a first-class CLI kernel."""

    workspace = Path(
        getattr(state, "workspace_path", "")
        or getattr(state, "repo_path", "")
        or turn_dir
    )
    kernel_dir = Path(turn_dir) / "kernel"
    kernel_dir.mkdir(parents=True, exist_ok=True)
    tick = action or default_local_capability_tick
    try:
        report = dict(tick(state, workspace) or {})
    except Exception as error:  # noqa: BLE001 - local kernel must still emit a decision
        report = {
            "ok": False,
            "summary": f"Local capability tick failed ({error}); recorded a structured continue.",
            "outcome_evidence": [str(error)[:400]],
        }
    decision = empty_local_decision(
        status=str(report.get("status") or "continue"),
        summary=str(
            report.get("summary")
            or "Local capability kernel produced a structured decision after first-class kernels were unavailable."
        ),
        strategy=str(report.get("strategy") or "Continue via the local capability kernel."),
        next_step=str(report.get("next_step") or "Resume on a healthy first-class kernel when a breaker closes."),
        capability_delta=str(report.get("capability_delta") or ""),
        outcome_evidence=list(report.get("outcome_evidence") or []),
        mission_goal=str(report.get("mission_goal") or getattr(state, "goal", "") or ""),
        done_when=str(report.get("done_when") or getattr(state, "done_when", "") or ""),
        done_when_met=bool(report.get("done_when_met")),
    )
    last_message = json.dumps(decision)
    result_path = kernel_dir / "latest-local-run.json"
    payload = {
        "kernel": LOCAL_KERNEL,
        "returncode": 0,
        "timed_out": False,
        "last_message": last_message,
        "prompt_chars": len(prompt or ""),
        "report": report,
        "finished_at": _iso(_utc_now(now)),
    }
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    result_path.write_text(text, encoding="utf-8")
    last_message_path = kernel_dir / "latest-local-last-message.md"
    last_message_path.write_text(last_message, encoding="utf-8")
    return {
        "kernel": LOCAL_KERNEL,
        "last_message": last_message,
        "session_id": str(getattr(state, "session_id", "") or "local"),
        "command": ("local-capability-kernel",),
        "result_path": str(result_path),
        "report": report,
        "decision": decision,
    }


def builtin_kernel_circuit_breaker_proof() -> dict[str, Any]:
    """Hermetic proof: the harvested 402 storm cannot retry a dead Grok."""

    import tempfile

    from blackhole_agent.kernel_salvage import (
        HARVESTED_GROK_402,
        classify_kernel_failure,
        classify_run_artifact,
        execute_kernel_turn_with_salvage,
        salvage_kernel_failure,
    )
    from blackhole_agent.pattern_register import classify_unbound_turn
    from blackhole_agent.unbound import KernelTurnResult, TurnDecision

    checks: dict[str, bool] = {}
    harvested = classify_run_artifact(HARVESTED_GROK_402, error="Grok CLI failed with exit code 1")
    checks["harvested_402"] = harvested.class_id == "quota_exhausted" and not harvested.retryable

    health = KernelHealth()
    trip_kernel(health, "grok", harvested.class_id, harvested.evidence)
    checks["trips_grok"] = (
        breaker_status(health.kernels["grok"]) == "open" and not kernel_is_available(health, "grok")
    )
    checks["reroutes_to_local"] = apply_health_reroute("grok", health, installed=()) == LOCAL_KERNEL
    checks["reroutes_to_peer"] = (
        apply_health_reroute("grok", health, installed={"kimi", "grok"}) == "kimi"
    )
    checks["local_always_available"] = kernel_is_available(health, LOCAL_KERNEL)

    timeout = classify_kernel_failure(timed_out=True, error="Timed out after 30 seconds.")
    timeout_health = KernelHealth()
    if timeout.class_id not in TRIP_CLASSES:
        pass
    else:
        trip_kernel(timeout_health, "grok", timeout.class_id)
    checks["timeout_does_not_trip"] = timeout.class_id not in TRIP_CLASSES and not timeout_health.kernels

    closed = salvage_kernel_failure(
        error="Grok CLI failed with exit code 1",
        current_kernel="grok",
        artifact=HARVESTED_GROK_402,
        installed_kernels=set(),
        allow_failover=False,
    )
    checks["blocks_when_failover_disabled"] = (
        closed.decision["status"] == "blocked" and closed.class_id == "quota_exhausted"
    )

    local = salvage_kernel_failure(
        error="Grok CLI failed with exit code 1",
        current_kernel="grok",
        artifact=HARVESTED_GROK_402,
        installed_kernels=set(),
    )
    checks["failsover_to_local"] = (
        local.failover_kernel == LOCAL_KERNEL and local.decision["status"] == "continue"
    )

    events = classify_unbound_turn(
        {
            "iteration": 13,
            "effective_status": "continue",
            "requested_status": "continue",
            "summary": local.decision["summary"],
            "kernel_salvage": local.to_dict(),
        }
    )
    checks["not_kernel_turn_failed"] = not any(
        item.get("class_id") == "kernel_turn_failed" for item in events
    )

    class _State:
        def __init__(self, repo: Path) -> None:
            self.kernel = "grok"
            self.session_id = "sess"
            self.session_started = True
            self.repo_path = str(repo)
            self.workspace_path = str(repo)
            self.goal = "Keep growing after a 402."
            self.done_when = "A structured decision is recorded."

    with tempfile.TemporaryDirectory(prefix="kernel-health-") as tmp:
        repo = Path(tmp)
        storm_health = KernelHealth()
        calls: list[str] = []
        resulting: list[str] = []

        def runner(state: Any, prompt: str, turn_dir: Path, **kwargs: Any) -> Any:
            calls.append(state.kernel)
            if state.kernel == "grok":
                kernel_dir = Path(turn_dir) / "kernel"
                kernel_dir.mkdir(parents=True, exist_ok=True)
                (kernel_dir / "latest-grok-run.json").write_text(
                    json.dumps(HARVESTED_GROK_402),
                    encoding="utf-8",
                )
                raise RuntimeError(
                    "Grok CLI failed with exit code 1; Payment Required usage balance exhausted"
                )
            return KernelTurnResult(
                kernel=state.kernel,
                last_message=json.dumps(
                    empty_local_decision(status="continue", summary=f"{state.kernel} ran")
                ),
                session_id="peer",
                command=(state.kernel,),
                result_path="",
            )

        for index in range(12):
            state = _State(repo)
            execute_kernel_turn_with_salvage(
                state,
                "prompt",
                repo / f"turn-{index:02d}",
                kernel_runner=runner,
                installed_kernels=set(),
                health=storm_health,
                persist_health=True,
            )
            resulting.append(state.kernel)
        checks["storm_invokes_grok_once"] = calls == ["grok"]
        checks["storm_finishes_on_local"] = resulting == [LOCAL_KERNEL] * 12
        persisted = load_kernel_health(repo)
        checks["storm_persists_open_breaker"] = breaker_status(persisted.kernels.get("grok")) == "open"

        probe_at = _utc_now() + timedelta(hours=7)
        checks["half_open_after_cooldown"] = kernel_is_available(persisted, "grok", now=probe_at)
        checks["still_open_before_cooldown"] = not kernel_is_available(persisted, "grok")

        mark_kernel_success(persisted, "grok")
        checks["success_closes_breaker"] = kernel_is_available(persisted, "grok")

        live_state = _State(repo)
        result, decision, meta = execute_kernel_turn_with_salvage(
            live_state,
            "prompt",
            repo / "live",
            kernel_runner=runner,
            installed_kernels=set(),
            health=KernelHealth(),
            persist_health=False,
        )
        checks["execute_failsover_to_local"] = (
            isinstance(decision, TurnDecision)
            and decision.status == "continue"
            and live_state.kernel == LOCAL_KERNEL
            and meta.get("source") == "failover"
            and bool(result.last_message)
        )

    ok = all(checks.values())
    return {
        "ok": ok,
        "action": "kernel_circuit_breaker",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "used_skill_route_discovery": False,
    }
