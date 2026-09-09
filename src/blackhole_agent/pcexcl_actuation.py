"""Next unsaturated diversity-catalog family after RFC 5520 PATH/KEY.

Path-Key-Based Mechanism is proved. Closed-contract leftover harvest used to steal
genesis with ``Mission contract is closed; later genesis can take the next
unsaturated diversity-catalog family.`` After pathkey seals a pathkeydigest
this slot is that next family: RFC 5521 PCE Route Exclusions
EXCLUDE/XRO over a pcexclid-gated pcexcldigest.
The protocol hole stays open so later genesis can opt the pcexcl provider in
and seal a pcexcldigest.
"""

from __future__ import annotations

PCEXCL_ACTUATION_ID = "capability.pcexcl-actuation"
PCEXCL_ACTUATION_DONE_WHEN = (
    f"capability_exists:{PCEXCL_ACTUATION_ID};"
    f"capability_proved:{PCEXCL_ACTUATION_ID};"
    "no_skill_route"
)
PCEXCL_ACTUATION_GOAL = (
    "Repair rfc5521 pcexcl exclude/xro cycle cannot land over http pcexcl pcexclid: "
    "hosted pcexcl remain unsupported so an EXCLUDE then XRO pcexclid handshake cannot "
    "land and a sealed pcexcldigest cannot be produced. A missing pcexcl pcexclid stays "
    "forbidden; fail-closed routing never opts the pcexcl provider in. An independent "
    "later poll of the stored pcexcldigest keeps the hole falsifiable. PCEXCL sessions "
    "stay fail-closed without a pcexclid-gated pcexcldigest."
)
PCEXCL_LEFTOVER = (
    "Later genesis can take RFC 5521 PCE Route Exclusions "
    "EXCLUDE/XRO over a pcexclid-gated pcexcldigest."
)
