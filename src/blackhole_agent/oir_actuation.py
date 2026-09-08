"""Next unsaturated diversity-catalog family after RFC 10018 P2MP/IR.

Multicast and Ethernet VPN with Segment Routing is proved. Closed-contract leftover harvest used to steal
genesis with ``Mission contract is closed; later genesis can take the next
unsaturated diversity-catalog family.`` After p2mpir seals a p2mpirdigest
this slot is that next family: RFC 9574 Optimized Ingress Replication for EVPN OIR/BUM
over an oirid-gated oirdigest.
The protocol hole stays open so later genesis can opt the oir provider in
and seal an oirdigest.
"""

from __future__ import annotations

OIR_ACTUATION_ID = "capability.oir-actuation"
OIR_ACTUATION_DONE_WHEN = (
    f"capability_exists:{OIR_ACTUATION_ID};"
    f"capability_proved:{OIR_ACTUATION_ID};"
    "no_skill_route"
)
OIR_ACTUATION_GOAL = (
    "Repair rfc9574 oir oir/bum cycle cannot land over http oir oirid: hosted optimized ingress replication for evpn remain unsupported so an OIR then BUM oirid handshake cannot land and a sealed oirdigest cannot be produced. A missing oir oirid stays forbidden; fail-closed routing never opts the oir provider in. An independent later poll of the stored oirdigest keeps the hole falsifiable. Optimized Ingress Replication sessions stay fail-closed without an oirid-gated oirdigest."
)
