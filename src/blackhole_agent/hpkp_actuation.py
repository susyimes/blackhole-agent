"""Next unsaturated diversity-catalog family after RFC 6797 HTTP Strict Transport Security.

HTTP Strict Transport Security is proved. Closed-contract leftover harvest used to steal genesis
with ``Mission contract is closed; later genesis can take the next unsaturated
diversity-catalog family.`` After Strict Transport Security seals a stsdigest this
slot is that next family: RFC 7469 HTTP Public Key Pinning PIN/REPORT over a
pinid-gated pindigest. The protocol hole stays open so later genesis can opt the
hpkp provider in and seal a pindigest.
"""

from __future__ import annotations

HPKP_ACTUATION_ID = "capability.hpkp-actuation"
HPKP_ACTUATION_DONE_WHEN = (
    f"capability_exists:{HPKP_ACTUATION_ID};"
    f"capability_proved:{HPKP_ACTUATION_ID};"
    "no_skill_route"
)
HPKP_ACTUATION_GOAL = (
    "Repair rfc7469 hpkp pin/report cycle cannot land over http "
    "hpkp pinid: hosted hpkp endpoints remain unsupported so a PIN then "
    "REPORT pinid handshake cannot land and a sealed pindigest "
    "cannot be produced. A missing hpkp pinid stays forbidden; fail-closed "
    "routing never opts the hpkp provider in. An independent later poll of the "
    "stored pindigest keeps the hole falsifiable."
)
