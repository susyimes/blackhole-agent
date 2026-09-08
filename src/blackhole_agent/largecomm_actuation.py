"""Next unsaturated diversity-catalog family after RFC 4360 EXT/TYPE.

BGP Extended Communities is proved. Closed-contract leftover harvest used to steal
genesis with ``Mission contract is closed; later genesis can take the next
unsaturated diversity-catalog family.`` After extcomm seals a extcommdigest
this slot is that next family: RFC 8092 BGP Large Communities Attribute LARGE/PART over a
largecommid-gated largecommdigest.
The protocol hole stays open so later genesis can opt the largecomm provider in
and seal a largecommdigest.
"""

from __future__ import annotations

LARGECOMM_ACTUATION_ID = "capability.largecomm-actuation"
LARGECOMM_ACTUATION_DONE_WHEN = (
    f"capability_exists:{LARGECOMM_ACTUATION_ID};"
    f"capability_proved:{LARGECOMM_ACTUATION_ID};"
    "no_skill_route"
)
LARGECOMM_ACTUATION_GOAL = (
    "Repair rfc8092 largecomm large/part cycle cannot land over http largecomm largecommid: hosted bgp large communities attribute endpoints remain unsupported so a LARGE then PART largecommid handshake cannot land and a sealed largecommdigest cannot be produced. A missing largecomm largecommid stays forbidden; fail-closed routing never opts the largecomm provider in. An independent later poll of the stored largecommdigest keeps the hole falsifiable. BGP Large Communities sessions stay fail-closed without a largecommid-gated largecommdigest."
)
