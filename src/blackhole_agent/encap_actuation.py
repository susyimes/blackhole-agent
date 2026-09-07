"""Next unsaturated diversity-catalog family after RFC 5565 MESH/PEER.

MESH is proved. Closed-contract leftover harvest used to steal
genesis with ``Mission contract is closed; later genesis can take the next
unsaturated diversity-catalog family.`` After mesh seals a meshdigest
this slot is that next family: RFC 5512 BGP Encapsulation Subsequent Address Family Identifier ENCAP/SAFI over an
encapid-gated encapdigest.
The protocol hole stays open so later genesis can opt the encap provider in
and seal an encapdigest.
"""

from __future__ import annotations

ENCAP_ACTUATION_ID = "capability.encap-actuation"
ENCAP_ACTUATION_DONE_WHEN = (
    f"capability_exists:{ENCAP_ACTUATION_ID};"
    f"capability_proved:{ENCAP_ACTUATION_ID};"
    "no_skill_route"
)
ENCAP_ACTUATION_GOAL = (
    "Repair rfc5512 encap encap/safi cycle cannot land over http encap encapid: hosted "
    "bgp encapsulation subsequent address family identifier endpoints remain unsupported so a ENCAP then SAFI encapid handshake "
    "cannot land and a sealed encapdigest cannot be produced. A missing encap encapid "
    "stays forbidden; fail-closed routing never opts the encap provider in. An "
    "independent later poll of the stored encapdigest keeps the hole falsifiable. "
    "BGP encapsulation sessions stay fail-closed without an encapid-gated encapdigest."
)
