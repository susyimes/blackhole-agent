"""Next unsaturated diversity-catalog family after RFC 3971 SEND.

SEND is proved. Closed-contract leftover harvest used to steal genesis with
``Mission contract is closed; later genesis can take the next unsaturated
diversity-catalog family.`` After SEND seals a senddigest this slot is that
next family: RFC 4193 Unique Local IPv6 Unicast Addresses UNIQUE/LOCAL over a
ulaid-gated uladigest.
The protocol hole stays open so later genesis can opt the ula provider in
and seal a uladigest.
"""

from __future__ import annotations

ULA_ACTUATION_ID = "capability.ula-actuation"
ULA_ACTUATION_DONE_WHEN = (
    f"capability_exists:{ULA_ACTUATION_ID};"
    f"capability_proved:{ULA_ACTUATION_ID};"
    "no_skill_route"
)
ULA_ACTUATION_GOAL = (
    "Repair rfc4193 ula unique/local cycle cannot land over http "
    "ula ulaid: hosted ula endpoints remain unsupported so a UNIQUE then "
    "LOCAL ulaid handshake cannot land and a sealed uladigest "
    "cannot be produced. A missing ula ulaid stays forbidden; fail-closed "
    "routing never opts the ula provider in. An independent later poll of the "
    "stored uladigest keeps the hole falsifiable."
)
