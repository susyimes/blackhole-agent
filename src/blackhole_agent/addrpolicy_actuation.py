"""Next unsaturated diversity-catalog family after RFC 6724 Default Address Selection for IPv6.

Default Address Selection for IPv6 is proved. Closed-contract leftover harvest used to
steal genesis with ``Mission contract is closed; later genesis can take the next
unsaturated diversity-catalog family.`` After addrselect seals a selectdigest
this slot is that next family: RFC 7078 Distributing Address Selection Policy using DHCPv6
POLICY/TABLE over a policyid-gated policydigest.
The protocol hole stays open so later genesis can opt the addrpolicy provider in
and seal a policydigest.
"""

from __future__ import annotations

ADDRPOLICY_ACTUATION_ID = "capability.addrpolicy-actuation"
ADDRPOLICY_ACTUATION_DONE_WHEN = (
    f"capability_exists:{ADDRPOLICY_ACTUATION_ID};"
    f"capability_proved:{ADDRPOLICY_ACTUATION_ID};"
    "no_skill_route"
)
ADDRPOLICY_ACTUATION_GOAL = (
    "Repair rfc7078 addrpolicy policy/table cycle cannot land over http "
    "addrpolicy policyid: hosted addrpolicy endpoints remain unsupported so a POLICY then "
    "TABLE policyid handshake cannot land and a sealed policydigest "
    "cannot be produced. A missing addrpolicy policyid stays forbidden; fail-closed "
    "routing never opts the addrpolicy provider in. An independent later poll of the "
    "stored policydigest keeps the hole falsifiable."
)
