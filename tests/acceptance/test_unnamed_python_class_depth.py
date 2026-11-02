"""A class instance method past the latin prefix table is still invoked.

The same probe runs against the previous milestone source and the candidate
source. It exits 0 either way and prints JSON with boolean passed plus a
nonempty observed object.
"""

from __future__ import annotations

import json


def main() -> int:
    observed: dict[str, object] = {"reflector": "missing"}
    passed = False
    try:
        from blackhole_agent.capability_foraging import reflect_python_class_instance_depth
    except Exception as exc:  # noqa: BLE001 - baseline source has no reflector
        observed = {"reflector": "missing", "error": type(exc).__name__}
        print(json.dumps({"passed": False, "observed": observed}))
        return 0
    try:
        named = reflect_python_class_instance_depth(4)
        unnamed = reflect_python_class_instance_depth(160)
    except Exception as exc:  # noqa: BLE001 - a crash is an unmet outcome, not a probe failure
        observed = {"reflector": "present", "error": type(exc).__name__, "detail": str(exc)[:300]}
        print(json.dumps({"passed": False, "observed": observed}))
        return 0
    observed = {
        "named_depth": named.get("depth"),
        "named_invoked": named.get("invoked"),
        "named_latin": named.get("latin_instance_flag"),
        "unnamed_depth": unnamed.get("depth"),
        "unnamed_invoked": unnamed.get("invoked"),
        "unnamed_latin": unnamed.get("latin_instance_flag"),
        "unnamed_past_table": unnamed.get("past_named_table"),
        "named_error": named.get("error") or "",
        "unnamed_error": unnamed.get("error") or "",
    }
    passed = bool(
        named.get("ok")
        and named.get("depth") == 4
        and named.get("invoked") == "AB"
        and named.get("latin_instance_flag") is True
        and unnamed.get("ok")
        and unnamed.get("depth") == 160
        and unnamed.get("invoked") == "AB"
        and unnamed.get("latin_instance_flag") is False
        and unnamed.get("past_named_table") is True
    )
    print(json.dumps({"passed": passed, "observed": observed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
