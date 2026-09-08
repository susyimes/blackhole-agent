"""Next unsaturated diversity-catalog family after RFC 9572 SMET/IMET.

Updates to EVPN BUM Procedures is proved. Closed-contract leftover harvest used to steal
genesis with ``Mission contract is closed; later genesis can take the next
unsaturated diversity-catalog family.`` After evpnbum seals a evpnbumdigest
this slot is that next family: RFC 9625 EVPN VPWS Flexible Cross-Connect FXC/VLAN
over an fxcid-gated fxcdigest.
The protocol hole stays open so later genesis can opt the fxc provider in
and seal a fxcdigest.
"""

from __future__ import annotations

FXC_ACTUATION_ID = "capability.fxc-actuation"
FXC_ACTUATION_DONE_WHEN = (
    f"capability_exists:{FXC_ACTUATION_ID};"
    f"capability_proved:{FXC_ACTUATION_ID};"
    "no_skill_route"
)
FXC_ACTUATION_GOAL = (
    "Repair rfc9625 fxc fxc/vlan cycle cannot land over http fxc fxcid: hosted flexible cross-connect ethernet tag remain unsupported so a FXC then VLAN fxcid handshake cannot land and a sealed fxcdigest cannot be produced. A missing fxc fxcid stays forbidden; fail-closed routing never opts the fxc provider in. An independent later poll of the stored fxcdigest keeps the hole falsifiable. Flexible Cross-Connect sessions stay fail-closed without a fxcid-gated fxcdigest."
)
