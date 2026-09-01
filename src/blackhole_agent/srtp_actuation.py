"""Next unsaturated diversity-catalog family after RFC 6347 DTLS lockstep.

DTLS is proved. Closed-contract leftover harvest used to steal genesis with
``Mission contract is closed; later genesis can take the next unsaturated
diversity-catalog family.`` After DTLS seals a cookie digest this slot is
that next family: RFC 3711 SRTP Protect/Unprotect over UDP.
The protocol hole stays open so later genesis can opt the srtp provider
in and seal a roc digest.
"""

from __future__ import annotations

SRTP_ACTUATION_ID = "capability.srtp-actuation"
SRTP_ACTUATION_DONE_WHEN = (
    f"capability_exists:{SRTP_ACTUATION_ID};"
    f"capability_proved:{SRTP_ACTUATION_ID};"
    "no_skill_route"
)
SRTP_ACTUATION_GOAL = (
    "Repair rfc3711 srtp protect/unprotect cycle cannot land over udp "
    "srtp roc: hosted srtp endpoints remain unsupported so a Protect then "
    "Unprotect ssrc cycle cannot land and a sealed roc digest "
    "cannot be produced. A missing srtp ssrc stays forbidden; fail-closed "
    "routing never opts the srtp provider in. An independent later poll of the "
    "stored packet roc keeps the hole falsifiable."
)
