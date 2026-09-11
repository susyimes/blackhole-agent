"""Next unsaturated family after login-scrub audit.

After a swept login task's scrubbed launcher and task XML removal is
recorded in a durable audit trail this slot is login-audit prune: every
sweep appends to the trail, so the trail grows without bound until an
operator prunes stale entries by hand. The hole stays open so later
genesis can prune aged-out scrub records without disturbing a live owner
pid in any surviving repo.
"""

from __future__ import annotations

LOOP_LOGIN_PRUNE_ID = "capability.loop-login-prune"
LOOP_LOGIN_PRUNE_DONE_WHEN = (
    "A durable login-scrub audit trail's stale records are pruned once they "
    "age out so the trail stays bounded without disturbing a live owner pid "
    "in any surviving repo."
)
LOOP_LOGIN_PRUNE_GOAL = (
    "Repair login-audit prune: the durable scrub audit trail grows without "
    "bound as every sweep appends, until an operator prunes stale entries "
    "by hand."
)
LOOP_LOGIN_PRUNE_LEFTOVER = (
    "Later genesis can take login-audit prune so a durable scrub audit "
    "trail's stale records age out without an operator who prunes stale "
    "entries by hand."
)
