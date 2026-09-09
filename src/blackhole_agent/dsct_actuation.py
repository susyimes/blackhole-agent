"""Next unsaturated diversity-catalog family after RFC 5441 BRPC/REPLY.

Backward-Recursive PCE-Based Computation is proved. Closed-contract leftover harvest used to steal
genesis with ``Mission contract is closed; later genesis can take the next
unsaturated diversity-catalog family.`` After brpc seals a brpcdigest
this slot is that next family: RFC 5455 Diffserv-aware Class-Type Object
CLASS/TYPE over a dsctid-gated dsctdigest.
The protocol hole stays open so later genesis can opt the dsct provider in
and seal a dsctdigest.
"""

from __future__ import annotations

DSCT_ACTUATION_ID = "capability.dsct-actuation"
DSCT_ACTUATION_DONE_WHEN = (
    f"capability_exists:{DSCT_ACTUATION_ID};"
    f"capability_proved:{DSCT_ACTUATION_ID};"
    "no_skill_route"
)
DSCT_ACTUATION_GOAL = (
    "Repair rfc5455 dsct class/type cycle cannot land over http dsct dsctid: "
    "hosted dsct remain unsupported so a CLASS then TYPE dsctid handshake cannot "
    "land and a sealed dsctdigest cannot be produced. A missing dsct dsctid stays "
    "forbidden; fail-closed routing never opts the dsct provider in. An independent "
    "later poll of the stored dsctdigest keeps the hole falsifiable. DSCT sessions "
    "stay fail-closed without a dsctid-gated dsctdigest."
)
DSCT_LEFTOVER = (
    "Later genesis can take RFC 5455 Diffserv-aware Class-Type Object "
    "CLASS/TYPE over a dsctid-gated dsctdigest."
)
