"""Paint a text-emphasis mark in its own half-em band.

On a marginless page at 10px font and line-height, a 40px block of AB CD
with text-emphasis filled keeps AB and CD, grows each line from 10px to 15px,
and starts the next block at y 30. The filled dot is U+2022, 5px square,
centered in the 10px advance. over moves the baseline to 15. under keeps the
baseline at 10 and sits the mark at y 10. A space gets no mark. none and an
omitted property leave the 10px lines. A child inherits the mark and color.
An empty string, a bare right position, a vertical box, an inline
declaration, and both the shorthand and text-emphasis-style are rejected.

Prints JSON with boolean passed and nonempty observed. Exit 0 either way.
"""

from __future__ import annotations

import json

_DOT = "\u2022"
_CIRCLE = "\u25cb"
_MARK = "\u203b"
_BASE = "html, body, div, span { margin: 0px; font-size: 10px; line-height: 10px; }\n"
_WRAP = '<div id="page"><div id="copy">AB CD</div><div id="next">Z</div></div>'
_ONE = '<div id="page"><div id="copy">AB</div><div id="next">Z</div></div>'
_GAP = '<div id="page"><div id="copy">A B</div><div id="next">Z</div></div>'
_INHERIT = (
    '<div id="page"><div id="host"><div id="copy">AB</div>'
    '<div id="next">Z</div></div></div>'
)
_INLINE = '<div id="page"><div id="copy">A<span id="s">B</span></div><div id="next">Z</div></div>'


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


def _lay(layout, markup: str, stylesheet: str) -> dict[str, object]:
    try:
        placed = layout(markup, stylesheet, viewport_width=400)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def _marks(line: dict[str, object] | None) -> object:
    if line is None:
        return None
    return line.get("emphasis")


def _dot(text: str, x: int, y: int, color: str = "#000000") -> dict[str, object]:
    return {"text": text, "x": x, "y": y, "width": 5, "height": 5, "color": color}


def _invalid(placed: dict[str, object], reason: str) -> bool:
    return placed.get("outcome") == "invalid" and placed.get("reason") == reason


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - a missing layout still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    filled_css = _BASE + "#copy { width: 40px; text-emphasis: filled; }\n"
    none_css = _BASE + "#copy { width: 40px; text-emphasis: none; }\n"
    omitted_css = _BASE + "#copy { width: 40px; }\n"
    under_css = _BASE + "#copy { width: 40px; text-emphasis: filled; text-emphasis-position: under; }\n"
    side_css = _BASE + "#copy { width: 40px; text-emphasis: filled; text-emphasis-position: right over; }\n"
    string_css = _BASE + '#copy { width: 40px; text-emphasis: "\u203b"; }\n'
    circle_css = _BASE + "#copy { width: 40px; text-emphasis-style: open circle; }\n"
    gap_css = _BASE + "#copy { width: 40px; text-emphasis: filled; }\n"
    inherit_css = (
        _BASE
        + "#host { text-emphasis: filled; color: #010203; }\n"
        + "#copy { width: 40px; }\n"
        + "#next { text-emphasis: none; }\n"
    )
    empty_css = _BASE + '#copy { width: 40px; text-emphasis: ""; }\n'
    bare_css = _BASE + "#copy { width: 40px; text-emphasis: filled; text-emphasis-position: right; }\n"
    vertical_css = (
        _BASE + "#copy { width: 40px; height: 80px; writing-mode: vertical-rl; text-emphasis: filled; }\n"
    )
    inline_css = _BASE + "#copy { width: 40px; }\n#s { text-emphasis: filled; }\n"
    both_css = _BASE + "#copy { width: 40px; text-emphasis: filled; text-emphasis-style: open; }\n"

    filled = _lay(layout_normal_flow, _WRAP, filled_css)
    none = _lay(layout_normal_flow, _WRAP, none_css)
    omitted = _lay(layout_normal_flow, _WRAP, omitted_css)
    under = _lay(layout_normal_flow, _ONE, under_css)
    side = _lay(layout_normal_flow, _ONE, side_css)
    string = _lay(layout_normal_flow, _ONE, string_css)
    circle = _lay(layout_normal_flow, _ONE, circle_css)
    gap = _lay(layout_normal_flow, _GAP, gap_css)
    inherited = _lay(layout_normal_flow, _INHERIT, inherit_css)
    empty = _lay(layout_normal_flow, _WRAP, empty_css)
    bare = _lay(layout_normal_flow, _WRAP, bare_css)
    vertical = _lay(layout_normal_flow, _WRAP, vertical_css)
    inline = _lay(layout_normal_flow, _INLINE, inline_css)
    both = _lay(layout_normal_flow, _WRAP, both_css)

    copy = _box(filled.get("boxes"), "copy")
    nxt = _box(filled.get("boxes"), "next")
    first = _line(copy, 0)
    second = _line(copy, 1)
    plain = _box(none.get("boxes"), "copy")
    plain_next = _box(none.get("boxes"), "next")
    omitted_copy = _box(omitted.get("boxes"), "copy")
    omitted_next = _box(omitted.get("boxes"), "next")
    under_copy = _box(under.get("boxes"), "copy")
    under_next = _box(under.get("boxes"), "next")
    under_line = _line(under_copy, 0)
    side_line = _line(_box(side.get("boxes"), "copy"), 0)
    string_line = _line(_box(string.get("boxes"), "copy"), 0)
    circle_line = _line(_box(circle.get("boxes"), "copy"), 0)
    gap_line = _line(_box(gap.get("boxes"), "copy"), 0)
    child = _box(inherited.get("boxes"), "copy")
    child_line = _line(child, 0)
    sibling = _box(inherited.get("boxes"), "next")
    sibling_line = _line(sibling, 0)

    observed = {
        "filled_outcome": filled.get("outcome"),
        "first": None
        if first is None
        else {
            "text": first.get("text"),
            "y": first.get("y"),
            "height": first.get("height"),
            "baseline": first.get("baseline"),
            "content_width": first.get("content_width"),
            "emphasis": first.get("emphasis"),
        },
        "second": None
        if second is None
        else {
            "text": second.get("text"),
            "y": second.get("y"),
            "height": second.get("height"),
            "baseline": second.get("baseline"),
            "emphasis": second.get("emphasis"),
        },
        "next_y": None if nxt is None else nxt.get("y"),
        "copy_height": None if copy is None else copy.get("content_height"),
        "none_height": None if _line(plain, 0) is None else _line(plain, 0).get("height"),
        "none_next": None if plain_next is None else plain_next.get("y"),
        "none_marks": _marks(_line(plain, 0)),
        "omitted_next": None if omitted_next is None else omitted_next.get("y"),
        "omitted_marks": _marks(_line(omitted_copy, 0)),
        "under_baseline": None if under_line is None else under_line.get("baseline"),
        "under_marks": _marks(under_line),
        "under_next": None if under_next is None else under_next.get("y"),
        "side_marks": _marks(side_line),
        "string_marks": _marks(string_line),
        "circle_marks": _marks(circle_line),
        "gap_text": None if gap_line is None else gap_line.get("text"),
        "gap_marks": _marks(gap_line),
        "child_marks": _marks(child_line),
        "child_height": None if child_line is None else child_line.get("height"),
        "sibling_y": None if sibling is None else sibling.get("y"),
        "sibling_marks": _marks(sibling_line),
        "empty": empty.get("reason"),
        "bare": bare.get("reason"),
        "vertical": vertical.get("reason"),
        "inline": inline.get("reason"),
        "both": both.get("reason"),
    }
    passed = (
        filled.get("outcome") == "placed"
        and first is not None
        and second is not None
        and nxt is not None
        and copy is not None
        and first.get("text") == "AB"
        and first.get("y") == 0
        and first.get("height") == 15
        and first.get("baseline") == 15
        and first.get("content_width") == 20
        and first.get("emphasis") == [_dot(_DOT, 2, 0), _dot(_DOT, 12, 0)]
        and second.get("text") == "CD"
        and second.get("y") == 15
        and second.get("height") == 15
        and second.get("baseline") == 15
        and second.get("emphasis") == [_dot(_DOT, 2, 15), _dot(_DOT, 12, 15)]
        and nxt.get("y") == 30
        and copy.get("content_height") == 30
        and none.get("outcome") == "placed"
        and _line(plain, 0) is not None
        and _line(plain, 0).get("text") == "AB"
        and _line(plain, 0).get("height") == 10
        and _line(plain, 1) is not None
        and _line(plain, 1).get("text") == "CD"
        and _line(plain, 1).get("height") == 10
        and "emphasis" not in _line(plain, 0)
        and "emphasis" not in _line(plain, 1)
        and plain_next is not None
        and plain_next.get("y") == 20
        and omitted.get("outcome") == "placed"
        and _line(omitted_copy, 0) is not None
        and _line(omitted_copy, 0).get("height") == 10
        and "emphasis" not in _line(omitted_copy, 0)
        and omitted_next is not None
        and omitted_next.get("y") == 20
        and under.get("outcome") == "placed"
        and under_line is not None
        and under_line.get("height") == 15
        and under_line.get("baseline") == 10
        and under_line.get("emphasis") == [_dot(_DOT, 2, 10), _dot(_DOT, 12, 10)]
        and under_next is not None
        and under_next.get("y") == 15
        and side.get("outcome") == "placed"
        and side_line is not None
        and side_line.get("baseline") == 15
        and side_line.get("emphasis") == [_dot(_DOT, 2, 0), _dot(_DOT, 12, 0)]
        and string.get("outcome") == "placed"
        and string_line is not None
        and string_line.get("emphasis") == [_dot(_MARK, 2, 0), _dot(_MARK, 12, 0)]
        and circle.get("outcome") == "placed"
        and circle_line is not None
        and circle_line.get("emphasis") == [_dot(_CIRCLE, 2, 0), _dot(_CIRCLE, 12, 0)]
        and gap.get("outcome") == "placed"
        and gap_line is not None
        and gap_line.get("text") == "A B"
        and gap_line.get("emphasis") == [_dot(_DOT, 2, 0), _dot(_DOT, 22, 0)]
        and inherited.get("outcome") == "placed"
        and child_line is not None
        and child_line.get("height") == 15
        and child_line.get("emphasis") == [_dot(_DOT, 2, 0, "#010203"), _dot(_DOT, 12, 0, "#010203")]
        and sibling is not None
        and sibling.get("y") == 15
        and sibling_line is not None
        and "emphasis" not in sibling_line
        and _invalid(empty, "text emphasis is invalid")
        and _invalid(bare, "text emphasis is invalid")
        and _invalid(vertical, "text emphasis is unsupported")
        and _invalid(inline, "inline text emphasis is unsupported")
        and _invalid(both, "text emphasis is invalid")
    )
    return bool(passed), observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
