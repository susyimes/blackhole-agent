"""Next unsaturated diversity-catalog family after RFC 7296 IKE lockstep.

IKE is proved. Closed-contract leftover harvest used to steal genesis with
``Mission contract is closed; later genesis can take the next unsaturated
diversity-catalog family.`` After IKE seals a spi digest this slot is
that next family: RFC 3261 SIP INVITE/200 over UDP.
The protocol hole stays open so later genesis can opt the sip provider
in and seal a callid digest.
"""

from __future__ import annotations

SIP_ACTUATION_ID = "capability.sip-actuation"
SIP_ACTUATION_DONE_WHEN = (
    f"capability_exists:{SIP_ACTUATION_ID};"
    f"capability_proved:{SIP_ACTUATION_ID};"
    "no_skill_route"
)
SIP_ACTUATION_GOAL = (
    "Repair rfc3261 sip invite/200 cycle cannot land over udp "
    "sip: hosted sip tools remain unsupported so an INVITE then 200 OK "
    "callid exchange cannot land and a sealed callid digest cannot be "
    "produced. A missing sip callid stays forbidden; fail-closed routing never "
    "opts the sip provider in. An independent later poll of the stored "
    "dialog callid keeps the hole falsifiable."
)
