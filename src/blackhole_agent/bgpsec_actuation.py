"""Next unsaturated diversity-catalog family after RFC 8092 LARGE/PART.

BGP Large Communities is proved. Closed-contract leftover harvest used to steal
genesis with ``Mission contract is closed; later genesis can take the next
unsaturated diversity-catalog family.`` After largecomm seals a largecommdigest
this slot is that next family: RFC 8205 BGPsec Protocol SIGN/PATH over a
bgpsecid-gated bgpsecdigest.
The protocol hole stays open so later genesis can opt the bgpsec provider in
and seal a bgpsecdigest.
"""

from __future__ import annotations

BGPSEC_ACTUATION_ID = "capability.bgpsec-actuation"
BGPSEC_ACTUATION_DONE_WHEN = (
    f"capability_exists:{BGPSEC_ACTUATION_ID};"
    f"capability_proved:{BGPSEC_ACTUATION_ID};"
    "no_skill_route"
)
BGPSEC_ACTUATION_GOAL = (
    "Repair rfc8205 bgpsec sign/path cycle cannot land over http bgpsec bgpsecid: hosted bgpsec protocol endpoints remain unsupported so a SIGN then PATH bgpsecid handshake cannot land and a sealed bgpsecdigest cannot be produced. A missing bgpsec bgpsecid stays forbidden; fail-closed routing never opts the bgpsec provider in. An independent later poll of the stored bgpsecdigest keeps the hole falsifiable. BGPsec sessions stay fail-closed without a bgpsecid-gated bgpsecdigest."
)
