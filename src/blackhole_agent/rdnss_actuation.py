"""Next unsaturated diversity-catalog family after RFC 8028 First-Hop Router Selection.

First-Hop Router Selection by Hosts in a Multi-Prefix Network is proved. Closed-contract leftover
harvest used to steal genesis with ``Mission contract is closed; later genesis can take
the next unsaturated diversity-catalog family.`` After firsthop seals a hopdigest
this slot is that next family: RFC 8106 IPv6 Router Advertisement Options for DNS
Configuration RDNSS/DNSSL over a rdnssid-gated rdnssdigest.
The protocol hole stays open so later genesis can opt the rdnss provider in
and seal a rdnssdigest.
"""

from __future__ import annotations

RDNSS_ACTUATION_ID = "capability.rdnss-actuation"
RDNSS_ACTUATION_DONE_WHEN = (
    f"capability_exists:{RDNSS_ACTUATION_ID};"
    f"capability_proved:{RDNSS_ACTUATION_ID};"
    "no_skill_route"
)
RDNSS_ACTUATION_GOAL = (
    "Repair rfc8106 rdnss rdnss/dnssl cycle cannot land over http "
    "rdnss rdnssid: hosted rdnss endpoints remain unsupported so a RDNSS then "
    "DNSSL rdnssid handshake cannot land and a sealed rdnssdigest "
    "cannot be produced. A missing rdnss rdnssid stays forbidden; fail-closed "
    "routing never opts the rdnss provider in. An independent later poll of the "
    "stored rdnssdigest keeps the hole falsifiable."
)
