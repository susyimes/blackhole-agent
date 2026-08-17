"""Bounded succession past cheap-anchor rotation after a 402-class death.

The harvested leftover from the local-capability-kernel mission: once preferred
anchors rotate, local ticks reuse completed inventory. Resume hydrates goal
text but does not continue a broader program. Experience harvest then goes
dark after a successful-repair streak, so the next genesis invents.

This plane compiles a bounded goal-conditioned program of proved python leaves
the cheap selector refuses, executes the next step in-process, persists that
program on the durable campaign, and lets a recovered kernel continue remaining
steps instead of inventing genesis.
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
from blackhole_agent.local_capability_kernel import (
    LOCAL_DENYLIST,
    PREFERRED_LOCAL_IDS,
    _EXPENSIVE_MARKERS,
    invoke_local_capability,
    is_safe_local_capability,
    load_tick_ledger,
)
from blackhole_agent.local_mission_sovereignty import (
    LocalCampaign,
    campaign_handoff,
    durable_campaign_root,
    load_campaign,
    plan_campaign_program,
    save_campaign,
)

SUCCESSION_DONE_WHEN = (
    "capability_exists:capability.kernel-succession;"
    "capability_proved:capability.kernel-succession;"
    "no_skill_route"
)
SUCCESSION_GOAL = (
    "When cheap local-anchor rotation is exhausted after a 402-class kernel death, "
    "escalate to a bounded succession program of proved python leaves the cheap "
    "selector refuses, persist remaining steps on the durable campaign, and let a "
    "recovered first-class kernel continue that program instead of inventing genesis."
)

SUCCESSION_DENYLIST = frozenset(
    {
        *LOCAL_DENYLIST,
        "capability.kernel-succession",
    }
)


def is_succession_capability(capability: Capability) -> bool:
    """True for proved-or-fixture python leaves the cheap local selector refuses."""

    if capability.id in SUCCESSION_DENYLIST:
        return False
    if capability.kind != "python" or ":" not in (capability.entry or ""):
        return False
    if any(marker in capability.id for marker in _EXPENSIVE_MARKERS):
        return False
    if is_safe_local_capability(capability):
        return False
    return True


def cheap_remaining(campaign: LocalCampaign) -> list[str]:
    completed = {item for item in campaign.completed_ids if item}
    return [
        item
        for item in campaign.program[campaign.cursor :]
        if item and item not in completed
    ]


def cheap_rotation_exhausted(campaign: LocalCampaign, ledger: CapabilityLedger) -> bool:
    """Cheap campaign has no unused step left; a replan would only reuse completed ids."""

    if cheap_remaining(campaign):
        return False
    if not campaign.completed_ids and int(campaign.tick_count or 0) <= 0:
        return False
    replanned = plan_campaign_program(
        ledger,
        campaign.goal,
        skip_ids=tuple(campaign.completed_ids),
    )
    if not replanned:
        return True
    completed = {item for item in campaign.completed_ids if item}
    return all(item in completed for item in replanned)


def plan_succession_program(
    ledger: CapabilityLedger,
    goal: str,
    *,
    skip_ids: tuple[str, ...] = (),
    max_steps: int = 4,
) -> list[str]:
    """Bounded goal-conditioned program over leaves cheap rotation will not pick."""

    skipped = {item for item in skip_ids if item}
    planned = plan_capability_program(ledger, goal or "", max_steps=max(4, max_steps))
    ordered: list[str] = []
    for capability_id in list(planned.get("steps") or []):
        capability = ledger.capabilities.get(capability_id)
        if capability is None or capability_id in skipped:
            continue
        if is_succession_capability(capability) and capability_id not in ordered:
            ordered.append(capability_id)
        if len(ordered) >= max(1, int(max_steps)):
            return ordered
    proved = sorted(
        item_id
        for item_id, item in ledger.capabilities.items()
        if is_succession_capability(item)
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
        if is_succession_capability(item) and item_id not in skipped and item_id not in ordered
    )
    for item_id in rest:
        ordered.append(item_id)
        if len(ordered) >= max(1, int(max_steps)):
            break
    return ordered


def select_succession_step(
    ledger: CapabilityLedger,
    campaign: LocalCampaign,
    *,
    goal: str = "",
) -> str:
    skip = tuple(
        dict.fromkeys([*campaign.completed_ids, *campaign.failed_ids, *PREFERRED_LOCAL_IDS])
    )
    program = plan_succession_program(ledger, goal or campaign.goal, skip_ids=skip)
    return program[0] if program else ""


def attach_succession_step(
    campaign: LocalCampaign,
    ledger: CapabilityLedger,
    *,
    goal: str = "",
) -> str:
    """Append the next succession leaf to the durable campaign program."""

    existing = cheap_remaining(campaign)
    if existing:
        return existing[0]
    step = select_succession_step(ledger, campaign, goal=goal)
    if not step:
        return ""
    if step not in campaign.program:
        campaign.program.append(step)
    return step


def continue_resumed_succession(
    state: Any,
    repo_path: Path | None = None,
    workspace: Path | None = None,
) -> dict[str, Any]:
    """When cheap rotation is exhausted, attach a succession step for the recovered kernel."""

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
    if not cheap_rotation_exhausted(campaign, ledger):
        remaining = cheap_remaining(campaign)
        return {
            "applied": False,
            "reason": "cheap_remaining",
            "step": remaining[0] if remaining else "",
            "program": list(campaign.program),
        }
    before = list(campaign.program)
    step = attach_succession_step(campaign, ledger, goal=campaign.goal)
    if not step:
        return {
            "applied": False,
            "reason": "no_succession_step",
            "step": "",
            "program": list(campaign.program),
        }
    campaign.handoff = campaign_handoff(campaign)
    campaign.handoff["succession_step"] = step
    save_campaign(durable, campaign)
    return {
        "applied": campaign.program != before or step in campaign.program,
        "reason": "succession_attached",
        "step": step,
        "program": list(campaign.program),
    }


def invoke_succession_step(
    ledger: CapabilityLedger,
    campaign: LocalCampaign,
    capability_id: str,
) -> dict[str, Any]:
    capability = ledger.capabilities.get(capability_id)
    if capability is None:
        result = {
            "capability_id": capability_id,
            "ok": False,
            "exit_code": 1,
            "kind": "python-inprocess",
            "summary": "capability missing from ledger",
            "entry": "",
        }
        campaign.failed_ids.append(capability_id)
        return result
    try:
        result = invoke_local_capability(capability)
    except Exception as error:  # noqa: BLE001 - succession must still emit a decision
        result = {
            "capability_id": capability_id,
            "ok": False,
            "exit_code": 1,
            "kind": "python-inprocess",
            "summary": str(error)[:400],
            "entry": capability.entry,
        }
    if result.get("ok"):
        if capability_id not in campaign.completed_ids:
            campaign.completed_ids.append(capability_id)
    elif capability_id not in campaign.failed_ids:
        campaign.failed_ids.append(capability_id)
    return result


def builtin_fixture_succession() -> dict[str, Any]:
    """Hermetic leaf used by the succession proof ledger."""

    return {"ok": True, "action": "fixture_succession", "probe": "kernel-succession"}


def _write_succession_ledger(root: Path) -> Path:
    from blackhole_agent.local_mission_sovereignty import _write_fixture_ledger
    from blackhole_agent.capability_compounder import default_ledger_path

    path = _write_fixture_ledger(root)
    ledger = load_tick_ledger(root)
    assert ledger is not None
    register_capability(
        ledger,
        Capability(
            id="capability.fixture-succession-c",
            name="Fixture succession C",
            description="Non-cheap leaf the preferred-anchor selector refuses.",
            kind="python",
            entry="blackhole_agent.kernel_succession:builtin_fixture_succession",
            proof_command="uv run python -c \"print('ok')\"",
            last_proof_exit_code=0,
        ),
        replace=True,
    )
    save_ledger(path, ledger)
    return default_ledger_path(root)


def builtin_kernel_succession_proof() -> dict[str, Any]:
    """Hermetic proof: cheap rotation exhaustion escalates; recovered kernels continue."""

    import json
    import tempfile

    from blackhole_agent.experience_fuel import harvest_experience
    from blackhole_agent.kernel_resume import hydrate_mission_from_campaign
    from blackhole_agent.kernel_salvage import (
        HARVESTED_GROK_402,
        classify_run_artifact,
        execute_kernel_turn_with_salvage,
    )
    from blackhole_agent.local_mission_sovereignty import local_mission_tick
    from blackhole_agent.pattern_register import classify_unbound_turn

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
            done_when: str = "capability_exists:repo.import-health;no_skill_route",
            mission_id: str = "mission-succession",
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

    with tempfile.TemporaryDirectory(prefix="kernel-succ-classify-") as tmp:
        root = Path(tmp)
        _write_succession_ledger(root)
        ledger = load_tick_ledger(root)
        assert ledger is not None
        cheap = ledger.capabilities["capability.fixture-local-a"]
        leaf = ledger.capabilities["capability.fixture-succession-c"]
        checks["succession_accepts_non_cheap_leaf"] = is_succession_capability(leaf) is True
        checks["cheap_refuses_succession_leaf"] = is_safe_local_capability(leaf) is False
        checks["succession_refuses_cheap_anchor"] = is_succession_capability(cheap) is False

        exhausted = LocalCampaign(
            mission_id="mission-succession",
            goal="Keep growing after a 402.",
            done_when="capability_exists:repo.import-health;no_skill_route",
            program=["capability.fixture-local-a", "capability.fixture-local-b"],
            cursor=2,
            completed_ids=["capability.fixture-local-a", "capability.fixture-local-b"],
            tick_count=2,
            last_contract_met=False,
        )
        checks["cheap_exhausted_after_completed_program"] = cheap_rotation_exhausted(
            exhausted, ledger
        )
        fresh = LocalCampaign(goal=exhausted.goal, tick_count=0)
        checks["fresh_campaign_is_not_exhausted"] = cheap_rotation_exhausted(fresh, ledger) is False
        step = select_succession_step(ledger, exhausted, goal=exhausted.goal)
        checks["select_picks_succession_leaf"] = step == "capability.fixture-succession-c"

        first = local_mission_tick(_State(root), root)
        second = local_mission_tick(_State(root), root)
        third = local_mission_tick(_State(root), root)
        first_id = (first.get("invoked") or [{}])[0].get("capability_id")
        second_id = (second.get("invoked") or [{}])[0].get("capability_id")
        third_id = (third.get("invoked") or [{}])[0].get("capability_id")
        persisted = load_campaign(root)
    checks["local_tick_escalates_after_cheap"] = (
        first_id == "capability.fixture-local-a"
        and second_id == "capability.fixture-local-b"
        and third_id == "capability.fixture-succession-c"
        and (third.get("invoked") or [{}])[0].get("ok") is True
        and bool(third.get("capability_delta"))
    )
    checks["campaign_persists_succession_step"] = (
        "capability.fixture-succession-c" in persisted.program
        and "capability.fixture-succession-c" in persisted.completed_ids
        and persisted.tick_count == 3
    )

    with tempfile.TemporaryDirectory(prefix="kernel-succ-resume-") as tmp:
        root = Path(tmp)
        _write_succession_ledger(root)
        unfinished = LocalCampaign(
            mission_id="prior",
            goal="Keep growing after a 402.",
            done_when="capability_exists:repo.import-health;no_skill_route",
            bound_from="harvested_kernel_failure",
            program=["capability.fixture-local-a", "capability.fixture-local-b"],
            cursor=2,
            completed_ids=["capability.fixture-local-a", "capability.fixture-local-b"],
            tick_count=2,
            last_contract_met=False,
            last_summary="cheap rotation exhausted",
        )
        save_campaign(root, unfinished)
        recovered = _State(root, goal="", done_when="", mission_id="recovered")
        hydrate_report = hydrate_mission_from_campaign(recovered, persist=True)
        resumed = load_campaign(root)
        second = continue_resumed_succession(recovered)
    checks["recovered_resume_attaches_succession"] = (
        recovered.goal == unfinished.goal
        and recovered.stage == "execution"
        and hydrate_report.get("applied") is True
        and "capability.fixture-succession-c" in resumed.program
        and (resumed.handoff or {}).get("succession_step") == "capability.fixture-succession-c"
        and second.get("reason") == "cheap_remaining"
        and second.get("step") == "capability.fixture-succession-c"
    )

    with tempfile.TemporaryDirectory(prefix="kernel-succ-fuel-") as tmp:
        root = Path(tmp)
        leftover_dir = root / ".blackhole-agent" / "unbound" / "missions" / "prior-leftover"
        leftover_dir.mkdir(parents=True)
        (leftover_dir / "state.json").write_text(
            json.dumps(
                {
                    "mission_id": "prior-leftover",
                    "status": "complete",
                    "stage": "execution",
                    "goal": "Local kernel executes cheap ledger capabilities.",
                    "done_when": "capability_proved:capability.local-capability-kernel",
                    "next_step": (
                        "Optional follow-on is a bounded mission-plane program on local "
                        "ticks once cheap-anchor rotation is exhausted."
                    ),
                    "last_error": "",
                    "recent_turns": [
                        {
                            "iteration": 1,
                            "effective_status": "complete",
                            "requested_status": "complete",
                            "kernel_salvage": {
                                "ok": True,
                                "class_id": "quota_exhausted",
                                "source": "failover",
                                "evidence": "Grok Build usage balance exhausted",
                            },
                        }
                    ],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        fuel = harvest_experience(root, limit=5)
        class_ids = [item.class_id for item in fuel.candidates]
        salvage_events = classify_unbound_turn(
            {
                "iteration": 13,
                "effective_status": "continue",
                "requested_status": "continue",
                "summary": "local campaign advanced",
                "kernel_salvage": {
                    "ok": True,
                    "class_id": "quota_exhausted",
                    "source": "failover",
                },
            }
        )
    checks["leftover_next_step_harvested"] = any(
        item.class_id == "mission_leftover" for item in fuel.candidates
    ) and any("cheap-anchor rotation" in item.summary for item in fuel.candidates)
    checks["salvage_visible_as_experience"] = "quota_exhausted" in class_ids
    checks["salvage_is_not_kernel_turn_failed"] = not any(
        item.get("class_id") == "kernel_turn_failed" for item in salvage_events
    )

    operator = _State(Path("."), goal="Operator growth goal.")
    from blackhole_agent.local_mission_sovereignty import bind_local_mission

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

    with tempfile.TemporaryDirectory(prefix="kernel-succ-402-") as tmp:
        repo = Path(tmp)
        _write_succession_ledger(repo)
        state = _State(repo)
        for name in ("turn-1", "turn-2", "turn-3"):
            state.kernel = "grok"
            result, decision, meta = execute_kernel_turn_with_salvage(
                state,
                "prompt",
                repo / name,
                kernel_runner=boom,
                installed_kernels=set(),
                persist_health=False,
            )
        artifact = json.loads((repo / "turn-3" / "kernel" / "latest-local-run.json").read_text(encoding="utf-8"))
        after_402 = load_campaign(repo)
    invoked = (artifact.get("report") or {}).get("invoked") or []
    checks["execute_402_then_succession"] = (
        meta.get("source") == "failover"
        and invoked
        and invoked[0]["capability_id"] == "capability.fixture-succession-c"
        and invoked[0]["ok"] is True
        and "capability.fixture-succession-c" in after_402.completed_ids
        and bool(getattr(decision, "capability_delta", ""))
        and result.kernel == "local"
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    return {
        "ok": ok,
        "action": "kernel_succession",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }
