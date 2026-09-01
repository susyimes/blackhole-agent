"""Next unsaturated diversity-catalog family after RFC 3261 SIP lockstep.

SIP is proved. Closed-contract leftover harvest used to steal genesis with
``Mission contract is closed; later genesis can take the next unsaturated
diversity-catalog family.`` After SIP seals a callid digest this slot is
that next family: RFC 5389 STUN Binding Request/Success over UDP.
The protocol hole stays open so later genesis can opt the stun provider
in and seal a txid digest.
"""

from __future__ import annotations

STUN_ACTUATION_ID = "capability.stun-actuation"
STUN_ACTUATION_DONE_WHEN = (
    f"capability_exists:{STUN_ACTUATION_ID};"
    f"capability_proved:{STUN_ACTUATION_ID};"
    "no_skill_route"
)
STUN_ACTUATION_GOAL = (
    "Repair rfc5389 stun binding request/success cycle cannot land over udp "
    "stun: hosted stun tools remain unsupported so a Binding Request then "
    "Binding Success txid exchange cannot land and a sealed txid digest cannot "
    "be produced. A missing stun txid stays forbidden; fail-closed routing never "
    "opts the stun provider in. An independent later poll of the stored "
    "transaction txid keeps the hole falsifiable."
)
