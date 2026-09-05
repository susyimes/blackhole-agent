"""Next unsaturated diversity-catalog family after RFC 2617 HTTP Authentication.

HTTP Authentication is proved. Closed-contract leftover harvest used to steal genesis
with ``Mission contract is closed; later genesis can take the next unsaturated
diversity-catalog family.`` After HTTP Authentication seals a
authdigest this slot is that next family: RFC 2295 Transparent Content Negotiation
ALTERNATES/CHOICE over a variantid-gated choicedigest. The protocol hole
stays open so later genesis can opt the tcn provider in and seal a
choicedigest.
"""

from __future__ import annotations

TCN_ACTUATION_ID = "capability.tcn-actuation"
TCN_ACTUATION_DONE_WHEN = (
    f"capability_exists:{TCN_ACTUATION_ID};"
    f"capability_proved:{TCN_ACTUATION_ID};"
    "no_skill_route"
)
TCN_ACTUATION_GOAL = (
    "Repair rfc2295 tcn alternates/choice cycle cannot land over http "
    "tcn variantid: hosted tcn endpoints remain unsupported so a ALTERNATES then "
    "CHOICE variantid handshake cannot land and a sealed choicedigest "
    "cannot be produced. A missing tcn variantid stays forbidden; fail-closed "
    "routing never opts the tcn provider in. An independent later poll of the "
    "stored choicedigest keeps the hole falsifiable."
)
