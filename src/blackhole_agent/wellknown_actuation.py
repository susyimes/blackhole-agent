"""Next unsaturated diversity-catalog family after RFC 5789 PATCH Method for HTTP.

PATCH Method for HTTP is proved. Closed-contract leftover harvest used to steal genesis
with ``Mission contract is closed; later genesis can take the next unsaturated
diversity-catalog family.`` After PATCH Method for HTTP seals a patchdigest this
slot is that next family: RFC 5785 Defining Well-Known Uniform Resource Identifiers
DISCOVERY/SUFFIX over a suffixid-gated suffixdigest. The protocol hole
stays open so later genesis can opt the wellknown provider in and seal a
suffixdigest.
"""

from __future__ import annotations

WELLKNOWN_ACTUATION_ID = "capability.wellknown-actuation"
WELLKNOWN_ACTUATION_DONE_WHEN = (
    f"capability_exists:{WELLKNOWN_ACTUATION_ID};"
    f"capability_proved:{WELLKNOWN_ACTUATION_ID};"
    "no_skill_route"
)
WELLKNOWN_ACTUATION_GOAL = (
    "Repair rfc5785 wellknown discovery/suffix cycle cannot land over http "
    "wellknown suffixid: hosted wellknown endpoints remain unsupported so a DISCOVERY then "
    "SUFFIX suffixid handshake cannot land and a sealed suffixdigest "
    "cannot be produced. A missing wellknown suffixid stays forbidden; fail-closed "
    "routing never opts the wellknown provider in. An independent later poll of the "
    "stored suffixdigest keeps the hole falsifiable."
)
