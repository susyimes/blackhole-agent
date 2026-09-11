"""Next unsaturated family after login-task drift repair.

After a drifted login registration with the wrong trigger or helper is
repaired this slot is login-task staleness: a registration whose command
or launcher points at a moved repo stays broken until an operator
re-points it by hand. The hole stays open so later genesis can re-point
the stale registration without starting a second controller beside a
live owner pid.
"""

from __future__ import annotations

LOOP_LOGIN_STALE_ID = "capability.loop-login-stale"
LOOP_LOGIN_STALE_DONE_WHEN = (
    "A stale login startup registration whose command or launcher points at "
    "a moved repo is repaired so the restore helper is scheduled again "
    "without starting a second controller beside a live owner pid."
)
LOOP_LOGIN_STALE_GOAL = (
    "Repair login-task staleness: a registration whose command or launcher "
    "points at a moved repo stays broken until an operator re-points it by "
    "hand."
)
LOOP_LOGIN_STALE_LEFTOVER = (
    "Later genesis can take login-task staleness so a stale command or "
    "launcher is re-pointed without an operator re-pointing it by hand."
)
