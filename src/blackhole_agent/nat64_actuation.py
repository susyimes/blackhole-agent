"""Next unsaturated diversity-catalog family after RFC 8781 PREF64/PREFIX.

Discovering PREF64 in Router Advertisements is proved. Closed-contract leftover
harvest used to steal genesis with ``Mission contract is closed; later genesis can take
the next unsaturated diversity-catalog family.`` After pref64 seals a pref64digest
this slot is that next family: RFC 6146 Stateful NAT64
NAT64/SESSION over a nat64id-gated nat64digest.
The protocol hole stays open so later genesis can opt the nat64 provider in
and seal a nat64digest.
"""

from __future__ import annotations

NAT64_ACTUATION_ID = "capability.nat64-actuation"
NAT64_ACTUATION_DONE_WHEN = (
    f"capability_exists:{NAT64_ACTUATION_ID};"
    f"capability_proved:{NAT64_ACTUATION_ID};"
    "no_skill_route"
)
NAT64_ACTUATION_GOAL = (
    "Repair rfc6146 nat64 nat64/session cycle cannot land over http "
    "nat64 nat64id: hosted nat64 endpoints remain unsupported so a NAT64 then "
    "SESSION nat64id handshake cannot land and a sealed nat64digest "
    "cannot be produced. A missing nat64 nat64id stays forbidden; fail-closed "
    "routing never opts the nat64 provider in. An independent later poll of the "
    "stored nat64digest keeps the hole falsifiable."
)
