"""The three node export growth planes share one runner.

The probe exits 0 either way and prints JSON with boolean passed and nonempty
observed. It asks which winner each plane names and whether the historical
runners are one function body. It does not register a ledger capability.
"""

from __future__ import annotations

import json


def outcome() -> dict[str, object]:
    observed: dict[str, object] = {}
    passed = False
    try:
        import blackhole_agent.capability_application_growth as growth

        names = (
            "run_application_node_default_export_growth_plane",
            "run_application_node_default_export_object_growth_plane",
            "run_application_node_default_export_class_growth_plane",
        )
        runners = [getattr(growth, name, None) for name in names]
        codes = [getattr(runner, "__code__", None) for runner in runners]
        shared = all(code is not None for code in codes) and codes[0] is codes[1] is codes[2]
        lookup = getattr(growth, "node_export_plane", None)
        planes: dict[str, object] = {}
        absent: object = "missing"
        if callable(lookup):
            for key in ("default-export", "default-export-object", "default-export-class"):
                row = lookup(key)
                planes[key] = None if not isinstance(row, dict) else row.get("winner_slug")
            absent = lookup("not-a-node-export-plane")
        observed = {
            "absent_plane": absent is None,
            "planes": planes,
            "shared_runner": shared,
        }
        passed = (
            shared
            and planes.get("default-export") == "humanize-string"
            and planes.get("default-export-object") == "query-string"
            and planes.get("default-export-class") == "markdown-it"
            and absent is None
        )
    except Exception as exc:
        observed = {"error": f"{type(exc).__name__}: {exc}"}
        passed = False
    return {"observed": observed, "passed": passed}


def main() -> int:
    print(json.dumps(outcome(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
