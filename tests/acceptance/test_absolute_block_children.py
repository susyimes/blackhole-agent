"""Lay static block children inside an absolutely positioned box.

A 50px-wide absolute box at left 30px and top 40px, with 7px padding-left and
5px padding-top, wraps its child's breakable text to that content width. The
child's 8px top margin and 4px bottom margin stay inside the absolute box, so
the automatic content height is 72px and the first line starts at x 37, y 53.
Two later children collapse a 10px bottom margin with a 30px top margin into
one 30px gap. The following in-flow block stays at y 0. A float child and a
shrink-to-fit absolute that contains a block child are rejected.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A layout that still rejects the child exits 0 with passed
false.
"""

from __future__ import annotations

import json

_WRAP = (
    '<div id="page"><div id="abs"><div id="copy">AB CD EF GH IJ</div></div>'
    '<div id="next">Z</div></div>'
)
_WRAP_CSS = """
#page { position: relative; }
#page, #copy, #next { font-size: 10px; line-height: 20px; }
#abs { position: absolute; left: 30px; top: 40px; width: 50px; padding-top: 5px; padding-left: 7px; }
#copy { margin-top: 8px; margin-bottom: 4px; }
"""
_PAIR = (
    '<div id="page"><div id="abs"><div id="a">ABCDE</div><div id="b">FGHIJ</div></div>'
    '<div id="next">Z</div></div>'
)
_PAIR_CSS = """
#page { position: relative; }
#a, #b, #next { font-size: 10px; line-height: 20px; }
#abs { position: absolute; left: 0px; top: 0px; width: 50px; }
#a { margin-top: 6px; margin-bottom: 10px; }
#b { margin-top: 30px; }
"""
_FLOAT = '<div id="page"><div id="abs"><div id="flo">Hi</div></div></div>'
_FLOAT_CSS = """
#flo { float: left; width: 10px; height: 10px; }
#abs { position: absolute; left: 0px; top: 0px; width: 40px; }
"""
_SHRINK = '<div id="page"><div id="abs"><div id="copy">Hello</div></div></div>'
_SHRINK_CSS = """
#abs { position: absolute; top: 0px; }
#copy { font-size: 10px; }
"""


def _box(boxes: object, ident: str) -> dict[str, object] | None:
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if isinstance(item, dict) and item.get("id") == ident:
            return item
    return None


def _line(box: dict[str, object] | None, index: int) -> dict[str, object] | None:
    if box is None or not isinstance(box.get("lines"), list):
        return None
    lines = box["lines"]
    if index >= len(lines) or not isinstance(lines[index], dict):
        return None
    return lines[index]


def _near(item: dict[str, object] | None, **expected: object) -> bool:
    if item is None:
        return False
    return all(item.get(key) == value for key, value in expected.items())


def _lay(layout, markup: str, stylesheet: str) -> dict[str, object]:
    try:
        placed = layout(markup, stylesheet, viewport_width=200)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without the layout still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    wrapped = _lay(layout_normal_flow, _WRAP, _WRAP_CSS)
    paired = _lay(layout_normal_flow, _PAIR, _PAIR_CSS)
    floated = _lay(layout_normal_flow, _FLOAT, _FLOAT_CSS)
    shrink = _lay(layout_normal_flow, _SHRINK, _SHRINK_CSS)
    boxes = wrapped.get("boxes")
    pair_boxes = paired.get("boxes")
    copy = _box(boxes, "copy")
    absolute = _box(boxes, "abs")
    nxt = _box(boxes, "next")
    page = _box(boxes, "page")
    observed: dict[str, object] = {
        "wrap_outcome": wrapped.get("outcome"),
        "wrap_reason": wrapped.get("reason"),
        "absolute": absolute,
        "copy": copy,
        "copy_lines": None if copy is None else copy.get("lines"),
        "next": nxt,
        "page": page,
        "pair_outcome": paired.get("outcome"),
        "pair_a": _box(pair_boxes, "a"),
        "pair_b": _box(pair_boxes, "b"),
        "pair_abs": _box(pair_boxes, "abs"),
        "pair_next": _box(pair_boxes, "next"),
        "float_outcome": floated.get("outcome"),
        "float_reason": floated.get("reason"),
        "shrink_outcome": shrink.get("outcome"),
        "shrink_reason": shrink.get("reason"),
    }
    checks = {
        "wrap_placed": wrapped.get("outcome") == "placed",
        "absolute_box": _near(absolute, x=30, y=40, content_width=50, content_height=72, border_height=77),
        "copy_box": _near(copy, x=37, y=53, content_width=50, content_height=60),
        "line_one": _near(_line(copy, 0), text="AB CD", x=37, y=53, height=20, content_width=50),
        "line_two": _near(_line(copy, 1), text="EF GH", x=37, y=73, height=20, content_width=50),
        "line_three": _near(_line(copy, 2), text="IJ", x=37, y=93, height=20, content_width=20),
        "flow_stays": _near(nxt, x=0, y=0, content_height=20),
        "page_ignores_absolute": _near(page, content_height=20),
        "pair_placed": paired.get("outcome") == "placed",
        "margin_inside": _near(_box(pair_boxes, "a"), x=0, y=6, content_height=20),
        "margins_collapse": _near(_box(pair_boxes, "b"), x=0, y=56, content_height=20),
        "collapsed_height": _near(_box(pair_boxes, "abs"), content_width=50, content_height=76),
        "pair_flow_stays": _near(_box(pair_boxes, "next"), y=0, content_height=20),
        "float_rejected": floated.get("outcome") == "invalid"
        and floated.get("reason") == "positioned content is unsupported",
        "shrink_rejected": shrink.get("outcome") == "invalid"
        and shrink.get("reason") == "absolute shrink-to-fit is unsupported",
    }
    observed["checks"] = checks
    return all(checks.values()), observed


def main() -> None:
    passed, observed = observe()
    print(json.dumps({"passed": bool(passed), "observed": observed}))


if __name__ == "__main__":
    main()
