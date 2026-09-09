"""Next unsaturated diversity-catalog family after RFC 3209 PATH/RESV.

RSVP-TE is proved. Closed-contract leftover harvest used to steal
genesis with ``Mission contract is closed; later genesis can take the next
unsaturated diversity-catalog family.`` After rsvpte seals a rsvptedigest
this slot is that next family: RFC 3473 GMPLS RSVP-TE NOTIFY/RESVCONF
over a gmplsid-gated gmplsdigest.
The protocol hole stays open so later genesis can opt the gmpls provider in
and seal a gmplsdigest.
"""

from __future__ import annotations

GMPLS_ACTUATION_ID = "capability.gmpls-actuation"
GMPLS_ACTUATION_DONE_WHEN = (
    f"capability_exists:{GMPLS_ACTUATION_ID};"
    f"capability_proved:{GMPLS_ACTUATION_ID};"
    "no_skill_route"
)
GMPLS_ACTUATION_GOAL = (
    "Repair rfc3473 gmpls notify/resvconf cycle cannot land over http gmpls gmplsid: hosted gmpls rsvp-te remain unsupported so a NOTIFY then RESVCONF gmplsid handshake cannot land and a sealed gmplsdigest cannot be produced. A missing gmpls gmplsid stays forbidden; fail-closed routing never opts the gmpls provider in. An independent later poll of the stored gmplsdigest keeps the hole falsifiable. GMPLS RSVP-TE sessions stay fail-closed without a gmplsid-gated gmplsdigest."
)
GMPLS_LEFTOVER = (
    "Later genesis can take RFC 3473 GMPLS RSVP-TE NOTIFY/RESVCONF over a gmplsid-gated gmplsdigest."
)
