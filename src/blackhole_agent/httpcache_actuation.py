"""Next unsaturated diversity-catalog family after RFC 9113 HTTP/2.

HTTP/2 is proved. Closed-contract leftover harvest used to steal genesis
with ``Mission contract is closed; later genesis can take the next unsaturated
diversity-catalog family.`` After HTTP/2 seals a hpack digest this slot is
that next family: RFC 9111 HTTP Caching STORE/REVALIDATE over a cache
validator. The protocol hole stays open so later genesis can opt the httpcache
provider in and seal a freshness digest.
"""

from __future__ import annotations

HTTPCACHE_ACTUATION_ID = "capability.httpcache-actuation"
HTTPCACHE_ACTUATION_DONE_WHEN = (
    f"capability_exists:{HTTPCACHE_ACTUATION_ID};"
    f"capability_proved:{HTTPCACHE_ACTUATION_ID};"
    "no_skill_route"
)
HTTPCACHE_ACTUATION_GOAL = (
    "Repair rfc9111 httpcache store/revalidate cycle cannot land over http "
    "httpcache cacheid: hosted httpcache endpoints remain unsupported so a STORE then "
    "REVALIDATE cacheid handshake cannot land and a sealed freshness digest "
    "cannot be produced. A missing httpcache cacheid stays forbidden; fail-closed "
    "routing never opts the httpcache provider in. An independent later poll of the "
    "stored cache validator keeps the hole falsifiable."
)
