"""Next unsaturated diversity-catalog family after RFC 4397 CALL/CONN.

GMPLS ASON is proved. Closed-contract leftover harvest used to steal
genesis with ``Mission contract is closed; later genesis can take the next
unsaturated diversity-catalog family.`` After ason seals an asondigest
this slot is that next family: RFC 4426 GMPLS Recovery NOTIFY/RESTORE
over a grecid-gated grecdigest.
The protocol hole stays open so later genesis can opt the grec provider in
and seal a grecdigest.
"""

from __future__ import annotations

GREC_ACTUATION_ID = "capability.grec-actuation"
GREC_ACTUATION_DONE_WHEN = (
    f"capability_exists:{GREC_ACTUATION_ID};"
    f"capability_proved:{GREC_ACTUATION_ID};"
    "no_skill_route"
)
GREC_ACTUATION_GOAL = (
    "Repair rfc4426 grec notify/restore cycle cannot land over http grec grecid: hosted grec remain unsupported so a NOTIFY then RESTORE grecid handshake cannot land and a sealed grecdigest cannot be produced. A missing grec grecid stays forbidden; fail-closed routing never opts the grec provider in. An independent later poll of the stored grecdigest keeps the hole falsifiable. GREC sessions stay fail-closed without a grecid-gated grecdigest."
)
GREC_LEFTOVER = (
    "Later genesis can take RFC 4426 GMPLS Recovery NOTIFY/RESTORE over a grecid-gated grecdigest."
)
