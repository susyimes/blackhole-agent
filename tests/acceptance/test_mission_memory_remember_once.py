"""One completed failure turn is remembered once.

Genesis harvest reads the same completed turns on every mission. Mission
memory used to add 1 to the class count on every read, including a later
read that finally knows the mission id. A row written before turn identities
existed grew the same way.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both met
and unmet outcomes.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from blackhole_agent.kernel_mission_memory import (
    load_mission_memory,
    remember_turn_record,
    save_mission_memory,
)


def _turn(iteration: int, finished_at: str) -> dict[str, object]:
    return {
        "iteration": iteration,
        "effective_status": "error",
        "error": (
            "Grok CLI failed with exit code 1; result details were written to "
            f"grok-run-remember-once-{iteration}.json"
        ),
        "summary": f"turn {iteration} failed before a structured decision",
        "finished_at": finished_at,
    }


def _count(root: Path) -> int:
    classes = load_mission_memory(root).get("classes") or {}
    row = classes.get("kernel_turn_failed") or {}
    return int(row.get("count") or 0)


def main() -> None:
    turn = _turn(2, "2026-08-16T05:51:28Z")
    later = _turn(3, "2026-08-16T06:10:00Z")
    with tempfile.TemporaryDirectory(prefix="remember-once-") as tmp:
        root = Path(tmp)
        remember_turn_record(root, turn, source_mission_id="")
        remember_turn_record(root, turn, source_mission_id="mission-a")
        reread = _count(root)
        remember_turn_record(root, later, source_mission_id="mission-a")
        after_new = _count(root)
        remember_turn_record(root, later, source_mission_id="mission-a")
        after_new_reread = _count(root)

    with tempfile.TemporaryDirectory(prefix="remember-once-legacy-") as tmp:
        legacy_root = Path(tmp)
        save_mission_memory(
            legacy_root,
            {
                "classes": {
                    "kernel_turn_failed": {
                        "class_id": "kernel_turn_failed",
                        "count": 9,
                        "evidence": "already counted",
                        "first_seen": "2026-08-16T05:51:28Z",
                        "last_seen": "2026-08-16T05:51:28Z",
                        "source": "unbound",
                        "summary": "turn 2 failed before a structured decision",
                    }
                }
            },
        )
        remember_turn_record(legacy_root, turn, source_mission_id="mission-a")
        legacy_reread = _count(legacy_root)
        remember_turn_record(legacy_root, later, source_mission_id="mission-b")
        legacy_after_new = _count(legacy_root)

    observed = {
        "reread_count": reread,
        "after_new_turn": after_new,
        "after_new_turn_reread": after_new_reread,
        "legacy_reread_count": legacy_reread,
        "legacy_after_new_turn": legacy_after_new,
    }
    passed = (
        reread == 1
        and after_new == 2
        and after_new_reread == 2
        and legacy_reread == 9
        and legacy_after_new == 10
    )
    print(json.dumps({"passed": bool(passed), "observed": observed}))


if __name__ == "__main__":
    main()
