"""Next unsaturated diversity-catalog family after RFC 5861 HTTP Cache-Control Extensions for Stale Content.

Stale Content is proved. Closed-contract leftover harvest used to steal genesis
with ``Mission contract is closed; later genesis can take the next unsaturated
diversity-catalog family.`` After Stale Content seals a staledigest this
slot is that next family: RFC 5789 PATCH Method for HTTP
PATCH/ENTITY over a patchid-gated patchdigest. The protocol hole
stays open so later genesis can opt the httppatch provider in and seal a
patchdigest.
"""

from __future__ import annotations

HTTPPATCH_ACTUATION_ID = "capability.httppatch-actuation"
HTTPPATCH_ACTUATION_DONE_WHEN = (
    f"capability_exists:{HTTPPATCH_ACTUATION_ID};"
    f"capability_proved:{HTTPPATCH_ACTUATION_ID};"
    "no_skill_route"
)
HTTPPATCH_ACTUATION_GOAL = (
    "Repair rfc5789 httppatch patch/entity cycle cannot land over http "
    "httppatch patchid: hosted httppatch endpoints remain unsupported so a PATCH then "
    "ENTITY patchid handshake cannot land and a sealed patchdigest "
    "cannot be produced. A missing httppatch patchid stays forbidden; fail-closed "
    "routing never opts the httppatch provider in. An independent later poll of the "
    "stored patchdigest keeps the hole falsifiable."
)
