"""Next unsaturated diversity-catalog family after RFC 8942 HTTP Client Hints.

Client Hints is proved. Closed-contract leftover harvest used to steal genesis
with ``Mission contract is closed; later genesis can take the next unsaturated
diversity-catalog family.`` After Client Hints seals a hintsdigest this
slot is that next family: RFC 8297 Early Hints LINK/HINT over a
linkid-gated earlydigest. The protocol hole stays open so later genesis can opt the
earlyhints provider in and seal an earlydigest.
"""

from __future__ import annotations

EARLYHINTS_ACTUATION_ID = "capability.earlyhints-actuation"
EARLYHINTS_ACTUATION_DONE_WHEN = (
    f"capability_exists:{EARLYHINTS_ACTUATION_ID};"
    f"capability_proved:{EARLYHINTS_ACTUATION_ID};"
    "no_skill_route"
)
EARLYHINTS_ACTUATION_GOAL = (
    "Repair rfc8297 earlyhints link/hint cycle cannot land over http "
    "earlyhints linkid: hosted earlyhints endpoints remain unsupported so a LINK then "
    "HINT linkid handshake cannot land and a sealed earlydigest "
    "cannot be produced. A missing earlyhints linkid stays forbidden; fail-closed "
    "routing never opts the earlyhints provider in. An independent later poll of the "
    "stored earlydigest keeps the hole falsifiable."
)
