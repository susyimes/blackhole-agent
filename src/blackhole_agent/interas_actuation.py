"""Next unsaturated diversity-catalog family after RFC 5150 STITCH/JOIN.

Label Switched Path Stitching is proved. Closed-contract leftover harvest used to steal
genesis with ``Mission contract is closed; later genesis can take the next
unsaturated diversity-catalog family.`` After lspstitch seals a lspstitchdigest
this slot is that next family: RFC 5151 Inter-AS Traffic Engineering
CONTIG/NEST over an interasid-gated interasdigest.
The protocol hole stays open so later genesis can opt the interas provider in
and seal a interasdigest.
"""

from __future__ import annotations

INTERAS_ACTUATION_ID = "capability.interas-actuation"
INTERAS_ACTUATION_DONE_WHEN = (
    f"capability_exists:{INTERAS_ACTUATION_ID};"
    f"capability_proved:{INTERAS_ACTUATION_ID};"
    "no_skill_route"
)
INTERAS_ACTUATION_GOAL = (
    "Repair rfc5151 interas contig/nest cycle cannot land over http interas interasid: "
    "hosted interas remain unsupported so a CONTIG then NEST interasid handshake cannot "
    "land and a sealed interasdigest cannot be produced. A missing interas interasid stays "
    "forbidden; fail-closed routing never opts the interas provider in. An independent "
    "later poll of the stored interasdigest keeps the hole falsifiable. INTERAS sessions "
    "stay fail-closed without an interasid-gated interasdigest."
)
INTERAS_LEFTOVER = (
    "Later genesis can take RFC 5151 Inter-AS Traffic Engineering CONTIG/NEST over an "
    "interasid-gated interasdigest."
)
