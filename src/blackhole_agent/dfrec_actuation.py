"""Next unsaturated diversity-catalog family after RFC 9625 FXC/VLAN.

EVPN VPWS Flexible Cross-Connect is proved. Closed-contract leftover harvest used to steal
genesis with ``Mission contract is closed; later genesis can take the next
unsaturated diversity-catalog family.`` After fxc seals a fxcdigest
this slot is that next family: RFC 9722 Fast Recovery for EVPN Designated Forwarder Election DFREC/FAST
over a dfrecid-gated dfrecdigest.
The protocol hole stays open so later genesis can opt the dfrec provider in
and seal a dfrecdigest.
"""

from __future__ import annotations

DFREC_ACTUATION_ID = "capability.dfrec-actuation"
DFREC_ACTUATION_DONE_WHEN = (
    f"capability_exists:{DFREC_ACTUATION_ID};"
    f"capability_proved:{DFREC_ACTUATION_ID};"
    "no_skill_route"
)
DFREC_ACTUATION_GOAL = (
    "Repair rfc9722 dfrec dfrec/fast cycle cannot land over http dfrec dfrecid: hosted fast recovery for evpn designated forwarder election remain unsupported so a DFREC then FAST dfrecid handshake cannot land and a sealed dfrecdigest cannot be produced. A missing dfrec dfrecid stays forbidden; fail-closed routing never opts the dfrec provider in. An independent later poll of the stored dfrecdigest keeps the hole falsifiable. Fast Recovery sessions stay fail-closed without a dfrecid-gated dfrecdigest."
)
