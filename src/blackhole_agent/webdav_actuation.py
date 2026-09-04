"""Next unsaturated diversity-catalog family after RFC 5785 Defining Well-Known Uniform Resource Identifiers.

Defining Well-Known Uniform Resource Identifiers is proved. Closed-contract leftover harvest used to steal genesis
with ``Mission contract is closed; later genesis can take the next unsaturated
diversity-catalog family.`` After Defining Well-Known Uniform Resource Identifiers seals a suffixdigest this
slot is that next family: RFC 4918 HTTP Extensions for WebDAV
PROPFIND/LOCK over a lockid-gated lockdigest. The protocol hole
stays open so later genesis can opt the webdav provider in and seal a
lockdigest.
"""

from __future__ import annotations

WEBDAV_ACTUATION_ID = "capability.webdav-actuation"
WEBDAV_ACTUATION_DONE_WHEN = (
    f"capability_exists:{WEBDAV_ACTUATION_ID};"
    f"capability_proved:{WEBDAV_ACTUATION_ID};"
    "no_skill_route"
)
WEBDAV_ACTUATION_GOAL = (
    "Repair rfc4918 webdav propfind/lock cycle cannot land over http "
    "webdav lockid: hosted webdav endpoints remain unsupported so a PROPFIND then "
    "LOCK lockid handshake cannot land and a sealed lockdigest "
    "cannot be produced. A missing webdav lockid stays forbidden; fail-closed "
    "routing never opts the webdav provider in. An independent later poll of the "
    "stored lockdigest keeps the hole falsifiable."
)
