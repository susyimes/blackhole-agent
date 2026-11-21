"""Place automatic grid items by column flow and dense packing.

Column flow stacks the second item under the first. The initial row flow
puts that same item in the next column. Dense packing fills the cell a
span left empty; sparse packing leaves it empty and parks the later item
on the next row. The following block starts under the grid.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A layout that still rejects grid-auto-flow exits 0 with
passed false.
"""

from __future__ import annotations

import json

_FOUR = (
    '<div id="page"><div id="grid"><span id="a"></span><span id="b"></span>'
    '<span id="c"></span><span id="d"></span></div><p id="next">Z</p></div>'
)
_THREE = (
    '<div id="page"><div id="grid"><span id="a"></span><span id="b"></span>'
    '<span id="c"></span></div><p id="next">Z</p></div>'
)
_PAGE = "#page { font-size: 10px; line-height: 10px; }\n#next { font-size: 10px; line-height: 10px; }\n"
_ROW = (
    _PAGE
    + "#grid { display: grid; width: 60px; grid-template-columns: 30px 30px; "
    + "grid-template-rows: 20px 20px; }\n"
)
_COLUMN = _ROW + "#grid { grid-auto-flow: column; }\n"
_SPARSE = (
    _PAGE
    + "#grid { display: grid; width: 120px; grid-template-columns: 40px 40px 40px; "
    + "grid-auto-rows: 20px; }\n"
    + "#a { grid-column: span 2; }\n"
    + "#b { grid-column: span 2; }\n"
)
_DENSE = _SPARSE + "#grid { grid-auto-flow: row dense; }\n"


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


def _under(grid: dict[str, object] | None, nxt: dict[str, object] | None) -> bool:
    return (
        grid is not None
        and nxt is not None
        and nxt.get("y") == int(grid.get("y") or 0) + int(grid.get("border_height") or 0)
    )


def _lay(layout, markup: str, stylesheet: str) -> dict[str, object]:
    try:
        placed = layout(markup, stylesheet, viewport_width=240)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def _shot(placed: dict[str, object], idents: tuple[str, ...]) -> dict[str, object]:
    boxes = placed.get("boxes")
    grid = _box(boxes, "grid")
    nxt = _box(boxes, "next")
    shot: dict[str, object] = {
        "outcome": placed.get("outcome"),
        "reason": placed.get("reason"),
        "next_under_grid": _under(grid, nxt),
    }
    for ident in idents:
        item = _box(boxes, ident)
        shot[ident] = None if item is None else {
            "x": item.get("x"),
            "y": item.get("y"),
            "content_width": item.get("content_width"),
            "content_height": item.get("content_height"),
        }
    return shot


def main() -> int:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - missing layout is an unmet outcome
        print(json.dumps({"passed": False, "observed": {"error": f"{type(exc).__name__}: {exc}"}}))
        return 0
    row = _lay(layout_normal_flow, _FOUR, _ROW)
    column = _lay(layout_normal_flow, _FOUR, _COLUMN)
    sparse = _lay(layout_normal_flow, _THREE, _SPARSE)
    dense = _lay(layout_normal_flow, _THREE, _DENSE)
    observed = {
        "row": _shot(row, ("a", "b", "c", "d")),
        "column": _shot(column, ("a", "b", "c", "d")),
        "sparse": _shot(sparse, ("a", "b", "c")),
        "dense": _shot(dense, ("a", "b", "c")),
    }
    row_boxes = row.get("boxes")
    column_boxes = column.get("boxes")
    sparse_boxes = sparse.get("boxes")
    dense_boxes = dense.get("boxes")
    passed = (
        row.get("outcome") == "placed"
        and _at(_box(row_boxes, "a"), 0, 0, 30, 20)
        and _at(_box(row_boxes, "b"), 30, 0, 30, 20)
        and _at(_box(row_boxes, "c"), 0, 20, 30, 20)
        and _at(_box(row_boxes, "d"), 30, 20, 30, 20)
        and _under(_box(row_boxes, "grid"), _box(row_boxes, "next"))
        and column.get("outcome") == "placed"
        and _at(_box(column_boxes, "a"), 0, 0, 30, 20)
        and _at(_box(column_boxes, "b"), 0, 20, 30, 20)
        and _at(_box(column_boxes, "c"), 30, 0, 30, 20)
        and _at(_box(column_boxes, "d"), 30, 20, 30, 20)
        and _under(_box(column_boxes, "grid"), _box(column_boxes, "next"))
        and sparse.get("outcome") == "placed"
        and _at(_box(sparse_boxes, "a"), 0, 0, 80, 20)
        and _at(_box(sparse_boxes, "b"), 0, 20, 80, 20)
        and _at(_box(sparse_boxes, "c"), 80, 20, 40, 20)
        and _under(_box(sparse_boxes, "grid"), _box(sparse_boxes, "next"))
        and dense.get("outcome") == "placed"
        and _at(_box(dense_boxes, "a"), 0, 0, 80, 20)
        and _at(_box(dense_boxes, "b"), 0, 20, 80, 20)
        and _at(_box(dense_boxes, "c"), 80, 0, 40, 20)
        and _under(_box(dense_boxes, "grid"), _box(dense_boxes, "next"))
    )
    print(json.dumps({"passed": passed, "observed": observed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
