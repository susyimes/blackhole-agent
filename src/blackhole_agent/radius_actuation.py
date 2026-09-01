"""Next unsaturated diversity-catalog family after RFC 5905 NTP lockstep.

NTP is proved. Closed-contract leftover harvest used to steal genesis with
``Mission contract is closed; later genesis can take the next unsaturated
diversity-catalog family.`` After NTP seals a timestamp digest this slot is
that next family: RFC 2865 RADIUS Access-Request/Access-Accept over UDP.
The protocol hole stays open so later genesis can opt the radius provider
in and seal an attribute digest.
"""

from __future__ import annotations

RADIUS_ACTUATION_ID = "capability.radius-actuation"
RADIUS_ACTUATION_DONE_WHEN = (
    f"capability_exists:{RADIUS_ACTUATION_ID};"
    f"capability_proved:{RADIUS_ACTUATION_ID};"
    "no_skill_route"
)
RADIUS_ACTUATION_GOAL = (
    "Repair rfc2865 radius access-request/access-accept cycle cannot land over "
    "udp attributes: hosted radius tools remain unsupported so an Access-Request "
    "then Access-Accept attribute exchange cannot land and a sealed attribute "
    "digest cannot be produced. A missing radius secret stays forbidden; "
    "fail-closed routing never opts the radius provider in. An independent later "
    "poll of the stored User-Name attribute keeps the hole falsifiable."
)
