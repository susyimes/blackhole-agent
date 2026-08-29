"""Resume unscoped local campaigns after class_closed empty genesis.

``capability.kernel-class-closure`` correctly stops re-injecting the harvested
402 class once salvage, the breaker, and the local kernel are proved. Local
bind then emits empty goal/done_when (``class_closed``). Local ticks still
advance a cheap program, including remaining steps such as
``capability.ledger-attestation``. ``capability.kernel-resume`` refuses to
hydrate campaigns that lack both goal and done_when, so a recovered kernel
invents genesis. Saturated forage families then trip selection gates and the
mission blocks.

This module scopes that remaining work:

- empty campaigns with leftover program steps get a machine-checkable
  ``program_passes`` contract
- recovered genesis hydrates from that remaining work instead of inventing
- local bind fills class_closed holes from the durable campaign
- a later mission id does not drop remaining campaign progress
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from blackhole_agent.capability_compounder import (
    Capability,
    default_ledger_path,
    legacy_pipeline_was_used,
    load_ledger,
    register_capability,
    save_ledger,
)
from blackhole_agent.kernel_class_closure import (
    CLASS_CLOSURE_REQUIREMENTS,
    KERNEL_TURN_FAILED,
    class_closure_ids,
)
from blackhole_agent.kernel_resume import (
    bind_create_fields,
    campaign_is_resumable,
    hydrate_mission_from_campaign,
)
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST, _write_fixture_ledger
from blackhole_agent.local_mission_sovereignty import (
    LocalCampaign,
    bind_local_mission,
    load_campaign,
    local_mission_tick,
    save_campaign,
)

SCHEMA_VERSION = 1
KERNEL_UNSCOPED_RESUME_ID = "capability.kernel-unscoped-resume"
MISSION_BLOCKED = "mission_blocked"

KERNEL_UNSCOPED_RESUME_DONE_WHEN = (
    f"capability_exists:{KERNEL_UNSCOPED_RESUME_ID};"
    f"capability_proved:{KERNEL_UNSCOPED_RESUME_ID};"
    "no_skill_route"
)
KERNEL_UNSCOPED_RESUME_GOAL = (
    "When kernel_turn_failed is closed, repair blocked genesis: scope remaining "
    "durable campaign work such as capability.ledger-attestation with a "
    "machine-checkable program_passes contract so recovered kernels resume "
    "instead of stalling into blocked status from empty class_closed bind."
)


def remaining_program_steps(campaign: LocalCampaign) -> list[str]:
    """Program steps still ahead of the durable campaign cursor."""

    completed = {item for item in campaign.completed_ids if item}
    cursor = max(0, int(campaign.cursor or 0))
    remaining: list[str] = []
    for item in list(campaign.program[cursor:]):
        step = str(item or "").strip()
        if step and step not in completed and step not in remaining:
            remaining.append(step)
    return remaining


def unscoped_resume_goal(remaining: list[str]) -> str:
    head = remaining[0] if remaining else "remaining campaign work"
    return (
        "Resume remaining durable campaign work after class_closed left genesis "
        f"unscoped: {head}"
    )


def unscoped_resume_done_when(remaining: list[str]) -> str:
    if not remaining:
        return "no_skill_route"
    predicates = ";".join(f"program_passes:{step}" for step in remaining)
    return f"{predicates};no_skill_route"


def campaign_is_unscoped(campaign: LocalCampaign) -> bool:
    return not str(campaign.goal or "").strip() or not str(campaign.done_when or "").strip()


def scope_unscoped_campaign(campaign: LocalCampaign) -> bool:
    """Fill empty goal/done_when from remaining program steps. Mutates campaign."""

    if int(campaign.tick_count or 0) <= 0:
        return False
    if str(campaign.consumed_at or "").strip():
        return False
    if campaign.last_contract_met is True:
        return False
    remaining = remaining_program_steps(campaign)
    if not remaining:
        return bool(str(campaign.goal or "").strip() and str(campaign.done_when or "").strip())
    if not str(campaign.goal or "").strip():
        campaign.goal = unscoped_resume_goal(remaining)
    if not str(campaign.done_when or "").strip():
        campaign.done_when = unscoped_resume_done_when(remaining)
    return bool(str(campaign.goal or "").strip() and str(campaign.done_when or "").strip())


def campaign_has_unscoped_remaining(campaign: LocalCampaign) -> bool:
    if int(campaign.tick_count or 0) <= 0:
        return False
    if str(campaign.consumed_at or "").strip() or campaign.last_contract_met is True:
        return False
    return bool(remaining_program_steps(campaign))


def should_preserve_campaign(
    campaign: LocalCampaign,
    *,
    mission_id: str,
    goal: str,
) -> bool:
    """Keep remaining durable work when a recovered mission continues it."""

    if int(campaign.tick_count or 0) <= 0:
        return False
    if str(campaign.consumed_at or "").strip() or campaign.last_contract_met is True:
        return False
    remaining = remaining_program_steps(campaign)
    resumed_here = str(campaign.resumed_by_mission_id or "") == str(mission_id or "")
    if not remaining and not resumed_here:
        return False
    existing_goal = str(campaign.goal or "").strip()
    incoming = str(goal or "").strip()
    if incoming and existing_goal and incoming != existing_goal:
        return resumed_here
    return True


def bind_from_unscoped_campaign(root: Path, *, persist: bool = True) -> tuple[str, str, str]:
    """Scope and return remaining campaign fields. Empty source when nothing to resume."""

    campaign = load_campaign(Path(root))
    if not scope_unscoped_campaign(campaign):
        return "", "", ""
    if persist:
        save_campaign(Path(root), campaign)
    return campaign.goal, campaign.done_when, "unscoped_campaign"


def _register_turn_failed_closers(root: Path) -> None:
    path = default_ledger_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    ledger = load_ledger(path) if path.is_file() else None
    if ledger is None:
        from blackhole_agent.capability_compounder import CapabilityLedger

        ledger = CapabilityLedger()
    for capability_id in CLASS_CLOSURE_REQUIREMENTS[KERNEL_TURN_FAILED]:
        register_capability(
            ledger,
            Capability(
                id=capability_id,
                name=capability_id,
                description="Proved structural closer for a harvested operational class.",
                kind="python",
                entry="blackhole_agent.local_capability_kernel:builtin_fixture_probe",
                proof_command="uv run python -c \"print('ok')\"",
                last_proof_exit_code=0,
            ),
            replace=True,
        )
    save_ledger(path, ledger)


class _State:
    def __init__(
        self,
        repo: Path,
        *,
        goal: str = "",
        done_when: str = "",
        mission_id: str = "mission-unscoped",
        stage: str = "genesis",
    ) -> None:
        self.kernel = "grok"
        self.session_id = "sess"
        self.session_started = True
        self.repo_path = str(repo)
        self.workspace_path = str(repo)
        self.goal = goal
        self.done_when = done_when
        self.mission_id = mission_id
        self.stage = stage


def _unscoped_fixture_campaign() -> LocalCampaign:
    return LocalCampaign(
        mission_id="prior-unscoped",
        goal="",
        done_when="",
        bound_from="class_closed",
        program=["capability.fixture-local-a", "capability.fixture-local-b"],
        cursor=1,
        completed_ids=["capability.fixture-local-a"],
        tick_count=3,
        last_contract_met=None,
        last_summary=(
            "Local mission sovereignty executed capability.fixture-local-a toward "
            "the bound mission without a first-class kernel."
        ),
    )


def builtin_kernel_unscoped_resume_proof() -> dict[str, Any]:
    """Hermetic proof: class_closed remaining work is scoped and resumable."""

    from blackhole_agent.kernel_leftover import leftover_marker_ids
    from blackhole_agent.kernel_resume import campaign_is_resumable as resume_is_resumable

    checks: dict[str, bool] = {}
    checks["denylists_self"] = KERNEL_UNSCOPED_RESUME_ID in LOCAL_DENYLIST
    checks["closes_mission_blocked"] = class_closure_ids(MISSION_BLOCKED) == (
        KERNEL_UNSCOPED_RESUME_ID,
    )
    checks["leftover_marker"] = KERNEL_UNSCOPED_RESUME_ID in leftover_marker_ids(
        "Local mission sovereignty executed a bound campaign without a first-class kernel."
    )  # "without a first-class" is the durable leftover marker

    unscoped = _unscoped_fixture_campaign()
    checks["remaining_steps"] = remaining_program_steps(unscoped) == ["capability.fixture-local-b"]
    checks["unscoped_predicate"] = campaign_is_unscoped(unscoped) is True
    checks["resume_sees_remaining"] = resume_is_resumable(unscoped) is True
    checks["empty_without_remaining_not_resumable"] = resume_is_resumable(
        LocalCampaign(tick_count=2, goal="", done_when="", program=[], cursor=0)
    ) is False
    checks["met_contract_not_resumable"] = resume_is_resumable(
        LocalCampaign(
            tick_count=4,
            goal="",
            done_when="",
            program=["capability.fixture-local-b"],
            cursor=0,
            last_contract_met=True,
        )
    ) is False

    scoped = _unscoped_fixture_campaign()
    checks["scope_fills_contract"] = (
        scope_unscoped_campaign(scoped) is True
        and "capability.fixture-local-b" in scoped.goal
        and scoped.done_when == "program_passes:capability.fixture-local-b;no_skill_route"
    )

    with tempfile.TemporaryDirectory(prefix="kernel-unscoped-hydrate-") as tmp:
        root = Path(tmp)
        save_campaign(root, _unscoped_fixture_campaign())
        empty = _State(root)
        report = hydrate_mission_from_campaign(empty, persist=True)
        reloaded = load_campaign(root)
    checks["hydrate_fills_empty_genesis"] = (
        report["applied"] is True
        and "capability.fixture-local-b" in empty.goal
        and "program_passes:capability.fixture-local-b" in empty.done_when
        and empty.stage == "execution"
        and reloaded.resumed_by_mission_id == "mission-unscoped"
        and "program_passes:capability.fixture-local-b" in reloaded.done_when
    )

    keep = _State(Path("."), goal="Operator growth goal.")
    hydrate_mission_from_campaign(keep, repo_path=Path("."))
    checks["preserves_operator_goal"] = keep.goal == "Operator growth goal."

    with tempfile.TemporaryDirectory(prefix="kernel-unscoped-create-") as tmp:
        root = Path(tmp)
        save_campaign(root, _unscoped_fixture_campaign())
        bound_goal, bound_done, bound_source = bind_create_fields(root)
    checks["create_bind_uses_remaining"] = (
        "capability.fixture-local-b" in bound_goal
        and "program_passes:capability.fixture-local-b" in bound_done
        and bound_source == "local_campaign"
    )

    create_goal, create_done, create_source = bind_create_fields(
        Path("."), "Operator growth goal.", "already-bound"
    )
    checks["create_bind_keeps_operator"] = (
        create_goal == "Operator growth goal."
        and create_done == "already-bound"
        and create_source == "operator"
    )

    with tempfile.TemporaryDirectory(prefix="kernel-unscoped-bind-") as tmp:
        root = Path(tmp)
        _write_fixture_ledger(root)
        _register_turn_failed_closers(root)
        save_campaign(root, _unscoped_fixture_campaign())
        binding = bind_local_mission(_State(root), harvest=True)
    checks["class_closed_bind_fills_remaining"] = (
        "capability.fixture-local-b" in binding.goal
        and "program_passes:capability.fixture-local-b" in binding.done_when
        and "unscoped_campaign" in binding.source
    )

    with tempfile.TemporaryDirectory(prefix="kernel-unscoped-empty-") as tmp:
        root = Path(tmp)
        _write_fixture_ledger(root)
        _register_turn_failed_closers(root)
        binding_empty = bind_local_mission(_State(root), harvest=True)
    checks["class_closed_stays_empty_without_campaign"] = (
        binding_empty.goal == ""
        and binding_empty.done_when == ""
        and binding_empty.source == "class_closed"
    )

    with tempfile.TemporaryDirectory(prefix="kernel-unscoped-preserve-") as tmp:
        root = Path(tmp)
        _write_fixture_ledger(root)
        _register_turn_failed_closers(root)
        save_campaign(root, _unscoped_fixture_campaign())
        tick = local_mission_tick(_State(root, mission_id="recovered-mission"), root)
        after = load_campaign(root)
    invoked = [item.get("capability_id") for item in list(tick.get("invoked") or [])]
    checks["tick_preserves_remaining_across_mission"] = (
        after.tick_count >= 4
        and "capability.fixture-local-a" in after.completed_ids
        and "capability.fixture-local-b" in invoked
        and "capability.fixture-local-b" in after.completed_ids
        and "program_passes:capability.fixture-local-b" in after.done_when
    )

    with tempfile.TemporaryDirectory(prefix="kernel-unscoped-operator-") as tmp:
        root = Path(tmp)
        _write_fixture_ledger(root)
        _register_turn_failed_closers(root)
        save_campaign(root, _unscoped_fixture_campaign())
        kept = bind_local_mission(
            _State(root, goal="Operator growth goal.", done_when="capability_exists:repo.import-health"),
            harvest=True,
        )
    checks["preserves_operator_bind"] = (
        kept.goal == "Operator growth goal." and "state.goal" in kept.source
    )

    prior = _unscoped_fixture_campaign()
    checks["preserve_remaining"] = should_preserve_campaign(
        prior, mission_id="other", goal=""
    ) is True
    finished = LocalCampaign(
        tick_count=4,
        consumed_at="2026-08-29T00:00:00Z",
        program=["capability.fixture-local-b"],
        cursor=0,
    )
    checks["preserve_skips_consumed"] = should_preserve_campaign(
        finished, mission_id="other", goal=""
    ) is False
    checks["no_skill_route"] = not legacy_pipeline_was_used()
    checks["schema_version"] = SCHEMA_VERSION == 1

    ok = all(checks.values())
    return {
        "ok": ok,
        "action": "kernel_unscoped_resume",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": KERNEL_UNSCOPED_RESUME_GOAL,
        "done_when": KERNEL_UNSCOPED_RESUME_DONE_WHEN,
    }
