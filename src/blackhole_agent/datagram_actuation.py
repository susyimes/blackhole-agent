"""Next unsaturated diversity-catalog family after RFC 9220 WebTransport lockstep.

WebTransport is proved. Closed-contract leftover harvest used to steal genesis
with ``Mission contract is closed; later genesis can take the next unsaturated
diversity-catalog family.`` After WebTransport seals a capsule digest this slot is
that next family: RFC 9221 QUIC DATAGRAM SEND/ECHO over UDP.
The protocol hole stays open so later genesis can opt the datagram
provider in and seal a contextid digest.
"""

from __future__ import annotations

DATAGRAM_ACTUATION_ID = "capability.datagram-actuation"
DATAGRAM_ACTUATION_DONE_WHEN = (
    f"capability_exists:{DATAGRAM_ACTUATION_ID};"
    f"capability_proved:{DATAGRAM_ACTUATION_ID};"
    "no_skill_route"
)
DATAGRAM_ACTUATION_GOAL = (
    "Repair rfc9221 datagram send/echo cycle cannot land over udp "
    "datagram flowid: hosted datagram endpoints remain unsupported so a SEND then "
    "ECHO flowid handshake cannot land and a sealed contextid digest "
    "cannot be produced. A missing datagram flowid stays forbidden; fail-closed "
    "routing never opts the datagram provider in. An independent later poll of the "
    "stored flow contextid keeps the hole falsifiable."
)
