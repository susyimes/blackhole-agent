"""Separate flex items and lines by a definite gap in normal flow.

A 20px gutter keeps two inflexible 40px items apart in a 100px row and leaves
a growing sibling only the free space after that gutter. column-gap 20px in a
90px row forces the next 40px item onto a later line, and row-gap 8px lifts
that line. An automatic column adds its row-gap to the used height. A definite
column subtracts the row-gap before the flexible item grows. A wrapping column
uses column-gap between columns.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree that still rejects gap exits 0 with passed false.
"""

from __future__ import annotations

import json
import sys

_PAIR = (
    '<div id="page"><div id="row"><span id="a"></span><span id="b"></span></div>'
    '<p id="next">Z</p></div>'
)
_THREE = (
    '<div id="page"><div id="row"><span id="a"></span><span id="b"></span>'
    '<span id="c"></span></div><p id="next">Z</p></div>'
)
_APART = """
#page { font-size: 10px; line-height: 10px; }
#row { display: flex; width: 100px; gap: 20px; }
#a { flex: none; width: 40px; height: 10px; }
#b { flex: none; width: 40px; height: 10px; }
"""
_GROW = """
#page { font-size: 10px; line-height: 10px; }
#row { display: flex; width: 100px; gap: 20px; }
#a { flex: none; width: 40px; height: 10px; }
#b { flex: 1; height: 10px; }
"""
_WRAP = """
#page { font-size: 10px; line-height: 10px; }
#row { display: flex; flex-wrap: wrap; width: 90px; gap: 8px 20px; }
#a { flex: none; width: 40px; height: 10px; }
#b { flex: none; width: 40px; height: 10px; }
#c { flex: none; width: 40px; height: 10px; }
"""
_COLUMN = """
#page { font-size: 10px; line-height: 10px; }
#row { display: flex; flex-direction: column; width: 40px; row-gap: 15px; }
#a { flex: none; width: 40px; height: 30px; }
#b { flex: none; width: 40px; height: 20px; }
"""
_DEFINITE = """
#page { font-size: 10px; line-height: 10px; }
#row { display: flex; flex-direction: column; width: 40px; height: 100px; row-gap: 20px; }
#a { flex: none; height: 40px; }
#b { flex: 1; }
"""
_COLUMNS = """
#page { font-size: 10px; line-height: 10px; }
#row { display: flex; flex-direction: column; flex-wrap: wrap; width: 90px; height: 90px; row-gap: 10px; column-gap: 10px; }
#a { flex: none; width: 40px; height: 40px; }
#b { flex: none; width: 40px; height: 40px; }
#c { flex: none; width: 40px; height: 40px; }
"""
_ZERO = """
#page { font-size: 10px; line-height: 10px; }
#row { display: flex; width: 100px; gap: 0px; }
#a { flex: none; width: 40px; height: 10px; }
#b { flex: none; width: 40px; height: 10px; }
"""


def _box(boxes: object, ident: str) -> dict[str, object] | None:
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if isinstance(item, dict) and item.get("id") == ident:
            return item
    return None


def _near(item: dict[str, object] | None, **expected: object) -> bool:
    if item is None:
        return False
    return all(item.get(key) == value for key, value in expected.items())


def _placed(box: dict[str, object] | None) -> dict[str, object] | None:
    if box is None:
        return None
    return {
        "x": box.get("x"),
        "y": box.get("y"),
        "content_width": box.get("content_width"),
        "content_height": box.get("content_height"),
    }


def _lay(layout, markup: str, stylesheet: str, width: int) -> dict[str, object]:
    try:
        placed = layout(markup, stylesheet, viewport_width=width)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without placement still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    apart = _lay(layout_normal_flow, _PAIR, _APART, 200)
    grown = _lay(layout_normal_flow, _PAIR, _GROW, 200)
    wrapped = _lay(layout_normal_flow, _THREE, _WRAP, 200)
    column = _lay(layout_normal_flow, _PAIR, _COLUMN, 200)
    definite = _lay(layout_normal_flow, _PAIR, _DEFINITE, 200)
    columns = _lay(layout_normal_flow, _THREE, _COLUMNS, 200)
    zero = _lay(layout_normal_flow, _PAIR, _ZERO, 200)

    def take(result: dict[str, object], ident: str) -> dict[str, object] | None:
        return _box(result.get("boxes"), ident)

    apart_row = take(apart, "row")
    grown_row = take(grown, "row")
    wrap_row = take(wrapped, "row")
    column_row = take(column, "row")
    definite_row = take(definite, "row")
    columns_row = take(columns, "row")
    observed: dict[str, object] = {
        "apart_outcome": apart.get("outcome"),
        "apart_reason": apart.get("reason"),
        "apart_a": _placed(take(apart, "a")),
        "apart_b": _placed(take(apart, "b")),
        "apart_row": _placed(apart_row),
        "apart_next": _placed(take(apart, "next")),
        "grow_outcome": grown.get("outcome"),
        "grow_reason": grown.get("reason"),
        "grow_a": _placed(take(grown, "a")),
        "grow_b": _placed(take(grown, "b")),
        "wrap_outcome": wrapped.get("outcome"),
        "wrap_reason": wrapped.get("reason"),
        "wrap_a": _placed(take(wrapped, "a")),
        "wrap_b": _placed(take(wrapped, "b")),
        "wrap_c": _placed(take(wrapped, "c")),
        "wrap_row": _placed(wrap_row),
        "wrap_next": _placed(take(wrapped, "next")),
        "column_outcome": column.get("outcome"),
        "column_reason": column.get("reason"),
        "column_a": _placed(take(column, "a")),
        "column_b": _placed(take(column, "b")),
        "column_row": _placed(column_row),
        "column_next": _placed(take(column, "next")),
        "definite_outcome": definite.get("outcome"),
        "definite_reason": definite.get("reason"),
        "definite_a": _placed(take(definite, "a")),
        "definite_b": _placed(take(definite, "b")),
        "columns_outcome": columns.get("outcome"),
        "columns_reason": columns.get("reason"),
        "columns_a": _placed(take(columns, "a")),
        "columns_b": _placed(take(columns, "b")),
        "columns_c": _placed(take(columns, "c")),
        "zero_outcome": zero.get("outcome"),
        "zero_a": _placed(take(zero, "a")),
        "zero_b": _placed(take(zero, "b")),
    }
    checks = {
        "gutter_between_inflexible_items": (
            apart.get("outcome") == "placed"
            and _near(take(apart, "a"), x=0, y=0, content_width=40, content_height=10)
            and _near(take(apart, "b"), x=60, y=0, content_width=40, content_height=10)
            and _near(apart_row, content_width=100, content_height=10)
            and isinstance(take(apart, "next"), dict)
            and take(apart, "next").get("y") == 10
        ),
        "growth_after_gutter": (
            grown.get("outcome") == "placed"
            and _near(take(grown, "a"), x=0, y=0, content_width=40, content_height=10)
            and _near(take(grown, "b"), x=60, y=0, content_width=40, content_height=10)
            and _near(grown_row, content_width=100, content_height=10)
        ),
        "main_gap_wraps_and_cross_gap_separates_lines": (
            wrapped.get("outcome") == "placed"
            and _near(take(wrapped, "a"), x=0, y=0, content_width=40, content_height=10)
            and _near(take(wrapped, "b"), x=0, y=18, content_width=40, content_height=10)
            and _near(take(wrapped, "c"), x=0, y=36, content_width=40, content_height=10)
            and _near(wrap_row, content_width=90, content_height=46)
            and isinstance(take(wrapped, "next"), dict)
            and take(wrapped, "next").get("y") == 46
        ),
        "automatic_column_includes_row_gap": (
            column.get("outcome") == "placed"
            and _near(take(column, "a"), x=0, y=0, content_width=40, content_height=30)
            and _near(take(column, "b"), x=0, y=45, content_width=40, content_height=20)
            and _near(column_row, content_width=40, content_height=65)
            and isinstance(take(column, "next"), dict)
            and take(column, "next").get("y") == 65
        ),
        "definite_column_grows_after_row_gap": (
            definite.get("outcome") == "placed"
            and _near(take(definite, "a"), x=0, y=0, content_width=40, content_height=40)
            and _near(take(definite, "b"), x=0, y=60, content_width=40, content_height=40)
            and _near(definite_row, content_width=40, content_height=100)
        ),
        "column_wrap_uses_both_gaps": (
            columns.get("outcome") == "placed"
            and _near(take(columns, "a"), x=0, y=0, content_width=40, content_height=40)
            and _near(take(columns, "b"), x=0, y=50, content_width=40, content_height=40)
            and _near(take(columns, "c"), x=50, y=0, content_width=40, content_height=40)
            and _near(columns_row, content_width=90, content_height=90)
        ),
        "zero_gap_stays_adjacent": (
            zero.get("outcome") == "placed"
            and _near(take(zero, "a"), x=0, y=0, content_width=40, content_height=10)
            and _near(take(zero, "b"), x=40, y=0, content_width=40, content_height=10)
        ),
    }
    observed["checks"] = checks
    return all(checks.values()), observed


def main() -> None:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - the probe must exit 0 even when it fails
        passed, observed = False, {"error": f"{type(exc).__name__}: {exc}"}
    payload = {"passed": bool(passed), "observed": observed if observed else {"error": "empty"}}
    try:
        encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    except (UnicodeEncodeError, TypeError) as exc:
        encoded = json.dumps(
            {"passed": False, "observed": {"error": f"{type(exc).__name__}: {exc}"}},
            separators=(",", ":"),
        ).encode("ascii")
    sys.stdout.buffer.write(encoded + b"\n")


if __name__ == "__main__":
    main()
