"""Next unsaturated diversity-catalog family after RFC 6266 Content-Disposition.

Content-Disposition is proved. Closed-contract leftover harvest used to steal genesis
with ``Mission contract is closed; later genesis can take the next unsaturated
diversity-catalog family.`` After Content-Disposition seals a dispositiondigest this
slot is that next family: RFC 5988 Web Linking LINK/RELATION over a
relationid-gated relationdigest. The protocol hole stays open so later genesis can opt the
weblinking provider in and seal a relationdigest.
"""

from __future__ import annotations

WEBLINKING_ACTUATION_ID = "capability.weblinking-actuation"
WEBLINKING_ACTUATION_DONE_WHEN = (
    f"capability_exists:{WEBLINKING_ACTUATION_ID};"
    f"capability_proved:{WEBLINKING_ACTUATION_ID};"
    "no_skill_route"
)
WEBLINKING_ACTUATION_GOAL = (
    "Repair rfc5988 weblinking link/relation cycle cannot land over http "
    "weblinking relationid: hosted weblinking endpoints remain unsupported so a LINK then "
    "RELATION relationid handshake cannot land and a sealed relationdigest "
    "cannot be produced. A missing weblinking relationid stays forbidden; fail-closed "
    "routing never opts the weblinking provider in. An independent later poll of the "
    "stored relationdigest keeps the hole falsifiable."
)
