"""Next unsaturated diversity-catalog family after RFC 6147 DNS64/SYNTH.

DNS64 is proved. Closed-contract leftover harvest used to steal
genesis with ``Mission contract is closed; later genesis can take the next
unsaturated diversity-catalog family.`` After dns64 seals a dns64digest
this slot is that next family: RFC 6877 464XLAT Combination of Stateful
and Stateless Translation CLAT/PLAT over a clatid-gated clatdigest.
The protocol hole stays open so later genesis can opt the xlat provider in
and seal a clatdigest.
"""

from __future__ import annotations

XLAT_ACTUATION_ID = "capability.xlat-actuation"
XLAT_ACTUATION_DONE_WHEN = (
    f"capability_exists:{XLAT_ACTUATION_ID};"
    f"capability_proved:{XLAT_ACTUATION_ID};"
    "no_skill_route"
)
XLAT_ACTUATION_GOAL = (
    "Repair rfc6877 xlat clat/plat cycle cannot land over http "
    "xlat clatid: hosted xlat endpoints remain unsupported so a CLAT then "
    "PLAT clatid handshake cannot land and a sealed clatdigest "
    "cannot be produced. A missing xlat clatid stays forbidden; fail-closed "
    "routing never opts the xlat provider in. An independent later poll of the "
    "stored clatdigest keeps the hole falsifiable."
)
