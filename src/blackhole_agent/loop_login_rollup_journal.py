"""Next unsaturated family after login-rollup drift persistence.

After a drifted login-scrub audit trail rollup is corrected against the
trail it summarizes, this slot is login-rollup repair silence: every repair
of a drifted rollup overwrites the drifted claims without a durable record,
so an operator auditing a repaired trail cannot tell what the drifted
rollup claimed without reconstructing the drifted claims by hand. The hole
stays open so later genesis can journal each rollup correction without
disturbing a live owner pid in any surviving repo.
"""

from __future__ import annotations

LOOP_LOGIN_ROLLUP_JOURNAL_ID = "capability.loop-login-rollup-journal"
LOOP_LOGIN_ROLLUP_JOURNAL_DONE_WHEN = (
    "A repaired login-scrub audit trail rollup leaves a durable record of "
    "what the drifted rollup claimed and what was corrected so the repair "
    "stays auditable without disturbing a live owner pid in any surviving "
    "repo."
)
LOOP_LOGIN_ROLLUP_JOURNAL_GOAL = (
    "Repair login-rollup repair silence: every repair of a drifted rollup "
    "overwrites the drifted claims without a durable record, so an operator "
    "auditing a repaired trail cannot tell what the drifted rollup claimed "
    "without reconstructing the drifted claims by hand."
)
LOOP_LOGIN_ROLLUP_JOURNAL_LEFTOVER = (
    "Later genesis can take login-rollup repair silence so a repaired "
    "rollup leaves a durable record of the drifted claims without an "
    "operator reconstructing the drifted claims by hand."
)
