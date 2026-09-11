"""Next unsaturated family after login-audit prune.

After a durable login-scrub audit trail's stale records are pruned once they
age out, this slot is login-prune tombstone: a pruned audit record vanishes
from the trail without a trace, so an operator reconciling the bounded trail
cannot tell an aged-out record from one that was never written. The hole
stays open so later genesis can leave a durable tombstone for pruned records
without disturbing a live owner pid in any surviving repo.
"""

from __future__ import annotations

LOOP_LOGIN_TOMBSTONE_ID = "capability.loop-login-tombstone"
LOOP_LOGIN_TOMBSTONE_DONE_WHEN = (
    "A pruned login-scrub audit record leaves a durable tombstone naming what "
    "aged out so the bounded trail stays reconcilable without disturbing a "
    "live owner pid in any surviving repo."
)
LOOP_LOGIN_TOMBSTONE_GOAL = (
    "Repair login-prune tombstone: a pruned audit record vanishes from the "
    "trail without a trace, so an operator reconciling the bounded trail "
    "cannot tell an aged-out record from one that was never written."
)
LOOP_LOGIN_TOMBSTONE_LEFTOVER = (
    "Later genesis can take login-prune tombstone so a pruned audit record "
    "leaves a durable tombstone without an operator reconstructing aged-out "
    "records by hand."
)
