"""Advance a preserved tab to the next tab-size stop.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A block that still paints the eight-space stop reports
passed false.
"""

from __future__ import annotations

import json

_TAB = "\t"
_FOUR = (
    f"<div id='page'>A{_TAB}B</div><div id='next'>Z</div>",
    "#page { width: 200px; font-size: 10px; white-space: pre; tab-size: 4; } #next { font-size: 10px; }",
    400,
)
_INITIAL = (
    f"<div id='page'>A{_TAB}B</div><div id='next'>Z</div>",
    "#page { width: 200px; font-size: 10px; white-space: pre; } #next { font-size: 10px; }",
    400,
)
_LENGTH = (
    f"<div id='page'>A{_TAB}B</div><div id='next'>Z</div>",
    "#page { width: 200px; font-size: 10px; white-space: pre; tab-size: 40px; } #next { font-size: 10px; }",
    400,
)
_STOPS = (
    f"<div id='page'>A{_TAB}B{_TAB}C</div><div id='next'>Z</div>",
    "#page { width: 400px; font-size: 10px; white-space: pre; tab-size: 4; } #next { font-size: 10px; }",
    400,
)
_EXACT = (
    f"<div id='page'>AB{_TAB}C</div><div id='next'>Z</div>",
    "#page { width: 200px; font-size: 10px; white-space: pre; tab-size: 2; } #next { font-size: 10px; }",
    400,
)
_ZERO = (
    f"<div id='page'>A{_TAB}B</div><div id='next'>Z</div>",
    "#page { width: 200px; font-size: 10px; white-space: pre; tab-size: 0; } #next { font-size: 10px; }",
    400,
)
_NORMAL = (
    f"<div id='page'>A{_TAB}B</div><div id='next'>Z</div>",
    "#page { width: 200px; font-size: 10px; white-space: normal; tab-size: 4; } #next { font-size: 10px; }",
    400,
)
_INHERIT_NUMBER = (
    f"<div id='host'><div id='child'>A{_TAB}B</div></div><div id='next'>Z</div>",
    "#host { width: 300px; font-size: 10px; white-space: pre; tab-size: 4; } #child { font-size: 20px; } #next { font-size: 10px; }",
    400,
)
_INHERIT_LENGTH = (
    f"<div id='host'><div id='child'>A{_TAB}B</div></div><div id='next'>Z</div>",
    "#host { width: 300px; font-size: 10px; white-space: pre; tab-size: 40px; } #child { font-size: 20px; } #next { font-size: 10px; }",
    400,
)
_WRAP = (
    f"<div id='page'>A{_TAB}B</div><div id='next'>Z</div>",
    "#page { width: 50px; font-size: 10px; white-space: pre-wrap; tab-size: 4; } #next { font-size: 10px; }",
    400,
)
_NEGATIVE = (
    f"<div id='page'>A{_TAB}B</div>",
    "#page { width: 200px; font-size: 10px; white-space: pre; tab-size: -1; }",
    400,
)
_PERCENT = (
    f"<div id='page'>A{_TAB}B</div>",
    "#page { width: 200px; font-size: 10px; white-space: pre; tab-size: 4%; }",
    400,
)
_INLINE = (
    "<div id='page'>A<span>B</span></div>",
    "#page { width: 80px; font-size: 10px; white-space: pre; } span { tab-size: 2; }",
    80,
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


def _matches(lines: list[dict[str, object]], expected: list[tuple[str, int, int]]) -> bool:
    if len(lines) != len(expected):
        return False
    for line, (text, y, width) in zip(lines, expected):
        if line.get("text") != text or line.get("x") != 0 or line.get("y") != y or line.get("content_width") != width:
            return False
    return True


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without the layout still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    four = _place(layout_normal_flow, *_FOUR)
    initial = _place(layout_normal_flow, *_INITIAL)
    length = _place(layout_normal_flow, *_LENGTH)
    stops = _place(layout_normal_flow, *_STOPS)
    exact = _place(layout_normal_flow, *_EXACT)
    zero = _place(layout_normal_flow, *_ZERO)
    normal = _place(layout_normal_flow, *_NORMAL)
    inherit_number = _place(layout_normal_flow, *_INHERIT_NUMBER)
    inherit_length = _place(layout_normal_flow, *_INHERIT_LENGTH)
    wrapped = _place(layout_normal_flow, *_WRAP)
    negative = _place(layout_normal_flow, *_NEGATIVE)
    percent = _place(layout_normal_flow, *_PERCENT)
    inline = _place(layout_normal_flow, *_INLINE)
    four_lines = _lines(_box(four, "page"))
    initial_lines = _lines(_box(initial, "page"))
    length_lines = _lines(_box(length, "page"))
    stop_lines = _lines(_box(stops, "page"))
    exact_lines = _lines(_box(exact, "page"))
    zero_lines = _lines(_box(zero, "page"))
    normal_lines = _lines(_box(normal, "page"))
    child_lines = _lines(_box(inherit_number, "child"))
    length_child_lines = _lines(_box(inherit_length, "child"))
    wrap_lines = _lines(_box(wrapped, "page"))
    observed: dict[str, object] = {
        "four": [_pack(line) for line in four_lines],
        "four_next_y": None if _box(four, "next") is None else _box(four, "next").get("y"),
        "initial": [_pack(line) for line in initial_lines],
        "initial_next_y": None if _box(initial, "next") is None else _box(initial, "next").get("y"),
        "length": [_pack(line) for line in length_lines],
        "stops": [_pack(line) for line in stop_lines],
        "exact": [_pack(line) for line in exact_lines],
        "zero": [_pack(line) for line in zero_lines],
        "normal": [_pack(line) for line in normal_lines],
        "inherit_number": [_pack(line) for line in child_lines],
        "inherit_number_next_y": None
        if _box(inherit_number, "next") is None
        else _box(inherit_number, "next").get("y"),
        "inherit_length": [_pack(line) for line in length_child_lines],
        "inherit_length_next_y": None
        if _box(inherit_length, "next") is None
        else _box(inherit_length, "next").get("y"),
        "wrap": [_pack(line) for line in wrap_lines],
        "wrap_next_y": None if _box(wrapped, "next") is None else _box(wrapped, "next").get("y"),
        "negative": negative.get("outcome"),
        "negative_reason": negative.get("reason"),
        "percent": percent.get("outcome"),
        "percent_reason": percent.get("reason"),
        "inline": inline.get("outcome"),
        "inline_reason": inline.get("reason"),
    }
    passed = (
        four.get("outcome") == "placed"
        and _matches(four_lines, [(f"A{_TAB}B", 0, 50)])
        and observed["four_next_y"] == 10
        and initial.get("outcome") == "placed"
        and _matches(initial_lines, [(f"A{_TAB}B", 0, 90)])
        and observed["initial_next_y"] == 10
        and length.get("outcome") == "placed"
        and _matches(length_lines, [(f"A{_TAB}B", 0, 50)])
        and stops.get("outcome") == "placed"
        and _matches(stop_lines, [(f"A{_TAB}B{_TAB}C", 0, 90)])
        and exact.get("outcome") == "placed"
        and _matches(exact_lines, [(f"AB{_TAB}C", 0, 50)])
        and zero.get("outcome") == "placed"
        and _matches(zero_lines, [(f"A{_TAB}B", 0, 20)])
        and normal.get("outcome") == "placed"
        and _matches(normal_lines, [("A B", 0, 30)])
        and inherit_number.get("outcome") == "placed"
        and _matches(child_lines, [(f"A{_TAB}B", 0, 100)])
        and observed["inherit_number_next_y"] == 20
        and inherit_length.get("outcome") == "placed"
        and _matches(length_child_lines, [(f"A{_TAB}B", 0, 60)])
        and observed["inherit_length_next_y"] == 20
        and wrapped.get("outcome") == "placed"
        and _matches(wrap_lines, [(f"A{_TAB}B", 0, 50)])
        and observed["wrap_next_y"] == 10
        and negative.get("outcome") == "invalid"
        and negative.get("reason") == "tab-size is invalid"
        and percent.get("outcome") == "invalid"
        and percent.get("reason") == "tab-size is invalid"
        and inline.get("outcome") == "invalid"
        and inline.get("reason") == "inline tab-size is unsupported"
    )
    return bool(passed), observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
