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
from blackhole_agent.mcp_call_isolation import (
    MCP_CALL_DONE_WHEN,
    MCP_CALL_GOAL,
    MCP_CALL_ID,
)
from blackhole_agent.mcp_reverse_channel import (
    MCP_REVERSE_DONE_WHEN,
    MCP_REVERSE_GOAL,
    MCP_REVERSE_ID,
)
from blackhole_agent.mcp_http_transport import (
    MCP_HTTP_DONE_WHEN,
    MCP_HTTP_GOAL,
    MCP_HTTP_ID,
)
from blackhole_agent.mcp_http_event_stream import (
    MCP_HTTP_EVENT_DONE_WHEN,
    MCP_HTTP_EVENT_GOAL,
    MCP_HTTP_EVENT_ID,
)
from blackhole_agent.mcp_handshake_isolation import (
    MCP_HANDSHAKE_DONE_WHEN,
    MCP_HANDSHAKE_GOAL,
    MCP_HANDSHAKE_ID,
)
from blackhole_agent.publication_resilience import (
    PUBLICATION_RESILIENCE_DONE_WHEN,
    PUBLICATION_RESILIENCE_GOAL,
    PUBLICATION_RESILIENCE_ID,
)
from blackhole_agent.browser_actuation import (
    BROWSER_ACTUATION_DONE_WHEN,
    BROWSER_ACTUATION_GOAL,
    BROWSER_ACTUATION_ID,
)
from blackhole_agent.gmail_actuation import (
    GMAIL_ACTUATION_DONE_WHEN,
    GMAIL_ACTUATION_GOAL,
    GMAIL_ACTUATION_ID,
)
from blackhole_agent.godot_actuation import (
    GODOT_ACTUATION_DONE_WHEN,
    GODOT_ACTUATION_GOAL,
    GODOT_ACTUATION_ID,
)
from blackhole_agent.mcp_plugin_reconnect import (
    MCP_RECONNECT_DONE_WHEN,
    MCP_RECONNECT_GOAL,
    MCP_RECONNECT_ID,
)
from blackhole_agent.kernel_half_open_probe import (
    HALF_OPEN_PROBE_DONE_WHEN,
    HALF_OPEN_PROBE_GOAL,
    HALF_OPEN_PROBE_ID,
)
from blackhole_agent.mcp_sampling import (
    MCP_SAMPLING_DONE_WHEN,
    MCP_SAMPLING_GOAL,
    MCP_SAMPLING_ID,
)
from blackhole_agent.mcp_resources import (
    MCP_RESOURCES_DONE_WHEN,
    MCP_RESOURCES_GOAL,
    MCP_RESOURCES_ID,
)
from blackhole_agent.mcp_prompts import (
    MCP_PROMPTS_DONE_WHEN,
    MCP_PROMPTS_GOAL,
    MCP_PROMPTS_ID,
)
from blackhole_agent.mcp_completions import (
    MCP_COMPLETIONS_DONE_WHEN,
    MCP_COMPLETIONS_GOAL,
    MCP_COMPLETIONS_ID,
)
from blackhole_agent.mcp_logging import (
    MCP_LOGGING_DONE_WHEN,
    MCP_LOGGING_GOAL,
    MCP_LOGGING_ID,
)
from blackhole_agent.mcp_elicitation import (
    MCP_ELICITATION_DONE_WHEN,
    MCP_ELICITATION_GOAL,
    MCP_ELICITATION_ID,
)
from blackhole_agent.mcp_cancellation import (
    MCP_CANCELLATION_DONE_WHEN,
    MCP_CANCELLATION_GOAL,
    MCP_CANCELLATION_ID,
)
from blackhole_agent.mcp_resource_subscribe import (
    MCP_SUBSCRIBE_DONE_WHEN,
    MCP_SUBSCRIBE_GOAL,
    MCP_SUBSCRIBE_ID,
)
from blackhole_agent.mcp_roots_list_changed import (
    MCP_ROOTS_CHANGED_DONE_WHEN,
    MCP_ROOTS_CHANGED_GOAL,
    MCP_ROOTS_CHANGED_ID,
)
from blackhole_agent.browser_cdp_actuation import (
    BROWSER_CDP_DONE_WHEN,
    BROWSER_CDP_GOAL,
    BROWSER_CDP_ID,
)
from blackhole_agent.github_actuation import (
    GITHUB_ACTUATION_DONE_WHEN,
    GITHUB_ACTUATION_GOAL,
    GITHUB_ACTUATION_ID,
)
from blackhole_agent.sqlite_actuation import (
    SQLITE_ACTUATION_DONE_WHEN,
    SQLITE_ACTUATION_GOAL,
    SQLITE_ACTUATION_ID,
)
from blackhole_agent.webhook_actuation import (
    WEBHOOK_ACTUATION_DONE_WHEN,
    WEBHOOK_ACTUATION_GOAL,
    WEBHOOK_ACTUATION_ID,
)
from blackhole_agent.mcp_progress import (
    MCP_PROGRESS_DONE_WHEN,
    MCP_PROGRESS_GOAL,
    MCP_PROGRESS_ID,
)
from blackhole_agent.mcp_tools_list_changed import (
    MCP_TOOLS_CHANGED_DONE_WHEN,
    MCP_TOOLS_CHANGED_GOAL,
    MCP_TOOLS_CHANGED_ID,
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
    {
        "id": MCP_CALL_ID,
        "goal": MCP_CALL_GOAL,
        "done_when": MCP_CALL_DONE_WHEN,
        "source": "genesis_bind_call_isolation",
    },
    {
        "id": MCP_REVERSE_ID,
        "goal": MCP_REVERSE_GOAL,
        "done_when": MCP_REVERSE_DONE_WHEN,
        "source": "genesis_bind_reverse_channel",
    },
    {
        "id": MCP_HTTP_ID,
        "goal": MCP_HTTP_GOAL,
        "done_when": MCP_HTTP_DONE_WHEN,
        "source": "genesis_bind_http_transport",
    },
    {
        "id": MCP_HTTP_EVENT_ID,
        "goal": MCP_HTTP_EVENT_GOAL,
        "done_when": MCP_HTTP_EVENT_DONE_WHEN,
        "source": "genesis_bind_http_event_stream",
    },
    {
        "id": PUBLICATION_RESILIENCE_ID,
        "goal": PUBLICATION_RESILIENCE_GOAL,
        "done_when": PUBLICATION_RESILIENCE_DONE_WHEN,
        "source": "genesis_bind_publication",
    },
    {
        "id": BROWSER_ACTUATION_ID,
        "goal": BROWSER_ACTUATION_GOAL,
        "done_when": BROWSER_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_browser",
    },
    {
        "id": GMAIL_ACTUATION_ID,
        "goal": GMAIL_ACTUATION_GOAL,
        "done_when": GMAIL_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_gmail",
    },
    {
        "id": GODOT_ACTUATION_ID,
        "goal": GODOT_ACTUATION_GOAL,
        "done_when": GODOT_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_godot",
    },
    {
        "id": MCP_RECONNECT_ID,
        "goal": MCP_RECONNECT_GOAL,
        "done_when": MCP_RECONNECT_DONE_WHEN,
        "source": "genesis_bind_reconnect",
    },
    {
        "id": HALF_OPEN_PROBE_ID,
        "goal": HALF_OPEN_PROBE_GOAL,
        "done_when": HALF_OPEN_PROBE_DONE_WHEN,
        "source": "genesis_bind_half_open_probe",
    },
    {
        "id": MCP_SAMPLING_ID,
        "goal": MCP_SAMPLING_GOAL,
        "done_when": MCP_SAMPLING_DONE_WHEN,
        "source": "genesis_bind_sampling",
    },
    {
        "id": MCP_RESOURCES_ID,
        "goal": MCP_RESOURCES_GOAL,
        "done_when": MCP_RESOURCES_DONE_WHEN,
        "source": "genesis_bind_resources",
    },
    {
        "id": MCP_PROMPTS_ID,
        "goal": MCP_PROMPTS_GOAL,
        "done_when": MCP_PROMPTS_DONE_WHEN,
        "source": "genesis_bind_prompts",
    },
    {
        "id": MCP_COMPLETIONS_ID,
        "goal": MCP_COMPLETIONS_GOAL,
        "done_when": MCP_COMPLETIONS_DONE_WHEN,
        "source": "genesis_bind_completions",
    },
    {
        "id": MCP_LOGGING_ID,
        "goal": MCP_LOGGING_GOAL,
        "done_when": MCP_LOGGING_DONE_WHEN,
        "source": "genesis_bind_logging",
    },
    {
        "id": MCP_ELICITATION_ID,
        "goal": MCP_ELICITATION_GOAL,
        "done_when": MCP_ELICITATION_DONE_WHEN,
        "source": "genesis_bind_elicitation",
    },
    {
        "id": MCP_CANCELLATION_ID,
        "goal": MCP_CANCELLATION_GOAL,
        "done_when": MCP_CANCELLATION_DONE_WHEN,
        "source": "genesis_bind_cancellation",
    },
    {
        "id": MCP_SUBSCRIBE_ID,
        "goal": MCP_SUBSCRIBE_GOAL,
        "done_when": MCP_SUBSCRIBE_DONE_WHEN,
        "source": "genesis_bind_resource_subscribe",
    },
    {
        "id": MCP_ROOTS_CHANGED_ID,
        "goal": MCP_ROOTS_CHANGED_GOAL,
        "done_when": MCP_ROOTS_CHANGED_DONE_WHEN,
        "source": "genesis_bind_roots_list_changed",
    },
    {
        "id": BROWSER_CDP_ID,
        "goal": BROWSER_CDP_GOAL,
        "done_when": BROWSER_CDP_DONE_WHEN,
        "source": "genesis_bind_browser_cdp",
    },
    {
        "id": GITHUB_ACTUATION_ID,
        "goal": GITHUB_ACTUATION_GOAL,
        "done_when": GITHUB_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_github",
    },
    {
        "id": SQLITE_ACTUATION_ID,
        "goal": SQLITE_ACTUATION_GOAL,
        "done_when": SQLITE_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_sqlite",
    },
    {
        "id": WEBHOOK_ACTUATION_ID,
        "goal": WEBHOOK_ACTUATION_GOAL,
        "done_when": WEBHOOK_ACTUATION_DONE_WHEN,
        "source": "genesis_bind_webhook",
    },
    {
        "id": MCP_PROGRESS_ID,
        "goal": MCP_PROGRESS_GOAL,
        "done_when": MCP_PROGRESS_DONE_WHEN,
        "source": "genesis_bind_progress",
    },
    {
        "id": MCP_TOOLS_CHANGED_ID,
        "goal": MCP_TOOLS_CHANGED_GOAL,
        "done_when": MCP_TOOLS_CHANGED_DONE_WHEN,
        "source": "genesis_bind_tools_list_changed",
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
    checks["catalog_names_handshake"] = DIVERSITY_CATALOG[3]["id"] == MCP_HANDSHAKE_ID
    checks["catalog_names_call"] = DIVERSITY_CATALOG[4]["id"] == MCP_CALL_ID
    checks["catalog_names_reverse"] = DIVERSITY_CATALOG[5]["id"] == MCP_REVERSE_ID
    checks["catalog_names_http"] = DIVERSITY_CATALOG[6]["id"] == MCP_HTTP_ID
    checks["catalog_names_event_stream"] = DIVERSITY_CATALOG[7]["id"] == MCP_HTTP_EVENT_ID
    checks["catalog_names_publication"] = DIVERSITY_CATALOG[8]["id"] == PUBLICATION_RESILIENCE_ID
    checks["catalog_names_browser"] = DIVERSITY_CATALOG[9]["id"] == BROWSER_ACTUATION_ID
    checks["catalog_names_gmail"] = DIVERSITY_CATALOG[10]["id"] == GMAIL_ACTUATION_ID
    checks["catalog_names_godot"] = DIVERSITY_CATALOG[11]["id"] == GODOT_ACTUATION_ID
    checks["catalog_names_reconnect"] = DIVERSITY_CATALOG[12]["id"] == MCP_RECONNECT_ID
    checks["catalog_names_half_open_probe"] = DIVERSITY_CATALOG[13]["id"] == HALF_OPEN_PROBE_ID
    checks["catalog_names_sampling"] = DIVERSITY_CATALOG[14]["id"] == MCP_SAMPLING_ID
    checks["catalog_names_resources"] = DIVERSITY_CATALOG[15]["id"] == MCP_RESOURCES_ID
    checks["catalog_names_prompts"] = DIVERSITY_CATALOG[16]["id"] == MCP_PROMPTS_ID
    checks["catalog_names_completions"] = DIVERSITY_CATALOG[17]["id"] == MCP_COMPLETIONS_ID
    checks["catalog_names_logging"] = DIVERSITY_CATALOG[18]["id"] == MCP_LOGGING_ID
    checks["catalog_names_elicitation"] = DIVERSITY_CATALOG[19]["id"] == MCP_ELICITATION_ID
    checks["catalog_names_cancellation"] = DIVERSITY_CATALOG[20]["id"] == MCP_CANCELLATION_ID
    checks["catalog_names_resource_subscribe"] = DIVERSITY_CATALOG[21]["id"] == MCP_SUBSCRIBE_ID
    checks["catalog_names_roots_list_changed"] = DIVERSITY_CATALOG[22]["id"] == MCP_ROOTS_CHANGED_ID
    checks["catalog_names_browser_cdp"] = DIVERSITY_CATALOG[23]["id"] == BROWSER_CDP_ID
    checks["catalog_names_github"] = DIVERSITY_CATALOG[24]["id"] == GITHUB_ACTUATION_ID
    checks["catalog_names_sqlite"] = DIVERSITY_CATALOG[25]["id"] == SQLITE_ACTUATION_ID
    checks["catalog_names_webhook"] = DIVERSITY_CATALOG[26]["id"] == WEBHOOK_ACTUATION_ID
    checks["catalog_names_progress"] = DIVERSITY_CATALOG[27]["id"] == MCP_PROGRESS_ID
    checks["catalog_names_tools_list_changed"] = (
        DIVERSITY_CATALOG[28]["id"] == MCP_TOOLS_CHANGED_ID
    )

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
