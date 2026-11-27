"""Lay out an empty table cell and omit a fully hidden empty row.

On a marginless page at 10px font and line-height, an empty cell above BB
with border-spacing 0 12px keeps the BB line at y 24 and the following block
at y 46 when empty-cells is show. hide moves that line to y 12 and the
following block to y 34. A visible letter, or one show cell in the empty row,
keeps y 46. Whitespace that collapses is empty. Two empty hide rows leave the
following block at y 12. A hidden empty row between AA and CC puts CC at y 34
and the following block at y 56; show keeps CC at y 46 and the block at y 68.
border-collapse ignores hide. A specified height that would omit a row is
rejected, and a bad keyword is rejected.

Prints JSON with boolean passed and nonempty observed. Exit 0 either way.
"""

from __future__ import annotations

import json
import sys

_BASE = "html, body, div, p { margin: 0px; font-size: 10px; line-height: 10px; }\n"
_ROWS = "#r1, #r2, #r3 { display: table-row; }\n#a, #b, #c, #d { display: table-cell; }\n"
_ONE = (
    '<div id="page"><div id="table"><div id="r1"><div id="a"></div></div>'
    '<div id="r2"><div id="b">BB</div></div></div><p id="next">Z</p></div>'
)
_LETTER = (
    '<div id="page"><div id="table"><div id="r1"><div id="a">Q</div></div>'
    '<div id="r2"><div id="b">BB</div></div></div><p id="next">Z</p></div>'
)
_PAIR = (
    '<div id="page"><div id="table"><div id="r1"><div id="a"></div><div id="d"></div></div>'
    '<div id="r2"><div id="b">BB</div></div></div><p id="next">Z</p></div>'
)
_BLANK = (
    '<div id="page"><div id="table"><div id="r1"><div id="a">   </div></div>'
    '<div id="r2"><div id="b">BB</div></div></div><p id="next">Z</p></div>'
)
_BOTH = (
    '<div id="page"><div id="table"><div id="r1"><div id="a"></div></div>'
    '<div id="r2"><div id="b"></div></div></div><p id="next">Z</p></div>'
)
_MID = (
    '<div id="page"><div id="table"><div id="r1"><div id="a">AA</div></div>'
    '<div id="r2"><div id="b"></div></div>'
    '<div id="r3"><div id="c">CC</div></div></div><p id="next">Z</p></div>'
)
_SHOW = "#table { display: table; border-spacing: 0 12px; empty-cells: show; }\n"
_HIDE = "#table { display: table; border-spacing: 0 12px; empty-cells: hide; }\n"
_OMIT = "#table { display: table; border-spacing: 0 12px; }\n"
_SPLIT = _HIDE + "#d { empty-cells: show; }\n"
_INHERIT = _HIDE + "#a { empty-cells: inherit; }\n"
_BAD = "#table { display: table; border-spacing: 0 12px; empty-cells: nope; }\n"
_COLLAPSE_HIDE = "#table { display: table; border-collapse: collapse; empty-cells: hide; }\n"
_COLLAPSE_SHOW = "#table { display: table; border-collapse: collapse; empty-cells: show; }\n"
_HEIGHT = "#table { display: table; height: 40px; border-spacing: 0 12px; empty-cells: hide; }\n"


def _box(boxes: object, ident: str) -> dict[str, object] | None:
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if isinstance(item, dict) and item.get("id") == ident:
            return item
    return None


def _line_y(box: dict[str, object] | None) -> object:
    if box is None or not isinstance(box.get("lines"), list) or not box["lines"]:
        return None
    line = box["lines"][0]
    return line.get("y") if isinstance(line, dict) else None


def _lay(layout, markup: str, stylesheet: str) -> dict[str, object]:
    try:
        placed = layout(markup, stylesheet, viewport_width=240)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def _spot(result: dict[str, object], ident: str) -> dict[str, object]:
    box = _box(result.get("boxes"), ident)
    return {
        "outcome": result.get("outcome"),
        "reason": result.get("reason"),
        "y": None if box is None else box.get("y"),
        "content_height": None if box is None else box.get("content_height"),
        "line_y": _line_y(box),
    }


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without placement still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    sheet = _BASE + _ROWS
    cases = {
        "omit": _lay(layout_normal_flow, _ONE, sheet + _OMIT),
        "show": _lay(layout_normal_flow, _ONE, sheet + _SHOW),
        "hide": _lay(layout_normal_flow, _ONE, sheet + _HIDE),
        "letter": _lay(layout_normal_flow, _LETTER, sheet + _HIDE),
        "split": _lay(layout_normal_flow, _PAIR, sheet + _SPLIT),
        "blank": _lay(layout_normal_flow, _BLANK, sheet + _HIDE),
        "both": _lay(layout_normal_flow, _BOTH, sheet + _HIDE),
        "mid_hide": _lay(layout_normal_flow, _MID, sheet + _HIDE),
        "mid_show": _lay(layout_normal_flow, _MID, sheet + _SHOW),
        "inherit": _lay(layout_normal_flow, _ONE, sheet + _INHERIT),
        "bad": _lay(layout_normal_flow, _ONE, sheet + _BAD),
        "collapse_hide": _lay(layout_normal_flow, _ONE, sheet + _COLLAPSE_HIDE),
        "collapse_show": _lay(layout_normal_flow, _ONE, sheet + _COLLAPSE_SHOW),
        "height": _lay(layout_normal_flow, _ONE, sheet + _HEIGHT),
    }
    observed: dict[str, object] = {
        name: {"table": _spot(result, "table"), "b": _spot(result, "b"), "c": _spot(result, "c"), "next": _spot(result, "next"), "r1": _spot(result, "r1")}
        for name, result in cases.items()
    }

    def placed(name: str) -> bool:
        return cases[name].get("outcome") == "placed"

    def at(name: str, ident: str, field: str) -> object:
        return _spot(cases[name], ident).get(field)

    checks = {
        "show_keeps_both_spacing_sides": (
            placed("omit")
            and placed("show")
            and at("omit", "b", "line_y") == 24
            and at("omit", "next", "y") == 46
            and at("omit", "table", "content_height") == 46
            and at("omit", "r1", "content_height") == 0
            and at("show", "b", "line_y") == 24
            and at("show", "next", "y") == 46
        ),
        "hide_omits_the_gap_after_an_empty_row": (
            placed("hide")
            and at("hide", "b", "line_y") == 12
            and at("hide", "next", "y") == 34
            and at("hide", "table", "content_height") == 34
            and at("hide", "r1", "content_height") == 0
        ),
        "visible_text_keeps_the_row": (
            placed("letter")
            and at("letter", "r1", "content_height") == 10
            and at("letter", "b", "line_y") == 34
            and at("letter", "next", "y") == 56
        ),
        "one_show_cell_keeps_the_empty_row": (
            placed("split") and at("split", "b", "line_y") == 24 and at("split", "next", "y") == 46
        ),
        "collapsed_whitespace_is_empty": (
            placed("blank") and at("blank", "b", "line_y") == 12 and at("blank", "next", "y") == 34
        ),
        "every_hidden_row_keeps_the_leading_gap": (
            placed("both") and at("both", "table", "content_height") == 12 and at("both", "next", "y") == 12
        ),
        "a_hidden_middle_row_keeps_one_gap": (
            placed("mid_hide")
            and at("mid_hide", "c", "line_y") == 34
            and at("mid_hide", "next", "y") == 56
            and placed("mid_show")
            and at("mid_show", "c", "line_y") == 46
            and at("mid_show", "next", "y") == 68
        ),
        "inherit_uses_the_table_value": (
            placed("inherit") and at("inherit", "b", "line_y") == 12 and at("inherit", "next", "y") == 34
        ),
        "collapsed_borders_ignore_empty_cells": (
            placed("collapse_hide")
            and placed("collapse_show")
            and at("collapse_hide", "b", "line_y") == 0
            and at("collapse_hide", "next", "y") == 10
            and at("collapse_show", "b", "line_y") == at("collapse_hide", "b", "line_y")
            and at("collapse_show", "next", "y") == at("collapse_hide", "next", "y")
        ),
        "specified_height_that_would_omit_a_row_is_rejected": (
            cases["height"].get("outcome") == "invalid" and cases["height"].get("boxes") is None
        ),
        "bad_keyword_is_rejected": cases["bad"].get("outcome") == "invalid" and cases["bad"].get("boxes") is None,
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
