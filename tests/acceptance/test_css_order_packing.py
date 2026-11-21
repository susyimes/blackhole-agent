"""Pack flex and grid items in CSS order-modified document order.

A negative order moves a later sibling ahead of earlier ones. Equal orders
keep source order. A wrapping flex line breaks on that sorted sequence, and
the same order fills the first automatic grid cell in row flow and in column
flow. A definite grid column stays on that line while the ordered item takes the
first free cell. The following block starts under the container.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A layout that still rejects order exits 0 with passed false.
"""

from __future__ import annotations

import json

_PAGE = "#page { font-size: 10px; line-height: 10px; }\n#next { font-size: 10px; line-height: 10px; }\n"
_FLEX = (
    '<div id="page"><div id="row"><span id="a"></span><span id="b"></span>'
    '<span id="c"></span></div><p id="next">Z</p></div>'
)
_SOURCE = (
    _PAGE
    + "#row { display: flex; width: 90px; }\n"
    + "#a, #b, #c { flex: none; width: 30px; height: 10px; }\n"
)
_NEGATIVE = _SOURCE + "#c { order: -1; }\n"
_WRAP = (
    _PAGE
    + "#row { display: flex; flex-wrap: wrap; width: 100px; }\n"
    + "#a { flex: none; width: 30px; height: 10px; order: 2; }\n"
    + "#b { flex: none; width: 80px; height: 10px; order: 0; }\n"
    + "#c { flex: none; width: 30px; height: 10px; order: 1; }\n"
)
_GRID = (
    '<div id="page"><div id="grid"><span id="a"></span><span id="b"></span>'
    '<span id="c"></span></div><p id="next">Z</p></div>'
)
_GRID_ROW = (
    _PAGE
    + "#grid { display: grid; width: 60px; grid-template-columns: 30px 30px; "
    + "grid-template-rows: 20px 20px; }\n"
    + "#c { order: -1; }\n"
)
_GRID_COLUMN = _GRID_ROW + "#grid { grid-auto-flow: column; }\n"
_LOCKED = (
    '<div id="page"><div id="grid"><span id="a"></span><span id="b"></span></div>'
    '<p id="next">Z</p></div>'
)
_LOCKED_CSS = (
    _PAGE
    + "#grid { display: grid; width: 60px; grid-template-columns: 30px 30px; "
    + "grid-template-rows: 20px; }\n"
    + "#a { grid-column: 2; }\n"
    + "#b { order: -1; }\n"
)


def _box(boxes: object, ident: str) -> dict[str, object] | None:
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if isinstance(item, dict) and item.get("id") == ident:
            return item
    return None


def _at(item: dict[str, object] | None, x: int, y: int, width: int, height: int) -> bool:
    return (
        item is not None
        and item.get("x") == x
        and item.get("y") == y
        and item.get("content_width") == width
        and item.get("content_height") == height
    )


def _under(container: dict[str, object] | None, nxt: dict[str, object] | None) -> bool:
    return (
        container is not None
        and nxt is not None
        and nxt.get("y") == int(container.get("y") or 0) + int(container.get("border_height") or 0)
    )


def _lay(layout, markup: str, stylesheet: str) -> dict[str, object]:
    try:
        placed = layout(markup, stylesheet, viewport_width=240)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def _shot(placed: dict[str, object], container: str) -> dict[str, object]:
    boxes = placed.get("boxes")
    shot: dict[str, object] = {
        "outcome": placed.get("outcome"),
        "reason": placed.get("reason"),
        "next_under": _under(_box(boxes, container), _box(boxes, "next")),
    }
    for ident in ("a", "b", "c", container):
        item = _box(boxes, ident)
        shot[ident] = None if item is None else {
            "x": item.get("x"),
            "y": item.get("y"),
            "content_width": item.get("content_width"),
            "content_height": item.get("content_height"),
            "border_height": item.get("border_height"),
        }
    return shot


def main() -> int:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - missing layout is an unmet outcome
        print(json.dumps({"passed": False, "observed": {"error": f"{type(exc).__name__}: {exc}"}}))
        return 0
    source = _lay(layout_normal_flow, _FLEX, _SOURCE)
    negative = _lay(layout_normal_flow, _FLEX, _NEGATIVE)
    wrapped = _lay(layout_normal_flow, _FLEX, _WRAP)
    row = _lay(layout_normal_flow, _GRID, _GRID_ROW)
    column = _lay(layout_normal_flow, _GRID, _GRID_COLUMN)
    locked = _lay(layout_normal_flow, _LOCKED, _LOCKED_CSS)
    observed = {
        "source": _shot(source, "row"),
        "negative": _shot(negative, "row"),
        "wrap": _shot(wrapped, "row"),
        "grid_row": _shot(row, "grid"),
        "grid_column": _shot(column, "grid"),
        "locked": _shot(locked, "grid"),
    }
    source_boxes = source.get("boxes")
    negative_boxes = negative.get("boxes")
    wrap_boxes = wrapped.get("boxes")
    row_boxes = row.get("boxes")
    column_boxes = column.get("boxes")
    locked_boxes = locked.get("boxes")
    passed = (
        source.get("outcome") == "placed"
        and _at(_box(source_boxes, "a"), 0, 0, 30, 10)
        and _at(_box(source_boxes, "b"), 30, 0, 30, 10)
        and _at(_box(source_boxes, "c"), 60, 0, 30, 10)
        and _under(_box(source_boxes, "row"), _box(source_boxes, "next"))
        and negative.get("outcome") == "placed"
        and _at(_box(negative_boxes, "c"), 0, 0, 30, 10)
        and _at(_box(negative_boxes, "a"), 30, 0, 30, 10)
        and _at(_box(negative_boxes, "b"), 60, 0, 30, 10)
        and _under(_box(negative_boxes, "row"), _box(negative_boxes, "next"))
        and wrapped.get("outcome") == "placed"
        and _at(_box(wrap_boxes, "b"), 0, 0, 80, 10)
        and _at(_box(wrap_boxes, "c"), 0, 10, 30, 10)
        and _at(_box(wrap_boxes, "a"), 30, 10, 30, 10)
        and _under(_box(wrap_boxes, "row"), _box(wrap_boxes, "next"))
        and row.get("outcome") == "placed"
        and _at(_box(row_boxes, "c"), 0, 0, 30, 20)
        and _at(_box(row_boxes, "a"), 30, 0, 30, 20)
        and _at(_box(row_boxes, "b"), 0, 20, 30, 20)
        and _under(_box(row_boxes, "grid"), _box(row_boxes, "next"))
        and column.get("outcome") == "placed"
        and _at(_box(column_boxes, "c"), 0, 0, 30, 20)
        and _at(_box(column_boxes, "a"), 0, 20, 30, 20)
        and _at(_box(column_boxes, "b"), 30, 0, 30, 20)
        and _under(_box(column_boxes, "grid"), _box(column_boxes, "next"))
        and locked.get("outcome") == "placed"
        and _at(_box(locked_boxes, "a"), 30, 0, 30, 20)
        and _at(_box(locked_boxes, "b"), 0, 0, 30, 20)
        and _under(_box(locked_boxes, "grid"), _box(locked_boxes, "next"))
    )
    print(json.dumps({"passed": passed, "observed": observed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
