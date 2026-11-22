"""Place a table caption above or below the grid in normal flow.

An automatic 10px table of AA beside BB with caption C puts that caption
line at y 0, the second cell line at x 20 y 10, and the following block at
y 20. The table content width stays 40. caption-side bottom puts the cell
line at y 0 and the caption at y 10. The caption's own caption-side wins
over the table. border-spacing 8px puts the second line at x 36 y 18 and
the following block at y 36. AA BB CC wraps to three lines inside the 40px
table and does not move the second cell off x 20. A centered AA sits at
x 10. Left, a second caption, a caption child, a collapsed caption, and a
caption margin are invalid.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A table that still rejects captions exits 0 with passed false.
"""

from __future__ import annotations

import json
import sys

_FONT = "#page { font-size: 10px; line-height: 10px; }\n"
_ROWS = "#row { display: table-row; }\n#a, #b { display: table-cell; }\n"
_PAIR = (
    '<div id="page"><div id="table"><div id="cap">C</div>'
    '<div id="row"><div id="a">AA</div><div id="b">BB</div></div></div>'
    '<p id="next">Z</p></div>'
)
_WIDE = (
    '<div id="page"><div id="table"><div id="cap">AA BB CC</div>'
    '<div id="row"><div id="a">AA</div><div id="b">BB</div></div></div>'
    '<p id="next">Z</p></div>'
)
_CENTER = (
    '<div id="page"><div id="table"><div id="cap">AA</div>'
    '<div id="row"><div id="a">Z</div></div></div><p id="next">Z</p></div>'
)
_TWO = (
    '<div id="page"><div id="table"><div id="cap">C</div><div id="cap2">D</div>'
    '<div id="row"><div id="a">AA</div><div id="b">BB</div></div></div>'
    '<p id="next">Z</p></div>'
)
_CHILD = (
    '<div id="page"><div id="table"><div id="cap"><div id="inner">C</div></div>'
    '<div id="row"><div id="a">AA</div><div id="b">BB</div></div></div>'
    '<p id="next">Z</p></div>'
)
_TOP = _FONT + "#table { display: table; }\n#cap { display: table-caption; }\n" + _ROWS
_BOTTOM = (
    _FONT
    + "#table { display: table; caption-side: bottom; }\n#cap { display: table-caption; }\n"
    + _ROWS
)
_OVERRIDE = (
    _FONT
    + "#table { display: table; caption-side: bottom; }\n"
    + "#cap { display: table-caption; caption-side: top; }\n"
    + _ROWS
)
_SPACE = (
    _FONT
    + "#table { display: table; border-spacing: 8px; }\n#cap { display: table-caption; }\n"
    + _ROWS
)
_WRAP = _FONT + "#table { display: table; }\n#cap { display: table-caption; }\n" + _ROWS
_ALIGNED = (
    _FONT
    + "#table { display: table; table-layout: fixed; width: 40px; }\n"
    + "#cap { display: table-caption; text-align: center; }\n"
    + _ROWS
)
_LEFT = (
    _FONT
    + "#table { display: table; caption-side: left; }\n#cap { display: table-caption; }\n"
    + _ROWS
)
_MARGIN = (
    _FONT
    + "#table { display: table; }\n#cap { display: table-caption; margin-top: 10px; }\n"
    + _ROWS
)
_COLLAPSE = (
    _FONT
    + "#table { display: table; border-collapse: collapse; }\n"
    + "#cap { display: table-caption; }\n"
    + _ROWS
    + "#a, #b { border-width: 4px; border-style: solid; }\n"
)
_SECOND = _FONT + "#table { display: table; }\n#cap, #cap2 { display: table-caption; }\n" + _ROWS
_NESTED = _FONT + "#table { display: table; }\n#cap { display: table-caption; }\n" + _ROWS


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


def _at(result: dict[str, object], ident: str, index: int = 0) -> dict[str, object]:
    box = _box(result.get("boxes"), ident)
    line = _line(box, index)
    return {
        "outcome": result.get("outcome"),
        "reason": result.get("reason"),
        "x": None if box is None else box.get("x"),
        "y": None if box is None else box.get("y"),
        "content_width": None if box is None else box.get("content_width"),
        "content_height": None if box is None else box.get("content_height"),
        "line_text": None if line is None else line.get("text"),
        "line_x": None if line is None else line.get("x"),
        "line_y": None if line is None else line.get("y"),
    }


def _rejected(result: dict[str, object]) -> bool:
    return result.get("outcome") == "invalid" and result.get("boxes") is None


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without placement still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    cases = {
        "top": _lay(layout_normal_flow, _PAIR, _TOP),
        "bottom": _lay(layout_normal_flow, _PAIR, _BOTTOM),
        "override": _lay(layout_normal_flow, _PAIR, _OVERRIDE),
        "space": _lay(layout_normal_flow, _PAIR, _SPACE),
        "wrap": _lay(layout_normal_flow, _WIDE, _WRAP),
        "center": _lay(layout_normal_flow, _CENTER, _ALIGNED),
        "left": _lay(layout_normal_flow, _PAIR, _LEFT),
        "second": _lay(layout_normal_flow, _TWO, _SECOND),
        "child": _lay(layout_normal_flow, _CHILD, _NESTED),
        "margin": _lay(layout_normal_flow, _PAIR, _MARGIN),
        "collapse": _lay(layout_normal_flow, _PAIR, _COLLAPSE),
    }
    observed: dict[str, object] = {
        name: {
            "table": _at(result, "table"),
            "cap": _at(result, "cap"),
            "cap_bb": _at(result, "cap", 1),
            "cap_cc": _at(result, "cap", 2),
            "b": _at(result, "b"),
            "next": _at(result, "next"),
        }
        for name, result in cases.items()
    }
    checks = {
        "top_caption_stacks_above_the_grid": (
            cases["top"].get("outcome") == "placed"
            and _at(cases["top"], "cap").get("line_y") == 0
            and _at(cases["top"], "cap").get("line_x") == 0
            and _at(cases["top"], "cap").get("content_width") == 40
            and _at(cases["top"], "b").get("line_x") == 20
            and _at(cases["top"], "b").get("line_y") == 10
            and _at(cases["top"], "table").get("content_width") == 40
            and _at(cases["top"], "table").get("content_height") == 20
            and _at(cases["top"], "next").get("y") == 20
        ),
        "bottom_caption_stacks_under_the_grid": (
            cases["bottom"].get("outcome") == "placed"
            and _at(cases["bottom"], "b").get("line_y") == 0
            and _at(cases["bottom"], "b").get("line_x") == 20
            and _at(cases["bottom"], "cap").get("line_y") == 10
            and _at(cases["bottom"], "next").get("y") == 20
        ),
        "caption_side_on_the_caption_wins": (
            cases["override"].get("outcome") == "placed"
            and _at(cases["override"], "cap").get("line_y") == 0
            and _at(cases["override"], "b").get("line_y") == 10
            and _at(cases["override"], "next").get("y") == 20
        ),
        "spacing_stays_under_the_caption": (
            cases["space"].get("outcome") == "placed"
            and _at(cases["space"], "b").get("line_x") == 36
            and _at(cases["space"], "b").get("line_y") == 18
            and _at(cases["space"], "cap").get("content_width") == 64
            and _at(cases["space"], "table").get("content_width") == 64
            and _at(cases["space"], "next").get("y") == 36
        ),
        "wrapped_caption_does_not_widen_columns": (
            cases["wrap"].get("outcome") == "placed"
            and _at(cases["wrap"], "table").get("content_width") == 40
            and _at(cases["wrap"], "cap").get("content_width") == 40
            and _at(cases["wrap"], "cap").get("content_height") == 30
            and _at(cases["wrap"], "cap").get("line_text") == "AA"
            and _at(cases["wrap"], "cap", 1).get("line_text") == "BB"
            and _at(cases["wrap"], "cap", 1).get("line_y") == 10
            and _at(cases["wrap"], "cap", 2).get("line_text") == "CC"
            and _at(cases["wrap"], "cap", 2).get("line_y") == 20
            and _at(cases["wrap"], "b").get("line_x") == 20
            and _at(cases["wrap"], "b").get("line_y") == 30
            and _at(cases["wrap"], "next").get("y") == 40
        ),
        "centered_caption_line_uses_the_table_width": (
            cases["center"].get("outcome") == "placed"
            and _at(cases["center"], "cap").get("line_x") == 10
            and _at(cases["center"], "cap").get("line_text") == "AA"
            and _at(cases["center"], "next").get("y") == 20
        ),
        "other_caption_side_is_rejected": _rejected(cases["left"]),
        "second_caption_is_rejected": _rejected(cases["second"]),
        "caption_child_is_rejected": _rejected(cases["child"]),
        "caption_margin_is_rejected": _rejected(cases["margin"]),
        "collapsed_caption_is_rejected": _rejected(cases["collapse"]),
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
