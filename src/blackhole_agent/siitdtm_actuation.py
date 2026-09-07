"""Next unsaturated diversity-catalog family after RFC 7755 PREFIX/DC.

SIIT-DC is proved. Closed-contract leftover harvest used to steal
genesis with ``Mission contract is closed; later genesis can take the next
unsaturated diversity-catalog family.`` After siitdc seals a siitdcdigest
this slot is that next family: RFC 7756 SIIT-DC Dual Translation Mode
DTM/MODE over a siitdtmid-gated siitdtmdigest.
The protocol hole stays open so later genesis can opt the siitdtm provider in
and seal a siitdtmdigest.
"""

from __future__ import annotations

SIITDTM_ACTUATION_ID = "capability.siitdtm-actuation"
SIITDTM_ACTUATION_DONE_WHEN = (
    f"capability_exists:{SIITDTM_ACTUATION_ID};"
    f"capability_proved:{SIITDTM_ACTUATION_ID};"
    "no_skill_route"
)
SIITDTM_ACTUATION_GOAL = (
    "Repair rfc7756 siitdtm dtm/mode cycle cannot land over http "
    "siitdtm siitdtmid: hosted dual-translation mode endpoints remain unsupported "
    "so a DTM then MODE siitdtmid handshake cannot land and a sealed "
    "siitdtmdigest cannot be produced. A missing siitdtm siitdtmid stays forbidden; "
    "fail-closed routing never opts the siitdtm provider in. An independent later "
    "poll of the stored siitdtmdigest keeps the hole falsifiable. Dual-translation "
    "mode stays fail-closed without a siitdtmid-gated siitdtmdigest."
)
