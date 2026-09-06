"""Next unsaturated diversity-catalog family after RFC 4861 Neighbor Discovery Protocol.

NDP is proved. Closed-contract leftover harvest used to steal genesis with
``Mission contract is closed; later genesis can take the next unsaturated
diversity-catalog family.`` After NDP seals an ndpdigest this slot is that
next family: RFC 4862 IPv6 Stateless Address Autoconfiguration ROUTER/PREFIX over a
slaacid-gated slaacdigest.
The protocol hole stays open so later genesis can opt the slaac provider in
and seal a slaacdigest.
"""

from __future__ import annotations

SLAAC_ACTUATION_ID = "capability.slaac-actuation"
SLAAC_ACTUATION_DONE_WHEN = (
    f"capability_exists:{SLAAC_ACTUATION_ID};"
    f"capability_proved:{SLAAC_ACTUATION_ID};"
    "no_skill_route"
)
SLAAC_ACTUATION_GOAL = (
    "Repair rfc4862 slaac router/prefix cycle cannot land over http "
    "slaac slaacid: hosted slaac endpoints remain unsupported so a ROUTER then "
    "PREFIX slaacid handshake cannot land and a sealed slaacdigest "
    "cannot be produced. A missing slaac slaacid stays forbidden; fail-closed "
    "routing never opts the slaac provider in. An independent later poll of the "
    "stored slaacdigest keeps the hole falsifiable."
)
