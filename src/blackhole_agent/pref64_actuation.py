"""Next unsaturated diversity-catalog family after RFC 8106 RDNSS/DNSSL.

IPv6 Router Advertisement Options for DNS Configuration is proved. Closed-contract leftover
harvest used to steal genesis with ``Mission contract is closed; later genesis can take
the next unsaturated diversity-catalog family.`` After rdnss seals a rdnssdigest
this slot is that next family: RFC 8781 Discovering PREF64 in Router Advertisements
PREF64/PREFIX over a pref64id-gated pref64digest.
The protocol hole stays open so later genesis can opt the pref64 provider in
and seal a pref64digest.
"""

from __future__ import annotations

PREF64_ACTUATION_ID = "capability.pref64-actuation"
PREF64_ACTUATION_DONE_WHEN = (
    f"capability_exists:{PREF64_ACTUATION_ID};"
    f"capability_proved:{PREF64_ACTUATION_ID};"
    "no_skill_route"
)
PREF64_ACTUATION_GOAL = (
    "Repair rfc8781 pref64 pref64/prefix cycle cannot land over http "
    "pref64 pref64id: hosted pref64 endpoints remain unsupported so a PREF64 then "
    "PREFIX pref64id handshake cannot land and a sealed pref64digest "
    "cannot be produced. A missing pref64 pref64id stays forbidden; fail-closed "
    "routing never opts the pref64 provider in. An independent later poll of the "
    "stored pref64digest keeps the hole falsifiable."
)
