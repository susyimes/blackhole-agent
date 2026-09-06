"""Next unsaturated diversity-catalog family after RFC 4007 IPv6 Scoped Address Architecture.

IPv6 Scoped Address Architecture is proved. Closed-contract leftover harvest used to
steal genesis with ``Mission contract is closed; later genesis can take the next
unsaturated diversity-catalog family.`` After ipv6scope seals a scopedigest
this slot is that next family: RFC 6724 Default Address Selection for IPv6
SOURCE/DEST over a selectid-gated selectdigest.
The protocol hole stays open so later genesis can opt the addrselect provider in
and seal a selectdigest.
"""

from __future__ import annotations

ADDRSELECT_ACTUATION_ID = "capability.addrselect-actuation"
ADDRSELECT_ACTUATION_DONE_WHEN = (
    f"capability_exists:{ADDRSELECT_ACTUATION_ID};"
    f"capability_proved:{ADDRSELECT_ACTUATION_ID};"
    "no_skill_route"
)
ADDRSELECT_ACTUATION_GOAL = (
    "Repair rfc6724 addrselect source/dest cycle cannot land over http "
    "addrselect selectid: hosted addrselect endpoints remain unsupported so a SOURCE then "
    "DEST selectid handshake cannot land and a sealed selectdigest "
    "cannot be produced. A missing addrselect selectid stays forbidden; fail-closed "
    "routing never opts the addrselect provider in. An independent later poll of the "
    "stored selectdigest keeps the hole falsifiable."
)
