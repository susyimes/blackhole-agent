"""Sovereign local mission continuation after first-class kernel death.

Salvage, the circuit breaker, and the cheap local tick already keep a 402
storm from stalling or retrying Grok. They still leave genesis unbound and
rotate inventory instead of pursuing a mission. This module closes that hole:

- bind a mission from state, experience fuel, or the harvested kernel_turn_failed
  class, never overwriting an operator-supplied field
- plan a cheap goal-conditioned campaign over safe ledger capabilities
- persist progress across failover ticks
- evaluate a machine-checkable outcome contract in-process
- emit mission_goal/done_when so genesis cannot stall
- persist a handoff so a recovered first-class kernel resumes, not restarts
- skip structurally closed operational classes and already-proved harvested
  contracts so a lagging controller checkout cannot rebind genesis_selection_blocked
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from blackhole_agent.capability_compounder import (
    Capability,
    CapabilityLedger,
    is_primitive_capability,
    legacy_pipeline_was_used,
    parse_outcome_contract,
    plan_capability_program,
    register_capability,
    save_ledger,
)
from blackhole_agent.experience_fuel import ExperienceCandidate, ExperienceFuel, harvest_experience
from blackhole_agent.kernel_health import empty_local_decision
from blackhole_agent.local_capability_kernel import (
    invoke_local_capability,
    is_safe_local_capability,
    load_tick_ledger,
    resolve_tick_root,
    select_local_program,
)
from blackhole_agent.pattern_register import PATTERN_CLASSES

SCHEMA_VERSION = 1
CAMPAIGN_RELATIVE = Path(".blackhole-agent") / "unbound" / "local-campaign.json"
MAX_CAMPAIGN_STEPS = 4

HARVESTED_KERNEL_FAILURE_GOAL = (
    "Close kernel_turn_failed: when a first-class kernel dies on quota, bind genesis "
    "and execute a goal-conditioned local campaign instead of stalling or ticking no-op inventory."
)
HARVESTED_KERNEL_FAILURE_DONE_WHEN = (
    "capability_exists:capability.local-mission-sovereignty;"
    "capability_proved:capability.local-mission-sovereignty;"
    "no_skill_route"
)


@dataclass(frozen=True)
class LocalMissionBinding:
    goal: str
    done_when: str
    source: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LocalCampaign:
    schema_version: int = SCHEMA_VERSION
    mission_id: str = ""
    goal: str = ""
    done_when: str = ""
    bound_from: str = ""
    program: list[str] = field(default_factory=list)
    cursor: int = 0
    completed_ids: list[str] = field(default_factory=list)
    failed_ids: list[str] = field(default_factory=list)
    tick_count: int = 0
    last_contract_met: bool | None = None
    last_summary: str = ""
    handoff: dict[str, Any] = field(default_factory=dict)
    updated_at: str = ""
    consumed_at: str = ""
    resumed_by_mission_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any] | None) -> "LocalCampaign":
        payload = payload or {}
        raw_program = payload.get("program") or []
        raw_completed = payload.get("completed_ids") or []
        raw_failed = payload.get("failed_ids") or []
        contract = payload.get("last_contract_met")
        handoff = payload.get("handoff") if isinstance(payload.get("handoff"), Mapping) else {}
        return cls(
            schema_version=int(payload.get("schema_version") or SCHEMA_VERSION),
            mission_id=str(payload.get("mission_id") or ""),
            goal=str(payload.get("goal") or ""),
            done_when=str(payload.get("done_when") or ""),
            bound_from=str(payload.get("bound_from") or ""),
            program=[str(item) for item in raw_program if str(item).strip()],
            cursor=int(payload.get("cursor") or 0),
            completed_ids=[str(item) for item in raw_completed if str(item).strip()],
            failed_ids=[str(item) for item in raw_failed if str(item).strip()],
            tick_count=int(payload.get("tick_count") or 0),
            last_contract_met=None if contract is None else bool(contract),
            last_summary=str(payload.get("last_summary") or ""),
            handoff=dict(handoff),
            updated_at=str(payload.get("updated_at") or ""),
            consumed_at=str(payload.get("consumed_at") or ""),
            resumed_by_mission_id=str(payload.get("resumed_by_mission_id") or ""),
        )


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def durable_campaign_root(state: Any, workspace: Path | None = None) -> Path:
    """Persist campaigns on the controller repo so worktree GC cannot drop them."""

    repo = str(getattr(state, "repo_path", "") or "").strip()
    if repo:
        return Path(repo)
    work = str(getattr(state, "workspace_path", "") or "").strip()
    if work:
        return Path(work)
    if workspace:
        return Path(workspace)
    return Path(".")


def campaign_path(root: Path) -> Path:
    return Path(root) / CAMPAIGN_RELATIVE


def load_campaign(root: Path) -> LocalCampaign:
    path = campaign_path(root)
    if not path.is_file():
        return LocalCampaign()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return LocalCampaign()
    return LocalCampaign.from_dict(payload if isinstance(payload, Mapping) else {})


def save_campaign(root: Path, campaign: LocalCampaign) -> Path:
    path = campaign_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    campaign.updated_at = _utc_now()
    path.write_text(json.dumps(campaign.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def mission_from_candidate(
    candidate: ExperienceCandidate | None,
    ledger: CapabilityLedger | None = None,
    *,
    root: Path | None = None,
    lineage_ref: str = "",
) -> tuple[str, str]:
    """Map harvested operational fuel onto a bindable Unbound mission.

    Classes with a structural closer bind that closer's exists/proved
    contract. Already-closed classes return empty so bind can fall through
    to a catalog successor instead of reusing the already-proved harvested
    local-mission-sovereignty contract.
    """

    if candidate is None:
        return HARVESTED_KERNEL_FAILURE_GOAL, HARVESTED_KERNEL_FAILURE_DONE_WHEN
    class_id = str(candidate.class_id or "")
    if class_id == "kernel_turn_failed":
        return HARVESTED_KERNEL_FAILURE_GOAL, HARVESTED_KERNEL_FAILURE_DONE_WHEN
    catalog = PATTERN_CLASSES.get(class_id, {})
    summary = str(candidate.summary or catalog.get("name") or "Operational failure").strip()
    if class_id:
        goal = f"Close operational class `{class_id}`: {summary}"
    else:
        goal = summary or HARVESTED_KERNEL_FAILURE_GOAL
    if class_id == "mission_leftover":
        try:
            from blackhole_agent.kernel_leftover import leftover_campaign_done_when

            return goal, leftover_campaign_done_when(summary, ledger=ledger)
        except Exception:  # noqa: BLE001 - leftover bind must still choose a mission
            return goal, HARVESTED_KERNEL_FAILURE_DONE_WHEN
    try:
        from blackhole_agent.kernel_class_closure import class_closure_ids, class_is_closed

        required = class_closure_ids(class_id)
    except Exception:  # noqa: BLE001 - bind must still choose a mission
        required = ()
    if required:
        if root is not None and class_is_closed(
            class_id,
            Path(root),
            ledger=ledger,
            lineage_ref=lineage_ref,
        ):
            return "", ""
        missing = [
            item
            for item in required
            if not (
                ledger is not None
                and ledger.capabilities.get(item) is not None
                and ledger.capabilities[item].last_proof_exit_code == 0
            )
        ]
        if ledger is not None and not missing:
            return "", ""
        closer = missing[0] if missing else required[0]
        return goal, (
            f"capability_exists:{closer};"
            f"capability_proved:{closer};"
            "no_skill_route"
        )
    return goal, HARVESTED_KERNEL_FAILURE_DONE_WHEN


def bind_local_mission(
    state: Any,
    *,
    fuel: ExperienceFuel | None = None,
    harvest: bool = True,
    repo_path: Path | None = None,
) -> LocalMissionBinding:
    """Fill only missing genesis fields. Operator-supplied values are kept."""

    goal = str(getattr(state, "goal", "") or "").strip()
    done_when = str(getattr(state, "done_when", "") or "").strip()
    sources: list[str] = []
    if goal:
        sources.append("state.goal")
    if done_when:
        sources.append("state.done_when")
    if goal and done_when:
        return LocalMissionBinding(goal=goal, done_when=done_when, source="+".join(sources))

    live = fuel
    if live is None and harvest:
        root = repo_path or Path(getattr(state, "repo_path", "") or getattr(state, "workspace_path", "") or ".")
        try:
            live = harvest_experience(Path(root), limit=5)
        except Exception:  # noqa: BLE001 - binding must still choose a mission
            live = None

    fill_goal = HARVESTED_KERNEL_FAILURE_GOAL
    fill_done = HARVESTED_KERNEL_FAILURE_DONE_WHEN
    fill_source = "harvested_kernel_failure"
    tick_root = Path(
        repo_path or getattr(state, "repo_path", "") or getattr(state, "workspace_path", "") or "."
    )
    if live is not None:
        try:
            from blackhole_agent.kernel_class_closure import class_is_closed

            if class_is_closed("kernel_turn_failed", tick_root):
                fill_goal = ""
                fill_done = ""
                fill_source = "class_closed"
        except Exception:  # noqa: BLE001 - binding must still choose a mission
            pass
    if live and live.forced:
        fill_goal = str(live.forced.get("goal") or fill_goal)
        fill_done = str(live.forced.get("done_when") or fill_done)
        fill_source = "pattern-register"
    elif live and live.candidates:
        ledger = load_tick_ledger(tick_root)
        try:
            from blackhole_agent.kernel_class_closure import load_effective_ledger

            effective = load_effective_ledger(tick_root, ledger=ledger)
            if effective is not None:
                ledger = effective
        except Exception:  # noqa: BLE001 - bind must still rank working-tree candidates
            pass
        for candidate in live.candidates:
            cand_goal, cand_done = mission_from_candidate(
                candidate,
                ledger=ledger,
                root=tick_root,
            )
            passes = True
            try:
                from blackhole_agent.kernel_genesis_bind import candidate_passes_selection

                passes = candidate_passes_selection(tick_root, cand_goal, cand_done)
            except Exception:  # noqa: BLE001 - skip candidates the gates cannot assess
                passes = False
            if cand_goal and cand_done and passes:
                fill_goal = cand_goal
                fill_done = cand_done
                fill_source = f"experience/{candidate.class_id or 'operational'}"
                break
    if fill_source == "class_closed" and (not fill_goal or not fill_done):
        try:
            from blackhole_agent.kernel_unscoped_resume import bind_from_unscoped_campaign

            scoped_goal, scoped_done, scoped_source = bind_from_unscoped_campaign(tick_root)
            if scoped_source:
                fill_goal = scoped_goal
                fill_done = scoped_done
                fill_source = scoped_source
        except Exception:  # noqa: BLE001 - binding must still choose a mission
            pass
    if fill_source == "class_closed" and (not fill_goal or not fill_done):
        try:
            from blackhole_agent.kernel_genesis_bind import bind_gate_passing_successor

            succ_goal, succ_done, succ_source = bind_gate_passing_successor(tick_root)
            if succ_source:
                fill_goal = succ_goal
                fill_done = succ_done
                fill_source = succ_source
        except Exception:  # noqa: BLE001 - binding must still choose a mission
            pass

    if not goal:
        goal = fill_goal
        sources.append(fill_source)
    if not done_when:
        done_when = fill_done
        if fill_source not in sources:
            sources.append(fill_source)
    return LocalMissionBinding(goal=goal, done_when=done_when, source="+".join(sources) or fill_source)


def evaluate_campaign_contract(
    ledger: CapabilityLedger,
    done_when: str,
    *,
    completed_ids: tuple[str, ...] = (),
    mission_plane_ok: bool | None = None,
) -> dict[str, Any]:
    """Cheap in-process contract check against the given ledger. No program runs."""

    parsed = parse_outcome_contract(done_when)
    predicates = list(parsed.get("predicates") or [])
    if not parsed.get("ok") or not predicates:
        return {
            "ok": True,
            "met": None,
            "machine_checkable": False,
            "results": [],
            "notes": list(parsed.get("notes") or []),
        }
    completed = {item for item in completed_ids if item}
    results: list[dict[str, Any]] = []
    for predicate in predicates:
        kind = str(predicate.get("kind") or "")
        arg = str(predicate.get("arg") or "").strip()
        passed = False
        detail = ""
        if kind == "capability_exists":
            passed = arg in ledger.capabilities
            detail = f"exists={passed}"
        elif kind == "capability_proved":
            capability = ledger.capabilities.get(arg)
            passed = bool(capability and capability.last_proof_exit_code == 0)
            detail = f"proved={passed}"
        elif kind == "no_skill_route":
            passed = not legacy_pipeline_was_used()
            detail = "no_skill_route"
        elif kind == "min_capabilities":
            passed = len(ledger.capabilities) >= int(arg or 0)
            detail = f"count={len(ledger.capabilities)}"
        elif kind == "min_primitives":
            count = sum(1 for item in ledger.capabilities.values() if is_primitive_capability(item))
            passed = count >= int(arg or 0)
            detail = f"primitives={count}"
        elif kind == "program_passes":
            passed = arg in completed
            detail = f"completed={passed}"
        elif kind == "mission_plane_ok":
            passed = bool(mission_plane_ok)
            detail = f"mission_plane_ok={passed}"
        else:
            detail = "unsupported_in_local_evaluator"
        results.append({"kind": kind, "arg": arg, "passed": passed, "detail": detail})
    return {
        "ok": True,
        "met": all(item["passed"] for item in results),
        "machine_checkable": True,
        "results": results,
        "notes": list(parsed.get("notes") or []),
    }


def plan_campaign_program(
    ledger: CapabilityLedger,
    goal: str,
    *,
    skip_ids: tuple[str, ...] = (),
    max_steps: int = MAX_CAMPAIGN_STEPS,
) -> list[str]:
    """Goal-conditioned safe program, falling back to the cheap local selector."""

    skipped = {item for item in skip_ids if item}
    planned = plan_capability_program(ledger, goal or "", max_steps=max(3, max_steps))
    steps: list[str] = []
    for capability_id in list(planned.get("steps") or []):
        capability = ledger.capabilities.get(capability_id)
        if capability is None or capability_id in skipped:
            continue
        if is_safe_local_capability(capability) and capability_id not in steps:
            steps.append(capability_id)
        if len(steps) >= max(1, int(max_steps)):
            return steps
    if steps:
        return steps
    return select_local_program(
        ledger,
        goal=goal,
        skip_ids=tuple(skipped),
        max_steps=max_steps,
    )


def campaign_handoff(campaign: LocalCampaign) -> dict[str, Any]:
    return {
        "goal": campaign.goal,
        "done_when": campaign.done_when,
        "bound_from": campaign.bound_from,
        "completed_ids": list(campaign.completed_ids),
        "failed_ids": list(campaign.failed_ids),
        "program": list(campaign.program),
        "cursor": campaign.cursor,
        "tick_count": campaign.tick_count,
        "contract_met": campaign.last_contract_met,
        "summary": campaign.last_summary,
    }


def render_local_campaign_for_prompt(repo_path: Path) -> str:
    """Compact recovering-kernel brief. Empty when no local campaign ran."""

    campaign = load_campaign(Path(repo_path))
    if campaign.tick_count <= 0:
        return ""
    completed = ", ".join(campaign.completed_ids) or "(none)"
    remaining = [
        item
        for item in campaign.program[campaign.cursor :]
        if item not in campaign.completed_ids
    ]
    remaining_text = ", ".join(remaining) or "(none)"
    succession = str((campaign.handoff or {}).get("succession_step") or "")
    succession_line = f"\n- succession_step: {succession}" if succession else ""
    plane_step = str((campaign.handoff or {}).get("mission_plane_step") or "")
    plane_line = f"\n- mission_plane_step: {plane_step}" if plane_step else ""
    plane_ok = (campaign.handoff or {}).get("mission_plane_ok")
    plane_ok_line = f"\n- mission_plane_ok: {plane_ok}" if plane_ok is not None else ""
    return (
        "Local-kernel campaign handoff (first-class kernel was unavailable; "
        "resume from this progress, do not restart genesis):\n"
        f"- bound_from: {campaign.bound_from}\n"
        f"- goal: {campaign.goal}\n"
        f"- done_when: {campaign.done_when}\n"
        f"- ticks: {campaign.tick_count}\n"
        f"- completed: {completed}\n"
        f"- remaining: {remaining_text}\n"
        f"- contract_met: {campaign.last_contract_met}\n"
        f"- last: {campaign.last_summary}"
        f"{succession_line}"
        f"{plane_line}"
        f"{plane_ok_line}"
    )


def _prepare_campaign(
    existing: LocalCampaign,
    *,
    mission_id: str,
    binding: LocalMissionBinding,
    ledger: CapabilityLedger,
) -> LocalCampaign:
    same_mission = existing.mission_id == mission_id and existing.goal == binding.goal
    keep_remaining = False
    if not same_mission:
        try:
            from blackhole_agent.kernel_unscoped_resume import should_preserve_campaign

            keep_remaining = should_preserve_campaign(
                existing,
                mission_id=mission_id,
                goal=binding.goal,
            )
        except Exception:  # noqa: BLE001 - campaign prepare must still bind
            keep_remaining = False
    campaign = existing if same_mission or keep_remaining else LocalCampaign()
    campaign.mission_id = mission_id
    campaign.goal = binding.goal
    campaign.done_when = binding.done_when
    campaign.bound_from = binding.source
    remaining = [item for item in campaign.program[campaign.cursor :] if item not in campaign.completed_ids]
    if not remaining:
        campaign.program = plan_campaign_program(
            ledger,
            binding.goal,
            skip_ids=tuple(campaign.completed_ids),
        )
        campaign.cursor = 0
    return campaign


def _next_step(campaign: LocalCampaign) -> str:
    while campaign.cursor < len(campaign.program):
        capability_id = campaign.program[campaign.cursor]
        campaign.cursor += 1
        if capability_id and capability_id not in campaign.completed_ids:
            return capability_id
    return ""


def local_mission_tick(state: Any, workspace: Path) -> dict[str, Any]:
    """Default local-kernel action: bind a mission and advance a campaign."""

    root = resolve_tick_root(state, workspace)
    durable = durable_campaign_root(state, workspace)
    binding = bind_local_mission(state, repo_path=durable)
    mission_id = str(getattr(state, "mission_id", "") or "local")
    ledger = load_tick_ledger(root)
    campaign = load_campaign(durable)
    invoked: list[dict[str, Any]] = []
    contract: dict[str, Any] = {"ok": True, "met": None, "machine_checkable": False, "results": []}

    if ledger is None:
        summary = (
            "Local mission sovereignty bound a mission while the ledger was missing; "
            "recorded a structured continue so genesis cannot stall."
        )
        campaign.mission_id = mission_id
        campaign.goal = binding.goal
        campaign.done_when = binding.done_when
        campaign.bound_from = binding.source
        campaign.tick_count += 1
        campaign.last_summary = summary
        campaign.handoff = campaign_handoff(campaign)
        save_campaign(durable, campaign)
        report = empty_local_decision(
            status="continue",
            summary=summary,
            strategy="Bind genesis locally and wait for a ledger or a healthy first-class kernel.",
            next_step="Resume on a healthy first-class kernel, or keep compounding once a ledger is present.",
            capability_delta="",
            outcome_evidence=[
                f"root={root}",
                "ledger_count=0",
                f"bound_from={binding.source}",
                "reason=ledger_missing",
            ],
            mission_goal=binding.goal,
            done_when=binding.done_when,
        )
        report.update(
            {
                "ok": True,
                "action": "local_mission_tick",
                "invoked": [],
                "program": [],
                "binding": binding.to_dict(),
                "contract": contract,
                "campaign": campaign.to_dict(),
            }
        )
        return report

    campaign = _prepare_campaign(campaign, mission_id=mission_id, binding=binding, ledger=ledger)
    if "mission_leftover" in binding.source:
        prefix = "Close operational class `mission_leftover`: "
        leftover_summary = (
            binding.goal[len(prefix) :] if binding.goal.startswith(prefix) else binding.goal
        )
        campaign.handoff = {**dict(campaign.handoff or {}), "leftover_summary": leftover_summary}
    previous_handoff = dict(campaign.handoff or {})
    growth_used = False
    compound_used = False
    compose_used = False
    program_used = False
    capability_id = ""
    try:
        from blackhole_agent.kernel_consumed_growth import attach_consumed_growth_leaf

        capability_id = attach_consumed_growth_leaf(
            campaign,
            ledger,
            root,
            goal=binding.goal,
            done_when=binding.done_when,
            bind_source=binding.source,
        )
        growth_used = bool(capability_id)
    except Exception:  # noqa: BLE001 - cheap tick must still emit a decision
        capability_id = ""
        growth_used = False
    if not capability_id:
        try:
            from blackhole_agent.kernel_compound_loop import attach_compound_loop_leaf

            capability_id = attach_compound_loop_leaf(
                campaign,
                ledger,
                root,
                goal=binding.goal,
                done_when=binding.done_when,
                bind_source=binding.source,
            )
            compound_used = bool(capability_id)
        except Exception:  # noqa: BLE001 - cheap tick must still emit a decision
            capability_id = ""
            compound_used = False
    if not capability_id:
        try:
            from blackhole_agent.kernel_primitive_compose import attach_primitive_composition

            capability_id = attach_primitive_composition(
                campaign,
                ledger,
                root,
                goal=binding.goal,
                done_when=binding.done_when,
                bind_source=binding.source,
            )
            compose_used = bool(capability_id)
        except Exception:  # noqa: BLE001 - cheap tick must still emit a decision
            capability_id = ""
            compose_used = False
    if not capability_id:
        try:
            from blackhole_agent.kernel_composed_program import attach_composed_program

            capability_id = attach_composed_program(
                campaign,
                ledger,
                root,
                goal=binding.goal,
                done_when=binding.done_when,
                bind_source=binding.source,
            )
            program_used = bool(capability_id)
        except Exception:  # noqa: BLE001 - cheap tick must still emit a decision
            capability_id = ""
            program_used = False
    if not capability_id:
        capability_id = _next_step(campaign)
    succession_used = False
    mission_plane_used = False
    if not capability_id:
        try:
            from blackhole_agent.kernel_succession import attach_succession_step

            capability_id = attach_succession_step(campaign, ledger, goal=binding.goal)
            succession_used = bool(capability_id)
        except Exception:  # noqa: BLE001 - cheap tick must still emit a decision
            capability_id = ""
            succession_used = False
    if not capability_id:
        try:
            from blackhole_agent.kernel_mission_plane import attach_mission_plane_step

            capability_id = attach_mission_plane_step(campaign, ledger, goal=binding.goal)
            mission_plane_used = bool(capability_id)
        except Exception:  # noqa: BLE001 - cheap tick must still emit a decision
            capability_id = ""
            mission_plane_used = False
    if capability_id:
        capability = ledger.capabilities.get(capability_id)
        if capability is None:
            invoked.append(
                {
                    "capability_id": capability_id,
                    "ok": False,
                    "exit_code": 1,
                    "kind": "python-inprocess",
                    "summary": "capability missing from ledger",
                    "entry": "",
                }
            )
            campaign.failed_ids.append(capability_id)
        else:
            try:
                result = invoke_local_capability(capability)
            except Exception as error:  # noqa: BLE001 - tick must still emit a decision
                result = {
                    "capability_id": capability_id,
                    "ok": False,
                    "exit_code": 1,
                    "kind": "python-inprocess",
                    "summary": str(error)[:400],
                    "entry": capability.entry,
                }
            invoked.append(result)
            if result.get("ok"):
                campaign.completed_ids.append(capability_id)
            else:
                campaign.failed_ids.append(capability_id)

    plane_ok = False
    preserve_handoff = None
    try:
        from blackhole_agent.kernel_mission_plane import (
            preserve_campaign_handoff,
            refresh_mission_plane_ok,
        )

        preserve_handoff = preserve_campaign_handoff
        plane_ok = refresh_mission_plane_ok(campaign, ledger)
    except Exception:  # noqa: BLE001 - contract evaluation must still run
        plane_ok = bool((campaign.handoff or {}).get("mission_plane_ok"))
    contract = evaluate_campaign_contract(
        ledger,
        binding.done_when,
        completed_ids=tuple(campaign.completed_ids),
        mission_plane_ok=plane_ok,
    )
    passed = [item["capability_id"] for item in invoked if item.get("ok")]
    if mission_plane_used:
        reason = "mission_plane"
    elif succession_used:
        reason = "succession"
    elif program_used:
        reason = "composed_program"
    elif compose_used:
        reason = "primitive_compose"
    elif compound_used:
        reason = "compound_loop"
    elif growth_used:
        reason = "consumed_growth"
    elif invoked:
        reason = "invoked"
    elif plane_ok:
        reason = "mission_plane_ok"
    else:
        reason = "no_safe_capability"
    evidence = [
        f"root={root}",
        f"ledger_count={len(ledger.capabilities)}",
        f"invoked_count={len(invoked)}",
        f"bound_from={binding.source}",
        f"reason={reason}",
        f"contract_met={contract.get('met')}",
        f"campaign_ticks={campaign.tick_count + 1}",
        f"mission_plane_ok={plane_ok}",
    ]
    evidence.extend(f"invoked={item['capability_id']}:ok={item.get('ok')}" for item in invoked)
    if passed and mission_plane_used:
        delta = (
            "Local mission-plane escaped cheap-anchor rotation and succession via "
            + ", ".join(passed)
            + " after first-class kernels were unavailable."
        )
        summary = (
            f"Local mission-plane executed {', '.join(passed)} after cheap "
            "local-anchor rotation and succession were exhausted."
        )
    elif passed and program_used:
        delta = (
            "Local composed-program promoted and proved "
            + ", ".join(passed)
            + " as a stacked composition program after unique composition coverage saturated."
        )
        summary = (
            f"Local composed-program promoted and proved {', '.join(passed)} "
            "in-process so recovered kernels keep stacking programs instead of "
            "blocking."
        )
    elif passed and compose_used:
        delta = (
            "Local primitive-compose promoted and proved "
            + ", ".join(passed)
            + " as a multi-primitive composition after unique primitive coverage saturated."
        )
        summary = (
            f"Local primitive-compose promoted and proved {', '.join(passed)} "
            "in-process so recovered kernels keep compounding programs instead of "
            "blocking."
        )
    elif passed and compound_used:
        delta = (
            "Local compound-loop absorbed and proved "
            + ", ".join(passed)
            + " as a novelty-ranked primitive after consumed-campaign leaves saturated."
        )
        summary = (
            f"Local compound-loop absorbed and proved {', '.join(passed)} "
            "in-process so recovered kernels expand primitive coverage instead of "
            "blocking."
        )
    elif passed and growth_used:
        delta = (
            "Local consumed-growth absorbed and proved "
            + ", ".join(passed)
            + " in-process after cheap inventory was all that remained."
        )
        summary = (
            f"Local consumed-growth absorbed and proved {', '.join(passed)} "
            "in-process so recovered kernels compound capability instead of "
            "rotating inventory."
        )
    elif passed and succession_used:
        delta = (
            "Local mission succession escaped cheap-anchor rotation via "
            + ", ".join(passed)
            + " after first-class kernels were unavailable."
        )
        summary = (
            f"Local mission succession executed {', '.join(passed)} after cheap "
            "local-anchor rotation was exhausted."
        )
    elif passed:
        delta = (
            "Local mission sovereignty bound a campaign from "
            f"{binding.source} and invoked "
            + ", ".join(passed)
            + " in-process after first-class kernels were unavailable."
        )
        summary = (
            f"Local mission sovereignty executed {', '.join(passed)} toward "
            "the bound mission without a first-class CLI kernel."
        )
    elif invoked:
        delta = ""
        summary = (
            "Local mission sovereignty invoked "
            + ", ".join(item["capability_id"] for item in invoked)
            + " but the entries failed; recorded a structured continue."
        )
    elif plane_ok:
        delta = (
            "Local mission-plane recorded mission_plane_ok because the bound "
            "goal program already completed in-process after first-class kernels were unavailable."
        )
        summary = (
            "Local mission-plane marked mission_plane_ok from the completed "
            "local campaign program."
        )
    else:
        delta = (
            "Local mission sovereignty bound genesis from "
            f"{binding.source} so a kernel death cannot leave the mission unscoped."
            if "state.goal" not in binding.source or "state.done_when" not in binding.source
            else ""
        )
        summary = (
            "Local mission sovereignty bound the mission and found no safe campaign "
            "step; recorded a structured continue so the mission does not stall."
        )
    finalize = False
    try:
        from blackhole_agent.kernel_finality import can_finalize_local_campaign

        finalize = can_finalize_local_campaign(contract, campaign, invoked_ok=bool(passed))
    except Exception:  # noqa: BLE001 - missing finality must still emit a decision
        finalize = False
    if finalize:
        if not delta:
            delta = (
                "Local kernel finalized a machine-checkable campaign contract "
                "after first-class kernels were unavailable."
            )
        summary = f"{summary} Local contract finality closed the mission."
        evidence = [*evidence, "local_finality=True"]
    campaign.tick_count += 1
    campaign.last_contract_met = contract.get("met") if isinstance(contract.get("met"), bool) else None
    campaign.last_summary = summary[:400]
    if preserve_handoff is not None:
        preserve_handoff(campaign, previous_handoff)
    else:
        campaign.handoff = campaign_handoff(campaign)
    if succession_used and passed:
        campaign.handoff["succession_step"] = passed[0]
    if mission_plane_used and passed:
        campaign.handoff["mission_plane_step"] = passed[0]
    if growth_used and passed:
        campaign.handoff["consumed_growth_leaf"] = passed[0]
    if compound_used and passed:
        campaign.handoff["compound_loop_leaf"] = passed[0]
    if compose_used and passed:
        campaign.handoff["primitive_compose_unit"] = passed[0]
    if program_used and passed:
        campaign.handoff["composed_program_unit"] = passed[0]
    if plane_ok:
        campaign.handoff["mission_plane_ok"] = True
    if finalize:
        campaign.handoff["local_finality"] = True
        try:
            from blackhole_agent.kernel_leftover import consume_bound_leftover

            consume_bound_leftover(durable, campaign)
        except Exception:  # noqa: BLE001 - missing leftover consume must still emit a decision
            pass
    save_campaign(durable, campaign)
    report = empty_local_decision(
        status="complete" if finalize else "continue",
        summary=summary,
        strategy=(
            "Close the bound local campaign when its machine-checkable contract "
            "is met after a 402-class kernel death."
            if finalize
            else "Bind missing genesis fields from experience or the harvested kernel "
            "failure, then execute a goal-conditioned local campaign while first-class kernels cool down."
        ),
        next_step=(
            "None. Mission complete."
            if finalize
            else "Resume on a healthy first-class kernel from the local campaign handoff, "
            "or keep advancing the campaign locally."
        ),
        capability_delta=delta,
        outcome_evidence=evidence,
        mission_goal=binding.goal,
        done_when=binding.done_when,
        done_when_met=bool(contract.get("met") is True),
    )
    report.update(
        {
            "ok": True,
            "action": "local_mission_tick",
            "invoked": invoked,
            "program": list(campaign.program),
            "binding": binding.to_dict(),
            "contract": contract,
            "campaign": campaign.to_dict(),
        }
    )
    return report


def _write_fixture_ledger(root: Path, *, include_sovereignty: bool = False) -> Path:
    from blackhole_agent.capability_compounder import default_ledger_path
    from blackhole_agent.local_capability_kernel import _write_fixture_ledger as write_cheap

    path = write_cheap(root)
    if not include_sovereignty:
        return path
    ledger = load_tick_ledger(root)
    assert ledger is not None
    register_capability(
        ledger,
        Capability(
            id="capability.local-mission-sovereignty",
            name="Local mission sovereignty",
            description="Hermetic sovereignty stamp used by the contract-met proof.",
            kind="python",
            entry="blackhole_agent.local_capability_kernel:builtin_fixture_probe",
            proof_command="uv run python -c \"print('ok')\"",
            last_proof_exit_code=0,
        ),
        replace=True,
    )
    save_ledger(path, ledger)
    return path


def builtin_local_mission_sovereignty_proof() -> dict[str, Any]:
    """Hermetic proof: a 402 genesis turn binds a mission and advances a campaign."""

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
        def __init__(
            self,
            repo: Path,
            *,
            goal: str = "",
            done_when: str = "",
            mission_id: str = "mission-sov",
        ) -> None:
            self.kernel = "grok"
            self.session_id = "sess"
            self.session_started = True
            self.repo_path = str(repo)
            self.workspace_path = str(repo)
            self.goal = goal
            self.done_when = done_when
            self.mission_id = mission_id

    empty = bind_local_mission(_State(Path(".")), harvest=False)
    checks["empty_genesis_binds_harvested"] = (
        empty.goal == HARVESTED_KERNEL_FAILURE_GOAL
        and empty.done_when == HARVESTED_KERNEL_FAILURE_DONE_WHEN
        and empty.source == "harvested_kernel_failure"
    )

    kept_goal = bind_local_mission(_State(Path("."), goal="Operator goal"), harvest=False)
    checks["preserves_operator_goal"] = (
        kept_goal.goal == "Operator goal" and kept_goal.done_when == HARVESTED_KERNEL_FAILURE_DONE_WHEN
    )
    kept_done = bind_local_mission(
        _State(Path("."), done_when="capability_exists:repo.import-health"),
        harvest=False,
    )
    checks["preserves_operator_done_when"] = (
        kept_done.done_when == "capability_exists:repo.import-health"
        and kept_done.goal == HARVESTED_KERNEL_FAILURE_GOAL
    )

    fuel = ExperienceFuel(
        candidates=[
            ExperienceCandidate(
                source="unbound",
                class_id="health_check_failed",
                summary="health surface failed",
                priority=3,
            )
        ]
    )
    from_fuel = bind_local_mission(_State(Path(".")), fuel=fuel, harvest=False)
    checks["experience_candidate_used"] = (
        "health_check_failed" in from_fuel.goal and from_fuel.source.startswith("experience/")
    )

    with tempfile.TemporaryDirectory(prefix="local-sov-advance-") as tmp:
        root = Path(tmp)
        _write_fixture_ledger(root)
        first = local_mission_tick(_State(root, goal="Keep growing after a 402."), root)
        second = local_mission_tick(_State(root, goal="Keep growing after a 402."), root)
        first_id = (first.get("invoked") or [{}])[0].get("capability_id")
        second_id = (second.get("invoked") or [{}])[0].get("capability_id")
        persisted = load_campaign(root)
    checks["campaign_advances"] = (
        first_id == "capability.fixture-local-a"
        and second_id == "capability.fixture-local-b"
        and first_id != second_id
        and "capability.fixture-local-a" in persisted.completed_ids
        and persisted.tick_count == 2
        and bool(first.get("capability_delta"))
    )
    checks["contract_evaluated"] = (
        (first.get("contract") or {}).get("machine_checkable") is True
        and (first.get("contract") or {}).get("met") is False
    )
    free_contract = evaluate_campaign_contract(CapabilityLedger(), "A structured decision is recorded.")
    checks["free_text_contract_is_not_machine"] = free_contract.get("machine_checkable") is False

    with tempfile.TemporaryDirectory(prefix="local-sov-met-") as tmp:
        met_root = Path(tmp)
        _write_fixture_ledger(met_root, include_sovereignty=True)
        met_tick = local_mission_tick(_State(met_root), met_root)
        met_contract = met_tick.get("contract") or {}
    checks["contract_met_when_capability_present"] = (
        met_contract.get("machine_checkable") is True
        and met_contract.get("met") is True
        and met_tick.get("done_when_met") is True
        and met_tick.get("mission_goal") == HARVESTED_KERNEL_FAILURE_GOAL
    )

    def boom(state: Any, prompt: str, turn_dir: Path, **kwargs: Any) -> Any:
        kernel_dir = Path(turn_dir) / "kernel"
        kernel_dir.mkdir(parents=True, exist_ok=True)
        (kernel_dir / "latest-grok-run.json").write_text(
            json.dumps(HARVESTED_GROK_402),
            encoding="utf-8",
        )
        raise RuntimeError("Grok CLI failed with exit code 1; Payment Required usage balance exhausted")

    with tempfile.TemporaryDirectory(prefix="local-sov-402-") as tmp:
        repo = Path(tmp)
        _write_fixture_ledger(repo)
        genesis = _State(repo)
        result, decision, meta = execute_kernel_turn_with_salvage(
            genesis,
            "prompt",
            repo / "turn",
            kernel_runner=boom,
            installed_kernels=set(),
            persist_health=False,
        )
        artifact = json.loads((repo / "turn" / "kernel" / "latest-local-run.json").read_text(encoding="utf-8"))
        handoff_text = render_local_campaign_for_prompt(repo)
        persisted_402 = load_campaign(repo)
    invoked = (artifact.get("report") or {}).get("invoked") or []
    checks["execute_402_binds_genesis"] = (
        isinstance(decision, TurnDecision)
        and decision.status == "continue"
        and genesis.kernel == "local"
        and meta.get("source") == "failover"
        and decision.mission_goal == HARVESTED_KERNEL_FAILURE_GOAL
        and decision.done_when == HARVESTED_KERNEL_FAILURE_DONE_WHEN
        and isinstance(result, KernelTurnResult)
        and bool(decision.capability_delta)
        and invoked
        and invoked[0]["capability_id"] == "capability.fixture-local-a"
        and invoked[0]["ok"] is True
    )
    checks["handoff_persisted"] = (
        persisted_402.tick_count >= 1
        and "Local-kernel campaign handoff" in handoff_text
        and HARVESTED_KERNEL_FAILURE_GOAL in handoff_text
    )

    with tempfile.TemporaryDirectory(prefix="local-sov-keep-") as tmp:
        keep_root = Path(tmp)
        _write_fixture_ledger(keep_root)
        keep_state = _State(keep_root, goal="Operator-supplied growth goal.")
        _result, keep_decision, _meta = execute_kernel_turn_with_salvage(
            keep_state,
            "prompt",
            keep_root / "turn",
            kernel_runner=boom,
            installed_kernels=set(),
            persist_health=False,
        )
    checks["execute_402_preserves_operator_goal"] = (
        keep_decision.mission_goal == "Operator-supplied growth goal."
        and keep_decision.done_when == HARVESTED_KERNEL_FAILURE_DONE_WHEN
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

    from blackhole_agent.kernel_class_closure import class_is_closed
    from blackhole_agent.kernel_genesis_bind import (
        CONSUMED_GROWTH_GOAL,
        CONSUMED_GROWTH_ID,
        GENESIS_SELECTION_BLOCKED,
        KERNEL_GENESIS_BIND_ID,
        _consumed_campaign,
        _git_commit_ledger,
        _register_proved,
        _write_loop_lineage,
        _write_selection_blocked_mission,
        bind_gate_passing_successor,
    )
    from blackhole_agent.kernel_unscoped_resume import _register_turn_failed_closers

    selection_goal, selection_done = mission_from_candidate(
        ExperienceCandidate(
            source="unbound",
            class_id=GENESIS_SELECTION_BLOCKED,
            summary="turn 3 reported blocked",
        )
    )
    checks["selection_class_binds_closer_not_self"] = (
        GENESIS_SELECTION_BLOCKED in selection_goal
        and KERNEL_GENESIS_BIND_ID in selection_done
        and "local-mission-sovereignty" not in selection_done
    )

    with tempfile.TemporaryDirectory(prefix="local-sov-stale-") as tmp:
        root = Path(tmp)
        _write_fixture_ledger(root)
        _register_turn_failed_closers(root)
        _register_proved(root, KERNEL_GENESIS_BIND_ID)
        sha = _git_commit_ledger(root)
        _write_fixture_ledger(root)
        _register_turn_failed_closers(root)
        _write_loop_lineage(root, sha)
        _write_selection_blocked_mission(root)
        save_campaign(root, _consumed_campaign())
        skipped_goal, skipped_done = mission_from_candidate(
            ExperienceCandidate(
                source="unbound",
                class_id=GENESIS_SELECTION_BLOCKED,
                summary="turn 3 reported blocked",
            ),
            root=root,
        )
        stale_closed = class_is_closed(GENESIS_SELECTION_BLOCKED, root)
        stale_fuel = harvest_experience(root, limit=5)
        stale_bind = bind_local_mission(_State(root), harvest=True)
        stale_succ_goal, stale_succ_done, stale_succ_source = bind_gate_passing_successor(root)
    checks["stale_checkout_skips_closed_selection_candidate"] = (
        skipped_goal == "" and skipped_done == "" and stale_closed is True
    )
    checks["stale_checkout_does_not_harvest_selection_class"] = not any(
        item.class_id == GENESIS_SELECTION_BLOCKED for item in stale_fuel.candidates
    )
    checks["stale_checkout_local_bind_skips_sovereignty_rerun"] = (
        HARVESTED_KERNEL_FAILURE_DONE_WHEN not in (stale_bind.done_when or "")
        and GENESIS_SELECTION_BLOCKED not in (stale_bind.goal or "")
        and "local-mission-sovereignty" not in (stale_bind.done_when or "")
    )
    checks["stale_checkout_successor_is_growth"] = (
        stale_succ_goal == CONSUMED_GROWTH_GOAL
        and CONSUMED_GROWTH_ID in stale_succ_done
        and stale_succ_source == "genesis_bind_growth"
    )

    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    return {
        "ok": ok,
        "action": "local_mission_sovereignty",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }
