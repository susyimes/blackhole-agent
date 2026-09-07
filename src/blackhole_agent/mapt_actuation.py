"""Next unsaturated diversity-catalog family after RFC 7597 CE/BR.

MAP-E is proved. Closed-contract leftover harvest used to steal
genesis with ``Mission contract is closed; later genesis can take the next
unsaturated diversity-catalog family.`` After mape seals a mapedigest
this slot is that next family: RFC 7599 Mapping of Address and Port using
Translation (MAP-T) DMR/EA over a maptid-gated maptdigest. The protocol
hole stays open so later genesis can opt the mapt provider in and seal a
maptdigest.
"""

from __future__ import annotations

MAPT_ACTUATION_ID = "capability.mapt-actuation"
MAPT_ACTUATION_DONE_WHEN = (
    f"capability_exists:{MAPT_ACTUATION_ID};"
    f"capability_proved:{MAPT_ACTUATION_ID};"
    "no_skill_route"
)
MAPT_ACTUATION_GOAL = (
    "Repair rfc7599 mapt dmr/ea cycle cannot land over http "
    "mapt maptid: hosted mapt endpoints remain unsupported so a DMR then "
    "EA maptid handshake cannot land and a sealed maptdigest "
    "cannot be produced. A missing mapt maptid stays forbidden; fail-closed "
    "routing never opts the mapt provider in. An independent later poll of the "
    "stored maptdigest keeps the hole falsifiable."
)
