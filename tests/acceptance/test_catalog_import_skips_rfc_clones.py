"""Loading the diversity catalog must not import retired actuation clones.

The same probe runs against the previous milestone source and the candidate
source. It exits 0 either way and prints JSON with boolean passed plus a
nonempty observed object.
"""

from __future__ import annotations

import json
import sys

RETIRED_MODULES = (
    "blackhole_agent.twfec_actuation",
    "blackhole_agent.elbl_actuation",
    "blackhole_agent.gtsm_actuation",
    "blackhole_agent.bgp4_actuation",
    "blackhole_agent.snmp_actuation",
    "blackhole_agent.dhcp_actuation",
)
RETIRED_IDS = (
    "capability.twfec-actuation",
    "capability.elbl-actuation",
    "capability.gtsm-actuation",
    "capability.bgp4-actuation",
    "capability.snmp-actuation",
    "capability.dhcp-actuation",
)


def main() -> int:
    observed: dict[str, object] = {}
    passed = False
    try:
        import blackhole_agent.kernel_genesis_diversify as diversify

        offers = [str(item.get("id")) for item in diversify.DIVERSITY_CATALOG]
        loaded = [
            name
            for name in sys.modules
            if name.startswith("blackhole_agent.") and name.endswith("_actuation")
        ]
        retired_loaded = [name for name in RETIRED_MODULES if name in sys.modules]
        retired_offered = [item for item in RETIRED_IDS if item in offers]
        observed = {
            "catalog_count": len(offers),
            "loaded_actuation_count": len(loaded),
            "retired_loaded": retired_loaded,
            "retired_offered": retired_offered,
            "sqlite_loaded": "blackhole_agent.sqlite_actuation" in sys.modules,
            "sqlite_offered": "capability.sqlite-actuation" in offers,
            "twfec_loaded": "blackhole_agent.twfec_actuation" in sys.modules,
            "twfec_offered": "capability.twfec-actuation" in offers,
        }
        passed = bool(
            observed["sqlite_loaded"]
            and observed["sqlite_offered"]
            and not observed["twfec_loaded"]
            and not observed["twfec_offered"]
            and not retired_loaded
            and not retired_offered
            and int(observed["loaded_actuation_count"]) < 40
        )
    except Exception as exc:
        observed = {"error": f"{type(exc).__name__}: {exc}"}
        passed = False
    print(json.dumps({"observed": observed, "passed": passed}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
