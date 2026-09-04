"""Next unsaturated diversity-catalog family after RFC 8297 Early Hints.

Early Hints is proved. Closed-contract leftover harvest used to steal genesis
with ``Mission contract is closed; later genesis can take the next unsaturated
diversity-catalog family.`` After Early Hints seals an earlydigest this
slot is that next family: RFC 8188 Encrypted Content-Encoding ENCRYPT/DECRYPT over an
encid-gated ecedigest. The protocol hole stays open so later genesis can opt the
encryptedcontent provider in and seal an ecedigest.
"""

from __future__ import annotations

ENCRYPTEDCONTENT_ACTUATION_ID = "capability.encryptedcontent-actuation"
ENCRYPTEDCONTENT_ACTUATION_DONE_WHEN = (
    f"capability_exists:{ENCRYPTEDCONTENT_ACTUATION_ID};"
    f"capability_proved:{ENCRYPTEDCONTENT_ACTUATION_ID};"
    "no_skill_route"
)
ENCRYPTEDCONTENT_ACTUATION_GOAL = (
    "Repair rfc8188 encryptedcontent encrypt/decrypt cycle cannot land over http "
    "encryptedcontent encid: hosted encryptedcontent endpoints remain unsupported so an ENCRYPT then "
    "DECRYPT encid handshake cannot land and a sealed ecedigest "
    "cannot be produced. A missing encryptedcontent encid stays forbidden; fail-closed "
    "routing never opts the encryptedcontent provider in. An independent later poll of the "
    "stored ecedigest keeps the hole falsifiable."
)
