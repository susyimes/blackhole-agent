"""Next unsaturated diversity-catalog family after RFC 7034 X-Frame-Options.

X-Frame-Options is proved. Closed-contract leftover harvest used to steal genesis
with ``Mission contract is closed; later genesis can take the next unsaturated
diversity-catalog family.`` After X-Frame-Options seals a framedigest this
slot is that next family: RFC 6454 The Web Origin Concept SERIALIZE/TUPLE over a
tupleid-gated tupledigest. The protocol hole stays open so later genesis can opt the
weborigin provider in and seal a tupledigest.
"""

from __future__ import annotations

WEBORIGIN_ACTUATION_ID = "capability.weborigin-actuation"
WEBORIGIN_ACTUATION_DONE_WHEN = (
    f"capability_exists:{WEBORIGIN_ACTUATION_ID};"
    f"capability_proved:{WEBORIGIN_ACTUATION_ID};"
    "no_skill_route"
)
WEBORIGIN_ACTUATION_GOAL = (
    "Repair rfc6454 weborigin serialize/tuple cycle cannot land over http "
    "weborigin tupleid: hosted weborigin endpoints remain unsupported so a SERIALIZE then "
    "TUPLE tupleid handshake cannot land and a sealed tupledigest "
    "cannot be produced. A missing weborigin tupleid stays forbidden; fail-closed "
    "routing never opts the weborigin provider in. An independent later poll of the "
    "stored tupledigest keeps the hole falsifiable."
)
