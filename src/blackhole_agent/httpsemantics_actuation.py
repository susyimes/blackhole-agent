"""Next unsaturated diversity-catalog family after RFC 9111 HTTP Caching.

HTTP Caching is proved. Closed-contract leftover harvest used to steal genesis
with ``Mission contract is closed; later genesis can take the next unsaturated
diversity-catalog family.`` After HTTP Caching seals a freshness digest this
slot is that next family: RFC 9110 HTTP Semantics GET/HEAD over a methodid-gated
fieldsection. The protocol hole stays open so later genesis can opt the
httpsemantics provider in and seal a fieldsection digest.
"""

from __future__ import annotations

HTTPSMANTICS_ACTUATION_ID = "capability.httpsemantics-actuation"
HTTPSMANTICS_ACTUATION_DONE_WHEN = (
    f"capability_exists:{HTTPSMANTICS_ACTUATION_ID};"
    f"capability_proved:{HTTPSMANTICS_ACTUATION_ID};"
    "no_skill_route"
)
HTTPSMANTICS_ACTUATION_GOAL = (
    "Repair rfc9110 httpsemantics get/head cycle cannot land over http "
    "httpsemantics methodid: hosted httpsemantics endpoints remain unsupported so a GET then "
    "HEAD methodid handshake cannot land and a sealed fieldsection digest "
    "cannot be produced. A missing httpsemantics methodid stays forbidden; fail-closed "
    "routing never opts the httpsemantics provider in. An independent later poll of the "
    "stored fieldsection keeps the hole falsifiable."
)
