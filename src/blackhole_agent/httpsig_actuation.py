"""Next unsaturated diversity-catalog family after RFC 9540 Oblivious Service Binding.

Oblivious Service Binding is proved. Closed-contract leftover harvest used to steal genesis
with ``Mission contract is closed; later genesis can take the next unsaturated
diversity-catalog family.`` After Oblivious Service Binding seals a keyconf digest this slot is
that next family: RFC 9421 HTTP Message Signatures SIGN/VERIFY over a signature base.
The protocol hole stays open so later genesis can opt the httpsig
provider in and seal a sigbase digest.
"""

from __future__ import annotations

HTTPSIG_ACTUATION_ID = "capability.httpsig-actuation"
HTTPSIG_ACTUATION_DONE_WHEN = (
    f"capability_exists:{HTTPSIG_ACTUATION_ID};"
    f"capability_proved:{HTTPSIG_ACTUATION_ID};"
    "no_skill_route"
)
HTTPSIG_ACTUATION_GOAL = (
    "Repair rfc9421 httpsig sign/verify cycle cannot land over http "
    "httpsig sigid: hosted httpsig endpoints remain unsupported so a SIGN then "
    "VERIFY sigid handshake cannot land and a sealed sigbase digest "
    "cannot be produced. A missing httpsig sigid stays forbidden; fail-closed "
    "routing never opts the httpsig provider in. An independent later poll of the "
    "stored message sigbase keeps the hole falsifiable."
)
