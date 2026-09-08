"""Next unsaturated diversity-catalog family after RFC 2918 REQUEST/REFRESH.

Route Refresh is proved. Closed-contract leftover harvest used to steal
genesis with ``Mission contract is closed; later genesis can take the next
unsaturated diversity-catalog family.`` After rtrefresh seals a rtrefreshdigest
this slot is that next family: RFC 1997 BGP Communities Attribute COMM/ATTR over a
bgpcommid-gated bgpcommdigest.
The protocol hole stays open so later genesis can opt the bgpcomm provider in
and seal a bgpcommdigest.
"""

from __future__ import annotations

BGPCOMM_ACTUATION_ID = "capability.bgpcomm-actuation"
BGPCOMM_ACTUATION_DONE_WHEN = (
    f"capability_exists:{BGPCOMM_ACTUATION_ID};"
    f"capability_proved:{BGPCOMM_ACTUATION_ID};"
    "no_skill_route"
)
BGPCOMM_ACTUATION_GOAL = (
    "Repair rfc1997 bgpcomm comm/attr cycle cannot land over http bgpcomm bgpcommid: hosted bgp communities attribute endpoints remain unsupported so a COMM then ATTR bgpcommid handshake cannot land and a sealed bgpcommdigest cannot be produced. A missing bgpcomm bgpcommid stays forbidden; fail-closed routing never opts the bgpcomm provider in. An independent later poll of the stored bgpcommdigest keeps the hole falsifiable. BGP Communities sessions stay fail-closed without a bgpcommid-gated bgpcommdigest."
)
