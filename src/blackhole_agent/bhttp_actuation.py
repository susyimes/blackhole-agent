"""Next unsaturated diversity-catalog family after RFC 9530 Digest Fields.

Digest Fields is proved. Closed-contract leftover harvest used to steal genesis
with ``Mission contract is closed; later genesis can take the next unsaturated
diversity-catalog family.`` After Digest Fields seals a contentdigest digest this slot is
that next family: RFC 9292 Binary HTTP ENCODE/DECODE over a binary message.
The protocol hole stays open so later genesis can opt the bhttp
provider in and seal a binarymsg digest.
"""

from __future__ import annotations

BHTTP_ACTUATION_ID = "capability.bhttp-actuation"
BHTTP_ACTUATION_DONE_WHEN = (
    f"capability_exists:{BHTTP_ACTUATION_ID};"
    f"capability_proved:{BHTTP_ACTUATION_ID};"
    "no_skill_route"
)
BHTTP_ACTUATION_GOAL = (
    "Repair rfc9292 bhttp encode/decode cycle cannot land over http "
    "bhttp messageid: hosted bhttp endpoints remain unsupported so an ENCODE then "
    "DECODE messageid handshake cannot land and a sealed binarymsg digest "
    "cannot be produced. A missing bhttp messageid stays forbidden; fail-closed "
    "routing never opts the bhttp provider in. An independent later poll of the "
    "stored message binarymsg keeps the hole falsifiable."
)
