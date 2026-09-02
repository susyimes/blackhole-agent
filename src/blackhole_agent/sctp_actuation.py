"""Next unsaturated diversity-catalog family after RFC 3711 SRTP lockstep.

SRTP is proved. Closed-contract leftover harvest used to steal genesis with
``Mission contract is closed; later genesis can take the next unsaturated
diversity-catalog family.`` After SRTP seals a roc digest this slot is
that next family: RFC 4960 SCTP INIT/INIT-ACK over UDP.
The protocol hole stays open so later genesis can opt the sctp provider
in and seal a tsn digest.
"""

from __future__ import annotations

SCTP_ACTUATION_ID = "capability.sctp-actuation"
SCTP_ACTUATION_DONE_WHEN = (
    f"capability_exists:{SCTP_ACTUATION_ID};"
    f"capability_proved:{SCTP_ACTUATION_ID};"
    "no_skill_route"
)
SCTP_ACTUATION_GOAL = (
    "Repair rfc4960 sctp init/init-ack cycle cannot land over udp "
    "sctp vtag: hosted sctp endpoints remain unsupported so an INIT then "
    "INIT-ACK vtag handshake cannot land and a sealed tsn digest "
    "cannot be produced. A missing sctp vtag stays forbidden; fail-closed "
    "routing never opts the sctp provider in. An independent later poll of the "
    "stored association tsn keeps the hole falsifiable."
)
