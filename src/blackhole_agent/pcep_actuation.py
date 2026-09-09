"""Next unsaturated diversity-catalog family after RFC 5152 COMPUTE/DOMAIN.

Per-Domain Path Computation is proved. Closed-contract leftover harvest used to steal
genesis with ``Mission contract is closed; later genesis can take the next
unsaturated diversity-catalog family.`` After perdom seals a perdomdigest
this slot is that next family: RFC 5440 Path Computation Element Communication
Protocol OPEN/PCREQ over a pcepid-gated pcepdigest.
The protocol hole stays open so later genesis can opt the pcep provider in
and seal a pcepdigest.
"""

from __future__ import annotations

PCEP_ACTUATION_ID = "capability.pcep-actuation"
PCEP_ACTUATION_DONE_WHEN = (
    f"capability_exists:{PCEP_ACTUATION_ID};"
    f"capability_proved:{PCEP_ACTUATION_ID};"
    "no_skill_route"
)
PCEP_ACTUATION_GOAL = (
    "Repair rfc5440 pcep open/pcreq cycle cannot land over http pcep pcepid: "
    "hosted pcep remain unsupported so an OPEN then PCREQ pcepid handshake cannot "
    "land and a sealed pcepdigest cannot be produced. A missing pcep pcepid stays "
    "forbidden; fail-closed routing never opts the pcep provider in. An independent "
    "later poll of the stored pcepdigest keeps the hole falsifiable. PCEP sessions "
    "stay fail-closed without a pcepid-gated pcepdigest."
)
PCEP_LEFTOVER = (
    "Later genesis can take RFC 5440 Path Computation Element Communication Protocol "
    "OPEN/PCREQ over a pcepid-gated pcepdigest."
)
