"""Next unsaturated family after login-task staleness repair.

After a stale login registration whose command or launcher pointed at a
moved repo is re-pointed this slot is login-task retirement: a
registration whose repo was deleted keeps the logon task firing a dead
launcher until an operator unschedules it by hand. The hole stays open so
later genesis can retire the dead registration without disturbing a live
owner pid in any surviving repo.
"""

from __future__ import annotations

LOOP_LOGIN_RETIRE_ID = "capability.loop-login-retire"
LOOP_LOGIN_RETIRE_DONE_WHEN = (
    "A login startup registration whose repo was deleted is unscheduled so "
    "logon stops firing a dead launcher without disturbing a live owner pid "
    "in any surviving repo."
)
LOOP_LOGIN_RETIRE_GOAL = (
    "Repair login-task retirement: a registration whose repo was deleted "
    "keeps the logon task firing a dead launcher until an operator "
    "unschedules it by hand."
)
LOOP_LOGIN_RETIRE_LEFTOVER = (
    "Later genesis can take login-task retirement so a deleted repo's "
    "registration is unscheduled without an operator doing it by hand."
)
