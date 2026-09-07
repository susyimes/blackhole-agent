"""Next unsaturated diversity-catalog family after RFC 4271 OPEN/UPDATE.

BGP-4 is proved. Closed-contract leftover harvest used to steal
genesis with ``Mission contract is closed; later genesis can take the next
unsaturated diversity-catalog family.`` After bgp4 seals a bgp4digest
this slot is that next family: RFC 2918 Route Refresh Capability for BGP-4 REQUEST/REFRESH over a
rtrefreshid-gated rtrefreshdigest.
The protocol hole stays open so later genesis can opt the rtrefresh provider in
and seal a rtrefreshdigest.
"""

from __future__ import annotations

RTREFRESH_ACTUATION_ID = "capability.rtrefresh-actuation"
RTREFRESH_ACTUATION_DONE_WHEN = (
    f"capability_exists:{RTREFRESH_ACTUATION_ID};"
    f"capability_proved:{RTREFRESH_ACTUATION_ID};"
    "no_skill_route"
)
RTREFRESH_ACTUATION_GOAL = (
    "Repair rfc2918 rtrefresh request/refresh cycle cannot land over http rtrefresh rtrefreshid: hosted route refresh for bgp-4 endpoints remain unsupported so a REQUEST then REFRESH rtrefreshid handshake cannot land and a sealed rtrefreshdigest cannot be produced. A missing rtrefresh rtrefreshid stays forbidden; fail-closed routing never opts the rtrefresh provider in. An independent later poll of the stored rtrefreshdigest keeps the hole falsifiable. Route Refresh sessions stay fail-closed without a rtrefreshid-gated rtrefreshdigest."
)
