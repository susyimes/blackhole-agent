"""Next unsaturated diversity-catalog family after RFC 826 Address Resolution Protocol.

ARP is proved. Closed-contract leftover harvest used to steal genesis with
``Mission contract is closed; later genesis can take the next unsaturated
diversity-catalog family.`` After ARP seals a arpdigest this slot is that
next family: RFC 903 Reverse Address Resolution Protocol REVERSE/REPLY over an
rarpid-gated rarpdigest.
The protocol hole stays open so later genesis can opt the rarp provider in
and seal a rarpdigest.
"""

from __future__ import annotations

RARP_ACTUATION_ID = "capability.rarp-actuation"
RARP_ACTUATION_DONE_WHEN = (
    f"capability_exists:{RARP_ACTUATION_ID};"
    f"capability_proved:{RARP_ACTUATION_ID};"
    "no_skill_route"
)
RARP_ACTUATION_GOAL = (
    "Repair rfc903 rarp reverse/reply cycle cannot land over http "
    "rarp rarpid: hosted rarp endpoints remain unsupported so a REVERSE then "
    "REPLY rarpid handshake cannot land and a sealed rarpdigest "
    "cannot be produced. A missing rarp rarpid stays forbidden; fail-closed "
    "routing never opts the rarp provider in. An independent later poll of the "
    "stored rarpdigest keeps the hole falsifiable."
)
