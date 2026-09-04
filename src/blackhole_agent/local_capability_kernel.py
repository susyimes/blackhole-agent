"""Sovereign local capability kernel.

The harvested 2026-08-16 Grok 402 dies before a model decision. Salvage and
the circuit breaker already fail over here so the mission does not stall.
This module is the missing worker: it loads the durable ledger, selects a
cheap proved python capability, invokes it in-process, and emits a structured
Unbound decision with capability_delta and outcome evidence.

A quota-exhausted first-class kernel therefore produces capability progress
instead of a no-op continue stub.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from blackhole_agent.capability_compounder import (
    ACTIVE_CAPABILITY_ENV,
    Capability,
    CapabilityLedger,
    default_ledger_path,
    legacy_pipeline_was_used,
    load_ledger,
    plan_capability_program,
    run_python_entry_inprocess,
)
from blackhole_agent.kernel_health import LOCAL_KERNEL, empty_local_decision

SCHEMA_VERSION = 1
TICK_RELATIVE = Path(".blackhole-agent") / "unbound" / "local-kernel.json"
MAX_STEPS_PER_TICK = 1
ROTATION_MEMORY = 4

PREFERRED_LOCAL_IDS = (
    "capability.ledger-inventory",
    "repo.import-health",
    "unbound.milestone-gate",
)

# Recursive or unbounded entries must never run inside a failover tick.
LOCAL_DENYLIST = frozenset(
    {
        "capability.local-capability-kernel",
        "capability.local-mission-sovereignty",
        "capability.kernel-resume",
        "capability.kernel-succession",
        "capability.kernel-mission-plane",
        "capability.kernel-finality",
        "capability.kernel-leftover",
        "capability.leftover-lineage-plane",
        "capability.leftover-catalog-handoff",
        "capability.worktree-gc-resilience",
        "capability.kernel-class-closure",
        "capability.kernel-unscoped-resume",
        "capability.kernel-genesis-bind",
        "capability.kernel-genesis-diversify",
        "capability.kernel-mission-memory",
        "capability.kernel-half-open-persist",
        "capability.mcp-handshake-isolation",
        "capability.mcp-call-isolation",
        "capability.mcp-reverse-channel",
        "capability.mcp-http-transport",
        "capability.mcp-http-event-stream",
        "capability.publication-resilience",
        "capability.browser-actuation",
        "capability.browser-cdp-actuation",
        "capability.gmail-actuation",
        "capability.godot-actuation",
        "capability.github-actuation",
        "capability.sqlite-actuation",
        "capability.webhook-actuation",
        "capability.mcp-progress",
        "capability.mcp-tools-list-changed",
        "capability.smtp-actuation",
        "capability.mcp-http-auth",
        "capability.imap-actuation",
        "capability.redis-actuation",
        "capability.mqtt-actuation",
        "capability.dns-actuation",
        "capability.ldap-actuation",
        "capability.postgres-actuation",
        "capability.s3-actuation",
        "capability.watch-actuation",
        "capability.mcp-cursor-pagination",
        "capability.mcp-structured-output",
        "capability.websocket-actuation",
        "capability.ssh-actuation",
        "capability.grpc-actuation",
        "capability.amqp-actuation",
        "capability.ftp-actuation",
        "capability.tftp-actuation",
        "capability.snmp-actuation",
        "capability.syslog-actuation",
        "capability.ntp-actuation",
        "capability.radius-actuation",
        "capability.dhcp-actuation",
        "capability.ike-actuation",
        "capability.sip-actuation",
        "capability.stun-actuation",
        "capability.turn-actuation",
        "capability.ice-actuation",
        "capability.dtls-actuation",
        "capability.srtp-actuation",
        "capability.sctp-actuation",
        "capability.datachannel-actuation",
        "capability.quic-actuation",
        "capability.http3-actuation",
        "capability.webtransport-actuation",
        "capability.datagram-actuation",
        "capability.masque-actuation",
        "capability.connectip-actuation",
        "capability.ohttp-actuation",
        "capability.ohsvcb-actuation",
        "capability.httpsig-actuation",
        "capability.digestfields-actuation",
        "capability.bhttp-actuation",
        "capability.http11-actuation",
        "capability.http2-actuation",
        "capability.httpcache-actuation",
        "capability.httpsemantics-actuation",
        "capability.structuredfields-actuation",
        "capability.clienthints-actuation",
        "capability.earlyhints-actuation",
        "capability.encryptedcontent-actuation",
        "capability.altsvc-actuation",
        "capability.hsts-actuation",
        "capability.hpkp-actuation",
        "capability.expectct-actuation",
        "capability.xfo-actuation",
        "capability.weborigin-actuation",
        "capability.httpcookie-actuation",
        "capability.contentdisposition-actuation",
        "capability.weblinking-actuation",
        "capability.mcp-plugin-reconnect",
        "capability.kernel-half-open-probe",
        "capability.mcp-sampling",
        "capability.mcp-resources",
        "capability.mcp-prompts",
        "capability.mcp-completions",
        "capability.mcp-logging",
        "capability.mcp-elicitation",
        "capability.mcp-cancellation",
        "capability.mcp-resource-subscribe",
        "capability.mcp-roots-list-changed",
        "capability.kernel-consumed-growth",
        "capability.kernel-compound-loop",
        "capability.kernel-primitive-compose",
        "capability.kernel-composed-program",
        "capability.kernel-program-stack",
        "capability.kernel-program-tower",
        "capability.kernel-program-lattice",
        "capability.kernel-program-fabric",
        "capability.kernel-program-weave",
        "capability.milestone-commit-resilience",
        "capability.validation-replay-resilience",
        "capability.kernel-circuit-breaker",
        "capability.kernel-decision-salvage",
        "capability.mission-plane",
        "capability.program-run",
        "capability.goal-plan",
        "capability.adaptive-grow",
        "capability.autonomic-cycle",
        "capability.growth-loop",
        "capability.second-wave-absorb",
        "capability.outcome-contract",
        "capability.contract-plane",
        "capability.ablation-proof",
        "capability.transfer-plane",
        "capability.adversarial-contract",
        "capability.assurance-plane",
        "capability.sovereignty-plane",
        "capability.lineage-plane",
        "capability.reconciliation-plane",
        "capability.continuity-plane",
        "capability.federation-plane",
        "capability.quorum-plane",
        "capability.finality-plane",
        "capability.execution-plane",
        "capability.actuation-plane",
        "capability.ledger-integrity",
        "capability.distill-ledger",
        "capability.repair-plane",
        "capability.foraging-plane",
        "capability.acquisition-plane",
        "capability.absorption-plane",
    }
)

_EXPENSIVE_MARKERS = ("-plane", "growth-loop", "adaptive", "autonomic", "integrity")


@dataclass
class LocalTickRecord:
    schema_version: int = SCHEMA_VERSION
    updated_at: str = ""
    tick_count: int = 0
    last_ids: list[str] = field(default_factory=list)
    last_ok: bool = False
    last_summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any] | None) -> "LocalTickRecord":
        payload = payload or {}
        raw_ids = payload.get("last_ids") or []
        return cls(
            schema_version=int(payload.get("schema_version") or SCHEMA_VERSION),
            updated_at=str(payload.get("updated_at") or ""),
            tick_count=int(payload.get("tick_count") or 0),
            last_ids=[str(item) for item in raw_ids if str(item).strip()],
            last_ok=bool(payload.get("last_ok")),
            last_summary=str(payload.get("last_summary") or ""),
        )


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def resolve_tick_root(state: Any, workspace: Path) -> Path:
    """Prefer a checkout that actually has a capability ledger."""

    candidates = [
        Path(workspace) if workspace else None,
        Path(getattr(state, "workspace_path", "") or ""),
        Path(getattr(state, "repo_path", "") or ""),
    ]
    for candidate in candidates:
        if candidate and (candidate / "capabilities" / "ledger.json").is_file():
            return candidate
    for candidate in candidates:
        if candidate and str(candidate):
            return candidate
    return Path(workspace)


def tick_record_path(root: Path) -> Path:
    return Path(root) / TICK_RELATIVE


def load_tick_record(root: Path) -> LocalTickRecord:
    path = tick_record_path(root)
    if not path.is_file():
        return LocalTickRecord()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return LocalTickRecord()
    return LocalTickRecord.from_dict(payload if isinstance(payload, Mapping) else {})


def save_tick_record(root: Path, record: LocalTickRecord) -> Path:
    path = tick_record_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    record.updated_at = _utc_now()
    path.write_text(json.dumps(record.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def is_safe_local_capability(capability: Capability) -> bool:
    if capability.id in LOCAL_DENYLIST:
        return False
    if capability.kind != "python" or ":" not in (capability.entry or ""):
        return False
    if any(marker in capability.id for marker in _EXPENSIVE_MARKERS):
        return False
    if capability.id.startswith("capability.fixture-local-"):
        return True
    if capability.id in PREFERRED_LOCAL_IDS:
        return True
    # Failover ticks stay on bootstrap leaves; composed planes stay denied.
    return "bootstrap" in capability.tags


def select_local_program(
    ledger: CapabilityLedger,
    *,
    goal: str = "",
    skip_ids: tuple[str, ...] = (),
    max_steps: int = MAX_STEPS_PER_TICK,
) -> list[str]:
    """Pick a cheap, rotating, proved-when-possible python program."""

    skipped = {item for item in skip_ids if item}
    safe = {
        item.id: item
        for item in ledger.capabilities.values()
        if is_safe_local_capability(item)
    }
    if not safe:
        return []

    ranked: list[str] = []
    for capability_id in PREFERRED_LOCAL_IDS:
        if capability_id in safe and capability_id not in ranked:
            ranked.append(capability_id)
    planned = plan_capability_program(ledger, goal or "", max_steps=max(3, max_steps))
    for capability_id in list(planned.get("steps") or []):
        if capability_id in safe and capability_id not in ranked:
            ranked.append(capability_id)
    proved = sorted(
        item_id
        for item_id, item in safe.items()
        if item.last_proof_exit_code == 0 and item_id not in ranked
    )
    ranked.extend(proved)
    ranked.extend(sorted(item_id for item_id in safe if item_id not in ranked))

    rotated = [item_id for item_id in ranked if item_id not in skipped]
    pool = rotated or ranked
    return pool[: max(1, int(max_steps))]


def invoke_local_capability(capability: Capability) -> dict[str, Any]:
    result = run_python_entry_inprocess(
        capability.entry,
        env={ACTIVE_CAPABILITY_ENV: capability.id},
    )
    return {
        "capability_id": capability.id,
        "ok": bool(result.ok),
        "exit_code": int(result.exit_code),
        "kind": result.kind,
        "summary": result.summary,
        "entry": capability.entry,
    }


def load_tick_ledger(root: Path) -> CapabilityLedger | None:
    path = default_ledger_path(root)
    if not path.is_file():
        return None
    try:
        return load_ledger(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def _decision_fields(
    *,
    invoked: list[dict[str, Any]],
    root: Path,
    goal: str,
    done_when: str,
    ledger_count: int,
    reason: str,
) -> dict[str, Any]:
    passed = [item["capability_id"] for item in invoked if item.get("ok")]
    failed = [item["capability_id"] for item in invoked if not item.get("ok")]
    evidence = [
        f"root={root}",
        f"ledger_count={ledger_count}",
        f"invoked_count={len(invoked)}",
        f"reason={reason}",
    ]
    evidence.extend(f"invoked={item['capability_id']}:ok={item.get('ok')}" for item in invoked)
    if passed:
        delta = (
            "Local capability kernel invoked "
            + ", ".join(passed)
            + " in-process after first-class kernels were unavailable."
        )
        summary = (
            f"Local capability kernel executed {', '.join(passed)} without a first-class CLI kernel."
        )
    elif invoked:
        delta = ""
        summary = (
            "Local capability kernel invoked "
            + ", ".join(failed)
            + " but the entries failed; recorded a structured continue."
        )
    else:
        delta = ""
        summary = (
            "Local capability kernel found no safe ledger capability to invoke; "
            "recorded a structured continue so the mission does not stall."
        )
    return empty_local_decision(
        status="continue",
        summary=summary,
        strategy="Execute cheap proved ledger capabilities locally while first-class kernels cool down.",
        next_step="Resume on a healthy first-class kernel when a breaker closes, or keep compounding locally.",
        capability_delta=delta,
        outcome_evidence=evidence,
        mission_goal=goal,
        done_when=done_when,
    )


def local_capability_tick(state: Any, workspace: Path) -> dict[str, Any]:
    """Default local-kernel action: invoke a cheap ledger capability."""

    root = resolve_tick_root(state, workspace)
    goal = str(getattr(state, "goal", "") or "")
    done_when = str(getattr(state, "done_when", "") or "")
    record = load_tick_record(root)
    ledger = load_tick_ledger(root)
    if ledger is None:
        report = _decision_fields(
            invoked=[],
            root=root,
            goal=goal,
            done_when=done_when,
            ledger_count=0,
            reason="ledger_missing",
        )
        report["ok"] = True
        report["action"] = "local_capability_tick"
        report["invoked"] = []
        return report

    program = select_local_program(
        ledger,
        goal=goal,
        skip_ids=tuple(record.last_ids[-ROTATION_MEMORY:]),
    )
    invoked: list[dict[str, Any]] = []
    for capability_id in program:
        capability = ledger.capabilities.get(capability_id)
        if capability is None:
            continue
        try:
            invoked.append(invoke_local_capability(capability))
        except Exception as error:  # noqa: BLE001 - tick must still emit a decision
            invoked.append(
                {
                    "capability_id": capability_id,
                    "ok": False,
                    "exit_code": 1,
                    "kind": "python-inprocess",
                    "summary": str(error)[:400],
                    "entry": capability.entry,
                }
            )

    report = _decision_fields(
        invoked=invoked,
        root=root,
        goal=goal,
        done_when=done_when,
        ledger_count=len(ledger.capabilities),
        reason="invoked" if invoked else "no_safe_capability",
    )
    report["ok"] = True
    report["action"] = "local_capability_tick"
    report["invoked"] = invoked
    report["program"] = program
    record.tick_count += 1
    record.last_ok = bool(invoked) and all(item.get("ok") for item in invoked)
    record.last_summary = str(report.get("summary") or "")[:400]
    if invoked:
        record.last_ids = [*(record.last_ids), *[item["capability_id"] for item in invoked]][
            -ROTATION_MEMORY:
        ]
    save_tick_record(root, record)
    return report


def builtin_fixture_probe() -> dict[str, Any]:
    """Hermetic probe used by the local-kernel proof ledger."""

    return {"ok": True, "action": "fixture_probe", "probe": "local-capability-kernel"}


def builtin_fixture_probe_b() -> dict[str, Any]:
    return {"ok": True, "action": "fixture_probe_b", "probe": "local-capability-kernel-b"}


def _write_fixture_ledger(root: Path, *, explode: bool = False) -> Path:
    from blackhole_agent.capability_compounder import CapabilityLedger, register_capability, save_ledger

    path = default_ledger_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    ledger = CapabilityLedger()
    first_entry = (
        "blackhole_agent.local_capability_kernel:builtin_missing_on_purpose"
        if explode
        else "blackhole_agent.local_capability_kernel:builtin_fixture_probe"
    )
    register_capability(
        ledger,
        Capability(
            id="capability.fixture-local-a",
            name="Fixture local A",
            description="Hermetic local-kernel probe A.",
            kind="python",
            entry=first_entry,
            proof_command="uv run python -c \"print('ok')\"",
            last_proof_exit_code=0,
        ),
    )
    register_capability(
        ledger,
        Capability(
            id="capability.fixture-local-b",
            name="Fixture local B",
            description="Hermetic local-kernel probe B.",
            kind="python",
            entry="blackhole_agent.local_capability_kernel:builtin_fixture_probe_b",
            proof_command="uv run python -c \"print('ok')\"",
            last_proof_exit_code=0,
        ),
    )
    save_ledger(path, ledger)
    return path


def builtin_local_capability_kernel_proof() -> dict[str, Any]:
    """Hermetic proof: a harvested 402 failsover into real ledger work."""

    import tempfile

    from blackhole_agent.kernel_salvage import (
        HARVESTED_GROK_402,
        classify_run_artifact,
        execute_kernel_turn_with_salvage,
    )
    from blackhole_agent.pattern_register import classify_unbound_turn
    from blackhole_agent.unbound import KernelTurnResult, TurnDecision

    checks: dict[str, bool] = {}
    harvested = classify_run_artifact(HARVESTED_GROK_402, error="Grok CLI failed with exit code 1")
    checks["harvested_402"] = harvested.class_id == "quota_exhausted" and not harvested.retryable

    class _State:
        def __init__(self, repo: Path, *, goal: str = "Keep growing after a 402.") -> None:
            self.kernel = "grok"
            self.session_id = "sess"
            self.session_started = True
            self.repo_path = str(repo)
            self.workspace_path = str(repo)
            self.goal = goal
            self.done_when = "A structured decision is recorded."

    with tempfile.TemporaryDirectory(prefix="local-kernel-empty-") as tmp:
        empty_root = Path(tmp)
        empty_tick = local_capability_tick(_State(empty_root), empty_root)
    checks["empty_ledger_continues"] = (
        empty_tick.get("ok") is True
        and empty_tick.get("status") == "continue"
        and empty_tick.get("invoked") == []
        and any("ledger_count=0" in item for item in empty_tick.get("outcome_evidence") or [])
    )

    with tempfile.TemporaryDirectory(prefix="local-kernel-fail-") as tmp:
        fail_root = Path(tmp)
        _write_fixture_ledger(fail_root, explode=True)
        failed_tick = local_capability_tick(_State(fail_root), fail_root)
    checks["failed_invoke_continues"] = (
        failed_tick.get("status") == "continue"
        and bool(failed_tick.get("invoked"))
        and failed_tick["invoked"][0]["ok"] is False
        and not failed_tick.get("capability_delta")
    )

    with tempfile.TemporaryDirectory(prefix="local-kernel-live-") as tmp:
        live_root = Path(tmp)
        _write_fixture_ledger(live_root)
        first = local_capability_tick(_State(live_root), live_root)
        second = local_capability_tick(_State(live_root), live_root)
        first_id = (first.get("invoked") or [{}])[0].get("capability_id")
        second_id = (second.get("invoked") or [{}])[0].get("capability_id")
    checks["fixture_invoked"] = (
        first.get("status") == "continue"
        and bool(first.get("capability_delta"))
        and first_id == "capability.fixture-local-a"
        and first["invoked"][0]["ok"] is True
    )
    checks["rotates_next_tick"] = second_id == "capability.fixture-local-b" and second_id != first_id

    def boom(state: Any, prompt: str, turn_dir: Path, **kwargs: Any) -> Any:
        kernel_dir = Path(turn_dir) / "kernel"
        kernel_dir.mkdir(parents=True, exist_ok=True)
        (kernel_dir / "latest-grok-run.json").write_text(
            json.dumps(HARVESTED_GROK_402),
            encoding="utf-8",
        )
        raise RuntimeError("Grok CLI failed with exit code 1; Payment Required usage balance exhausted")

    with tempfile.TemporaryDirectory(prefix="local-kernel-402-") as tmp:
        repo = Path(tmp)
        _write_fixture_ledger(repo)
        state = _State(repo)
        result, decision, meta = execute_kernel_turn_with_salvage(
            state,
            "prompt",
            repo / "turn",
            kernel_runner=boom,
            installed_kernels=set(),
            persist_health=False,
        )
        artifact = json.loads((repo / "turn" / "kernel" / "latest-local-run.json").read_text(encoding="utf-8"))
    invoked = (artifact.get("report") or {}).get("invoked") or []
    checks["execute_402_invokes"] = (
        isinstance(decision, TurnDecision)
        and decision.status == "continue"
        and state.kernel == LOCAL_KERNEL
        and meta.get("source") == "failover"
        and isinstance(result, KernelTurnResult)
        and bool(decision.capability_delta)
        and any("capability.fixture-local-a" in item for item in decision.outcome_evidence)
        and invoked
        and invoked[0]["capability_id"] == "capability.fixture-local-a"
        and invoked[0]["ok"] is True
    )

    events = classify_unbound_turn(
        {
            "iteration": 13,
            "effective_status": "continue",
            "requested_status": "continue",
            "summary": decision.summary,
            "kernel_salvage": meta,
        }
    )
    checks["not_kernel_turn_failed"] = not any(
        item.get("class_id") == "kernel_turn_failed" for item in events
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    from blackhole_agent.capability_compounder import CapabilityLedger, register_capability

    mixed = CapabilityLedger()
    register_capability(
        mixed,
        Capability(
            id="capability.fragility-audit",
            name="Goal fragility audit",
            description="Expensive audit that must not win a failover tick.",
            kind="python",
            entry="blackhole_agent.local_capability_kernel:builtin_fixture_probe",
            proof_command="uv run python -c \"print('ok')\"",
            last_proof_exit_code=0,
            tags=("audit",),
        ),
    )
    register_capability(
        mixed,
        Capability(
            id="capability.ledger-inventory",
            name="Capability ledger inventory",
            description="Cheap inventory anchor.",
            kind="python",
            entry="blackhole_agent.local_capability_kernel:builtin_fixture_probe",
            proof_command="uv run python -c \"print('ok')\"",
            last_proof_exit_code=0,
            tags=("bootstrap",),
        ),
    )
    checks["prefers_cheap_anchor"] = select_local_program(
        mixed, goal="Keep growing after a 402."
    ) == ["capability.ledger-inventory"]

    ok = all(checks.values())
    return {
        "ok": ok,
        "action": "local_capability_kernel",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }
