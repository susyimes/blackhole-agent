"""Contract-met deferral notes do not schedule work; explicit follow-ups still do.

A completed mission whose next_step reads "Mission contract met; later genesis
can decide whether ..." is deferred advice, not a mission_leftover. Exercise
persisted state, recent turns and archived turns through the real experience
harvester and genesis renderer. Exit zero for either verdict.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from blackhole_agent.experience_fuel import (
    harvest_unbound_failures,
    leftover_next_step,
    render_experience_for_genesis,
)


DEFERRED = (
    "Mission contract met; later genesis can decide whether old inventoried "
    "orphans become adoptable or reclaimable with operator acknowledgment."
)
ACTIONABLE = (
    "Mission contract met. Follow-on: repair the stale launcher "
    "registration now."
)
REPAIR = "Follow-on: repair the stale launcher registration now."


def leftovers(root: Path) -> list[str]:
    return [item.summary for item in harvest_unbound_failures(root) if item.class_id == "mission_leftover"]


def observe(location: str) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="accept-contract-met-") as directory:
        root = Path(directory)
        mission = root / ".blackhole-agent" / "unbound" / "missions" / "completed"
        mission.mkdir(parents=True)
        state_path = mission / "state.json"
        turn = {"iteration": 1, "status": "complete", "next_step": DEFERRED}
        state: dict[str, object] = {
            "mission_id": "completed",
            "status": "complete",
            "goal": "Reap orphaned continuous-loop controllers.",
            "created_at": "2026-09-12T01:00:00Z",
        }
        record_path = state_path
        if location == "state":
            state["next_step"] = DEFERRED
        elif location == "recent_turn":
            state["recent_turns"] = [turn]
        else:
            record_path = mission / "turns" / "0001" / "turn.json"
            record_path.parent.mkdir(parents=True)
            record_path.write_text(json.dumps(turn), encoding="utf-8")
        state_path.write_text(json.dumps(state), encoding="utf-8")
        before = record_path.read_bytes()

        deferred_candidates = leftovers(root)
        deferred_brief = render_experience_for_genesis(root)
        history_preserved = record_path.read_bytes() == before

        # An explicit follow-on after the same contract-settled closer must
        # still be eligible. No scheduler or controller is started.
        repair_dir = root / ".blackhole-agent" / "unbound" / "missions" / "new-evidence"
        repair_dir.mkdir()
        (repair_dir / "state.json").write_text(
            json.dumps({
                "mission_id": "new-evidence",
                "status": "active",
                "created_at": "2026-09-12T02:00:00Z",
                "next_step": ACTIONABLE,
            }),
            encoding="utf-8",
        )
        repair_candidates = leftovers(root)
        repair_brief = render_experience_for_genesis(root)
        return {
            "location": location,
            "deferred_candidates": deferred_candidates,
            "deferred_in_genesis": DEFERRED in deferred_brief,
            "history_preserved": history_preserved,
            "repair_candidates": repair_candidates,
            "repair_in_genesis": REPAIR in repair_brief,
        }


def main() -> None:
    observed = [observe(location) for location in ("state", "recent_turn", "archived_turn")]
    direct = {
        "deferred_next_step": leftover_next_step(DEFERRED),
        "actionable_next_step": leftover_next_step(ACTIONABLE),
    }
    passed = (
        all(
            not row["deferred_candidates"]
            and not row["deferred_in_genesis"]
            and row["history_preserved"]
            and row["repair_candidates"] == [REPAIR]
            and row["repair_in_genesis"]
            for row in observed
        )
        and direct["deferred_next_step"] == ""
        and direct["actionable_next_step"] == REPAIR
    )
    print(json.dumps({"passed": passed, "observed": observed, "direct": direct}, sort_keys=True))


if __name__ == "__main__":
    main()
