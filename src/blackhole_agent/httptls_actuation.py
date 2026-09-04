"""Next unsaturated diversity-catalog family after RFC 4559 SPNEGO-based Kerberos and NTLM HTTP Authentication.

SPNEGO-based Kerberos and NTLM HTTP Authentication is proved. Closed-contract leftover harvest used to steal genesis
with ``Mission contract is closed; later genesis can take the next unsaturated
diversity-catalog family.`` After SPNEGO-based Kerberos and NTLM HTTP Authentication seals a negotiatedigest this
slot is that next family: RFC 2817 Upgrading to TLS Within HTTP/1.1
UPGRADE/TLS over an upgradeid-gated upgradetlsdigest. The protocol hole
stays open so later genesis can opt the httptls provider in and seal a
upgradetlsdigest.
"""

from __future__ import annotations

HTTPTLS_ACTUATION_ID = "capability.httptls-actuation"
HTTPTLS_ACTUATION_DONE_WHEN = (
    f"capability_exists:{HTTPTLS_ACTUATION_ID};"
    f"capability_proved:{HTTPTLS_ACTUATION_ID};"
    "no_skill_route"
)
HTTPTLS_ACTUATION_GOAL = (
    "Repair rfc2817 httptls upgrade/tls cycle cannot land over http "
    "httptls upgradeid: hosted httptls endpoints remain unsupported so a UPGRADE then "
    "TLS upgradeid handshake cannot land and a sealed upgradetlsdigest "
    "cannot be produced. A missing httptls upgradeid stays forbidden; fail-closed "
    "routing never opts the httptls provider in. An independent later poll of the "
    "stored upgradetlsdigest keeps the hole falsifiable."
)
