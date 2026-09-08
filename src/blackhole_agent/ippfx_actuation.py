"""Next unsaturated diversity-catalog family after RFC 9135 IRB/L3.

Integrated Routing and Bridging in Ethernet VPN is proved. Closed-contract leftover harvest used to steal
genesis with ``Mission contract is closed; later genesis can take the next
unsaturated diversity-catalog family.`` After irb seals a irbdigest
this slot is that next family: RFC 9136 IP Prefix Advertisement in Ethernet VPN PREFIX/IP
over an ippfxid-gated ippfxdigest.
The protocol hole stays open so later genesis can opt the ippfx provider in
and seal a ippfxdigest.
"""

from __future__ import annotations

IPPFX_ACTUATION_ID = "capability.ippfx-actuation"
IPPFX_ACTUATION_DONE_WHEN = (
    f"capability_exists:{IPPFX_ACTUATION_ID};"
    f"capability_proved:{IPPFX_ACTUATION_ID};"
    "no_skill_route"
)
IPPFX_ACTUATION_GOAL = (
    "Repair rfc9136 ippfx prefix/ip cycle cannot land over http ippfx ippfxid: hosted ip prefix advertisement in ethernet vpn endpoints remain unsupported so a PREFIX then IP ippfxid handshake cannot land and a sealed ippfxdigest cannot be produced. A missing ippfx ippfxid stays forbidden; fail-closed routing never opts the ippfx provider in. An independent later poll of the stored ippfxdigest keeps the hole falsifiable. IP Prefix Advertisement in Ethernet VPN sessions stay fail-closed without a ippfxid-gated ippfxdigest."
)
