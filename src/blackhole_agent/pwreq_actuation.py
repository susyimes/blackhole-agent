"""Next unsaturated diversity-catalog family after RFC 3985 PSN/NSP.

Pseudo Wire Emulation Edge-to-Edge (PWE3) Architecture is proved. Closed-contract leftover harvest used to steal
genesis with ``Mission contract is closed; later genesis can take the next
unsaturated diversity-catalog family.`` After pwe3 seals a pwe3digest
this slot is that next family: RFC 3916 Requirements for Pseudo-Wire Emulation Edge-to-Edge NATIVE/PW
over a pwreqid-gated pwreqdigest.
The protocol hole stays open so later genesis can opt the pwreq provider in
and seal a pwreqdigest.
"""

from __future__ import annotations

PWREQ_ACTUATION_ID = "capability.pwreq-actuation"
PWREQ_ACTUATION_DONE_WHEN = (
    f"capability_exists:{PWREQ_ACTUATION_ID};"
    f"capability_proved:{PWREQ_ACTUATION_ID};"
    "no_skill_route"
)
PWREQ_ACTUATION_GOAL = (
    "Repair rfc3916 pwreq native/pw cycle cannot land over http pwreq pwreqid: hosted requirements for pseudo-wire emulation edge-to-edge remain unsupported so a NATIVE then PW pwreqid handshake cannot land and a sealed pwreqdigest cannot be produced. A missing pwreq pwreqid stays forbidden; fail-closed routing never opts the pwreq provider in. An independent later poll of the stored pwreqdigest keeps the hole falsifiable. Requirements for Pseudo-Wire Emulation Edge-to-Edge sessions stay fail-closed without a pwreqid-gated pwreqdigest."
)
PWREQ_LEFTOVER = (
    "Later genesis can take RFC 3916 Requirements for Pseudo-Wire Emulation Edge-to-Edge NATIVE/PW over a pwreqid-gated pwreqdigest."
)
