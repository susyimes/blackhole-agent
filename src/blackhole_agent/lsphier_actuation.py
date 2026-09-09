"""Next unsaturated diversity-catalog family after RFC 4204 CONFIG/HELLO.

LMP is proved. Closed-contract leftover harvest used to steal
genesis with ``Mission contract is closed; later genesis can take the next
unsaturated diversity-catalog family.`` After lmp seals a lmpdigest
this slot is that next family: RFC 4206 LSP HIERARCHY FA/HIERARCHY
over an lsphierid-gated lsphierdigest.
The protocol hole stays open so later genesis can opt the lsphier provider in
and seal a lsphierdigest.
"""

from __future__ import annotations

LSPHIER_ACTUATION_ID = "capability.lsphier-actuation"
LSPHIER_ACTUATION_DONE_WHEN = (
    f"capability_exists:{LSPHIER_ACTUATION_ID};"
    f"capability_proved:{LSPHIER_ACTUATION_ID};"
    "no_skill_route"
)
LSPHIER_ACTUATION_GOAL = (
    "Repair rfc4206 lsphier fa/hierarchy cycle cannot land over http lsphier lsphierid: hosted lsphier remain unsupported so a FA then HIERARCHY lsphierid handshake cannot land and a sealed lsphierdigest cannot be produced. A missing lsphier lsphierid stays forbidden; fail-closed routing never opts the lsphier provider in. An independent later poll of the stored lsphierdigest keeps the hole falsifiable. LSP Hierarchy sessions stay fail-closed without an lsphierid-gated lsphierdigest."
)
LSPHIER_LEFTOVER = (
    "Later genesis can take RFC 4206 LSP HIERARCHY FA/HIERARCHY over an lsphierid-gated lsphierdigest."
)
