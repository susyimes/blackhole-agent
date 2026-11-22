"""Wrap normal-flow lines around a float's shape-outside.

A 100px left float whose circle is centered in the margin box leaves the top
corner open, so an 110px word sits on the first line at x 90. The same word
drops below a rectangular float. An inset that ends at 40px releases the next
line there. shape-margin 0 keeps a 90px word at x 80; shape-margin 20px pushes
it to x 100. A right-hand circle leaves the line at x 0. A content-box
reference and a positive shape-margin on an ellipse are rejected. The
following block starts under the float.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A layout that still excludes the whole margin box exits 0
with passed false.
"""

from __future__ import annotations

import json

_PAGE = "#page, #copy, #next, #host { font-size: 10px; line-height: 20px; }\n"
_CIRCLE = (
    '<div id="page"><div id="host"><div id="flo"></div><p id="copy">ABCDEFGHIJK</p></div>'
    '<p id="next">Z</p></div>'
)
_CIRCLE_CSS = (
    _PAGE
    + "#flo { float: left; width: 100px; height: 100px; shape-outside: circle(50px at 50px 50px); }\n"
)
_INSET = '<div id="page"><div id="flo"></div><p id="copy">ABCDE</p></div>'
_INSET_CSS = (
    "#page, #copy { font-size: 10px; line-height: 10px; }\n"
    "#flo { float: left; width: 100px; height: 100px; "
    "shape-outside: inset(0px 0px 60px 0px); }\n"
)
_MARGIN = '<div id="page"><div id="flo"></div><p id="copy">ABCDEFGHI</p></div>'
_MARGIN_TIGHT = (
    "#page, #copy { font-size: 10px; line-height: 100px; }\n"
    "#flo { float: left; width: 100px; height: 100px; "
    "shape-outside: circle(30px at 50px 50px); shape-margin: 0px; }\n"
)
_MARGIN_WIDE = (
    "#page, #copy { font-size: 10px; line-height: 100px; }\n"
    "#flo { float: left; width: 100px; height: 100px; "
    "shape-outside: circle(30px at 50px 50px); shape-margin: 20px; }\n"
)
_RIGHT = '<div id="page"><div id="flo"></div><p id="copy">ABCDEFGHIJK</p></div>'
_RIGHT_CSS = (
    _PAGE
    + "#flo { float: right; width: 100px; height: 100px; "
    "shape-outside: circle(50px at 50px 50px); }\n"
)
_BAD = '<div id="page"><div id="flo"></div><p id="copy">A</p></div>'
_BAD_CSS = (
    "#flo { float: left; width: 40px; height: 40px; "
    "shape-outside: circle(10px at 20px 20px) content-box; }\n"
)
_ELLIPSE_CSS = (
    "#flo { float: left; width: 100px; height: 100px; "
    "shape-outside: ellipse(40px 20px at 50px 50px); shape-margin: 10px; }\n"
)


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


def _lay(layout, markup: str, stylesheet: str, width: int) -> dict[str, object]:
    try:
        placed = layout(markup, stylesheet, viewport_width=width)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def _view(result: dict[str, object], ident: str) -> dict[str, object] | None:
    box = _box(result.get("boxes"), ident)
    if box is None:
        return None
    lines = box.get("lines")
    first = lines[0] if isinstance(lines, list) and lines and isinstance(lines[0], dict) else None
    return {
        "x": box.get("x"),
        "y": box.get("y"),
        "content_width": box.get("content_width"),
        "content_height": box.get("content_height"),
        "line": None
        if first is None
        else {
            "text": first.get("text"),
            "x": first.get("x"),
            "y": first.get("y"),
            "height": first.get("height"),
            "content_width": first.get("content_width"),
        },
    }


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without placement still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    circle = _lay(layout_normal_flow, _CIRCLE, _CIRCLE_CSS, 200)
    inset = _lay(layout_normal_flow, _INSET, _INSET_CSS, 100)
    tight = _lay(layout_normal_flow, _MARGIN, _MARGIN_TIGHT, 200)
    wide = _lay(layout_normal_flow, _MARGIN, _MARGIN_WIDE, 200)
    right = _lay(layout_normal_flow, _RIGHT, _RIGHT_CSS, 200)
    bad = _lay(layout_normal_flow, _BAD, _BAD_CSS, 200)
    ellipse = _lay(layout_normal_flow, _BAD, _ELLIPSE_CSS, 200)

    copy = _box(circle.get("boxes"), "copy")
    host = _box(circle.get("boxes"), "host")
    nxt = _box(circle.get("boxes"), "next")
    observed: dict[str, object] = {
        "circle_outcome": circle.get("outcome"),
        "circle_reason": circle.get("reason"),
        "circle_copy": _view(circle, "copy"),
        "circle_host": _view(circle, "host"),
        "circle_next_y": None if nxt is None else nxt.get("y"),
        "inset_outcome": inset.get("outcome"),
        "inset_reason": inset.get("reason"),
        "inset_copy": _view(inset, "copy"),
        "tight_outcome": tight.get("outcome"),
        "tight_reason": tight.get("reason"),
        "tight_copy": _view(tight, "copy"),
        "wide_outcome": wide.get("outcome"),
        "wide_reason": wide.get("reason"),
        "wide_copy": _view(wide, "copy"),
        "right_outcome": right.get("outcome"),
        "right_reason": right.get("reason"),
        "right_copy": _view(right, "copy"),
        "bad_outcome": bad.get("outcome"),
        "bad_reason": bad.get("reason"),
        "ellipse_outcome": ellipse.get("outcome"),
        "ellipse_reason": ellipse.get("reason"),
    }
    checks = {
        "circle_placed": circle.get("outcome") == "placed",
        "circle_line": _near(
            _line(copy, 0),
            text="ABCDEFGHIJK",
            x=90,
            y=0,
            height=20,
            content_width=110,
        ),
        "circle_host": _near(host, x=0, y=0, content_width=200, content_height=100),
        "circle_next": _near(nxt, y=100),
        "inset_line": _near(
            _line(_box(inset.get("boxes"), "copy"), 0),
            text="ABCDE",
            x=0,
            y=40,
            height=10,
            content_width=50,
        ),
        "margin_tight": _near(
            _line(_box(tight.get("boxes"), "copy"), 0),
            text="ABCDEFGHI",
            x=80,
            y=0,
            height=100,
            content_width=90,
        ),
        "margin_wide": _near(
            _line(_box(wide.get("boxes"), "copy"), 0),
            text="ABCDEFGHI",
            x=100,
            y=0,
            height=100,
            content_width=90,
        ),
        "right_line": _near(
            _line(_box(right.get("boxes"), "copy"), 0),
            text="ABCDEFGHIJK",
            x=0,
            y=0,
            height=20,
            content_width=110,
        ),
        "bad_shape": bad.get("outcome") == "invalid" and bad.get("boxes") is None and bad.get("reason") == "reference",
        "ellipse_margin": (
            ellipse.get("outcome") == "invalid"
            and ellipse.get("boxes") is None
            and ellipse.get("reason") == "shape_margin"
        ),
    }
    observed["checks"] = checks
    return all(checks.values()), observed


def main() -> None:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, separators=(",", ":")))


if __name__ == "__main__":
    main()
