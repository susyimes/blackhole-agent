"""Next unsaturated diversity-catalog family after RFC 6146 NAT64/SESSION.

Stateful NAT64 is proved. Closed-contract leftover harvest used to steal
genesis with ``Mission contract is closed; later genesis can take the next
unsaturated diversity-catalog family.`` After nat64 seals a nat64digest
this slot is that next family: RFC 6147 DNS Extensions for Network Address
Translation from IPv6 Clients to IPv4 Servers DNS64/SYNTH over a
dns64id-gated dns64digest.
The protocol hole stays open so later genesis can opt the dns64 provider in
and seal a dns64digest.
"""

from __future__ import annotations

DNS64_ACTUATION_ID = "capability.dns64-actuation"
DNS64_ACTUATION_DONE_WHEN = (
    f"capability_exists:{DNS64_ACTUATION_ID};"
    f"capability_proved:{DNS64_ACTUATION_ID};"
    "no_skill_route"
)
DNS64_ACTUATION_GOAL = (
    "Repair rfc6147 dns64 dns64/synth cycle cannot land over http "
    "dns64 dns64id: hosted dns64 endpoints remain unsupported so a DNS64 then "
    "SYNTH dns64id handshake cannot land and a sealed dns64digest "
    "cannot be produced. A missing dns64 dns64id stays forbidden; fail-closed "
    "routing never opts the dns64 provider in. An independent later poll of the "
    "stored dns64digest keeps the hole falsifiable."
)
