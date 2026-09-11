"""Next unsaturated family after continuous-loop reboot restoration.

After loop-reboot-restore is proved this slot is login-task enablement: the
restore helper exists but is not scheduled at login, so an operator must
still invoke it by hand. The hole stays open so later genesis can register
the helper without starting a second controller beside a live owner pid.
"""

from __future__ import annotations

LOOP_LOGIN_TASK_ID = "capability.loop-login-task"
LOOP_LOGIN_TASK_DONE_WHEN = (
    "A login startup registration schedules the restore helper so an orphaned "
    "loop resumes after login without starting a second controller beside a "
    "live owner pid."
)
LOOP_LOGIN_TASK_GOAL = (
    "Repair login-task enablement: the restore helper exists but is not "
    "scheduled at login, so an operator must still invoke the helper by hand."
)
LOOP_LOGIN_TASK_LEFTOVER = (
    "Later genesis can take login-task enablement so the restore helper is "
    "scheduled at login without an operator invoking it by hand."
)
