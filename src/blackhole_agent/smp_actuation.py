"""Next unsaturated diversity-catalog family after RFC 6387 ASYM/BIDIR.

GMPLS Asymmetric Bandwidth Bidirectional Label Switched Paths (LSPs) is proved. Closed-contract leftover harvest used to steal
genesis with ``Mission contract is closed; later genesis can take the next
unsaturated diversity-catalog family.`` After asbw seals a asbwdigest
this slot is that next family: RFC 6388 LSP Hierarchy Supporting Shared Mesh Protection
SHARE/PROTECT over an smpid-gated smpdigest.
The protocol hole stays open so later genesis can opt the smp provider in
and seal a smpdigest.
"""

from __future__ import annotations

SMP_ACTUATION_ID = "capability.smp-actuation"
SMP_ACTUATION_DONE_WHEN = (
    f"capability_exists:{SMP_ACTUATION_ID};"
    f"capability_proved:{SMP_ACTUATION_ID};"
    "no_skill_route"
)
SMP_ACTUATION_GOAL = (
    "Repair rfc6388 smp share/protect cycle cannot land over http smp smpid: "
    "hosted smp remain unsupported so a SHARE then PROTECT smpid handshake cannot "
    "land and a sealed smpdigest cannot be produced. A missing smp smpid stays "
    "forbidden; fail-closed routing never opts the smp provider in. An independent "
    "later poll of the stored smpdigest keeps the hole falsifiable. SMP sessions "
    "stay fail-closed without an smpid-gated smpdigest."
)
SMP_LEFTOVER = (
    "Later genesis can take RFC 6388 LSP Hierarchy Supporting Shared Mesh Protection "
    "SHARE/PROTECT over an smpid-gated smpdigest."
)
