"""Next unsaturated diversity-catalog family after RFC 3032 LABEL/STACK.

MPLS Label Stack Encoding is proved. Closed-contract leftover harvest used to steal
genesis with ``Mission contract is closed; later genesis can take the next
unsaturated diversity-catalog family.`` After mplslse seals a lsedigest
this slot is that next family: RFC 3209 RSVP-TE PATH/RESV
over an rsvpteid-gated rsvptedigest.
The protocol hole stays open so later genesis can opt the rsvpte provider in
and seal a rsvptedigest.
"""

from __future__ import annotations

RSVPTE_ACTUATION_ID = "capability.rsvpte-actuation"
RSVPTE_ACTUATION_DONE_WHEN = (
    f"capability_exists:{RSVPTE_ACTUATION_ID};"
    f"capability_proved:{RSVPTE_ACTUATION_ID};"
    "no_skill_route"
)
RSVPTE_ACTUATION_GOAL = (
    "Repair rfc3209 rsvpte path/resv cycle cannot land over http rsvpte rsvpteid: hosted rsvp-te remain unsupported so a PATH then RESV rsvpteid handshake cannot land and a sealed rsvptedigest cannot be produced. A missing rsvpte rsvpteid stays forbidden; fail-closed routing never opts the rsvpte provider in. An independent later poll of the stored rsvptedigest keeps the hole falsifiable. RSVP-TE sessions stay fail-closed without an rsvpteid-gated rsvptedigest."
)
RSVPTE_LEFTOVER = (
    "Later genesis can take RFC 3209 RSVP-TE PATH/RESV over an rsvpteid-gated rsvptedigest."
)
