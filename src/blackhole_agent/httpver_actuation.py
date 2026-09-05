"""Next unsaturated diversity-catalog family after RFC 2186 Internet Cache Protocol.

Internet Cache Protocol is proved. Closed-contract leftover harvest used to steal genesis
with ``Mission contract is closed; later genesis can take the next unsaturated
diversity-catalog family.`` After Internet Cache Protocol seals a
icpdigest this slot is that next family: RFC 2145 Use and Interpretation of
HTTP Version Numbers VERSION/INTERPRET over a versionid-gated versiondigest.
The protocol hole stays open so later genesis can opt the httpver provider in
and seal a versiondigest.
"""

from __future__ import annotations

HTTPVER_ACTUATION_ID = "capability.httpver-actuation"
HTTPVER_ACTUATION_DONE_WHEN = (
    f"capability_exists:{HTTPVER_ACTUATION_ID};"
    f"capability_proved:{HTTPVER_ACTUATION_ID};"
    "no_skill_route"
)
HTTPVER_ACTUATION_GOAL = (
    "Repair rfc2145 httpver version/interpret cycle cannot land over http "
    "httpver versionid: hosted httpver endpoints remain unsupported so a VERSION then "
    "INTERPRET versionid handshake cannot land and a sealed versiondigest "
    "cannot be produced. A missing httpver versionid stays forbidden; fail-closed "
    "routing never opts the httpver provider in. An independent later poll of the "
    "stored versiondigest keeps the hole falsifiable."
)
