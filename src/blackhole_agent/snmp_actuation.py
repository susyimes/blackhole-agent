"""Next unsaturated diversity-catalog family after RFC 1350 TFTP lockstep.

TFTP is proved. Closed-contract leftover harvest used to steal genesis with
``Mission contract is closed; later genesis can take the next unsaturated
diversity-catalog family.`` After TFTP seals a block digest this slot is
that next family: RFC 1157 SNMP GET/SET/RESPONSE over UDP. The protocol
hole stays open so later genesis can opt the snmp provider in and seal a
varbind digest.
"""

from __future__ import annotations

SNMP_ACTUATION_ID = "capability.snmp-actuation"
SNMP_ACTUATION_DONE_WHEN = (
    f"capability_exists:{SNMP_ACTUATION_ID};"
    f"capability_proved:{SNMP_ACTUATION_ID};"
    "no_skill_route"
)
SNMP_ACTUATION_GOAL = (
    "Repair rfc1157 snmp get/set/response cycle cannot land over udp lockstep "
    "pdus: hosted snmp tools remain unsupported so a SET then GET/RESPONSE "
    "pdu exchange cannot land and a sealed varbind digest cannot be produced. "
    "A missing snmp community stays forbidden; fail-closed routing never opts "
    "the snmp provider in. An independent later GET of the stored varbind "
    "keeps the hole falsifiable."
)
