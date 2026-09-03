"""Next unsaturated diversity-catalog family after RFC 9298 MASQUE lockstep.

MASQUE is proved. Closed-contract leftover harvest used to steal genesis
with ``Mission contract is closed; later genesis can take the next unsaturated
diversity-catalog family.`` After MASQUE seals an authority digest this slot is
that next family: RFC 9484 CONNECT-IP ASSIGN/ADVERTISE over HTTP.
The protocol hole stays open so later genesis can opt the connectip
provider in and seal an ipaddr digest.
"""

from __future__ import annotations

CONNECTIP_ACTUATION_ID = "capability.connectip-actuation"
CONNECTIP_ACTUATION_DONE_WHEN = (
    f"capability_exists:{CONNECTIP_ACTUATION_ID};"
    f"capability_proved:{CONNECTIP_ACTUATION_ID};"
    "no_skill_route"
)
CONNECTIP_ACTUATION_GOAL = (
    "Repair rfc9484 connectip assign/advertise cycle cannot land over http "
    "connectip prefixid: hosted connectip endpoints remain unsupported so an ASSIGN then "
    "ADVERTISE prefixid handshake cannot land and a sealed ipaddr digest "
    "cannot be produced. A missing connectip prefixid stays forbidden; fail-closed "
    "routing never opts the connectip provider in. An independent later poll of the "
    "stored assigned ipaddr keeps the hole falsifiable."
)
