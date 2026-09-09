"""Next unsaturated diversity-catalog family after RFC 4920 CRANK/RETRY.

Crankback Signaling is proved. Closed-contract leftover harvest used to steal
genesis with ``Mission contract is closed; later genesis can take the next
unsaturated diversity-catalog family.`` After crankback seals a crankbackdigest
this slot is that next family: RFC 5150 Label Switched Path Stitching
STITCH/JOIN over a lspstitchid-gated lspstitchdigest.
The protocol hole stays open so later genesis can opt the lspstitch provider in
and seal a lspstitchdigest.
"""

from __future__ import annotations

LSPSTITCH_ACTUATION_ID = "capability.lspstitch-actuation"
LSPSTITCH_ACTUATION_DONE_WHEN = (
    f"capability_exists:{LSPSTITCH_ACTUATION_ID};"
    f"capability_proved:{LSPSTITCH_ACTUATION_ID};"
    "no_skill_route"
)
LSPSTITCH_ACTUATION_GOAL = (
    "Repair rfc5150 lspstitch stitch/join cycle cannot land over http lspstitch lspstitchid: "
    "hosted lspstitch remain unsupported so a STITCH then JOIN lspstitchid handshake cannot "
    "land and a sealed lspstitchdigest cannot be produced. A missing lspstitch lspstitchid stays "
    "forbidden; fail-closed routing never opts the lspstitch provider in. An independent "
    "later poll of the stored lspstitchdigest keeps the hole falsifiable. LSPSTITCH sessions "
    "stay fail-closed without a lspstitchid-gated lspstitchdigest."
)
LSPSTITCH_LEFTOVER = (
    "Later genesis can take RFC 5150 Label Switched Path Stitching STITCH/JOIN over a "
    "lspstitchid-gated lspstitchdigest."
)
