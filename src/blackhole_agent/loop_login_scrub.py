"""Next unsaturated family after login-task sweep.

After a record-gone login task is swept from the scheduler this slot is
login-task scrub: a swept scheduler entry leaves its dead launcher and task
XML artifacts on disk until an operator deletes the artifacts by hand. The
hole stays open so later genesis can scrub the leftover artifacts without
disturbing a live owner pid in any surviving repo.
"""

from __future__ import annotations

LOOP_LOGIN_SCRUB_ID = "capability.loop-login-scrub"
LOOP_LOGIN_SCRUB_DONE_WHEN = (
    "A swept login task's leftover launcher and task XML artifacts are "
    "scrubbed from disk so a record-gone task leaves no on-disk residue "
    "without disturbing a live owner pid in any surviving repo."
)
LOOP_LOGIN_SCRUB_GOAL = (
    "Repair login-task scrub: a swept scheduler entry leaves its dead "
    "launcher and task XML artifacts on disk until an operator deletes the "
    "artifacts by hand."
)
LOOP_LOGIN_SCRUB_LEFTOVER = (
    "Later genesis can take login-task scrub so a swept task's leftover "
    "launcher and task XML artifacts are scrubbed without an operator "
    "deleting the artifacts by hand."
)
