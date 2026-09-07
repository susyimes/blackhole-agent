"""Next unsaturated diversity-catalog family after RFC 7599 DMR/EA.

MAP-T is proved. Closed-contract leftover harvest used to steal
genesis with ``Mission contract is closed; later genesis can take the next
unsaturated diversity-catalog family.`` After mapt seals a maptdigest
this slot is that next family: RFC 7598 DHCPv6 Options for Configuration of
Softwire Address and Port-Mapped Clients RULE/PORTPARAMS over an s46id-gated
s46digest. The protocol hole stays open so later genesis can opt the s46
provider in and seal a s46digest.
"""

from __future__ import annotations

S46_ACTUATION_ID = "capability.s46-actuation"
S46_ACTUATION_DONE_WHEN = (
    f"capability_exists:{S46_ACTUATION_ID};"
    f"capability_proved:{S46_ACTUATION_ID};"
    "no_skill_route"
)
S46_ACTUATION_GOAL = (
    "Repair rfc7598 s46 rule/portparams cycle cannot land over http "
    "s46 s46id: hosted s46 endpoints remain unsupported so a RULE then "
    "PORTPARAMS s46id handshake cannot land and a sealed s46digest "
    "cannot be produced. A missing s46 s46id stays forbidden; fail-closed "
    "routing never opts the s46 provider in. An independent later poll of the "
    "stored s46digest keeps the hole falsifiable."
)
