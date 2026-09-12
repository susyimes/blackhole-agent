"""Next unsaturated family after login-rollup repair silence.

After a repaired login-scrub audit trail rollup leaves a durable journal
of what the drifted rollup claimed, this slot is login-repair-journal
bloat: every rollup repair appends a permanent journal entry, so a trail
that drifts for years piles journal entries up without bound until an
operator prunes the journal by hand. The hole stays open so later genesis
can bound the repair journal without disturbing a live owner pid in any
surviving repo.
"""

from __future__ import annotations

LOOP_LOGIN_JOURNAL_PRUNE_ID = "capability.loop-login-journal-prune"
LOOP_LOGIN_JOURNAL_PRUNE_DONE_WHEN = (
    "A login-scrub audit trail's rollup repair journal is pruned of aged "
    "repair records so the journal stays bounded without disturbing a live "
    "owner pid in any surviving repo."
)
LOOP_LOGIN_JOURNAL_PRUNE_GOAL = (
    "Repair login-repair-journal bloat: every rollup repair appends a "
    "permanent journal entry, so a trail that drifts for years piles "
    "journal entries up without bound until an operator prunes the journal "
    "by hand."
)
LOOP_LOGIN_JOURNAL_PRUNE_LEFTOVER = (
    "Later genesis can take login-repair-journal bloat so a repair journal "
    "stays bounded without an operator pruning the journal by hand."
)
