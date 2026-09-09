"""Next unsaturated diversity-catalog family after RFC 5541 OBJ/FUN.

Encoding of Objective Functions is proved. Closed-contract leftover harvest used to steal
genesis with ``Mission contract is closed; later genesis can take the next
unsaturated diversity-catalog family.`` After objfun seals an objfundest
this slot is that next family: RFC 5557 Global Concurrent Optimization
GCO/SVEC over a gcoid-gated gcodigest.
The protocol hole stays open so later genesis can opt the gco provider in
and seal a gcodigest.
"""

from __future__ import annotations

GCO_ACTUATION_ID = "capability.gco-actuation"
GCO_ACTUATION_DONE_WHEN = (
    f"capability_exists:{GCO_ACTUATION_ID};"
    f"capability_proved:{GCO_ACTUATION_ID};"
    "no_skill_route"
)
GCO_ACTUATION_GOAL = (
    "Repair rfc5557 gco gco/svec cycle cannot land over http gco gcoid: "
    "hosted gco remain unsupported so a GCO then SVEC gcoid handshake cannot "
    "land and a sealed gcodigest cannot be produced. A missing gco gcoid stays "
    "forbidden; fail-closed routing never opts the gco provider in. An independent "
    "later poll of the stored gcodigest keeps the hole falsifiable. GCO sessions "
    "stay fail-closed without a gcoid-gated gcodigest."
)
GCO_LEFTOVER = (
    "Later genesis can take RFC 5557 Global Concurrent Optimization "
    "GCO/SVEC over a gcoid-gated gcodigest."
)
