"""Next unsaturated diversity-catalog family after RFC 7838 HTTP Alternative Services.

HTTP Alternative Services is proved. Closed-contract leftover harvest used to steal genesis
with ``Mission contract is closed; later genesis can take the next unsaturated
diversity-catalog family.`` After Alternative Services seals an origindigest this
slot is that next family: RFC 6797 HTTP Strict Transport Security STS/PRELOAD over an
hstsid-gated stsdigest. The protocol hole stays open so later genesis can opt the
hsts provider in and seal a stsdigest.
"""

from __future__ import annotations

HSTS_ACTUATION_ID = "capability.hsts-actuation"
HSTS_ACTUATION_DONE_WHEN = (
    f"capability_exists:{HSTS_ACTUATION_ID};"
    f"capability_proved:{HSTS_ACTUATION_ID};"
    "no_skill_route"
)
HSTS_ACTUATION_GOAL = (
    "Repair rfc6797 hsts sts/preload cycle cannot land over http "
    "hsts hstsid: hosted hsts endpoints remain unsupported so an STS then "
    "PRELOAD hstsid handshake cannot land and a sealed stsdigest "
    "cannot be produced. A missing hsts hstsid stays forbidden; fail-closed "
    "routing never opts the hsts provider in. An independent later poll of the "
    "stored stsdigest keeps the hole falsifiable."
)
