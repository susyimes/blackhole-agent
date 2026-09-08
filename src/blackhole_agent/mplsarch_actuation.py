"""Next unsaturated diversity-catalog family after RFC 3916 NATIVE/PW.

Requirements for Pseudo-Wire Emulation Edge-to-Edge is proved. Closed-contract leftover harvest used to steal
genesis with ``Mission contract is closed; later genesis can take the next
unsaturated diversity-catalog family.`` After pwreq seals a pwreqdigest
this slot is that next family: RFC 3031 Multiprotocol Label Switching Architecture FEC/NHLFE
over an mplsid-gated mplsdigest.
The protocol hole stays open so later genesis can opt the mplsarch provider in
and seal a mplsdigest.
"""

from __future__ import annotations

MPLSARCH_ACTUATION_ID = "capability.mplsarch-actuation"
MPLSARCH_ACTUATION_DONE_WHEN = (
    f"capability_exists:{MPLSARCH_ACTUATION_ID};"
    f"capability_proved:{MPLSARCH_ACTUATION_ID};"
    "no_skill_route"
)
MPLSARCH_ACTUATION_GOAL = (
    "Repair rfc3031 mplsarch fec/nhlfe cycle cannot land over http mplsarch mplsid: hosted multiprotocol label switching architecture remain unsupported so a FEC then NHLFE mplsid handshake cannot land and a sealed mplsdigest cannot be produced. A missing mplsarch mplsid stays forbidden; fail-closed routing never opts the mplsarch provider in. An independent later poll of the stored mplsdigest keeps the hole falsifiable. Multiprotocol Label Switching Architecture sessions stay fail-closed without an mplsid-gated mplsdigest."
)
MPLSARCH_LEFTOVER = (
    "Later genesis can take RFC 3031 Multiprotocol Label Switching Architecture FEC/NHLFE over an mplsid-gated mplsdigest."
)
