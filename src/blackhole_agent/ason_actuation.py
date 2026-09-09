"""Next unsaturated diversity-catalog family after RFC 4328 OTU/ODU.

GMPLS OTN is proved. Closed-contract leftover harvest used to steal
genesis with ``Mission contract is closed; later genesis can take the next
unsaturated diversity-catalog family.`` After otn seals an otndigest
this slot is that next family: RFC 4397 GMPLS ASON CALL/CONN
over an asonid-gated asondigest.
The protocol hole stays open so later genesis can opt the ason provider in
and seal an asondigest.
"""

from __future__ import annotations

ASON_ACTUATION_ID = "capability.ason-actuation"
ASON_ACTUATION_DONE_WHEN = (
    f"capability_exists:{ASON_ACTUATION_ID};"
    f"capability_proved:{ASON_ACTUATION_ID};"
    "no_skill_route"
)
ASON_ACTUATION_GOAL = (
    "Repair rfc4397 ason call/conn cycle cannot land over http ason asonid: hosted ason remain unsupported so a CALL then CONN asonid handshake cannot land and a sealed asondigest cannot be produced. A missing ason asonid stays forbidden; fail-closed routing never opts the ason provider in. An independent later poll of the stored asondigest keeps the hole falsifiable. ASON sessions stay fail-closed without an asonid-gated asondigest."
)
ASON_LEFTOVER = (
    "Later genesis can take RFC 4397 GMPLS ASON CALL/CONN over an asonid-gated asondigest."
)
