"""Acceptance: uniform nested instance planes are one factory, not one copy each.

The probe prints JSON and exits 0 for both the old copied module and the
factory. passed is true only when the quindecuple plane still names its
historical capability and winner and the module is under 25000 lines.
"""

from __future__ import annotations

import json


def main() -> None:
    observed: dict[str, object] = {}
    passed = False
    try:
        import blackhole_agent.capability_application_growth as growth
    except Exception as exc:  # noqa: BLE001 - baseline must report, not crash
        observed["import_error"] = type(exc).__name__
        print(json.dumps({"passed": False, "observed": observed}))
        return
    path = growth.__file__
    with open(path, encoding="utf-8") as handle:
        observed["lines"] = sum(1 for _ in handle)
    describe = getattr(growth, "describe_nested_instance_plane", None)
    replay = getattr(
        growth,
        "replay_application_python_quindecuple_nested_namespace_class_instance_growth_plane_proof",
        None,
    )
    observed["describe_present"] = callable(describe)
    observed["replay_present"] = callable(replay)
    if callable(describe):
        spec = describe("quindecuple")
        observed["capability_id"] = spec.get("capability_id")
        observed["winner"] = spec.get("winner")
        expected = getattr(
            growth,
            "PYTHON_QUINDECUPLE_NESTED_NAMESPACE_CLASS_INSTANCE_CALLABLE",
            None,
        )
        observed["winner_matches"] = spec.get("winner") == expected and bool(expected)
        passed = (
            isinstance(observed["lines"], int)
            and observed["lines"] < 25000
            and spec.get("capability_id")
            == "capability.application-python-quind-nested-instance-growth-plane"
            and observed["winner_matches"] is True
            and callable(replay)
        )
    print(json.dumps({"passed": passed, "observed": observed}))


if __name__ == "__main__":
    main()
