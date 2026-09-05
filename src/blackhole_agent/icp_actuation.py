"""Next unsaturated diversity-catalog family after RFC 2227 Simple Hit-Metering.

Simple Hit-Metering is proved. Closed-contract leftover harvest used to steal genesis
with ``Mission contract is closed; later genesis can take the next unsaturated
diversity-catalog family.`` After Simple Hit-Metering seals a
usagedigest this slot is that next family: RFC 2186 Internet Cache Protocol
QUERY/HIT over a queryid-gated icpdigest. The protocol hole
stays open so later genesis can opt the icp provider in and seal a
icpdigest.
"""

from __future__ import annotations

ICP_ACTUATION_ID = "capability.icp-actuation"
ICP_ACTUATION_DONE_WHEN = (
    f"capability_exists:{ICP_ACTUATION_ID};"
    f"capability_proved:{ICP_ACTUATION_ID};"
    "no_skill_route"
)
ICP_ACTUATION_GOAL = (
    "Repair rfc2186 icp query/hit cycle cannot land over http "
    "icp queryid: hosted icp endpoints remain unsupported so a QUERY then "
    "HIT queryid handshake cannot land and a sealed icpdigest "
    "cannot be produced. A missing icp queryid stays forbidden; fail-closed "
    "routing never opts the icp provider in. An independent later poll of the "
    "stored icpdigest keeps the hole falsifiable."
)
