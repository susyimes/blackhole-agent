"""Next unsaturated family after login-task retirement.

After a deleted repo's login registration is unscheduled this slot is
login-task sweep: a scheduled logon task whose registration record is gone
keeps firing until an operator deletes the task by hand. The hole stays open
so later genesis can sweep the orphaned task without disturbing a live owner
pid in any surviving repo.
"""

from __future__ import annotations

LOOP_LOGIN_SWEEP_ID = "capability.loop-login-sweep"
LOOP_LOGIN_SWEEP_DONE_WHEN = (
    "A scheduled login task whose registration record is gone is removed "
    "from the scheduler so logon stops firing it without disturbing a live "
    "owner pid in any surviving repo."
)
LOOP_LOGIN_SWEEP_GOAL = (
    "Repair login-task sweep: a scheduled logon task whose registration "
    "record is gone keeps firing until an operator deletes the task by hand."
)
LOOP_LOGIN_SWEEP_LEFTOVER = (
    "Later genesis can take login-task sweep so a scheduled task whose "
    "registration record is gone is removed without an operator deleting "
    "the task by hand."
)
