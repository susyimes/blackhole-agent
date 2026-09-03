"""Next unsaturated diversity-catalog family after RFC 9114 HTTP/3 lockstep.

HTTP/3 is proved. Closed-contract leftover harvest used to steal genesis
with ``Mission contract is closed; later genesis can take the next unsaturated
diversity-catalog family.`` After HTTP/3 seals a qpack digest this slot is
that next family: RFC 9220 WebTransport CONNECT/SESSION over HTTP/3.
The protocol hole stays open so later genesis can opt the webtransport
provider in and seal a capsule digest.
"""

from __future__ import annotations

WEBTRANSPORT_ACTUATION_ID = "capability.webtransport-actuation"
WEBTRANSPORT_ACTUATION_DONE_WHEN = (
    f"capability_exists:{WEBTRANSPORT_ACTUATION_ID};"
    f"capability_proved:{WEBTRANSPORT_ACTUATION_ID};"
    "no_skill_route"
)
WEBTRANSPORT_ACTUATION_GOAL = (
    "Repair rfc9220 webtransport connect/session cycle cannot land over udp "
    "webtransport sessionid: hosted webtransport endpoints remain unsupported so a CONNECT then "
    "SESSION sessionid handshake cannot land and a sealed capsule digest "
    "cannot be produced. A missing webtransport sessionid stays forbidden; fail-closed "
    "routing never opts the webtransport provider in. An independent later poll of the "
    "stored session capsule keeps the hole falsifiable."
)
