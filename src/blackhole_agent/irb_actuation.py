"""Next unsaturated diversity-catalog family after RFC 8584 DF/NDF.

Ethernet VPN Designated Forwarder Election is proved. Closed-contract leftover harvest used to steal
genesis with ``Mission contract is closed; later genesis can take the next
unsaturated diversity-catalog family.`` After dfe seals a dfedigest
this slot is that next family: RFC 9135 Integrated Routing and Bridging in Ethernet VPN IRB/L3
over an irbid-gated irbdigest.
The protocol hole stays open so later genesis can opt the irb provider in
and seal a irbdigest.
"""

from __future__ import annotations

IRB_ACTUATION_ID = "capability.irb-actuation"
IRB_ACTUATION_DONE_WHEN = (
    f"capability_exists:{IRB_ACTUATION_ID};"
    f"capability_proved:{IRB_ACTUATION_ID};"
    "no_skill_route"
)
IRB_ACTUATION_GOAL = (
    "Repair rfc9135 irb irb/l3 cycle cannot land over http irb irbid: hosted integrated routing and bridging in ethernet vpn endpoints remain unsupported so a IRB then L3 irbid handshake cannot land and a sealed irbdigest cannot be produced. A missing irb irbid stays forbidden; fail-closed routing never opts the irb provider in. An independent later poll of the stored irbdigest keeps the hole falsifiable. Integrated Routing and Bridging in Ethernet VPN sessions stay fail-closed without a irbid-gated irbdigest."
)
