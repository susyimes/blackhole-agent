"""Separate table cells by border-spacing in normal flow.

An automatic table of AA beside BB at 10px, with border-spacing 8px, puts the
second line at x 36 and the following block at y 26. The table content width
is 64, including a gap outside both edges. border-spacing 4px 12px puts that
line at x 28 and the following block at y 34. Two rows with border-spacing
0 12px put the second line at y 34 and the following block at y 56. A fixed
80px table with border-spacing 10px puts the second line at x 45 inside
content width 80 and the following block at y 30. Collapsed 4px borders keep
the second line at x 28 and the following block at y 18 even when spacing is
10px. A negative length is invalid.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A table that still rejects spacing exits 0 with passed false.
"""

from __future__ import annotations

import json
import sys

_FONT = "#page { font-size: 10px; line-height: 10px; }\n"
_PAIR = (
    '<div id="page"><div id="table"><div id="row"><div id="a">AA</div>'
    '<div id="b">BB</div></div></div><p id="next">Z</p></div>'
)
_STACK = (
    '<div id="page"><div id="table"><div id="r1"><div id="a">AA</div></div>'
    '<div id="r2"><div id="b">BB</div></div></div><p id="next">Z</p></div>'
)
_ROWS = "#row, #r1, #r2 { display: table-row; }\n#a, #b { display: table-cell; }\n"
_AUTO = _FONT + "#table { display: table; border-spacing: 8px; }\n" + _ROWS
_AXES = _FONT + "#table { display: table; border-spacing: 4px 12px; }\n" + _ROWS
_VERTICAL = _FONT + "#table { display: table; border-spacing: 0 12px; }\n" + _ROWS
_FIXED = (
    _FONT
    + "#table { display: table; table-layout: fixed; width: 80px; border-spacing: 10px; }\n"
    + _ROWS
)
_COLLAPSE = (
    _FONT
    + "#table { display: table; border-collapse: collapse; border-spacing: 10px; }\n"
    + _ROWS
    + "#a, #b { border-width: 4px; border-style: solid; }\n"
)
_NEGATIVE = _FONT + "#table { display: table; border-spacing: -1px; }\n" + _ROWS


def _box(boxes: object, ident: str) -> dict[str, object] | None:
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if isinstance(item, dict) and item.get("id") == ident:
            return item
    return None


def _line(box: dict[str, object] | None) -> dict[str, object] | None:
    if box is None or not isinstance(box.get("lines"), list) or not box["lines"]:
        return None
    line = box["lines"][0]
    return line if isinstance(line, dict) else None


def _lay(layout, markup: str, stylesheet: str) -> dict[str, object]:
    try:
        placed = layout(markup, stylesheet, viewport_width=240)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def _at(result: dict[str, object], ident: str) -> dict[str, object]:
    box = _box(result.get("boxes"), ident)
    line = _line(box)
    return {
        "outcome": result.get("outcome"),
        "reason": result.get("reason"),
        "x": None if box is None else box.get("x"),
        "y": None if box is None else box.get("y"),
        "content_width": None if box is None else box.get("content_width"),
        "line_x": None if line is None else line.get("x"),
        "line_y": None if line is None else line.get("y"),
    }


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without placement still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    cases = {
        "gap": _lay(layout_normal_flow, _PAIR, _AUTO),
        "axes": _lay(layout_normal_flow, _PAIR, _AXES),
        "rows": _lay(layout_normal_flow, _STACK, _VERTICAL),
        "fixed": _lay(layout_normal_flow, _PAIR, _FIXED),
        "collapsed": _lay(layout_normal_flow, _PAIR, _COLLAPSE),
        "negative": _lay(layout_normal_flow, _PAIR, _NEGATIVE),
    }
    observed: dict[str, object] = {
        name: {
            "table": _at(result, "table"),
            "b": _at(result, "b"),
            "next": _at(result, "next"),
        }
        for name, result in cases.items()
    }
    checks = {
        "horizontal_gap_includes_both_outer_edges": (
            cases["gap"].get("outcome") == "placed"
            and _at(cases["gap"], "b").get("line_x") == 36
            and _at(cases["gap"], "table").get("content_width") == 64
            and _at(cases["gap"], "next").get("y") == 26
        ),
        "horizontal_and_vertical_lengths_stay_distinct": (
            cases["axes"].get("outcome") == "placed"
            and _at(cases["axes"], "b").get("line_x") == 28
            and _at(cases["axes"], "next").get("y") == 34
        ),
        "vertical_gap_separates_the_next_row": (
            cases["rows"].get("outcome") == "placed"
            and _at(cases["rows"], "b").get("line_y") == 34
            and _at(cases["rows"], "b").get("line_x") == 0
            and _at(cases["rows"], "next").get("y") == 56
        ),
        "fixed_width_keeps_the_gap_between_columns": (
            cases["fixed"].get("outcome") == "placed"
            and _at(cases["fixed"], "b").get("line_x") == 45
            and _at(cases["fixed"], "table").get("content_width") == 80
            and _at(cases["fixed"], "next").get("y") == 30
        ),
        "collapsed_borders_ignore_spacing": (
            cases["collapsed"].get("outcome") == "placed"
            and _at(cases["collapsed"], "b").get("line_x") == 28
            and _at(cases["collapsed"], "next").get("y") == 18
        ),
        "negative_spacing_is_rejected": (
            cases["negative"].get("outcome") == "invalid" and cases["negative"].get("boxes") is None
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
