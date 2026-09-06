"""Next unsaturated diversity-catalog family after RFC 7217 Opaque IIDs.

OPAQUEIID is proved. Closed-contract leftover harvest used to steal genesis with
``Mission contract is closed; later genesis can take the next unsaturated
diversity-catalog family.`` After OPAQUEIID seals an opaquedigest this slot is that
next family: RFC 3972 Cryptographically Generated Addresses GENERATE/VERIFY over a
cgaid-gated cgadigest.
The protocol hole stays open so later genesis can opt the cga provider in
and seal a cgadigest.
"""

from __future__ import annotations

CGA_ACTUATION_ID = "capability.cga-actuation"
CGA_ACTUATION_DONE_WHEN = (
    f"capability_exists:{CGA_ACTUATION_ID};"
    f"capability_proved:{CGA_ACTUATION_ID};"
    "no_skill_route"
)
CGA_ACTUATION_GOAL = (
    "Repair rfc3972 cga generate/verify cycle cannot land over http "
    "cga cgaid: hosted cga endpoints remain unsupported so a GENERATE then "
    "VERIFY cgaid handshake cannot land and a sealed cgadigest "
    "cannot be produced. A missing cga cgaid stays forbidden; fail-closed "
    "routing never opts the cga provider in. An independent later poll of the "
    "stored cgadigest keeps the hole falsifiable."
)
