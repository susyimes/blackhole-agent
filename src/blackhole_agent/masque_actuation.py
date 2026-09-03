"""Next unsaturated diversity-catalog family after RFC 9221 QUIC DATAGRAM lockstep.

QUIC DATAGRAM is proved. Closed-contract leftover harvest used to steal genesis
with ``Mission contract is closed; later genesis can take the next unsaturated
diversity-catalog family.`` After DATAGRAM seals a contextid digest this slot is
that next family: RFC 9298 MASQUE CONNECT-UDP BIND/PROXY over HTTP.
The protocol hole stays open so later genesis can opt the masque
provider in and seal an authority digest.
"""

from __future__ import annotations

MASQUE_ACTUATION_ID = "capability.masque-actuation"
MASQUE_ACTUATION_DONE_WHEN = (
    f"capability_exists:{MASQUE_ACTUATION_ID};"
    f"capability_proved:{MASQUE_ACTUATION_ID};"
    "no_skill_route"
)
MASQUE_ACTUATION_GOAL = (
    "Repair rfc9298 masque bind/proxy cycle cannot land over http "
    "masque targetid: hosted masque endpoints remain unsupported so a BIND then "
    "PROXY targetid handshake cannot land and a sealed authority digest "
    "cannot be produced. A missing masque targetid stays forbidden; fail-closed "
    "routing never opts the masque provider in. An independent later poll of the "
    "stored proxy authority keeps the hole falsifiable."
)
