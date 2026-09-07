"""Next unsaturated diversity-catalog family after RFC 7596 BINDING/PORTSET.

Lightweight 4over6 is proved. Closed-contract leftover harvest used to steal
genesis with ``Mission contract is closed; later genesis can take the next
unsaturated diversity-catalog family.`` After lw4o6 seals a lw4o6digest
this slot is that next family: RFC 7597 Mapping of Address and Port with
Encapsulation (MAP-E) CE/BR over a mapeid-gated mapedigest. The protocol
hole stays open so later genesis can opt the mape provider in and seal a
mapedigest.
"""

from __future__ import annotations

MAPE_ACTUATION_ID = "capability.mape-actuation"
MAPE_ACTUATION_DONE_WHEN = (
    f"capability_exists:{MAPE_ACTUATION_ID};"
    f"capability_proved:{MAPE_ACTUATION_ID};"
    "no_skill_route"
)
MAPE_ACTUATION_GOAL = (
    "Repair rfc7597 mape ce/br cycle cannot land over http "
    "mape mapeid: hosted mape endpoints remain unsupported so a CE then "
    "BR mapeid handshake cannot land and a sealed mapedigest "
    "cannot be produced. A missing mape mapeid stays forbidden; fail-closed "
    "routing never opts the mape provider in. An independent later poll of the "
    "stored mapedigest keeps the hole falsifiable."
)
