"""Recorded milestone handoff notes do not schedule work; later failures still do.

Exercise persisted state, recent turns and archived turns through the real
experience harvester and genesis renderer. Exit zero for either verdict.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from blackhole_agent.experience_fuel import harvest_unbound_failures, render_experience_for_genesis


HANDOFF = (
    "Controller records the milestone; later genesis can take "
    "capability.loop-login-stale (stale command/launcher pointing at a "
    "moved repo)."
)
REPOINT = (
    "Later genesis can take login-task stale repair: the registration "
    "points at a moved repo and must be re-pointed."
)


def leftovers(root: Path) -> list[str]:
    return [item.summary for item in harvest_unbound_failures(root) if item.class_id == "mission_leftover"]


def observe(location: str) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="accept-handoff-") as directory:
        root = Path(directory)
        mission = root / ".blackhole-agent" / "unbound" / "missions" / "completed"
        mission.mkdir(parents=True)
        state_path = mission / "state.json"
        turn = {"iteration": 1, "status": "complete", "next_step": HANDOFF}
        state: dict[str, object] = {
            "mission_id": "completed",
            "status": "complete",
            "milestone_count": 1,
            "goal": "Repair login-task drift.",
            "created_at": "2026-09-11T10:00:00Z",
        }
        record_path = state_path
        if location == "state":
            state["next_step"] = HANDOFF
        elif location == "recent_turn":
            state["recent_turns"] = [turn]
        else:
            record_path = mission / "turns" / "0001" / "turn.json"
            record_path.parent.mkdir(parents=True)
            record_path.write_text(json.dumps(turn), encoding="utf-8")
        state_path.write_text(json.dumps(state), encoding="utf-8")
        before = record_path.read_bytes()

        handoff_candidates = leftovers(root)
        handoff_brief = render_experience_for_genesis(root)
        history_preserved = record_path.read_bytes() == before

        # New evidence must be eligible, even with the older handoff note still
        # present in the mission history. No scheduler or controller is started.
        repair_dir = root / ".blackhole-agent" / "unbound" / "missions" / "new-evidence"
        repair_dir.mkdir()
        (repair_dir / "state.json").write_text(
            json.dumps({
                "mission_id": "new-evidence",
                "status": "active",
                "created_at": "2026-09-11T11:00:00Z",
                "next_step": REPOINT,
            }),
            encoding="utf-8",
        )
        repoint_candidates = leftovers(root)
        repoint_brief = render_experience_for_genesis(root)
        return {
            "location": location,
            "handoff_candidates": handoff_candidates,
            "handoff_in_genesis": HANDOFF in handoff_brief,
            "history_preserved": history_preserved,
            "repoint_candidates": repoint_candidates,
            "repoint_in_genesis": REPOINT in repoint_brief,
        }


def main() -> None:
    observed = [observe(location) for location in ("state", "recent_turn", "archived_turn")]
    passed = all(
        not row["handoff_candidates"]
        and not row["handoff_in_genesis"]
        and row["history_preserved"]
        and row["repoint_candidates"] == [REPOINT]
        and row["repoint_in_genesis"]
        for row in observed
    )
    print(json.dumps({"passed": passed, "observed": observed}, sort_keys=True))


if __name__ == "__main__":
    main()
