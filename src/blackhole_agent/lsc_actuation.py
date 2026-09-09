"""Next unsaturated diversity-catalog family after RFC 6163 WSON/RWA.

Framework for GMPLS and PCE Control of Wavelength Switched Optical Networks is proved. Closed-contract leftover harvest used to steal
genesis with ``Mission contract is closed; later genesis can take the next
unsaturated diversity-catalog family.`` After wson seals a wsondigest
this slot is that next family: RFC 6205 Generalized Labels for Lambda-Switch-Capable (LSC) Label Switching Routers
LSC/LABEL over an lscid-gated lscdigest.
The protocol hole stays open so later genesis can opt the lsc provider in
and seal a lscdigest.
"""

from __future__ import annotations

LSC_ACTUATION_ID = "capability.lsc-actuation"
LSC_ACTUATION_DONE_WHEN = (
    f"capability_exists:{LSC_ACTUATION_ID};"
    f"capability_proved:{LSC_ACTUATION_ID};"
    "no_skill_route"
)
LSC_ACTUATION_GOAL = (
    "Repair rfc6205 lsc lsc/label cycle cannot land over http lsc lscid: "
    "hosted lsc remain unsupported so a LSC then LABEL lscid handshake cannot "
    "land and a sealed lscdigest cannot be produced. A missing lsc lscid stays "
    "forbidden; fail-closed routing never opts the lsc provider in. An independent "
    "later poll of the stored lscdigest keeps the hole falsifiable. LSC sessions "
    "stay fail-closed without an lscid-gated lscdigest."
)
LSC_LEFTOVER = (
    "Later genesis can take RFC 6205 Generalized Labels for Lambda-Switch-Capable (LSC) Label Switching Routers "
    "LSC/LABEL over an lscid-gated lscdigest."
)
