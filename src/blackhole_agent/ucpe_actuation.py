"""Next unsaturated diversity-catalog family after RFC 7598 RULE/PORTPARAMS.

S46 is proved. Closed-contract leftover harvest used to steal
genesis with ``Mission contract is closed; later genesis can take the next
unsaturated diversity-catalog family.`` After s46 seals a s46digest
this slot is that next family: RFC 8026 Unified IPv4-in-IPv6 Softwire
Customer Premises Equipment CONTAINER/PROVISION over a ucpeid-gated
ucpedigest. The protocol hole stays open so later genesis can opt the ucpe
provider in and seal a ucpedigest.
"""

from __future__ import annotations

UCPE_ACTUATION_ID = "capability.ucpe-actuation"
UCPE_ACTUATION_DONE_WHEN = (
    f"capability_exists:{UCPE_ACTUATION_ID};"
    f"capability_proved:{UCPE_ACTUATION_ID};"
    "no_skill_route"
)
UCPE_ACTUATION_GOAL = (
    "Repair rfc8026 ucpe container/provision cycle cannot land over http "
    "ucpe ucpeid: hosted unified customer-premises endpoints remain unsupported "
    "so a CONTAINER then PROVISION ucpeid handshake cannot land and a sealed "
    "ucpedigest cannot be produced. A missing ucpe ucpeid stays forbidden; "
    "fail-closed routing never opts the ucpe provider in. An independent later "
    "poll of the stored ucpedigest keeps the hole falsifiable. Unified CPE "
    "provisioning-solution stays fail-closed without a ucpeid-gated ucpedigest."
)
