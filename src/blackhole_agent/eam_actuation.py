"""Next unsaturated diversity-catalog family after RFC 7915 TRANSLATE/ICMP.

SIIT is proved. Closed-contract leftover harvest used to steal
genesis with ``Mission contract is closed; later genesis can take the next
unsaturated diversity-catalog family.`` After siit seals a siitdigest
this slot is that next family: RFC 7757 Explicit Address Mappings for
Stateless IP/ICMP Translation EXPLICIT/MAPPING over an eamid-gated eamdigest.
The protocol hole stays open so later genesis can opt the eam provider in
and seal a eamdigest.
"""

from __future__ import annotations

EAM_ACTUATION_ID = "capability.eam-actuation"
EAM_ACTUATION_DONE_WHEN = (
    f"capability_exists:{EAM_ACTUATION_ID};"
    f"capability_proved:{EAM_ACTUATION_ID};"
    "no_skill_route"
)
EAM_ACTUATION_GOAL = (
    "Repair rfc7757 eam explicit/mapping cycle cannot land over http "
    "eam eamid: hosted explicit-address-mapping endpoints remain unsupported "
    "so an EXPLICIT then MAPPING eamid handshake cannot land and a sealed "
    "eamdigest cannot be produced. A missing eam eamid stays forbidden; "
    "fail-closed routing never opts the eam provider in. An independent later "
    "poll of the stored eamdigest keeps the hole falsifiable. Explicit address "
    "mappings stay fail-closed without an eamid-gated eamdigest."
)
