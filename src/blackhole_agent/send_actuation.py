"""Next unsaturated diversity-catalog family after RFC 3972 CGA.

CGA is proved. Closed-contract leftover harvest used to steal genesis with
``Mission contract is closed; later genesis can take the next unsaturated
diversity-catalog family.`` After CGA seals a cgadigest this slot is that
next family: RFC 3971 SEcure Neighbor Discovery CPS/CPA over a
sendid-gated senddigest.
The protocol hole stays open so later genesis can opt the send provider in
and seal a senddigest.
"""

from __future__ import annotations

SEND_ACTUATION_ID = "capability.send-actuation"
SEND_ACTUATION_DONE_WHEN = (
    f"capability_exists:{SEND_ACTUATION_ID};"
    f"capability_proved:{SEND_ACTUATION_ID};"
    "no_skill_route"
)
SEND_ACTUATION_GOAL = (
    "Repair rfc3971 send cps/cpa cycle cannot land over http "
    "send sendid: hosted send endpoints remain unsupported so a CPS then "
    "CPA sendid handshake cannot land and a sealed senddigest "
    "cannot be produced. A missing send sendid stays forbidden; fail-closed "
    "routing never opts the send provider in. An independent later poll of the "
    "stored senddigest keeps the hole falsifiable."
)
