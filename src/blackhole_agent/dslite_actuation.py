"""Next unsaturated diversity-catalog family after RFC 7050 IPV4ONLY/AAAA.

DISC is proved. Closed-contract leftover harvest used to steal
genesis with ``Mission contract is closed; later genesis can take the next
unsaturated diversity-catalog family.`` After disc seals a discdigest
this slot is that next family: RFC 6333 Dual-Stack Lite Broadband
Deployments Following IPv4 Exhaustion B4/AFTR over a dsliteid-gated
dslitedigest. The protocol hole stays open so later genesis can opt the
dslite provider in and seal a dslitedigest.
"""

from __future__ import annotations

DSLITE_ACTUATION_ID = "capability.dslite-actuation"
DSLITE_ACTUATION_DONE_WHEN = (
    f"capability_exists:{DSLITE_ACTUATION_ID};"
    f"capability_proved:{DSLITE_ACTUATION_ID};"
    "no_skill_route"
)
DSLITE_ACTUATION_GOAL = (
    "Repair rfc6333 dslite b4/aftr cycle cannot land over http "
    "dslite dsliteid: hosted dslite endpoints remain unsupported so a B4 then "
    "AFTR dsliteid handshake cannot land and a sealed dslitedigest "
    "cannot be produced. A missing dslite dsliteid stays forbidden; fail-closed "
    "routing never opts the dslite provider in. An independent later poll of the "
    "stored dslitedigest keeps the hole falsifiable."
)
