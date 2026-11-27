"""Inset separate-model table cell text by padding and its used border.

On a marginless page at font-size 10px and line-height 10px, padding 4px 6px
on AA puts that line at x 6 y 4, the table content width at 32, and the
following block at y 18. A 2px solid border moves the line to x 2 y 2 and
the following block to y 14. Both together put the line at x 6 y 6 and the
following block at y 22. The next cell starts after the first cell's
horizontal chrome. border-spacing stays outside the border edge. A narrow
table wraps inside the content box. Uneven edges, a medium border of 3px,
and a none style are honored. An empty shown cell keeps its vertical padding.
A hidden empty cell still drops that row. Collapse, a fixed table, a span, a
block child, a percentage, and a negative length are rejected.

Prints JSON with boolean passed and nonempty observed. Exit 0 either way.
"""

from __future__ import annotations

import json
import sys

_BASE = "html, body, div, p { margin: 0px; font-size: 10px; line-height: 10px; }\n"
_CELL = "#a, #b, #c { display: table-cell; }\n#r1, #r2 { display: table-row; }\n"
_ONE = (
    '<div id="page"><div id="table"><div id="r1"><div id="a">AA</div></div>'
    "</div><p id=\"next\">Z</p></div>"
)
_PAIR = (
    '<div id="page"><div id="table"><div id="r1"><div id="a">AA</div>'
    '<div id="b">BB</div></div></div><p id="next">Z</p></div>'
)
_WRAP = (
    '<div id="page"><div id="table"><div id="r1"><div id="a">AA AA</div></div>'
    "</div><p id=\"next\">Z</p></div>"
)
_STACK = (
    '<div id="page"><div id="table"><div id="r1"><div id="a"></div></div>'
    '<div id="r2"><div id="b">BB</div></div></div><p id="next">Z</p></div>'
)
_ALIGN = (
    '<div id="page"><div id="table"><div id="r1"><div id="a">Q</div>'
    '<div id="b">Q</div></div></div><p id="next">Z</p></div>'
)
_CHILD = (
    '<div id="page"><div id="table"><div id="r1"><div id="a"><div id="kid">AA</div>'
    "</div></div></div><p id=\"next\">Z</p></div>"
)
_SPAN = (
    '<div id="page"><div id="table"><div id="r1"><div id="a" colspan="2">AA</div></div>'
    '<div id="r2"><div id="b">B</div><div id="c">C</div></div></div><p id="next">Z</p></div>'
)


def _box(boxes: object, ident: str) -> dict[str, object] | None:
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if isinstance(item, dict) and item.get("id") == ident:
            return item
    return None


def _line(box: dict[str, object] | None, index: int = 0) -> dict[str, object] | None:
    if box is None or not isinstance(box.get("lines"), list) or len(box["lines"]) <= index:
        return None
    line = box["lines"][index]
    return line if isinstance(line, dict) else None


def _lay(layout, markup: str, stylesheet: str) -> dict[str, object]:
    try:
        placed = layout(markup, stylesheet, viewport_width=240)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def _spot(result: dict[str, object], ident: str, index: int = 0) -> dict[str, object]:
    box = _box(result.get("boxes"), ident)
    line = _line(box, index)
    return {
        "outcome": result.get("outcome"),
        "reason": result.get("reason"),
        "x": None if line is None else line.get("x"),
        "y": None if line is None else line.get("y"),
        "width": None if box is None else box.get("content_width"),
        "lines": 0 if box is None or not isinstance(box.get("lines"), list) else len(box["lines"]),
    }


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without placement still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    sheets = {
        "pad": _BASE + "#table { display: table; }\n#a { padding: 4px 6px; }\n" + _CELL,
        "border": _BASE + "#table { display: table; }\n#a { border-width: 2px; border-style: solid; }\n" + _CELL,
        "both": _BASE
        + "#table { display: table; }\n#a { padding: 4px; border-width: 2px; border-style: solid; }\n"
        + _CELL,
        "pair": _BASE + "#table { display: table; }\n#a, #b { padding: 0px 4px; }\n" + _CELL,
        "spaced": _BASE + "#table { display: table; border-spacing: 8px; }\n#a { padding: 4px; }\n" + _CELL,
        "wrap": _BASE + "#table { display: table; width: 40px; }\n#a { padding: 0px 10px; }\n" + _CELL,
        "uneven": _BASE
        + "#table { display: table; }\n#a { padding-top: 5px; padding-right: 9px; "
        + "padding-bottom: 7px; padding-left: 3px; border-top-width: 2px; "
        + "border-right-width: 6px; border-bottom-width: 1px; border-left-width: 4px; "
        + "border-style: solid; }\n"
        + _CELL,
        "bottom": _BASE + "#table { display: table; }\n#a { padding-bottom: 6px; }\n" + _CELL,
        "medium": _BASE + "#table { display: table; }\n#a { border-style: solid; }\n" + _CELL,
        "none": _BASE + "#table { display: table; }\n#a { border-width: 8px; border-style: none; }\n" + _CELL,
        "empty_show": _BASE + "#table { display: table; empty-cells: show; }\n#a { padding: 4px; }\n" + _CELL,
        "empty_hide": _BASE + "#table { display: table; empty-cells: hide; }\n#a { padding: 4px; }\n" + _CELL,
        "align": _BASE + "#table { display: table; }\n#a { padding-top: 6px; }\n" + _CELL,
        "collapse": _BASE
        + "#table { display: table; border-collapse: collapse; }\n#a { padding: 4px; }\n"
        + _CELL,
        "fixed": _BASE
        + "#table { display: table; table-layout: fixed; width: 80px; }\n#a { padding: 4px; }\n"
        + _CELL,
        "percent": _BASE + "#table { display: table; }\n#a { padding: 10%; }\n" + _CELL,
        "negative": _BASE + "#table { display: table; }\n#a { padding: -1px; }\n" + _CELL,
        "span": _BASE + "#table { display: table; }\n#a { padding: 4px; }\n" + _CELL,
        "child": _BASE + "#table { display: table; }\n#a { padding: 4px; }\n" + _CELL,
    }
    markup = {
        "pad": _ONE,
        "border": _ONE,
        "both": _ONE,
        "pair": _PAIR,
        "spaced": _ONE,
        "wrap": _WRAP,
        "uneven": _ONE,
        "bottom": _ONE,
        "medium": _ONE,
        "none": _ONE,
        "empty_show": _STACK,
        "empty_hide": _STACK,
        "align": _ALIGN,
        "collapse": _ONE,
        "fixed": _ONE,
        "percent": _ONE,
        "negative": _ONE,
        "span": _SPAN,
        "child": _CHILD,
    }
    cases = {name: _lay(layout_normal_flow, markup[name], sheets[name]) for name in sheets}
    observed = {
        name: {
            "table": _spot(result, "table"),
            "a": _spot(result, "a"),
            "a2": _spot(result, "a", 1),
            "b": _spot(result, "b"),
            "next": _spot(result, "next"),
        }
        for name, result in cases.items()
    }

    def at(name: str, ident: str, field: str, index: int = 0) -> object:
        return _spot(cases[name], ident, index).get(field)

    def rejected(name: str) -> bool:
        return cases[name].get("outcome") == "invalid" and cases[name].get("reason") == "table cell edge is unsupported"

    checks = {
        "pad_insets_and_grows_the_table": (
            at("pad", "a", "x") == 6
            and at("pad", "a", "y") == 4
            and at("pad", "table", "width") == 32
            and at("pad", "next", "y") == 18
        ),
        "border_insets_the_line": (
            at("border", "a", "x") == 2
            and at("border", "a", "y") == 2
            and at("border", "table", "width") == 24
            and at("border", "next", "y") == 14
        ),
        "padding_and_border_add": (
            at("both", "a", "x") == 6
            and at("both", "a", "y") == 6
            and at("both", "table", "width") == 32
            and at("both", "next", "y") == 22
        ),
        "next_cell_starts_after_chrome": (
            at("pair", "a", "x") == 4 and at("pair", "b", "x") == 32 and at("pair", "next", "y") == 10
        ),
        "spacing_stays_outside_the_border": (
            at("spaced", "a", "x") == 12
            and at("spaced", "a", "y") == 12
            and at("spaced", "table", "width") == 44
            and at("spaced", "next", "y") == 34
        ),
        "text_wraps_inside_the_content_box": (
            at("wrap", "a", "x") == 10
            and at("wrap", "a", "y") == 0
            and at("wrap", "a", "lines") == 2
            and at("wrap", "a", "y", 1) == 10
            and at("wrap", "next", "y") == 20
        ),
        "uneven_edges_inset_independently": (
            at("uneven", "a", "x") == 7
            and at("uneven", "a", "y") == 7
            and at("uneven", "table", "width") == 42
            and at("uneven", "next", "y") == 25
        ),
        "bottom_padding_keeps_the_line_and_moves_the_next_block": (
            at("bottom", "a", "y") == 0 and at("bottom", "next", "y") == 16 and at("bottom", "table", "width") == 20
        ),
        "medium_border_is_3px": (
            at("medium", "a", "x") == 3
            and at("medium", "a", "y") == 3
            and at("medium", "table", "width") == 26
            and at("medium", "next", "y") == 16
        ),
        "none_style_adds_no_border": (
            at("none", "a", "x") == 0
            and at("none", "a", "y") == 0
            and at("none", "table", "width") == 20
            and at("none", "next", "y") == 10
        ),
        "shown_empty_cell_keeps_vertical_padding": at("empty_show", "b", "y") == 8 and at("empty_show", "next", "y") == 18,
        "hidden_empty_cell_still_drops_the_row": at("empty_hide", "b", "y") == 0 and at("empty_hide", "next", "y") == 10,
        "baseline_aligns_across_padding": at("align", "a", "y") == 6 and at("align", "b", "y") == 6 and at("align", "next", "y") == 16,
        "collapsed_padding_is_rejected": rejected("collapse"),
        "fixed_padding_is_rejected": rejected("fixed"),
        "percentage_padding_is_rejected": rejected("percent"),
        "negative_padding_is_rejected": rejected("negative"),
        "spanned_padding_is_rejected": rejected("span"),
        "block_child_padding_is_rejected": rejected("child"),
    }
    return all(checks.values()), {"checks": checks, "observed": observed}


def main() -> None:
    passed, observed = observe()
    json.dump({"passed": passed, "observed": observed}, sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
