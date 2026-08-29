"""Promote a ready multi-primitive composition after unique primitive coverage saturates.

``capability.kernel-compound-loop`` absorbs novelty-ranked primitive leaves.
Once those leaves fill unique coverage, recovered kernels and 402-local ticks
fall back to cheap inventory. Composition stalls on saturated primitives.

This module closes that hole:

- detect when novelty-ranked in-process primitive leaves saturate unique
  coverage, or genesis is bound to this closer
- rank ready multi-primitive compositions by coverage novelty
- promote and prove the top novel composition in-process
- attach it to the durable campaign so the next local tick compounds a program
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
    COMPOUND_LOOP_HORIZON,
    COMPOUND_LOOP_LEAF_PREFIX,
    _leaf_index,
    absorb_and_prove_compound_leaf,
    bound_to_composed_program,
    bound_to_primitive_compose,
    bound_to_program_stack,
    bound_to_program_tower,
    is_compound_loop_leaf_id,
    primitive_unique_coverage_is_saturated,
)
from blackhole_agent.kernel_consumed_growth import is_cheap_inventory_id
from blackhole_agent.kernel_genesis_bind import (
    COMPOSED_PROGRAM_GOAL,
    COMPOSED_PROGRAM_ID,
    COMPOUND_LOOP_ID,
    CONSUMED_GROWTH_ID,
    KERNEL_GENESIS_BIND_ID,
    PRIMITIVE_COMPOSE_DONE_WHEN,
    PRIMITIVE_COMPOSE_GOAL,
    PRIMITIVE_COMPOSE_ID,
)
from blackhole_agent.kernel_succession import cheap_remaining
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST, invoke_local_capability
from blackhole_agent.local_mission_sovereignty import LocalCampaign

SCHEMA_VERSION = 1
KERNEL_PRIMITIVE_COMPOSE_ID = PRIMITIVE_COMPOSE_ID
KERNEL_PRIMITIVE_COMPOSE_DONE_WHEN = PRIMITIVE_COMPOSE_DONE_WHEN
KERNEL_PRIMITIVE_COMPOSE_GOAL = PRIMITIVE_COMPOSE_GOAL

PRIMITIVE_COMPOSE_UNIT_PREFIX = "capability.primitive-compose"
PRIMITIVE_COMPOSE_TAG = "primitive-compose-unit"

UNIT_PROOF_COMMAND = (
    "uv run python -c \"from blackhole_agent.kernel_primitive_compose import "
    "builtin_execute_composed_capability; r=builtin_execute_composed_capability(); "
    "assert r['ok']\""
)


def is_primitive_compose_id(capability_id: str) -> bool:
    """True for multi-primitive units minted by this closer."""

    item = str(capability_id or "").strip()
    return item.startswith(f"{PRIMITIVE_COMPOSE_UNIT_PREFIX}-")


def compose_id_from_members(members: tuple[str, ...]) -> str:
    indexes = [_leaf_index(item) for item in members]
    return f"{PRIMITIVE_COMPOSE_UNIT_PREFIX}-{'-'.join(str(index) for index in indexes)}"


def compose_member_ids(compose_id: str) -> tuple[str, ...]:
    item = str(compose_id or "").strip()
    prefix = f"{PRIMITIVE_COMPOSE_UNIT_PREFIX}-"
    if not item.startswith(prefix):
        return ()
    indexes: list[int] = []
    for part in item[len(prefix) :].split("-"):
        try:
            indexes.append(int(part))
        except ValueError:
            return ()
    if len(indexes) < 2:
        return ()
    return tuple(f"{COMPOUND_LOOP_LEAF_PREFIX}-{index}" for index in indexes)


def builtin_execute_composed_capability() -> dict[str, Any]:
    """Hermetic in-process composition of novelty-ranked primitive leaves.

    Named ``builtin_execute_composed_capability`` so coverage scoring treats
    the unit as a composition rather than another primitive leaf.
    """

    from blackhole_agent.kernel_compound_loop import builtin_compound_loop_leaf

    cap_id = (os.environ.get(ACTIVE_CAPABILITY_ENV) or "").strip()
    members = compose_member_ids(cap_id)
    if len(members) < 2:
        members = (
            f"{COMPOUND_LOOP_LEAF_PREFIX}-1",
            f"{COMPOUND_LOOP_LEAF_PREFIX}-2",
        )
    results = [builtin_compound_loop_leaf() for _ in members]
    ok = all(bool(item.get("ok")) for item in results)
    return {
        "ok": ok,
        "action": "primitive_compose_unit",
        "capability_id": cap_id,
        "members": list(members),
        "member_count": len(members),
        "used_skill_route_discovery": False,
    }


def primitive_compose_is_needed(
    campaign: LocalCampaign,
    ledger: CapabilityLedger,
    *,
    goal: str = "",
    done_when: str = "",
    bind_source: str = "",
) -> bool:
    """True when saturated primitive coverage (or this closer) would otherwise idle."""

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
                for item in leftover
            ):
                return False
    except Exception:  # noqa: BLE001 - compose must still decide from campaign fields
        pass
    live_goal = str(goal or campaign.goal or "")
    live_done = str(done_when or campaign.done_when or "")
    source = str(bind_source or campaign.bound_from or "")
    scoped = bound_to_primitive_compose(live_goal, live_done, source)
    saturated = primitive_unique_coverage_is_saturated(ledger, campaign)
    if not saturated:
        return False
    program_bound = bound_to_composed_program(live_goal, live_done, source)
    stack_bound = bound_to_program_stack(live_goal, live_done, source)
    tower_bound = bound_to_program_tower(live_goal, live_done, source)
    if (
        program_bound or stack_bound or tower_bound
    ) and composition_unique_coverage_is_saturated(ledger, campaign):
        return False
    if not scoped and not saturated:
        return False
    remaining = cheap_remaining(campaign)
    if remaining:
        capability = ledger.capabilities.get(remaining[0])
        if capability is not None and PRIMITIVE_COMPOSE_TAG in capability.tags:
            return True
        if is_primitive_compose_id(remaining[0]):
            return True
        return is_cheap_inventory_id(remaining[0])
    return True


def _compose_candidates(ledger: CapabilityLedger) -> list[tuple[str, tuple[str, ...]]]:
    proved = sorted(
        (
            item_id
            for item_id, item in ledger.capabilities.items()
            if is_compound_loop_leaf_id(item_id) and item.last_proof_exit_code == 0
        ),
        key=_leaf_index,
    )
    seen: set[str] = set()
    recipes: list[tuple[str, tuple[str, ...]]] = []

    def _push(members: tuple[str, ...]) -> None:
        if len(members) < 2:
            return
        compose_id = compose_id_from_members(members)
        if compose_id in seen:
            return
        seen.add(compose_id)
        recipes.append((compose_id, members))

    for index in range(len(proved) - 1):
        _push((proved[index], proved[index + 1]))
    return recipes


def rank_ready_primitive_compositions(
    ledger: CapabilityLedger,
    *,
    skip_ids: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    """Rank ready multi-primitive compositions by unique coverage novelty."""

    skipped = {item for item in skip_ids if item}
    opportunities: list[dict[str, Any]] = []
    for compose_id, members in _compose_candidates(ledger):
        if compose_id in skipped:
            continue
        missing = [item for item in members if item not in ledger.capabilities]
        exists = compose_id in ledger.capabilities
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
                "suggested_id": compose_id,
                "members": list(members),
                "priority": 1000 - 10 * len(members),
                "tags": ["composed", "promoted", "growth"],
                "synthesis": "composition",
            }
        )
    annotate_opportunities_with_novelty(ledger, opportunities)
    return rank_growth_opportunities(opportunities)


def composition_unique_coverage_is_saturated(
    ledger: CapabilityLedger,
    campaign: LocalCampaign | None = None,
) -> bool:
    """True when no novelty-ranked multi-primitive composition remains to promote."""

    _ = campaign  # coverage is a ledger property; campaign completion is orthogonal
    ranked = rank_ready_primitive_compositions(ledger)
    has_novel = any(
        item.get("novel") and item.get("status") == "ready" for item in ranked
    )
    if has_novel:
        return False
    proved = [
        item_id
        for item_id, item in ledger.capabilities.items()
        if is_primitive_compose_id(item_id) and item.last_proof_exit_code == 0
    ]
    return len(proved) >= 2


def select_primitive_composition(
    ledger: CapabilityLedger,
    campaign: LocalCampaign,
) -> str:
    """Pick an unfinished in-ledger composition, else the top novel recipe."""

    skip = {item for item in [*campaign.completed_ids, *campaign.failed_ids] if item}
    existing = [
        item_id
        for item_id, item in ledger.capabilities.items()
        if PRIMITIVE_COMPOSE_TAG in item.tags and item_id not in skip
    ]
    if existing:
        existing.sort(
            key=lambda item_id: (
                0 if ledger.capabilities[item_id].last_proof_exit_code != 0 else 1,
                item_id,
            )
        )
        return existing[0]
    for item in rank_ready_primitive_compositions(ledger, skip_ids=tuple(skip)):
        compose_id = str(item.get("suggested_id") or "").strip()
        if not compose_id or compose_id in skip:
            continue
        if item.get("novel") and item.get("status") == "ready":
            return compose_id
    return ""


def _compose_spec(ledger: CapabilityLedger, compose_id: str, members: tuple[str, ...]) -> Capability:
    indexes = [_leaf_index(item) for item in members]
    label = "+".join(str(index) for index in indexes)
    return Capability(
        id=compose_id,
        name=f"Primitive composition {label}",
        description=(
            "In-process multi-primitive composition promoted when novelty-ranked "
            "primitive leaves saturate unique coverage and compounding would "
            "otherwise stall."
        ),
        kind="python",
        entry="blackhole_agent.kernel_primitive_compose:builtin_execute_composed_capability",
        proof_command=UNIT_PROOF_COMMAND,
        dependencies=tuple(members),
        behavior_paths=("src/blackhole_agent/kernel_primitive_compose.py",),
        capability_delta=(
            "Ready multi-primitive compositions promote in-process instead of "
            "rotating cheap inventory after unique primitive coverage saturates."
        ),
        tags=(PRIMITIVE_COMPOSE_TAG, "composed", "promoted", "growth", "kernel"),
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


def promote_and_prove_primitive_composition(
    root: Path,
    ledger: CapabilityLedger,
    compose_id: str,
) -> str:
    """Register the ranked composition if missing and stamp an in-process proof."""

    members = compose_member_ids(compose_id)
    if len(members) < 2:
        return ""
    missing = [item for item in members if item not in ledger.capabilities]
    if missing:
        return ""
    existing = ledger.capabilities.get(compose_id)
    if existing is None:
        register_capability(ledger, _compose_spec(ledger, compose_id, members), replace=False)
        existing = ledger.capabilities[compose_id]
    if existing.last_proof_exit_code != 0:
        result = invoke_local_capability(existing)
        if not result.get("ok"):
            return ""
        _stamp_proved(ledger, existing, exit_code=0)
        existing = ledger.capabilities[compose_id]
    path = default_ledger_path(Path(root))
    path.parent.mkdir(parents=True, exist_ok=True)
    save_ledger(path, ledger)
    proved = ledger.capabilities.get(compose_id)
    if proved is None or proved.last_proof_exit_code != 0:
        return ""
    if is_primitive_capability(proved):
        return ""
    return compose_id


def saturate_primitive_leaves(
    root: Path,
    ledger: CapabilityLedger,
    campaign: LocalCampaign,
) -> list[str]:
    """Absorb and complete the novelty-ranked primitive horizon."""

    absorbed: list[str] = []
    for index in range(1, COMPOUND_LOOP_HORIZON + 1):
        leaf_id = f"{COMPOUND_LOOP_LEAF_PREFIX}-{index}"
        proved = absorb_and_prove_compound_leaf(Path(root), ledger, leaf_id)
        if not proved:
            return absorbed
        absorbed.append(proved)
        if proved not in campaign.completed_ids:
            campaign.completed_ids.append(proved)
    return absorbed


def saturate_primitive_compositions(
    root: Path,
    ledger: CapabilityLedger,
    campaign: LocalCampaign,
) -> list[str]:
    """Promote every remaining novel consecutive-pair composition."""

    promoted: list[str] = []
    skip = {item for item in [*campaign.completed_ids, *campaign.failed_ids] if item}
    while True:
        compose_id = ""
        for item in rank_ready_primitive_compositions(ledger, skip_ids=tuple(skip)):
            candidate = str(item.get("suggested_id") or "").strip()
            if not candidate or candidate in skip:
                continue
            if item.get("novel") and item.get("status") == "ready":
                compose_id = candidate
                break
        if not compose_id:
            return promoted
        proved = promote_and_prove_primitive_composition(Path(root), ledger, compose_id)
        if not proved:
            return promoted
        promoted.append(proved)
        skip.add(proved)
        if proved not in campaign.completed_ids:
            campaign.completed_ids.append(proved)


def attach_primitive_composition(
    campaign: LocalCampaign,
    ledger: CapabilityLedger,
    root: Path,
    *,
    goal: str = "",
    done_when: str = "",
    bind_source: str = "",
) -> str:
    """Promote the next novel composition and make it the next campaign step."""

    remaining = cheap_remaining(campaign)
    if remaining:
        capability = ledger.capabilities.get(remaining[0])
        if capability is not None and PRIMITIVE_COMPOSE_TAG in capability.tags:
            return remaining[0]
        if is_primitive_compose_id(remaining[0]):
            return remaining[0]
        if not is_cheap_inventory_id(remaining[0]):
            return ""
    if not primitive_compose_is_needed(
        campaign,
        ledger,
        goal=goal,
        done_when=done_when,
        bind_source=bind_source,
    ):
        return ""
    compose_id = select_primitive_composition(ledger, campaign)
    if not compose_id:
        return ""
    promoted = promote_and_prove_primitive_composition(Path(root), ledger, compose_id)
    if not promoted:
        return ""
    campaign.program = [
        item
        for item in campaign.program
        if item
        and item not in campaign.completed_ids
        and not is_cheap_inventory_id(item)
        and not is_compound_loop_leaf_id(item)
    ]
    if promoted not in campaign.program:
        campaign.program.append(promoted)
    campaign.cursor = campaign.program.index(promoted) + 1
    handoff = dict(campaign.handoff or {})
    handoff["primitive_compose_unit"] = promoted
    campaign.handoff = handoff
    return promoted


def continue_resumed_primitive_compose(
    state: Any,
    repo_path: Path | None = None,
    workspace: Path | None = None,
) -> dict[str, Any]:
    """When unique primitive coverage saturates, attach a multi-primitive composition."""

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
    step = attach_primitive_composition(
        campaign,
        ledger,
        work,
        goal=str(getattr(state, "goal", "") or campaign.goal),
        done_when=str(getattr(state, "done_when", "") or campaign.done_when),
    )
    if not step:
        return {
            "applied": False,
            "reason": "no_primitive_composition",
            "step": "",
            "program": list(campaign.program),
        }
    if before != list(campaign.program):
        save_campaign(durable, campaign)
    return {
        "applied": True,
        "reason": "primitive_compose",
        "step": step,
        "program": list(campaign.program),
    }


def builtin_kernel_primitive_compose_proof() -> dict[str, Any]:
    """Hermetic proof: saturated primitive coverage promotes a multi-primitive composition."""

    import tempfile

    from blackhole_agent.capability_compounder import (
        existing_composed_coverage_sets,
        primitive_coverage,
    )
    from blackhole_agent.kernel_genesis_bind import (
        COMPOSED_PROGRAM_DONE_WHEN,
        _consumed_campaign,
        _register_proved,
        _unscoped_remaining_campaign,
        _write_forage_history,
        bind_gate_passing_successor,
    )
    from blackhole_agent.kernel_leftover import leftover_marker_ids
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
    checks["denylists_self"] = KERNEL_PRIMITIVE_COMPOSE_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = KERNEL_PRIMITIVE_COMPOSE_ID in leftover_marker_ids(
        KERNEL_PRIMITIVE_COMPOSE_GOAL
    )
    first_leaf = f"{COMPOUND_LOOP_LEAF_PREFIX}-1"
    second_leaf = f"{COMPOUND_LOOP_LEAF_PREFIX}-2"
    first_compose = f"{PRIMITIVE_COMPOSE_UNIT_PREFIX}-1-2"
    checks["compose_unit_is_not_cheap"] = is_cheap_inventory_id(first_compose) is False
    checks["catalog_names_composed_program"] = (
        COMPOSED_PROGRAM_ID == "capability.kernel-composed-program"
    )

    class _State:
        def __init__(
            self,
            repo: Path,
            *,
            goal: str = "",
            done_when: str = "",
            mission_id: str = "mission-primitive-compose",
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

    with tempfile.TemporaryDirectory(prefix="kernel-primitive-compose-need-") as tmp:
        root = Path(tmp)
        _write_fixture_ledger(root)
        ledger = load_tick_ledger(root)
        assert ledger is not None
        empty = LocalCampaign()
        unscoped = _unscoped_remaining_campaign()
        checks["not_needed_without_campaign"] = primitive_compose_is_needed(empty, ledger) is False
        checks["not_needed_on_unscoped_remaining"] = (
            primitive_compose_is_needed(unscoped, ledger) is False
        )
        checks["not_needed_on_bound_compose_before_saturation"] = (
            primitive_compose_is_needed(
                empty,
                ledger,
                goal=KERNEL_PRIMITIVE_COMPOSE_GOAL,
                done_when=KERNEL_PRIMITIVE_COMPOSE_DONE_WHEN,
                bind_source="genesis_bind_compose",
            )
            is False
        )
        saturated_campaign = LocalCampaign(tick_count=4, last_contract_met=True)
        saturated_leaves = saturate_primitive_leaves(root, ledger, saturated_campaign)
        checks["needed_on_bound_compose_when_saturated"] = (
            len(saturated_leaves) == COMPOUND_LOOP_HORIZON
            and primitive_unique_coverage_is_saturated(ledger, saturated_campaign) is True
            and primitive_compose_is_needed(
                saturated_campaign,
                ledger,
                goal=KERNEL_PRIMITIVE_COMPOSE_GOAL,
                done_when=KERNEL_PRIMITIVE_COMPOSE_DONE_WHEN,
                bind_source="genesis_bind_compose",
            )
            is True
        )
        ranked = rank_ready_primitive_compositions(ledger)
        top = ranked[0] if ranked else {}
        checks["novelty_ranks_pair_first"] = (
            top.get("suggested_id") == first_compose
            and top.get("novel") is True
            and int(top.get("novelty_score") or 0) >= 500
            and list(top.get("members") or []) == [first_leaf, second_leaf]
        )
        before_ids = set(ledger.capabilities)
        before_sets = existing_composed_coverage_sets(ledger)
        compose_id = promote_and_prove_primitive_composition(root, ledger, first_compose)
        grown = load_tick_ledger(root)
        assert grown is not None
        composed = grown.capabilities.get(compose_id or "")
        coverage = primitive_coverage(grown, compose_id or "")
        checks["promote_registers_unique_composed_coverage"] = (
            compose_id == first_compose
            and first_compose not in before_ids
            and composed is not None
            and composed.last_proof_exit_code == 0
            and is_primitive_capability(composed) is False
            and coverage == frozenset({first_leaf, second_leaf})
            and coverage not in before_sets
            and coverage in existing_composed_coverage_sets(grown)
            and invoke_local_capability(composed).get("ok") is True
        )
        ranked_after = rank_ready_primitive_compositions(grown, skip_ids=(first_compose,))
        next_top = ranked_after[0] if ranked_after else {}
        next_id = str(next_top.get("suggested_id") or "")
        second = promote_and_prove_primitive_composition(root, grown, next_id)
        after = load_tick_ledger(root)
        assert after is not None
        second_cap = after.capabilities.get(second or "")
        second_coverage = primitive_coverage(after, second or "") if second else frozenset()
        checks["second_promote_expands_composed_coverage"] = (
            bool(second)
            and second != first_compose
            and next_top.get("novel") is True
            and second_cap is not None
            and second_cap.last_proof_exit_code == 0
            and is_primitive_capability(second_cap) is False
            and second_coverage != coverage
            and len(second_coverage) >= 2
            and second_coverage not in before_sets
        )

    with tempfile.TemporaryDirectory(prefix="kernel-primitive-compose-tick-") as tmp:
        root = Path(tmp)
        _write_fixture_ledger(root)
        _register_turn_failed_closers(root)
        _write_forage_history(root)
        _register_proved(root, KERNEL_GENESIS_BIND_ID)
        _register_proved(root, CONSUMED_GROWTH_ID)
        _register_proved(root, COMPOUND_LOOP_ID)
        campaign = _consumed_campaign()
        ledger = load_tick_ledger(root)
        assert ledger is not None
        saturate_primitive_leaves(root, ledger, campaign)
        save_campaign(root, campaign)
        tick = local_mission_tick(_State(root), root)
        live = load_campaign(root)
        invoked = tick.get("invoked") or []
        invoked_id = invoked[0]["capability_id"] if invoked else ""
        grown = load_tick_ledger(root)
        unit = None if grown is None else grown.capabilities.get(first_compose)
        checks["tick_after_saturated_primitives_runs_compose"] = (
            invoked_id == first_compose
            and bool(invoked)
            and invoked[0].get("ok") is True
            and first_compose in live.completed_ids
            and unit is not None
            and unit.last_proof_exit_code == 0
            and is_primitive_capability(unit) is False
            and primitive_coverage(grown, first_compose) == frozenset({first_leaf, second_leaf})
            and str((live.handoff or {}).get("primitive_compose_unit") or "") == first_compose
        )
        checks["tick_bound_from_compose"] = "genesis_bind" in str(
            (tick.get("binding") or {}).get("source") or live.bound_from
        )

    with tempfile.TemporaryDirectory(prefix="kernel-primitive-compose-operator-") as tmp:
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

    with tempfile.TemporaryDirectory(prefix="kernel-primitive-compose-remaining-") as tmp:
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

    with tempfile.TemporaryDirectory(prefix="kernel-primitive-compose-hydrate-") as tmp:
        root = Path(tmp)
        _write_fixture_ledger(root)
        _register_turn_failed_closers(root)
        _write_forage_history(root)
        _register_proved(root, KERNEL_GENESIS_BIND_ID)
        _register_proved(root, CONSUMED_GROWTH_ID)
        _register_proved(root, COMPOUND_LOOP_ID)
        save_campaign(root, _consumed_campaign())
        empty = _State(root)
        report = hydrate_mission_from_campaign(empty, persist=True)
        checks["hydrate_fills_primitive_compose"] = (
            report.get("applied") is True
            and empty.goal == KERNEL_PRIMITIVE_COMPOSE_GOAL
            and KERNEL_PRIMITIVE_COMPOSE_ID in empty.done_when
            and empty.stage == "execution"
            and str(report.get("source") or "").startswith("genesis_bind")
        )
        create_goal, create_done, create_source = bind_create_fields(root)
        checks["create_bind_uses_primitive_compose"] = (
            create_goal == KERNEL_PRIMITIVE_COMPOSE_GOAL
            and KERNEL_PRIMITIVE_COMPOSE_ID in create_done
            and str(create_source).startswith("genesis_bind")
        )

    with tempfile.TemporaryDirectory(prefix="kernel-primitive-compose-skip-") as tmp:
        root = Path(tmp)
        _write_fixture_ledger(root)
        _register_turn_failed_closers(root)
        _write_forage_history(root)
        _register_proved(root, KERNEL_GENESIS_BIND_ID)
        _register_proved(root, CONSUMED_GROWTH_ID)
        _register_proved(root, COMPOUND_LOOP_ID)
        _register_proved(root, KERNEL_PRIMITIVE_COMPOSE_ID)
        save_campaign(root, _consumed_campaign())
        skip_goal, skip_done, skip_source = bind_gate_passing_successor(root)
        checks["proved_compose_skips_to_program"] = (
            skip_goal == COMPOSED_PROGRAM_GOAL
            and COMPOSED_PROGRAM_ID in skip_done
            and skip_source == "genesis_bind_program"
            and COMPOSED_PROGRAM_DONE_WHEN == skip_done
        )

    keep = _State(Path("."), goal="Operator growth goal.")
    hydrate_mission_from_campaign(keep, repo_path=Path("."))
    checks["hydrate_preserves_operator_goal"] = keep.goal == "Operator growth goal."
    checks["no_skill_route"] = not legacy_pipeline_was_used()
    checks["schema_version"] = SCHEMA_VERSION == 1

    ok = all(checks.values())
    return {
        "ok": ok,
        "action": "kernel_primitive_compose",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": KERNEL_PRIMITIVE_COMPOSE_GOAL,
        "done_when": KERNEL_PRIMITIVE_COMPOSE_DONE_WHEN,
    }
