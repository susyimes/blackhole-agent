"""Lay in-flow block children inside a float.

The first child's top margin stays inside the float. Adjoining margins
collapse. An automatic child stretches, a specified width and a percentage
keep their used widths, and an automatic float shrinks to the widest child
margin box. The following line starts beside that float. An inline child
stays rejected.

Prints JSON with boolean passed and nonempty observed. Exit 0 either way.
"""

from __future__ import annotations

import json

_ZERO = "margin:0px;"

_STACK = (
    '<div id="page"><div id="pin"><div id="one"></div><div id="two"></div></div>'
    '<p id="copy">Hello</p></div>'
)
_STACK_CSS = f"""
#page,#pin,#one,#two,#copy {{{_ZERO}}}
#pin {{ float:left; width:80px; }}
#one {{ height:20px; margin-top:10px; margin-bottom:10px; }}
#two {{ height:30px; margin-top:40px; margin-bottom:5px; }}
#copy {{ font-size:10px; line-height:20px; }}
"""

_WIDTHS = (
    '<div id="page"><div id="pin"><div id="fixed"></div><div id="half"></div></div></div>'
)
_WIDTHS_CSS = f"""
#page,#pin,#fixed,#half {{{_ZERO}}}
#pin {{ float:left; width:80px; }}
#fixed {{ width:50px; height:10px; }}
#half {{ width:50%; height:10px; }}
"""

_SHRINK = (
    '<div id="page"><div id="pin"><div id="wide"></div><div id="narrow"></div></div>'
    '<p id="copy">Hello</p></div>'
)
_SHRINK_CSS = f"""
#page,#pin,#wide,#narrow,#copy {{{_ZERO}}}
#pin {{ float:left; }}
#wide {{ width:70px; height:10px; margin-left:10px; }}
#narrow {{ width:40px; height:10px; }}
#copy {{ font-size:10px; line-height:20px; }}
"""

_INLINE = '<div id="page"><i id="pin"><b></b></i><p id="copy">Hi</p></div>'
_INLINE_CSS = "#pin { float:left; width:40px; } #copy { font-size:10px; margin:0px; }"


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


def _edge(box: dict[str, object] | None) -> dict[str, object] | None:
    if box is None:
        return None
    return {
        "x": box.get("x"),
        "y": box.get("y"),
        "content_width": box.get("content_width"),
        "content_height": box.get("content_height"),
        "border_height": box.get("border_height"),
    }


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without the walk still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    stack = _lay(layout_normal_flow, _STACK, _STACK_CSS)
    widths = _lay(layout_normal_flow, _WIDTHS, _WIDTHS_CSS)
    shrink = _lay(layout_normal_flow, _SHRINK, _SHRINK_CSS)
    inline = _lay(layout_normal_flow, _INLINE, _INLINE_CSS)
    stack_boxes = stack.get("boxes")
    width_boxes = widths.get("boxes")
    shrink_boxes = shrink.get("boxes")
    pin = _box(stack_boxes, "pin")
    one = _box(stack_boxes, "one")
    two = _box(stack_boxes, "two")
    copy = _box(stack_boxes, "copy")
    page = _box(stack_boxes, "page")
    fixed = _box(width_boxes, "fixed")
    half = _box(width_boxes, "half")
    sized = _box(width_boxes, "pin")
    wide = _box(shrink_boxes, "wide")
    narrow = _box(shrink_boxes, "narrow")
    shrunk = _box(shrink_boxes, "pin")
    beside = _box(shrink_boxes, "copy")
    observed: dict[str, object] = {
        "stack_outcome": stack.get("outcome"),
        "stack_reason": stack.get("reason"),
        "page": _edge(page),
        "pin": _edge(pin),
        "one": _edge(one),
        "two": _edge(two),
        "copy": _edge(copy),
        "copy_line": _line(copy, 0),
        "widths_outcome": widths.get("outcome"),
        "widths_reason": widths.get("reason"),
        "fixed": _edge(fixed),
        "half": _edge(half),
        "sized": _edge(sized),
        "shrink_outcome": shrink.get("outcome"),
        "shrink_reason": shrink.get("reason"),
        "wide": _edge(wide),
        "narrow": _edge(narrow),
        "shrunk": _edge(shrunk),
        "beside_line": _line(beside, 0),
        "inline_outcome": inline.get("outcome"),
        "inline_reason": inline.get("reason"),
    }
    checks = {
        "stack_placed": stack.get("outcome") == "placed",
        "pin": _near(pin, x=0, y=0, content_width=80, content_height=105, border_height=105),
        "one": _near(one, x=0, y=10, content_width=80, content_height=20, border_height=20),
        "two": _near(two, x=0, y=70, content_width=80, content_height=30, border_height=30),
        "copy_line": _near(_line(copy, 0), text="Hello", x=80, y=0, height=20, content_width=50),
        "page": _near(page, x=0, y=0, content_width=200, content_height=105),
        "fixed": _near(fixed, x=0, y=0, content_width=50, content_height=10),
        "half": _near(half, x=0, y=10, content_width=40, content_height=10),
        "sized": _near(sized, content_width=80, content_height=20),
        "wide": _near(wide, x=10, y=0, content_width=70, content_height=10),
        "narrow": _near(narrow, x=0, y=10, content_width=40, content_height=10),
        "shrunk": _near(shrunk, x=0, y=0, content_width=80, content_height=20),
        "beside": _near(_line(beside, 0), text="Hello", x=80, y=0, height=20, content_width=50),
        "inline_rejected": (
            inline.get("outcome") == "invalid"
            and inline.get("boxes") is None
            and inline.get("reason") == "float content is unsupported"
        ),
    }
    observed["checks"] = checks
    return all(checks.values()), observed


def main() -> None:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, separators=(",", ":")))


if __name__ == "__main__":
    main()
