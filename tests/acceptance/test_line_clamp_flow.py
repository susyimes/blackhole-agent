"""Clamp a horizontal block and end the discarded tail with an ellipsis.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A block that still paints every wrapped line reports passed
false.
"""

from __future__ import annotations

import json

_ELLIPSIS = "\u2026"
_ONE = (
    "<div id='page'>AAAA BBBB CCCC DDDD</div><div id='next'>Z</div>",
    "#page { width: 90px; font-size: 10px; line-clamp: 1; } #next { font-size: 10px; }",
    400,
)
_TWO = (
    "<div id='page'>AAAA BBBB CCCC DDDD EEEE</div><div id='next'>Z</div>",
    "#page { width: 90px; font-size: 10px; line-clamp: 2; } #next { font-size: 10px; }",
    400,
)
_NONE = (
    "<div id='page'>AAAA BBBB CCCC DDDD</div><div id='next'>Z</div>",
    "#page { width: 90px; font-size: 10px; line-clamp: none; } #next { font-size: 10px; }",
    400,
)
_FITS = (
    "<div id='page'>AAAA BBBB</div><div id='next'>Z</div>",
    "#page { width: 90px; font-size: 10px; line-clamp: 1; } #next { font-size: 10px; }",
    400,
)
_NOWRAP = (
    "<div id='page'>ABCDEFGHIJ</div><div id='next'>Z</div>",
    "#page { width: 50px; font-size: 10px; white-space: nowrap; line-clamp: 1; } #next { font-size: 10px; }",
    400,
)
_CHILD = (
    "<div id='page'><div id='child'>AAAA BBBB CCCC DDDD</div></div>",
    "#page { width: 200px; font-size: 10px; line-clamp: 1; } #child { width: 90px; }",
    400,
)
_ZERO = (
    "<div id='page'>AAAA BBBB</div>",
    "#page { width: 90px; font-size: 10px; line-clamp: 0; }",
    400,
)
_INLINE = (
    "<div id='page'>AA<span>BB</span></div>",
    "#page { width: 80px; font-size: 10px; } span { line-clamp: 1; }",
    80,
)
_FLOAT = (
    "<div id='host'><div id='float'>ZZ</div>AAAA BBBB CCCC DDDD</div>",
    "#host { width: 140px; font-size: 10px; line-clamp: 1; } #float { float: left; }",
    400,
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

    one = _place(layout_normal_flow, *_ONE)
    two = _place(layout_normal_flow, *_TWO)
    none = _place(layout_normal_flow, *_NONE)
    fits = _place(layout_normal_flow, *_FITS)
    nowrap = _place(layout_normal_flow, *_NOWRAP)
    child = _place(layout_normal_flow, *_CHILD)
    zero = _place(layout_normal_flow, *_ZERO)
    inline = _place(layout_normal_flow, *_INLINE)
    floated = _place(layout_normal_flow, *_FLOAT)
    one_lines = _lines(_box(one, "page"))
    two_lines = _lines(_box(two, "page"))
    none_lines = _lines(_box(none, "page"))
    fits_lines = _lines(_box(fits, "page"))
    nowrap_lines = _lines(_box(nowrap, "page"))
    child_lines = _lines(_box(child, "child"))
    one_next = _box(one, "next")
    two_next = _box(two, "next")
    none_next = _box(none, "next")
    fits_next = _box(fits, "next")
    nowrap_next = _box(nowrap, "next")
    observed: dict[str, object] = {
        "one": [_pack(line) for line in one_lines],
        "one_next_y": None if one_next is None else one_next.get("y"),
        "two": [_pack(line) for line in two_lines],
        "two_next_y": None if two_next is None else two_next.get("y"),
        "none": [_pack(line) for line in none_lines],
        "none_next_y": None if none_next is None else none_next.get("y"),
        "fits": [_pack(line) for line in fits_lines],
        "fits_next_y": None if fits_next is None else fits_next.get("y"),
        "nowrap": [_pack(line) for line in nowrap_lines],
        "nowrap_next_y": None if nowrap_next is None else nowrap_next.get("y"),
        "child": [_pack(line) for line in child_lines],
        "zero": zero.get("outcome"),
        "zero_reason": zero.get("reason"),
        "inline": inline.get("outcome"),
        "inline_reason": inline.get("reason"),
        "float": floated.get("outcome"),
        "float_reason": floated.get("reason"),
    }
    passed = (
        one.get("outcome") == "placed"
        and _matches(one_lines, [(f"AAAA BBB{_ELLIPSIS}", 0, 90)])
        and observed["one_next_y"] == 10
        and two.get("outcome") == "placed"
        and _matches(two_lines, [("AAAA BBBB", 0, 90), (f"CCCC DDD{_ELLIPSIS}", 10, 90)])
        and observed["two_next_y"] == 20
        and none.get("outcome") == "placed"
        and _matches(none_lines, [("AAAA BBBB", 0, 90), ("CCCC DDDD", 10, 90)])
        and observed["none_next_y"] == 20
        and fits.get("outcome") == "placed"
        and _matches(fits_lines, [("AAAA BBBB", 0, 90)])
        and observed["fits_next_y"] == 10
        and nowrap.get("outcome") == "placed"
        and _matches(nowrap_lines, [("ABCDEFGHIJ", 0, 100)])
        and observed["nowrap_next_y"] == 10
        and child.get("outcome") == "placed"
        and _matches(child_lines, [("AAAA BBBB", 0, 90), ("CCCC DDDD", 10, 90)])
        and zero.get("outcome") == "invalid"
        and zero.get("reason") == "line-clamp is invalid"
        and inline.get("outcome") == "invalid"
        and inline.get("reason") == "inline line-clamp is unsupported"
        and floated.get("outcome") == "invalid"
        and floated.get("reason") == "clamped block content is unsupported"
    )
    return bool(passed), observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
