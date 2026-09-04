"""Next unsaturated diversity-catalog family after RFC 7469 HTTP Public Key Pinning.

HTTP Public Key Pinning is proved. Closed-contract leftover harvest used to steal genesis
with ``Mission contract is closed; later genesis can take the next unsaturated
diversity-catalog family.`` After Public Key Pinning seals a pindigest this
slot is that next family: RFC 9163 Expect-CT EXPECT/REPORT over a
ctid-gated ctdigest. The protocol hole stays open so later genesis can opt the
expectct provider in and seal a ctdigest.
"""

from __future__ import annotations

EXPECTCT_ACTUATION_ID = "capability.expectct-actuation"
EXPECTCT_ACTUATION_DONE_WHEN = (
    f"capability_exists:{EXPECTCT_ACTUATION_ID};"
    f"capability_proved:{EXPECTCT_ACTUATION_ID};"
    "no_skill_route"
)
EXPECTCT_ACTUATION_GOAL = (
    "Repair rfc9163 expectct expect/report cycle cannot land over http "
    "expectct ctid: hosted expectct endpoints remain unsupported so an EXPECT then "
    "REPORT ctid handshake cannot land and a sealed ctdigest "
    "cannot be produced. A missing expectct ctid stays forbidden; fail-closed "
    "routing never opts the expectct provider in. An independent later poll of the "
    "stored ctdigest keeps the hole falsifiable."
)
