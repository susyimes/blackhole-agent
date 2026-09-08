"""Next unsaturated diversity-catalog family after RFC 8214 AD/VPWS.

Virtual Private Wire Service Support in Ethernet VPN is proved. Closed-contract leftover harvest used to steal
genesis with ``Mission contract is closed; later genesis can take the next
unsaturated diversity-catalog family.`` After evpn seals a evpndigest
this slot is that next family: RFC 8317 Ethernet-Tree (E-Tree) Support in Ethernet VPN ROOT/LEAF
over an etreeid-gated etreedigest.
The protocol hole stays open so later genesis can opt the etree provider in
and seal a etreedigest.
"""

from __future__ import annotations

ETREE_ACTUATION_ID = "capability.etree-actuation"
ETREE_ACTUATION_DONE_WHEN = (
    f"capability_exists:{ETREE_ACTUATION_ID};"
    f"capability_proved:{ETREE_ACTUATION_ID};"
    "no_skill_route"
)
ETREE_ACTUATION_GOAL = (
    "Repair rfc8317 etree root/leaf cycle cannot land over http etree etreeid: hosted ethernet-tree (e-tree) support in ethernet vpn endpoints remain unsupported so a ROOT then LEAF etreeid handshake cannot land and a sealed etreedigest cannot be produced. A missing etree etreeid stays forbidden; fail-closed routing never opts the etree provider in. An independent later poll of the stored etreedigest keeps the hole falsifiable. Ethernet-Tree (E-Tree) Support in Ethernet VPN sessions stay fail-closed without a etreeid-gated etreedigest."
)
