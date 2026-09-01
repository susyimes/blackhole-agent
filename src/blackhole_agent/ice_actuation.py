"""Next unsaturated diversity-catalog family after RFC 5766 TURN lockstep.

TURN is proved. Closed-contract leftover harvest used to steal genesis with
``Mission contract is closed; later genesis can take the next unsaturated
diversity-catalog family.`` After TURN seals a relay digest this slot is
that next family: RFC 8445 ICE connectivity-check/nominated-pair over UDP.
The protocol hole stays open so later genesis can opt the ice provider
in and seal a foundation digest.
"""

from __future__ import annotations

ICE_ACTUATION_ID = "capability.ice-actuation"
ICE_ACTUATION_DONE_WHEN = (
    f"capability_exists:{ICE_ACTUATION_ID};"
    f"capability_proved:{ICE_ACTUATION_ID};"
    "no_skill_route"
)
ICE_ACTUATION_GOAL = (
    "Repair rfc8445 ice connectivity-check/nominated-pair cycle cannot land over udp "
    "ice: hosted ice agents remain unsupported so a connectivity-check then "
    "nominated-pair Success ufrag handshake cannot land and a sealed foundation digest "
    "cannot be produced. A missing ice ufrag stays forbidden; fail-closed "
    "routing never opts the ice provider in. An independent later poll of the "
    "stored candidate foundation keeps the hole falsifiable."
)
