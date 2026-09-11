"""Next unsaturated family after login-prune tombstone.

After a pruned login-scrub audit record leaves a durable tombstone naming
what aged out, this slot is login-tombstone bloat: every prune adds a
permanent tombstone, so a trail that prunes for years piles tombstones up
without bound until an operator compacts tombstones by hand. The hole stays
open so later genesis can compact aged tombstones without disturbing a live
owner pid in any surviving repo.
"""

from __future__ import annotations

LOOP_LOGIN_COMPACT_ID = "capability.loop-login-compact"
LOOP_LOGIN_COMPACT_DONE_WHEN = (
    "A durable login-scrub audit trail's tombstones are compacted once the "
    "records they name are long gone so the trail stays small and "
    "reconcilable without disturbing a live owner pid in any surviving repo."
)
LOOP_LOGIN_COMPACT_GOAL = (
    "Repair login-tombstone bloat: every prune adds a permanent tombstone, "
    "so a trail that prunes for years piles tombstones up without bound "
    "until an operator compacts tombstones by hand."
)
LOOP_LOGIN_COMPACT_LEFTOVER = (
    "Later genesis can take login-tombstone bloat so a trail's tombstones "
    "are compacted without an operator compacting tombstones by hand."
)
