"""Next unsaturated diversity-catalog family after RFC 8941 Structured Fields.

Structured Fields is proved. Closed-contract leftover harvest used to steal genesis
with ``Mission contract is closed; later genesis can take the next unsaturated
diversity-catalog family.`` After Structured Fields seals an sfv digest this
slot is that next family: RFC 8942 HTTP Client Hints ACCEPTCH/CRITCH over a
chid-gated hintsdigest. The protocol hole stays open so later genesis can opt the
clienthints provider in and seal a hintsdigest.
"""

from __future__ import annotations

CLIENTHINTS_ACTUATION_ID = "capability.clienthints-actuation"
CLIENTHINTS_ACTUATION_DONE_WHEN = (
    f"capability_exists:{CLIENTHINTS_ACTUATION_ID};"
    f"capability_proved:{CLIENTHINTS_ACTUATION_ID};"
    "no_skill_route"
)
CLIENTHINTS_ACTUATION_GOAL = (
    "Repair rfc8942 clienthints acceptch/critch cycle cannot land over http "
    "clienthints chid: hosted clienthints endpoints remain unsupported so an ACCEPTCH then "
    "CRITCH chid handshake cannot land and a sealed hintsdigest "
    "cannot be produced. A missing clienthints chid stays forbidden; fail-closed "
    "routing never opts the clienthints provider in. An independent later poll of the "
    "stored hintsdigest keeps the hole falsifiable."
)
