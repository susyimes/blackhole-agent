"""Next unsaturated diversity-catalog family after RFC 2295 Transparent Content Negotiation.

Transparent Content Negotiation is proved. Closed-contract leftover harvest used to steal genesis
with ``Mission contract is closed; later genesis can take the next unsaturated
diversity-catalog family.`` After Transparent Content Negotiation seals a
choicedigest this slot is that next family: RFC 2227 Simple Hit-Metering
METER/USAGE over a meterid-gated usagedigest. The protocol hole
stays open so later genesis can opt the hitmeter provider in and seal a
usagedigest.
"""

from __future__ import annotations

HITMETER_ACTUATION_ID = "capability.hitmeter-actuation"
HITMETER_ACTUATION_DONE_WHEN = (
    f"capability_exists:{HITMETER_ACTUATION_ID};"
    f"capability_proved:{HITMETER_ACTUATION_ID};"
    "no_skill_route"
)
HITMETER_ACTUATION_GOAL = (
    "Repair rfc2227 hitmeter meter/usage cycle cannot land over http "
    "hitmeter meterid: hosted hitmeter endpoints remain unsupported so a METER then "
    "USAGE meterid handshake cannot land and a sealed usagedigest "
    "cannot be produced. A missing hitmeter meterid stays forbidden; fail-closed "
    "routing never opts the hitmeter provider in. An independent later poll of the "
    "stored usagedigest keeps the hole falsifiable."
)
