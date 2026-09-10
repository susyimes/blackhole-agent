"""Next unsaturated diversity-catalog family after RFC 6513 MVPN/CMCAST.

Multicast in MPLS/BGP IP VPNs is proved. Closed-contract leftover
harvest used to steal genesis with ``Mission contract is closed; later genesis
can take the next unsaturated diversity-catalog family.`` After mvpn seals a
mvpndigest this slot is that next family: RFC 6514 BGP Encodings and Procedures
for Multicast in MPLS/BGP IP VPNs PMSI/NLRI over a pmsiid-gated pmsidigest.
The protocol hole stays open so later genesis can opt the pmsi provider in
and seal a pmsidigest.
"""

from __future__ import annotations

PMSI_ACTUATION_ID = "capability.pmsi-actuation"
PMSI_ACTUATION_DONE_WHEN = (
    f"capability_exists:{PMSI_ACTUATION_ID};"
    f"capability_proved:{PMSI_ACTUATION_ID};"
    "no_skill_route"
)
PMSI_ACTUATION_GOAL = (
    "Repair rfc6514 pmsi pmsi/nlri cycle cannot land over http pmsi pmsiid: "
    "hosted pmsi remain unsupported so a PMSI then NLRI pmsiid handshake cannot "
    "land and a sealed pmsidigest cannot be produced. A missing pmsi pmsiid stays "
    "forbidden; fail-closed routing never opts the pmsi provider in. An independent "
    "later poll of the stored pmsidigest keeps the hole falsifiable. PMSI sessions "
    "stay fail-closed without a pmsiid-gated pmsidigest."
)
PMSI_LEFTOVER = (
    "Later genesis can take RFC 6514 BGP Encodings and Procedures for Multicast "
    "in MPLS/BGP IP VPNs PMSI/NLRI over a pmsiid-gated pmsidigest."
)
