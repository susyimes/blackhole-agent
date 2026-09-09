"""Next unsaturated diversity-catalog family after RFC 4874 EXCLUDE/ROUTE.

Exclude Routes is proved. Closed-contract leftover harvest used to steal
genesis with ``Mission contract is closed; later genesis can take the next
unsaturated diversity-catalog family.`` After exroute seals an exroutedigest
this slot is that next family: RFC 4875 Point-to-Multipoint TE LSPs
P2MP/S2L over a p2mpteid-gated p2mptedigest.
The protocol hole stays open so later genesis can opt the p2mpte provider in
and seal a p2mptedigest.
"""

from __future__ import annotations

P2MPTE_ACTUATION_ID = "capability.p2mpte-actuation"
P2MPTE_ACTUATION_DONE_WHEN = (
    f"capability_exists:{P2MPTE_ACTUATION_ID};"
    f"capability_proved:{P2MPTE_ACTUATION_ID};"
    "no_skill_route"
)
P2MPTE_ACTUATION_GOAL = (
    "Repair rfc4875 p2mpte p2mp/s2l cycle cannot land over http p2mpte p2mpteid: "
    "hosted p2mpte remain unsupported so a P2MP then S2L p2mpteid handshake cannot "
    "land and a sealed p2mptedigest cannot be produced. A missing p2mpte p2mpteid stays "
    "forbidden; fail-closed routing never opts the p2mpte provider in. An independent "
    "later poll of the stored p2mptedigest keeps the hole falsifiable. P2MPTE sessions "
    "stay fail-closed without a p2mpteid-gated p2mptedigest."
)
P2MPTE_LEFTOVER = (
    "Later genesis can take RFC 4875 Point-to-Multipoint TE LSPs P2MP/S2L over a "
    "p2mpteid-gated p2mptedigest."
)
