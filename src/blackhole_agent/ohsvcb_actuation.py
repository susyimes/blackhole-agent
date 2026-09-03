"""Next unsaturated diversity-catalog family after RFC 9458 Oblivious HTTP lockstep.

Oblivious HTTP is proved. Closed-contract leftover harvest used to steal genesis
with ``Mission contract is closed; later genesis can take the next unsaturated
diversity-catalog family.`` After Oblivious HTTP seals a gateway digest this slot is
that next family: RFC 9540 Oblivious Service Binding QUERY/ANSWER over DNS SVCB.
The protocol hole stays open so later genesis can opt the ohsvcb
provider in and seal a keyconf digest.
"""

from __future__ import annotations

OHSVCB_ACTUATION_ID = "capability.ohsvcb-actuation"
OHSVCB_ACTUATION_DONE_WHEN = (
    f"capability_exists:{OHSVCB_ACTUATION_ID};"
    f"capability_proved:{OHSVCB_ACTUATION_ID};"
    "no_skill_route"
)
OHSVCB_ACTUATION_GOAL = (
    "Repair rfc9540 ohsvcb query/answer cycle cannot land over dns "
    "ohsvcb svcbid: hosted ohsvcb endpoints remain unsupported so a QUERY then "
    "ANSWER svcbid handshake cannot land and a sealed keyconf digest "
    "cannot be produced. A missing ohsvcb svcbid stays forbidden; fail-closed "
    "routing never opts the ohsvcb provider in. An independent later poll of the "
    "stored service keyconf keeps the hole falsifiable."
)
