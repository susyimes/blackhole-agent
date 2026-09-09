"""Next unsaturated diversity-catalog family after RFC 6435 LI/LB.

A Protocol for Lock Instruct and Loopback of MPLS Transport Profile
(MPLS-TP) OAM is proved. Closed-contract leftover harvest used to steal
genesis with ``Mission contract is closed; later genesis can take the next
unsaturated diversity-catalog family.`` After lilb seals a lilbdigest
this slot is that next family: RFC 6478 Pseudowire Status for Static
Pseudowires STATUS/ACK over an pwstid-gated pwstdigest.
The protocol hole stays open so later genesis can opt the pwst provider in
and seal a pwstdigest.
"""

from __future__ import annotations

PWST_ACTUATION_ID = "capability.pwst-actuation"
PWST_ACTUATION_DONE_WHEN = (
    f"capability_exists:{PWST_ACTUATION_ID};"
    f"capability_proved:{PWST_ACTUATION_ID};"
    "no_skill_route"
)
PWST_ACTUATION_GOAL = (
    "Repair rfc6478 pwst status/ack cycle cannot land over http pwst pwstid: "
    "hosted pwst remain unsupported so a STATUS then ACK pwstid handshake cannot "
    "land and a sealed pwstdigest cannot be produced. A missing pwst pwstid stays "
    "forbidden; fail-closed routing never opts the pwst provider in. An independent "
    "later poll of the stored pwstdigest keeps the hole falsifiable. PWST sessions "
    "stay fail-closed without an pwstid-gated pwstdigest."
)
PWST_LEFTOVER = (
    "Later genesis can take RFC 6478 Pseudowire Status for Static "
    "Pseudowires "
    "STATUS/ACK over an pwstid-gated pwstdigest."
)
