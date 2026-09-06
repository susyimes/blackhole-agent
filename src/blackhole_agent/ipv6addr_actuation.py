"""Next unsaturated diversity-catalog family after RFC 4193 ULA.

ULA is proved. Closed-contract leftover harvest used to steal genesis with
``Mission contract is closed; later genesis can take the next unsaturated
diversity-catalog family.`` After ULA seals a uladigest this slot is that
next family: RFC 4291 IPv6 Addressing Architecture GLOBAL/UNICAST over an
ipv6addrid-gated ipv6addrdigest.
The protocol hole stays open so later genesis can opt the ipv6addr provider in
and seal a ipv6addrdigest.
"""

from __future__ import annotations

IPV6ADDR_ACTUATION_ID = "capability.ipv6addr-actuation"
IPV6ADDR_ACTUATION_DONE_WHEN = (
    f"capability_exists:{IPV6ADDR_ACTUATION_ID};"
    f"capability_proved:{IPV6ADDR_ACTUATION_ID};"
    "no_skill_route"
)
IPV6ADDR_ACTUATION_GOAL = (
    "Repair rfc4291 ipv6addr global/unicast cycle cannot land over http "
    "ipv6addr ipv6addrid: hosted ipv6addr endpoints remain unsupported so a GLOBAL then "
    "UNICAST ipv6addrid handshake cannot land and a sealed ipv6addrdigest "
    "cannot be produced. A missing ipv6addr ipv6addrid stays forbidden; fail-closed "
    "routing never opts the ipv6addr provider in. An independent later poll of the "
    "stored ipv6addrdigest keeps the hole falsifiable."
)
