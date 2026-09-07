"""Next unsaturated diversity-catalog family after RFC 6877 CLAT/PLAT.

464XLAT is proved. Closed-contract leftover harvest used to steal
genesis with ``Mission contract is closed; later genesis can take the next
unsaturated diversity-catalog family.`` After xlat seals a clatdigest
this slot is that next family: RFC 7050 Discovery of the IPv6 Prefix Used
for IPv6 Address Synthesis IPV4ONLY/AAAA over a discid-gated discdigest.
The protocol hole stays open so later genesis can opt the disc provider in
and seal a discdigest.
"""

from __future__ import annotations

DISC_ACTUATION_ID = "capability.disc-actuation"
DISC_ACTUATION_DONE_WHEN = (
    f"capability_exists:{DISC_ACTUATION_ID};"
    f"capability_proved:{DISC_ACTUATION_ID};"
    "no_skill_route"
)
DISC_ACTUATION_GOAL = (
    "Repair rfc7050 disc ipv4only/aaaa cycle cannot land over http "
    "disc discid: hosted disc endpoints remain unsupported so a IPV4ONLY then "
    "AAAA discid handshake cannot land and a sealed discdigest "
    "cannot be produced. A missing disc discid stays forbidden; fail-closed "
    "routing never opts the disc provider in. An independent later poll of the "
    "stored discdigest keeps the hole falsifiable."
)
