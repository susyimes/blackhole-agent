"""Next unsaturated diversity-catalog family after RFC 6333 B4/AFTR.

DS-Lite is proved. Closed-contract leftover harvest used to steal
genesis with ``Mission contract is closed; later genesis can take the next
unsaturated diversity-catalog family.`` After dslite seals a dslitedigest
this slot is that next family: RFC 7596 Lightweight 4over6 An Extension
to the Dual-Stack Lite Architecture BINDING/PORTSET over a lw4o6id-gated
lw4o6digest. The protocol hole stays open so later genesis can opt the
lw4o6 provider in and seal a lw4o6digest.
"""

from __future__ import annotations

LW4O6_ACTUATION_ID = "capability.lw4o6-actuation"
LW4O6_ACTUATION_DONE_WHEN = (
    f"capability_exists:{LW4O6_ACTUATION_ID};"
    f"capability_proved:{LW4O6_ACTUATION_ID};"
    "no_skill_route"
)
LW4O6_ACTUATION_GOAL = (
    "Repair rfc7596 lw4o6 binding/portset cycle cannot land over http "
    "lw4o6 lw4o6id: hosted lw4o6 endpoints remain unsupported so a BINDING then "
    "PORTSET lw4o6id handshake cannot land and a sealed lw4o6digest "
    "cannot be produced. A missing lw4o6 lw4o6id stays forbidden; fail-closed "
    "routing never opts the lw4o6 provider in. An independent later poll of the "
    "stored lw4o6digest keeps the hole falsifiable."
)
