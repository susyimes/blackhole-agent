"""Next unsaturated diversity-catalog family after RFC 9110 HTTP Semantics.

HTTP Semantics is proved. Closed-contract leftover harvest used to steal genesis
with ``Mission contract is closed; later genesis can take the next unsaturated
diversity-catalog family.`` After HTTP Semantics seals a fieldsection digest this
slot is that next family: RFC 8941 Structured Fields DICT/LIST over a dictid-gated
sfv. The protocol hole stays open so later genesis can opt the
structuredfields provider in and seal an sfv digest.
"""

from __future__ import annotations

STRUCTUREDFIELDS_ACTUATION_ID = "capability.structuredfields-actuation"
STRUCTUREDFIELDS_ACTUATION_DONE_WHEN = (
    f"capability_exists:{STRUCTUREDFIELDS_ACTUATION_ID};"
    f"capability_proved:{STRUCTUREDFIELDS_ACTUATION_ID};"
    "no_skill_route"
)
STRUCTUREDFIELDS_ACTUATION_GOAL = (
    "Repair rfc8941 structuredfields dict/list cycle cannot land over http "
    "structuredfields dictid: hosted structuredfields endpoints remain unsupported so a DICT then "
    "LIST dictid handshake cannot land and a sealed sfv digest "
    "cannot be produced. A missing structuredfields dictid stays forbidden; fail-closed "
    "routing never opts the structuredfields provider in. An independent later poll of the "
    "stored sfv keeps the hole falsifiable."
)
