"""Next unsaturated diversity-catalog family after RFC 8445 ICE lockstep.

ICE is proved. Closed-contract leftover harvest used to steal genesis with
``Mission contract is closed; later genesis can take the next unsaturated
diversity-catalog family.`` After ICE seals a foundation digest this slot is
that next family: RFC 6347 DTLS ClientHello/Finished over UDP.
The protocol hole stays open so later genesis can opt the dtls provider
in and seal a cookie digest.
"""

from __future__ import annotations

DTLS_ACTUATION_ID = "capability.dtls-actuation"
DTLS_ACTUATION_DONE_WHEN = (
    f"capability_exists:{DTLS_ACTUATION_ID};"
    f"capability_proved:{DTLS_ACTUATION_ID};"
    "no_skill_route"
)
DTLS_ACTUATION_GOAL = (
    "Repair rfc6347 dtls clienthello/finished cycle cannot land over udp "
    "dtls epoch: hosted dtls endpoints remain unsupported so a ClientHello then "
    "Finished cookie handshake cannot land and a sealed cookie digest "
    "cannot be produced. A missing dtls cookie stays forbidden; fail-closed "
    "routing never opts the dtls provider in. An independent later poll of the "
    "stored handshake cookie keeps the hole falsifiable."
)
