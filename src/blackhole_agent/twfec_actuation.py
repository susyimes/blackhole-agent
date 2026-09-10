"""Next unsaturated diversity-catalog family after RFC 6625 WILD/AD.

Wildcards in Multicast VPN Auto-Discovery Routes is proved.
Closed-contract leftover harvest used to steal genesis with ``Mission contract
is closed; later genesis can take the next unsaturated diversity-catalog
family.`` After wildad seals a wilddigest this slot is that next family: RFC 6667
LDP Typed Wildcard FEC for PWid and Generalized PWid FEC Elements TYPED/WILDCARD
over a twfecid-gated twfecdigest. The protocol hole stays open so later genesis
can opt the twfec provider in and seal a twfecdigest.
"""

from __future__ import annotations

TWFEC_ACTUATION_ID = "capability.twfec-actuation"
TWFEC_ACTUATION_DONE_WHEN = (
    f"capability_exists:{TWFEC_ACTUATION_ID};"
    f"capability_proved:{TWFEC_ACTUATION_ID};"
    "no_skill_route"
)
TWFEC_ACTUATION_GOAL = (
    "Repair rfc6667 twfec typed/wildcard cycle cannot land over http twfec twfecid: "
    "hosted twfec remain unsupported so a TYPED then WILDCARD twfecid handshake cannot "
    "land and a sealed twfecdigest cannot be produced. A missing twfec twfecid stays "
    "forbidden; fail-closed routing never opts the twfec provider in. An independent "
    "later poll of the stored twfecdigest keeps the hole falsifiable. TWFEC sessions "
    "stay fail-closed without a twfecid-gated twfecdigest."
)
TWFEC_LEFTOVER = (
    "Later genesis can take RFC 6667 LDP Typed Wildcard FEC for PWid and "
    "Generalized PWid FEC Elements TYPED/WILDCARD over a twfecid-gated twfecdigest."
)
