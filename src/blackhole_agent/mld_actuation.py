"""Next unsaturated diversity-catalog family after RFC 1112 Internet Group Management Protocol.

IGMP is proved. Closed-contract leftover harvest used to steal genesis with
``Mission contract is closed; later genesis can take the next unsaturated
diversity-catalog family.`` After IGMP seals an igmpdigest this slot is that
next family: RFC 2710 Multicast Listener Discovery LISTENER/DONE over an
mldid-gated mlddigest.
The protocol hole stays open so later genesis can opt the mld provider in
and seal an mlddigest.
"""

from __future__ import annotations

MLD_ACTUATION_ID = "capability.mld-actuation"
MLD_ACTUATION_DONE_WHEN = (
    f"capability_exists:{MLD_ACTUATION_ID};"
    f"capability_proved:{MLD_ACTUATION_ID};"
    "no_skill_route"
)
MLD_ACTUATION_GOAL = (
    "Repair rfc2710 mld listener/done cycle cannot land over http "
    "mld mldid: hosted mld endpoints remain unsupported so a LISTENER then "
    "DONE mldid handshake cannot land and a sealed mlddigest "
    "cannot be produced. A missing mld mldid stays forbidden; fail-closed "
    "routing never opts the mld provider in. An independent later poll of the "
    "stored mlddigest keeps the hole falsifiable."
)
