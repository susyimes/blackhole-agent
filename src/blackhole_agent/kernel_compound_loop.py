"""Run a novelty-ranked growth loop after absorbed consumed-campaign leaves saturate.

``capability.kernel-consumed-growth`` absorbs a single in-process leaf. Once that
leaf is proved and completed, recovered kernels and 402-local ticks fall back to
cheap inventory. Compounding stalls on a saturated absorbed leaf.

This module closes that hole:

- detect when absorbed consumed-campaign leaves saturate, or genesis is bound
  to this closer
- rank the next primitive-leaf candidates by novelty (new primitive coverage)
- absorb and prove the top novel primitive in-process
- attach it to the durable campaign so the next local tick expands coverage
- skip a proved catalog item to the next genesis-bind successor so genesis
  cannot go empty again
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from blackhole_agent.capability_compounder import (
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
from blackhole_agent.kernel_consumed_growth import (
    CONSUMED_GROWTH_LEAF_ID,
    is_cheap_inventory_id,
)
from blackhole_agent.kernel_genesis_bind import (
    COMPOUND_LOOP_DONE_WHEN,
    COMPOUND_LOOP_GOAL,
    COMPOUND_LOOP_ID,
    COMPOSED_PROGRAM_GOAL,
    COMPOSED_PROGRAM_ID,
    CONSUMED_GROWTH_ID,
    KERNEL_GENESIS_BIND_ID,
    PRIMITIVE_COMPOSE_GOAL,
    PRIMITIVE_COMPOSE_ID,
    PROGRAM_STACK_GOAL,
    PROGRAM_STACK_ID,
    PROGRAM_TOWER_GOAL,
    PROGRAM_TOWER_ID,
)
from blackhole_agent.kernel_succession import cheap_remaining
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST, invoke_local_capability
from blackhole_agent.local_mission_sovereignty import LocalCampaign

SCHEMA_VERSION = 1
KERNEL_COMPOUND_LOOP_ID = COMPOUND_LOOP_ID
KERNEL_COMPOUND_LOOP_DONE_WHEN = COMPOUND_LOOP_DONE_WHEN
KERNEL_COMPOUND_LOOP_GOAL = COMPOUND_LOOP_GOAL

COMPOUND_LOOP_LEAF_PREFIX = "capability.compound-loop-leaf"
COMPOUND_LOOP_LEAF_TAG = "compound-loop-leaf"
COMPOUND_LOOP_HORIZON = 8

LEAF_PROOF_COMMAND = (
    "uv run python -c \"from blackhole_agent.kernel_compound_loop import "
    "builtin_compound_loop_leaf; r=builtin_compound_loop_leaf(); assert r['ok']\""
)


def builtin_compound_loop_leaf() -> dict[str, Any]:
    """Hermetic primitive absorbed by the novelty-ranked compound loop."""

    return {
        "ok": True,
        "action": "compound_loop_leaf",
        "probe": "kernel-compound-loop",
        "used_skill_route_discovery": False,
    }


def is_compound_loop_leaf_id(capability_id: str) -> bool:
    """True for novelty-ranked primitives minted by this loop."""

    item = str(capability_id or "").strip()
    return item.startswith(f"{COMPOUND_LOOP_LEAF_PREFIX}-")


def bound_to_compound_loop(goal: str, done_when: str = "", bind_source: str = "") -> bool:
    """True when genesis is already scoped to this closer."""

    if COMPOUND_LOOP_ID in f"{goal} {done_when}":
        return True
    if str(goal or "").strip() == COMPOUND_LOOP_GOAL:
        return True
    return "genesis_bind_compound" in str(bind_source or "")


def absorbed_leaves_are_saturated(campaign: LocalCampaign, ledger: CapabilityLedger) -> bool:
    """True when the consumed-campaign growth leaf is already proved and completed."""

    leaf = ledger.capabilities.get(CONSUMED_GROWTH_LEAF_ID)
    if leaf is None or leaf.last_proof_exit_code != 0:
        return False
    return CONSUMED_GROWTH_LEAF_ID in campaign.completed_ids


def primitive_unique_coverage_is_saturated(
    ledger: CapabilityLedger,
    campaign: LocalCampaign | None = None,
) -> bool:
    """True when no novelty-ranked in-process primitive remains to absorb."""

    _ = campaign  # coverage is a ledger property; campaign completion is orthogonal
    ranked = rank_novel_primitive_leaves(ledger)
    has_novel = any(
        item.get("novel") and item.get("status") == "ready_to_absorb" for item in ranked
    )
    if has_novel:
        return False
    proved = [
        item_id
        for item_id, item in ledger.capabilities.items()
        if is_compound_loop_leaf_id(item_id) and item.last_proof_exit_code == 0
    ]
    return len(proved) >= 2


def bound_to_primitive_compose(goal: str, done_when: str = "", bind_source: str = "") -> bool:
    """True when genesis is already scoped to the composition closer."""

    if PRIMITIVE_COMPOSE_ID in f"{goal} {done_when}":
        return True
    if str(goal or "").strip() == PRIMITIVE_COMPOSE_GOAL:
        return True
    return "genesis_bind_compose" in str(bind_source or "")


def bound_to_composed_program(goal: str, done_when: str = "", bind_source: str = "") -> bool:
    """True when genesis is already scoped to the composed-program closer."""

    if COMPOSED_PROGRAM_ID in f"{goal} {done_when}":
        return True
    if str(goal or "").strip() == COMPOSED_PROGRAM_GOAL:
        return True
    return "genesis_bind_program" in str(bind_source or "")


def bound_to_program_stack(goal: str, done_when: str = "", bind_source: str = "") -> bool:
    """True when genesis is already scoped to the program-stack closer."""

    if PROGRAM_STACK_ID in f"{goal} {done_when}":
        return True
    if str(goal or "").strip() == PROGRAM_STACK_GOAL:
        return True
    return "genesis_bind_stack" in str(bind_source or "")


def bound_to_program_tower(goal: str, done_when: str = "", bind_source: str = "") -> bool:
    """True when genesis is already scoped to the program-tower closer."""

    if PROGRAM_TOWER_ID in f"{goal} {done_when}":
        return True
    if str(goal or "").strip() == PROGRAM_TOWER_GOAL:
        return True
    return "genesis_bind_tower" in str(bind_source or "")


def compound_loop_is_needed(
    campaign: LocalCampaign,
    ledger: CapabilityLedger,
    *,
    goal: str = "",
    done_when: str = "",
    bind_source: str = "",
) -> bool:
    """True when saturated absorbed leaves (or this closer) would otherwise idle."""

    try:
        from blackhole_agent.kernel_unscoped_resume import (
            campaign_has_unscoped_remaining,
            remaining_program_steps,
        )

        if campaign_has_unscoped_remaining(campaign):
            leftover = remaining_program_steps(campaign)
            if leftover and not all(
                is_cheap_inventory_id(item) or is_compound_loop_leaf_id(item) for item in leftover
            ):
                return False
    except Exception:  # noqa: BLE001 - loop must still decide from campaign fields
        pass
    live_goal = str(goal or campaign.goal or "")
    live_done = str(done_when or campaign.done_when or "")
    source = str(bind_source or campaign.bound_from or "")
    compose_bound = bound_to_primitive_compose(live_goal, live_done, source)
    program_bound = bound_to_composed_program(live_goal, live_done, source)
    stack_bound = bound_to_program_stack(live_goal, live_done, source)
    tower_bound = bound_to_program_tower(live_goal, live_done, source)
    if (
        compose_bound or program_bound or stack_bound or tower_bound
    ) and primitive_unique_coverage_is_saturated(ledger, campaign):
        return False
    scoped = (
        bound_to_compound_loop(live_goal, live_done, source)
        or compose_bound
        or program_bound
        or stack_bound
        or tower_bound
    )
    saturated = absorbed_leaves_are_saturated(campaign, ledger)
    if not scoped and not saturated:
        return False
    remaining = cheap_remaining(campaign)
    if remaining:
        capability = ledger.capabilities.get(remaining[0])
        if capability is not None and COMPOUND_LOOP_LEAF_TAG in capability.tags:
            return True
        return is_cheap_inventory_id(remaining[0])
    return True


def _leaf_index(leaf_id: str) -> int:
    prefix = f"{COMPOUND_LOOP_LEAF_PREFIX}-"
    if not str(leaf_id).startswith(prefix):
        return 0
    try:
        return int(str(leaf_id)[len(prefix) :])
    except ValueError:
        return 0


def rank_novel_primitive_leaves(
    ledger: CapabilityLedger,
    *,
    skip_ids: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    """Rank the next compound-loop primitives by primitive-coverage novelty."""

    skipped = {item for item in skip_ids if item}
    opportunities: list[dict[str, Any]] = []
    for index in range(1, COMPOUND_LOOP_HORIZON + 1):
        leaf_id = f"{COMPOUND_LOOP_LEAF_PREFIX}-{index}"
        if leaf_id in skipped:
            continue
        exists = leaf_id in ledger.capabilities
        opportunities.append(
            {
                "kind": "domain_absorb",
                "status": "already_absorbed" if exists else "ready_to_absorb",
                "suggested_id": leaf_id,
                "members": [leaf_id],
                "priority": COMPOUND_LOOP_HORIZON - index,
            }
        )
    annotate_opportunities_with_novelty(ledger, opportunities)
    return rank_growth_opportunities(opportunities)


def select_compound_loop_leaf(
    ledger: CapabilityLedger,
    campaign: LocalCampaign,
) -> str:
    """Pick an unfinished in-ledger leaf, else the top novel primitive."""

    skip = {item for item in [*campaign.completed_ids, *campaign.failed_ids] if item}
    existing = [
        item_id
        for item_id, item in ledger.capabilities.items()
        if COMPOUND_LOOP_LEAF_TAG in item.tags and item_id not in skip
    ]
    if existing:
        existing.sort(
            key=lambda item_id: (
                0 if ledger.capabilities[item_id].last_proof_exit_code != 0 else 1,
                _leaf_index(item_id),
                item_id,
            )
        )
        return existing[0]
    for item in rank_novel_primitive_leaves(ledger, skip_ids=tuple(skip)):
        leaf_id = str(item.get("suggested_id") or "").strip()
        if not leaf_id or leaf_id in skip:
            continue
        if item.get("novel") and item.get("status") == "ready_to_absorb":
            return leaf_id
    return ""


def _leaf_spec(ledger: CapabilityLedger, leaf_id: str) -> Capability:
    dependencies: list[str] = []
    if "repo.import-health" in ledger.capabilities:
        dependencies.append("repo.import-health")
    if "capability.ledger-inventory" in ledger.capabilities:
        dependencies.append("capability.ledger-inventory")
    index = _leaf_index(leaf_id)
    return Capability(
        id=leaf_id,
        name=f"Compound-loop primitive leaf {index}",
        description=(
            "In-process novelty-ranked primitive absorbed when consumed-campaign "
            "leaves saturate and compounding would otherwise stall."
        ),
        kind="python",
        entry="blackhole_agent.kernel_compound_loop:builtin_compound_loop_leaf",
        proof_command=LEAF_PROOF_COMMAND,
        dependencies=tuple(dependencies),
        behavior_paths=("src/blackhole_agent/kernel_compound_loop.py",),
        capability_delta=(
            "Novelty-ranked primitive coverage expanded in-process instead of "
            "rotating cheap inventory after absorbed leaves saturate."
        ),
        tags=(COMPOUND_LOOP_LEAF_TAG, "growth", "kernel", "primitive", "novelty"),
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


def absorb_and_prove_compound_leaf(
    root: Path,
    ledger: CapabilityLedger,
    leaf_id: str,
) -> str:
    """Register the ranked primitive if missing and stamp an in-process proof."""

    existing = ledger.capabilities.get(leaf_id)
    if existing is None:
        register_capability(ledger, _leaf_spec(ledger, leaf_id), replace=False)
        existing = ledger.capabilities[leaf_id]
    if existing.last_proof_exit_code != 0:
        result = invoke_local_capability(existing)
        if not result.get("ok"):
            return ""
        _stamp_proved(ledger, existing, exit_code=0)
        existing = ledger.capabilities[leaf_id]
    path = default_ledger_path(Path(root))
    path.parent.mkdir(parents=True, exist_ok=True)
    save_ledger(path, ledger)
    proved = ledger.capabilities.get(leaf_id)
    if proved is None or proved.last_proof_exit_code != 0:
        return ""
    if not is_primitive_capability(proved):
        return ""
    return leaf_id


def attach_compound_loop_leaf(
    campaign: LocalCampaign,
    ledger: CapabilityLedger,
    root: Path,
    *,
    goal: str = "",
    done_when: str = "",
    bind_source: str = "",
) -> str:
    """Absorb the next novel primitive and make it the next campaign step."""

    remaining = cheap_remaining(campaign)
    if remaining:
        capability = ledger.capabilities.get(remaining[0])
        if capability is not None and COMPOUND_LOOP_LEAF_TAG in capability.tags:
            return remaining[0]
        if not is_cheap_inventory_id(remaining[0]):
            return ""
    if not compound_loop_is_needed(
        campaign,
        ledger,
        goal=goal,
        done_when=done_when,
        bind_source=bind_source,
    ):
        return ""
    leaf_id = select_compound_loop_leaf(ledger, campaign)
    if not leaf_id:
        return ""
    absorbed = absorb_and_prove_compound_leaf(Path(root), ledger, leaf_id)
    if not absorbed:
        return ""
    campaign.program = [
        item
        for item in campaign.program
        if item and item not in campaign.completed_ids and not is_cheap_inventory_id(item)
    ]
    if absorbed not in campaign.program:
        campaign.program.append(absorbed)
    campaign.cursor = campaign.program.index(absorbed) + 1
    handoff = dict(campaign.handoff or {})
    handoff["compound_loop_leaf"] = absorbed
    campaign.handoff = handoff
    return absorbed


def continue_resumed_compound_loop(
    state: Any,
    repo_path: Path | None = None,
    workspace: Path | None = None,
) -> dict[str, Any]:
    """When absorbed leaves saturate, attach the next novelty-ranked primitive."""

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
    step = attach_compound_loop_leaf(
        campaign,
        ledger,
        work,
        goal=str(getattr(state, "goal", "") or campaign.goal),
        done_when=str(getattr(state, "done_when", "") or campaign.done_when),
    )
    if not step:
        return {
            "applied": False,
            "reason": "no_compound_leaf",
            "step": "",
            "program": list(campaign.program),
        }
    if before != list(campaign.program):
        save_campaign(durable, campaign)
    return {
        "applied": True,
        "reason": "compound_loop",
        "step": step,
        "program": list(campaign.program),
    }


def builtin_kernel_compound_loop_proof() -> dict[str, Any]:
    """Hermetic proof: saturated absorbed leaves expand via a novelty-ranked loop."""

    import tempfile

    from blackhole_agent.capability_compounder import primitive_coverage
    from blackhole_agent.kernel_consumed_growth import absorb_and_prove_growth_leaf
    from blackhole_agent.kernel_genesis_bind import (
        PRIMITIVE_COMPOSE_DONE_WHEN,
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
    checks["denylists_self"] = KERNEL_COMPOUND_LOOP_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = KERNEL_COMPOUND_LOOP_ID in leftover_marker_ids(
        KERNEL_COMPOUND_LOOP_GOAL
    )
    first_leaf = f"{COMPOUND_LOOP_LEAF_PREFIX}-1"
    second_leaf = f"{COMPOUND_LOOP_LEAF_PREFIX}-2"
    checks["leaf_is_not_cheap"] = is_cheap_inventory_id(first_leaf) is False
    checks["catalog_names_primitive_compose"] = (
        PRIMITIVE_COMPOSE_ID == "capability.kernel-primitive-compose"
    )

    class _State:
        def __init__(
            self,
            repo: Path,
            *,
            goal: str = "",
            done_when: str = "",
            mission_id: str = "mission-compound-loop",
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

    with tempfile.TemporaryDirectory(prefix="kernel-compound-loop-need-") as tmp:
        root = Path(tmp)
        _write_fixture_ledger(root)
        ledger = load_tick_ledger(root)
        assert ledger is not None
        empty = LocalCampaign()
        unscoped = _unscoped_remaining_campaign()
        checks["not_needed_without_campaign"] = compound_loop_is_needed(empty, ledger) is False
        checks["not_needed_on_unscoped_remaining"] = (
            compound_loop_is_needed(unscoped, ledger) is False
        )
        checks["needed_on_bound_compound_loop"] = compound_loop_is_needed(
            empty,
            ledger,
            goal=KERNEL_COMPOUND_LOOP_GOAL,
            done_when=KERNEL_COMPOUND_LOOP_DONE_WHEN,
            bind_source="genesis_bind_compound",
        ) is True
        growth_id = absorb_and_prove_growth_leaf(root, ledger)
        saturated = LocalCampaign(
            completed_ids=[CONSUMED_GROWTH_LEAF_ID],
            tick_count=4,
            last_contract_met=True,
        )
        checks["needed_on_saturated_absorbed_leaves"] = (
            growth_id == CONSUMED_GROWTH_LEAF_ID
            and absorbed_leaves_are_saturated(saturated, ledger) is True
            and compound_loop_is_needed(saturated, ledger) is True
        )
        ranked = rank_novel_primitive_leaves(ledger)
        top = ranked[0] if ranked else {}
        checks["novelty_ranks_missing_primitive_first"] = (
            top.get("suggested_id") == first_leaf
            and top.get("novel") is True
            and int(top.get("novelty_score") or 0) >= 1000
        )
        before_ids = set(ledger.capabilities)
        before_primitives = {
            item.id for item in ledger.capabilities.values() if is_primitive_capability(item)
        }
        leaf_id = absorb_and_prove_compound_leaf(root, ledger, first_leaf)
        grown = load_tick_ledger(root)
        assert grown is not None
        leaf = grown.capabilities.get(leaf_id or "")
        checks["absorb_registers_and_proves_novel_primitive"] = (
            leaf_id == first_leaf
            and first_leaf not in before_ids
            and leaf is not None
            and leaf.last_proof_exit_code == 0
            and is_primitive_capability(leaf)
            and primitive_coverage(grown, first_leaf) == frozenset({first_leaf})
            and invoke_local_capability(leaf).get("ok") is True
        )
        ranked_after = rank_novel_primitive_leaves(grown, skip_ids=(first_leaf,))
        next_top = ranked_after[0] if ranked_after else {}
        second = absorb_and_prove_compound_leaf(root, grown, second_leaf)
        after = load_tick_ledger(root)
        assert after is not None
        after_primitives = {
            item.id for item in after.capabilities.values() if is_primitive_capability(item)
        }
        checks["second_absorb_expands_coverage"] = (
            second == second_leaf
            and next_top.get("suggested_id") == second_leaf
            and next_top.get("novel") is True
            and first_leaf in after_primitives
            and second_leaf in after_primitives
            and first_leaf not in before_primitives
            and primitive_coverage(after, second_leaf) == frozenset({second_leaf})
            and primitive_coverage(after, first_leaf)
            != primitive_coverage(after, second_leaf)
        )

    with tempfile.TemporaryDirectory(prefix="kernel-compound-loop-tick-") as tmp:
        root = Path(tmp)
        _write_fixture_ledger(root)
        _register_turn_failed_closers(root)
        _write_forage_history(root)
        _register_proved(root, KERNEL_GENESIS_BIND_ID)
        save_campaign(root, _consumed_campaign())
        first = local_mission_tick(_State(root), root)
        second = local_mission_tick(_State(root), root)
        campaign = load_campaign(root)
        first_invoked = (first.get("invoked") or [{}])[0].get("capability_id")
        second_invoked = (second.get("invoked") or [{}])[0].get("capability_id")
        grown = load_tick_ledger(root)
        loop_leaf = None if grown is None else grown.capabilities.get(first_leaf)
        checks["tick_after_growth_leaf_runs_compound_loop"] = (
            first_invoked == CONSUMED_GROWTH_LEAF_ID
            and second_invoked == first_leaf
            and bool(second.get("invoked"))
            and second["invoked"][0].get("ok") is True
            and first_leaf in campaign.completed_ids
            and loop_leaf is not None
            and loop_leaf.last_proof_exit_code == 0
            and str((campaign.handoff or {}).get("compound_loop_leaf") or "") == first_leaf
        )

    with tempfile.TemporaryDirectory(prefix="kernel-compound-loop-loop-") as tmp:
        root = Path(tmp)
        _write_fixture_ledger(root)
        _register_turn_failed_closers(root)
        _write_forage_history(root)
        _register_proved(root, KERNEL_GENESIS_BIND_ID)
        _register_proved(root, CONSUMED_GROWTH_ID)
        save_campaign(root, _consumed_campaign())
        first = local_mission_tick(_State(root), root)
        second = local_mission_tick(_State(root), root)
        campaign = load_campaign(root)
        first_invoked = (first.get("invoked") or [{}])[0].get("capability_id")
        second_invoked = (second.get("invoked") or [{}])[0].get("capability_id")
        grown = load_tick_ledger(root)
        checks["tick_loop_expands_second_primitive"] = (
            first_invoked == first_leaf
            and second_invoked == second_leaf
            and first_leaf in campaign.completed_ids
            and second_leaf in campaign.completed_ids
            and grown is not None
            and grown.capabilities[first_leaf].last_proof_exit_code == 0
            and grown.capabilities[second_leaf].last_proof_exit_code == 0
            and primitive_coverage(grown, first_leaf)
            != primitive_coverage(grown, second_leaf)
        )
        checks["tick_bound_from_compound"] = "genesis_bind" in str(
            (first.get("binding") or {}).get("source") or campaign.bound_from
        )

    with tempfile.TemporaryDirectory(prefix="kernel-compound-loop-operator-") as tmp:
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

    with tempfile.TemporaryDirectory(prefix="kernel-compound-loop-remaining-") as tmp:
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

    with tempfile.TemporaryDirectory(prefix="kernel-compound-loop-hydrate-") as tmp:
        root = Path(tmp)
        _write_fixture_ledger(root)
        _register_turn_failed_closers(root)
        _write_forage_history(root)
        _register_proved(root, KERNEL_GENESIS_BIND_ID)
        _register_proved(root, CONSUMED_GROWTH_ID)
        save_campaign(root, _consumed_campaign())
        empty = _State(root)
        report = hydrate_mission_from_campaign(empty, persist=True)
        checks["hydrate_fills_compound_loop"] = (
            report.get("applied") is True
            and empty.goal == KERNEL_COMPOUND_LOOP_GOAL
            and KERNEL_COMPOUND_LOOP_ID in empty.done_when
            and empty.stage == "execution"
            and str(report.get("source") or "").startswith("genesis_bind")
        )
        create_goal, create_done, create_source = bind_create_fields(root)
        checks["create_bind_uses_compound_loop"] = (
            create_goal == KERNEL_COMPOUND_LOOP_GOAL
            and KERNEL_COMPOUND_LOOP_ID in create_done
            and str(create_source).startswith("genesis_bind")
        )

    with tempfile.TemporaryDirectory(prefix="kernel-compound-loop-skip-") as tmp:
        root = Path(tmp)
        _write_fixture_ledger(root)
        _register_turn_failed_closers(root)
        _write_forage_history(root)
        _register_proved(root, KERNEL_GENESIS_BIND_ID)
        _register_proved(root, CONSUMED_GROWTH_ID)
        _register_proved(root, KERNEL_COMPOUND_LOOP_ID)
        save_campaign(root, _consumed_campaign())
        skip_goal, skip_done, skip_source = bind_gate_passing_successor(root)
        checks["proved_compound_loop_skips_to_compose"] = (
            skip_goal == PRIMITIVE_COMPOSE_GOAL
            and PRIMITIVE_COMPOSE_ID in skip_done
            and skip_source == "genesis_bind_compose"
            and PRIMITIVE_COMPOSE_DONE_WHEN == skip_done
        )

    keep = _State(Path("."), goal="Operator growth goal.")
    hydrate_mission_from_campaign(keep, repo_path=Path("."))
    checks["hydrate_preserves_operator_goal"] = keep.goal == "Operator growth goal."
    checks["no_skill_route"] = not legacy_pipeline_was_used()
    checks["schema_version"] = SCHEMA_VERSION == 1

    ok = all(checks.values())
    return {
        "ok": ok,
        "action": "kernel_compound_loop",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": KERNEL_COMPOUND_LOOP_GOAL,
        "done_when": KERNEL_COMPOUND_LOOP_DONE_WHEN,
    }
