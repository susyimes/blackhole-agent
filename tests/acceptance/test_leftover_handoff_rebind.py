"""Acceptance probe: consumed leftover leaves the recovering-kernel brief.

Prints JSON with boolean passed and nonempty observed. Exits 0 for both met
and unmet outcomes so the controller can replay the same probe on baseline
and candidate source trees.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

observed: dict[str, object] = {"family": "leftover-handoff-rebind"}
passed = False

try:
    from blackhole_agent.evolution_quality import behavior_family
    from blackhole_agent.kernel_genesis_bind import bind_gate_passing_successor
    from blackhole_agent.kernel_leftover import consume_leftover, leftover_is_open
    from blackhole_agent.leftover_handoff_rebind import (
        LEFTOVER_HANDOFF_REBIND_DONE_WHEN,
        LEFTOVER_HANDOFF_REBIND_GOAL,
        leftover_handoff_is_stale,
    )
    from blackhole_agent.local_mission_sovereignty import (
        LocalCampaign,
        render_local_campaign_for_prompt,
        save_campaign,
    )
    from blackhole_agent.mission_selection import assess_mission_selection
except Exception as error:  # pragma: no cover - baseline missing the closer
    observed["error"] = type(error).__name__
    observed["detail"] = str(error)
    print(json.dumps({"passed": False, "observed": observed}, sort_keys=True))
    raise SystemExit(0)

CLOSED_LEFTOVER = (
    "Later genesis can take RFC 6625 Wildcards in Multicast VPN Auto-Discovery "
    "Routes WILD/AD over a wildid-gated wilddigest."
)
OPEN_LEFTOVER = "Optional follow-on is joining STEWARDSHIP_STACK as one cross-engine charter."
CLOSED_GOAL = f"Close operational class `mission_leftover`: {CLOSED_LEFTOVER}"
OPEN_GOAL = f"Close operational class `mission_leftover`: {OPEN_LEFTOVER}"


def _leftover_campaign(goal: str, leftover: str, *, consumed: bool) -> LocalCampaign:
    return LocalCampaign(
        mission_id="acceptance-leftover-handoff",
        goal=goal,
        done_when="program_passes:capability.ledger-inventory;no_skill_route",
        bound_from="state.goal+state.done_when",
        tick_count=1,
        last_contract_met=consumed,
        consumed_at="2026-09-10T02:17:17Z" if consumed else "",
        last_summary="local finality",
        handoff={"leftover_consumed": consumed, "leftover_summary": leftover},
    )


try:
    with tempfile.TemporaryDirectory(prefix="accept-leftover-closed-") as tmp:
        closed_root = Path(tmp)
        save_campaign(closed_root, _leftover_campaign(CLOSED_GOAL, CLOSED_LEFTOVER, consumed=True))
        consume_leftover(closed_root, CLOSED_LEFTOVER, satisfied_by="local_finality")
        closed_handoff = render_local_campaign_for_prompt(closed_root)
        stale = leftover_handoff_is_stale(
            _leftover_campaign(CLOSED_GOAL, CLOSED_LEFTOVER, consumed=True),
            closed_root,
        )
        leftover_closed = leftover_is_open(CLOSED_LEFTOVER, closed_root) is False
        bind_goal, bind_done, bind_source = bind_gate_passing_successor(closed_root)
        bind_gate = assess_mission_selection(closed_root, bind_goal, bind_done)

    with tempfile.TemporaryDirectory(prefix="accept-leftover-open-") as tmp:
        open_root = Path(tmp)
        save_campaign(open_root, _leftover_campaign(OPEN_GOAL, OPEN_LEFTOVER, consumed=False))
        open_handoff = render_local_campaign_for_prompt(open_root)

    with tempfile.TemporaryDirectory(prefix="accept-leftover-other-") as tmp:
        other_root = Path(tmp)
        save_campaign(
            other_root,
            LocalCampaign(
                mission_id="acceptance-other",
                goal="Keep advancing after a kernel death.",
                bound_from="harvested_kernel_failure",
                tick_count=1,
                last_summary="bound genesis after 402",
            ),
        )
        other_handoff = render_local_campaign_for_prompt(other_root)

    suppresses_closed = (
        leftover_closed
        and stale is True
        and "Local-kernel campaign handoff" not in closed_handoff
        and "wilddigest" not in closed_handoff
        and "RFC 6625" not in closed_handoff
    )
    keeps_open = "Local-kernel campaign handoff" in open_handoff and "STEWARDSHIP_STACK" in open_handoff
    keeps_other = other_handoff.startswith("Local-kernel campaign handoff")
    bind_ok = (
        bind_goal == LEFTOVER_HANDOFF_REBIND_GOAL
        and bind_done == LEFTOVER_HANDOFF_REBIND_DONE_WHEN
        and bind_source == "genesis_bind_leftover_handoff"
        and bind_gate.accepted is True
        and behavior_family(bind_goal) != "network/handshake-digest-demo"
    )
    observed.update(
        {
            "ok": bool(suppresses_closed and keeps_open and keeps_other and bind_ok),
            "leftover_closed": leftover_closed,
            "stale": stale,
            "closed_handoff_empty": not closed_handoff,
            "open_leftover_in_brief": keeps_open,
            "other_brief_stays": keeps_other,
            "bind_source": bind_source,
            "bind_family": behavior_family(bind_goal) or "nonhandshake",
            "bind_accepted": bool(bind_gate.accepted),
            "sentinel": "BH-LEFTOVER-HANDOFF-OK" if bind_ok and suppresses_closed else "",
            "error": "",
        }
    )
    passed = bool(suppresses_closed and keeps_open and keeps_other and bind_ok)
except Exception as error:  # pragma: no cover - fixture or bind failure
    observed["error"] = type(error).__name__
    observed["detail"] = str(error)
    passed = False

print(json.dumps({"passed": passed, "observed": observed}, sort_keys=True))
