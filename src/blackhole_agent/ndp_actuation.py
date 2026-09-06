"""Next unsaturated diversity-catalog family after RFC 2710 Multicast Listener Discovery.

MLD is proved. Closed-contract leftover harvest used to steal genesis with
``Mission contract is closed; later genesis can take the next unsaturated
diversity-catalog family.`` After MLD seals an mlddigest this slot is that
next family: RFC 4861 Neighbor Discovery Protocol SOLICIT/ADVERT over an
ndpid-gated ndpdigest.
The protocol hole stays open so later genesis can opt the ndp provider in
and seal an ndpdigest.
"""

from __future__ import annotations

NDP_ACTUATION_ID = "capability.ndp-actuation"
NDP_ACTUATION_DONE_WHEN = (
    f"capability_exists:{NDP_ACTUATION_ID};"
    f"capability_proved:{NDP_ACTUATION_ID};"
    "no_skill_route"
)
NDP_ACTUATION_GOAL = (
    "Repair rfc4861 ndp solicit/advert cycle cannot land over http "
    "ndp ndpid: hosted ndp endpoints remain unsupported so a SOLICIT then "
    "ADVERT ndpid handshake cannot land and a sealed ndpdigest "
    "cannot be produced. A missing ndp ndpid stays forbidden; fail-closed "
    "routing never opts the ndp provider in. An independent later poll of the "
    "stored ndpdigest keeps the hole falsifiable."
)
