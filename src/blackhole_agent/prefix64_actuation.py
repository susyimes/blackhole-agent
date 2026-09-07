"""Next unsaturated diversity-catalog family after RFC 8114 ASM/SSM.

M46 is proved. Closed-contract leftover harvest used to steal
genesis with ``Mission contract is closed; later genesis can take the next
unsaturated diversity-catalog family.`` After m46 seals a m46digest
this slot is that next family: RFC 8115 DHCPv6 Option for IPv4-Embedded
Multicast and Unicast IPv6 Prefixes PREFIX/EMBED over a prefix64id-gated
prefix64digest. The protocol hole stays open so later genesis can opt the
prefix64 provider in and seal a prefix64digest.
"""

from __future__ import annotations

PREFIX64_ACTUATION_ID = "capability.prefix64-actuation"
PREFIX64_ACTUATION_DONE_WHEN = (
    f"capability_exists:{PREFIX64_ACTUATION_ID};"
    f"capability_proved:{PREFIX64_ACTUATION_ID};"
    "no_skill_route"
)
PREFIX64_ACTUATION_GOAL = (
    "Repair rfc8115 prefix64 prefix/embed cycle cannot land over http "
    "prefix64 prefix64id: hosted ipv4-embedded multicast-and-unicast ipv6-prefix "
    "endpoints remain unsupported so a PREFIX then EMBED prefix64id handshake "
    "cannot land and a sealed prefix64digest cannot be produced. A missing "
    "prefix64 prefix64id stays forbidden; fail-closed routing never opts the "
    "prefix64 provider in. An independent later poll of the stored prefix64digest "
    "keeps the hole falsifiable. DHCPv6 multicast-prefix delivery stays "
    "fail-closed without a prefix64id-gated prefix64digest."
)
