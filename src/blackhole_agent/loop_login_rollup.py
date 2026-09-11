"""Next unsaturated family after login-tombstone compact.

After a durable login-scrub audit trail's long-gone tombstones are
compacted so the trail stays small, this slot is login-compact silence:
every compaction erases aged tombstones without a trace, so an operator
reconciling a compacted trail cannot tell a compacted tombstone from a
record that was never written. The hole stays open so later genesis can
leave a durable rollup of what was compacted without disturbing a live
owner pid in any surviving repo.
"""

from __future__ import annotations

LOOP_LOGIN_ROLLUP_ID = "capability.loop-login-rollup"
LOOP_LOGIN_ROLLUP_DONE_WHEN = (
    "A compacted login-scrub audit trail leaves a durable rollup naming how "
    "many tombstones were compacted and the span they covered so the trail "
    "stays reconcilable without disturbing a live owner pid in any "
    "surviving repo."
)
LOOP_LOGIN_ROLLUP_GOAL = (
    "Repair login-compact silence: every compaction erases aged tombstones "
    "without a trace, so an operator reconciling a compacted trail cannot "
    "tell a compacted tombstone from a record that was never written."
)
LOOP_LOGIN_ROLLUP_LEFTOVER = (
    "Later genesis can take login-compact silence so a compacted trail "
    "leaves a durable rollup without an operator reconstructing compacted "
    "tombstones by hand."
)
