"""Next unsaturated family after login-rollup trust.

After a compacted login-scrub audit trail's rollup is verified against the
trail it summarizes, this slot is login-rollup drift persistence: a drifted
rollup is detected, but the drifted rollup keeps misstating what was
compacted until an operator rewrites the drifted rollup by hand. The hole
stays open so later genesis can correct a drifted rollup against the trail
without disturbing a live owner pid in any surviving repo.
"""

from __future__ import annotations

LOOP_LOGIN_ROLLUP_REPAIR_ID = "capability.loop-login-rollup-repair"
LOOP_LOGIN_ROLLUP_REPAIR_DONE_WHEN = (
    "A drifted login-scrub audit trail rollup is corrected against the trail "
    "it summarizes so the durable rollup states what was compacted without "
    "disturbing a live owner pid in any surviving repo."
)
LOOP_LOGIN_ROLLUP_REPAIR_GOAL = (
    "Repair login-rollup drift persistence: a drifted compaction rollup is "
    "detected, but the drifted rollup keeps misstating what was compacted "
    "until an operator rewrites the drifted rollup by hand."
)
LOOP_LOGIN_ROLLUP_REPAIR_LEFTOVER = (
    "Later genesis can take login-rollup drift persistence so a drifted "
    "rollup is corrected without an operator rewriting the drifted rollup "
    "by hand."
)
