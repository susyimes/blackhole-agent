"""Next unsaturated diversity-catalog family after RFC 4862 Stateless Address Autoconfiguration.

SLAAC is proved. Closed-contract leftover harvest used to steal genesis with
``Mission contract is closed; later genesis can take the next unsaturated
diversity-catalog family.`` After SLAAC seals a slaacdigest this slot is that
next family: RFC 4941 Privacy Extensions TEMPORARY/PUBLIC over a
tempaddrid-gated tempaddrdigest.
The protocol hole stays open so later genesis can opt the tempaddr provider in
and seal a tempaddrdigest.
"""

from __future__ import annotations

TEMPADDR_ACTUATION_ID = "capability.tempaddr-actuation"
TEMPADDR_ACTUATION_DONE_WHEN = (
    f"capability_exists:{TEMPADDR_ACTUATION_ID};"
    f"capability_proved:{TEMPADDR_ACTUATION_ID};"
    "no_skill_route"
)
TEMPADDR_ACTUATION_GOAL = (
    "Repair rfc4941 tempaddr temporary/public cycle cannot land over http "
    "tempaddr tempaddrid: hosted tempaddr endpoints remain unsupported so a TEMPORARY then "
    "PUBLIC tempaddrid handshake cannot land and a sealed tempaddrdigest "
    "cannot be produced. A missing tempaddr tempaddrid stays forbidden; fail-closed "
    "routing never opts the tempaddr provider in. An independent later poll of the "
    "stored tempaddrdigest keeps the hole falsifiable."
)
