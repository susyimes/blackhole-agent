"""Next unsaturated diversity-catalog family after RFC 959 FTP PASV transfer.

FTP is proved. Closed-contract leftover harvest used to steal genesis with
``Mission contract is closed; later genesis can take the next unsaturated
diversity-catalog family.`` This slot is that next family: RFC 1350 TFTP
RRQ/WRQ/DATA/ACK over UDP. The protocol hole stays open so later genesis
can opt the tftp provider in and seal a block digest.
"""

from __future__ import annotations

TFTP_ACTUATION_ID = "capability.tftp-actuation"
TFTP_ACTUATION_DONE_WHEN = (
    f"capability_exists:{TFTP_ACTUATION_ID};"
    f"capability_proved:{TFTP_ACTUATION_ID};"
    "no_skill_route"
)
TFTP_ACTUATION_GOAL = (
    "Repair rfc1350 tftp rrq/wrq/data/ack cycle cannot land over udp lockstep "
    "opcodes: hosted tftp tools remain unsupported so a WRQ then DATA/ACK "
    "opcode exchange cannot land and a sealed block digest cannot be produced. "
    "A missing tftp tid stays forbidden; fail-closed routing never opts the "
    "tftp provider in. An independent later RRQ of the stored octet stream "
    "keeps the hole falsifiable."
)
