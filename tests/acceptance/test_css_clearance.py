"""Signed CSS clearance puts the used top edge on the cleared float bottom.

A previous margin of 4 and a top margin of 3 collapse to a hypothetical
edge at 5. A float bottom two units below that edge yields clearance -1
and a used edge at 7. A float bottom at 19 against a previous margin of 10
and a top margin of 3 yields clearance 5, which is the float height 8
minus the top margin. An edge already on or past the float bottom, clear
none, and a float on the uncleared side leave clearance at 0. An empty
collapsed-through block, an unknown clear, a missing element, and a
non-integer float bottom are invalid.

Prints JSON with boolean passed and nonempty observed. Exit 0 either way.
"""

from __future__ import annotations

import json


def _flow(previous: int, top: int) -> dict[str, object]:
    return {
        "id": "root",
        "children": [
            {"id": "b1", "margin_bottom": previous, "height": 1},
            {"id": "b2", "margin_top": top, "height": 1},
        ],
    }


def _resolved(
    result: object,
    *,
    introduced: bool,
    clearance: int,
    hypothetical: int,
    separated: int | None,
    used: int,
    floor: int | None,
) -> bool:
    return (
        isinstance(result, dict)
        and result.get("outcome") == "resolved"
        and result.get("introduced") is introduced
        and result.get("clearance") == clearance
        and result.get("hypothetical_border") == hypothetical
        and result.get("separated_border") == separated
        and result.get("used_border") == used
        and result.get("float_bottom") == floor
    )


def _invalid(result: object, reason: str) -> bool:
    return (
        isinstance(result, dict)
        and result.get("outcome") == "invalid"
        and result.get("reason") == reason
        and result.get("clearance") is None
        and result.get("used_border") is None
    )


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_clearance import resolve_clearance
    except Exception as exc:  # noqa: BLE001 - a tree without clearance still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    negative = _flow(4, 3)
    positive = _flow(10, 3)
    past = _flow(1, 10)
    pulled = _flow(-4, 2)
    parent = {
        "id": "root",
        "border_top": 1,
        "children": [{"id": "c", "margin_top": 3, "height": 1}],
    }
    empty = {
        "id": "root",
        "children": [
            {"id": "b1", "margin_bottom": 4, "height": 1},
            {"id": "b2", "margin_top": 3},
        ],
    }
    untouched = _flow(4, 3)
    calls = [
        ("negative_spec", negative, "b2", "left", [{"side": "left", "bottom": 7}]),
        ("positive_flush", positive, "b2", "both", [{"side": "left", "bottom": 19}]),
        ("already_even", negative, "b2", "left", [{"side": "left", "bottom": 5}]),
        ("already_past", past, "b2", "both", [{"side": "left", "bottom": 4}]),
        ("clear_none", negative, "b2", "none", [{"side": "left", "bottom": 100}]),
        ("uncleared_side", negative, "b2", "left", [{"side": "right", "bottom": 100}]),
        ("both_sides", negative, "b2", "both", [{"side": "left", "bottom": 6}, {"side": "right", "bottom": 12}]),
        ("negative_margin", pulled, "b2", "left", [{"side": "left", "bottom": 0}]),
        ("parent_border", parent, "c", "left", [{"side": "left", "bottom": 20}]),
    ]
    expected = {
        "negative_spec": (True, -1, 5, 8, 7, 7),
        "positive_flush": (True, 5, 11, 14, 19, 19),
        "already_even": (False, 0, 5, None, 5, 5),
        "already_past": (False, 0, 11, None, 11, 4),
        "clear_none": (False, 0, 5, None, 5, None),
        "uncleared_side": (False, 0, 5, None, 5, None),
        "both_sides": (True, 4, 5, 8, 12, 12),
        "negative_margin": (True, 1, -1, -1, 0, 0),
        "parent_border": (True, 16, 4, 4, 20, 20),
    }
    observed: dict[str, object] = {}
    checks: list[bool] = []
    for name, box, element, clear, floats in calls:
        result = resolve_clearance(box, element=element, clear=clear, floats=floats)
        introduced, clearance, hypothetical, separated, used, floor = expected[name]
        observed[name] = {
            "outcome": result.get("outcome"),
            "introduced": result.get("introduced"),
            "clearance": result.get("clearance"),
            "hypothetical_border": result.get("hypothetical_border"),
            "separated_border": result.get("separated_border"),
            "used_border": result.get("used_border"),
            "float_bottom": result.get("float_bottom"),
        }
        checks.append(
            _resolved(
                result,
                introduced=introduced,
                clearance=clearance,
                hypothetical=hypothetical,
                separated=separated,
                used=used,
                floor=floor,
            )
        )
    rejected = {
        "collapsed_through": (empty, "b2", "left", [{"side": "left", "bottom": 7}], "collapsed-through"),
        "unknown_clear": (negative, "b2", "inherit", [{"side": "left", "bottom": 7}], "clear"),
        "missing_element": (negative, "missing", "left", [{"side": "left", "bottom": 7}], "element"),
        "fractional_bottom": (negative, "b2", "left", [{"side": "left", "bottom": 7.0}], "float"),
    }
    for name, (box, element, clear, floats, reason) in rejected.items():
        result = resolve_clearance(box, element=element, clear=clear, floats=floats)
        observed[name] = {"outcome": result.get("outcome"), "reason": result.get("reason")}
        checks.append(_invalid(result, reason))
    before = json.dumps(untouched, sort_keys=True)
    resolve_clearance(untouched, element="b2", clear="left", floats=[{"side": "left", "bottom": 7}])
    observed["input_unchanged"] = json.dumps(untouched, sort_keys=True) == before
    checks.append(observed["input_unchanged"] is True)
    return all(checks), observed


def main() -> int:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - unmet behavior and baseline both exit 0
        passed, observed = False, {"error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps({"passed": bool(passed), "observed": observed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
