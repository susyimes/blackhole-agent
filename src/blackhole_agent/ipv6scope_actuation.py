"""Next unsaturated diversity-catalog family after RFC 4291 IPv6 Addressing Architecture.

IPv6 Addressing Architecture is proved. Closed-contract leftover harvest used to
steal genesis with ``Mission contract is closed; later genesis can take the next
unsaturated diversity-catalog family.`` After ipv6addr seals an ipv6addrdigest
this slot is that next family: RFC 4007 IPv6 Scoped Address Architecture
SCOPE/ZONE over a scopeid-gated scopedigest.
The protocol hole stays open so later genesis can opt the ipv6scope provider in
and seal a scopedigest.
"""

from __future__ import annotations

IPV6SCOPE_ACTUATION_ID = "capability.ipv6scope-actuation"
IPV6SCOPE_ACTUATION_DONE_WHEN = (
    f"capability_exists:{IPV6SCOPE_ACTUATION_ID};"
    f"capability_proved:{IPV6SCOPE_ACTUATION_ID};"
    "no_skill_route"
)
IPV6SCOPE_ACTUATION_GOAL = (
    "Repair rfc4007 ipv6scope scope/zone cycle cannot land over http "
    "ipv6scope scopeid: hosted ipv6scope endpoints remain unsupported so a SCOPE then "
    "ZONE scopeid handshake cannot land and a sealed scopedigest "
    "cannot be produced. A missing ipv6scope scopeid stays forbidden; fail-closed "
    "routing never opts the ipv6scope provider in. An independent later poll of the "
    "stored scopedigest keeps the hole falsifiable."
)
