"""Next unsaturated diversity-catalog family after RFC 4213 6IN4/CONFIG.

6IN4 is proved. Closed-contract leftover harvest used to steal
genesis with ``Mission contract is closed; later genesis can take the next
unsaturated diversity-catalog family.`` After sixin4 seals a sixin4digest
this slot is that next family: RFC 5572 IPv6 Tunnel Broker with the Tunnel
Setup Protocol TSP/SETUP over a tspid-gated tspdigest.
The protocol hole stays open so later genesis can opt the tsp provider in
and seal a tspdigest.
"""

from __future__ import annotations

TSP_ACTUATION_ID = "capability.tsp-actuation"
TSP_ACTUATION_DONE_WHEN = (
    f"capability_exists:{TSP_ACTUATION_ID};"
    f"capability_proved:{TSP_ACTUATION_ID};"
    "no_skill_route"
)
TSP_ACTUATION_GOAL = (
    'Repair rfc5572 tsp tsp/setup cycle cannot land over http tsp tspid: hosted ipv6 tunnel broker with the tunnel setup protocol endpoints remain unsupported so a TSP then SETUP tspid handshake cannot land and a sealed tspdigest cannot be produced. A missing tsp tspid stays forbidden; fail-closed routing never opts the tsp provider in. An independent later poll of the stored tspdigest keeps the hole falsifiable. Tunnel setup protocol sessions stay fail-closed without a tspid-gated tspdigest.'
)
