"""Next unsaturated diversity-catalog family after RFC 2817 Upgrading to TLS Within HTTP/1.1.

Upgrading to TLS Within HTTP/1.1 is proved. Closed-contract leftover harvest used to steal genesis
with ``Mission contract is closed; later genesis can take the next unsaturated
diversity-catalog family.`` After Upgrading to TLS Within HTTP/1.1 seals a
upgradetlsdigest this slot is that next family: RFC 2617 HTTP Authentication
AUTH/DIGEST over a nonceid-gated authdigest. The protocol hole
stays open so later genesis can opt the httpauth provider in and seal a
authdigest.
"""

from __future__ import annotations

HTTPAUTH_ACTUATION_ID = "capability.httpauth-actuation"
HTTPAUTH_ACTUATION_DONE_WHEN = (
    f"capability_exists:{HTTPAUTH_ACTUATION_ID};"
    f"capability_proved:{HTTPAUTH_ACTUATION_ID};"
    "no_skill_route"
)
HTTPAUTH_ACTUATION_GOAL = (
    "Repair rfc2617 httpauth auth/digest cycle cannot land over http "
    "httpauth nonceid: hosted httpauth endpoints remain unsupported so a AUTH then "
    "DIGEST nonceid handshake cannot land and a sealed authdigest "
    "cannot be produced. A missing httpauth nonceid stays forbidden; fail-closed "
    "routing never opts the httpauth provider in. An independent later poll of the "
    "stored authdigest keeps the hole falsifiable."
)
