"""Next unsaturated diversity-catalog family after RFC 3473 NOTIFY/RESVCONF.

GMPLS RSVP-TE is proved. Closed-contract leftover harvest used to steal
genesis with ``Mission contract is closed; later genesis can take the next
unsaturated diversity-catalog family.`` After gmpls seals a gmplsdigest
this slot is that next family: RFC 4204 LMP CONFIG/HELLO
over an lmpid-gated lmpdigest.
The protocol hole stays open so later genesis can opt the lmp provider in
and seal a lmpdigest.
"""

from __future__ import annotations

LMP_ACTUATION_ID = "capability.lmp-actuation"
LMP_ACTUATION_DONE_WHEN = (
    f"capability_exists:{LMP_ACTUATION_ID};"
    f"capability_proved:{LMP_ACTUATION_ID};"
    "no_skill_route"
)
LMP_ACTUATION_GOAL = (
    "Repair rfc4204 lmp config/hello cycle cannot land over http lmp lmpid: hosted lmp remain unsupported so a CONFIG then HELLO lmpid handshake cannot land and a sealed lmpdigest cannot be produced. A missing lmp lmpid stays forbidden; fail-closed routing never opts the lmp provider in. An independent later poll of the stored lmpdigest keeps the hole falsifiable. LMP sessions stay fail-closed without an lmpid-gated lmpdigest."
)
LMP_LEFTOVER = (
    "Later genesis can take RFC 4204 LMP CONFIG/HELLO over an lmpid-gated lmpdigest."
)
