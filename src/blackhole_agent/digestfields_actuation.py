"""Next unsaturated diversity-catalog family after RFC 9421 HTTP Message Signatures.

HTTP Message Signatures is proved. Closed-contract leftover harvest used to steal genesis
with ``Mission contract is closed; later genesis can take the next unsaturated
diversity-catalog family.`` After HTTP Message Signatures seals a sigbase digest this slot is
that next family: RFC 9530 Digest Fields DIGEST/VERIFY over a content digest.
The protocol hole stays open so later genesis can opt the digestfields
provider in and seal a contentdigest digest.
"""

from __future__ import annotations

DIGESTFIELDS_ACTUATION_ID = "capability.digestfields-actuation"
DIGESTFIELDS_ACTUATION_DONE_WHEN = (
    f"capability_exists:{DIGESTFIELDS_ACTUATION_ID};"
    f"capability_proved:{DIGESTFIELDS_ACTUATION_ID};"
    "no_skill_route"
)
DIGESTFIELDS_ACTUATION_GOAL = (
    "Repair rfc9530 digestfields digest/verify cycle cannot land over http "
    "digestfields digestid: hosted digestfields endpoints remain unsupported so a DIGEST then "
    "VERIFY digestid handshake cannot land and a sealed contentdigest digest "
    "cannot be produced. A missing digestfields digestid stays forbidden; fail-closed "
    "routing never opts the digestfields provider in. An independent later poll of the "
    "stored representation contentdigest keeps the hole falsifiable."
)
