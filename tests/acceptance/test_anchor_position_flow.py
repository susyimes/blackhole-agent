"""Place an absolute box on the border box of its named anchor.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A layout that still ignores position-area reports passed
false.
"""

from __future__ import annotations

import json

_PAGE = '<div id="card"></div><div id="tip"></div><div id="next"></div>'
_BLOCK = (
    _PAGE,
    "#card { anchor-name: --card; width: 40px; height: 20px; }"
    "#tip { position: absolute; position-anchor: --card; position-area: block-start;"
    " left: 100px; top: 80px; width: 50px; height: 30px; margin-bottom: 4px; }"
    "#next { width: 10px; height: 10px; }",
)
_INLINE = (
    _PAGE,
    "#card { anchor-name: --card; width: 40px; height: 20px; }"
    "#tip { position: absolute; position-anchor: --card; position-area: inline-end;"
    " left: 100px; top: 80px; width: 10px; height: 8px; }"
    "#next { width: 10px; height: 10px; }",
)
_FIXED = (
    _PAGE,
    "#card { anchor-name: --card; width: 40px; height: 20px; }"
    "#tip { position: fixed; position-anchor: --card; position-area: inline-end;"
    " width: 10px; height: 8px; }"
    "#next { width: 10px; height: 10px; }",
)
_RELATIVE = (
    _PAGE,
    "#card { anchor-name: --card; position: relative; left: 3px; top: 5px;"
    " width: 40px; height: 20px; }"
    "#tip { position: absolute; position-anchor: --card; position-area: block-start;"
    " left: 100px; top: 80px; width: 50px; height: 30px; margin-bottom: 4px; }"
    "#next { width: 10px; height: 10px; }",
)
_PLAIN = (
    '<div id="tip"></div>',
    "#tip { position: absolute; left: 8px; top: 6px; width: 10px; height: 12px; }",
)
_MISSING = (
    _PAGE,
    "#card { width: 40px; height: 20px; }"
    "#tip { position: absolute; position-anchor: --missing; position-area: block-start;"
    " width: 10px; height: 10px; }",
)
_DUPLICATE = (
    '<div id="card"></div><div id="next"></div>',
    "#card { anchor-name: --card; width: 40px; height: 20px; }"
    "#next { anchor-name: --card; width: 10px; height: 10px; }",
)
_STATIC = (
    '<div id="card"></div>',
    "#card { position-anchor: --card; position-area: block-start; width: 40px; height: 20px; }",
)
_FLOAT = (
    '<div id="card">A</div><div id="tip"></div>',
    "#card { anchor-name: --card; float: left; width: 40px; height: 20px; }"
    "#tip { position: absolute; position-anchor: --card; position-area: block-start;"
    " width: 10px; height: 10px; }",
)
_INSIDE = (
    '<div id="tip"><div id="card"></div></div>',
    "#tip { position: absolute; position-anchor: --card; position-area: block-start;"
    " width: 80px; height: 40px; }"
    "#card { anchor-name: --card; width: 10px; height: 10px; }",
)
_INDEFINITE = (
    '<div id="card"></div><div id="tip"></div>',
    "#card { anchor-name: --card; width: 40px; height: 20px; }"
    "#tip { position: absolute; position-anchor: --card; position-area: block-start;"
    " width: 10px; height: 10px; }",
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


def _meets_block_start(card: dict[str, object] | None, tip: dict[str, object] | None, margin: int) -> bool:
    if card is None or tip is None:
        return False
    card_x, card_y = _number(card.get("x")), _number(card.get("y"))
    card_w, card_h = _number(card.get("border_width")), _number(card.get("border_height"))
    tip_x, tip_y = _number(tip.get("x")), _number(tip.get("y"))
    tip_w, tip_h = _number(tip.get("border_width")), _number(tip.get("border_height"))
    if None in {card_x, card_y, card_w, card_h, tip_x, tip_y, tip_w, tip_h}:
        return False
    centered = 2 * tip_x + tip_w == 2 * card_x + card_w
    meets = tip_y + tip_h + margin == card_y
    return centered and meets and tip_w == 50 and tip_h == 30


def _meets_inline_end(card: dict[str, object] | None, tip: dict[str, object] | None) -> bool:
    if card is None or tip is None:
        return False
    card_x, card_y = _number(card.get("x")), _number(card.get("y"))
    card_w, card_h = _number(card.get("border_width")), _number(card.get("border_height"))
    tip_x, tip_y = _number(tip.get("x")), _number(tip.get("y"))
    tip_w, tip_h = _number(tip.get("border_width")), _number(tip.get("border_height"))
    if None in {card_x, card_y, card_w, card_h, tip_x, tip_y, tip_w, tip_h}:
        return False
    centered = 2 * tip_y + tip_h == 2 * card_y + card_h
    meets = tip_x == card_x + card_w
    return centered and meets and tip_w == 10 and tip_h == 8


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

    def layout(name: str, markup: str, stylesheet: str, *, height: int | None = 300) -> dict[str, object]:
        result = _place(layout_normal_flow, markup, stylesheet, height=height)
        observed[name] = {
            "outcome": result.get("outcome"),
            "reason": result.get("reason"),
            "card": _edge(_box(result, "card")),
            "tip": _edge(_box(result, "tip")),
            "next": _edge(_box(result, "next")),
        }
        return result

    block = layout("block_start", *_BLOCK)
    block_card, block_tip = _box(block, "card"), _box(block, "tip")
    checks.append(block.get("outcome") == "placed")
    checks.append(_meets_block_start(block_card, block_tip, 4))
    checks.append(_follows(block_card, _box(block, "next"), 0, 0))
    checks.append(_number(None if block_tip is None else block_tip.get("x")) != 100)

    inline = layout("inline_end", *_INLINE)
    checks.append(inline.get("outcome") == "placed")
    checks.append(_meets_inline_end(_box(inline, "card"), _box(inline, "tip")))
    checks.append(_follows(_box(inline, "card"), _box(inline, "next"), 0, 0))

    fixed = layout("fixed_inline_end", *_FIXED)
    checks.append(fixed.get("outcome") == "placed")
    checks.append(_meets_inline_end(_box(fixed, "card"), _box(fixed, "tip")))

    relative = layout("relative_anchor", *_RELATIVE)
    checks.append(relative.get("outcome") == "placed")
    checks.append(_meets_block_start(_box(relative, "card"), _box(relative, "tip"), 4))
    checks.append(_follows(_box(relative, "card"), _box(relative, "next"), 3, 5))

    plain = layout("specified_insets", *_PLAIN)
    plain_tip = _box(plain, "tip")
    checks.append(plain.get("outcome") == "placed")
    checks.append(_edge(plain_tip) == {"x": 8, "y": 6, "border_width": 10, "border_height": 12})

    missing = layout("missing_anchor", *_MISSING)
    checks.append(missing.get("outcome") == "invalid")
    checks.append(missing.get("reason") == "default anchor is missing")

    duplicate = layout("duplicate_anchor", *_DUPLICATE)
    checks.append(duplicate.get("outcome") == "invalid")
    checks.append(duplicate.get("reason") == "anchor-name is duplicated")

    static = layout("static_area", *_STATIC)
    checks.append(static.get("outcome") == "invalid")
    checks.append(static.get("reason") == "position-area is unsupported")

    floated = layout("float_anchor", *_FLOAT)
    checks.append(floated.get("outcome") == "invalid")
    checks.append(floated.get("reason") == "anchor is out of flow")

    inside = layout("anchor_inside", *_INSIDE)
    checks.append(inside.get("outcome") == "invalid")
    checks.append(inside.get("reason") == "anchor is inside the positioned box")

    indefinite = layout("indefinite_viewport", *_INDEFINITE, height=None)
    checks.append(indefinite.get("outcome") == "invalid")
    checks.append(indefinite.get("reason") == "anchor containing block is indefinite")

    observed["checks"] = checks
    return all(checks), observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
