"""Next unsaturated diversity-catalog family after RFC 2529 6OVER4/MCAST.

6OVER4 is proved. Closed-contract leftover harvest used to steal
genesis with ``Mission contract is closed; later genesis can take the next
unsaturated diversity-catalog family.`` After sixover4 seals a sixover4digest
this slot is that next family: RFC 4213 Basic Transition Mechanisms for IPv6
Hosts and Routers 6IN4/CONFIG over a sixin4id-gated sixin4digest.
The protocol hole stays open so later genesis can opt the sixin4 provider in
and seal a sixin4digest.
"""

from __future__ import annotations

SIXIN4_ACTUATION_ID = "capability.sixin4-actuation"
SIXIN4_ACTUATION_DONE_WHEN = (
    f"capability_exists:{SIXIN4_ACTUATION_ID};"
    f"capability_proved:{SIXIN4_ACTUATION_ID};"
    "no_skill_route"
)
SIXIN4_ACTUATION_GOAL = (
    "Repair rfc4213 sixin4 6in4/config cycle cannot land over http "
    "sixin4 sixin4id: hosted basic transition mechanisms endpoints remain unsupported "
    "so a 6IN4 then CONFIG sixin4id handshake cannot land and a sealed "
    "sixin4digest cannot be produced. A missing sixin4 sixin4id stays forbidden; "
    "fail-closed routing never opts the sixin4 provider in. An independent later "
    "poll of the stored sixin4digest keeps the hole falsifiable. Configured "
    "ipv6-in-ipv4 tunnels stay fail-closed without a sixin4id-gated "
    "sixin4digest."
)
