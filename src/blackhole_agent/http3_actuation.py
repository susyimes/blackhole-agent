"""Next unsaturated diversity-catalog family after RFC 9000 QUIC lockstep.

QUIC is proved. Closed-contract leftover harvest used to steal genesis
with ``Mission contract is closed; later genesis can take the next unsaturated
diversity-catalog family.`` After QUIC seals a pktnum digest this slot is
that next family: RFC 9114 HTTP/3 SETTINGS/HEADERS over QUIC.
The protocol hole stays open so later genesis can opt the http3
provider in and seal a qpack digest.
"""

from __future__ import annotations

HTTP3_ACTUATION_ID = "capability.http3-actuation"
HTTP3_ACTUATION_DONE_WHEN = (
    f"capability_exists:{HTTP3_ACTUATION_ID};"
    f"capability_proved:{HTTP3_ACTUATION_ID};"
    "no_skill_route"
)
HTTP3_ACTUATION_GOAL = (
    "Repair rfc9114 http3 settings/headers cycle cannot land over udp "
    "http3 streamid: hosted http3 endpoints remain unsupported so a SETTINGS then "
    "HEADERS streamid handshake cannot land and a sealed qpack digest "
    "cannot be produced. A missing http3 streamid stays forbidden; fail-closed "
    "routing never opts the http3 provider in. An independent later poll of the "
    "stored stream qpack keeps the hole falsifiable."
)
