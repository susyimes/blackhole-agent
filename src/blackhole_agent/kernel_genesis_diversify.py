"""Bind a gate-passing successor when the compounding catalog is exhausted.

``bind_gate_passing_successor`` walks the compounding ``SUCCESSOR_CATALOG``.
After program weave is proved, the compounding catalog is exhausted. On live
history that weave is a repetition-gate near-duplicate of fabric/lattice/tower,
so bind returns empty unless forage-shaped history still accepts it. Recovered
kernels and first-class genesis then invent until ``genesis_selection_blocked``.

This module closes that hole:

- detect when the compounding catalog has no remaining gate-passing successor
- rank a diversity catalog of unsaturated capability families
- bind the first open, gate-passing diversity mission
- skip a proved diversity item to the next gate-passing family
- preserve operator fields and unscoped remaining campaign work
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Sequence

from blackhole_agent.capability_compounder import (
    Capability,
    default_ledger_path,
    legacy_pipeline_was_used,
    load_ledger,
    register_capability,
    save_ledger,
    utc_now_iso,
)
from blackhole_agent.kernel_genesis_bind import (
    COMPOUND_LOOP_ID,
    COMPOSED_PROGRAM_ID,
    CONSUMED_GROWTH_ID,
    KERNEL_GENESIS_BIND_GOAL,
    KERNEL_GENESIS_BIND_ID,
    PRIMITIVE_COMPOSE_ID,
    PROGRAM_FABRIC_GOAL,
    PROGRAM_FABRIC_ID,
    PROGRAM_LATTICE_GOAL,
    PROGRAM_LATTICE_ID,
    PROGRAM_STACK_ID,
    PROGRAM_TOWER_GOAL,
    PROGRAM_TOWER_ID,
    PROGRAM_WEAVE_GOAL,
    PROGRAM_WEAVE_ID,
    _State,
    _catalog_item_open,
    _consumed_campaign,
    _register_proved,
    _unscoped_remaining_campaign,
    _write_complete_mission,
    _write_forage_history,
    bind_gate_passing_successor,
    genesis_bind_is_needed,
)
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.kernel_half_open_persist import (
    HALF_OPEN_PERSIST_DONE_WHEN,
    HALF_OPEN_PERSIST_GOAL,
    HALF_OPEN_PERSIST_ID,
)
from blackhole_agent.kernel_mission_memory import (
    MISSION_MEMORY_DONE_WHEN,
    MISSION_MEMORY_GOAL,
    MISSION_MEMORY_ID,
)
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST, _write_fixture_ledger
from blackhole_agent.local_mission_sovereignty import (
    LocalCampaign,
    bind_local_mission,
    load_campaign,
    save_campaign,
)
from blackhole_agent.mission_selection import (
    assess_mission_selection,
    load_recent_mission_history,
    semantic_signature,
    semantic_similarity,
)

SCHEMA_VERSION = 1
REPO_ROOT = Path(__file__).resolve().parents[2]
GENESIS_DIVERSIFY_ID = "capability.kernel-genesis-diversify"
MCP_HANDSHAKE_ID = "capability.mcp-handshake-isolation"

GENESIS_DIVERSIFY_DONE_WHEN = (
    f"capability_exists:{GENESIS_DIVERSIFY_ID};"
    f"capability_proved:{GENESIS_DIVERSIFY_ID};"
    "no_skill_route"
)
GENESIS_DIVERSIFY_GOAL = (
    "When experience fuel is empty and every remaining catalog successor fails "
    "controller selection gates, repair the empty successor: mint a diversity-ranked "
    "mission on a different capability family in-process so a live consumed campaign "
    "cannot leave genesis unbound."
)
MCP_HANDSHAKE_DONE_WHEN = (
    f"capability_exists:{MCP_HANDSHAKE_ID};"
    f"capability_proved:{MCP_HANDSHAKE_ID};"
    "no_skill_route"
)
MCP_HANDSHAKE_GOAL = (
    "Repair MCP client handshake isolation: a plugin whose initialize response "
    "never arrives still fails the whole MCP plane; isolate the dead handshake so "
    "live servers keep serving."
)

COMPOUNDING_THROUGH_FABRIC = (
    KERNEL_GENESIS_BIND_ID,
    CONSUMED_GROWTH_ID,
    COMPOUND_LOOP_ID,
    PRIMITIVE_COMPOSE_ID,
    COMPOSED_PROGRAM_ID,
    PROGRAM_STACK_ID,
    PROGRAM_TOWER_ID,
    PROGRAM_LATTICE_ID,
    PROGRAM_FABRIC_ID,
)

DIVERSITY_CATALOG: tuple[dict[str, str], ...] = (
    {
        "id": GENESIS_DIVERSIFY_ID,
        "goal": GENESIS_DIVERSIFY_GOAL,
        "done_when": GENESIS_DIVERSIFY_DONE_WHEN,
        "source": "genesis_bind_diversity",
    },
    {
        "id": MISSION_MEMORY_ID,
        "goal": MISSION_MEMORY_GOAL,
        "done_when": MISSION_MEMORY_DONE_WHEN,
        "source": "genesis_bind_memory",
    },
    {
        "id": HALF_OPEN_PERSIST_ID,
        "goal": HALF_OPEN_PERSIST_GOAL,
        "done_when": HALF_OPEN_PERSIST_DONE_WHEN,
        "source": "genesis_bind_half_open",
    },
    {
        "id": MCP_HANDSHAKE_ID,
        "goal": MCP_HANDSHAKE_GOAL,
        "done_when": MCP_HANDSHAKE_DONE_WHEN,
        "source": "genesis_bind_handshake",
    },
)

_LIVE_SHAPED_GOALS = (
    PROGRAM_TOWER_GOAL,
    PROGRAM_LATTICE_GOAL,
    PROGRAM_FABRIC_GOAL,
    (
        "Repair mixed-stack restoration after a red MCP hop fails the mixed grade: "
        "heal the hop in-process, re-solve the composition, and restore mixed stack "
        "health; an unrepairable hop must leave the stack unhealthy while default "
        "recovery stays blind."
    ),
    (
        "Close operational class `mission_leftover`: Optional later work is mixed "
        "absorbed stack repair so a healable producer restores mixed absorbed stack "
        "health."
    ),
    (
        "Close operational class `mission_leftover`: Optional later work is watching "
        "mixed MCP+absorbed goals in the recovery plane so a red MCP hop is healed."
    ),
    (
        "Repair leftover harvest isolation of the origin ledger: a shipped leftover "
        "still enters genesis fuel because leftover satisfaction only reads the "
        "lagging checkout ledger."
    ),
    (
        "Repair mission-worktree reclamation of stale directories: a path that exists "
        "on disk but is no longer a git working tree still fails git worktree remove, "
        "poisons the GC report, and leaves last_worktree_gc_error sticky so later "
        "valid worktrees never finish clean."
    ),
)


def genesis_diversify_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.kernel_genesis_diversify import "
        "builtin_kernel_genesis_diversify_proof; r=builtin_kernel_genesis_diversify_proof(); "
        "assert r['ok'] and r.get('action')=='kernel_genesis_diversify' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_genesis_diversify_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=GENESIS_DIVERSIFY_ID,
        name="Genesis catalog diversity bind",
        description=(
            "When experience fuel is empty and the compounding catalog's remaining "
            "successor fails controller selection gates, genesis bind ranks a "
            "diversity catalog of unsaturated capability families and fills the "
            "first open gate-passing mission instead of returning empty."
        ),
        kind="python",
        entry="blackhole_agent.kernel_genesis_diversify:builtin_kernel_genesis_diversify_proof",
        proof_command=genesis_diversify_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.kernel-genesis-bind",
        ),
        behavior_paths=(
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/kernel_genesis_bind.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/kernel_leftover.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "Empty genesis bind after a rejected compounding successor no longer "
            "stalls: a diversity-ranked mission on a different capability family "
            "is bound in-process so recovered kernels cannot leave genesis unbound."
        ),
        tags=("genesis", "selection", "diversity", "catalog", "kernel"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def bind_diversity_successor(
    root: Path,
    *,
    campaign: LocalCampaign | None = None,
    lineage_ref: str = "",
    history: Sequence[Any] | None = None,
) -> tuple[str, str, str]:
    """Return the first open diversity successor that passes selection gates."""

    live_campaign = campaign if campaign is not None else load_campaign(Path(root))
    if not genesis_bind_is_needed(live_campaign):
        return "", "", ""
    live_history = list(
        history
        if history is not None
        else load_recent_mission_history(Path(root))
    )
    for item in DIVERSITY_CATALOG:
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
            history=live_history,
        )
        if gate.accepted:
            return goal, done_when, str(item.get("source") or "genesis_bind_diversity")
    return "", "", ""


def _register_compounding_through_fabric(root: Path) -> None:
    for capability_id in COMPOUNDING_THROUGH_FABRIC:
        _register_proved(root, capability_id)


def _write_live_shaped_history(root: Path) -> None:
    for index, goal in enumerate(_LIVE_SHAPED_GOALS, start=1):
        _write_complete_mission(root, f"live-shaped-{index}", goal, order=index)


def _prepare_exhausted_catalog(root: Path) -> None:
    from blackhole_agent.kernel_unscoped_resume import _register_turn_failed_closers

    _write_fixture_ledger(root)
    _register_turn_failed_closers(root)
    _write_live_shaped_history(root)
    _register_compounding_through_fabric(root)
    save_campaign(root, _consumed_campaign())


def builtin_kernel_genesis_diversify_proof() -> dict[str, Any]:
    """Hermetic proof: a rejected compounding successor cannot leave genesis empty."""

    from blackhole_agent.kernel_resume import bind_create_fields, hydrate_mission_from_campaign
    from blackhole_agent.kernel_unscoped_resume import _register_turn_failed_closers

    checks: dict[str, bool] = {}
    checks["denylists_self"] = GENESIS_DIVERSIFY_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(GENESIS_DIVERSIFY_GOAL) == (
        GENESIS_DIVERSIFY_ID,
    )
    checks["memory_marker"] = leftover_marker_ids(MISSION_MEMORY_GOAL) == (MISSION_MEMORY_ID,)
    checks["not_a_weave_duplicate"] = (
        semantic_similarity(
            semantic_signature(GENESIS_DIVERSIFY_GOAL),
            semantic_signature(PROGRAM_WEAVE_GOAL),
        )
        < 0.82
    )
    checks["not_a_bind_duplicate"] = (
        semantic_similarity(
            semantic_signature(GENESIS_DIVERSIFY_GOAL),
            semantic_signature(KERNEL_GENESIS_BIND_GOAL),
        )
        < 0.82
    )
    checks["not_a_fabric_duplicate"] = (
        semantic_similarity(
            semantic_signature(GENESIS_DIVERSIFY_GOAL),
            semantic_signature(PROGRAM_FABRIC_GOAL),
        )
        < 0.82
    )
    checks["needed_on_consumed"] = genesis_bind_is_needed(_consumed_campaign()) is True
    checks["not_needed_on_unscoped_remaining"] = (
        genesis_bind_is_needed(_unscoped_remaining_campaign()) is False
    )

    with tempfile.TemporaryDirectory(prefix="kernel-genesis-diversify-forage-") as tmp:
        root = Path(tmp)
        _write_fixture_ledger(root)
        _register_turn_failed_closers(root)
        _write_forage_history(root)
        _register_compounding_through_fabric(root)
        save_campaign(root, _consumed_campaign())
        forage_goal, forage_done, forage_source = bind_gate_passing_successor(root)
    checks["forage_history_still_binds_weave"] = (
        forage_goal == PROGRAM_WEAVE_GOAL
        and PROGRAM_WEAVE_ID in forage_done
        and forage_source == "genesis_bind_weave"
    )

    with tempfile.TemporaryDirectory(prefix="kernel-genesis-diversify-live-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        weave_gate = assess_mission_selection(
            root,
            PROGRAM_WEAVE_GOAL,
            f"capability_exists:{PROGRAM_WEAVE_ID};capability_proved:{PROGRAM_WEAVE_ID};no_skill_route",
        )
        diversify_gate = assess_mission_selection(
            root, GENESIS_DIVERSIFY_GOAL, GENESIS_DIVERSIFY_DONE_WHEN
        )
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
        diversity_goal, diversity_done, diversity_source = bind_diversity_successor(root)
    checks["live_history_rejects_weave"] = weave_gate.accepted is False
    checks["live_history_accepts_diversity"] = diversify_gate.accepted is True
    checks["exhausted_catalog_binds_diversity"] = (
        live_goal == GENESIS_DIVERSIFY_GOAL
        and GENESIS_DIVERSIFY_ID in live_done
        and live_source == "genesis_bind_diversity"
        and live_goal != PROGRAM_WEAVE_GOAL
        and bool(live_source)
    )
    checks["diversity_helper_matches_bind"] = (
        diversity_goal == live_goal
        and diversity_done == live_done
        and diversity_source == live_source
    )

    with tempfile.TemporaryDirectory(prefix="kernel-genesis-diversify-hydrate-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        empty = _State(root)
        report = hydrate_mission_from_campaign(empty, persist=True)
        create_goal, create_done, create_source = bind_create_fields(root)
        local = bind_local_mission(_State(root), harvest=True)
    checks["hydrate_fills_diversity"] = (
        report.get("applied") is True
        and empty.goal == GENESIS_DIVERSIFY_GOAL
        and GENESIS_DIVERSIFY_ID in empty.done_when
        and empty.stage == "execution"
        and str(report.get("source") or "") == "genesis_bind_diversity"
    )
    checks["create_bind_uses_diversity"] = (
        create_goal == GENESIS_DIVERSIFY_GOAL
        and GENESIS_DIVERSIFY_ID in create_done
        and str(create_source) == "genesis_bind_diversity"
    )
    checks["local_bind_fills_diversity"] = (
        local.goal == GENESIS_DIVERSIFY_GOAL
        and GENESIS_DIVERSIFY_ID in local.done_when
        and "genesis_bind_diversity" in local.source
    )

    with tempfile.TemporaryDirectory(prefix="kernel-genesis-diversify-operator-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        kept = bind_local_mission(
            _State(root, goal="Operator growth goal.", done_when="capability_exists:repo.import-health"),
            harvest=True,
        )
    checks["preserves_operator_bind"] = (
        kept.goal == "Operator growth goal." and "state.goal" in kept.source
    )

    with tempfile.TemporaryDirectory(prefix="kernel-genesis-diversify-remaining-") as tmp:
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

    with tempfile.TemporaryDirectory(prefix="kernel-genesis-diversify-skip-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        _register_proved(root, GENESIS_DIVERSIFY_ID)
        skip_goal, skip_done, skip_source = bind_gate_passing_successor(root)
    checks["proved_diversity_skips_to_memory"] = (
        skip_goal == MISSION_MEMORY_GOAL
        and MISSION_MEMORY_ID in skip_done
        and skip_source == "genesis_bind_memory"
    )

    keep = _State(Path("."), goal="Operator growth goal.")
    hydrate_mission_from_campaign(keep, persist=False)
    checks["hydrate_preserves_operator_goal"] = keep.goal == "Operator growth goal."
    checks["no_skill_route"] = not legacy_pipeline_was_used()
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["catalog_names_memory"] = DIVERSITY_CATALOG[1]["id"] == MISSION_MEMORY_ID
    checks["catalog_names_half_open"] = DIVERSITY_CATALOG[2]["id"] == HALF_OPEN_PERSIST_ID

    ok = all(checks.values())
    if ok:
        ensure_genesis_diversify_capability()
    return {
        "ok": ok,
        "action": "kernel_genesis_diversify",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": GENESIS_DIVERSIFY_GOAL,
        "done_when": GENESIS_DIVERSIFY_DONE_WHEN,
    }
