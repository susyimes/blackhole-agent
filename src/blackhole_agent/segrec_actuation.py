"""Next unsaturated diversity-catalog family after RFC 4872 PROTECT/SWITCH.

GMPLS End-to-End Recovery is proved. Closed-contract leftover harvest used to steal
genesis with ``Mission contract is closed; later genesis can take the next
unsaturated diversity-catalog family.`` After e2erec seals an e2erecdigest
this slot is that next family: RFC 4873 GMPLS Segment Recovery
SEGMENT/RECOVER over a segrecid-gated segrecdigest.
The protocol hole stays open so later genesis can opt the segrec provider in
and seal a segrecdigest.
"""

from __future__ import annotations

SEGREC_ACTUATION_ID = "capability.segrec-actuation"
SEGREC_ACTUATION_DONE_WHEN = (
    f"capability_exists:{SEGREC_ACTUATION_ID};"
    f"capability_proved:{SEGREC_ACTUATION_ID};"
    "no_skill_route"
)
SEGREC_ACTUATION_GOAL = (
    "Repair rfc4873 segrec segment/recover cycle cannot land over http segrec segrecid: "
    "hosted segrec remain unsupported so a SEGMENT then RECOVER segrecid handshake cannot "
    "land and a sealed segrecdigest cannot be produced. A missing segrec segrecid stays "
    "forbidden; fail-closed routing never opts the segrec provider in. An independent "
    "later poll of the stored segrecdigest keeps the hole falsifiable. SEGREC sessions "
    "stay fail-closed without a segrecid-gated segrecdigest."
)
SEGREC_LEFTOVER = (
    "Later genesis can take RFC 4873 GMPLS Segment Recovery SEGMENT/RECOVER over a "
    "segrecid-gated segrecdigest."
)
