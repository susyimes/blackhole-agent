"""Next unsaturated diversity-catalog family after RFC 6052 WKP/NSP.

V4EMBED is proved. Closed-contract leftover harvest used to steal
genesis with ``Mission contract is closed; later genesis can take the next
unsaturated diversity-catalog family.`` After v4embed seals a v4embeddigest
this slot is that next family: RFC 8215 Local-Use IPv4/IPv6 Translation
Prefix LUP/NSL over a luprefixid-gated luprefixdigest.
The protocol hole stays open so later genesis can opt the luprefix provider in
and seal a luprefixdigest.
"""

from __future__ import annotations

LUPREFIX_ACTUATION_ID = "capability.luprefix-actuation"
LUPREFIX_ACTUATION_DONE_WHEN = (
    f"capability_exists:{LUPREFIX_ACTUATION_ID};"
    f"capability_proved:{LUPREFIX_ACTUATION_ID};"
    "no_skill_route"
)
LUPREFIX_ACTUATION_GOAL = (
    "Repair rfc8215 luprefix lup/nsl cycle cannot land over http "
    "luprefix luprefixid: hosted local-use ipv4/ipv6 translation prefix endpoints remain unsupported "
    "so a LUP then NSL luprefixid handshake cannot land and a sealed "
    "luprefixdigest cannot be produced. A missing luprefix luprefixid stays forbidden; "
    "fail-closed routing never opts the luprefix provider in. An independent later "
    "poll of the stored luprefixdigest keeps the hole falsifiable. Local-use translator "
    "prefixes stay fail-closed without a luprefixid-gated "
    "luprefixdigest."
)
