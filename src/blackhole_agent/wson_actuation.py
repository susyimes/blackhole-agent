"""Next unsaturated diversity-catalog family after RFC 6006 P2MP/ENDPOINTS.

Extensions to PCEP for Point-to-Multipoint TE LSPs is proved. Closed-contract leftover harvest used to steal
genesis with ``Mission contract is closed; later genesis can take the next
unsaturated diversity-catalog family.`` After pcepmp seals a pcepmpdigest
this slot is that next family: RFC 6163 Framework for GMPLS and PCE Control of Wavelength Switched Optical Networks
WSON/RWA over a wsonid-gated wsondigest.
The protocol hole stays open so later genesis can opt the wson provider in
and seal a wsondigest.
"""

from __future__ import annotations

WSON_ACTUATION_ID = "capability.wson-actuation"
WSON_ACTUATION_DONE_WHEN = (
    f"capability_exists:{WSON_ACTUATION_ID};"
    f"capability_proved:{WSON_ACTUATION_ID};"
    "no_skill_route"
)
WSON_ACTUATION_GOAL = (
    "Repair rfc6163 wson wson/rwa cycle cannot land over http wson wsonid: "
    "hosted wson remain unsupported so a WSON then RWA wsonid handshake cannot "
    "land and a sealed wsondigest cannot be produced. A missing wson wsonid stays "
    "forbidden; fail-closed routing never opts the wson provider in. An independent "
    "later poll of the stored wsondigest keeps the hole falsifiable. WSON sessions "
    "stay fail-closed without a wsonid-gated wsondigest."
)
WSON_LEFTOVER = (
    "Later genesis can take RFC 6163 Framework for GMPLS and PCE Control of Wavelength Switched Optical Networks "
    "WSON/RWA over a wsonid-gated wsondigest."
)
