"""Next unsaturated diversity-catalog family after RFC 8188 Encrypted Content-Encoding.

Encrypted Content-Encoding is proved. Closed-contract leftover harvest used to steal genesis
with ``Mission contract is closed; later genesis can take the next unsaturated
diversity-catalog family.`` After Encrypted Content-Encoding seals an ecedigest this
slot is that next family: RFC 7838 HTTP Alternative Services ALTSVC/ORIGIN over an
altsvcid-gated origindigest. The protocol hole stays open so later genesis can opt the
altsvc provider in and seal an origindigest.
"""

from __future__ import annotations

ALTSVC_ACTUATION_ID = "capability.altsvc-actuation"
ALTSVC_ACTUATION_DONE_WHEN = (
    f"capability_exists:{ALTSVC_ACTUATION_ID};"
    f"capability_proved:{ALTSVC_ACTUATION_ID};"
    "no_skill_route"
)
ALTSVC_ACTUATION_GOAL = (
    "Repair rfc7838 altsvc altsvc/origin cycle cannot land over http "
    "altsvc altsvcid: hosted altsvc endpoints remain unsupported so an ALTSVC then "
    "ORIGIN altsvcid handshake cannot land and a sealed origindigest "
    "cannot be produced. A missing altsvc altsvcid stays forbidden; fail-closed "
    "routing never opts the altsvc provider in. An independent later poll of the "
    "stored origindigest keeps the hole falsifiable."
)
