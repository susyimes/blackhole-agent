"""Next unsaturated diversity-catalog family after RFC 3031 FEC/NHLFE.

Multiprotocol Label Switching Architecture is proved. Closed-contract leftover harvest used to steal
genesis with ``Mission contract is closed; later genesis can take the next
unsaturated diversity-catalog family.`` After mplsarch seals a mplsdigest
this slot is that next family: RFC 3032 MPLS Label Stack Encoding LABEL/STACK
over an lseid-gated lsedigest.
The protocol hole stays open so later genesis can opt the mplslse provider in
and seal a lsedigest.
"""

from __future__ import annotations

MPLSLSE_ACTUATION_ID = "capability.mplslse-actuation"
MPLSLSE_ACTUATION_DONE_WHEN = (
    f"capability_exists:{MPLSLSE_ACTUATION_ID};"
    f"capability_proved:{MPLSLSE_ACTUATION_ID};"
    "no_skill_route"
)
MPLSLSE_ACTUATION_GOAL = (
    "Repair rfc3032 mplslse label/stack cycle cannot land over http mplslse lseid: hosted mpls label stack encoding remain unsupported so a LABEL then STACK lseid handshake cannot land and a sealed lsedigest cannot be produced. A missing mplslse lseid stays forbidden; fail-closed routing never opts the mplslse provider in. An independent later poll of the stored lsedigest keeps the hole falsifiable. MPLS Label Stack Encoding sessions stay fail-closed without an lseid-gated lsedigest."
)
MPLSLSE_LEFTOVER = (
    "Later genesis can take RFC 3032 MPLS Label Stack Encoding LABEL/STACK over an lseid-gated lsedigest."
)
