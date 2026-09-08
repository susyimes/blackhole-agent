"""Next unsaturated diversity-catalog family after RFC 9722 DFREC/FAST.

Fast Recovery for EVPN Designated Forwarder Election is proved. Closed-contract leftover harvest used to steal
genesis with ``Mission contract is closed; later genesis can take the next
unsaturated diversity-catalog family.`` After dfrec seals a dfrecdigest
this slot is that next family: RFC 9856 Multicast Source Redundancy in EVPNs WARM/HOT
over a msredid-gated msreddigest.
The protocol hole stays open so later genesis can opt the msred provider in
and seal a msreddigest.
"""

from __future__ import annotations

MSRED_ACTUATION_ID = "capability.msred-actuation"
MSRED_ACTUATION_DONE_WHEN = (
    f"capability_exists:{MSRED_ACTUATION_ID};"
    f"capability_proved:{MSRED_ACTUATION_ID};"
    "no_skill_route"
)
MSRED_ACTUATION_GOAL = (
    "Repair rfc9856 msred warm/hot cycle cannot land over http msred msredid: hosted multicast source redundancy remain unsupported so a WARM then HOT msredid handshake cannot land and a sealed msreddigest cannot be produced. A missing msred msredid stays forbidden; fail-closed routing never opts the msred provider in. An independent later poll of the stored msreddigest keeps the hole falsifiable. Multicast Source Redundancy sessions stay fail-closed without a msredid-gated msreddigest."
)
