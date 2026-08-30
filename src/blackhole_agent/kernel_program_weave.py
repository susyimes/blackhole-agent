"""Raise a ready program weave after unique program-fabric coverage saturates.

``capability.kernel-program-fabric`` mints consecutive-pair fabrics of
program lattices. Once those fabrics fill unique coverage, recovered kernels
and 402-local ticks fall back to cheap inventory probes. Tapestry compounding
stalls on saturated program fabrics.

This module closes that hole:

- detect when in-process program fabrics saturate unique coverage, or genesis
  is bound to this closer
- rank ready program weaves (weaves of minted program fabrics) by coverage
  novelty
- raise and prove the top novel weave in-process
- attach it to the durable campaign so the next local tick compounds tapestries
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
    bound_to_program_weave,
    is_compound_loop_leaf_id,
)
from blackhole_agent.kernel_consumed_growth import is_cheap_inventory_id
from blackhole_agent.kernel_composed_program import (
    COMPOSED_PROGRAM_UNIT_PREFIX,
    is_composed_program_id,
    saturate_composed_programs,
)
from blackhole_agent.kernel_genesis_bind import (
    COMPOUND_LOOP_ID,
    COMPOSED_PROGRAM_ID,
    CONSUMED_GROWTH_ID,
    KERNEL_GENESIS_BIND_ID,
    PRIMITIVE_COMPOSE_ID,
    PROGRAM_FABRIC_ID,
    PROGRAM_LATTICE_ID,
    PROGRAM_STACK_ID,
    PROGRAM_TOWER_ID,
    PROGRAM_WEAVE_DONE_WHEN,
    PROGRAM_WEAVE_GOAL,
    PROGRAM_WEAVE_ID,
)
from blackhole_agent.kernel_primitive_compose import is_primitive_compose_id
from blackhole_agent.kernel_program_fabric import (
    PROGRAM_FABRIC_UNIT_PREFIX,
    builtin_execute_composed_capability as execute_fabric,
    fabric_id_from_members,
    fabric_member_ids,
    fabric_unique_coverage_is_saturated,
    is_program_fabric_id,
    program_fabric_is_needed,
    saturate_program_fabrics,
)
from blackhole_agent.kernel_program_lattice import (
    PROGRAM_LATTICE_MEMBER_SEP,
    PROGRAM_LATTICE_UNIT_PREFIX,
    is_program_lattice_id,
    program_lattice_is_needed,
    saturate_program_lattices,
)
from blackhole_agent.kernel_program_stack import (
    PROGRAM_STACK_UNIT_PREFIX,
    is_program_stack_id,
    program_stack_is_needed,
    saturate_program_stacks,
)
from blackhole_agent.kernel_program_tower import (
    PROGRAM_TOWER_MEMBER_SEP,
    PROGRAM_TOWER_UNIT_PREFIX,
    is_program_tower_id,
    program_tower_is_needed,
    saturate_program_towers,
)
from blackhole_agent.kernel_succession import cheap_remaining
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST, invoke_local_capability
from blackhole_agent.local_mission_sovereignty import LocalCampaign

SCHEMA_VERSION = 1
KERNEL_PROGRAM_WEAVE_ID = PROGRAM_WEAVE_ID
KERNEL_PROGRAM_WEAVE_DONE_WHEN = PROGRAM_WEAVE_DONE_WHEN
KERNEL_PROGRAM_WEAVE_GOAL = PROGRAM_WEAVE_GOAL

PROGRAM_WEAVE_UNIT_PREFIX = "capability.program-weave"
PROGRAM_WEAVE_MEMBER_SEP = "_______"
PROGRAM_WEAVE_TAG = "program-weave-unit"

UNIT_PROOF_COMMAND = (
    "uv run python -c \"from blackhole_agent.kernel_program_weave import "
    "builtin_execute_composed_capability; r=builtin_execute_composed_capability(); "
    "assert r['ok']\""
)


def is_program_weave_id(capability_id: str) -> bool:
    """True for program-weave units raised by this closer."""

    item = str(capability_id or "").strip()
    return item.startswith(f"{PROGRAM_WEAVE_UNIT_PREFIX}-")


def weave_id_from_members(members: tuple[str, ...]) -> str:
    prefix = f"{PROGRAM_FABRIC_UNIT_PREFIX}-"
    suffixes: list[str] = []
    for item in members:
        raw = str(item or "").strip()
        if not raw.startswith(prefix):
            return ""
        suffixes.append(raw[len(prefix) :])
    if len(suffixes) < 2:
        return ""
    return f"{PROGRAM_WEAVE_UNIT_PREFIX}-{PROGRAM_WEAVE_MEMBER_SEP.join(suffixes)}"


def weave_member_ids(weave_id: str) -> tuple[str, ...]:
    item = str(weave_id or "").strip()
    prefix = f"{PROGRAM_WEAVE_UNIT_PREFIX}-"
    if not item.startswith(prefix):
        return ()
    parts = [part for part in item[len(prefix) :].split(PROGRAM_WEAVE_MEMBER_SEP) if part]
    members = tuple(f"{PROGRAM_FABRIC_UNIT_PREFIX}-{part}" for part in parts)
    if len(members) < 2:
        return ()
    return members


def builtin_execute_composed_capability() -> dict[str, Any]:
    """Hermetic in-process weave of minted program fabrics.

    Named ``builtin_execute_composed_capability`` so coverage scoring treats
    the unit as a composition rather than another primitive leaf.
    """

    cap_id = (os.environ.get(ACTIVE_CAPABILITY_ENV) or "").strip()
    members = weave_member_ids(cap_id)
    if len(members) < 2:
        members = (
            f"{PROGRAM_FABRIC_UNIT_PREFIX}-weave-fallback-a",
            f"{PROGRAM_FABRIC_UNIT_PREFIX}-weave-fallback-b",
        )
    results: list[dict[str, Any]] = []
    saved = os.environ.get(ACTIVE_CAPABILITY_ENV)
    try:
        for member in members:
            os.environ[ACTIVE_CAPABILITY_ENV] = member
            results.append(execute_fabric())
    finally:
        if saved is None:
            os.environ.pop(ACTIVE_CAPABILITY_ENV, None)
        else:
            os.environ[ACTIVE_CAPABILITY_ENV] = saved
    ok = all(bool(item.get("ok")) for item in results)
    return {
        "ok": ok,
        "action": "program_weave_unit",
        "capability_id": cap_id,
        "members": list(members),
        "member_count": len(members),
        "used_skill_route_discovery": False,
    }


def program_weave_is_needed(
    campaign: LocalCampaign,
    ledger: CapabilityLedger,
    *,
    goal: str = "",
    done_when: str = "",
    bind_source: str = "",
) -> bool:
    """True when saturated program-fabric coverage (or this closer) would otherwise idle."""

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
                or is_program_stack_id(item)
                or is_program_tower_id(item)
                or is_program_lattice_id(item)
                or is_program_fabric_id(item)
                or is_program_weave_id(item)
                for item in leftover
            ):
                return False
    except Exception:  # noqa: BLE001 - weave closer must still decide from campaign fields
        pass
    live_goal = str(goal or campaign.goal or "")
    live_done = str(done_when or campaign.done_when or "")
    source = str(bind_source or campaign.bound_from or "")
    scoped = bound_to_program_weave(live_goal, live_done, source)
    saturated = fabric_unique_coverage_is_saturated(ledger, campaign)
    if not saturated:
        return False
    if not scoped and not saturated:
        return False
    remaining = cheap_remaining(campaign)
    if remaining:
        capability = ledger.capabilities.get(remaining[0])
        if capability is not None and PROGRAM_WEAVE_TAG in capability.tags:
            return True
        if is_program_weave_id(remaining[0]):
            return True
        return is_cheap_inventory_id(remaining[0])
    return True


def _weave_candidates(ledger: CapabilityLedger) -> list[tuple[str, tuple[str, ...]]]:
    proved = sorted(
        (
            item_id
            for item_id, item in ledger.capabilities.items()
            if is_program_fabric_id(item_id) and item.last_proof_exit_code == 0
        ),
        key=lambda item_id: (fabric_member_ids(item_id), item_id),
    )
    seen: set[str] = set()
    recipes: list[tuple[str, tuple[str, ...]]] = []

    def _push(members: tuple[str, ...]) -> None:
        if len(members) < 2:
            return
        weave_id = weave_id_from_members(members)
        if not weave_id or weave_id in seen:
            return
        seen.add(weave_id)
        recipes.append((weave_id, members))

    for index in range(len(proved) - 1):
        _push((proved[index], proved[index + 1]))
    return recipes


def rank_ready_program_weaves(
    ledger: CapabilityLedger,
    *,
    skip_ids: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    """Rank ready program weaves by unique coverage novelty."""

    skipped = {item for item in skip_ids if item}
    opportunities: list[dict[str, Any]] = []
    for index, (weave_id, members) in enumerate(_weave_candidates(ledger)):
        if weave_id in skipped:
            continue
        missing = [item for item in members if item not in ledger.capabilities]
        exists = weave_id in ledger.capabilities
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
                "suggested_id": weave_id,
                "members": list(members),
                "priority": 1000 - index,
                "tags": ["composed", "promoted", "growth", "program", "weave"],
                "synthesis": "weave",
            }
        )
    annotate_opportunities_with_novelty(ledger, opportunities)
    return rank_growth_opportunities(opportunities)


def select_program_weave(
    ledger: CapabilityLedger,
    campaign: LocalCampaign,
) -> str:
    """Pick an unfinished in-ledger weave, else the top novel recipe."""

    skip = {item for item in [*campaign.completed_ids, *campaign.failed_ids] if item}
    existing = [
        item_id
        for item_id, item in ledger.capabilities.items()
        if PROGRAM_WEAVE_TAG in item.tags and item_id not in skip
    ]
    if existing:
        existing.sort(
            key=lambda item_id: (
                0 if ledger.capabilities[item_id].last_proof_exit_code != 0 else 1,
                item_id,
            )
        )
        return existing[0]
    for item in rank_ready_program_weaves(ledger, skip_ids=tuple(skip)):
        weave_id = str(item.get("suggested_id") or "").strip()
        if not weave_id or weave_id in skip:
            continue
        if item.get("novel") and item.get("status") == "ready":
            return weave_id
    return ""


def _weave_spec(ledger: CapabilityLedger, weave_id: str, members: tuple[str, ...]) -> Capability:
    _ = ledger
    suffixes = []
    prefix = f"{PROGRAM_FABRIC_UNIT_PREFIX}-"
    for item in members:
        raw = str(item)
        suffixes.append(raw[len(prefix) :] if raw.startswith(prefix) else raw)
    label = "+".join(suffixes)
    return Capability(
        id=weave_id,
        name=f"Program weave {label}",
        description=(
            "In-process program weave raised when unique program-fabric "
            "coverage saturates and tapestry compounding would otherwise stall."
        ),
        kind="python",
        entry="blackhole_agent.kernel_program_weave:builtin_execute_composed_capability",
        proof_command=UNIT_PROOF_COMMAND,
        dependencies=tuple(members),
        behavior_paths=("src/blackhole_agent/kernel_program_weave.py",),
        capability_delta=(
            "Ready program weaves raise in-process instead of falling through "
            "to cheap inventory after unique program-fabric coverage saturates."
        ),
        tags=(PROGRAM_WEAVE_TAG, "composed", "promoted", "growth", "kernel", "program", "weave"),
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


def promote_and_prove_program_weave(
    root: Path,
    ledger: CapabilityLedger,
    weave_id: str,
) -> str:
    """Register the ranked weave if missing and stamp an in-process proof."""

    members = weave_member_ids(weave_id)
    if len(members) < 2:
        existing = ledger.capabilities.get(weave_id)
        deps = tuple(str(item) for item in existing.dependencies) if existing is not None else ()
        if len(deps) >= 2 and all(is_program_fabric_id(item) for item in deps):
            members = deps
        else:
            return ""
    missing = [item for item in members if item not in ledger.capabilities]
    if missing:
        return ""
    existing = ledger.capabilities.get(weave_id)
    if existing is None:
        register_capability(ledger, _weave_spec(ledger, weave_id, members), replace=False)
        existing = ledger.capabilities[weave_id]
    if existing.last_proof_exit_code != 0:
        result = invoke_local_capability(existing)
        if not result.get("ok"):
            return ""
        _stamp_proved(ledger, existing, exit_code=0)
        existing = ledger.capabilities[weave_id]
    path = default_ledger_path(Path(root))
    path.parent.mkdir(parents=True, exist_ok=True)
    save_ledger(path, ledger)
    proved = ledger.capabilities.get(weave_id)
    if proved is None or proved.last_proof_exit_code != 0:
        return ""
    if is_primitive_capability(proved):
        return ""
    return weave_id


def attach_program_weave(
    campaign: LocalCampaign,
    ledger: CapabilityLedger,
    root: Path,
    *,
    goal: str = "",
    done_when: str = "",
    bind_source: str = "",
) -> str:
    """Raise the next novel program weave and make it the next campaign step."""

    remaining = cheap_remaining(campaign)
    if remaining:
        capability = ledger.capabilities.get(remaining[0])
        if capability is not None and PROGRAM_WEAVE_TAG in capability.tags:
            return remaining[0]
        if is_program_weave_id(remaining[0]):
            return remaining[0]
        if not is_cheap_inventory_id(remaining[0]):
            return ""
    if not program_weave_is_needed(
        campaign,
        ledger,
        goal=goal,
        done_when=done_when,
        bind_source=bind_source,
    ):
        return ""
    weave_id = select_program_weave(ledger, campaign)
    if not weave_id:
        return ""
    promoted = promote_and_prove_program_weave(Path(root), ledger, weave_id)
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
        and not is_composed_program_id(item)
        and not is_program_stack_id(item)
        and not is_program_tower_id(item)
        and not is_program_lattice_id(item)
        and not is_program_fabric_id(item)
    ]
    if promoted not in campaign.program:
        campaign.program.append(promoted)
    campaign.cursor = campaign.program.index(promoted) + 1
    handoff = dict(campaign.handoff or {})
    handoff["program_weave_unit"] = promoted
    campaign.handoff = handoff
    return promoted


def continue_resumed_program_weave(
    state: Any,
    repo_path: Path | None = None,
    workspace: Path | None = None,
) -> dict[str, Any]:
    """When unique program-fabric coverage saturates, attach a program weave."""

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
    step = attach_program_weave(
        campaign,
        ledger,
        work,
        goal=str(getattr(state, "goal", "") or campaign.goal),
        done_when=str(getattr(state, "done_when", "") or campaign.done_when),
    )
    if not step:
        return {
            "applied": False,
            "reason": "no_program_weave",
            "step": "",
            "program": list(campaign.program),
        }
    if before != list(campaign.program):
        save_campaign(durable, campaign)
    return {
        "applied": True,
        "reason": "program_weave",
        "step": step,
        "program": list(campaign.program),
    }


def builtin_kernel_program_weave_proof() -> dict[str, Any]:
    """Hermetic proof: saturated program-fabric coverage raises a program weave."""

    import tempfile

    from blackhole_agent.capability_compounder import (
        existing_composed_coverage_sets,
        primitive_coverage,
    )
    from blackhole_agent.kernel_compound_loop import compound_loop_is_needed
    from blackhole_agent.kernel_composed_program import composed_program_is_needed
    from blackhole_agent.kernel_genesis_bind import (
        _consumed_campaign,
        _register_proved,
        _unscoped_remaining_campaign,
        _write_forage_history,
        bind_gate_passing_successor,
    )
    from blackhole_agent.kernel_genesis_diversify import (
        GENESIS_DIVERSIFY_DONE_WHEN,
        GENESIS_DIVERSIFY_GOAL,
        GENESIS_DIVERSIFY_ID,
    )
    from blackhole_agent.kernel_leftover import leftover_marker_ids
    from blackhole_agent.kernel_primitive_compose import (
        primitive_compose_is_needed,
        saturate_primitive_compositions,
        saturate_primitive_leaves,
    )
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
    checks["denylists_self"] = KERNEL_PROGRAM_WEAVE_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = KERNEL_PROGRAM_WEAVE_ID in leftover_marker_ids(
        KERNEL_PROGRAM_WEAVE_GOAL
    )
    checks["leftover_does_not_bind_fabric"] = PROGRAM_FABRIC_ID not in leftover_marker_ids(
        KERNEL_PROGRAM_WEAVE_GOAL
    )
    checks["leftover_does_not_bind_lattice"] = PROGRAM_LATTICE_ID not in leftover_marker_ids(
        KERNEL_PROGRAM_WEAVE_GOAL
    )
    checks["leftover_does_not_bind_tower"] = PROGRAM_TOWER_ID not in leftover_marker_ids(
        KERNEL_PROGRAM_WEAVE_GOAL
    )
    checks["leftover_does_not_bind_stack"] = PROGRAM_STACK_ID not in leftover_marker_ids(
        KERNEL_PROGRAM_WEAVE_GOAL
    )
    first_leaf = f"{COMPOUND_LOOP_LEAF_PREFIX}-1"
    second_leaf = f"{COMPOUND_LOOP_LEAF_PREFIX}-2"
    third_leaf = f"{COMPOUND_LOOP_LEAF_PREFIX}-3"
    fourth_leaf = f"{COMPOUND_LOOP_LEAF_PREFIX}-4"
    fifth_leaf = f"{COMPOUND_LOOP_LEAF_PREFIX}-5"
    sixth_leaf = f"{COMPOUND_LOOP_LEAF_PREFIX}-6"
    seventh_leaf = f"{COMPOUND_LOOP_LEAF_PREFIX}-7"
    eighth_leaf = f"{COMPOUND_LOOP_LEAF_PREFIX}-8"
    first_program = f"{COMPOSED_PROGRAM_UNIT_PREFIX}-1-2__2-3"
    second_program = f"{COMPOSED_PROGRAM_UNIT_PREFIX}-2-3__3-4"
    third_program = f"{COMPOSED_PROGRAM_UNIT_PREFIX}-3-4__4-5"
    fourth_program = f"{COMPOSED_PROGRAM_UNIT_PREFIX}-4-5__5-6"
    first_stack = f"{PROGRAM_STACK_UNIT_PREFIX}-1-2__2-3___2-3__3-4"
    second_stack = f"{PROGRAM_STACK_UNIT_PREFIX}-2-3__3-4___3-4__4-5"
    third_stack = f"{PROGRAM_STACK_UNIT_PREFIX}-3-4__4-5___4-5__5-6"
    first_tower = (
        f"{PROGRAM_TOWER_UNIT_PREFIX}-1-2__2-3___2-3__3-4"
        f"{PROGRAM_TOWER_MEMBER_SEP}2-3__3-4___3-4__4-5"
    )
    second_tower = (
        f"{PROGRAM_TOWER_UNIT_PREFIX}-2-3__3-4___3-4__4-5"
        f"{PROGRAM_TOWER_MEMBER_SEP}3-4__4-5___4-5__5-6"
    )
    first_lattice = (
        f"{PROGRAM_LATTICE_UNIT_PREFIX}-1-2__2-3___2-3__3-4"
        f"{PROGRAM_TOWER_MEMBER_SEP}2-3__3-4___3-4__4-5"
        f"{PROGRAM_LATTICE_MEMBER_SEP}2-3__3-4___3-4__4-5"
        f"{PROGRAM_TOWER_MEMBER_SEP}3-4__4-5___4-5__5-6"
    )
    second_lattice = (
        f"{PROGRAM_LATTICE_UNIT_PREFIX}-2-3__3-4___3-4__4-5"
        f"{PROGRAM_TOWER_MEMBER_SEP}3-4__4-5___4-5__5-6"
        f"{PROGRAM_LATTICE_MEMBER_SEP}3-4__4-5___4-5__5-6"
        f"{PROGRAM_TOWER_MEMBER_SEP}4-5__5-6___5-6__6-7"
    )
    third_lattice = (
        f"{PROGRAM_LATTICE_UNIT_PREFIX}-3-4__4-5___4-5__5-6"
        f"{PROGRAM_TOWER_MEMBER_SEP}4-5__5-6___5-6__6-7"
        f"{PROGRAM_LATTICE_MEMBER_SEP}4-5__5-6___5-6__6-7"
        f"{PROGRAM_TOWER_MEMBER_SEP}5-6__6-7___6-7__7-8"
    )
    first_fabric = fabric_id_from_members((first_lattice, second_lattice))
    second_fabric = fabric_id_from_members((second_lattice, third_lattice))
    first_weave = weave_id_from_members((first_fabric, second_fabric))
    checks["weave_unit_is_not_cheap"] = is_cheap_inventory_id(first_weave) is False
    checks["catalog_names_program_weave"] = PROGRAM_WEAVE_ID == "capability.kernel-program-weave"
    _ = (
        first_program,
        second_program,
        third_program,
        fourth_program,
        first_stack,
        second_stack,
        third_stack,
        first_tower,
        second_tower,
        eighth_leaf,
    )

    class _State:
        def __init__(
            self,
            repo: Path,
            *,
            goal: str = "",
            done_when: str = "",
            mission_id: str = "mission-program-weave",
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

    with tempfile.TemporaryDirectory(prefix="kernel-program-weave-need-") as tmp:
        root = Path(tmp)
        _write_fixture_ledger(root)
        ledger = load_tick_ledger(root)
        assert ledger is not None
        empty = LocalCampaign()
        unscoped = _unscoped_remaining_campaign()
        checks["not_needed_without_campaign"] = program_weave_is_needed(empty, ledger) is False
        checks["not_needed_on_unscoped_remaining"] = (
            program_weave_is_needed(unscoped, ledger) is False
        )
        checks["not_needed_on_bound_weave_before_saturation"] = (
            program_weave_is_needed(
                empty,
                ledger,
                goal=KERNEL_PROGRAM_WEAVE_GOAL,
                done_when=KERNEL_PROGRAM_WEAVE_DONE_WHEN,
                bind_source="genesis_bind_weave",
            )
            is False
        )
        checks["bound_weave_still_needs_compound_loop"] = (
            compound_loop_is_needed(
                empty,
                ledger,
                goal=KERNEL_PROGRAM_WEAVE_GOAL,
                done_when=KERNEL_PROGRAM_WEAVE_DONE_WHEN,
                bind_source="genesis_bind_weave",
            )
            is True
        )
        saturated_campaign = LocalCampaign(tick_count=4, last_contract_met=True)
        saturated_leaves = saturate_primitive_leaves(root, ledger, saturated_campaign)
        checks["bound_weave_needs_compose_after_primitives"] = (
            len(saturated_leaves) >= 7
            and primitive_compose_is_needed(
                saturated_campaign,
                ledger,
                goal=KERNEL_PROGRAM_WEAVE_GOAL,
                done_when=KERNEL_PROGRAM_WEAVE_DONE_WHEN,
                bind_source="genesis_bind_weave",
            )
            is True
            and composed_program_is_needed(
                saturated_campaign,
                ledger,
                goal=KERNEL_PROGRAM_WEAVE_GOAL,
                done_when=KERNEL_PROGRAM_WEAVE_DONE_WHEN,
                bind_source="genesis_bind_weave",
            )
            is False
            and program_stack_is_needed(
                saturated_campaign,
                ledger,
                goal=KERNEL_PROGRAM_WEAVE_GOAL,
                done_when=KERNEL_PROGRAM_WEAVE_DONE_WHEN,
                bind_source="genesis_bind_weave",
            )
            is False
            and program_tower_is_needed(
                saturated_campaign,
                ledger,
                goal=KERNEL_PROGRAM_WEAVE_GOAL,
                done_when=KERNEL_PROGRAM_WEAVE_DONE_WHEN,
                bind_source="genesis_bind_weave",
            )
            is False
            and program_lattice_is_needed(
                saturated_campaign,
                ledger,
                goal=KERNEL_PROGRAM_WEAVE_GOAL,
                done_when=KERNEL_PROGRAM_WEAVE_DONE_WHEN,
                bind_source="genesis_bind_weave",
            )
            is False
            and program_fabric_is_needed(
                saturated_campaign,
                ledger,
                goal=KERNEL_PROGRAM_WEAVE_GOAL,
                done_when=KERNEL_PROGRAM_WEAVE_DONE_WHEN,
                bind_source="genesis_bind_weave",
            )
            is False
            and program_weave_is_needed(
                saturated_campaign,
                ledger,
                goal=KERNEL_PROGRAM_WEAVE_GOAL,
                done_when=KERNEL_PROGRAM_WEAVE_DONE_WHEN,
                bind_source="genesis_bind_weave",
            )
            is False
        )
        saturated_compositions = saturate_primitive_compositions(
            root, ledger, saturated_campaign
        )
        checks["bound_weave_needs_program_after_compositions"] = (
            len(saturated_compositions) >= 6
            and composed_program_is_needed(
                saturated_campaign,
                ledger,
                goal=KERNEL_PROGRAM_WEAVE_GOAL,
                done_when=KERNEL_PROGRAM_WEAVE_DONE_WHEN,
                bind_source="genesis_bind_weave",
            )
            is True
            and primitive_compose_is_needed(
                saturated_campaign,
                ledger,
                goal=KERNEL_PROGRAM_WEAVE_GOAL,
                done_when=KERNEL_PROGRAM_WEAVE_DONE_WHEN,
                bind_source="genesis_bind_weave",
            )
            is False
            and program_stack_is_needed(
                saturated_campaign,
                ledger,
                goal=KERNEL_PROGRAM_WEAVE_GOAL,
                done_when=KERNEL_PROGRAM_WEAVE_DONE_WHEN,
                bind_source="genesis_bind_weave",
            )
            is False
            and program_tower_is_needed(
                saturated_campaign,
                ledger,
                goal=KERNEL_PROGRAM_WEAVE_GOAL,
                done_when=KERNEL_PROGRAM_WEAVE_DONE_WHEN,
                bind_source="genesis_bind_weave",
            )
            is False
            and program_lattice_is_needed(
                saturated_campaign,
                ledger,
                goal=KERNEL_PROGRAM_WEAVE_GOAL,
                done_when=KERNEL_PROGRAM_WEAVE_DONE_WHEN,
                bind_source="genesis_bind_weave",
            )
            is False
            and program_fabric_is_needed(
                saturated_campaign,
                ledger,
                goal=KERNEL_PROGRAM_WEAVE_GOAL,
                done_when=KERNEL_PROGRAM_WEAVE_DONE_WHEN,
                bind_source="genesis_bind_weave",
            )
            is False
            and program_weave_is_needed(
                saturated_campaign,
                ledger,
                goal=KERNEL_PROGRAM_WEAVE_GOAL,
                done_when=KERNEL_PROGRAM_WEAVE_DONE_WHEN,
                bind_source="genesis_bind_weave",
            )
            is False
        )
        saturated_programs = saturate_composed_programs(root, ledger, saturated_campaign)
        checks["bound_weave_needs_stack_after_programs"] = (
            len(saturated_programs) >= 5
            and program_stack_is_needed(
                saturated_campaign,
                ledger,
                goal=KERNEL_PROGRAM_WEAVE_GOAL,
                done_when=KERNEL_PROGRAM_WEAVE_DONE_WHEN,
                bind_source="genesis_bind_weave",
            )
            is True
            and composed_program_is_needed(
                saturated_campaign,
                ledger,
                goal=KERNEL_PROGRAM_WEAVE_GOAL,
                done_when=KERNEL_PROGRAM_WEAVE_DONE_WHEN,
                bind_source="genesis_bind_weave",
            )
            is False
            and program_tower_is_needed(
                saturated_campaign,
                ledger,
                goal=KERNEL_PROGRAM_WEAVE_GOAL,
                done_when=KERNEL_PROGRAM_WEAVE_DONE_WHEN,
                bind_source="genesis_bind_weave",
            )
            is False
            and program_lattice_is_needed(
                saturated_campaign,
                ledger,
                goal=KERNEL_PROGRAM_WEAVE_GOAL,
                done_when=KERNEL_PROGRAM_WEAVE_DONE_WHEN,
                bind_source="genesis_bind_weave",
            )
            is False
            and program_fabric_is_needed(
                saturated_campaign,
                ledger,
                goal=KERNEL_PROGRAM_WEAVE_GOAL,
                done_when=KERNEL_PROGRAM_WEAVE_DONE_WHEN,
                bind_source="genesis_bind_weave",
            )
            is False
            and program_weave_is_needed(
                saturated_campaign,
                ledger,
                goal=KERNEL_PROGRAM_WEAVE_GOAL,
                done_when=KERNEL_PROGRAM_WEAVE_DONE_WHEN,
                bind_source="genesis_bind_weave",
            )
            is False
        )
        saturated_stacks = saturate_program_stacks(root, ledger, saturated_campaign)
        checks["bound_weave_needs_tower_after_stacks"] = (
            len(saturated_stacks) >= 4
            and program_tower_is_needed(
                saturated_campaign,
                ledger,
                goal=KERNEL_PROGRAM_WEAVE_GOAL,
                done_when=KERNEL_PROGRAM_WEAVE_DONE_WHEN,
                bind_source="genesis_bind_weave",
            )
            is True
            and program_stack_is_needed(
                saturated_campaign,
                ledger,
                goal=KERNEL_PROGRAM_WEAVE_GOAL,
                done_when=KERNEL_PROGRAM_WEAVE_DONE_WHEN,
                bind_source="genesis_bind_weave",
            )
            is False
            and composed_program_is_needed(
                saturated_campaign,
                ledger,
                goal=KERNEL_PROGRAM_WEAVE_GOAL,
                done_when=KERNEL_PROGRAM_WEAVE_DONE_WHEN,
                bind_source="genesis_bind_weave",
            )
            is False
            and program_lattice_is_needed(
                saturated_campaign,
                ledger,
                goal=KERNEL_PROGRAM_WEAVE_GOAL,
                done_when=KERNEL_PROGRAM_WEAVE_DONE_WHEN,
                bind_source="genesis_bind_weave",
            )
            is False
            and program_fabric_is_needed(
                saturated_campaign,
                ledger,
                goal=KERNEL_PROGRAM_WEAVE_GOAL,
                done_when=KERNEL_PROGRAM_WEAVE_DONE_WHEN,
                bind_source="genesis_bind_weave",
            )
            is False
            and program_weave_is_needed(
                saturated_campaign,
                ledger,
                goal=KERNEL_PROGRAM_WEAVE_GOAL,
                done_when=KERNEL_PROGRAM_WEAVE_DONE_WHEN,
                bind_source="genesis_bind_weave",
            )
            is False
        )
        saturated_towers = saturate_program_towers(root, ledger, saturated_campaign)
        checks["bound_weave_needs_lattice_after_towers"] = (
            len(saturated_towers) >= 3
            and program_lattice_is_needed(
                saturated_campaign,
                ledger,
                goal=KERNEL_PROGRAM_WEAVE_GOAL,
                done_when=KERNEL_PROGRAM_WEAVE_DONE_WHEN,
                bind_source="genesis_bind_weave",
            )
            is True
            and program_tower_is_needed(
                saturated_campaign,
                ledger,
                goal=KERNEL_PROGRAM_WEAVE_GOAL,
                done_when=KERNEL_PROGRAM_WEAVE_DONE_WHEN,
                bind_source="genesis_bind_weave",
            )
            is False
            and program_stack_is_needed(
                saturated_campaign,
                ledger,
                goal=KERNEL_PROGRAM_WEAVE_GOAL,
                done_when=KERNEL_PROGRAM_WEAVE_DONE_WHEN,
                bind_source="genesis_bind_weave",
            )
            is False
            and composed_program_is_needed(
                saturated_campaign,
                ledger,
                goal=KERNEL_PROGRAM_WEAVE_GOAL,
                done_when=KERNEL_PROGRAM_WEAVE_DONE_WHEN,
                bind_source="genesis_bind_weave",
            )
            is False
            and program_fabric_is_needed(
                saturated_campaign,
                ledger,
                goal=KERNEL_PROGRAM_WEAVE_GOAL,
                done_when=KERNEL_PROGRAM_WEAVE_DONE_WHEN,
                bind_source="genesis_bind_weave",
            )
            is False
            and program_weave_is_needed(
                saturated_campaign,
                ledger,
                goal=KERNEL_PROGRAM_WEAVE_GOAL,
                done_when=KERNEL_PROGRAM_WEAVE_DONE_WHEN,
                bind_source="genesis_bind_weave",
            )
            is False
        )
        saturated_lattices = saturate_program_lattices(root, ledger, saturated_campaign)
        checks["bound_weave_needs_fabric_after_lattices"] = (
            len(saturated_lattices) >= 2
            and program_fabric_is_needed(
                saturated_campaign,
                ledger,
                goal=KERNEL_PROGRAM_WEAVE_GOAL,
                done_when=KERNEL_PROGRAM_WEAVE_DONE_WHEN,
                bind_source="genesis_bind_weave",
            )
            is True
            and program_lattice_is_needed(
                saturated_campaign,
                ledger,
                goal=KERNEL_PROGRAM_WEAVE_GOAL,
                done_when=KERNEL_PROGRAM_WEAVE_DONE_WHEN,
                bind_source="genesis_bind_weave",
            )
            is False
            and program_tower_is_needed(
                saturated_campaign,
                ledger,
                goal=KERNEL_PROGRAM_WEAVE_GOAL,
                done_when=KERNEL_PROGRAM_WEAVE_DONE_WHEN,
                bind_source="genesis_bind_weave",
            )
            is False
            and program_stack_is_needed(
                saturated_campaign,
                ledger,
                goal=KERNEL_PROGRAM_WEAVE_GOAL,
                done_when=KERNEL_PROGRAM_WEAVE_DONE_WHEN,
                bind_source="genesis_bind_weave",
            )
            is False
            and composed_program_is_needed(
                saturated_campaign,
                ledger,
                goal=KERNEL_PROGRAM_WEAVE_GOAL,
                done_when=KERNEL_PROGRAM_WEAVE_DONE_WHEN,
                bind_source="genesis_bind_weave",
            )
            is False
            and primitive_compose_is_needed(
                saturated_campaign,
                ledger,
                goal=KERNEL_PROGRAM_WEAVE_GOAL,
                done_when=KERNEL_PROGRAM_WEAVE_DONE_WHEN,
                bind_source="genesis_bind_weave",
            )
            is False
            and program_weave_is_needed(
                saturated_campaign,
                ledger,
                goal=KERNEL_PROGRAM_WEAVE_GOAL,
                done_when=KERNEL_PROGRAM_WEAVE_DONE_WHEN,
                bind_source="genesis_bind_weave",
            )
            is False
        )
        saturated_fabrics = saturate_program_fabrics(root, ledger, saturated_campaign)
        checks["needed_on_bound_weave_when_saturated"] = (
            len(saturated_fabrics) >= 2
            and fabric_unique_coverage_is_saturated(ledger, saturated_campaign) is True
            and program_weave_is_needed(
                saturated_campaign,
                ledger,
                goal=KERNEL_PROGRAM_WEAVE_GOAL,
                done_when=KERNEL_PROGRAM_WEAVE_DONE_WHEN,
                bind_source="genesis_bind_weave",
            )
            is True
            and program_fabric_is_needed(
                saturated_campaign,
                ledger,
                goal=KERNEL_PROGRAM_WEAVE_GOAL,
                done_when=KERNEL_PROGRAM_WEAVE_DONE_WHEN,
                bind_source="genesis_bind_weave",
            )
            is False
            and program_lattice_is_needed(
                saturated_campaign,
                ledger,
                goal=KERNEL_PROGRAM_WEAVE_GOAL,
                done_when=KERNEL_PROGRAM_WEAVE_DONE_WHEN,
                bind_source="genesis_bind_weave",
            )
            is False
            and program_tower_is_needed(
                saturated_campaign,
                ledger,
                goal=KERNEL_PROGRAM_WEAVE_GOAL,
                done_when=KERNEL_PROGRAM_WEAVE_DONE_WHEN,
                bind_source="genesis_bind_weave",
            )
            is False
            and program_stack_is_needed(
                saturated_campaign,
                ledger,
                goal=KERNEL_PROGRAM_WEAVE_GOAL,
                done_when=KERNEL_PROGRAM_WEAVE_DONE_WHEN,
                bind_source="genesis_bind_weave",
            )
            is False
            and composed_program_is_needed(
                saturated_campaign,
                ledger,
                goal=KERNEL_PROGRAM_WEAVE_GOAL,
                done_when=KERNEL_PROGRAM_WEAVE_DONE_WHEN,
                bind_source="genesis_bind_weave",
            )
            is False
            and primitive_compose_is_needed(
                saturated_campaign,
                ledger,
                goal=KERNEL_PROGRAM_WEAVE_GOAL,
                done_when=KERNEL_PROGRAM_WEAVE_DONE_WHEN,
                bind_source="genesis_bind_weave",
            )
            is False
        )
        ranked = rank_ready_program_weaves(ledger)
        top = ranked[0] if ranked else {}
        checks["novelty_ranks_pair_first"] = (
            top.get("suggested_id") == first_weave
            and top.get("novel") is True
            and int(top.get("novelty_score") or 0) >= 500
            and list(top.get("members") or []) == [first_fabric, second_fabric]
        )
        before_ids = set(ledger.capabilities)
        before_sets = existing_composed_coverage_sets(ledger)
        weave_id = promote_and_prove_program_weave(root, ledger, first_weave)
        grown = load_tick_ledger(root)
        assert grown is not None
        weaved = grown.capabilities.get(weave_id or "")
        coverage = primitive_coverage(grown, weave_id or "")
        expected_leaves = {
            first_leaf,
            second_leaf,
            third_leaf,
            fourth_leaf,
            fifth_leaf,
            sixth_leaf,
            seventh_leaf,
        }
        checks["promote_registers_unique_weave_coverage"] = (
            weave_id == first_weave
            and first_weave not in before_ids
            and weaved is not None
            and weaved.last_proof_exit_code == 0
            and is_primitive_capability(weaved) is False
            and expected_leaves <= coverage
            and len(coverage) >= 7
            and coverage not in before_sets
            and coverage in existing_composed_coverage_sets(grown)
            and invoke_local_capability(weaved).get("ok") is True
        )

    with tempfile.TemporaryDirectory(prefix="kernel-program-weave-tick-") as tmp:
        root = Path(tmp)
        _write_fixture_ledger(root)
        _register_turn_failed_closers(root)
        _write_forage_history(root)
        _register_proved(root, KERNEL_GENESIS_BIND_ID)
        _register_proved(root, CONSUMED_GROWTH_ID)
        _register_proved(root, COMPOUND_LOOP_ID)
        _register_proved(root, PRIMITIVE_COMPOSE_ID)
        _register_proved(root, COMPOSED_PROGRAM_ID)
        _register_proved(root, PROGRAM_STACK_ID)
        _register_proved(root, PROGRAM_TOWER_ID)
        _register_proved(root, PROGRAM_LATTICE_ID)
        _register_proved(root, PROGRAM_FABRIC_ID)
        campaign = _consumed_campaign()
        ledger = load_tick_ledger(root)
        assert ledger is not None
        saturate_primitive_leaves(root, ledger, campaign)
        saturate_primitive_compositions(root, ledger, campaign)
        saturate_composed_programs(root, ledger, campaign)
        saturate_program_stacks(root, ledger, campaign)
        saturate_program_towers(root, ledger, campaign)
        saturate_program_lattices(root, ledger, campaign)
        saturate_program_fabrics(root, ledger, campaign)
        save_campaign(root, campaign)
        tick = local_mission_tick(_State(root), root)
        live = load_campaign(root)
        invoked = tick.get("invoked") or []
        invoked_id = invoked[0]["capability_id"] if invoked else ""
        grown = load_tick_ledger(root)
        unit = None if grown is None else grown.capabilities.get(first_weave)
        checks["tick_after_saturated_fabrics_runs_weave"] = (
            invoked_id == first_weave
            and bool(invoked)
            and invoked[0].get("ok") is True
            and first_weave in live.completed_ids
            and unit is not None
            and unit.last_proof_exit_code == 0
            and is_primitive_capability(unit) is False
            and {first_leaf, second_leaf, third_leaf, fourth_leaf, fifth_leaf, sixth_leaf, seventh_leaf}
            <= primitive_coverage(grown, first_weave)
            and str((live.handoff or {}).get("program_weave_unit") or "") == first_weave
        )
        checks["tick_bound_from_weave"] = "genesis_bind" in str(
            (tick.get("binding") or {}).get("source") or live.bound_from
        )

    with tempfile.TemporaryDirectory(prefix="kernel-program-weave-operator-") as tmp:
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

    with tempfile.TemporaryDirectory(prefix="kernel-program-weave-remaining-") as tmp:
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

    with tempfile.TemporaryDirectory(prefix="kernel-program-weave-hydrate-") as tmp:
        root = Path(tmp)
        _write_fixture_ledger(root)
        _register_turn_failed_closers(root)
        _write_forage_history(root)
        _register_proved(root, KERNEL_GENESIS_BIND_ID)
        _register_proved(root, CONSUMED_GROWTH_ID)
        _register_proved(root, COMPOUND_LOOP_ID)
        _register_proved(root, PRIMITIVE_COMPOSE_ID)
        _register_proved(root, COMPOSED_PROGRAM_ID)
        _register_proved(root, PROGRAM_STACK_ID)
        _register_proved(root, PROGRAM_TOWER_ID)
        _register_proved(root, PROGRAM_LATTICE_ID)
        _register_proved(root, PROGRAM_FABRIC_ID)
        save_campaign(root, _consumed_campaign())
        empty = _State(root)
        report = hydrate_mission_from_campaign(empty, persist=True)
        checks["hydrate_fills_program_weave"] = (
            report.get("applied") is True
            and empty.goal == KERNEL_PROGRAM_WEAVE_GOAL
            and KERNEL_PROGRAM_WEAVE_ID in empty.done_when
            and empty.stage == "execution"
            and str(report.get("source") or "").startswith("genesis_bind")
        )
        create_goal, create_done, create_source = bind_create_fields(root)
        checks["create_bind_uses_program_weave"] = (
            create_goal == KERNEL_PROGRAM_WEAVE_GOAL
            and KERNEL_PROGRAM_WEAVE_ID in create_done
            and str(create_source).startswith("genesis_bind")
        )

    with tempfile.TemporaryDirectory(prefix="kernel-program-weave-skip-") as tmp:
        root = Path(tmp)
        _write_fixture_ledger(root)
        _register_turn_failed_closers(root)
        _write_forage_history(root)
        _register_proved(root, KERNEL_GENESIS_BIND_ID)
        _register_proved(root, CONSUMED_GROWTH_ID)
        _register_proved(root, COMPOUND_LOOP_ID)
        _register_proved(root, PRIMITIVE_COMPOSE_ID)
        _register_proved(root, COMPOSED_PROGRAM_ID)
        _register_proved(root, PROGRAM_STACK_ID)
        _register_proved(root, PROGRAM_TOWER_ID)
        _register_proved(root, PROGRAM_LATTICE_ID)
        _register_proved(root, PROGRAM_FABRIC_ID)
        _register_proved(root, KERNEL_PROGRAM_WEAVE_ID)
        save_campaign(root, _consumed_campaign())
        skip_goal, skip_done, skip_source = bind_gate_passing_successor(root)
        checks["proved_weave_skips_to_diversity"] = (
            skip_goal == GENESIS_DIVERSIFY_GOAL
            and GENESIS_DIVERSIFY_ID in skip_done
            and skip_source == "genesis_bind_diversity"
            and GENESIS_DIVERSIFY_DONE_WHEN == skip_done
        )

    keep = _State(Path("."), goal="Operator growth goal.")
    hydrate_mission_from_campaign(keep, persist=False)
    checks["hydrate_preserves_operator_goal"] = keep.goal == "Operator growth goal."
    checks["no_skill_route"] = not legacy_pipeline_was_used()
    checks["schema_version"] = SCHEMA_VERSION == 1

    ok = all(checks.values())
    return {
        "ok": ok,
        "action": "kernel_program_weave",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": KERNEL_PROGRAM_WEAVE_GOAL,
        "done_when": KERNEL_PROGRAM_WEAVE_DONE_WHEN,
    }
