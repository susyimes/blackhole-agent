"""Lay a CSS table into normal flow from the text inside its cells.

An automatic table of "AA" and "BBB" at 10px is 50px wide, not the 200px
parent, and the next block starts under that one line. A fixed 20px column
wraps "AA BB" into two line boxes, so the row is 20px and the next block
starts there. The other cell's single line sits on that row's bottom edge.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree that still rejects display table exits 0 with passed
false.
"""

from __future__ import annotations

import json
import sys

_AUTO = (
    '<div id="page"><div id="table"><div id="row"><div id="a">AA</div>'
    '<div id="b">BBB</div></div></div><p id="next">Z</p></div>'
)
_FIXED = (
    '<div id="page"><div id="table"><div id="row"><div id="a">AA BB</div>'
    '<div id="b">C</div></div></div><p id="next">Z</p></div>'
)
_NESTED = (
    '<div id="page"><div id="table"><div id="row"><div id="a"><span>AA</span></div>'
    "</div></div></div>"
)
_AUTO_CSS = """
#page { font-size: 10px; line-height: 10px; }
#table { display: table; }
#row { display: table-row; }
#a, #b { display: table-cell; }
"""
_FIXED_CSS = """
#page { font-size: 10px; line-height: 10px; }
#table { display: table; table-layout: fixed; width: 80px; }
#row { display: table-row; }
#a { display: table-cell; width: 20px; vertical-align: top; }
#b { display: table-cell; vertical-align: bottom; }
"""
_NESTED_CSS = """
#page { font-size: 10px; line-height: 10px; }
#table { display: table; }
#row { display: table-row; }
#a { display: table-cell; }
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


def _lines(box: dict[str, object] | None) -> list[dict[str, object]]:
    if box is None or not isinstance(box.get("lines"), list):
        return []
    return [line for line in box["lines"] if isinstance(line, dict)]


def _lay(layout, markup: str, stylesheet: str) -> dict[str, object]:
    try:
        placed = layout(markup, stylesheet, viewport_width=200)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without placement still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    automatic = _lay(layout_normal_flow, _AUTO, _AUTO_CSS)
    fixed = _lay(layout_normal_flow, _FIXED, _FIXED_CSS)
    nested = _lay(layout_normal_flow, _NESTED, _NESTED_CSS)

    def take(result: dict[str, object], ident: str) -> dict[str, object] | None:
        return _box(result.get("boxes"), ident)

    auto_a = take(automatic, "a")
    auto_b = take(automatic, "b")
    fixed_a = take(fixed, "a")
    fixed_b = take(fixed, "b")
    fixed_lines_a = _lines(fixed_a)
    fixed_lines_b = _lines(fixed_b)
    observed: dict[str, object] = {
        "auto_outcome": automatic.get("outcome"),
        "auto_reason": automatic.get("reason"),
        "auto_table": None if take(automatic, "table") is None else {
            "x": take(automatic, "table").get("x"),
            "y": take(automatic, "table").get("y"),
            "content_width": take(automatic, "table").get("content_width"),
            "content_height": take(automatic, "table").get("content_height"),
        },
        "auto_a": None if auto_a is None else {"x": auto_a.get("x"), "content_width": auto_a.get("content_width")},
        "auto_b": None if auto_b is None else {"x": auto_b.get("x"), "content_width": auto_b.get("content_width")},
        "auto_next_y": None if take(automatic, "next") is None else take(automatic, "next").get("y"),
        "auto_page_width": None if take(automatic, "page") is None else take(automatic, "page").get("content_width"),
        "fixed_outcome": fixed.get("outcome"),
        "fixed_reason": fixed.get("reason"),
        "fixed_a_lines": [(line.get("text"), line.get("y")) for line in fixed_lines_a],
        "fixed_b_line": None if not fixed_lines_b else {"text": fixed_lines_b[0].get("text"), "y": fixed_lines_b[0].get("y")},
        "fixed_b": None if fixed_b is None else {
            "x": fixed_b.get("x"),
            "content_width": fixed_b.get("content_width"),
            "content_height": fixed_b.get("content_height"),
        },
        "fixed_next_y": None if take(fixed, "next") is None else take(fixed, "next").get("y"),
        "nested_outcome": nested.get("outcome"),
        "nested_reason": nested.get("reason"),
    }
    checks = {
        "automatic_table_shrinks_to_cell_text": (
            automatic.get("outcome") == "placed"
            and _near(take(automatic, "table"), x=0, y=0, content_width=50, content_height=10)
            and _near(auto_a, x=0, y=0, content_width=20, content_height=10)
            and _near(auto_b, x=20, y=0, content_width=30, content_height=10)
            and _near(take(automatic, "page"), content_width=200)
            and _near(take(automatic, "next"), y=10)
        ),
        "fixed_column_wraps_and_grows_the_row": (
            fixed.get("outcome") == "placed"
            and _near(take(fixed, "table"), content_width=80, content_height=20)
            and _near(fixed_a, x=0, y=0, content_width=20, content_height=20)
            and [line.get("text") for line in fixed_lines_a] == ["AA", "BB"]
            and [line.get("y") for line in fixed_lines_a] == [0, 10]
            and _near(fixed_b, x=20, y=0, content_width=60, content_height=20)
            and _near(take(fixed, "next"), y=20)
        ),
        "bottom_aligned_line_sits_on_the_row_bottom": (
            len(fixed_lines_b) == 1
            and fixed_lines_b[0].get("text") == "C"
            and fixed_lines_b[0].get("y") == 10
        ),
        "element_inside_a_cell_is_rejected": nested.get("outcome") == "invalid",
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
