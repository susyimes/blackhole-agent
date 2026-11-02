"""Acceptance: a numeric depth with no copied catalog record still runs.

Depth 160 is the leftover marker for one hundred sixty submodule levels.
The copied quindecuple-and-later table stopped at 159. passed is true only
when that depth describes its historical capability, invoking the instance
method returns AB, and the quindecuple plane keeps its original winner.
"""

from __future__ import annotations

import json


def main() -> None:
    observed: dict[str, object] = {}
    passed = False
    try:
        import blackhole_agent.capability_application_growth as growth

        describe = growth.describe_nested_instance_plane
        invoke = growth.invoke_described_nested_instance_plane
        spec = describe(160)
        historical = describe("quindecuple")
        invoked = invoke(160)
        observed["capability_id"] = spec.get("capability_id")
        observed["depth"] = spec.get("depth")
        observed["modules"] = len(tuple(spec.get("modules") or ()))
        observed["stored_record"] = spec.get("stored_record")
        observed["invoked"] = invoked
        observed["quindecuple_capability_id"] = historical.get("capability_id")
        observed["quindecuple_winner"] = historical.get("winner")
        observed["quindecuple_stored"] = historical.get("stored_record")
        passed = (
            spec.get("capability_id")
            == "capability.application-python-sexaginticent-nested-instance-growth-plane"
            and spec.get("depth") == 160
            and observed["modules"] == 160
            and spec.get("stored_record") is False
            and invoked == "AB"
            and historical.get("capability_id")
            == "capability.application-python-quind-nested-instance-growth-plane"
            and str(historical.get("winner") or "").endswith("boson.Codec.encode")
            and historical.get("stored_record") is True
        )
    except Exception as exc:  # noqa: BLE001 - baseline must report, not crash
        observed["error"] = f"{type(exc).__name__}: {exc}"[:300]
    print(json.dumps({"passed": passed, "observed": observed}))


if __name__ == "__main__":
    main()
