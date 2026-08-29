"""Bind a gate-passing successor after consumed campaigns leave genesis empty.

``capability.kernel-unscoped-resume`` scopes remaining program steps after
``class_closed`` bind. Once that campaign is consumed, genesis is empty
again. Saturated forage families fail selection gates, and three rejections
block the mission. Local ticks then report cheap inventory work without a
first-class CLI kernel.

This module closes that hole:

- empty genesis after a consumed or unmet-remaining campaign binds a
  successor that ``assess_mission_selection`` accepts
- remaining unscoped campaign work still wins
- operator-supplied fields are never overwritten
- recovered create/hydrate paths fill the same successor so genesis cannot
  invent forage into blocked status
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Mapping

from blackhole_agent.capability_compounder import (
    Capability,
    default_ledger_path,
    legacy_pipeline_was_used,
    load_ledger,
    register_capability,
    save_ledger,
)
from blackhole_agent.kernel_class_closure import class_closure_ids, class_is_closed, load_effective_ledger
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST, _write_fixture_ledger
from blackhole_agent.local_mission_sovereignty import (
    LocalCampaign,
    bind_local_mission,
    load_campaign,
    save_campaign,
)
from blackhole_agent.mission_selection import assess_mission_selection, load_recent_mission_history
from blackhole_agent.pattern_register import blocked_class_id

SCHEMA_VERSION = 1
KERNEL_GENESIS_BIND_ID = "capability.kernel-genesis-bind"
GENESIS_SELECTION_BLOCKED = "genesis_selection_blocked"
CONSUMED_GROWTH_ID = "capability.kernel-consumed-growth"

KERNEL_GENESIS_BIND_DONE_WHEN = (
    f"capability_exists:{KERNEL_GENESIS_BIND_ID};"
    f"capability_proved:{KERNEL_GENESIS_BIND_ID};"
    "no_skill_route"
)
KERNEL_GENESIS_BIND_GOAL = (
    "When a consumed local campaign and closed kernel_turn_failed operational row "
    "leave genesis empty, repair blocked selection: bind a gate-passing successor "
    "mission in-process so saturated forage cannot stall recovered kernels into "
    "blocked status."
)
CONSUMED_GROWTH_DONE_WHEN = (
    f"capability_exists:{CONSUMED_GROWTH_ID};"
    f"capability_proved:{CONSUMED_GROWTH_ID};"
    "no_skill_route"
)
CONSUMED_GROWTH_GOAL = (
    "When cheap inventory ticks are all that remain after a consumed campaign, "
    "repair stalled growth: absorb and prove a new ledger leaf in-process so "
    "recovered kernels compound capability instead of blocking."
)
COMPOUND_LOOP_ID = "capability.kernel-compound-loop"
COMPOUND_LOOP_DONE_WHEN = (
    f"capability_exists:{COMPOUND_LOOP_ID};"
    f"capability_proved:{COMPOUND_LOOP_ID};"
    "no_skill_route"
)
COMPOUND_LOOP_GOAL = (
    "When in-process absorbed leaves from consumed campaigns saturate, repair "
    "stalled compounding: run a novelty-ranked growth loop in-process so recovered "
    "kernels keep expanding primitive coverage instead of blocking."
)
PRIMITIVE_COMPOSE_ID = "capability.kernel-primitive-compose"
PRIMITIVE_COMPOSE_DONE_WHEN = (
    f"capability_exists:{PRIMITIVE_COMPOSE_ID};"
    f"capability_proved:{PRIMITIVE_COMPOSE_ID};"
    "no_skill_route"
)
PRIMITIVE_COMPOSE_GOAL = (
    "When novelty-ranked in-process primitive leaves saturate unique coverage, "
    "repair stalled composition: promote a ready multi-primitive composition "
    "in-process so recovered kernels keep compounding programs instead of blocking."
)
COMPOSED_PROGRAM_ID = "capability.kernel-composed-program"
COMPOSED_PROGRAM_DONE_WHEN = (
    f"capability_exists:{COMPOSED_PROGRAM_ID};"
    f"capability_proved:{COMPOSED_PROGRAM_ID};"
    "no_skill_route"
)
COMPOSED_PROGRAM_GOAL = (
    "When in-process multi-primitive compositions saturate unique coverage, "
    "repair stalled program compounding: promote a ready composed program "
    "in-process so recovered kernels keep stacking programs instead of blocking."
)
PROGRAM_STACK_ID = "capability.kernel-program-stack"
PROGRAM_STACK_DONE_WHEN = (
    f"capability_exists:{PROGRAM_STACK_ID};"
    f"capability_proved:{PROGRAM_STACK_ID};"
    "no_skill_route"
)
PROGRAM_STACK_GOAL = (
    "When in-process composed programs saturate unique coverage, "
    "repair stalled program stacking: promote a ready stacked program "
    "in-process so recovered kernels keep compounding towers instead of blocking."
)
PROGRAM_TOWER_ID = "capability.kernel-program-tower"
PROGRAM_TOWER_DONE_WHEN = (
    f"capability_exists:{PROGRAM_TOWER_ID};"
    f"capability_proved:{PROGRAM_TOWER_ID};"
    "no_skill_route"
)
PROGRAM_TOWER_GOAL = (
    "When unique stacked-program coverage saturates, repair stalled lattice "
    "compounding: promote a ready program tower of stacked programs in-process "
    "so recovered kernels keep compounding lattices instead of rotating cheap "
    "inventory."
)
PROGRAM_LATTICE_ID = "capability.kernel-program-lattice"
PROGRAM_LATTICE_DONE_WHEN = (
    f"capability_exists:{PROGRAM_LATTICE_ID};"
    f"capability_proved:{PROGRAM_LATTICE_ID};"
    "no_skill_route"
)
PROGRAM_LATTICE_GOAL = (
    "After program towers fill unique coverage, repair stalled fabric "
    "compounding: mint a ready program lattice in-process so recovered kernels "
    "keep compounding fabrics instead of falling back to cheap inventory probes."
)

SUCCESSOR_CATALOG: tuple[dict[str, str], ...] = (
    {
        "id": KERNEL_GENESIS_BIND_ID,
        "goal": KERNEL_GENESIS_BIND_GOAL,
        "done_when": KERNEL_GENESIS_BIND_DONE_WHEN,
        "source": "genesis_bind_catalog",
    },
    {
        "id": CONSUMED_GROWTH_ID,
        "goal": CONSUMED_GROWTH_GOAL,
        "done_when": CONSUMED_GROWTH_DONE_WHEN,
        "source": "genesis_bind_growth",
    },
    {
        "id": COMPOUND_LOOP_ID,
        "goal": COMPOUND_LOOP_GOAL,
        "done_when": COMPOUND_LOOP_DONE_WHEN,
        "source": "genesis_bind_compound",
    },
    {
        "id": PRIMITIVE_COMPOSE_ID,
        "goal": PRIMITIVE_COMPOSE_GOAL,
        "done_when": PRIMITIVE_COMPOSE_DONE_WHEN,
        "source": "genesis_bind_compose",
    },
    {
        "id": COMPOSED_PROGRAM_ID,
        "goal": COMPOSED_PROGRAM_GOAL,
        "done_when": COMPOSED_PROGRAM_DONE_WHEN,
        "source": "genesis_bind_program",
    },
    {
        "id": PROGRAM_STACK_ID,
        "goal": PROGRAM_STACK_GOAL,
        "done_when": PROGRAM_STACK_DONE_WHEN,
        "source": "genesis_bind_stack",
    },
    {
        "id": PROGRAM_TOWER_ID,
        "goal": PROGRAM_TOWER_GOAL,
        "done_when": PROGRAM_TOWER_DONE_WHEN,
        "source": "genesis_bind_tower",
    },
    {
        "id": PROGRAM_LATTICE_ID,
        "goal": PROGRAM_LATTICE_GOAL,
        "done_when": PROGRAM_LATTICE_DONE_WHEN,
        "source": "genesis_bind_lattice",
    },
)


def candidate_passes_selection(root: Path, goal: str, done_when: str) -> bool:
    """True when the controller-enforced genesis gates would accept this pair."""

    try:
        return bool(assess_mission_selection(Path(root), goal, done_when).accepted)
    except Exception:  # noqa: BLE001 - bind must still choose a successor
        return False


def genesis_bind_is_needed(campaign: LocalCampaign) -> bool:
    """True after a consumed or met campaign leaves no remaining work.

    First-time empty genesis stays open so the kernel can still choose a
    mission; selection gates remain the safety net for that path.
    """

    try:
        from blackhole_agent.kernel_unscoped_resume import campaign_has_unscoped_remaining

        if campaign_has_unscoped_remaining(campaign):
            return False
    except Exception:  # noqa: BLE001 - bind must still decide from campaign fields
        pass
    ticks = int(campaign.tick_count or 0)
    consumed = bool(str(campaign.consumed_at or "").strip())
    met = campaign.last_contract_met is True
    return ticks > 0 and (consumed or met)


def _catalog_item_open(item: Mapping[str, str], root: Path, *, lineage_ref: str = "") -> bool:
    capability_id = str(item.get("id") or "").strip()
    if not capability_id:
        return False
    try:
        ledger = load_effective_ledger(Path(root), lineage_ref=lineage_ref)
    except Exception:  # noqa: BLE001 - catalog ranking must still continue
        ledger = None
        path = default_ledger_path(Path(root))
        if path.is_file():
            try:
                ledger = load_ledger(path)
            except Exception:  # noqa: BLE001 - catalog ranking must still continue
                ledger = None
    if ledger is None:
        return True
    capability = ledger.capabilities.get(capability_id)
    if capability is None:
        return True
    return capability.last_proof_exit_code != 0


def bind_gate_passing_successor(
    root: Path,
    *,
    campaign: LocalCampaign | None = None,
    lineage_ref: str = "",
) -> tuple[str, str, str]:
    """Return a gate-passing successor, or empty source when nothing binds."""

    live_campaign = campaign if campaign is not None else load_campaign(Path(root))
    if not genesis_bind_is_needed(live_campaign):
        return "", "", ""
    history = load_recent_mission_history(Path(root))
    try:
        from blackhole_agent.experience_fuel import harvest_experience
        from blackhole_agent.local_mission_sovereignty import mission_from_candidate

        fuel = harvest_experience(Path(root), limit=5, lineage_ref=lineage_ref)
        ledger = load_effective_ledger(Path(root), lineage_ref=lineage_ref)
        for item in fuel.candidates:
            class_id = str(item.class_id or "")
            if class_id and class_is_closed(
                class_id,
                Path(root),
                ledger=ledger,
                lineage_ref=lineage_ref,
            ):
                continue
            goal, done_when = mission_from_candidate(
                item,
                ledger=ledger,
                root=Path(root),
                lineage_ref=lineage_ref,
            )
            if not goal or not done_when:
                continue
            gate = assess_mission_selection(
                Path(root),
                goal,
                done_when,
                history=history,
            )
            if gate.accepted:
                return goal, done_when, f"experience/{class_id or 'operational'}"
    except Exception:  # noqa: BLE001 - catalog fallback must still run
        pass
    for item in SUCCESSOR_CATALOG:
        if not _catalog_item_open(item, Path(root), lineage_ref=lineage_ref):
            continue
        goal = str(item.get("goal") or "").strip()
        done_when = str(item.get("done_when") or "").strip()
        if not goal or not done_when:
            continue
        gate = assess_mission_selection(
            Path(root),
            goal,
            done_when,
            history=history,
        )
        if gate.accepted:
            return goal, done_when, str(item.get("source") or "genesis_bind_catalog")
    return "", "", ""


class _State:
    def __init__(
        self,
        repo: Path,
        *,
        goal: str = "",
        done_when: str = "",
        mission_id: str = "mission-genesis-bind",
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


def _consumed_campaign() -> LocalCampaign:
    return LocalCampaign(
        mission_id="prior-consumed",
        goal=(
            "Resume remaining durable campaign work after class_closed left genesis "
            "unscoped: capability.ledger-attestation"
        ),
        done_when="program_passes:capability.ledger-attestation;no_skill_route",
        bound_from="class_closed",
        program=["capability.ledger-inventory", "capability.ledger-attestation"],
        cursor=2,
        completed_ids=["capability.ledger-inventory", "capability.ledger-attestation"],
        tick_count=3,
        last_contract_met=True,
        consumed_at="2026-08-29T08:32:38Z",
        last_summary=(
            "Local mission sovereignty executed capability.goal-stack-health toward "
            "the bound mission without a first-class CLI kernel."
        ),
    )


def _unscoped_remaining_campaign() -> LocalCampaign:
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
        last_summary="bound genesis after class_closed",
    )


def _write_forage_history(root: Path, *, count: int = 6, start_level: int = 145) -> None:
    missions = root / ".blackhole-agent" / "unbound" / "missions"
    missions.mkdir(parents=True, exist_ok=True)
    for index in range(count):
        level = start_level + index
        mission_id = f"forage-{level}"
        state_path = missions / mission_id / "state.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        goal = (
            "Optional later work is reflecting Python nested-namespace class instance "
            f"methods {level} submodule levels down so sdists whose covering API is a "
            f"{level}-level nested Class().method instance rather than a {level - 1}-level "
            "nested Class().method instance can be foraged the same way."
        )
        state_path.write_text(
            json.dumps(
                {
                    "mission_id": mission_id,
                    "status": "complete",
                    "goal": goal,
                    "done_when": "A runnable behavior is proved.",
                    "recent_turns": [],
                }
            ),
            encoding="utf-8",
        )
        stamp = float(index + 1)
        os.utime(state_path, (stamp, stamp))


def _write_complete_mission(root: Path, mission_id: str, goal: str, *, order: int) -> None:
    state_path = root / ".blackhole-agent" / "unbound" / "missions" / mission_id / "state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {
                "mission_id": mission_id,
                "status": "complete",
                "goal": goal,
                "done_when": KERNEL_GENESIS_BIND_DONE_WHEN,
                "recent_turns": [],
            }
        ),
        encoding="utf-8",
    )
    os.utime(state_path, (float(order), float(order)))


def _write_selection_blocked_mission(root: Path) -> None:
    path = (
        Path(root)
        / ".blackhole-agent"
        / "unbound"
        / "missions"
        / "blocked-selection"
        / "state.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "mission_id": "blocked-selection",
                "status": "blocked",
                "goal": "",
                "done_when": "",
                "last_summary": "Autonomous mission selection rejected (3/3): capability_diversity_gate",
                "recent_turns": [
                    {
                        "iteration": 3,
                        "effective_status": "blocked",
                        "summary": "Autonomous mission selection rejected (3/3): capability_diversity_gate",
                        "selection_gate": {
                            "accepted": False,
                            "reasons": [
                                "capability_diversity_gate: capability family is saturated in the recent mission window"
                            ],
                        },
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )


def _write_loop_lineage(root: Path, lineage_ref: str) -> None:
    path = Path(root) / ".blackhole-agent" / "unbound" / "continuous-loop.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"lineage_ref": lineage_ref, "status": "running_mission"}) + "\n",
        encoding="utf-8",
    )


def _git_commit_ledger(root: Path) -> str:
    subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Blackhole Test"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "blackhole@example.invalid"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "lineage ledger"], cwd=root, check=True, capture_output=True)
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return (sha.stdout or "").strip()


def _register_proved(root: Path, capability_id: str) -> None:
    path = default_ledger_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    ledger = load_ledger(path) if path.is_file() else None
    if ledger is None:
        from blackhole_agent.capability_compounder import CapabilityLedger

        ledger = CapabilityLedger()
    register_capability(
        ledger,
        Capability(
            id=capability_id,
            name=capability_id,
            description="Proved catalog successor used by genesis bind.",
            kind="python",
            entry="blackhole_agent.local_capability_kernel:builtin_fixture_probe",
            proof_command="uv run python -c \"print('ok')\"",
            last_proof_exit_code=0,
        ),
        replace=True,
    )
    save_ledger(path, ledger)


def builtin_kernel_genesis_bind_proof() -> dict[str, Any]:
    """Hermetic proof: consumed campaigns bind a gate-passing successor."""

    from blackhole_agent.kernel_leftover import leftover_marker_ids
    from blackhole_agent.kernel_resume import bind_create_fields, hydrate_mission_from_campaign
    from blackhole_agent.kernel_unscoped_resume import _register_turn_failed_closers
    from blackhole_agent.pattern_register import classify_unbound_turn

    checks: dict[str, bool] = {}
    checks["denylists_self"] = KERNEL_GENESIS_BIND_ID in LOCAL_DENYLIST
    checks["closes_genesis_selection_blocked"] = class_closure_ids(GENESIS_SELECTION_BLOCKED) == (
        KERNEL_GENESIS_BIND_ID,
    )
    checks["leftover_marker"] = KERNEL_GENESIS_BIND_ID in leftover_marker_ids(KERNEL_GENESIS_BIND_GOAL)
    checks["needed_on_consumed"] = genesis_bind_is_needed(_consumed_campaign()) is True
    checks["not_needed_on_unscoped_remaining"] = (
        genesis_bind_is_needed(_unscoped_remaining_campaign()) is False
    )
    checks["not_needed_without_campaign"] = genesis_bind_is_needed(LocalCampaign()) is False

    classified = classify_unbound_turn(
        {
            "iteration": 3,
            "effective_status": "blocked",
            "summary": "Autonomous mission selection rejected (3/3): capability_diversity_gate",
            "selection_gate": {
                "accepted": False,
                "reasons": ["capability_diversity_gate: capability family is saturated in the recent mission window"],
            },
        }
    )
    checks["classifies_selection_block"] = any(
        item.get("class_id") == GENESIS_SELECTION_BLOCKED for item in classified
    )
    checks["blocked_helper"] = blocked_class_id({"status": "blocked", "last_summary": "timeout"}) == (
        "mission_blocked"
    )

    with tempfile.TemporaryDirectory(prefix="kernel-genesis-bind-forage-") as tmp:
        root = Path(tmp)
        _write_fixture_ledger(root)
        _register_turn_failed_closers(root)
        _write_forage_history(root)
        save_campaign(root, _consumed_campaign())
        goal, done_when, source = bind_gate_passing_successor(root)
        forage_gate = assess_mission_selection(
            root,
            "Optional later work is reflecting Python nested-namespace class instance methods "
            "151 submodule levels down so sdists whose covering API is a 151-level nested "
            "Class().method instance rather than a 150-level nested Class().method instance "
            "can be foraged the same way.",
            "The next depth-specific fixture passes.",
        )
        successor_ok = candidate_passes_selection(
            root, KERNEL_GENESIS_BIND_GOAL, KERNEL_GENESIS_BIND_DONE_WHEN
        )
    checks["forage_still_rejected"] = forage_gate.accepted is False
    checks["successor_accepted_against_forage"] = successor_ok is True
    checks["successor_beats_forage"] = (
        goal == KERNEL_GENESIS_BIND_GOAL
        and KERNEL_GENESIS_BIND_ID in done_when
        and source == "genesis_bind_catalog"
    )

    with tempfile.TemporaryDirectory(prefix="kernel-genesis-bind-hydrate-") as tmp:
        root = Path(tmp)
        _write_fixture_ledger(root)
        _register_turn_failed_closers(root)
        _write_forage_history(root)
        save_campaign(root, _consumed_campaign())
        empty = _State(root)
        report = hydrate_mission_from_campaign(empty, persist=True)
    checks["hydrate_fills_empty_genesis"] = (
        report.get("applied") is True
        and empty.goal == KERNEL_GENESIS_BIND_GOAL
        and KERNEL_GENESIS_BIND_ID in empty.done_when
        and empty.stage == "execution"
        and str(report.get("source") or "").startswith("genesis_bind")
    )

    with tempfile.TemporaryDirectory(prefix="kernel-genesis-bind-create-") as tmp:
        root = Path(tmp)
        _write_fixture_ledger(root)
        _register_turn_failed_closers(root)
        _write_forage_history(root)
        save_campaign(root, _consumed_campaign())
        bound_goal, bound_done, bound_source = bind_create_fields(root)
    checks["create_bind_uses_successor"] = (
        bound_goal == KERNEL_GENESIS_BIND_GOAL
        and KERNEL_GENESIS_BIND_ID in bound_done
        and str(bound_source).startswith("genesis_bind")
    )

    create_goal, create_done, create_source = bind_create_fields(
        Path("."), "Operator growth goal.", "already-bound"
    )
    checks["create_bind_keeps_operator"] = (
        create_goal == "Operator growth goal."
        and create_done == "already-bound"
        and create_source == "operator"
    )

    with tempfile.TemporaryDirectory(prefix="kernel-genesis-bind-local-") as tmp:
        root = Path(tmp)
        _write_fixture_ledger(root)
        _register_turn_failed_closers(root)
        _write_forage_history(root)
        save_campaign(root, _consumed_campaign())
        binding = bind_local_mission(_State(root), harvest=True)
    checks["class_closed_bind_fills_successor"] = (
        binding.goal == KERNEL_GENESIS_BIND_GOAL
        and KERNEL_GENESIS_BIND_ID in binding.done_when
        and "genesis_bind" in binding.source
    )

    with tempfile.TemporaryDirectory(prefix="kernel-genesis-bind-operator-") as tmp:
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

    with tempfile.TemporaryDirectory(prefix="kernel-genesis-bind-remaining-") as tmp:
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

    with tempfile.TemporaryDirectory(prefix="kernel-genesis-bind-skip-") as tmp:
        root = Path(tmp)
        _write_fixture_ledger(root)
        _register_turn_failed_closers(root)
        _write_forage_history(root)
        _write_complete_mission(root, "prior-genesis-bind", KERNEL_GENESIS_BIND_GOAL, order=20)
        _register_proved(root, KERNEL_GENESIS_BIND_ID)
        save_campaign(root, _consumed_campaign())
        skip_goal, skip_done, skip_source = bind_gate_passing_successor(root)
    checks["proved_catalog_item_skips_to_next"] = (
        skip_goal == CONSUMED_GROWTH_GOAL
        and CONSUMED_GROWTH_ID in skip_done
        and skip_source == "genesis_bind_growth"
    )

    keep = _State(Path("."), goal="Operator growth goal.")
    hydrate_mission_from_campaign(keep, repo_path=Path("."))
    checks["hydrate_preserves_operator_goal"] = keep.goal == "Operator growth goal."

    from blackhole_agent.experience_fuel import ExperienceCandidate, harvest_experience
    from blackhole_agent.kernel_class_closure import class_is_closed
    from blackhole_agent.local_mission_sovereignty import (
        HARVESTED_KERNEL_FAILURE_DONE_WHEN,
        mission_from_candidate,
    )

    closed_goal, closed_done = mission_from_candidate(
        ExperienceCandidate(
            source="unbound",
            class_id=GENESIS_SELECTION_BLOCKED,
            summary="turn 3 reported blocked",
        ),
        ledger=None,
    )
    checks["open_selection_class_binds_closer_not_sovereignty"] = (
        GENESIS_SELECTION_BLOCKED in closed_goal
        and KERNEL_GENESIS_BIND_ID in closed_done
        and "local-mission-sovereignty" not in closed_done
    )

    with tempfile.TemporaryDirectory(prefix="kernel-genesis-bind-stale-") as tmp:
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
        stale_closed = class_is_closed(GENESIS_SELECTION_BLOCKED, root)
        stale_fuel = harvest_experience(root, limit=5)
        stale_goal, stale_done, stale_source = bind_gate_passing_successor(root)
        stale_create_goal, stale_create_done, stale_create_source = bind_create_fields(root)
    checks["stale_checkout_still_closes_class"] = stale_closed is True
    checks["stale_checkout_drops_selection_fuel"] = not any(
        item.class_id == GENESIS_SELECTION_BLOCKED for item in stale_fuel.candidates
    )
    checks["stale_checkout_binds_growth_not_sovereignty"] = (
        stale_goal == CONSUMED_GROWTH_GOAL
        and CONSUMED_GROWTH_ID in stale_done
        and stale_source == "genesis_bind_growth"
        and HARVESTED_KERNEL_FAILURE_DONE_WHEN not in stale_done
        and GENESIS_SELECTION_BLOCKED not in stale_goal
    )
    checks["stale_create_bind_uses_growth"] = (
        stale_create_goal == CONSUMED_GROWTH_GOAL
        and CONSUMED_GROWTH_ID in stale_create_done
        and str(stale_create_source).startswith("genesis_bind")
    )

    checks["no_skill_route"] = not legacy_pipeline_was_used()
    checks["schema_version"] = SCHEMA_VERSION == 1

    ok = all(checks.values())
    return {
        "ok": ok,
        "action": "kernel_genesis_bind",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": KERNEL_GENESIS_BIND_GOAL,
        "done_when": KERNEL_GENESIS_BIND_DONE_WHEN,
    }
