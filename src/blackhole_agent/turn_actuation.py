"""Next unsaturated diversity-catalog family after RFC 5389 STUN lockstep.

STUN is proved. Closed-contract leftover harvest used to steal genesis with
``Mission contract is closed; later genesis can take the next unsaturated
diversity-catalog family.`` After STUN seals a txid digest this slot is
that next family: RFC 5766 TURN Allocate/Allocation Success over UDP.
The protocol hole stays open so later genesis can opt the turn provider
in and seal a relay digest.
"""

from __future__ import annotations

TURN_ACTUATION_ID = "capability.turn-actuation"
TURN_ACTUATION_DONE_WHEN = (
    f"capability_exists:{TURN_ACTUATION_ID};"
    f"capability_proved:{TURN_ACTUATION_ID};"
    "no_skill_route"
)
TURN_ACTUATION_GOAL = (
    "Repair rfc5766 turn allocate/success cycle cannot land over udp "
    "turn: hosted turn relays remain unsupported so an Allocate then "
    "Allocation Success nonce handshake cannot land and a sealed relay digest "
    "cannot be produced. A missing turn nonce stays forbidden; fail-closed "
    "routing never opts the turn provider in. An independent later poll of the "
    "stored allocation nonce keeps the hole falsifiable."
)
