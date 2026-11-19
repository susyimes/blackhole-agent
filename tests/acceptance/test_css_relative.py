"""Relative offsets move one box and leave the next static position alone.

A box at the origin with left 10 and right auto is used at x 10, with
right -10. The following static box that starts at y 20 stays at y 20
even when it also specifies left. Left 10 and right 4 keep left in ltr
and keep right in rtl. Top 8 and bottom 3 keep top. A top percentage
against an automatic containing height becomes auto, so a bottom of 6
pulls the box up by 6. An unknown position, an unknown direction, and a
boolean inset are invalid.

Prints JSON with boolean passed and nonempty observed. Exit 0 either way.
"""

from __future__ import annotations

import json


def _box(**fields: object) -> dict[str, object]:
    box: dict[str, object] = {
        "id": "a",
        "position": "relative",
        "x": 0,
        "y": 0,
        "width": 40,
        "height": 20,
        "direction": "ltr",
        "left": "auto",
        "right": "auto",
        "top": "auto",
        "bottom": "auto",
    }
    box.update(fields)
    return box


def _placed(result: object, expected: dict[str, object]) -> bool:
    if not isinstance(result, dict) or result.get("outcome") != "placed":
        return False
    boxes = result.get("boxes")
    if not isinstance(boxes, list):
        return False
    found = next((box for box in boxes if isinstance(box, dict) and box.get("id") == expected["id"]), None)
    if not isinstance(found, dict):
        return False
    return all(found.get(key) == value for key, value in expected.items())


def _invalid(result: object, reason: str) -> bool:
    return (
        isinstance(result, dict)
        and result.get("outcome") == "invalid"
        and result.get("reason") == reason
        and result.get("boxes") is None
    )


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_relative import place_relative
    except Exception as exc:  # noqa: BLE001 - baseline without the module still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    checks: list[bool] = []
    observed: dict[str, object] = {}
    flow = [
        _box(id="a", left=10, right="auto"),
        _box(id="b", position="static", x=0, y=20, left=50, direction="nope"),
    ]
    shifted = place_relative(flow, containing_width=200, containing_height="auto")
    observed["shifted"] = shifted.get("boxes") if isinstance(shifted, dict) else shifted
    checks.append(
        _placed(
            shifted,
            {
                "id": "a",
                "x": 10,
                "y": 0,
                "width": 40,
                "height": 20,
                "left": 10,
                "right": -10,
                "top": 0,
                "bottom": 0,
                "static_x": 0,
                "static_y": 0,
            },
        )
    )
    checks.append(
        _placed(
            shifted,
            {
                "id": "b",
                "x": 0,
                "y": 20,
                "left": 0,
                "right": 0,
                "top": 0,
                "bottom": 0,
                "static_y": 20,
            },
        )
    )

    cases = {
        "pull_left": (
            [_box(left="auto", right=10)],
            {"id": "a", "x": -10, "left": -10, "right": 10},
        ),
        "ltr_keeps_left": (
            [_box(left=10, right=4, direction="ltr")],
            {"id": "a", "x": 10, "left": 10, "right": -10},
        ),
        "rtl_keeps_right": (
            [_box(left=10, right=4, direction="rtl")],
            {"id": "a", "x": -4, "left": -4, "right": 4},
        ),
        "top_wins": (
            [_box(top=8, bottom=3)],
            {"id": "a", "y": 8, "top": 8, "bottom": -8},
        ),
        "percent_left": (
            [_box(left="10%")],
            {"id": "a", "x": 20, "left": 20, "right": -20},
        ),
        "percent_top_auto_height": (
            [_box(top="25%", bottom=6)],
            {"id": "a", "y": -6, "top": -6, "bottom": 6},
        ),
        "percent_top_definite": (
            [_box(top="25%")],
            {"id": "a", "y": 20, "top": 20, "bottom": -20},
        ),
    }
    for name, (boxes, expected) in cases.items():
        height = 80 if name == "percent_top_definite" else "auto"
        result = place_relative(boxes, containing_width=200, containing_height=height)
        observed[name] = result.get("boxes") if isinstance(result, dict) else result
        checks.append(_placed(result, expected))

    invalids = {
        "position": ( [_box(position="sticky")], "position must be static or relative"),
        "direction": ( [_box(direction="auto")], "direction must be ltr or rtl"),
        "inset": ( [_box(left=True)], "left must be a length, a percentage, or auto"),
    }
    for name, (boxes, reason) in invalids.items():
        result = place_relative(boxes, containing_width=200)
        observed[name] = {"outcome": result.get("outcome"), "reason": result.get("reason")}
        checks.append(_invalid(result, reason))

    untouched = [_box(left=10)]
    before = json.dumps(untouched, sort_keys=True)
    place_relative(untouched, containing_width=200)
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
