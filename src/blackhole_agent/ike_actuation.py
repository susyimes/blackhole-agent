"""Next unsaturated diversity-catalog family after RFC 2131 DHCP lockstep.

DHCP is proved. Closed-contract leftover harvest used to steal genesis with
``Mission contract is closed; later genesis can take the next unsaturated
diversity-catalog family.`` After DHCP seals a lease digest this slot is
that next family: RFC 7296 IKE SA_INIT/AUTH over UDP.
The protocol hole stays open so later genesis can opt the ike provider
in and seal a spi digest.
"""

from __future__ import annotations

IKE_ACTUATION_ID = "capability.ike-actuation"
IKE_ACTUATION_DONE_WHEN = (
    f"capability_exists:{IKE_ACTUATION_ID};"
    f"capability_proved:{IKE_ACTUATION_ID};"
    "no_skill_route"
)
IKE_ACTUATION_GOAL = (
    "Repair rfc7296 ike sa-init/auth cycle cannot land over udp "
    "ike: hosted ike tools remain unsupported so an IKE_SA_INIT then IKE_AUTH "
    "spi exchange cannot land and a sealed spi digest cannot be "
    "produced. A missing ike spi stays forbidden; fail-closed routing never "
    "opts the ike provider in. An independent later poll of the stored "
    "initiator spi keeps the hole falsifiable."
)
