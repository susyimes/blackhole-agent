"""An integer constructor no longer hides the instance method.

``Codec.__init__(self, width)`` stores ``int(width)``. Introspection that only
tries ``()``, ``{}``, and ``""`` never sees ``encode``. The same probe runs
against the previous milestone source and the candidate source. It exits 0
either way and prints JSON with boolean passed plus a nonempty observed object.
"""

from __future__ import annotations

import json


def main() -> int:
    observed: dict[str, object] = {}
    passed = False
    try:
        from blackhole_agent.capability_foraging import reflect_required_constructor_method

        result = reflect_required_constructor_method()
        observed = {
            "required_visible": result.get("required_visible"),
            "required_trial": result.get("required_trial"),
            "required_invoked": result.get("required_invoked"),
            "required_error": result.get("required_error"),
            "zero_visible": result.get("zero_visible"),
            "zero_trial": result.get("zero_trial"),
            "zero_invoked": result.get("zero_invoked"),
            "zero_error": result.get("zero_error"),
        }
        passed = (
            result.get("ok") is True
            and observed["required_visible"] is True
            and observed["required_trial"] == "int"
            and observed["required_invoked"] == "AB1"
            and observed["zero_visible"] is True
            and observed["zero_trial"] == "none"
            and observed["zero_invoked"] == "AB"
        )
    except Exception as exc:
        observed = {"error": type(exc).__name__, "detail": str(exc)[:500]}
        passed = False
    print(json.dumps({"passed": passed, "observed": observed}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
