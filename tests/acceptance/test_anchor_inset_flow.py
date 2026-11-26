"""Line an absolute margin edge up with an anchor() inset.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A layout that still rejects anchor() as an illegal length
reports passed false.
"""

from __future__ import annotations

import json

_PAGE = '<div id="card"></div><div id="tip"></div><div id="next"></div>'
_RIGHT = (
    _PAGE,
    "#card { anchor-name: --card; width: 40px; height: 20px; }"
    "#tip { position: absolute; position-anchor: --card; left: anchor(right);"
    " top: anchor(top); width: 10px; height: 8px; margin-left: 4px; }"
    "#next { width: 10px; height: 10px; }",
)
_CENTER = (
    _PAGE,
    "#card { anchor-name: --card; width: 40px; height: 20px; }"
    "#tip { position: absolute; left: anchor(--card left); top: anchor(--card center);"
    " width: 10px; height: 8px; }"
    "#next { width: 10px; height: 10px; }",
)
_PERCENT = (
    _PAGE,
    "#card { anchor-name: --card; width: 40px; height: 20px; }"
    "#tip { position: absolute; position-anchor: --card; left: anchor(100%);"
    " top: anchor(0%); width: 10px; height: 8px; }"
    "#next { width: 10px; height: 10px; }",
)
_FIXED = (
    _PAGE,
    "#card { anchor-name: --card; width: 40px; height: 20px; }"
    "#tip { position: fixed; position-anchor: --card; left: anchor(right);"
    " top: anchor(top); width: 10px; height: 8px; }"
    "#next { width: 10px; height: 10px; }",
)
_RELATIVE = (
    _PAGE,
    "#card { anchor-name: --card; position: relative; left: 3px; top: 5px;"
    " width: 40px; height: 20px; }"
    "#tip { position: absolute; position-anchor: --card; left: anchor(right);"
    " top: anchor(top); width: 10px; height: 8px; }"
    "#next { width: 10px; height: 10px; }",
)
_FALLBACK = (
    '<div id="tip"></div><div id="next"></div>',
    "#tip { position: absolute; left: anchor(right, 15px); top: 6px;"
    " width: 10px; height: 8px; }"
    "#next { width: 12px; height: 9px; }",
)
_WRONG_AXIS = (
    _PAGE,
    "#card { anchor-name: --card; width: 40px; height: 20px; }"
    "#tip { position: absolute; position-anchor: --card; left: anchor(top);"
    " top: 0px; width: 10px; height: 8px; }",
)
_WRONG_FALLBACK = (
    _PAGE,
    "#card { anchor-name: --card; width: 40px; height: 20px; }"
    "#tip { position: absolute; position-anchor: --card; left: anchor(top, 12px);"
    " top: 0px; width: 10px; height: 8px; }"
    "#next { width: 10px; height: 10px; }",
)
_MISSING = (
    _PAGE,
    "#card { width: 40px; height: 20px; }"
    "#tip { position: absolute; left: anchor(right); top: 0px;"
    " width: 10px; height: 8px; }",
)
_STATIC = (
    '<div id="card"></div>',
    "#card { left: anchor(right); width: 40px; height: 20px; }",
)
_FLOAT = (
    '<div id="card"></div><div id="tip"></div>',
    "#card { anchor-name: --card; float: left; width: 40px; height: 20px; }"
    "#tip { position: absolute; position-anchor: --card; left: anchor(right);"
    " top: anchor(top); width: 10px; height: 8px; }",
)
_INSIDE = (
    '<div id="tip"><div id="card"></div></div>',
    "#tip { position: absolute; position-anchor: --card; left: anchor(right);"
    " top: 0px; width: 80px; height: 40px; }"
    "#card { anchor-name: --card; width: 10px; height: 10px; }",
)


def _place(function, markup: str, stylesheet: str, *, height: int | None = 300) -> dict[str, object]:
    try:
        kwargs = {"viewport_width": 400}
        if height is not None:
            kwargs["viewport_height"] = height
        result = function(markup, stylesheet, **kwargs)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}"}
    if not isinstance(result, dict):
        return {"outcome": "error", "reason": "result"}
    return result


def _box(result: dict[str, object], box_id: str) -> dict[str, object] | None:
    boxes = result.get("boxes")
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if isinstance(item, dict) and item.get("id") == box_id:
            return item
    return None


def _edge(box: dict[str, object] | None) -> dict[str, object] | None:
    if box is None:
        return None
    return {
        "x": box.get("x"),
        "y": box.get("y"),
        "border_width": box.get("border_width"),
        "border_height": box.get("border_height"),
    }


def _number(value: object) -> int | None:
    if type(value) is bool or not isinstance(value, (int, float)):
        return None
    return int(value)


def _meets(card: dict[str, object] | None, tip: dict[str, object] | None, dx: int, dy: int) -> bool:
    if card is None or tip is None:
        return False
    card_x, card_y = _number(card.get("x")), _number(card.get("y"))
    card_w, card_h = _number(card.get("border_width")), _number(card.get("border_height"))
    tip_x, tip_y = _number(tip.get("x")), _number(tip.get("y"))
    tip_w, tip_h = _number(tip.get("border_width")), _number(tip.get("border_height"))
    if None in {card_x, card_y, card_w, card_h, tip_x, tip_y, tip_w, tip_h}:
        return False
    return tip_x == card_x + dx and tip_y == card_y + dy and tip_w == 10 and tip_h == 8


def _follows(card: dict[str, object] | None, nxt: dict[str, object] | None, dx: int, dy: int) -> bool:
    if card is None or nxt is None:
        return False
    card_x, card_y = _number(card.get("x")), _number(card.get("y"))
    card_h = _number(card.get("border_height"))
    next_x, next_y = _number(nxt.get("x")), _number(nxt.get("y"))
    if None in {card_x, card_y, card_h, next_x, next_y}:
        return False
    return next_x == card_x - dx and next_y == card_y - dy + card_h


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - a tree without the layout still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}
    checks: list[bool] = []

    def layout(name: str, markup: str, stylesheet: str) -> dict[str, object]:
        result = _place(layout_normal_flow, markup, stylesheet)
        observed[name] = {
            "outcome": result.get("outcome"),
            "reason": result.get("reason"),
            "card": _edge(_box(result, "card")),
            "tip": _edge(_box(result, "tip")),
            "next": _edge(_box(result, "next")),
        }
        return result

    right = layout("margin_edge", *_RIGHT)
    right_card, right_tip = _box(right, "card"), _box(right, "tip")
    checks.append(right.get("outcome") == "placed")
    checks.append(_meets(right_card, right_tip, 44, 0))
    checks.append(_follows(right_card, _box(right, "next"), 0, 0))

    center = layout("center", *_CENTER)
    center_card = _box(center, "card")
    checks.append(center.get("outcome") == "placed")
    checks.append(_meets(center_card, _box(center, "tip"), 0, 10))
    checks.append(_follows(center_card, _box(center, "next"), 0, 0))

    percent = layout("percentage", *_PERCENT)
    percent_card = _box(percent, "card")
    checks.append(percent.get("outcome") == "placed")
    checks.append(_meets(percent_card, _box(percent, "tip"), 40, 0))

    fixed = layout("fixed", *_FIXED)
    fixed_card = _box(fixed, "card")
    checks.append(fixed.get("outcome") == "placed")
    checks.append(_meets(fixed_card, _box(fixed, "tip"), 40, 0))
    checks.append(_follows(fixed_card, _box(fixed, "next"), 0, 0))

    relative = layout("relative_anchor", *_RELATIVE)
    relative_card = _box(relative, "card")
    checks.append(relative.get("outcome") == "placed")
    checks.append(_meets(relative_card, _box(relative, "tip"), 40, 0))
    checks.append(_follows(relative_card, _box(relative, "next"), 3, 5))

    fallback = layout("missing_fallback", *_FALLBACK)
    fallback_tip, fallback_next = _box(fallback, "tip"), _box(fallback, "next")
    checks.append(fallback.get("outcome") == "placed")
    checks.append(_edge(fallback_tip) == {"x": 15, "y": 6, "border_width": 10, "border_height": 8})
    checks.append(_edge(fallback_next) == {"x": 0, "y": 0, "border_width": 12, "border_height": 9})

    wrong = layout("wrong_axis", *_WRONG_AXIS)
    checks.append(wrong.get("outcome") == "invalid")
    checks.append(wrong.get("reason") == "anchor() side is on the wrong axis")

    rescued = layout("wrong_axis_fallback", *_WRONG_FALLBACK)
    rescued_tip = _box(rescued, "tip")
    checks.append(rescued.get("outcome") == "placed")
    checks.append(_number(None if rescued_tip is None else rescued_tip.get("x")) == 12)
    checks.append(_follows(_box(rescued, "card"), _box(rescued, "next"), 0, 0))

    missing = layout("missing_anchor", *_MISSING)
    checks.append(missing.get("outcome") == "invalid")
    checks.append(missing.get("reason") == "default anchor is missing")

    static = layout("static_box", *_STATIC)
    checks.append(static.get("outcome") == "invalid")
    checks.append(static.get("reason") == "anchor() is unsupported")

    floated = layout("float_anchor", *_FLOAT)
    checks.append(floated.get("outcome") == "invalid")
    checks.append(floated.get("reason") == "anchor is out of flow")

    inside = layout("anchor_inside", *_INSIDE)
    checks.append(inside.get("outcome") == "invalid")
    checks.append(inside.get("reason") == "anchor is inside the positioned box")

    observed["checks"] = checks
    return all(checks), observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
