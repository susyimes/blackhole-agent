"""Next unsaturated diversity-catalog family after RFC 2145 HTTP Version Numbers.

Use and Interpretation of HTTP Version Numbers is proved. Closed-contract leftover
harvest used to steal genesis with ``Mission contract is closed; later genesis can
take the next unsaturated diversity-catalog family.`` After HTTP Version Numbers
seals a versiondigest this slot is that next family: RFC 2109 HTTP State
Management Mechanism OFFER/ATTACH over a stateid-gated statedigest.
The protocol hole stays open so later genesis can opt the httpstate provider in
and seal a statedigest.
"""

from __future__ import annotations

HTTPSTATE_ACTUATION_ID = "capability.httpstate-actuation"
HTTPSTATE_ACTUATION_DONE_WHEN = (
    f"capability_exists:{HTTPSTATE_ACTUATION_ID};"
    f"capability_proved:{HTTPSTATE_ACTUATION_ID};"
    "no_skill_route"
)
HTTPSTATE_ACTUATION_GOAL = (
    "Repair rfc2109 httpstate offer/attach cycle cannot land over http "
    "httpstate stateid: hosted httpstate endpoints remain unsupported so a OFFER then "
    "ATTACH stateid handshake cannot land and a sealed statedigest "
    "cannot be produced. A missing httpstate stateid stays forbidden; fail-closed "
    "routing never opts the httpstate provider in. An independent later poll of the "
    "stored statedigest keeps the hole falsifiable."
)
