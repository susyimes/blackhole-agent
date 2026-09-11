"""Next unsaturated family after login-task repair.

After a missing or disabled login registration is repaired this slot is
login-task drift: a registration with the wrong trigger or helper stays
wrong until an operator rewrites it by hand. The hole stays open so later
genesis can rewrite the drifted registration without starting a second
controller beside a live owner pid.
"""

from __future__ import annotations

LOOP_LOGIN_DRIFT_ID = "capability.loop-login-drift"
LOOP_LOGIN_DRIFT_DONE_WHEN = (
    "A drifted login startup registration with the wrong trigger or helper is "
    "repaired so the restore helper is scheduled again without starting a "
    "second controller beside a live owner pid."
)
LOOP_LOGIN_DRIFT_GOAL = (
    "Repair login-task drift: a registration with the wrong trigger or helper "
    "stays wrong until an operator rewrites it by hand."
)
LOOP_LOGIN_DRIFT_LEFTOVER = (
    "Later genesis can take login-task drift so a wrong trigger or helper "
    "is rewritten without an operator rewriting it by hand."
)
