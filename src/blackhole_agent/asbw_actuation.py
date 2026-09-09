"""Next unsaturated diversity-catalog family after RFC 6205 LSC/LABEL.

Generalized Labels for Lambda-Switch-Capable (LSC) Label Switching Routers is proved. Closed-contract leftover harvest used to steal
genesis with ``Mission contract is closed; later genesis can take the next
unsaturated diversity-catalog family.`` After lsc seals a lscdigest
this slot is that next family: RFC 6387 GMPLS Asymmetric Bandwidth Bidirectional Label Switched Paths (LSPs)
ASYM/BIDIR over an asbwid-gated asbwdigest.
The protocol hole stays open so later genesis can opt the asbw provider in
and seal a asbwdigest.
"""

from __future__ import annotations

ASBW_ACTUATION_ID = "capability.asbw-actuation"
ASBW_ACTUATION_DONE_WHEN = (
    f"capability_exists:{ASBW_ACTUATION_ID};"
    f"capability_proved:{ASBW_ACTUATION_ID};"
    "no_skill_route"
)
ASBW_ACTUATION_GOAL = (
    "Repair rfc6387 asbw asym/bidir cycle cannot land over http asbw asbwid: "
    "hosted asbw remain unsupported so a ASYM then BIDIR asbwid handshake cannot "
    "land and a sealed asbwdigest cannot be produced. A missing asbw asbwid stays "
    "forbidden; fail-closed routing never opts the asbw provider in. An independent "
    "later poll of the stored asbwdigest keeps the hole falsifiable. ASBW sessions "
    "stay fail-closed without an asbwid-gated asbwdigest."
)
ASBW_LEFTOVER = (
    "Later genesis can take RFC 6387 GMPLS Asymmetric Bandwidth Bidirectional Label Switched Paths (LSPs) "
    "ASYM/BIDIR over an asbwid-gated asbwdigest."
)
