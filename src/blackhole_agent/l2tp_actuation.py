"""Next unsaturated diversity-catalog family after RFC 5572 TSP/SETUP.

TSP is proved. Closed-contract leftover harvest used to steal
genesis with ``Mission contract is closed; later genesis can take the next
unsaturated diversity-catalog family.`` After tsp seals a tspdigest
this slot is that next family: RFC 5571 Softwire Hub and Spoke Deployment
Framework with Layer Two Tunneling Protocol version 2 L2TP/SPOKE over a
l2tpid-gated l2tpdigest.
The protocol hole stays open so later genesis can opt the l2tp provider in
and seal a l2tpdigest.
"""

from __future__ import annotations

L2TP_ACTUATION_ID = "capability.l2tp-actuation"
L2TP_ACTUATION_DONE_WHEN = (
    f"capability_exists:{L2TP_ACTUATION_ID};"
    f"capability_proved:{L2TP_ACTUATION_ID};"
    "no_skill_route"
)
L2TP_ACTUATION_GOAL = (
    "Repair rfc5571 l2tp l2tp/spoke cycle cannot land over http l2tp l2tpid: hosted "
    "softwire hub and spoke deployment framework with layer two tunneling protocol "
    "version 2 endpoints remain unsupported so a L2TP then SPOKE l2tpid handshake "
    "cannot land and a sealed l2tpdigest cannot be produced. A missing l2tp l2tpid "
    "stays forbidden; fail-closed routing never opts the l2tp provider in. An "
    "independent later poll of the stored l2tpdigest keeps the hole falsifiable. "
    "Softwire hub-and-spoke sessions stay fail-closed without a l2tpid-gated l2tpdigest."
)
