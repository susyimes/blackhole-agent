"""Next unsaturated diversity-catalog family after RFC 6427 FM/AIS.

MPLS Fault Management Operations, Administration, and Maintenance (OAM) is proved. Closed-contract leftover harvest used to steal
genesis with ``Mission contract is closed; later genesis can take the next
unsaturated diversity-catalog family.`` After fmoam seals a fmoamdigest
this slot is that next family: RFC 6428 Proactive Connectivity Verification, Continuity Check, and Remote Defect Indication for the MPLS Transport Profile
CC/CV over an pcvid-gated pcvdigest.
The protocol hole stays open so later genesis can opt the pcv provider in
and seal a pcvdigest.
"""

from __future__ import annotations

PCV_ACTUATION_ID = "capability.pcv-actuation"
PCV_ACTUATION_DONE_WHEN = (
    f"capability_exists:{PCV_ACTUATION_ID};"
    f"capability_proved:{PCV_ACTUATION_ID};"
    "no_skill_route"
)
PCV_ACTUATION_GOAL = (
    "Repair rfc6428 pcv cc/cv cycle cannot land over http pcv pcvid: "
    "hosted pcv remain unsupported so a CC then CV pcvid handshake cannot "
    "land and a sealed pcvdigest cannot be produced. A missing pcv pcvid stays "
    "forbidden; fail-closed routing never opts the pcv provider in. An independent "
    "later poll of the stored pcvdigest keeps the hole falsifiable. PCV sessions "
    "stay fail-closed without an pcvid-gated pcvdigest."
)
PCV_LEFTOVER = (
    "Later genesis can take RFC 6428 Proactive Connectivity Verification, Continuity Check, and Remote Defect Indication for the MPLS Transport Profile "
    "CC/CV over an pcvid-gated pcvdigest."
)
