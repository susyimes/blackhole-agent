"""Next unsaturated family after leftover-handoff-rebind.

Consumed leftover briefs are dropped. After leftover-handoff-rebind is proved
this slot is orphaned continuous-loop reaping: a durable loop whose owner pid
is gone still reports status=running_mission. The hole stays open so later
genesis can reap the orphan without touching a live owner pid.
"""

from __future__ import annotations

ORPHAN_LOOP_REAP_ID = "capability.orphan-loop-reap"
ORPHAN_LOOP_REAP_DONE_WHEN = (
    "A durable continuous-loop state whose owner pid is gone reports "
    "effective_status=orphaned and a reap helper clears status=running_mission "
    "without touching a live owner pid."
)
ORPHAN_LOOP_REAP_GOAL = (
    "Repair orphaned continuous-loop reaping: a dead controller pid cannot keep "
    "status=running_mission after the process is gone, so later wakes treat an "
    "orphaned loop as still active."
)
ORPHAN_LOOP_REAP_LEFTOVER = (
    "Later genesis can take orphaned continuous-loop reaping so a dead "
    "controller pid cannot keep status=running_mission after the process is gone."
)
