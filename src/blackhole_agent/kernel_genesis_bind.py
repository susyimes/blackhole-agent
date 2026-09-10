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
- when remaining compounding catalog rows fail selection gates, bind falls
  through to a diversity catalog of unsaturated capability families
"""

from __future__ import annotations

# Historical proof modules import these helpers through this module.
from blackhole_agent.kernel_class_closure import class_closure_ids as class_closure_ids
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST as LOCAL_DENYLIST
from blackhole_agent.local_capability_kernel import _write_fixture_ledger as _write_fixture_ledger
from blackhole_agent.local_mission_sovereignty import bind_local_mission as bind_local_mission
from blackhole_agent.pattern_register import blocked_class_id as blocked_class_id

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
from blackhole_agent.kernel_class_closure import class_is_closed, load_effective_ledger
from blackhole_agent.local_mission_sovereignty import (
    LocalCampaign,
    load_campaign,
    save_campaign,
)
from blackhole_agent.mission_selection import assess_mission_selection, load_recent_mission_history

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
PROGRAM_FABRIC_ID = "capability.kernel-program-fabric"
PROGRAM_FABRIC_DONE_WHEN = (
    f"capability_exists:{PROGRAM_FABRIC_ID};"
    f"capability_proved:{PROGRAM_FABRIC_ID};"
    "no_skill_route"
)
PROGRAM_FABRIC_GOAL = (
    "When unique program-lattice coverage saturates, repair stalled weave "
    "compounding: mint a ready program fabric of lattices in-process so recovered "
    "kernels keep compounding weaves instead of probing cheap inventory."
)
PROGRAM_WEAVE_ID = "capability.kernel-program-weave"
PROGRAM_WEAVE_DONE_WHEN = (
    f"capability_exists:{PROGRAM_WEAVE_ID};"
    f"capability_proved:{PROGRAM_WEAVE_ID};"
    "no_skill_route"
)
PROGRAM_WEAVE_GOAL = (
    "After program fabrics fill unique coverage, repair stalled tapestry "
    "compounding: raise a ready program weave in-process so recovered kernels "
    "keep compounding tapestries instead of falling through to cheap inventory."
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
    {
        "id": PROGRAM_FABRIC_ID,
        "goal": PROGRAM_FABRIC_GOAL,
        "done_when": PROGRAM_FABRIC_DONE_WHEN,
        "source": "genesis_bind_fabric",
    },
    {
        "id": PROGRAM_WEAVE_ID,
        "goal": PROGRAM_WEAVE_GOAL,
        "done_when": PROGRAM_WEAVE_DONE_WHEN,
        "source": "genesis_bind_weave",
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
    try:
        from blackhole_agent.kernel_genesis_diversify import bind_diversity_successor

        return bind_diversity_successor(
            Path(root),
            campaign=live_campaign,
            lineage_ref=lineage_ref,
            history=history,
        )
    except Exception:  # noqa: BLE001 - bind must still fail closed
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
    """Prove candidate binding without treating ledger self-proofs as outcomes."""
    from unittest.mock import patch

    from blackhole_agent.kernel_resume import hydrate_mission_from_campaign

    checks: dict[str, bool] = {}
    goal = "Repair publication retries so interrupted pushes recover exactly once."
    done = "An interrupted push followed by retry leaves one remote commit and preserves ancestry."
    with tempfile.TemporaryDirectory(prefix="genesis-bind-quality-") as tmp:
        root = Path(tmp)
        save_campaign(root, _consumed_campaign())
        checks["rejects_ledger_only_candidate"] = not candidate_passes_selection(
            root, KERNEL_GENESIS_BIND_GOAL, KERNEL_GENESIS_BIND_DONE_WHEN
        )
        checks["accepts_behavior_candidate"] = candidate_passes_selection(root, goal, done)
        checks["legacy_catalog_leaves_genesis_open"] = bind_gate_passing_successor(root) == ("", "", "")
        empty = _State(root)
        hydrate_mission_from_campaign(empty)
        checks["no_unproved_auto_binding"] = not empty.goal and empty.stage == "genesis"
        operator = _State(root, goal="Operator task", done_when="Operator acceptance", stage="execution")
        hydrate_mission_from_campaign(operator)
        checks["preserves_operator_fields"] = operator.goal == "Operator task" and operator.done_when == "Operator acceptance"
        fixture = ({"id": "capability.fixture-outcome", "goal": goal, "done_when": done, "source": "fixture-outcome"},)
        with patch(__name__ + ".SUCCESSOR_CATALOG", fixture):
            chosen = bind_gate_passing_successor(root)
        checks["binds_qualified_candidate"] = chosen == (goal, done, "fixture-outcome")
        checks["remaining_campaign_not_overwritten"] = not genesis_bind_is_needed(_unscoped_remaining_campaign())
    checks["no_skill_route"] = not legacy_pipeline_was_used()
    return {
        "ok": all(checks.values()), "action": "kernel_genesis_bind", "checks": checks,
        "passed_count": sum(checks.values()), "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": KERNEL_GENESIS_BIND_GOAL, "done_when": KERNEL_GENESIS_BIND_DONE_WHEN,
    }
