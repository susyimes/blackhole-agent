"""Shift a non-replaced inline off the strut with vertical-align.

In a 200px viewport, a 10px paragraph with line-height 10px places A, a span
B at vertical-align 10px, and C on one line of content width 30 and height
20. B is at y 0. A and C are at y 10. The next block starts at y 20.
vertical-align -10px puts B at y 10 and A and C at y 0, and the next block
at y 20. A 100 percent alignment matches the 10px raise. A parent span at
10px around an inner span at 4px places that inner span at y 0, the parent
letters at y 4, and the outside letters at y 14, with the next block at y
24. vertical-align top on a later span sits that span at y 0 beside the
raised letter. A 15px width wraps A on a 10px line and the raised B on a
20px line, and the next block starts at y 30. sub, inherit, a top alignment
inside a shifted inline, and padding beside the shift stay rejected.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A layout that still ignores the shift exits 0 with passed
false.
"""

from __future__ import annotations

import json

_PAGE = '<div id="page"><p id="row">A<span id="b">B</span>C</p><p id="next">Z</p></div>'
_NEST = '<div id="page"><p id="row">A<span id="s">B<span id="e">C</span>D</span>E</p><p id="next">Z</p></div>'
_TOP = '<div id="page"><p id="row">A<span id="b">B</span>C<span id="d">D</span></p><p id="next">Z</p></div>'
_WRAP = '<div id="page"><p id="row">A <span id="b">B</span></p><p id="next">Z</p></div>'
_BASE = "html, body, div, p, span { margin: 0px; font-size: 10px; line-height: 10px; }\n"
_RAISE = _BASE + "#b { vertical-align: 10px; }\n"
_LOWER = _BASE + "#b { vertical-align: -10px; }\n"
_PERCENT = _BASE + "#b { vertical-align: 100%; }\n"
_NEST_CSS = _BASE + "#s { vertical-align: 10px; } #e { vertical-align: 4px; }\n"
_TOP_CSS = _BASE + "#b { vertical-align: 10px; } #d { vertical-align: top; }\n"
_WRAP_CSS = _BASE + "#row { width: 15px; } #b { vertical-align: 10px; }\n"
_SUB = _BASE + "#b { vertical-align: sub; }\n"
_INHERIT = _BASE + "#b { vertical-align: inherit; }\n"
_NESTED_TOP = _BASE + "#s { vertical-align: 10px; } #e { vertical-align: top; }\n"
_PAD = _BASE + "#b { vertical-align: 10px; padding-left: 10px; }\n"


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


def _runs(line: dict[str, object] | None) -> object:
    if line is None:
        return None
    return line.get("runs")


def _invalid(placed: dict[str, object], reason: str) -> bool:
    return placed.get("outcome") == "invalid" and placed.get("reason") == reason


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without the shift still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    raised = _lay(layout_normal_flow, _PAGE, _RAISE)
    lowered = _lay(layout_normal_flow, _PAGE, _LOWER)
    percent = _lay(layout_normal_flow, _PAGE, _PERCENT)
    nested = _lay(layout_normal_flow, _NEST, _NEST_CSS)
    topped = _lay(layout_normal_flow, _TOP, _TOP_CSS)
    wrapped = _lay(layout_normal_flow, _WRAP, _WRAP_CSS)
    sub = _lay(layout_normal_flow, _PAGE, _SUB)
    inherited = _lay(layout_normal_flow, _PAGE, _INHERIT)
    nested_top = _lay(layout_normal_flow, _NEST, _NESTED_TOP)
    padded = _lay(layout_normal_flow, _PAGE, _PAD)

    raise_row = _box(raised.get("boxes"), "row")
    raise_next = _box(raised.get("boxes"), "next")
    lower_row = _box(lowered.get("boxes"), "row")
    lower_next = _box(lowered.get("boxes"), "next")
    percent_row = _box(percent.get("boxes"), "row")
    nest_row = _box(nested.get("boxes"), "row")
    nest_next = _box(nested.get("boxes"), "next")
    top_row = _box(topped.get("boxes"), "row")
    top_next = _box(topped.get("boxes"), "next")
    wrap_row = _box(wrapped.get("boxes"), "row")
    wrap_next = _box(wrapped.get("boxes"), "next")
    raise_line = _line(raise_row, 0)
    lower_line = _line(lower_row, 0)
    percent_line = _line(percent_row, 0)
    nest_line = _line(nest_row, 0)
    top_line = _line(top_row, 0)

    observed = {
        "raise": {
            "outcome": raised.get("outcome"),
            "reason": raised.get("reason"),
            "line": None
            if raise_line is None
            else {"height": raise_line.get("height"), "runs": _runs(raise_line)},
            "next": None if raise_next is None else raise_next.get("y"),
        },
        "lower": {
            "outcome": lowered.get("outcome"),
            "height": None if lower_line is None else lower_line.get("height"),
            "runs": _runs(lower_line),
            "next": None if lower_next is None else lower_next.get("y"),
        },
        "percent": {"outcome": percent.get("outcome"), "runs": _runs(percent_line)},
        "nest": {
            "outcome": nested.get("outcome"),
            "height": None if nest_line is None else nest_line.get("height"),
            "runs": _runs(nest_line),
            "next": None if nest_next is None else nest_next.get("y"),
        },
        "top": {
            "outcome": topped.get("outcome"),
            "runs": _runs(top_line),
            "next": None if top_next is None else top_next.get("y"),
        },
        "wrap": {
            "outcome": wrapped.get("outcome"),
            "lines": [
                None
                if _line(wrap_row, index) is None
                else {
                    "text": _line(wrap_row, index).get("text"),
                    "y": _line(wrap_row, index).get("y"),
                    "height": _line(wrap_row, index).get("height"),
                    "runs": _runs(_line(wrap_row, index)),
                }
                for index in range(2)
            ],
            "next": None if wrap_next is None else wrap_next.get("y"),
        },
        "sub": {"outcome": sub.get("outcome"), "reason": sub.get("reason")},
        "inherit": {"outcome": inherited.get("outcome"), "reason": inherited.get("reason")},
        "nested_top": {"outcome": nested_top.get("outcome"), "reason": nested_top.get("reason")},
        "padding": {"outcome": padded.get("outcome"), "reason": padded.get("reason")},
    }
    checks = {
        "length_raises_one_run": (
            raised.get("outcome") == "placed"
            and _near(raise_line, text="ABC", x=0, y=0, content_width=30, height=20)
            and _line(raise_row, 1) is None
            and _runs(raise_line)
            == [
                {"text": "A", "x": 0, "font_size": 10, "width": 10, "y": 10},
                {"text": "B", "x": 10, "font_size": 10, "width": 10, "y": 0},
                {"text": "C", "x": 20, "font_size": 10, "width": 10, "y": 10},
            ]
            and _near(raise_next, y=20)
        ),
        "negative_length_lowers_one_run": (
            lowered.get("outcome") == "placed"
            and _near(lower_line, text="ABC", content_width=30, height=20)
            and _runs(lower_line)
            == [
                {"text": "A", "x": 0, "font_size": 10, "width": 10, "y": 0},
                {"text": "B", "x": 10, "font_size": 10, "width": 10, "y": 10},
                {"text": "C", "x": 20, "font_size": 10, "width": 10, "y": 0},
            ]
            and _near(lower_next, y=20)
        ),
        "percentage_matches_the_length": (
            percent.get("outcome") == "placed"
            and _near(percent_line, text="ABC", content_width=30, height=20)
            and _runs(percent_line) == _runs(raise_line)
            and isinstance(_runs(raise_line), list)
        ),
        "nested_lengths_add": (
            nested.get("outcome") == "placed"
            and _near(nest_line, text="ABCDE", content_width=50, height=24)
            and _runs(nest_line)
            == [
                {"text": "A", "x": 0, "font_size": 10, "width": 10, "y": 14},
                {"text": "B", "x": 10, "font_size": 10, "width": 10, "y": 4},
                {"text": "C", "x": 20, "font_size": 10, "width": 10, "y": 0},
                {"text": "D", "x": 30, "font_size": 10, "width": 10, "y": 4},
                {"text": "E", "x": 40, "font_size": 10, "width": 10, "y": 14},
            ]
            and _near(nest_next, y=24)
        ),
        "top_meets_the_line_top": (
            topped.get("outcome") == "placed"
            and _near(top_line, text="ABCD", content_width=40, height=20)
            and _runs(top_line)
            == [
                {"text": "A", "x": 0, "font_size": 10, "width": 10, "y": 10},
                {"text": "B", "x": 10, "font_size": 10, "width": 10, "y": 0},
                {"text": "C", "x": 20, "font_size": 10, "width": 10, "y": 10},
                {"text": "D", "x": 30, "font_size": 10, "width": 10, "y": 0},
            ]
            and _near(top_next, y=20)
        ),
        "short_measure_wraps_before_the_shift": (
            wrapped.get("outcome") == "placed"
            and _near(_line(wrap_row, 0), text="A", x=0, y=0, content_width=10, height=10)
            and _near(_line(wrap_row, 1), text="B", x=0, y=10, content_width=10, height=20)
            and _runs(_line(wrap_row, 1)) == [{"text": "B", "x": 0, "font_size": 10, "width": 10, "y": 10}]
            and _line(wrap_row, 2) is None
            and _near(wrap_next, y=30)
        ),
        "sub_stays_rejected": _invalid(sub, "vertical-align is unsupported"),
        "inherit_stays_rejected": _invalid(inherited, "vertical-align inherit is unsupported"),
        "nested_keyword_stays_rejected": _invalid(nested_top, "nested vertical-align is unsupported"),
        "padding_beside_the_shift_stays_rejected": _invalid(padded, "inline chrome is unsupported"),
    }
    return all(checks.values()), {"checks": checks, "cases": observed}


def main() -> None:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - the probe must exit 0 either way
        passed, observed = False, {"error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps({"passed": bool(passed), "observed": observed}, sort_keys=True))


if __name__ == "__main__":
    main()
