"""Next unsaturated diversity-catalog family after RFC 8831 Data Channel lockstep.

Data Channel is proved. Closed-contract leftover harvest used to steal genesis
with ``Mission contract is closed; later genesis can take the next unsaturated
diversity-catalog family.`` After Data Channel seals a dcep digest this slot is
that next family: RFC 9000 QUIC INITIAL/HANDSHAKE over UDP.
The protocol hole stays open so later genesis can opt the quic
provider in and seal a pktnum digest.
"""

from __future__ import annotations

QUIC_ACTUATION_ID = "capability.quic-actuation"
QUIC_ACTUATION_DONE_WHEN = (
    f"capability_exists:{QUIC_ACTUATION_ID};"
    f"capability_proved:{QUIC_ACTUATION_ID};"
    "no_skill_route"
)
QUIC_ACTUATION_GOAL = (
    "Repair rfc9000 quic initial/handshake cycle cannot land over udp "
    "quic dcid: hosted quic endpoints remain unsupported so an INITIAL then "
    "HANDSHAKE dcid handshake cannot land and a sealed pktnum digest "
    "cannot be produced. A missing quic dcid stays forbidden; fail-closed "
    "routing never opts the quic provider in. An independent later poll of the "
    "stored packet pktnum keeps the hole falsifiable."
)
