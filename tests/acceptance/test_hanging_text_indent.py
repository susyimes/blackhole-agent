"""Invert text-indent when the hanging keyword is set.

The first line of a horizontal block stays at the content edge. Every later
line starts at the indent. A block that still rejects hanging, or that still
indents only the first line, reports passed false.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit.
"""

from __future__ import annotations

import json

_WORDS = "AAAA BBBB CCCC"
_PAIR = "AAAA BBBB"
_BASE = (
    '<div id="page"><div id="story">{text}</div><div id="next">Z</div></div>'
)
_HANG = (
    _BASE.format(text=_WORDS),
    "#page { width: 80px; font-size: 10px; line-height: 10px; } "
    "#story { text-indent: 20px hanging; } #next { font-size: 10px; line-height: 10px; }",
    200,
)
_FIRST = (
    _BASE.format(text=_WORDS),
    "#page { width: 80px; font-size: 10px; line-height: 10px; } "
    "#story { text-indent: 20px; } #next { font-size: 10px; line-height: 10px; }",
    200,
)
_WIDE_HANG = (
    _BASE.format(text=_PAIR),
    "#page { width: 100px; font-size: 10px; line-height: 10px; } "
    "#story { text-indent: hanging 20px; } #next { font-size: 10px; line-height: 10px; }",
    200,
)
_WIDE_FIRST = (
    _BASE.format(text=_PAIR),
    "#page { width: 100px; font-size: 10px; line-height: 10px; } "
    "#story { text-indent: 20px; } #next { font-size: 10px; line-height: 10px; }",
    200,
)
_INHERIT = (
    '<div id="page"><div id="child">AAAA BBBB CCCC</div>'
    '<div id="plain">AAAA BBBB CCCC</div></div>',
    "#page { width: 200px; font-size: 10px; line-height: 10px; text-indent: 20px hanging; } "
    "#child { width: 80px; } #plain { width: 80px; text-indent: 0px; }",
    400,
)
_PERCENT = (
    _BASE.format(text=_WORDS),
    "#page { width: 80px; font-size: 10px; line-height: 10px; } "
    "#story { text-indent: hanging 25%; } #next { font-size: 10px; line-height: 10px; }",
    200,
)
_NEGATIVE = (
    _BASE.format(text=_WORDS),
    "#page { width: 50px; font-size: 10px; line-height: 10px; } "
    "#story { text-indent: -20px hanging; } #next { font-size: 10px; line-height: 10px; }",
    200,
)
_EACH = (
    '<div id="page">AAAA BBBB</div>',
    "#page { width: 80px; font-size: 10px; text-indent: 20px each-line; }",
    200,
)
_VERTICAL = (
    '<div id="page">AAAA BBBB</div>',
    "#page { width: 80px; font-size: 10px; writing-mode: vertical-rl; text-indent: 20px hanging; }",
    200,
)


def _place(function, markup: str, stylesheet: str, viewport_width: int) -> dict[str, object]:
    try:
        result = function(markup, stylesheet, viewport_width=viewport_width)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    if not isinstance(result, dict):
        return {"outcome": "error", "reason": "result", "boxes": None}
    return result


def _box(result: dict[str, object], box_id: str) -> dict[str, object] | None:
    boxes = result.get("boxes")
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if isinstance(item, dict) and item.get("id") == box_id:
            return item
    return None


def _lines(box: dict[str, object] | None) -> list[dict[str, object]]:
    if box is None or not isinstance(box.get("lines"), list):
        return []
    return [item for item in box["lines"] if isinstance(item, dict)]


def _pack(line: dict[str, object] | None) -> dict[str, object] | None:
    if line is None:
        return None
    return {
        "text": line.get("text"),
        "x": line.get("x"),
        "y": line.get("y"),
        "width": line.get("content_width"),
    }


def _packed(result: dict[str, object], box_id: str) -> list[dict[str, object] | None]:
    return [_pack(line) for line in _lines(_box(result, box_id))]


def _at(lines: list[dict[str, object] | None], index: int, text: str, x: int, y: int, width: int) -> bool:
    if index >= len(lines):
        return False
    line = lines[index]
    return (
        isinstance(line, dict)
        and line.get("text") == text
        and line.get("x") == x
        and line.get("y") == y
        and line.get("width") == width
    )


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without the layout still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    hanging = _place(layout_normal_flow, *_HANG)
    first = _place(layout_normal_flow, *_FIRST)
    wide_hang = _place(layout_normal_flow, *_WIDE_HANG)
    wide_first = _place(layout_normal_flow, *_WIDE_FIRST)
    inherited = _place(layout_normal_flow, *_INHERIT)
    percent = _place(layout_normal_flow, *_PERCENT)
    negative = _place(layout_normal_flow, *_NEGATIVE)
    each_line = _place(layout_normal_flow, *_EACH)
    vertical = _place(layout_normal_flow, *_VERTICAL)

    hang_lines = _packed(hanging, "story")
    first_lines = _packed(first, "story")
    wide_hang_lines = _packed(wide_hang, "story")
    wide_first_lines = _packed(wide_first, "story")
    child_lines = _packed(inherited, "child")
    plain_lines = _packed(inherited, "plain")
    percent_lines = _packed(percent, "story")
    negative_lines = _packed(negative, "story")
    hang_next = _box(hanging, "next")
    wide_hang_next = _box(wide_hang, "next")
    wide_first_next = _box(wide_first, "next")
    percent_next = _box(percent, "next")
    negative_next = _box(negative, "next")

    observed: dict[str, object] = {
        "hanging": hang_lines,
        "hanging_next_y": None if hang_next is None else hang_next.get("y"),
        "first": first_lines,
        "wide_hanging": wide_hang_lines,
        "wide_hanging_next_y": None if wide_hang_next is None else wide_hang_next.get("y"),
        "wide_first": wide_first_lines,
        "wide_first_next_y": None if wide_first_next is None else wide_first_next.get("y"),
        "child": child_lines,
        "plain": plain_lines,
        "percent": percent_lines,
        "percent_next_y": None if percent_next is None else percent_next.get("y"),
        "negative": negative_lines,
        "negative_next_y": None if negative_next is None else negative_next.get("y"),
        "each_line": each_line.get("reason"),
        "vertical": vertical.get("reason"),
    }
    passed = (
        hanging.get("outcome") == "placed"
        and _at(hang_lines, 0, "AAAA", 0, 0, 40)
        and _at(hang_lines, 1, "BBBB", 20, 10, 40)
        and _at(hang_lines, 2, "CCCC", 20, 20, 40)
        and hang_next is not None
        and hang_next.get("y") == 30
        and first.get("outcome") == "placed"
        and _at(first_lines, 0, "AAAA", 20, 0, 40)
        and _at(first_lines, 1, "BBBB", 0, 10, 40)
        and _at(first_lines, 2, "CCCC", 0, 20, 40)
        and wide_hang.get("outcome") == "placed"
        and _at(wide_hang_lines, 0, "AAAA BBBB", 0, 0, 90)
        and len(wide_hang_lines) == 1
        and wide_hang_next is not None
        and wide_hang_next.get("y") == 10
        and wide_first.get("outcome") == "placed"
        and _at(wide_first_lines, 0, "AAAA", 20, 0, 40)
        and _at(wide_first_lines, 1, "BBBB", 0, 10, 40)
        and wide_first_next is not None
        and wide_first_next.get("y") == 20
        and inherited.get("outcome") == "placed"
        and _at(child_lines, 0, "AAAA", 0, 0, 40)
        and _at(child_lines, 1, "BBBB", 20, 10, 40)
        and _at(child_lines, 2, "CCCC", 20, 20, 40)
        and _at(plain_lines, 0, "AAAA", 0, 30, 40)
        and _at(plain_lines, 1, "BBBB", 0, 40, 40)
        and _at(plain_lines, 2, "CCCC", 0, 50, 40)
        and percent.get("outcome") == "placed"
        and percent_lines == hang_lines
        and percent_next is not None
        and percent_next.get("y") == 30
        and negative.get("outcome") == "placed"
        and _at(negative_lines, 0, "AAAA", 0, 0, 40)
        and _at(negative_lines, 1, "BBBB", -20, 10, 40)
        and _at(negative_lines, 2, "CCCC", -20, 20, 40)
        and negative_next is not None
        and negative_next.get("y") == 30
        and each_line.get("outcome") == "invalid"
        and each_line.get("reason") == "text-indent is unsupported"
        and vertical.get("outcome") == "invalid"
        and vertical.get("reason") == "text-indent writing mode is unsupported"
    )
    return bool(passed), observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
