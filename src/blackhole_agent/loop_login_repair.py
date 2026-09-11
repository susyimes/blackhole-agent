"""Next unsaturated family after login-task enablement.

After the restore helper is scheduled at login this slot is login-task
repair: a missing or disabled login registration stays gone until an
operator re-registers it by hand. The hole stays open so later genesis
can repair the registration without starting a second controller beside
a live owner pid.
"""

from __future__ import annotations

LOOP_LOGIN_REPAIR_ID = "capability.loop-login-repair"
LOOP_LOGIN_REPAIR_DONE_WHEN = (
    "A missing or disabled login startup registration is repaired so the "
    "restore helper is scheduled again without starting a second controller "
    "beside a live owner pid."
)
LOOP_LOGIN_REPAIR_GOAL = (
    "Repair login-task durability: a missing or disabled login registration "
    "stays gone until an operator re-registers it by hand."
)
LOOP_LOGIN_REPAIR_LEFTOVER = (
    "Later genesis can take login-task repair so a missing or disabled login "
    "registration is restored without an operator re-registering it by hand."
)
