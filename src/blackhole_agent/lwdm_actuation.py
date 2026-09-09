"""Next unsaturated diversity-catalog family after RFC 4208 UNIC/UNIN.

GMPLS UNI is proved. Closed-contract leftover harvest used to steal
genesis with ``Mission contract is closed; later genesis can take the next
unsaturated diversity-catalog family.`` After guni seals a gunidigest
this slot is that next family: RFC 4209 LMP-WDM VERIFY/TRACE
over a lwdmid-gated lwdmdigest.
The protocol hole stays open so later genesis can opt the lwdm provider in
and seal a lwdmdigest.
"""

from __future__ import annotations

LWDM_ACTUATION_ID = "capability.lwdm-actuation"
LWDM_ACTUATION_DONE_WHEN = (
    f"capability_exists:{LWDM_ACTUATION_ID};"
    f"capability_proved:{LWDM_ACTUATION_ID};"
    "no_skill_route"
)
LWDM_ACTUATION_GOAL = (
    "Repair rfc4209 lwdm verify/trace cycle cannot land over http lwdm lwdmid: hosted lwdm remain unsupported so a VERIFY then TRACE lwdmid handshake cannot land and a sealed lwdmdigest cannot be produced. A missing lwdm lwdmid stays forbidden; fail-closed routing never opts the lwdm provider in. An independent later poll of the stored lwdmdigest keeps the hole falsifiable. LMP-WDM sessions stay fail-closed without a lwdmid-gated lwdmdigest."
)
LWDM_LEFTOVER = (
    "Later genesis can take RFC 4209 LMP-WDM VERIFY/TRACE over a lwdmid-gated lwdmdigest."
)
