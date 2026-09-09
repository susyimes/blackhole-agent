"""Next unsaturated diversity-catalog family after RFC 4209 VERIFY/TRACE.

LMP-WDM is proved. Closed-contract leftover harvest used to steal
genesis with ``Mission contract is closed; later genesis can take the next
unsaturated diversity-catalog family.`` After lwdm seals a lwdmdigest
this slot is that next family: RFC 4328 GMPLS OTN OTU/ODU
over an otnid-gated otndigest.
The protocol hole stays open so later genesis can opt the otn provider in
and seal an otndigest.
"""

from __future__ import annotations

OTN_ACTUATION_ID = "capability.otn-actuation"
OTN_ACTUATION_DONE_WHEN = (
    f"capability_exists:{OTN_ACTUATION_ID};"
    f"capability_proved:{OTN_ACTUATION_ID};"
    "no_skill_route"
)
OTN_ACTUATION_GOAL = (
    "Repair rfc4328 otn otu/odu cycle cannot land over http otn otnid: hosted otn remain unsupported so a OTU then ODU otnid handshake cannot land and a sealed otndigest cannot be produced. A missing otn otnid stays forbidden; fail-closed routing never opts the otn provider in. An independent later poll of the stored otndigest keeps the hole falsifiable. OTN sessions stay fail-closed without an otnid-gated otndigest."
)
OTN_LEFTOVER = (
    "Later genesis can take RFC 4328 GMPLS OTN OTU/ODU over an otnid-gated otndigest."
)
