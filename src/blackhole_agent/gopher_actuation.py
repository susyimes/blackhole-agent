"""Next unsaturated diversity-catalog family after RFC 1521 MIME.

MIME is proved. Closed-contract leftover harvest used to steal genesis with
``Mission contract is closed; later genesis can take the next unsaturated
diversity-catalog family.`` After MIME seals a mimedigest this slot is that
next family: RFC 1436 The Internet Gopher Protocol SELECTOR/MENU over a
gopherid-gated gopherdigest.
The protocol hole stays open so later genesis can opt the gopher provider in
and seal a gopherdigest.
"""

from __future__ import annotations

GOPHER_ACTUATION_ID = "capability.gopher-actuation"
GOPHER_ACTUATION_DONE_WHEN = (
    f"capability_exists:{GOPHER_ACTUATION_ID};"
    f"capability_proved:{GOPHER_ACTUATION_ID};"
    "no_skill_route"
)
GOPHER_ACTUATION_GOAL = (
    "Repair rfc1436 gopher selector/menu cycle cannot land over http "
    "gopher gopherid: hosted gopher endpoints remain unsupported so a SELECTOR then "
    "MENU gopherid handshake cannot land and a sealed gopherdigest "
    "cannot be produced. A missing gopher gopherid stays forbidden; fail-closed "
    "routing never opts the gopher provider in. An independent later poll of the "
    "stored gopherdigest keeps the hole falsifiable."
)
