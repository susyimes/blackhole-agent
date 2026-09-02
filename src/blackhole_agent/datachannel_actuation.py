"""Next unsaturated diversity-catalog family after RFC 4960 SCTP lockstep.

SCTP is proved. Closed-contract leftover harvest used to steal genesis with
``Mission contract is closed; later genesis can take the next unsaturated
diversity-catalog family.`` After SCTP seals a tsn digest this slot is
that next family: RFC 8831 WebRTC Data Channel OPEN/ACK over SCTP.
The protocol hole stays open so later genesis can opt the datachannel
provider in and seal a dcep digest.
"""

from __future__ import annotations

DATACHANNEL_ACTUATION_ID = "capability.datachannel-actuation"
DATACHANNEL_ACTUATION_DONE_WHEN = (
    f"capability_exists:{DATACHANNEL_ACTUATION_ID};"
    f"capability_proved:{DATACHANNEL_ACTUATION_ID};"
    "no_skill_route"
)
DATACHANNEL_ACTUATION_GOAL = (
    "Repair rfc8831 datachannel open/ack cycle cannot land over sctp "
    "datachannel ppid: hosted datachannel endpoints remain unsupported so an OPEN then "
    "ACK ppid handshake cannot land and a sealed dcep digest "
    "cannot be produced. A missing datachannel ppid stays forbidden; fail-closed "
    "routing never opts the datachannel provider in. An independent later poll of the "
    "stored channel dcep keeps the hole falsifiable."
)
