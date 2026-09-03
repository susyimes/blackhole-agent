"""Next unsaturated diversity-catalog family after RFC 9292 Binary HTTP.

Binary HTTP is proved. Closed-contract leftover harvest used to steal genesis
with ``Mission contract is closed; later genesis can take the next unsaturated
diversity-catalog family.`` After Binary HTTP seals a binarymsg digest this slot is
that next family: RFC 9112 HTTP/1.1 PARSE/SERIALIZE over a textual start-line.
The protocol hole stays open so later genesis can opt the http11
provider in and seal a startline digest.
"""

from __future__ import annotations

HTTP11_ACTUATION_ID = "capability.http11-actuation"
HTTP11_ACTUATION_DONE_WHEN = (
    f"capability_exists:{HTTP11_ACTUATION_ID};"
    f"capability_proved:{HTTP11_ACTUATION_ID};"
    "no_skill_route"
)
HTTP11_ACTUATION_GOAL = (
    "Repair rfc9112 http11 parse/serialize cycle cannot land over http "
    "http11 requestid: hosted http11 endpoints remain unsupported so a PARSE then "
    "SERIALIZE requestid handshake cannot land and a sealed startline digest "
    "cannot be produced. A missing http11 requestid stays forbidden; fail-closed "
    "routing never opts the http11 provider in. An independent later poll of the "
    "stored httpmessage startline keeps the hole falsifiable."
)
