"""Next unsaturated diversity-catalog family after RFC 8215 LUP/NSL.

LUPREFIX is proved. Closed-contract leftover harvest used to steal
genesis with ``Mission contract is closed; later genesis can take the next
unsaturated diversity-catalog family.`` After luprefix seals a luprefixdigest
this slot is that next family: RFC 5969 IPv6 Rapid Deployment on IPv4
Infrastructures 6RD/DELEG over a sixrdid-gated sixrddigest.
The protocol hole stays open so later genesis can opt the sixrd provider in
and seal a sixrddigest.
"""

from __future__ import annotations

SIXRD_ACTUATION_ID = "capability.sixrd-actuation"
SIXRD_ACTUATION_DONE_WHEN = (
    f"capability_exists:{SIXRD_ACTUATION_ID};"
    f"capability_proved:{SIXRD_ACTUATION_ID};"
    "no_skill_route"
)
SIXRD_ACTUATION_GOAL = (
    "Repair rfc5969 sixrd 6rd/deleg cycle cannot land over http "
    "sixrd sixrdid: hosted ipv6 rapid deployment endpoints remain unsupported "
    "so a 6RD then DELEG sixrdid handshake cannot land and a sealed "
    "sixrddigest cannot be produced. A missing sixrd sixrdid stays forbidden; "
    "fail-closed routing never opts the sixrd provider in. An independent later "
    "poll of the stored sixrddigest keeps the hole falsifiable. IPv6 rapid "
    "deployment delegated prefixes stay fail-closed without a sixrdid-gated "
    "sixrddigest."
)
