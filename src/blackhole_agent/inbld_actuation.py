"""Next unsaturated diversity-catalog family after RFC 6790 EL/ELI.

Entropy Labels are proved. After elbl seals an elbldigest this slot is that
next family: RFC 6826 Multipoint LDP In-Band Signaling INBAND/OPAQUE over an
inbldid-gated inbldigest. The protocol hole stays open so later genesis can
opt the inbld provider in and seal an inbldigest.
"""

from __future__ import annotations

INBLD_ACTUATION_ID = "capability.inbld-actuation"
INBLD_ACTUATION_DONE_WHEN = (
    f"capability_exists:{INBLD_ACTUATION_ID};"
    f"capability_proved:{INBLD_ACTUATION_ID};"
    "no_skill_route"
)
INBLD_ACTUATION_GOAL = (
    "Repair rfc6826 inbld inband/opaque cycle cannot land over http inbld inbldid: "
    "hosted inbld remain unsupported so a INBAND then OPAQUE inbldid handshake cannot "
    "land and a sealed inbldigest cannot be produced. A missing inbld inbldid stays "
    "forbidden; fail-closed routing never opts the inbld provider in. An independent "
    "later poll of the stored inbldigest keeps the hole falsifiable. INBLD sessions "
    "stay fail-closed without an inbldid-gated inbldigest."
)
INBLD_LEFTOVER = (
    "Later genesis can take RFC 6826 Multipoint LDP In-Band Signaling "
    "INBAND/OPAQUE over an inbldid-gated inbldigest."
)
