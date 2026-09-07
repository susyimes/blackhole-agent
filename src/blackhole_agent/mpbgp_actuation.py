"""Next unsaturated diversity-catalog family after RFC 5512 ENCAP/SAFI.

ENCAP is proved. Closed-contract leftover harvest used to steal
genesis with ``Mission contract is closed; later genesis can take the next
unsaturated diversity-catalog family.`` After encap seals an encapdigest
this slot is that next family: RFC 4760 Multiprotocol Extensions for BGP-4 REACH/UNREACH over a
mpbgpid-gated mpbgpdigest.
The protocol hole stays open so later genesis can opt the mpbgp provider in
and seal an mpbgpdigest.
"""

from __future__ import annotations

MPBGP_ACTUATION_ID = "capability.mpbgp-actuation"
MPBGP_ACTUATION_DONE_WHEN = (
    f"capability_exists:{MPBGP_ACTUATION_ID};"
    f"capability_proved:{MPBGP_ACTUATION_ID};"
    "no_skill_route"
)
MPBGP_ACTUATION_GOAL = (
    "Repair rfc4760 mpbgp reach/unreach cycle cannot land over http mpbgp mpbgpid: hosted "
    "multiprotocol extensions for bgp-4 nlri endpoints remain unsupported so a REACH then UNREACH mpbgpid handshake "
    "cannot land and a sealed mpbgpdigest cannot be produced. A missing mpbgp mpbgpid "
    "stays forbidden; fail-closed routing never opts the mpbgp provider in. An "
    "independent later poll of the stored mpbgpdigest keeps the hole falsifiable. "
    "Multiprotocol BGP sessions stay fail-closed without a mpbgpid-gated mpbgpdigest."
)
