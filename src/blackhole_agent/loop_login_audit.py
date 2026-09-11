"""Next unsaturated family after login-task scrub.

After a swept login task's leftover launcher and task XML artifacts are
scrubbed from disk this slot is login-scrub audit: the scrub removes files
but records nothing durable about what it removed, so an operator
reconciling deletions by hand cannot tell a scrubbed task from one that was
never scheduled. The hole stays open so later genesis can record the audit
trail without disturbing a live owner pid in any surviving repo.
"""

from __future__ import annotations

LOOP_LOGIN_AUDIT_ID = "capability.loop-login-audit"
LOOP_LOGIN_AUDIT_DONE_WHEN = (
    "A swept login task's scrubbed launcher and task XML removal is recorded "
    "in a durable audit trail so an operator can see what was scrubbed "
    "without disturbing a live owner pid in any surviving repo."
)
LOOP_LOGIN_AUDIT_GOAL = (
    "Repair login-scrub audit: a swept login task's scrubbed on-disk "
    "artifacts leave no durable record, so an operator reconciling deletions "
    "by hand cannot tell a scrubbed task from one that was never scheduled."
)
LOOP_LOGIN_AUDIT_LEFTOVER = (
    "Later genesis can take login-scrub audit so a swept task's scrubbed "
    "artifacts are recorded durably without an operator reconciling "
    "deletions by hand."
)
