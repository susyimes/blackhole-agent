"""Next unsaturated diversity-catalog family after RFC 1436 The Internet Gopher Protocol.

Gopher is proved. Closed-contract leftover harvest used to steal genesis with
``Mission contract is closed; later genesis can take the next unsaturated
diversity-catalog family.`` After Gopher seals a gopherdigest this slot is that
next family: RFC 1288 The Finger User Information Protocol QUERY/USER over a
fingerid-gated fingerdigest.
The protocol hole stays open so later genesis can opt the finger provider in
and seal a fingerdigest.
"""

from __future__ import annotations

FINGER_ACTUATION_ID = "capability.finger-actuation"
FINGER_ACTUATION_DONE_WHEN = (
    f"capability_exists:{FINGER_ACTUATION_ID};"
    f"capability_proved:{FINGER_ACTUATION_ID};"
    "no_skill_route"
)
FINGER_ACTUATION_GOAL = (
    "Repair rfc1288 finger query/user cycle cannot land over http "
    "finger fingerid: hosted finger endpoints remain unsupported so a QUERY then "
    "USER fingerid handshake cannot land and a sealed fingerdigest "
    "cannot be produced. A missing finger fingerid stays forbidden; fail-closed "
    "routing never opts the finger provider in. An independent later poll of the "
    "stored fingerdigest keeps the hole falsifiable."
)
