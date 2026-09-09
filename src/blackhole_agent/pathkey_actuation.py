"""Next unsaturated diversity-catalog family after RFC 5455 CLASS/TYPE.

Diffserv-aware Class-Type Object is proved. Closed-contract leftover harvest used to steal
genesis with ``Mission contract is closed; later genesis can take the next
unsaturated diversity-catalog family.`` After dsct seals a dsctdigest
this slot is that next family: RFC 5520 Path-Key-Based Mechanism
PATH/KEY over a pathkeyid-gated pathkeydigest.
The protocol hole stays open so later genesis can opt the pathkey provider in
and seal a pathkeydigest.
"""

from __future__ import annotations

PATHKEY_ACTUATION_ID = "capability.pathkey-actuation"
PATHKEY_ACTUATION_DONE_WHEN = (
    f"capability_exists:{PATHKEY_ACTUATION_ID};"
    f"capability_proved:{PATHKEY_ACTUATION_ID};"
    "no_skill_route"
)
PATHKEY_ACTUATION_GOAL = (
    "Repair rfc5520 pathkey path/key cycle cannot land over http pathkey pathkeyid: "
    "hosted pathkey remain unsupported so a PATH then KEY pathkeyid handshake cannot "
    "land and a sealed pathkeydigest cannot be produced. A missing pathkey pathkeyid stays "
    "forbidden; fail-closed routing never opts the pathkey provider in. An independent "
    "later poll of the stored pathkeydigest keeps the hole falsifiable. PATHKEY sessions "
    "stay fail-closed without a pathkeyid-gated pathkeydigest."
)
PATHKEY_LEFTOVER = (
    "Later genesis can take RFC 5520 Path-Key-Based Mechanism "
    "PATH/KEY over a pathkeyid-gated pathkeydigest."
)
