"""Place an absolute box from the text inside it.

Automatic width is the shrink-to-fit of that text. Automatic height is the
stacked line boxes. Insets that are both automatic use the static position
between block siblings, and the absolute box does not push the next paragraph.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree that still rejects the text exits 0 with passed false.
"""

from __future__ import annotations

import json

_STATIC_MARKUP = (
    '<div id="page"><div id="card"><p id="above">AA</p>'
    '<div id="abs">Hello</div><p id="below">BB</p></div></div>'
)
_STATIC_CSS = """
#card { position: relative; width: 200px; }
#above, #below, #abs { font-size: 10px; }
#abs { position: absolute; }
"""

_WRAP_MARKUP = '<div id="page"><p id="flow">Stay</p><div id="abs">AB CD</div></div>'
_WRAP_CSS = """
#page { position: relative; }
#flow, #abs { font-size: 10px; }
#abs { position: absolute; left: 160px; top: 4px; }
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


def _place(markup: str, stylesheet: str) -> dict[str, object]:
    from blackhole_agent.css_normal_flow import layout_normal_flow

    placed = layout_normal_flow(markup, stylesheet, viewport_width=200)
    return placed if isinstance(placed, dict) else {"outcome": "error", "boxes": None}


def observe() -> tuple[bool, dict[str, object]]:
    try:
        static = _place(_STATIC_MARKUP, _STATIC_CSS)
        wrapped = _place(_WRAP_MARKUP, _WRAP_CSS)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    static_boxes = static.get("boxes")
    wrap_boxes = wrapped.get("boxes")
    above = _box(static_boxes, "above")
    absolute = _box(static_boxes, "abs")
    below = _box(static_boxes, "below")
    page = _box(static_boxes, "page")
    flow = _box(wrap_boxes, "flow")
    narrow = _box(wrap_boxes, "abs")
    narrow_page = _box(wrap_boxes, "page")
    observed: dict[str, object] = {
        "static_outcome": static.get("outcome"),
        "static_reason": static.get("reason"),
        "above": above,
        "absolute": absolute,
        "below": below,
        "page": page,
        "wrap_outcome": wrapped.get("outcome"),
        "flow": flow,
        "narrow": narrow,
        "narrow_page": narrow_page,
    }
    checks = {
        "static_placed": static.get("outcome") == "placed",
        "page_ignores_absolute": _near(page, x=0, y=0, content_width=200, content_height=20),
        "above": _near(above, x=0, y=0, content_height=10),
        "above_text": _near(_line(above, 0), text="AA", x=0, y=0, height=10, content_width=20),
        "static_hello": _near(absolute, x=0, y=10, content_width=50, content_height=10),
        "static_line": _near(_line(absolute, 0), text="Hello", x=0, y=10, height=10, content_width=50),
        "below_keeps_slot": _near(below, x=0, y=10, content_height=10),
        "below_text": _near(_line(below, 0), text="BB", x=0, y=10, height=10, content_width=20),
        "wrap_placed": wrapped.get("outcome") == "placed",
        "flow_stays": _near(flow, x=0, y=0, content_height=10),
        "flow_text": _near(_line(flow, 0), text="Stay", x=0, y=0, height=10, content_width=40),
        "page_stays": _near(narrow_page, content_height=10),
        "shrink_box": _near(narrow, x=160, y=4, content_width=40, content_height=20),
        "shrink_first": _near(_line(narrow, 0), text="AB", x=160, y=4, height=10, content_width=20),
        "shrink_second": _near(_line(narrow, 1), text="CD", x=160, y=14, height=10, content_width=20),
    }
    observed["checks"] = checks
    return all(checks.values()), observed


def main() -> None:
    passed, observed = observe()
    print(json.dumps({"passed": bool(passed), "observed": observed}))


if __name__ == "__main__":
    main()
