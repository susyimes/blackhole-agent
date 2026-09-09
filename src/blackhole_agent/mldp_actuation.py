"""Next unsaturated diversity-catalog family after RFC 6478 STATUS/ACK.

Pseudowire Status for Static Pseudowires is proved. Closed-contract leftover
harvest used to steal genesis with ``Mission contract is closed; later genesis
can take the next unsaturated diversity-catalog family.`` After pwst seals a
pwstdigest this slot is that next family: RFC 6512 Using Multipoint LDP When
the Backbone Has No Route to the Root MLDP/ROOT over an mldpid-gated
mldpdigest.
The protocol hole stays open so later genesis can opt the mldp provider in
and seal a mldpdigest.
"""

from __future__ import annotations

MLDP_ACTUATION_ID = "capability.mldp-actuation"
MLDP_ACTUATION_DONE_WHEN = (
    f"capability_exists:{MLDP_ACTUATION_ID};"
    f"capability_proved:{MLDP_ACTUATION_ID};"
    "no_skill_route"
)
MLDP_ACTUATION_GOAL = (
    "Repair rfc6512 mldp mldp/root cycle cannot land over http mldp mldpid: "
    "hosted mldp remain unsupported so a MLDP then ROOT mldpid handshake cannot "
    "land and a sealed mldpdigest cannot be produced. A missing mldp mldpid stays "
    "forbidden; fail-closed routing never opts the mldp provider in. An independent "
    "later poll of the stored mldpdigest keeps the hole falsifiable. MLDP sessions "
    "stay fail-closed without an mldpid-gated mldpdigest."
)
MLDP_LEFTOVER = (
    "Later genesis can take RFC 6512 Using Multipoint LDP When the Backbone "
    "Has No Route to the Root "
    "MLDP/ROOT over an mldpid-gated mldpdigest."
)
