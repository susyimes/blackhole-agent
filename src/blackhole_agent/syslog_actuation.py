"""Next unsaturated diversity-catalog family after RFC 1157 SNMP lockstep.

SNMP is proved. Closed-contract leftover harvest used to steal genesis with
``Mission contract is closed; later genesis can take the next unsaturated
diversity-catalog family.`` After SNMP seals a varbind digest this slot is
that next family: RFC 5424 syslog PRI/HEADER/STRUCTURED-DATA/MSG over UDP.
The protocol hole stays open so later genesis can opt the syslog provider in
and seal a syslog digest.
"""

from __future__ import annotations

SYSLOG_ACTUATION_ID = "capability.syslog-actuation"
SYSLOG_ACTUATION_DONE_WHEN = (
    f"capability_exists:{SYSLOG_ACTUATION_ID};"
    f"capability_proved:{SYSLOG_ACTUATION_ID};"
    "no_skill_route"
)
SYSLOG_ACTUATION_GOAL = (
    "Repair rfc5424 syslog nilvalue-gated structured-data: hosted syslog "
    "tools remain unsupported so a PRI/HEADER/STRUCTURED-DATA/MSG cycle "
    "cannot land and a sealed syslog digest cannot be produced. A missing "
    "syslog hostname stays forbidden; fail-closed routing never opts the "
    "syslog provider in. An independent later replay of the stored message "
    "keeps the hole falsifiable."
)
