"""Size ::before and ::after glyphs with their own font metrics.

In a 200px viewport, a 10px paragraph with line-height 10px places ::before
AB at font-size 20px and line-height 20px beside CD. The line is 70 wide and
20 tall, and the next block starts at y 20. A 45px width wraps AB, then CD,
and the next block starts at y 30. ::after EF at 30px by 30px makes the
unwrapped line 130 wide and 30 tall. A span's ::before X makes AXBC 50 wide
and 20 tall. An omitted line-height keeps the 10px leading, so the same AB CD
line is 15 tall. A percentage font-size is invalid. A margin on the pseudo
stays rejected. A flex container and an absolute box stay rejected.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A layout that still rejects the font exits 0 with passed
false.
"""

from __future__ import annotations

import json

_PAGE = '<div id="page"><p id="row"> CD</p><p id="next">Z</p></div>'
_SPAN = '<div id="page"><p id="row">A<span id="s">B</span>C</p><p id="next">Z</p></div>'
_FLEX = '<div id="page"><div id="row">CD</div><p id="next">Z</p></div>'
_ABS = '<div id="page"><p id="host">ZZ</p><p id="abs">CD</p></div>'
_BASE = "html, body, div, p, span { margin: 0px; font-size: 10px; line-height: 10px; }\n"
_BEFORE = '#row::before { content: "AB"; font-size: 20px; line-height: 20px; }\n'
_FIT = _BASE + _BEFORE
_WRAP = _BASE + "#row { width: 45px; }\n" + _BEFORE
_AFTER = _BASE + _BEFORE + '#row::after { content: "EF"; font-size: 30px; line-height: 30px; }\n'
_SPAN_CSS = _BASE + '#s::before { content: "X"; font-size: 20px; line-height: 20px; }\n'
_INHERIT = _BASE + '#row::before { content: "AB"; font-size: 20px; }\n'
_PERCENT = _BASE + '#row::before { content: "AB"; font-size: 50%; }\n'
_MARGIN = _BASE + '#row::before { content: "AB"; margin-left: 10px; }\n'
_FLEX_CSS = _BASE + "#row { display: flex; }\n" + _BEFORE
_ABS_CSS = _BASE + "#abs { position: absolute; }\n" + '#abs::before { content: "AB"; font-size: 20px; line-height: 20px; }\n'


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


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without placement still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    fit = _lay(layout_normal_flow, _PAGE, _FIT)
    wrap = _lay(layout_normal_flow, _PAGE, _WRAP)
    after = _lay(layout_normal_flow, _PAGE, _AFTER)
    spanned = _lay(layout_normal_flow, _SPAN, _SPAN_CSS)
    inherited = _lay(layout_normal_flow, _PAGE, _INHERIT)
    percent = _lay(layout_normal_flow, _PAGE, _PERCENT)
    margin = _lay(layout_normal_flow, _PAGE, _MARGIN)
    flexed = _lay(layout_normal_flow, _FLEX, _FLEX_CSS)
    absolute = _lay(layout_normal_flow, _ABS, _ABS_CSS)

    fit_row = _box(fit.get("boxes"), "row")
    fit_next = _box(fit.get("boxes"), "next")
    wrap_row = _box(wrap.get("boxes"), "row")
    wrap_next = _box(wrap.get("boxes"), "next")
    after_row = _box(after.get("boxes"), "row")
    after_next = _box(after.get("boxes"), "next")
    span_row = _box(spanned.get("boxes"), "row")
    span_next = _box(spanned.get("boxes"), "next")
    inherit_row = _box(inherited.get("boxes"), "row")
    inherit_next = _box(inherited.get("boxes"), "next")
    fit_line = _line(fit_row, 0)
    after_line = _line(after_row, 0)
    span_line = _line(span_row, 0)
    inherit_line = _line(inherit_row, 0)

    observed = {
        "fit": {"outcome": fit.get("outcome"), "reason": fit.get("reason"), "line": _runs(fit_line), "next": None if fit_next is None else fit_next.get("y")},
        "wrap": {
            "outcome": wrap.get("outcome"),
            "lines": [
                None if _line(wrap_row, index) is None else _line(wrap_row, index).get("text")
                for index in range(2)
            ],
            "next": None if wrap_next is None else wrap_next.get("y"),
        },
        "after": {"outcome": after.get("outcome"), "width": None if after_line is None else after_line.get("content_width"), "next": None if after_next is None else after_next.get("y")},
        "span": {"outcome": spanned.get("outcome"), "text": None if span_line is None else span_line.get("text"), "next": None if span_next is None else span_next.get("y")},
        "inherit": {"outcome": inherited.get("outcome"), "height": None if inherit_line is None else inherit_line.get("height"), "next": None if inherit_next is None else inherit_next.get("y")},
        "percent": {"outcome": percent.get("outcome"), "reason": percent.get("reason")},
        "margin": {"outcome": margin.get("outcome"), "reason": margin.get("reason")},
        "flex": {"outcome": flexed.get("outcome"), "reason": flexed.get("reason")},
        "absolute": {"outcome": absolute.get("outcome"), "reason": absolute.get("reason")},
    }
    checks = {
        "before_shares_the_line": (
            fit.get("outcome") == "placed"
            and _near(fit_line, text="AB CD", x=0, y=0, content_width=70, height=20)
            and _line(fit_row, 1) is None
            and _runs(fit_line) == [
                {"text": "AB", "x": 0, "font_size": 20, "width": 40},
                {"text": " CD", "x": 40, "font_size": 10, "width": 30},
            ]
            and _near(fit_next, y=20)
        ),
        "before_wraps_before_the_element": (
            wrap.get("outcome") == "placed"
            and _near(_line(wrap_row, 0), text="AB", x=0, y=0, content_width=40, height=20)
            and _near(_line(wrap_row, 1), text="CD", x=0, y=20, content_width=20, height=10)
            and _line(wrap_row, 2) is None
            and _near(wrap_next, y=30)
        ),
        "after_uses_its_own_metrics": (
            after.get("outcome") == "placed"
            and _near(after_line, text="AB CDEF", x=0, y=0, content_width=130, height=30)
            and _runs(after_line) == [
                {"text": "AB", "x": 0, "font_size": 20, "width": 40},
                {"text": " CD", "x": 40, "font_size": 10, "width": 30},
                {"text": "EF", "x": 70, "font_size": 30, "width": 60},
            ]
            and _near(after_next, y=30)
        ),
        "span_before_stays_on_that_span": (
            spanned.get("outcome") == "placed"
            and _near(span_line, text="AXBC", x=0, y=0, content_width=50, height=20)
            and _runs(span_line) == [
                {"text": "A", "x": 0, "font_size": 10, "width": 10},
                {"text": "X", "x": 10, "font_size": 20, "width": 20},
                {"text": "BC", "x": 30, "font_size": 10, "width": 20},
            ]
            and _near(span_next, y=20)
        ),
        "omitted_line_height_keeps_parent_leading": (
            inherited.get("outcome") == "placed"
            and _near(inherit_line, text="AB CD", content_width=70, height=15)
            and _near(inherit_next, y=15)
        ),
        "percentage_font_size_is_invalid": percent.get("outcome") == "invalid" and percent.get("reason") == "font-size is invalid",
        "margin_stays_rejected": margin.get("outcome") == "invalid" and margin.get("reason") == "generated box is unsupported",
        "flex_stays_rejected": flexed.get("outcome") == "invalid" and flexed.get("reason") == "generated font is unsupported",
        "absolute_stays_rejected": absolute.get("outcome") == "invalid" and absolute.get("reason") == "generated font is unsupported",
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
