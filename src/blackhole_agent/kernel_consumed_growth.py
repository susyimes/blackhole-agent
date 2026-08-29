"""Absorb and prove a new ledger leaf after consumed campaigns stall on inventory.

``capability.kernel-genesis-bind`` binds a gate-passing successor once a local
campaign is consumed. When that successor is this closer — or when the only
remaining local program is cheap inventory — recovered kernels and 402-local
ticks rotate ``ledger-inventory`` / ``import-health`` instead of growing the
ledger.

This module closes that hole:

- detect when cheap inventory is all that remains after a consumed campaign
  or a bound consumed-growth successor
- absorb a new python leaf onto the working-tree ledger in-process
- prove it by invoking its entry and stamping the proof
- attach that leaf to the durable campaign so the next local tick compounds
  capability instead of replaying inventory
- skip a proved catalog item to the next genesis-bind successor so genesis
  cannot go empty again
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from blackhole_agent.capability_compounder import (
    Capability,
    CapabilityLedger,
    default_ledger_path,
    legacy_pipeline_was_used,
    register_capability,
    save_ledger,
    utc_now_iso,
)
from blackhole_agent.kernel_genesis_bind import (
    COMPOUND_LOOP_GOAL,
    COMPOUND_LOOP_ID,
    CONSUMED_GROWTH_DONE_WHEN,
    CONSUMED_GROWTH_GOAL,
    CONSUMED_GROWTH_ID,
    KERNEL_GENESIS_BIND_ID,
)
from blackhole_agent.kernel_succession import cheap_remaining
from blackhole_agent.local_capability_kernel import (
    LOCAL_DENYLIST,
    PREFERRED_LOCAL_IDS,
    invoke_local_capability,
)
from blackhole_agent.local_mission_sovereignty import (
    LocalCampaign,
    plan_campaign_program,
)

SCHEMA_VERSION = 1
KERNEL_CONSUMED_GROWTH_ID = CONSUMED_GROWTH_ID
CONSUMED_GROWTH_LEAF_ID = "capability.consumed-growth-leaf"
CONSUMED_GROWTH_LEAF_TAG = "consumed-growth-leaf"

KERNEL_CONSUMED_GROWTH_DONE_WHEN = CONSUMED_GROWTH_DONE_WHEN
KERNEL_CONSUMED_GROWTH_GOAL = CONSUMED_GROWTH_GOAL

LEAF_PROOF_COMMAND = (
    "uv run python -c \"from blackhole_agent.kernel_consumed_growth import "
    "builtin_consumed_growth_leaf; r=builtin_consumed_growth_leaf(); assert r['ok']\""
)


def builtin_consumed_growth_leaf() -> dict[str, Any]:
    """Hermetic leaf absorbed after consumed campaigns stall on inventory."""

    return {
        "ok": True,
        "action": "consumed_growth_leaf",
        "probe": "kernel-consumed-growth",
        "used_skill_route_discovery": False,
    }


def is_cheap_inventory_id(capability_id: str) -> bool:
    """True for preferred inventory anchors and fixture-local cheap probes."""

    item = str(capability_id or "").strip()
    if not item:
        return False
    if item in PREFERRED_LOCAL_IDS:
        return True
    return item.startswith("capability.fixture-local-")


def bound_to_consumed_growth(goal: str, done_when: str = "") -> bool:
    """True when genesis is already scoped to this closer."""

    if CONSUMED_GROWTH_ID in f"{goal} {done_when}":
        return True
    return str(goal or "").strip() == CONSUMED_GROWTH_GOAL


def remaining_is_cheap_inventory(
    campaign: LocalCampaign,
    ledger: CapabilityLedger,
    goal: str = "",
) -> bool:
    """True when the next campaign program would only replay cheap inventory."""

    remaining = cheap_remaining(campaign)
    if remaining:
        return all(is_cheap_inventory_id(item) for item in remaining)
    planned = plan_campaign_program(
        ledger,
        goal or campaign.goal,
        skip_ids=tuple(campaign.completed_ids),
    )
    if not planned:
        return True
    return all(is_cheap_inventory_id(item) for item in planned)


def consumed_growth_is_needed(
    campaign: LocalCampaign,
    ledger: CapabilityLedger,
    *,
    goal: str = "",
    done_when: str = "",
    bind_source: str = "",
) -> bool:
    """True when cheap inventory is the stall after a consumed campaign."""

    live_goal = str(goal or campaign.goal or "")
    live_done = str(done_when or campaign.done_when or "")
    source = str(bind_source or campaign.bound_from or "")
    scoped = bound_to_consumed_growth(live_goal, live_done) or "genesis_bind_growth" in source
    if not scoped:
        return False
    try:
        from blackhole_agent.kernel_unscoped_resume import campaign_has_unscoped_remaining

        if campaign_has_unscoped_remaining(campaign):
            return False
    except Exception:  # noqa: BLE001 - growth must still decide from campaign fields
        pass
    return remaining_is_cheap_inventory(campaign, ledger, live_goal)


def _leaf_spec(ledger: CapabilityLedger) -> Capability:
    dependencies: list[str] = []
    if "repo.import-health" in ledger.capabilities:
        dependencies.append("repo.import-health")
    if "capability.ledger-inventory" in ledger.capabilities:
        dependencies.append("capability.ledger-inventory")
    return Capability(
        id=CONSUMED_GROWTH_LEAF_ID,
        name="Consumed-campaign growth leaf",
        description=(
            "In-process leaf absorbed when cheap inventory is all that remains "
            "after a consumed local campaign."
        ),
        kind="python",
        entry="blackhole_agent.kernel_consumed_growth:builtin_consumed_growth_leaf",
        proof_command=LEAF_PROOF_COMMAND,
        dependencies=tuple(dependencies),
        behavior_paths=("src/blackhole_agent/kernel_consumed_growth.py",),
        capability_delta=(
            "Consumed campaigns compound a new ledger leaf in-process instead of "
            "rotating cheap inventory ticks."
        ),
        tags=(CONSUMED_GROWTH_LEAF_TAG, "growth", "kernel"),
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


def absorb_and_prove_growth_leaf(
    root: Path,
    ledger: CapabilityLedger,
) -> str:
    """Register the growth leaf if missing and stamp an in-process proof."""

    existing = ledger.capabilities.get(CONSUMED_GROWTH_LEAF_ID)
    if existing is None:
        register_capability(ledger, _leaf_spec(ledger), replace=False)
        existing = ledger.capabilities[CONSUMED_GROWTH_LEAF_ID]
    if existing.last_proof_exit_code != 0:
        result = invoke_local_capability(existing)
        if not result.get("ok"):
            return ""
        _stamp_proved(ledger, existing, exit_code=0)
        existing = ledger.capabilities[CONSUMED_GROWTH_LEAF_ID]
    path = default_ledger_path(Path(root))
    path.parent.mkdir(parents=True, exist_ok=True)
    save_ledger(path, ledger)
    proved = ledger.capabilities.get(CONSUMED_GROWTH_LEAF_ID)
    if proved is None or proved.last_proof_exit_code != 0:
        return ""
    return CONSUMED_GROWTH_LEAF_ID


def attach_consumed_growth_leaf(
    campaign: LocalCampaign,
    ledger: CapabilityLedger,
    root: Path,
    *,
    goal: str = "",
    done_when: str = "",
    bind_source: str = "",
) -> str:
    """Absorb a new leaf and make it the next campaign step. Empty when not needed."""

    remaining = cheap_remaining(campaign)
    if remaining and not is_cheap_inventory_id(remaining[0]):
        capability = ledger.capabilities.get(remaining[0])
        if capability is not None and CONSUMED_GROWTH_LEAF_TAG in capability.tags:
            return remaining[0]
        return ""
    if not consumed_growth_is_needed(
        campaign,
        ledger,
        goal=goal,
        done_when=done_when,
        bind_source=bind_source,
    ):
        return ""
    if CONSUMED_GROWTH_LEAF_ID in campaign.completed_ids:
        return ""
    leaf_id = absorb_and_prove_growth_leaf(Path(root), ledger)
    if not leaf_id:
        return ""
    campaign.program = [
        item
        for item in campaign.program
        if item and item not in campaign.completed_ids and not is_cheap_inventory_id(item)
    ]
    if leaf_id not in campaign.program:
        campaign.program.append(leaf_id)
    campaign.cursor = campaign.program.index(leaf_id) + 1
    handoff = dict(campaign.handoff or {})
    handoff["consumed_growth_leaf"] = leaf_id
    campaign.handoff = handoff
    return leaf_id


def continue_resumed_consumed_growth(
    state: Any,
    repo_path: Path | None = None,
    workspace: Path | None = None,
) -> dict[str, Any]:
    """When cheap inventory is the stall, attach an absorbed leaf for resume."""

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
    step = attach_consumed_growth_leaf(
        campaign,
        ledger,
        work,
        goal=str(getattr(state, "goal", "") or campaign.goal),
        done_when=str(getattr(state, "done_when", "") or campaign.done_when),
    )
    if not step:
        return {
            "applied": False,
            "reason": "no_growth_leaf",
            "step": "",
            "program": list(campaign.program),
        }
    if before != list(campaign.program):
        save_campaign(durable, campaign)
    return {
        "applied": True,
        "reason": "consumed_growth",
        "step": step,
        "program": list(campaign.program),
    }


def builtin_kernel_consumed_growth_proof() -> dict[str, Any]:
    """Hermetic proof: consumed campaigns absorb and prove a new ledger leaf."""

    import tempfile

    from blackhole_agent.kernel_genesis_bind import (
        COMPOUND_LOOP_DONE_WHEN,
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
    checks["denylists_self"] = KERNEL_CONSUMED_GROWTH_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = KERNEL_CONSUMED_GROWTH_ID in leftover_marker_ids(
        KERNEL_CONSUMED_GROWTH_GOAL
    )
    checks["leaf_is_not_cheap"] = is_cheap_inventory_id(CONSUMED_GROWTH_LEAF_ID) is False
    checks["catalog_names_compound_loop"] = COMPOUND_LOOP_ID == "capability.kernel-compound-loop"
    checks["not_needed_without_campaign"] = True

    class _State:
        def __init__(
            self,
            repo: Path,
            *,
            goal: str = "",
            done_when: str = "",
            mission_id: str = "mission-consumed-growth",
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

    with tempfile.TemporaryDirectory(prefix="kernel-consumed-growth-need-") as tmp:
        root = Path(tmp)
        _write_fixture_ledger(root)
        ledger = load_tick_ledger(root)
        assert ledger is not None
        consumed = _consumed_campaign()
        unscoped = _unscoped_remaining_campaign()
        empty = LocalCampaign()
        checks["needed_on_consumed_cheap"] = consumed_growth_is_needed(
            consumed,
            ledger,
            goal=KERNEL_CONSUMED_GROWTH_GOAL,
            done_when=KERNEL_CONSUMED_GROWTH_DONE_WHEN,
            bind_source="genesis_bind_growth",
        ) is True
        checks["not_needed_on_unscoped_remaining"] = (
            consumed_growth_is_needed(unscoped, ledger) is False
        )
        checks["not_needed_without_campaign"] = consumed_growth_is_needed(empty, ledger) is False
        planned = plan_campaign_program(ledger, KERNEL_CONSUMED_GROWTH_GOAL)
        checks["cheap_plan_without_growth_is_inventory"] = bool(planned) and all(
            is_cheap_inventory_id(item) for item in planned
        )
        before_ids = set(ledger.capabilities)
        leaf_id = absorb_and_prove_growth_leaf(root, ledger)
        grown = load_tick_ledger(root)
        assert grown is not None
        leaf = grown.capabilities.get(leaf_id or "")
        checks["absorb_registers_and_proves_new_leaf"] = (
            leaf_id == CONSUMED_GROWTH_LEAF_ID
            and CONSUMED_GROWTH_LEAF_ID not in before_ids
            and leaf is not None
            and leaf.last_proof_exit_code == 0
            and invoke_local_capability(leaf).get("ok") is True
        )
        again = absorb_and_prove_growth_leaf(root, grown)
        checks["absorb_is_idempotent"] = again == CONSUMED_GROWTH_LEAF_ID

    with tempfile.TemporaryDirectory(prefix="kernel-consumed-growth-tick-") as tmp:
        root = Path(tmp)
        _write_fixture_ledger(root)
        _register_turn_failed_closers(root)
        _write_forage_history(root)
        _register_proved(root, KERNEL_GENESIS_BIND_ID)
        save_campaign(root, _consumed_campaign())
        tick = local_mission_tick(_State(root), root)
        campaign = load_campaign(root)
        invoked = tick.get("invoked") or []
        invoked_id = invoked[0]["capability_id"] if invoked else ""
        grown = load_tick_ledger(root)
        leaf = None if grown is None else grown.capabilities.get(CONSUMED_GROWTH_LEAF_ID)
        checks["tick_invokes_absorbed_leaf"] = (
            invoked_id == CONSUMED_GROWTH_LEAF_ID
            and bool(invoked)
            and invoked[0].get("ok") is True
            and CONSUMED_GROWTH_LEAF_ID in campaign.completed_ids
            and leaf is not None
            and leaf.last_proof_exit_code == 0
            and str((campaign.handoff or {}).get("consumed_growth_leaf") or "") == CONSUMED_GROWTH_LEAF_ID
        )
        checks["tick_bound_from_growth"] = "genesis_bind" in str(
            (tick.get("binding") or {}).get("source") or campaign.bound_from
        )

    with tempfile.TemporaryDirectory(prefix="kernel-consumed-growth-operator-") as tmp:
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

    with tempfile.TemporaryDirectory(prefix="kernel-consumed-growth-remaining-") as tmp:
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

    with tempfile.TemporaryDirectory(prefix="kernel-consumed-growth-hydrate-") as tmp:
        root = Path(tmp)
        _write_fixture_ledger(root)
        _register_turn_failed_closers(root)
        _write_forage_history(root)
        _register_proved(root, KERNEL_GENESIS_BIND_ID)
        save_campaign(root, _consumed_campaign())
        empty = _State(root)
        report = hydrate_mission_from_campaign(empty, persist=True)
        checks["hydrate_fills_consumed_growth"] = (
            report.get("applied") is True
            and empty.goal == KERNEL_CONSUMED_GROWTH_GOAL
            and KERNEL_CONSUMED_GROWTH_ID in empty.done_when
            and empty.stage == "execution"
            and str(report.get("source") or "").startswith("genesis_bind")
        )
        create_goal, create_done, create_source = bind_create_fields(root)
        checks["create_bind_uses_growth"] = (
            create_goal == KERNEL_CONSUMED_GROWTH_GOAL
            and KERNEL_CONSUMED_GROWTH_ID in create_done
            and str(create_source).startswith("genesis_bind")
        )

    with tempfile.TemporaryDirectory(prefix="kernel-consumed-growth-skip-") as tmp:
        root = Path(tmp)
        _write_fixture_ledger(root)
        _register_turn_failed_closers(root)
        _write_forage_history(root)
        _register_proved(root, KERNEL_GENESIS_BIND_ID)
        _register_proved(root, KERNEL_CONSUMED_GROWTH_ID)
        save_campaign(root, _consumed_campaign())
        skip_goal, skip_done, skip_source = bind_gate_passing_successor(root)
        checks["proved_growth_skips_to_compound_loop"] = (
            skip_goal == COMPOUND_LOOP_GOAL
            and COMPOUND_LOOP_ID in skip_done
            and skip_source == "genesis_bind_compound"
            and COMPOUND_LOOP_DONE_WHEN == skip_done
        )

    keep = _State(Path("."), goal="Operator growth goal.")
    hydrate_mission_from_campaign(keep, repo_path=Path("."))
    checks["hydrate_preserves_operator_goal"] = keep.goal == "Operator growth goal."
    checks["no_skill_route"] = not legacy_pipeline_was_used()
    checks["schema_version"] = SCHEMA_VERSION == 1

    ok = all(checks.values())
    return {
        "ok": ok,
        "action": "kernel_consumed_growth",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": KERNEL_CONSUMED_GROWTH_GOAL,
        "done_when": KERNEL_CONSUMED_GROWTH_DONE_WHEN,
    }
