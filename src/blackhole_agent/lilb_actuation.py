"""Next unsaturated diversity-catalog family after RFC 6428 CC/CV.

Proactive Connectivity Verification, Continuity Check, and Remote Defect Indication
for the MPLS Transport Profile is proved. Closed-contract leftover harvest used to steal
genesis with ``Mission contract is closed; later genesis can take the next
unsaturated diversity-catalog family.`` After pcv seals a pcvdigest
this slot is that next family: RFC 6435 A Protocol for Lock Instruct and Loopback of
MPLS Transport Profile (MPLS-TP) OAM LI/LB over an lilbid-gated lilbdigest.
The protocol hole stays open so later genesis can opt the lilb provider in
and seal a lilbdigest.
"""

from __future__ import annotations

LILB_ACTUATION_ID = "capability.lilb-actuation"
LILB_ACTUATION_DONE_WHEN = (
    f"capability_exists:{LILB_ACTUATION_ID};"
    f"capability_proved:{LILB_ACTUATION_ID};"
    "no_skill_route"
)
LILB_ACTUATION_GOAL = (
    "Repair rfc6435 lilb li/lb cycle cannot land over http lilb lilbid: "
    "hosted lilb remain unsupported so a LI then LB lilbid handshake cannot "
    "land and a sealed lilbdigest cannot be produced. A missing lilb lilbid stays "
    "forbidden; fail-closed routing never opts the lilb provider in. An independent "
    "later poll of the stored lilbdigest keeps the hole falsifiable. LILB sessions "
    "stay fail-closed without an lilbid-gated lilbdigest."
)
LILB_LEFTOVER = (
    "Later genesis can take RFC 6435 A Protocol for Lock Instruct and Loopback of "
    "MPLS Transport Profile (MPLS-TP) OAM "
    "LI/LB over an lilbid-gated lilbdigest."
)
