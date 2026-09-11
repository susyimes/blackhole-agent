"""Next unsaturated diversity-catalog family after RFC 6720 GTSM/TTL.

The Generalized TTL Security Mechanism for LDP is proved. After gtsm seals a
gtsmdigest this slot is that next family: RFC 6790 The Use of Entropy Labels
in MPLS Forwarding EL/ELI over an elblid-gated elbldigest. The protocol hole
stays open so later genesis can opt the elbl provider in and seal an elbldigest.
"""

from __future__ import annotations

ELBL_ACTUATION_ID = "capability.elbl-actuation"
ELBL_ACTUATION_DONE_WHEN = (
    f"capability_exists:{ELBL_ACTUATION_ID};"
    f"capability_proved:{ELBL_ACTUATION_ID};"
    "no_skill_route"
)
ELBL_ACTUATION_GOAL = (
    "Repair rfc6790 elbl el/eli cycle cannot land over http elbl elblid: "
    "hosted elbl remain unsupported so a EL then ELI elblid handshake cannot "
    "land and a sealed elbldigest cannot be produced. A missing elbl elblid stays "
    "forbidden; fail-closed routing never opts the elbl provider in. An independent "
    "later poll of the stored elbldigest keeps the hole falsifiable. ELBL sessions "
    "stay fail-closed without an elblid-gated elbldigest."
)
ELBL_LEFTOVER = (
    "Later genesis can take RFC 6790 The Use of Entropy Labels in MPLS "
    "Forwarding EL/ELI over an elblid-gated elbldigest."
)
