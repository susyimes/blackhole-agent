"""Next unsaturated diversity-catalog family after RFC 1738 Uniform Resource Locators.

Uniform Resource Locators are proved. Closed-contract leftover harvest
used to steal genesis with ``Mission contract is closed; later genesis can
take the next unsaturated diversity-catalog family.`` After URL
seals a urldigest this slot is that next family: RFC 1630
Universal Resource Identifiers IDENTIFY/DEREF over a uriid-gated
uridigest.
The protocol hole stays open so later genesis can opt the uri provider in
and seal a uridigest.
"""

from __future__ import annotations

URI_ACTUATION_ID = "capability.uri-actuation"
URI_ACTUATION_DONE_WHEN = (
    f"capability_exists:{URI_ACTUATION_ID};"
    f"capability_proved:{URI_ACTUATION_ID};"
    "no_skill_route"
)
URI_ACTUATION_GOAL = (
    "Repair rfc1630 uri identify/deref cycle cannot land over http "
    "uri uriid: hosted uri endpoints remain unsupported so an IDENTIFY then "
    "DEREF uriid handshake cannot land and a sealed uridigest "
    "cannot be produced. A missing uri uriid stays forbidden; fail-closed "
    "routing never opts the uri provider in. An independent later poll of the "
    "stored uridigest keeps the hole falsifiable."
)
