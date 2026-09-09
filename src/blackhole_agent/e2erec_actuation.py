"""Next unsaturated diversity-catalog family after RFC 4426 NOTIFY/RESTORE.

GMPLS Recovery is proved. Closed-contract leftover harvest used to steal
genesis with ``Mission contract is closed; later genesis can take the next
unsaturated diversity-catalog family.`` After grec seals a grecdigest
this slot is that next family: RFC 4872 GMPLS End-to-End Recovery
PROTECT/SWITCH over an e2erecid-gated e2erecdigest.
The protocol hole stays open so later genesis can opt the e2erec provider in
and seal a e2erecdigest.
"""

from __future__ import annotations

E2EREC_ACTUATION_ID = "capability.e2erec-actuation"
E2EREC_ACTUATION_DONE_WHEN = (
    f"capability_exists:{E2EREC_ACTUATION_ID};"
    f"capability_proved:{E2EREC_ACTUATION_ID};"
    "no_skill_route"
)
E2EREC_ACTUATION_GOAL = (
    'Repair rfc4872 e2erec protect/switch cycle cannot land over http e2erec e2erecid: hosted e2erec remain unsupported so a PROTECT then SWITCH e2erecid handshake cannot land and a sealed e2erecdigest cannot be produced. A missing e2erec e2erecid stays forbidden; fail-closed routing never opts the e2erec provider in. An independent later poll of the stored e2erecdigest keeps the hole falsifiable. E2EREC sessions stay fail-closed without an e2erecid-gated e2erecdigest.'
)
E2EREC_LEFTOVER = (
    'Later genesis can take RFC 4872 GMPLS End-to-End Recovery PROTECT/SWITCH over an e2erecid-gated e2erecdigest.'
)
