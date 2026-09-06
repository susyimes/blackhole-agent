"""Next unsaturated diversity-catalog family after RFC 4941 Privacy Extensions.

TEMPADDR is proved. Closed-contract leftover harvest used to steal genesis with
``Mission contract is closed; later genesis can take the next unsaturated
diversity-catalog family.`` After TEMPADDR seals a tempaddrdigest this slot is that
next family: RFC 7217 Semantically Opaque Interface Identifiers STABLE/OPAQUE over an
opaqueid-gated opaquedigest.
The protocol hole stays open so later genesis can opt the opaqueiid provider in
and seal an opaquedigest.
"""

from __future__ import annotations

OPAQUEIID_ACTUATION_ID = "capability.opaqueiid-actuation"
OPAQUEIID_ACTUATION_DONE_WHEN = (
    f"capability_exists:{OPAQUEIID_ACTUATION_ID};"
    f"capability_proved:{OPAQUEIID_ACTUATION_ID};"
    "no_skill_route"
)
OPAQUEIID_ACTUATION_GOAL = (
    "Repair rfc7217 opaqueiid stable/opaque cycle cannot land over http "
    "opaqueiid opaqueid: hosted opaqueiid endpoints remain unsupported so a STABLE then "
    "OPAQUE opaqueid handshake cannot land and a sealed opaquedigest "
    "cannot be produced. A missing opaqueiid opaqueid stays forbidden; fail-closed "
    "routing never opts the opaqueiid provider in. An independent later poll of the "
    "stored opaquedigest keeps the hole falsifiable."
)
