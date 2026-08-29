"""Promote a ready composed program after unique composition coverage saturates.

``capability.kernel-primitive-compose`` promotes consecutive-pair compositions
of novelty-ranked primitive leaves. Once those compositions fill unique
coverage, recovered kernels and 402-local ticks fall back to cheap inventory.
Program compounding stalls on saturated compositions.

This module closes that hole:

- detect when in-process multi-primitive compositions saturate unique
  coverage, or genesis is bound to this closer
- rank ready composed programs (stacks of promoted compositions) by
  coverage novelty
- promote and prove the top novel program in-process
- attach it to the durable campaign so the next local tick stacks programs
- skip a proved catalog item to the next genesis-bind successor so genesis
  cannot go empty again
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from blackhole_agent.capability_compounder import (
    ACTIVE_CAPABILITY_ENV,
    Capability,
    CapabilityLedger,
    annotate_opportunities_with_novelty,
    default_ledger_path,
    is_primitive_capability,
    legacy_pipeline_was_used,
    rank_growth_opportunities,
    register_capability,
    save_ledger,
    utc_now_iso,
)
from blackhole_agent.kernel_compound_loop import (
    COMPOUND_LOOP_LEAF_PREFIX,
    bound_to_composed_program,
    bound_to_program_stack,
    is_compound_loop_leaf_id,
)
from blackhole_agent.kernel_consumed_growth import is_cheap_inventory_id
from blackhole_agent.kernel_genesis_bind import (
    COMPOSED_PROGRAM_DONE_WHEN,
    COMPOSED_PROGRAM_GOAL,
    COMPOSED_PROGRAM_ID,
    COMPOUND_LOOP_ID,
    CONSUMED_GROWTH_ID,
    KERNEL_GENESIS_BIND_ID,
    PRIMITIVE_COMPOSE_ID,
    PROGRAM_STACK_DONE_WHEN,
    PROGRAM_STACK_GOAL,
    PROGRAM_STACK_ID,
)
from blackhole_agent.kernel_primitive_compose import (
    PRIMITIVE_COMPOSE_UNIT_PREFIX,
    composition_unique_coverage_is_saturated,
    compose_member_ids,
    is_primitive_compose_id,
    saturate_primitive_compositions,
    saturate_primitive_leaves,
)
from blackhole_agent.kernel_succession import cheap_remaining
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST, invoke_local_capability
from blackhole_agent.local_mission_sovereignty import LocalCampaign

SCHEMA_VERSION = 1
KERNEL_COMPOSED_PROGRAM_ID = COMPOSED_PROGRAM_ID
KERNEL_COMPOSED_PROGRAM_DONE_WHEN = COMPOSED_PROGRAM_DONE_WHEN
KERNEL_COMPOSED_PROGRAM_GOAL = COMPOSED_PROGRAM_GOAL

COMPOSED_PROGRAM_UNIT_PREFIX = "capability.composed-program"
COMPOSED_PROGRAM_TAG = "composed-program-unit"

UNIT_PROOF_COMMAND = (
    "uv run python -c \"from blackhole_agent.kernel_composed_program import "
    "builtin_execute_composed_capability; r=builtin_execute_composed_capability(); "
    "assert r['ok']\""
)


def is_composed_program_id(capability_id: str) -> bool:
    """True for composed-program units minted by this closer."""

    item = str(capability_id or "").strip()
    return item.startswith(f"{COMPOSED_PROGRAM_UNIT_PREFIX}-")


def program_id_from_members(members: tuple[str, ...]) -> str:
    prefix = f"{PRIMITIVE_COMPOSE_UNIT_PREFIX}-"
    suffixes: list[str] = []
    for item in members:
        raw = str(item or "").strip()
        if not raw.startswith(prefix):
            return ""
        suffixes.append(raw[len(prefix) :])
    if len(suffixes) < 2:
        return ""
    return f"{COMPOSED_PROGRAM_UNIT_PREFIX}-{'__'.join(suffixes)}"


def program_member_ids(program_id: str) -> tuple[str, ...]:
    item = str(program_id or "").strip()
    prefix = f"{COMPOSED_PROGRAM_UNIT_PREFIX}-"
    if not item.startswith(prefix):
        return ()
    parts = [part for part in item[len(prefix) :].split("__") if part]
    members = tuple(f"{PRIMITIVE_COMPOSE_UNIT_PREFIX}-{part}" for part in parts)
    if len(members) < 2:
        return ()
    if any(not compose_member_ids(member) for member in members):
        return ()
    return members


def builtin_execute_composed_capability() -> dict[str, Any]:
    """Hermetic in-process program of promoted multi-primitive compositions.

    Named ``builtin_execute_composed_capability`` so coverage scoring treats
    the unit as a composition rather than another primitive leaf.
    """

    from blackhole_agent.kernel_primitive_compose import (
        builtin_execute_composed_capability as execute_composition,
    )

    cap_id = (os.environ.get(ACTIVE_CAPABILITY_ENV) or "").strip()
    members = program_member_ids(cap_id)
    if len(members) < 2:
        members = (
            f"{PRIMITIVE_COMPOSE_UNIT_PREFIX}-1-2",
            f"{PRIMITIVE_COMPOSE_UNIT_PREFIX}-2-3",
        )
    results: list[dict[str, Any]] = []
    saved = os.environ.get(ACTIVE_CAPABILITY_ENV)
    try:
        for member in members:
            os.environ[ACTIVE_CAPABILITY_ENV] = member
            results.append(execute_composition())
    finally:
        if saved is None:
            os.environ.pop(ACTIVE_CAPABILITY_ENV, None)
        else:
            os.environ[ACTIVE_CAPABILITY_ENV] = saved
    ok = all(bool(item.get("ok")) for item in results)
    return {
        "ok": ok,
        "action": "composed_program_unit",
        "capability_id": cap_id,
        "members": list(members),
        "member_count": len(members),
        "used_skill_route_discovery": False,
    }


def composed_program_is_needed(
    campaign: LocalCampaign,
    ledger: CapabilityLedger,
    *,
    goal: str = "",
    done_when: str = "",
    bind_source: str = "",
) -> bool:
    """True when saturated composition coverage (or this closer) would otherwise idle."""

    try:
        from blackhole_agent.kernel_unscoped_resume import (
            campaign_has_unscoped_remaining,
            remaining_program_steps,
        )

        if campaign_has_unscoped_remaining(campaign):
            leftover = remaining_program_steps(campaign)
            if leftover and not all(
                is_cheap_inventory_id(item)
                or is_compound_loop_leaf_id(item)
                or is_primitive_compose_id(item)
                or is_composed_program_id(item)
                for item in leftover
            ):
                return False
    except Exception:  # noqa: BLE001 - program closer must still decide from campaign fields
        pass
    live_goal = str(goal or campaign.goal or "")
    live_done = str(done_when or campaign.done_when or "")
    source = str(bind_source or campaign.bound_from or "")
    scoped = bound_to_composed_program(live_goal, live_done, source)
    saturated = composition_unique_coverage_is_saturated(ledger, campaign)
    if not saturated:
        return False
    stack_bound = bound_to_program_stack(live_goal, live_done, source)
    if stack_bound and program_unique_coverage_is_saturated(ledger, campaign):
        return False
    if not scoped and not saturated:
        return False
    remaining = cheap_remaining(campaign)
    if remaining:
        capability = ledger.capabilities.get(remaining[0])
        if capability is not None and COMPOSED_PROGRAM_TAG in capability.tags:
            return True
        if is_composed_program_id(remaining[0]):
            return True
        return is_cheap_inventory_id(remaining[0])
    return True


def _program_candidates(ledger: CapabilityLedger) -> list[tuple[str, tuple[str, ...]]]:
    proved = sorted(
        (
            item_id
            for item_id, item in ledger.capabilities.items()
            if is_primitive_compose_id(item_id) and item.last_proof_exit_code == 0
        ),
        key=lambda item_id: (compose_member_ids(item_id), item_id),
    )
    seen: set[str] = set()
    recipes: list[tuple[str, tuple[str, ...]]] = []

    def _push(members: tuple[str, ...]) -> None:
        if len(members) < 2:
            return
        program_id = program_id_from_members(members)
        if not program_id or program_id in seen:
            return
        seen.add(program_id)
        recipes.append((program_id, members))

    for index in range(len(proved) - 1):
        _push((proved[index], proved[index + 1]))
    return recipes


def rank_ready_composed_programs(
    ledger: CapabilityLedger,
    *,
    skip_ids: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    """Rank ready composed programs by unique coverage novelty."""

    skipped = {item for item in skip_ids if item}
    opportunities: list[dict[str, Any]] = []
    for program_id, members in _program_candidates(ledger):
        if program_id in skipped:
            continue
        missing = [item for item in members if item not in ledger.capabilities]
        exists = program_id in ledger.capabilities
        if missing:
            status = "blocked_missing_members"
        elif exists:
            status = "already_promoted"
        else:
            status = "ready"
        opportunities.append(
            {
                "kind": "composition",
                "status": status,
                "suggested_id": program_id,
                "members": list(members),
                "priority": 1000 - 10 * len(members),
                "tags": ["composed", "promoted", "growth", "program"],
                "synthesis": "program",
            }
        )
    annotate_opportunities_with_novelty(ledger, opportunities)
    return rank_growth_opportunities(opportunities)


def program_unique_coverage_is_saturated(
    ledger: CapabilityLedger,
    campaign: LocalCampaign | None = None,
) -> bool:
    """True when no novelty-ranked composed program remains to promote."""

    _ = campaign  # coverage is a ledger property; campaign completion is orthogonal
    ranked = rank_ready_composed_programs(ledger)
    has_novel = any(
        item.get("novel") and item.get("status") == "ready" for item in ranked
    )
    if has_novel:
        return False
    proved = [
        item_id
        for item_id, item in ledger.capabilities.items()
        if is_composed_program_id(item_id) and item.last_proof_exit_code == 0
    ]
    return len(proved) >= 2


def select_composed_program(
    ledger: CapabilityLedger,
    campaign: LocalCampaign,
) -> str:
    """Pick an unfinished in-ledger program, else the top novel recipe."""

    skip = {item for item in [*campaign.completed_ids, *campaign.failed_ids] if item}
    existing = [
        item_id
        for item_id, item in ledger.capabilities.items()
        if COMPOSED_PROGRAM_TAG in item.tags and item_id not in skip
    ]
    if existing:
        existing.sort(
            key=lambda item_id: (
                0 if ledger.capabilities[item_id].last_proof_exit_code != 0 else 1,
                item_id,
            )
        )
        return existing[0]
    for item in rank_ready_composed_programs(ledger, skip_ids=tuple(skip)):
        program_id = str(item.get("suggested_id") or "").strip()
        if not program_id or program_id in skip:
            continue
        if item.get("novel") and item.get("status") == "ready":
            return program_id
    return ""


def _program_spec(ledger: CapabilityLedger, program_id: str, members: tuple[str, ...]) -> Capability:
    _ = ledger
    suffixes = []
    prefix = f"{PRIMITIVE_COMPOSE_UNIT_PREFIX}-"
    for item in members:
        raw = str(item)
        suffixes.append(raw[len(prefix) :] if raw.startswith(prefix) else raw)
    label = "+".join(suffixes)  # human label; ids join members with __
    return Capability(
        id=program_id,
        name=f"Composed program {label}",
        description=(
            "In-process composed program promoted when unique multi-primitive "
            "composition coverage saturates and program compounding would "
            "otherwise stall."
        ),
        kind="python",
        entry="blackhole_agent.kernel_composed_program:builtin_execute_composed_capability",
        proof_command=UNIT_PROOF_COMMAND,
        dependencies=tuple(members),
        behavior_paths=("src/blackhole_agent/kernel_composed_program.py",),
        capability_delta=(
            "Ready composed programs promote in-process instead of rotating "
            "cheap inventory after unique composition coverage saturates."
        ),
        tags=(COMPOSED_PROGRAM_TAG, "composed", "promoted", "growth", "kernel", "program"),
    )


def _stamp_proved(ledger: CapabilityLedger, capability: Capability, *, exit_code: int) -> None:
    now = utc_now_iso()
    ledger.capabilities[capability.id] = Capability(
        id=capability.id,
        name=capability.name,
        description=capability.description,
        kind=capability.kind,
        entry=capability.entry,
        proof_command=capability.proof_command,
        dependencies=capability.dependencies,
        behavior_paths=capability.behavior_paths,
        capability_delta=capability.capability_delta,
        tags=capability.tags,
        created_at=capability.created_at or now,
        updated_at=now,
        source_mission_id=capability.source_mission_id,
        source_milestone=capability.source_milestone,
        last_proved_at=now,
        last_proof_exit_code=int(exit_code),
    )
    ledger.updated_at = now


def promote_and_prove_composed_program(
    root: Path,
    ledger: CapabilityLedger,
    program_id: str,
) -> str:
    """Register the ranked program if missing and stamp an in-process proof."""

    members = program_member_ids(program_id)
    if len(members) < 2:
        return ""
    missing = [item for item in members if item not in ledger.capabilities]
    if missing:
        return ""
    existing = ledger.capabilities.get(program_id)
    if existing is None:
        register_capability(ledger, _program_spec(ledger, program_id, members), replace=False)
        existing = ledger.capabilities[program_id]
    if existing.last_proof_exit_code != 0:
        result = invoke_local_capability(existing)
        if not result.get("ok"):
            return ""
        _stamp_proved(ledger, existing, exit_code=0)
        existing = ledger.capabilities[program_id]
    path = default_ledger_path(Path(root))
    path.parent.mkdir(parents=True, exist_ok=True)
    save_ledger(path, ledger)
    proved = ledger.capabilities.get(program_id)
    if proved is None or proved.last_proof_exit_code != 0:
        return ""
    if is_primitive_capability(proved):
        return ""
    return program_id


def saturate_composed_programs(
    root: Path,
    ledger: CapabilityLedger,
    campaign: LocalCampaign,
) -> list[str]:
    """Promote every remaining novel consecutive-pair composed program."""

    promoted: list[str] = []
    skip = {item for item in [*campaign.completed_ids, *campaign.failed_ids] if item}
    while True:
        program_id = ""
        for item in rank_ready_composed_programs(ledger, skip_ids=tuple(skip)):
            candidate = str(item.get("suggested_id") or "").strip()
            if not candidate or candidate in skip:
                continue
            if item.get("novel") and item.get("status") == "ready":
                program_id = candidate
                break
        if not program_id:
            return promoted
        proved = promote_and_prove_composed_program(Path(root), ledger, program_id)
        if not proved:
            return promoted
        promoted.append(proved)
        skip.add(proved)
        if proved not in campaign.completed_ids:
            campaign.completed_ids.append(proved)


def attach_composed_program(
    campaign: LocalCampaign,
    ledger: CapabilityLedger,
    root: Path,
    *,
    goal: str = "",
    done_when: str = "",
    bind_source: str = "",
) -> str:
    """Promote the next novel composed program and make it the next campaign step."""

    remaining = cheap_remaining(campaign)
    if remaining:
        capability = ledger.capabilities.get(remaining[0])
        if capability is not None and COMPOSED_PROGRAM_TAG in capability.tags:
            return remaining[0]
        if is_composed_program_id(remaining[0]):
            return remaining[0]
        if not is_cheap_inventory_id(remaining[0]):
            return ""
    if not composed_program_is_needed(
        campaign,
        ledger,
        goal=goal,
        done_when=done_when,
        bind_source=bind_source,
    ):
        return ""
    program_id = select_composed_program(ledger, campaign)
    if not program_id:
        return ""
    promoted = promote_and_prove_composed_program(Path(root), ledger, program_id)
    if not promoted:
        return ""
    campaign.program = [
        item
        for item in campaign.program
        if item
        and item not in campaign.completed_ids
        and not is_cheap_inventory_id(item)
        and not is_compound_loop_leaf_id(item)
        and not is_primitive_compose_id(item)
    ]
    if promoted not in campaign.program:
        campaign.program.append(promoted)
    campaign.cursor = campaign.program.index(promoted) + 1
    handoff = dict(campaign.handoff or {})
    handoff["composed_program_unit"] = promoted
    campaign.handoff = handoff
    return promoted


def continue_resumed_composed_program(
    state: Any,
    repo_path: Path | None = None,
    workspace: Path | None = None,
) -> dict[str, Any]:
    """When unique composition coverage saturates, attach a composed program."""

    from blackhole_agent.kernel_resume import campaign_is_resumable
    from blackhole_agent.local_capability_kernel import load_tick_ledger
    from blackhole_agent.local_mission_sovereignty import durable_campaign_root, load_campaign, save_campaign

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
    before = list(campaign.program)
    step = attach_composed_program(
        campaign,
        ledger,
        work,
        goal=str(getattr(state, "goal", "") or campaign.goal),
        done_when=str(getattr(state, "done_when", "") or campaign.done_when),
    )
    if not step:
        return {
            "applied": False,
            "reason": "no_composed_program",
            "step": "",
            "program": list(campaign.program),
        }
    if before != list(campaign.program):
        save_campaign(durable, campaign)
    return {
        "applied": True,
        "reason": "composed_program",
        "step": step,
        "program": list(campaign.program),
    }


def builtin_kernel_composed_program_proof() -> dict[str, Any]:
    """Hermetic proof: saturated composition coverage promotes a composed program."""

    import tempfile

    from blackhole_agent.capability_compounder import (
        existing_composed_coverage_sets,
        primitive_coverage,
    )
    from blackhole_agent.kernel_compound_loop import compound_loop_is_needed
    from blackhole_agent.kernel_genesis_bind import (
        _consumed_campaign,
        _register_proved,
        _unscoped_remaining_campaign,
        _write_forage_history,
        bind_gate_passing_successor,
    )
    from blackhole_agent.kernel_leftover import leftover_marker_ids
    from blackhole_agent.kernel_primitive_compose import primitive_compose_is_needed
    from blackhole_agent.kernel_resume import bind_create_fields, hydrate_mission_from_campaign
    from blackhole_agent.kernel_unscoped_resume import _register_turn_failed_closers
    from blackhole_agent.local_capability_kernel import _write_fixture_ledger, load_tick_ledger
    from blackhole_agent.local_mission_sovereignty import (
        bind_local_mission,
        load_campaign,
        local_mission_tick,
        save_campaign,
    )

    checks: dict[str, bool] = {}
    checks["denylists_self"] = KERNEL_COMPOSED_PROGRAM_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = KERNEL_COMPOSED_PROGRAM_ID in leftover_marker_ids(
        KERNEL_COMPOSED_PROGRAM_GOAL
    )
    first_leaf = f"{COMPOUND_LOOP_LEAF_PREFIX}-1"
    second_leaf = f"{COMPOUND_LOOP_LEAF_PREFIX}-2"
    third_leaf = f"{COMPOUND_LOOP_LEAF_PREFIX}-3"
    first_compose = f"{PRIMITIVE_COMPOSE_UNIT_PREFIX}-1-2"
    second_compose = f"{PRIMITIVE_COMPOSE_UNIT_PREFIX}-2-3"
    first_program = f"{COMPOSED_PROGRAM_UNIT_PREFIX}-1-2__2-3"
    checks["program_unit_is_not_cheap"] = is_cheap_inventory_id(first_program) is False
    checks["catalog_names_program_stack"] = PROGRAM_STACK_ID == "capability.kernel-program-stack"

    class _State:
        def __init__(
            self,
            repo: Path,
            *,
            goal: str = "",
            done_when: str = "",
            mission_id: str = "mission-composed-program",
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

    with tempfile.TemporaryDirectory(prefix="kernel-composed-program-need-") as tmp:
        root = Path(tmp)
        _write_fixture_ledger(root)
        ledger = load_tick_ledger(root)
        assert ledger is not None
        empty = LocalCampaign()
        unscoped = _unscoped_remaining_campaign()
        checks["not_needed_without_campaign"] = composed_program_is_needed(empty, ledger) is False
        checks["not_needed_on_unscoped_remaining"] = (
            composed_program_is_needed(unscoped, ledger) is False
        )
        checks["not_needed_on_bound_program_before_saturation"] = (
            composed_program_is_needed(
                empty,
                ledger,
                goal=KERNEL_COMPOSED_PROGRAM_GOAL,
                done_when=KERNEL_COMPOSED_PROGRAM_DONE_WHEN,
                bind_source="genesis_bind_program",
            )
            is False
        )
        checks["bound_program_still_needs_compound_loop"] = (
            compound_loop_is_needed(
                empty,
                ledger,
                goal=KERNEL_COMPOSED_PROGRAM_GOAL,
                done_when=KERNEL_COMPOSED_PROGRAM_DONE_WHEN,
                bind_source="genesis_bind_program",
            )
            is True
        )
        saturated_campaign = LocalCampaign(tick_count=4, last_contract_met=True)
        saturated_leaves = saturate_primitive_leaves(root, ledger, saturated_campaign)
        checks["bound_program_needs_compose_after_primitives"] = (
            len(saturated_leaves) >= 3
            and primitive_compose_is_needed(
                saturated_campaign,
                ledger,
                goal=KERNEL_COMPOSED_PROGRAM_GOAL,
                done_when=KERNEL_COMPOSED_PROGRAM_DONE_WHEN,
                bind_source="genesis_bind_program",
            )
            is True
            and composed_program_is_needed(
                saturated_campaign,
                ledger,
                goal=KERNEL_COMPOSED_PROGRAM_GOAL,
                done_when=KERNEL_COMPOSED_PROGRAM_DONE_WHEN,
                bind_source="genesis_bind_program",
            )
            is False
        )
        saturated_compositions = saturate_primitive_compositions(
            root, ledger, saturated_campaign
        )
        checks["needed_on_bound_program_when_saturated"] = (
            len(saturated_compositions) >= 2
            and composition_unique_coverage_is_saturated(ledger, saturated_campaign) is True
            and composed_program_is_needed(
                saturated_campaign,
                ledger,
                goal=KERNEL_COMPOSED_PROGRAM_GOAL,
                done_when=KERNEL_COMPOSED_PROGRAM_DONE_WHEN,
                bind_source="genesis_bind_program",
            )
            is True
            and primitive_compose_is_needed(
                saturated_campaign,
                ledger,
                goal=KERNEL_COMPOSED_PROGRAM_GOAL,
                done_when=KERNEL_COMPOSED_PROGRAM_DONE_WHEN,
                bind_source="genesis_bind_program",
            )
            is False
        )
        ranked = rank_ready_composed_programs(ledger)
        top = ranked[0] if ranked else {}
        checks["novelty_ranks_pair_first"] = (
            top.get("suggested_id") == first_program
            and top.get("novel") is True
            and int(top.get("novelty_score") or 0) >= 500
            and list(top.get("members") or []) == [first_compose, second_compose]
        )
        before_ids = set(ledger.capabilities)
        before_sets = existing_composed_coverage_sets(ledger)
        program_id = promote_and_prove_composed_program(root, ledger, first_program)
        grown = load_tick_ledger(root)
        assert grown is not None
        programmed = grown.capabilities.get(program_id or "")
        coverage = primitive_coverage(grown, program_id or "")
        checks["promote_registers_unique_program_coverage"] = (
            program_id == first_program
            and first_program not in before_ids
            and programmed is not None
            and programmed.last_proof_exit_code == 0
            and is_primitive_capability(programmed) is False
            and coverage == frozenset({first_leaf, second_leaf, third_leaf})
            and coverage not in before_sets
            and coverage in existing_composed_coverage_sets(grown)
            and invoke_local_capability(programmed).get("ok") is True
        )
        ranked_after = rank_ready_composed_programs(grown, skip_ids=(first_program,))
        next_top = ranked_after[0] if ranked_after else {}
        next_id = str(next_top.get("suggested_id") or "")
        second = promote_and_prove_composed_program(root, grown, next_id)
        after = load_tick_ledger(root)
        assert after is not None
        second_cap = after.capabilities.get(second or "")
        second_coverage = primitive_coverage(after, second or "") if second else frozenset()
        checks["second_promote_expands_program_coverage"] = (
            bool(second)
            and second != first_program
            and next_top.get("novel") is True
            and second_cap is not None
            and second_cap.last_proof_exit_code == 0
            and is_primitive_capability(second_cap) is False
            and second_coverage != coverage
            and len(second_coverage) >= 3
            and second_coverage not in before_sets
        )

    with tempfile.TemporaryDirectory(prefix="kernel-composed-program-tick-") as tmp:
        root = Path(tmp)
        _write_fixture_ledger(root)
        _register_turn_failed_closers(root)
        _write_forage_history(root)
        _register_proved(root, KERNEL_GENESIS_BIND_ID)
        _register_proved(root, CONSUMED_GROWTH_ID)
        _register_proved(root, COMPOUND_LOOP_ID)
        _register_proved(root, PRIMITIVE_COMPOSE_ID)
        campaign = _consumed_campaign()
        ledger = load_tick_ledger(root)
        assert ledger is not None
        saturate_primitive_leaves(root, ledger, campaign)
        saturate_primitive_compositions(root, ledger, campaign)
        save_campaign(root, campaign)
        tick = local_mission_tick(_State(root), root)
        live = load_campaign(root)
        invoked = tick.get("invoked") or []
        invoked_id = invoked[0]["capability_id"] if invoked else ""
        grown = load_tick_ledger(root)
        unit = None if grown is None else grown.capabilities.get(first_program)
        checks["tick_after_saturated_compositions_runs_program"] = (
            invoked_id == first_program
            and bool(invoked)
            and invoked[0].get("ok") is True
            and first_program in live.completed_ids
            and unit is not None
            and unit.last_proof_exit_code == 0
            and is_primitive_capability(unit) is False
            and primitive_coverage(grown, first_program)
            == frozenset({first_leaf, second_leaf, third_leaf})
            and str((live.handoff or {}).get("composed_program_unit") or "") == first_program
        )
        checks["tick_bound_from_program"] = "genesis_bind" in str(
            (tick.get("binding") or {}).get("source") or live.bound_from
        )

    with tempfile.TemporaryDirectory(prefix="kernel-composed-program-operator-") as tmp:
        root = Path(tmp)
        _write_fixture_ledger(root)
        _register_turn_failed_closers(root)
        save_campaign(root, _consumed_campaign())
        kept = bind_local_mission(
            _State(root, goal="Operator growth goal.", done_when="capability_exists:repo.import-health"),
            harvest=True,
        )
        checks["preserves_operator_bind"] = (
            kept.goal == "Operator growth goal." and "state.goal" in kept.source
        )

    with tempfile.TemporaryDirectory(prefix="kernel-composed-program-remaining-") as tmp:
        root = Path(tmp)
        _write_fixture_ledger(root)
        _register_turn_failed_closers(root)
        save_campaign(root, _unscoped_remaining_campaign())
        remaining = bind_local_mission(_State(root), harvest=True)
        checks["unscoped_remaining_still_wins"] = (
            "capability.fixture-local-b" in remaining.goal
            and "program_passes:capability.fixture-local-b" in remaining.done_when
            and "unscoped_campaign" in remaining.source
        )

    with tempfile.TemporaryDirectory(prefix="kernel-composed-program-hydrate-") as tmp:
        root = Path(tmp)
        _write_fixture_ledger(root)
        _register_turn_failed_closers(root)
        _write_forage_history(root)
        _register_proved(root, KERNEL_GENESIS_BIND_ID)
        _register_proved(root, CONSUMED_GROWTH_ID)
        _register_proved(root, COMPOUND_LOOP_ID)
        _register_proved(root, PRIMITIVE_COMPOSE_ID)
        save_campaign(root, _consumed_campaign())
        empty = _State(root)
        report = hydrate_mission_from_campaign(empty, persist=True)
        checks["hydrate_fills_composed_program"] = (
            report.get("applied") is True
            and empty.goal == KERNEL_COMPOSED_PROGRAM_GOAL
            and KERNEL_COMPOSED_PROGRAM_ID in empty.done_when
            and empty.stage == "execution"
            and str(report.get("source") or "").startswith("genesis_bind")
        )
        create_goal, create_done, create_source = bind_create_fields(root)
        checks["create_bind_uses_composed_program"] = (
            create_goal == KERNEL_COMPOSED_PROGRAM_GOAL
            and KERNEL_COMPOSED_PROGRAM_ID in create_done
            and str(create_source).startswith("genesis_bind")
        )

    with tempfile.TemporaryDirectory(prefix="kernel-composed-program-skip-") as tmp:
        root = Path(tmp)
        _write_fixture_ledger(root)
        _register_turn_failed_closers(root)
        _write_forage_history(root)
        _register_proved(root, KERNEL_GENESIS_BIND_ID)
        _register_proved(root, CONSUMED_GROWTH_ID)
        _register_proved(root, COMPOUND_LOOP_ID)
        _register_proved(root, PRIMITIVE_COMPOSE_ID)
        _register_proved(root, KERNEL_COMPOSED_PROGRAM_ID)
        save_campaign(root, _consumed_campaign())
        skip_goal, skip_done, skip_source = bind_gate_passing_successor(root)
        checks["proved_program_skips_to_stack"] = (
            skip_goal == PROGRAM_STACK_GOAL
            and PROGRAM_STACK_ID in skip_done
            and skip_source == "genesis_bind_stack"
            and PROGRAM_STACK_DONE_WHEN == skip_done
        )

    keep = _State(Path("."), goal="Operator growth goal.")
    hydrate_mission_from_campaign(keep, repo_path=Path("."))
    checks["hydrate_preserves_operator_goal"] = keep.goal == "Operator growth goal."
    checks["no_skill_route"] = not legacy_pipeline_was_used()
    checks["schema_version"] = SCHEMA_VERSION == 1

    ok = all(checks.values())
    return {
        "ok": ok,
        "action": "kernel_composed_program",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": KERNEL_COMPOSED_PROGRAM_GOAL,
        "done_when": KERNEL_COMPOSED_PROGRAM_DONE_WHEN,
    }
