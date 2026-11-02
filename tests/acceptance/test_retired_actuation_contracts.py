"""Retired dns, websocket, ftp, and tftp clones stay as catalog contracts.

Importing the diversity catalog must not load those implementations. Their
catalog ids and goals remain readable, and importing a deleted module fails.
The same probe exits 0 on the previous milestone source and on this tree.
"""

from __future__ import annotations

import json
import sys

RETIRED = (
    "blackhole_agent.dns_actuation",
    "blackhole_agent.websocket_actuation",
    "blackhole_agent.ftp_actuation",
    "blackhole_agent.tftp_actuation",
)
RETIRED_IDS = (
    "capability.dns-actuation",
    "capability.websocket-actuation",
    "capability.ftp-actuation",
    "capability.tftp-actuation",
)


def main() -> int:
    observed: dict[str, object] = {}
    passed = False
    try:
        import blackhole_agent.kernel_genesis_diversify as diversify

        loaded = {name: name in sys.modules for name in RETIRED}
        offers = {str(item.get("id") or "") for item in diversify.DIVERSITY_CATALOG}
        resolver = getattr(diversify, "catalog_entry", None)
        dns = resolver("capability.dns-actuation") if callable(resolver) else None
        import_error = ""
        try:
            import blackhole_agent.dns_actuation  # noqa: F401
        except ModuleNotFoundError as exc:
            import_error = type(exc).__name__
        goal = str((dns or {}).get("goal") or "")
        observed = {
            "loaded": loaded,
            "offered": {item: item in offers for item in RETIRED_IDS},
            "sqlite_loaded": "blackhole_agent.sqlite_actuation" in sys.modules,
            "dns_goal_from_catalog": goal.startswith("Repair nameserver TSIG-gated apex record:"),
            "dns_import_error": import_error,
        }
        passed = bool(
            not any(loaded.values())
            and all(observed["offered"].values())  # type: ignore[union-attr]
            and observed["sqlite_loaded"]
            and observed["dns_goal_from_catalog"]
            and import_error == "ModuleNotFoundError"
            and "blackhole_agent.dns_actuation" not in sys.modules
        )
    except Exception as exc:
        observed = {"error": f"{type(exc).__name__}: {exc}"}
        passed = False
    print(json.dumps({"observed": observed, "passed": passed}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
