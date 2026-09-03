"""Next unsaturated diversity-catalog family after RFC 9112 HTTP/1.1.

HTTP/1.1 is proved. Closed-contract leftover harvest used to steal genesis
with ``Mission contract is closed; later genesis can take the next unsaturated
diversity-catalog family.`` After HTTP/1.1 seals a startline digest this slot is
that next family: RFC 9113 HTTP/2 PREFACE/SETTINGS over a connection preface.
The protocol hole stays open so later genesis can opt the http2
provider in and seal a hpack digest.
"""

from __future__ import annotations

HTTP2_ACTUATION_ID = "capability.http2-actuation"
HTTP2_ACTUATION_DONE_WHEN = (
    f"capability_exists:{HTTP2_ACTUATION_ID};"
    f"capability_proved:{HTTP2_ACTUATION_ID};"
    "no_skill_route"
)
HTTP2_ACTUATION_GOAL = (
    "Repair rfc9113 http2 preface/settings cycle cannot land over http "
    "http2 settingsid: hosted http2 endpoints remain unsupported so a PREFACE then "
    "SETTINGS settingsid handshake cannot land and a sealed hpack digest "
    "cannot be produced. A missing http2 settingsid stays forbidden; fail-closed "
    "routing never opts the http2 provider in. An independent later poll of the "
    "stored connection preface keeps the hole falsifiable."
)
