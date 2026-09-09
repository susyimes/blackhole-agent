"""Next unsaturated diversity-catalog family after RFC 4873 SEGMENT/RECOVER.

GMPLS Segment Recovery is proved. Closed-contract leftover harvest used to steal
genesis with ``Mission contract is closed; later genesis can take the next
unsaturated diversity-catalog family.`` After segrec seals a segrecdigest
this slot is that next family: RFC 4874 Exclude Routes
EXCLUDE/ROUTE over an exrouteid-gated exroutedigest.
The protocol hole stays open so later genesis can opt the exroute provider in
and seal an exroutedigest.
"""

from __future__ import annotations

EXROUTE_ACTUATION_ID = "capability.exroute-actuation"
EXROUTE_ACTUATION_DONE_WHEN = (
    f"capability_exists:{EXROUTE_ACTUATION_ID};"
    f"capability_proved:{EXROUTE_ACTUATION_ID};"
    "no_skill_route"
)
EXROUTE_ACTUATION_GOAL = (
    "Repair rfc4874 exroute exclude/route cycle cannot land over http exroute exrouteid: "
    "hosted exroute remain unsupported so an EXCLUDE then ROUTE exrouteid handshake cannot "
    "land and a sealed exroutedigest cannot be produced. A missing exroute exrouteid stays "
    "forbidden; fail-closed routing never opts the exroute provider in. An independent "
    "later poll of the stored exroutedigest keeps the hole falsifiable. EXROUTE sessions "
    "stay fail-closed without an exrouteid-gated exroutedigest."
)
EXROUTE_LEFTOVER = (
    "Later genesis can take RFC 4874 Exclude Routes EXCLUDE/ROUTE over an "
    "exrouteid-gated exroutedigest."
)
