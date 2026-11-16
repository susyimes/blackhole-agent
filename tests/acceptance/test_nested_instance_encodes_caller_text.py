"""The nested-instance invoker encodes the caller's text.

invoke_described_nested_instance_plane used to ignore its text argument and
return AB for every string. The default argument ab must still return AB.
A non-string is an empty result and does not raise.

Prints JSON with boolean passed and nonempty observed. Exits 0 for both met
and unmet outcomes so the controller can replay this probe on baseline and
candidate source.
"""

from __future__ import annotations

import json


def main() -> None:
    observed: dict[str, object] = {}
    passed = False
    try:
        from blackhole_agent.capability_application_growth import (
            invoke_described_nested_instance_plane,
        )

        hello = invoke_described_nested_instance_plane(4, "Hello")
        other = invoke_described_nested_instance_plane(2, "xy")
        default = invoke_described_nested_instance_plane(3)
        refused = invoke_described_nested_instance_plane(3, 1)  # type: ignore[arg-type]
        observed = {
            "hello": hello,
            "other": other,
            "default": default,
            "refused": refused,
        }
        passed = hello == "HELLO" and other == "XY" and default == "AB" and refused == ""
    except Exception as exc:  # noqa: BLE001 - baseline must report, not crash
        observed = {"error": f"{type(exc).__name__}: {exc}"[:300]}
        passed = False
    print(json.dumps({"passed": passed, "observed": observed}, sort_keys=True))


if __name__ == "__main__":
    main()
