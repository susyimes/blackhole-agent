"""Place a shifted inline on the same line as an inline-block.

In a 200px viewport, a 10px paragraph with line-height 10px places A, a span
B at vertical-align 10px, an inline-block C, and D on one line of content
width 40 and height 20. B is at y 0. A and D are at y 10. The inline-block
border box is at x 20 y 10 and paints C. The next block starts at y 20.
vertical-align -10px puts B at y 10 and A, D, and the inline-block at y 0.
A 100 percent alignment matches the 10px raise. vertical-align top on the
inline-block sits that box at y 0 beside the raised letter. A 25px width
wraps A and B on a 20px line and the inline-block with D on a 10px line at
y 20, and the next block starts at y 30. sub lowers B by 2px beside the
inline-block, grows the line to 12px, and starts the next block at y 12.
An inline-block nested inside the shifted span, inherit, and padding beside
the shift stay rejected.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A layout that still rejects the pair exits 0 with passed
false.
"""

from __future__ import annotations

import json

_PAGE = '<div id="page"><p id="row">A<span id="b">B</span><span id="atom">C</span>D</p><p id="next">Z</p></div>'
_NEST = '<div id="page"><p id="row">A<span id="s">B<span id="atom">C</span></span>D</p><p id="next">Z</p></div>'
_BASE = "html, body, div, p, span { margin: 0px; font-size: 10px; line-height: 10px; }\n"
_ATOM = "#atom { display: inline-block; }\n"
_RAISE = _BASE + "#b { vertical-align: 10px; } " + _ATOM
_LOWER = _BASE + "#b { vertical-align: -10px; } " + _ATOM
_PERCENT = _BASE + "#b { vertical-align: 100%; } " + _ATOM
_TOP = _BASE + "#b { vertical-align: 10px; } #atom { display: inline-block; vertical-align: top; }\n"
_WRAP = _BASE + "#row { width: 25px; } #b { vertical-align: 10px; } " + _ATOM
_NEST_CSS = _BASE + "#s { vertical-align: 10px; } " + _ATOM
_SUB = _BASE + "#b { vertical-align: sub; } " + _ATOM
_INHERIT = _BASE + "#b { vertical-align: inherit; } " + _ATOM
_PAD = _BASE + "#b { vertical-align: 10px; padding-left: 10px; } " + _ATOM

_RAISED_RUNS = [
    {"text": "A", "x": 0, "font_size": 10, "width": 10, "y": 10},
    {"text": "B", "x": 10, "font_size": 10, "width": 10, "y": 0},
    {"text": "D", "x": 30, "font_size": 10, "width": 10, "y": 10},
]


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


def _glyph(box: dict[str, object] | None) -> str | None:
    line = _line(box, 0)
    if line is None:
        return None
    text = line.get("text")
    return text if isinstance(text, str) else None


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without the pair still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    raised = _lay(layout_normal_flow, _PAGE, _RAISE)
    lowered = _lay(layout_normal_flow, _PAGE, _LOWER)
    percent = _lay(layout_normal_flow, _PAGE, _PERCENT)
    topped = _lay(layout_normal_flow, _PAGE, _TOP)
    wrapped = _lay(layout_normal_flow, _PAGE, _WRAP)
    nested = _lay(layout_normal_flow, _NEST, _NEST_CSS)
    sub = _lay(layout_normal_flow, _PAGE, _SUB)
    inherited = _lay(layout_normal_flow, _PAGE, _INHERIT)
    padded = _lay(layout_normal_flow, _PAGE, _PAD)

    raise_row = _box(raised.get("boxes"), "row")
    raise_atom = _box(raised.get("boxes"), "atom")
    raise_next = _box(raised.get("boxes"), "next")
    lower_row = _box(lowered.get("boxes"), "row")
    lower_atom = _box(lowered.get("boxes"), "atom")
    lower_next = _box(lowered.get("boxes"), "next")
    percent_row = _box(percent.get("boxes"), "row")
    percent_atom = _box(percent.get("boxes"), "atom")
    top_row = _box(topped.get("boxes"), "row")
    top_atom = _box(topped.get("boxes"), "atom")
    top_next = _box(topped.get("boxes"), "next")
    wrap_row = _box(wrapped.get("boxes"), "row")
    wrap_atom = _box(wrapped.get("boxes"), "atom")
    wrap_next = _box(wrapped.get("boxes"), "next")
    raise_line = _line(raise_row, 0)
    lower_line = _line(lower_row, 0)
    percent_line = _line(percent_row, 0)
    top_line = _line(top_row, 0)

    observed = {
        "raise": {
            "outcome": raised.get("outcome"),
            "reason": raised.get("reason"),
            "line": None
            if raise_line is None
            else {"height": raise_line.get("height"), "text": raise_line.get("text"), "runs": _runs(raise_line)},
            "atom": None
            if raise_atom is None
            else {"x": raise_atom.get("x"), "y": raise_atom.get("y"), "text": _glyph(raise_atom)},
            "next": None if raise_next is None else raise_next.get("y"),
        },
        "lower": {
            "outcome": lowered.get("outcome"),
            "runs": _runs(lower_line),
            "atom_y": None if lower_atom is None else lower_atom.get("y"),
            "next": None if lower_next is None else lower_next.get("y"),
        },
        "percent": {
            "outcome": percent.get("outcome"),
            "runs": _runs(percent_line),
            "atom_y": None if percent_atom is None else percent_atom.get("y"),
        },
        "top": {
            "outcome": topped.get("outcome"),
            "runs": _runs(top_line),
            "atom_y": None if top_atom is None else top_atom.get("y"),
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
            "atom": None
            if wrap_atom is None
            else {"x": wrap_atom.get("x"), "y": wrap_atom.get("y"), "text": _glyph(wrap_atom)},
            "next": None if wrap_next is None else wrap_next.get("y"),
        },
        "nested": {"outcome": nested.get("outcome"), "reason": nested.get("reason")},
        "sub": {"outcome": sub.get("outcome"), "reason": sub.get("reason")},
        "inherit": {"outcome": inherited.get("outcome"), "reason": inherited.get("reason")},
        "padding": {"outcome": padded.get("outcome"), "reason": padded.get("reason")},
    }
    checks = {
        "shifted_glyph_leaves_the_atomic_baseline": (
            raised.get("outcome") == "placed"
            and _near(raise_line, text="ABD", x=0, y=0, content_width=40, height=20)
            and _line(raise_row, 1) is None
            and _runs(raise_line) == _RAISED_RUNS
            and _near(raise_atom, x=20, y=10, content_width=10, content_height=10, border_width=10, border_height=10)
            and _glyph(raise_atom) == "C"
            and _near(raise_next, y=20)
        ),
        "negative_length_lowers_the_glyph": (
            lowered.get("outcome") == "placed"
            and _near(lower_line, text="ABD", content_width=40, height=20)
            and _runs(lower_line)
            == [
                {"text": "A", "x": 0, "font_size": 10, "width": 10, "y": 0},
                {"text": "B", "x": 10, "font_size": 10, "width": 10, "y": 10},
                {"text": "D", "x": 30, "font_size": 10, "width": 10, "y": 0},
            ]
            and _near(lower_atom, x=20, y=0, content_height=10)
            and _glyph(lower_atom) == "C"
            and _near(lower_next, y=20)
        ),
        "percentage_matches_the_length": (
            percent.get("outcome") == "placed"
            and _runs(percent_line) == _RAISED_RUNS
            and _near(percent_atom, x=20, y=10)
        ),
        "atomic_top_meets_the_grown_line": (
            topped.get("outcome") == "placed"
            and _near(top_line, text="ABD", content_width=40, height=20)
            and _runs(top_line) == _RAISED_RUNS
            and _near(top_atom, x=20, y=0, content_height=10)
            and _glyph(top_atom) == "C"
            and _near(top_next, y=20)
        ),
        "short_measure_wraps_before_the_atomic_box": (
            wrapped.get("outcome") == "placed"
            and _near(_line(wrap_row, 0), text="AB", x=0, y=0, content_width=20, height=20)
            and _runs(_line(wrap_row, 0))
            == [
                {"text": "A", "x": 0, "font_size": 10, "width": 10, "y": 10},
                {"text": "B", "x": 10, "font_size": 10, "width": 10, "y": 0},
            ]
            and _near(_line(wrap_row, 1), text="D", x=0, y=20, content_width=20, height=10)
            and _runs(_line(wrap_row, 1)) == [{"text": "D", "x": 10, "font_size": 10, "width": 10}]
            and _line(wrap_row, 2) is None
            and _near(wrap_atom, x=0, y=20, content_width=10, content_height=10)
            and _glyph(wrap_atom) == "C"
            and _near(wrap_next, y=30)
        ),
        "nested_atomic_inside_the_shift_stays_rejected": _invalid(
            nested, "vertical-align beside an inline-block is unsupported"
        ),
        "sub_lowers_the_glyph_beside_the_atomic_box": (
            sub.get("outcome") == "placed"
            and _near(_line(_box(sub.get("boxes"), "row"), 0), text="ABD", x=0, y=0, content_width=40, height=12)
            and _runs(_line(_box(sub.get("boxes"), "row"), 0))
            == [
                {"text": "A", "x": 0, "font_size": 10, "width": 10, "y": 0},
                {"text": "B", "x": 10, "font_size": 10, "width": 10, "y": 2},
                {"text": "D", "x": 30, "font_size": 10, "width": 10, "y": 0},
            ]
            and _near(_box(sub.get("boxes"), "atom"), x=20, y=0, content_width=10, content_height=10)
            and _near(_box(sub.get("boxes"), "next"), y=12)
        ),
        "inherit_stays_rejected": _invalid(inherited, "vertical-align inherit is unsupported"),
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
