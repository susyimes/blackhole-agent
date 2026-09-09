"""Next unsaturated diversity-catalog family after RFC 4875 P2MP/S2L.

Point-to-Multipoint TE LSPs is proved. Closed-contract leftover harvest used to steal
genesis with ``Mission contract is closed; later genesis can take the next
unsaturated diversity-catalog family.`` After p2mpte seals a p2mptedigest
this slot is that next family: RFC 4920 Crankback Signaling
CRANK/RETRY over a crankbackid-gated crankbackdigest.
The protocol hole stays open so later genesis can opt the crankback provider in
and seal a crankbackdigest.
"""

from __future__ import annotations

CRANKBACK_ACTUATION_ID = "capability.crankback-actuation"
CRANKBACK_ACTUATION_DONE_WHEN = (
    f"capability_exists:{CRANKBACK_ACTUATION_ID};"
    f"capability_proved:{CRANKBACK_ACTUATION_ID};"
    "no_skill_route"
)
CRANKBACK_ACTUATION_GOAL = (
    "Repair rfc4920 crankback crank/retry cycle cannot land over http crankback crankbackid: "
    "hosted crankback remain unsupported so a CRANK then RETRY crankbackid handshake cannot "
    "land and a sealed crankbackdigest cannot be produced. A missing crankback crankbackid stays "
    "forbidden; fail-closed routing never opts the crankback provider in. An independent "
    "later poll of the stored crankbackdigest keeps the hole falsifiable. CRANKBACK sessions "
    "stay fail-closed without a crankbackid-gated crankbackdigest."
)
CRANKBACK_LEFTOVER = (
    "Later genesis can take RFC 4920 Crankback Signaling CRANK/RETRY over a "
    "crankbackid-gated crankbackdigest."
)
