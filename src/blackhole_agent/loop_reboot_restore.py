"""Next unsaturated family after orphaned continuous-loop reaping.

After orphan-loop-reap is proved this slot is continuous-loop reboot
restoration: a reaped orphan after login or reboot stays stopped until an
operator starts it. The hole stays open so later genesis can restore the
native loop without starting a second controller beside a live owner pid.
"""

from __future__ import annotations

LOOP_REBOOT_RESTORE_ID = "capability.loop-reboot-restore"
LOOP_REBOOT_RESTORE_DONE_WHEN = (
    "A reaped orphaned continuous-loop state is restored by a startup helper "
    "that starts only when no live owner pid exists and does not start a "
    "second controller beside a live owner pid."
)
LOOP_REBOOT_RESTORE_GOAL = (
    "Repair continuous-loop reboot restoration: a reaped orphan after login "
    "or reboot stays stopped until an operator starts it, so the native loop "
    "does not resume."
)
LOOP_REBOOT_RESTORE_LEFTOVER = (
    "Later genesis can take continuous-loop reboot restoration so a reaped "
    "orphan after login or reboot stays stopped until an operator starts it."
)
