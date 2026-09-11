"""Next unsaturated family after login-tombstone rollup.

After a compacted login-scrub audit trail leaves a durable rollup naming
how many tombstones were compacted and the span they covered, this slot is
login-rollup trust: the durable compaction rollup is never checked against
the trail it summarizes, so a drifted or forged rollup silently misstates
what was compacted until an operator reconciles the rollup by hand. The
hole stays open so later genesis can verify the rollup against the trail
without disturbing a live owner pid in any surviving repo.
"""

from __future__ import annotations

LOOP_LOGIN_VERIFY_ID = "capability.loop-login-verify"
LOOP_LOGIN_VERIFY_DONE_WHEN = (
    "A durable login-scrub audit trail's compaction rollup is verified "
    "against the trail it summarizes so a drifted rollup is detected "
    "without disturbing a live owner pid in any surviving repo."
)
LOOP_LOGIN_VERIFY_GOAL = (
    "Repair login-rollup trust: the durable compaction rollup is never "
    "checked against the trail it summarizes, so a drifted or forged rollup "
    "silently misstates what was compacted until an operator reconciles the "
    "rollup by hand."
)
LOOP_LOGIN_VERIFY_LEFTOVER = (
    "Later genesis can take login-rollup trust so a compaction rollup is "
    "verified against the trail without an operator reconciling the rollup "
    "by hand."
)
