"""Next unsaturated diversity-catalog family after RFC 9163 Expect-CT.

Expect-CT is proved. Closed-contract leftover harvest used to steal genesis
with ``Mission contract is closed; later genesis can take the next unsaturated
diversity-catalog family.`` After Expect-CT seals a ctdigest this
slot is that next family: RFC 7034 X-Frame-Options DENY/SAMEORIGIN over a
frameid-gated framedigest. The protocol hole stays open so later genesis can opt the
xfo provider in and seal a framedigest.
"""

from __future__ import annotations

XFO_ACTUATION_ID = "capability.xfo-actuation"
XFO_ACTUATION_DONE_WHEN = (
    f"capability_exists:{XFO_ACTUATION_ID};"
    f"capability_proved:{XFO_ACTUATION_ID};"
    "no_skill_route"
)
XFO_ACTUATION_GOAL = (
    "Repair rfc7034 xfo deny/sameorigin cycle cannot land over http "
    "xfo frameid: hosted xfo endpoints remain unsupported so a DENY then "
    "SAMEORIGIN frameid handshake cannot land and a sealed framedigest "
    "cannot be produced. A missing xfo frameid stays forbidden; fail-closed "
    "routing never opts the xfo provider in. An independent later poll of the "
    "stored framedigest keeps the hole falsifiable."
)
