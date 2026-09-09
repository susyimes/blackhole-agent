"""Next unsaturated diversity-catalog family after RFC 5440 OPEN/PCREQ.

Path Computation Element Communication Protocol is proved. Closed-contract leftover harvest used to steal
genesis with ``Mission contract is closed; later genesis can take the next
unsaturated diversity-catalog family.`` After pcep seals a pcepdigest
this slot is that next family: RFC 5441 Backward-Recursive PCE-Based Computation
BRPC/REPLY over a brpcid-gated brpcdigest.
The protocol hole stays open so later genesis can opt the brpc provider in
and seal a brpcdigest.
"""

from __future__ import annotations

BRPC_ACTUATION_ID = "capability.brpc-actuation"
BRPC_ACTUATION_DONE_WHEN = (
    f"capability_exists:{BRPC_ACTUATION_ID};"
    f"capability_proved:{BRPC_ACTUATION_ID};"
    "no_skill_route"
)
BRPC_ACTUATION_GOAL = (
    "Repair rfc5441 brpc brpc/reply cycle cannot land over http brpc brpcid: "
    "hosted brpc remain unsupported so a BRPC then REPLY brpcid handshake cannot "
    "land and a sealed brpcdigest cannot be produced. A missing brpc brpcid stays "
    "forbidden; fail-closed routing never opts the brpc provider in. An independent "
    "later poll of the stored brpcdigest keeps the hole falsifiable. BRPC sessions "
    "stay fail-closed without a brpcid-gated brpcdigest."
)
BRPC_LEFTOVER = (
    "Later genesis can take RFC 5441 Backward-Recursive PCE-Based Computation "
    "BRPC/REPLY over a brpcid-gated brpcdigest."
)
