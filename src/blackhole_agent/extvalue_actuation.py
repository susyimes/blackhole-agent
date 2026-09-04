"""Next unsaturated diversity-catalog family after RFC 5988 Web Linking.

Web Linking is proved. Closed-contract leftover harvest used to steal genesis
with ``Mission contract is closed; later genesis can take the next unsaturated
diversity-catalog family.`` After Web Linking seals a relationdigest this
slot is that next family: RFC 5987 Character Set and Language Encoding
ENCODING/LANGUAGE over a charsetid-gated charsetdigest. The protocol hole
stays open so later genesis can opt the extvalue provider in and seal a
charsetdigest.
"""

from __future__ import annotations

EXTVALUE_ACTUATION_ID = "capability.extvalue-actuation"
EXTVALUE_ACTUATION_DONE_WHEN = (
    f"capability_exists:{EXTVALUE_ACTUATION_ID};"
    f"capability_proved:{EXTVALUE_ACTUATION_ID};"
    "no_skill_route"
)
EXTVALUE_ACTUATION_GOAL = (
    "Repair rfc5987 extvalue encoding/language cycle cannot land over http "
    "extvalue charsetid: hosted extvalue endpoints remain unsupported so a ENCODING then "
    "LANGUAGE charsetid handshake cannot land and a sealed charsetdigest "
    "cannot be produced. A missing extvalue charsetid stays forbidden; fail-closed "
    "routing never opts the extvalue provider in. An independent later poll of the "
    "stored charsetdigest keeps the hole falsifiable."
)
