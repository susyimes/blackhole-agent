"""Next unsaturated diversity-catalog family after RFC 5886 MON/PCEID.

A Set of Monitoring Tools for PCE-Based Architecture is proved. Closed-contract leftover harvest used to steal
genesis with ``Mission contract is closed; later genesis can take the next
unsaturated diversity-catalog family.`` After pcemon seals a pcemondigest
this slot is that next family: RFC 6006 Extensions to PCEP for Point-to-Multipoint TE LSPs
P2MP/ENDPOINTS over a pcepmpid-gated pcepmpdigest.
The protocol hole stays open so later genesis can opt the pcepmp provider in
and seal a pcepmpdigest.
"""

from __future__ import annotations

PCEPMP_ACTUATION_ID = "capability.pcepmp-actuation"
PCEPMP_ACTUATION_DONE_WHEN = (
    f"capability_exists:{PCEPMP_ACTUATION_ID};"
    f"capability_proved:{PCEPMP_ACTUATION_ID};"
    "no_skill_route"
)
PCEPMP_ACTUATION_GOAL = (
    "Repair rfc6006 pcepmp p2mp/endpoints cycle cannot land over http pcepmp pcepmpid: "
    "hosted pcepmp remain unsupported so a P2MP then ENDPOINTS pcepmpid handshake cannot "
    "land and a sealed pcepmpdigest cannot be produced. A missing pcepmp pcepmpid stays "
    "forbidden; fail-closed routing never opts the pcepmp provider in. An independent "
    "later poll of the stored pcepmpdigest keeps the hole falsifiable. PCEPMP sessions "
    "stay fail-closed without a pcepmpid-gated pcepmpdigest."
)
PCEPMP_LEFTOVER = (
    "Later genesis can take RFC 6006 Extensions to PCEP for Point-to-Multipoint TE LSPs "
    "P2MP/ENDPOINTS over a pcepmpid-gated pcepmpdigest."
)
