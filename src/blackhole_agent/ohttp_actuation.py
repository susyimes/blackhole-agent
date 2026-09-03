"""Next unsaturated diversity-catalog family after RFC 9484 CONNECT-IP lockstep.

CONNECT-IP is proved. Closed-contract leftover harvest used to steal genesis
with ``Mission contract is closed; later genesis can take the next unsaturated
diversity-catalog family.`` After CONNECT-IP seals an ipaddr digest this slot is
that next family: RFC 9458 Oblivious HTTP ENCAPSULATE/DECAPSULATE over HTTP.
The protocol hole stays open so later genesis can opt the ohttp
provider in and seal a gateway digest.
"""

from __future__ import annotations

OHTTP_ACTUATION_ID = "capability.ohttp-actuation"
OHTTP_ACTUATION_DONE_WHEN = (
    f"capability_exists:{OHTTP_ACTUATION_ID};"
    f"capability_proved:{OHTTP_ACTUATION_ID};"
    "no_skill_route"
)
OHTTP_ACTUATION_GOAL = (
    "Repair rfc9458 ohttp encapsulate/decapsulate cycle cannot land over http "
    "ohttp configid: hosted ohttp endpoints remain unsupported so an ENCAPSULATE then "
    "DECAPSULATE configid handshake cannot land and a sealed gateway digest "
    "cannot be produced. A missing ohttp configid stays forbidden; fail-closed "
    "routing never opts the ohttp provider in. An independent later poll of the "
    "stored gateway config keeps the hole falsifiable."
)
