"""Next unsaturated diversity-catalog family after RFC 6512 MLDP/ROOT.

Using Multipoint LDP When the Backbone Has No Route to the Root is proved. Closed-contract leftover
harvest used to steal genesis with ``Mission contract is closed; later genesis
can take the next unsaturated diversity-catalog family.`` After mldp seals a
mldpdigest this slot is that next family: RFC 6513 Multicast in MPLS/BGP IP
VPNs MVPN/CMCAST over an mvpnid-gated mvpndigest.
The protocol hole stays open so later genesis can opt the mvpn provider in
and seal a mvpndigest.
"""

from __future__ import annotations

MVPN_ACTUATION_ID = "capability.mvpn-actuation"
MVPN_ACTUATION_DONE_WHEN = (
    f"capability_exists:{MVPN_ACTUATION_ID};"
    f"capability_proved:{MVPN_ACTUATION_ID};"
    "no_skill_route"
)
MVPN_ACTUATION_GOAL = (
    "Repair rfc6513 mvpn mvpn/cmcast cycle cannot land over http mvpn mvpnid: "
    "hosted mvpn remain unsupported so a MVPN then CMCAST mvpnid handshake cannot "
    "land and a sealed mvpndigest cannot be produced. A missing mvpn mvpnid stays "
    "forbidden; fail-closed routing never opts the mvpn provider in. An independent "
    "later poll of the stored mvpndigest keeps the hole falsifiable. MVPN sessions "
    "stay fail-closed without an mvpnid-gated mvpndigest."
)
MVPN_LEFTOVER = (
    "Later genesis can take RFC 6513 Multicast in MPLS/BGP IP VPNs "
    "MVPN/CMCAST over an mvpnid-gated mvpndigest."
)
