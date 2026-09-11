"""Drop consumed leftover briefs so genesis can rebound a nonhandshake successor.

A leftover-bound local campaign can be consumed and leftover_is_open can be
false while ``render_local_campaign_for_prompt`` still injects the closed
leftover into the next genesis brief. Remaining diversity-catalog rows are
handshake leftovers that fail selection, so ``bind_gate_passing_successor``
returns empty and the recovering kernel reopens shipped work.

This module closes that hole:

- leftover-bound campaigns whose leftover is already closed no longer render
- an open leftover campaign still appears in the recovering-kernel brief
- a non-leftover campaign still appears
- bind ranks leftover-handoff-rebind as a gate-passing nonhandshake successor
- later genesis is pointed at orphaned continuous-loop reaping
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
    utc_now_iso,
)
from blackhole_agent.kernel_leftover import (
    campaign_binds_leftover,
    leftover_is_open,
    leftover_marker_ids,
    leftover_satisfied_by,
    leftover_summary_from_goal,
)
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.orphan_loop_reap import (
    ORPHAN_LOOP_REAP_DONE_WHEN,
    ORPHAN_LOOP_REAP_GOAL,
    ORPHAN_LOOP_REAP_ID,
    ORPHAN_LOOP_REAP_LEFTOVER,
)

SCHEMA_VERSION = 1
LEFTOVER_HANDOFF_REBIND_ID = "capability.leftover-handoff-rebind"
LEFTOVER_HANDOFF_REBIND_GOAL = (
    "Repair stale leftover prompt injection: a consumed leftover still renders "
    "in the recovering-kernel brief after leftover satisfaction closed it, so "
    "empty genesis cannot rebound a nonhandshake mission."
)
LEFTOVER_HANDOFF_REBIND_DONE_WHEN = (
    "A consumed leftover whose leftover satisfaction is already closed no "
    "longer appears in the recovering-kernel brief; bind_gate_passing_successor "
    "returns a nonhandshake successor that assess_mission_selection accepts; an "
    "open leftover campaign still appears in the brief."
)
LEFTOVER_HANDOFF_REBIND_LEFTOVER = ORPHAN_LOOP_REAP_LEFTOVER
REPO_ROOT = Path(__file__).resolve().parents[2]
HARVESTED_CLOSED_LEFTOVER = (
    "Later genesis can take RFC 6625 Wildcards in Multicast VPN Auto-Discovery "
    "Routes WILD/AD over a wildid-gated wilddigest."
)
OPEN_UNRELATED_LEFTOVER = (
    "Optional follow-on is joining STEWARDSHIP_STACK as one cross-engine charter."
)


def leftover_handoff_is_stale(campaign: Any, root: Path) -> bool:
    """True when a leftover-bound campaign should no longer appear in genesis."""

    if int(getattr(campaign, "tick_count", 0) or 0) <= 0:
        return False
    if not campaign_binds_leftover(campaign):
        return False
    handoff = dict(getattr(campaign, "handoff", None) or {})
    consumed = (
        bool(str(getattr(campaign, "consumed_at", "") or "").strip())
        or getattr(campaign, "last_contract_met", None) is True
        or bool(handoff.get("leftover_consumed"))
    )
    if not consumed:
        return False
    summary = str(
        handoff.get("leftover_summary")
        or leftover_summary_from_goal(getattr(campaign, "goal", "") or "")
        or ""
    ).strip()
    if not summary:
        return False
    try:
        return leftover_is_open(summary, Path(root)) is False
    except Exception:  # noqa: BLE001 - stale detection must still honor local finality
        return bool(handoff.get("leftover_consumed"))


def leftover_handoff_rebind_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.leftover_handoff_rebind import "
        "builtin_leftover_handoff_rebind_proof; r=builtin_leftover_handoff_rebind_proof(); "
        "assert r['ok'] and r.get('action')=='leftover_handoff_rebind' "
        "and r.get('passed_count',0) >= 10 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_leftover_handoff_rebind_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=LEFTOVER_HANDOFF_REBIND_ID,
        name="Leftover handoff rebind",
        description=(
            "A consumed leftover whose leftover satisfaction is already closed "
            "leaves the recovering-kernel brief, an open leftover still appears, "
            "and empty genesis bind ranks a gate-passing nonhandshake successor "
            "instead of reopening shipped leftover work."
        ),
        kind="python",
        entry="blackhole_agent.leftover_handoff_rebind:builtin_leftover_handoff_rebind_proof",
        proof_command=leftover_handoff_rebind_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.kernel-leftover",
            "capability.kernel-genesis-bind",
        ),
        behavior_paths=(
            "src/blackhole_agent/leftover_handoff_rebind.py",
            "src/blackhole_agent/orphan_loop_reap.py",
            "src/blackhole_agent/local_mission_sovereignty.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/kernel_leftover.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "Consumed leftover campaigns no longer re-enter genesis: the "
            "recovering-kernel brief stays empty after leftover satisfaction, "
            "and bind fills leftover-handoff-rebind so handshake leftovers "
            "cannot stall empty genesis."
        ),
        tags=("leftover", "handoff", "genesis", "selection", "rebind"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def _leftover_campaign(
    goal: str,
    *,
    consumed: bool,
    leftover_summary: str = "",
) -> Any:
    from blackhole_agent.local_mission_sovereignty import LocalCampaign

    summary = leftover_summary or leftover_summary_from_goal(goal)
    return LocalCampaign(
        mission_id="leftover-handoff-rebind",
        goal=goal,
        done_when="program_passes:capability.ledger-inventory;no_skill_route",
        bound_from="state.goal+state.done_when",
        tick_count=1,
        last_contract_met=consumed,
        consumed_at="2026-09-10T02:17:17Z" if consumed else "",
        last_summary="local finality",
        handoff={
            "leftover_consumed": consumed,
            "leftover_summary": summary,
        },
    )


def builtin_leftover_handoff_rebind_proof() -> dict[str, Any]:
    """Hermetic proof: consumed leftover briefs drop; bind ranks a nonhandshake successor."""

    from blackhole_agent.evolution_quality import behavior_family
    from blackhole_agent.kernel_genesis_bind import bind_gate_passing_successor
    from blackhole_agent.kernel_genesis_diversify import DIVERSITY_CATALOG
    from blackhole_agent.kernel_leftover import consume_leftover
    from blackhole_agent.leftover_catalog_handoff import (
        HARVESTED_CATALOG_HANDOFF,
        LEFTOVER_CATALOG_HANDOFF_GOAL,
        LEFTOVER_CATALOG_HANDOFF_ID,
    )
    from blackhole_agent.local_mission_sovereignty import (
        HARVESTED_KERNEL_FAILURE_GOAL,
        LocalCampaign,
        render_local_campaign_for_prompt,
        save_campaign,
    )
    from blackhole_agent.mission_selection import assess_mission_selection

    checks: dict[str, bool] = {}
    checks["denylists_self"] = LEFTOVER_HANDOFF_REBIND_ID in LOCAL_DENYLIST
    checks["denylists_next_family"] = ORPHAN_LOOP_REAP_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(LEFTOVER_HANDOFF_REBIND_GOAL) == (
        LEFTOVER_HANDOFF_REBIND_ID,
    )
    checks["leftover_text_binds_next_family"] = leftover_marker_ids(
        LEFTOVER_HANDOFF_REBIND_LEFTOVER
    ) == (ORPHAN_LOOP_REAP_ID,)
    checks["next_family_goal_is_orphan_reap"] = leftover_marker_ids(ORPHAN_LOOP_REAP_GOAL) == (
        ORPHAN_LOOP_REAP_ID,
    )
    checks["catalog_handoff_markers_stay"] = leftover_marker_ids(LEFTOVER_CATALOG_HANDOFF_GOAL) == (
        LEFTOVER_CATALOG_HANDOFF_ID,
    ) and leftover_marker_ids(HARVESTED_CATALOG_HANDOFF) == (LEFTOVER_CATALOG_HANDOFF_ID,)
    catalog = DIVERSITY_CATALOG
    checks["catalog_names_rebind"] = (
        len(catalog) > 239
        and catalog[239]["id"] == LEFTOVER_HANDOFF_REBIND_ID
        and catalog[239]["goal"] == LEFTOVER_HANDOFF_REBIND_GOAL
        and catalog[239]["done_when"] == LEFTOVER_HANDOFF_REBIND_DONE_WHEN
        and catalog[239]["source"] == "genesis_bind_leftover_handoff"
    )
    checks["catalog_names_orphan_reap"] = (
        len(catalog) > 240
        and catalog[240]["id"] == ORPHAN_LOOP_REAP_ID
        and catalog[240]["goal"] == ORPHAN_LOOP_REAP_GOAL
        and catalog[240]["source"] == "genesis_bind_orphan_loop"
    )
    closed_goal = f"Close operational class `mission_leftover`: {HARVESTED_CLOSED_LEFTOVER}"
    open_goal = f"Close operational class `mission_leftover`: {OPEN_UNRELATED_LEFTOVER}"

    with tempfile.TemporaryDirectory(prefix="leftover-handoff-closed-") as tmp:
        root = Path(tmp)
        save_campaign(root, _leftover_campaign(closed_goal, consumed=True))
        consume_leftover(root, HARVESTED_CLOSED_LEFTOVER, satisfied_by="local_finality")
        closed_handoff = render_local_campaign_for_prompt(root)
        stale = leftover_handoff_is_stale(_leftover_campaign(closed_goal, consumed=True), root)
        reason = leftover_satisfied_by(HARVESTED_CLOSED_LEFTOVER, root)
        after = leftover_is_open(HARVESTED_CLOSED_LEFTOVER, root)
    checks["consumed_leftover_is_closed"] = after is False and bool(reason)
    checks["stale_leftover_is_detected"] = stale is True
    checks["consumed_leftover_leaves_brief"] = (
        "Local-kernel campaign handoff" not in closed_handoff
        and "wilddigest" not in closed_handoff
        and "RFC 6625" not in closed_handoff
    )

    with tempfile.TemporaryDirectory(prefix="leftover-handoff-open-") as tmp:
        root = Path(tmp)
        save_campaign(root, _leftover_campaign(open_goal, consumed=False, leftover_summary=OPEN_UNRELATED_LEFTOVER))
        open_handoff = render_local_campaign_for_prompt(root)
        open_stale = leftover_handoff_is_stale(
            _leftover_campaign(open_goal, consumed=False, leftover_summary=OPEN_UNRELATED_LEFTOVER),
            root,
        )
    checks["open_leftover_stays_in_brief"] = (
        open_stale is False
        and "Local-kernel campaign handoff" in open_handoff
        and "STEWARDSHIP_STACK" in open_handoff
    )

    with tempfile.TemporaryDirectory(prefix="leftover-handoff-other-") as tmp:
        root = Path(tmp)
        save_campaign(
            root,
            LocalCampaign(
                mission_id="other",
                goal=HARVESTED_KERNEL_FAILURE_GOAL,
                bound_from="harvested_kernel_failure",
                tick_count=1,
                last_summary="bound genesis after 402",
            ),
        )
        other_handoff = render_local_campaign_for_prompt(root)
    checks["non_leftover_brief_stays"] = other_handoff.startswith("Local-kernel campaign handoff")

    with tempfile.TemporaryDirectory(prefix="leftover-handoff-bind-") as tmp:
        root = Path(tmp)
        save_campaign(root, _leftover_campaign(closed_goal, consumed=True))
        consume_leftover(root, HARVESTED_CLOSED_LEFTOVER, satisfied_by="local_finality")
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
        gate = assess_mission_selection(root, live_goal, live_done)
    checks["empty_genesis_binds_rebind"] = (
        live_goal == LEFTOVER_HANDOFF_REBIND_GOAL
        and live_done == LEFTOVER_HANDOFF_REBIND_DONE_WHEN
        and live_source == "genesis_bind_leftover_handoff"
        and gate.accepted is True
        and behavior_family(live_goal) != "network/handshake-digest-demo"
    )
    checks["rebind_contract_is_outcome_level"] = (
        "capability_exists:" not in LEFTOVER_HANDOFF_REBIND_DONE_WHEN
        and "capability_proved:" not in LEFTOVER_HANDOFF_REBIND_DONE_WHEN
    )
    checks["next_family_is_not_handshake"] = (
        behavior_family(ORPHAN_LOOP_REAP_GOAL) != "network/handshake-digest-demo"
        and ORPHAN_LOOP_REAP_DONE_WHEN != ""
    )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_leftover_handoff_rebind_capability()
    return {
        "ok": ok,
        "action": "leftover_handoff_rebind",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": LEFTOVER_HANDOFF_REBIND_GOAL,
        "done_when": LEFTOVER_HANDOFF_REBIND_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
