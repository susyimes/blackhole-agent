"""Next unsaturated diversity-catalog family after RFC 4918 HTTP Extensions for WebDAV.

HTTP Extensions for WebDAV is proved. Closed-contract leftover harvest used to steal genesis
with ``Mission contract is closed; later genesis can take the next unsaturated
diversity-catalog family.`` After HTTP Extensions for WebDAV seals a lockdigest this
slot is that next family: RFC 4559 SPNEGO-based Kerberos and NTLM HTTP Authentication
NEGOTIATE/AUTHENTICATE over a negotiateid-gated negotiatedigest. The protocol hole
stays open so later genesis can opt the spnego provider in and seal a
negotiatedigest.
"""

from __future__ import annotations

SPNEGO_ACTUATION_ID = "capability.spnego-actuation"
SPNEGO_ACTUATION_DONE_WHEN = (
    f"capability_exists:{SPNEGO_ACTUATION_ID};"
    f"capability_proved:{SPNEGO_ACTUATION_ID};"
    "no_skill_route"
)
SPNEGO_ACTUATION_GOAL = (
    "Repair rfc4559 spnego negotiate/authenticate cycle cannot land over http "
    "spnego negotiateid: hosted spnego endpoints remain unsupported so a NEGOTIATE then "
    "AUTHENTICATE negotiateid handshake cannot land and a sealed negotiatedigest "
    "cannot be produced. A missing spnego negotiateid stays forbidden; fail-closed "
    "routing never opts the spnego provider in. An independent later poll of the "
    "stored negotiatedigest keeps the hole falsifiable."
)
