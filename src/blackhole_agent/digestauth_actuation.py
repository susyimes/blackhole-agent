"""Next unsaturated diversity-catalog family after RFC 2109 HTTP State Management.

HTTP State Management Mechanism is proved. Closed-contract leftover harvest
used to steal genesis with ``Mission contract is closed; later genesis can
take the next unsaturated diversity-catalog family.`` After HTTP State
Management seals a statedigest this slot is that next family: RFC 2069
Digest Access Authentication CHALLENGE/RESPONSE over a challengeid-gated
responsedigest.
The protocol hole stays open so later genesis can opt the digestauth provider in
and seal a responsedigest.
"""

from __future__ import annotations

DIGESTAUTH_ACTUATION_ID = "capability.digestauth-actuation"
DIGESTAUTH_ACTUATION_DONE_WHEN = (
    f"capability_exists:{DIGESTAUTH_ACTUATION_ID};"
    f"capability_proved:{DIGESTAUTH_ACTUATION_ID};"
    "no_skill_route"
)
DIGESTAUTH_ACTUATION_GOAL = (
    "Repair rfc2069 digestauth challenge/response cycle cannot land over http "
    "digestauth challengeid: hosted digestauth endpoints remain unsupported so a CHALLENGE then "
    "RESPONSE challengeid handshake cannot land and a sealed responsedigest "
    "cannot be produced. A missing digestauth challengeid stays forbidden; fail-closed "
    "routing never opts the digestauth provider in. An independent later poll of the "
    "stored responsedigest keeps the hole falsifiable."
)
