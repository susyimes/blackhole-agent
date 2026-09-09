"""Next unsaturated diversity-catalog family after RFC 5521 EXCLUDE/XRO.

PCE Route Exclusions is proved. Closed-contract leftover harvest used to steal
genesis with ``Mission contract is closed; later genesis can take the next
unsaturated diversity-catalog family.`` After pcexcl seals a pcexcldigest
this slot is that next family: RFC 5541 Encoding of Objective Functions
OBJ/FUN over an objfunid-gated objfundest.
The protocol hole stays open so later genesis can opt the objfun provider in
and seal an objfundest.
"""

from __future__ import annotations

OBJFUN_ACTUATION_ID = "capability.objfun-actuation"
OBJFUN_ACTUATION_DONE_WHEN = (
    f"capability_exists:{OBJFUN_ACTUATION_ID};"
    f"capability_proved:{OBJFUN_ACTUATION_ID};"
    "no_skill_route"
)
OBJFUN_ACTUATION_GOAL = (
    "Repair rfc5541 objfun obj/fun cycle cannot land over http objfun objfunid: "
    "hosted objfun remain unsupported so an OBJ then FUN objfunid handshake cannot "
    "land and a sealed objfundest cannot be produced. A missing objfun objfunid stays "
    "forbidden; fail-closed routing never opts the objfun provider in. An independent "
    "later poll of the stored objfundest keeps the hole falsifiable. OBJFUN sessions "
    "stay fail-closed without an objfunid-gated objfundest."
)
OBJFUN_LEFTOVER = (
    "Later genesis can take RFC 5541 Encoding of Objective Functions "
    "OBJ/FUN over an objfunid-gated objfundest."
)
