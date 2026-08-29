"""Bounded in-process mission-plane after cheap and succession exhaust.

The harvested leftover from the local-capability-kernel mission asked for a
bounded mission-plane program on local ticks once cheap-anchor rotation is
exhausted. Succession already escalates to non-cheap python leaves, but it
still refuses `-plane` ids and never evaluates `mission_plane_ok`. After those
leaves complete, local ticks idle.

This plane compiles a bounded goal-conditioned program (plan + in-process run,
no absorb/grow/subprocess), invokes the next `-plane` leaf cheap and succession
refuse, persists remaining steps on the durable campaign, and lets a recovered
kernel continue that program instead of inventing genesis.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from blackhole_agent.capability_compounder import (
    Capability,
    CapabilityLedger,
    legacy_pipeline_was_used,
    plan_capability_program,
    register_capability,
    save_ledger,
)
from blackhole_agent.kernel_succession import (
    cheap_remaining,
    cheap_rotation_exhausted,
    is_succession_capability,
    select_succession_step,
)
from blackhole_agent.local_capability_kernel import (
    LOCAL_DENYLIST,
    is_safe_local_capability,
    load_tick_ledger,
)
from blackhole_agent.local_mission_sovereignty import (
    LocalCampaign,
    campaign_handoff,
    durable_campaign_root,
    load_campaign,
    save_campaign,
)

MISSION_PLANE_DONE_WHEN = (
    "capability_exists:capability.kernel-mission-plane;"
    "capability_proved:capability.kernel-mission-plane;"
    "no_skill_route"
)
MISSION_PLANE_GOAL = (
    "When cheap local-anchor rotation and succession leaves are exhausted after a "
    "402-class kernel death, escalate to a bounded in-process mission-plane program "
    "(plan + run, no absorb/grow), persist remaining steps on the durable campaign, "
    "evaluate mission_plane_ok in the local contract, and let a recovered first-class "
    "kernel continue that program instead of idling or inventing genesis."
)

MISSION_PLANE_DENYLIST = frozenset(
    {
        *LOCAL_DENYLIST,
        "capability.kernel-mission-plane",
        "capability.kernel-succession",
    }
)
MISSION_PLANE_TAG = "local-mission-plane"
HANDOFF_KEYS = (
    "succession_step",
    "mission_plane_step",
    "mission_plane_ok",
    "mission_plane_program",
    "local_finality",
    "leftover_summary",
    "leftover_consumed",
    "consumed_growth_leaf",
    "compound_loop_leaf",
)


def is_mission_plane_capability(capability: Capability) -> bool:
    """True for bounded `-plane` leaves cheap and succession both refuse."""

    if capability.id in MISSION_PLANE_DENYLIST:
        return False
    if capability.kind != "python" or ":" not in (capability.entry or ""):
        return False
    if is_safe_local_capability(capability) or is_succession_capability(capability):
        return False
    if capability.id.startswith("capability.fixture-") and "-plane" in capability.id:
        return True
    return MISSION_PLANE_TAG in capability.tags


def succession_leaves_exhausted(campaign: LocalCampaign, ledger: CapabilityLedger) -> bool:
    """Cheap rotation is done and succession has no unused leaf left."""

    if cheap_remaining(campaign):
        return False
    if not cheap_rotation_exhausted(campaign, ledger):
        return False
    return not select_succession_step(ledger, campaign, goal=campaign.goal or "")


def plan_mission_plane_program(
    ledger: CapabilityLedger,
    goal: str,
    *,
    skip_ids: tuple[str, ...] = (),
    max_steps: int = 4,
) -> list[str]:
    """Bounded goal-conditioned program over leaves cheap/succession will not pick."""

    skipped = {item for item in skip_ids if item}
    planned = plan_capability_program(ledger, goal or "", max_steps=max(4, max_steps))
    ordered: list[str] = []
    for capability_id in list(planned.get("steps") or []):
        capability = ledger.capabilities.get(capability_id)
        if capability is None or capability_id in skipped:
            continue
        if is_mission_plane_capability(capability) and capability_id not in ordered:
            ordered.append(capability_id)
        if len(ordered) >= max(1, int(max_steps)):
            return ordered
    proved = sorted(
        item_id
        for item_id, item in ledger.capabilities.items()
        if is_mission_plane_capability(item)
        and item_id not in skipped
        and item_id not in ordered
        and item.last_proof_exit_code == 0
    )
    for item_id in proved:
        ordered.append(item_id)
        if len(ordered) >= max(1, int(max_steps)):
            return ordered
    rest = sorted(
        item_id
        for item_id, item in ledger.capabilities.items()
        if is_mission_plane_capability(item) and item_id not in skipped and item_id not in ordered
    )
    for item_id in rest:
        ordered.append(item_id)
        if len(ordered) >= max(1, int(max_steps)):
            break
    return ordered


def select_mission_plane_step(
    ledger: CapabilityLedger,
    campaign: LocalCampaign,
    *,
    goal: str = "",
) -> str:
    skip = tuple(dict.fromkeys([*campaign.completed_ids, *campaign.failed_ids]))
    program = plan_mission_plane_program(ledger, goal or campaign.goal, skip_ids=skip)
    return program[0] if program else ""


def goal_program_completed(ledger: CapabilityLedger, campaign: LocalCampaign) -> bool:
    """True when the cheap goal-conditioned plan has already been executed."""

    planned = plan_capability_program(ledger, campaign.goal or "", max_steps=4)
    steps = [str(item) for item in list(planned.get("steps") or []) if str(item).strip()]
    if not steps:
        return False
    completed = {item for item in campaign.completed_ids if item}
    return all(step in completed for step in steps)


def refresh_mission_plane_ok(campaign: LocalCampaign, ledger: CapabilityLedger) -> bool:
    """Persist mission_plane_ok when the plane program or goal plan is complete."""

    handoff = dict(campaign.handoff or {})
    planned = [str(item) for item in list(handoff.get("mission_plane_program") or []) if str(item)]
    completed = {item for item in campaign.completed_ids if item}
    ok = bool(planned) and all(step in completed for step in planned)
    if not ok:
        ok = goal_program_completed(ledger, campaign)
    if ok:
        handoff["mission_plane_ok"] = True
        campaign.handoff = handoff
    return bool(handoff.get("mission_plane_ok"))


def attach_mission_plane_step(
    campaign: LocalCampaign,
    ledger: CapabilityLedger,
    *,
    goal: str = "",
) -> str:
    """Append the next bounded mission-plane leaf to the durable campaign program."""

    existing = cheap_remaining(campaign)
    if existing:
        capability = ledger.capabilities.get(existing[0])
        if capability is not None and is_mission_plane_capability(capability):
            return existing[0]
        return ""
    if not succession_leaves_exhausted(campaign, ledger):
        return ""
    step = select_mission_plane_step(ledger, campaign, goal=goal)
    if not step:
        return ""
    if step not in campaign.program:
        campaign.program.append(step)
    handoff = dict(campaign.handoff or {})
    handoff["mission_plane_step"] = step
    if not handoff.get("mission_plane_program"):
        skip = tuple(dict.fromkeys([*campaign.completed_ids, *campaign.failed_ids]))
        handoff["mission_plane_program"] = plan_mission_plane_program(
            ledger, goal or campaign.goal, skip_ids=skip
        ) or [step]
    campaign.handoff = handoff
    return step


def preserve_campaign_handoff(campaign: LocalCampaign, previous: dict[str, Any] | None) -> None:
    """Keep succession/plane extras across the rebuilt campaign handoff."""

    merged = campaign_handoff(campaign)
    prior = previous or {}
    for key in HANDOFF_KEYS:
        if key in prior and key not in merged:
            merged[key] = prior[key]
    extra = dict(campaign.handoff or {})
    for key in HANDOFF_KEYS:
        if key in extra:
            merged[key] = extra[key]
    campaign.handoff = merged


def continue_resumed_mission_plane(
    state: Any,
    repo_path: Path | None = None,
    workspace: Path | None = None,
) -> dict[str, Any]:
    """When cheap and succession are exhausted, attach a mission-plane step."""

    from blackhole_agent.kernel_resume import campaign_is_resumable

    durable = Path(repo_path) if repo_path is not None else durable_campaign_root(state, workspace)
    campaign = load_campaign(durable)
    if not campaign_is_resumable(campaign):
        return {
            "applied": False,
            "reason": "no_resumable_campaign",
            "step": "",
            "program": list(campaign.program),
        }
    work = Path(
        workspace
        or getattr(state, "workspace_path", "")
        or getattr(state, "repo_path", "")
        or durable
    )
    ledger = load_tick_ledger(work) or load_tick_ledger(durable)
    if ledger is None:
        return {
            "applied": False,
            "reason": "ledger_missing",
            "step": "",
            "program": list(campaign.program),
        }
    remaining = cheap_remaining(campaign)
    if remaining:
        return {
            "applied": False,
            "reason": "program_remaining",
            "step": remaining[0],
            "program": list(campaign.program),
        }
    if not succession_leaves_exhausted(campaign, ledger):
        return {
            "applied": False,
            "reason": "succession_remaining",
            "step": "",
            "program": list(campaign.program),
        }
    before = list(campaign.program)
    step = attach_mission_plane_step(campaign, ledger, goal=campaign.goal)
    if not step:
        refresh_mission_plane_ok(campaign, ledger)
        save_campaign(durable, campaign)
        return {
            "applied": False,
            "reason": "no_mission_plane_step",
            "step": "",
            "program": list(campaign.program),
            "mission_plane_ok": bool((campaign.handoff or {}).get("mission_plane_ok")),
        }
    campaign.handoff = dict(campaign.handoff or {})
    campaign.handoff["mission_plane_step"] = step
    save_campaign(durable, campaign)
    return {
        "applied": campaign.program != before or step in campaign.program,
        "reason": "mission_plane_attached",
        "step": step,
        "program": list(campaign.program),
    }


def builtin_fixture_mission_plane() -> dict[str, Any]:
    """Hermetic leaf used by the mission-plane proof ledger."""

    return {"ok": True, "action": "fixture_mission_plane", "probe": "kernel-mission-plane"}


def _write_mission_plane_ledger(root: Path) -> Path:
    from blackhole_agent.kernel_succession import _write_succession_ledger
    from blackhole_agent.capability_compounder import default_ledger_path

    path = _write_succession_ledger(root)
    ledger = load_tick_ledger(root)
    assert ledger is not None
    register_capability(
        ledger,
        Capability(
            id="capability.fixture-mission-plane-d",
            name="Fixture mission plane D",
            description="Bounded -plane leaf cheap and succession both refuse.",
            kind="python",
            entry="blackhole_agent.kernel_mission_plane:builtin_fixture_mission_plane",
            proof_command="uv run python -c \"print('ok')\"",
            last_proof_exit_code=0,
            tags=(MISSION_PLANE_TAG,),
        ),
        replace=True,
    )
    save_ledger(path, ledger)
    return default_ledger_path(root)


def builtin_kernel_mission_plane_proof() -> dict[str, Any]:
    """Hermetic proof: after cheap and succession, local ticks run a mission-plane."""

    import json
    import tempfile

    from blackhole_agent.kernel_resume import hydrate_mission_from_campaign
    from blackhole_agent.kernel_salvage import (
        HARVESTED_GROK_402,
        classify_run_artifact,
        execute_kernel_turn_with_salvage,
    )
    from blackhole_agent.local_mission_sovereignty import (
        bind_local_mission,
        evaluate_campaign_contract,
        local_mission_tick,
    )

    checks: dict[str, bool] = {}
    harvested = classify_run_artifact(HARVESTED_GROK_402, error="Grok CLI failed with exit code 1")
    checks["harvested_402"] = harvested.class_id == "quota_exhausted" and not harvested.retryable

    class _State:
        def __init__(
            self,
            repo: Path,
            workspace: Path | None = None,
            *,
            goal: str = "Keep growing after a 402.",
            done_when: str = "mission_plane_ok;no_skill_route",
            mission_id: str = "mission-plane",
            stage: str = "genesis",
        ) -> None:
            self.kernel = "grok"
            self.session_id = "sess"
            self.session_started = True
            self.repo_path = str(repo)
            self.workspace_path = str(workspace or repo)
            self.goal = goal
            self.done_when = done_when
            self.mission_id = mission_id
            self.stage = stage

    with tempfile.TemporaryDirectory(prefix="kernel-plane-classify-") as tmp:
        root = Path(tmp)
        _write_mission_plane_ledger(root)
        ledger = load_tick_ledger(root)
        assert ledger is not None
        cheap = ledger.capabilities["capability.fixture-local-a"]
        leaf = ledger.capabilities["capability.fixture-succession-c"]
        plane = ledger.capabilities["capability.fixture-mission-plane-d"]
        checks["plane_accepts_plane_leaf"] = is_mission_plane_capability(plane) is True
        checks["cheap_refuses_plane_leaf"] = is_safe_local_capability(plane) is False
        checks["succession_refuses_plane_leaf"] = is_succession_capability(plane) is False
        checks["plane_refuses_cheap_and_succession"] = (
            is_mission_plane_capability(cheap) is False
            and is_mission_plane_capability(leaf) is False
        )

        first = local_mission_tick(_State(root), root)
        second = local_mission_tick(_State(root), root)
        third = local_mission_tick(_State(root), root)
        fourth = local_mission_tick(_State(root), root)
        first_id = (first.get("invoked") or [{}])[0].get("capability_id")
        second_id = (second.get("invoked") or [{}])[0].get("capability_id")
        third_id = (third.get("invoked") or [{}])[0].get("capability_id")
        fourth_id = (fourth.get("invoked") or [{}])[0].get("capability_id")
        persisted = load_campaign(root)
        contract = evaluate_campaign_contract(
            ledger,
            "mission_plane_ok;no_skill_route",
            completed_ids=tuple(persisted.completed_ids),
            mission_plane_ok=bool((persisted.handoff or {}).get("mission_plane_ok")),
        )
    checks["local_tick_escalates_after_succession"] = (
        first_id == "capability.fixture-local-a"
        and second_id == "capability.fixture-local-b"
        and third_id == "capability.fixture-succession-c"
        and fourth_id == "capability.fixture-mission-plane-d"
        and (fourth.get("invoked") or [{}])[0].get("ok") is True
        and bool(fourth.get("capability_delta"))
        and str(fourth.get("outcome_evidence") or "").find("mission_plane") >= 0
    )
    checks["campaign_persists_mission_plane_step"] = (
        "capability.fixture-mission-plane-d" in persisted.program
        and "capability.fixture-mission-plane-d" in persisted.completed_ids
        and persisted.tick_count == 4
        and (persisted.handoff or {}).get("mission_plane_step")
        == "capability.fixture-mission-plane-d"
    )
    checks["mission_plane_ok_predicate_met"] = (
        fourth.get("done_when_met") is True
        and (fourth.get("contract") or {}).get("met") is True
        and contract.get("met") is True
        and bool((persisted.handoff or {}).get("mission_plane_ok"))
    )

    with tempfile.TemporaryDirectory(prefix="kernel-plane-resume-") as tmp:
        root = Path(tmp)
        _write_mission_plane_ledger(root)
        unfinished = LocalCampaign(
            mission_id="prior",
            goal="Keep growing after a 402.",
            done_when="mission_plane_ok;no_skill_route",
            bound_from="harvested_kernel_failure",
            program=[
                "capability.fixture-local-a",
                "capability.fixture-local-b",
                "capability.fixture-succession-c",
            ],
            cursor=3,
            completed_ids=[
                "capability.fixture-local-a",
                "capability.fixture-local-b",
                "capability.fixture-succession-c",
            ],
            tick_count=3,
            last_contract_met=False,
            last_summary="succession exhausted",
        )
        save_campaign(root, unfinished)
        recovered = _State(root, goal="", done_when="", mission_id="recovered")
        hydrate_report = hydrate_mission_from_campaign(recovered, persist=True)
        resumed = load_campaign(root)
        second = continue_resumed_mission_plane(recovered)
    checks["recovered_resume_attaches_mission_plane"] = (
        recovered.goal == unfinished.goal
        and recovered.stage == "execution"
        and hydrate_report.get("applied") is True
        and "capability.fixture-mission-plane-d" in resumed.program
        and (resumed.handoff or {}).get("mission_plane_step")
        == "capability.fixture-mission-plane-d"
        and second.get("reason") == "program_remaining"
        and second.get("step") == "capability.fixture-mission-plane-d"
    )

    operator = _State(Path("."), goal="Operator growth goal.")
    kept = bind_local_mission(operator, harvest=False)
    checks["preserves_operator_goal"] = kept.goal == "Operator growth goal."

    def boom(state: Any, prompt: str, turn_dir: Path, **kwargs: Any) -> Any:
        kernel_dir = Path(turn_dir) / "kernel"
        kernel_dir.mkdir(parents=True, exist_ok=True)
        (kernel_dir / "latest-grok-run.json").write_text(
            json.dumps(HARVESTED_GROK_402),
            encoding="utf-8",
        )
        raise RuntimeError("Grok CLI failed with exit code 1; Payment Required usage balance exhausted")

    with tempfile.TemporaryDirectory(prefix="kernel-plane-402-") as tmp:
        repo = Path(tmp)
        _write_mission_plane_ledger(repo)
        state = _State(repo)
        last_meta: dict[str, Any] = {}
        last_decision: Any = None
        last_result: Any = None
        for name in ("turn-1", "turn-2", "turn-3", "turn-4"):
            state.kernel = "grok"
            last_result, last_decision, last_meta = execute_kernel_turn_with_salvage(
                state,
                "prompt",
                repo / name,
                kernel_runner=boom,
                installed_kernels=set(),
                persist_health=False,
            )
        artifact = json.loads((repo / "turn-4" / "kernel" / "latest-local-run.json").read_text(encoding="utf-8"))
        after_402 = load_campaign(repo)
    invoked = (artifact.get("report") or {}).get("invoked") or []
    checks["execute_402_then_mission_plane"] = (
        last_meta.get("source") == "failover"
        and invoked
        and invoked[0]["capability_id"] == "capability.fixture-mission-plane-d"
        and invoked[0]["ok"] is True
        and "capability.fixture-mission-plane-d" in after_402.completed_ids
        and bool(getattr(last_decision, "capability_delta", ""))
        and last_decision.done_when_met is True
        and last_result.kernel == "local"
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    with tempfile.TemporaryDirectory(prefix="kernel-plane-empty-") as tmp:
        empty_root = Path(tmp)
        empty_tick = local_mission_tick(_State(empty_root), empty_root)
    checks["empty_ledger_continues"] = (
        empty_tick.get("ok") is True
        and empty_tick.get("status") == "continue"
        and empty_tick.get("invoked") == []
        and any("ledger_count=0" in item for item in empty_tick.get("outcome_evidence") or [])
    )

    ok = all(checks.values())
    return {
        "ok": ok,
        "action": "kernel_mission_plane",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }
