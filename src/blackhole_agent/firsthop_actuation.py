"""Next unsaturated diversity-catalog family after RFC 7078 Address Selection Policy.

Distributing Address Selection Policy using DHCPv6 is proved. Closed-contract leftover
harvest used to steal genesis with ``Mission contract is closed; later genesis can take
the next unsaturated diversity-catalog family.`` After addrpolicy seals a policydigest
this slot is that next family: RFC 8028 First-Hop Router Selection by Hosts in a
Multi-Prefix Network FIRST/HOP over a hopid-gated hopdigest.
The protocol hole stays open so later genesis can opt the firsthop provider in
and seal a hopdigest.
"""

from __future__ import annotations

FIRSTHOP_ACTUATION_ID = "capability.firsthop-actuation"
FIRSTHOP_ACTUATION_DONE_WHEN = (
    f"capability_exists:{FIRSTHOP_ACTUATION_ID};"
    f"capability_proved:{FIRSTHOP_ACTUATION_ID};"
    "no_skill_route"
)
FIRSTHOP_ACTUATION_GOAL = (
    "Repair rfc8028 firsthop first/hop cycle cannot land over http "
    "firsthop hopid: hosted firsthop endpoints remain unsupported so a FIRST then "
    "HOP hopid handshake cannot land and a sealed hopdigest "
    "cannot be produced. A missing firsthop hopid stays forbidden; fail-closed "
    "routing never opts the firsthop provider in. An independent later poll of the "
    "stored hopdigest keeps the hole falsifiable."
)
