"""Next unsaturated diversity-catalog family after RFC 9856 WARM/HOT.

Multicast Source Redundancy in EVPNs is proved. Closed-contract leftover harvest used to steal
genesis with ``Mission contract is closed; later genesis can take the next
unsaturated diversity-catalog family.`` After msred seals a msreddigest
this slot is that next family: RFC 10018 Multicast and Ethernet VPN with Segment Routing P2MP/IR
over a p2mpirid-gated p2mpirdigest.
The protocol hole stays open so later genesis can opt the p2mpir provider in
and seal a p2mpirdigest.
"""

from __future__ import annotations

P2MPIR_ACTUATION_ID = "capability.p2mpir-actuation"
P2MPIR_ACTUATION_DONE_WHEN = (
    f"capability_exists:{P2MPIR_ACTUATION_ID};"
    f"capability_proved:{P2MPIR_ACTUATION_ID};"
    "no_skill_route"
)
P2MPIR_ACTUATION_GOAL = (
    "Repair rfc10018 p2mpir p2mp/ir cycle cannot land over http p2mpir p2mpirid: hosted multicast and ethernet vpn with segment routing remain unsupported so a P2MP then IR p2mpirid handshake cannot land and a sealed p2mpirdigest cannot be produced. A missing p2mpir p2mpirid stays forbidden; fail-closed routing never opts the p2mpir provider in. An independent later poll of the stored p2mpirdigest keeps the hole falsifiable. Multicast and Ethernet VPN with Segment Routing sessions stay fail-closed without a p2mpirid-gated p2mpirdigest."
)
