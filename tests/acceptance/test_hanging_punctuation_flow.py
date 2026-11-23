"""Hang punctuation outside the line measure.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A block that still charges the hanging mark against the
measure reports passed false.
"""

from __future__ import annotations

import json

_OPEN = (
    "<div id='page'>(A B</div><div id='next'>Z</div>",
    "#page { width: 30px; font-size: 10px; hanging-punctuation: first; } #next { font-size: 10px; }",
)
_QUOTE = (
    "<div id='page'>\u201cA B</div><div id='next'>Z</div>",
    "#page { width: 30px; font-size: 10px; hanging-punctuation: first; } #next { font-size: 10px; }",
)
_PLAIN = (
    "<div id='page'>(A B</div><div id='next'>Z</div>",
    "#page { width: 30px; font-size: 10px; } #next { font-size: 10px; }",
)
_CLOSE = (
    "<div id='page'>AA BB)</div><div id='next'>Z</div>",
    "#page { width: 50px; font-size: 10px; hanging-punctuation: last; } #next { font-size: 10px; }",
)
_FORCE = (
    "<div id='page'>AAAA.</div><div id='next'>Z</div>",
    "#page { width: 40px; font-size: 10px; hanging-punctuation: force-end; } #next { font-size: 10px; }",
)
_FORCE_FIT = (
    "<div id='page'>AAA.</div><div id='next'>Z</div>",
    "#page { width: 40px; font-size: 10px; hanging-punctuation: force-end; } #next { font-size: 10px; }",
)
_ALLOW_FIT = (
    "<div id='page'>AAA.</div><div id='next'>Z</div>",
    "#page { width: 40px; font-size: 10px; hanging-punctuation: allow-end; } #next { font-size: 10px; }",
)
_ALLOW = (
    "<div id='page'>AAAA.</div><div id='next'>Z</div>",
    "#page { width: 40px; font-size: 10px; hanging-punctuation: allow-end; } #next { font-size: 10px; }",
)
_SECOND = (
    "<div id='page'>AAA (B</div><div id='next'>Z</div>",
    "#page { width: 30px; font-size: 10px; hanging-punctuation: first; } #next { font-size: 10px; }",
)
_INHERIT = (
    "<div id='host'><div id='child'>(A B</div></div><div id='next'>Z</div>",
    "#host { width: 30px; font-size: 10px; hanging-punctuation: first; } #next { font-size: 10px; }",
)
_CLEARED = (
    "<div id='host'><div id='child'>(A B</div></div><div id='next'>Z</div>",
    "#host { width: 30px; font-size: 10px; hanging-punctuation: first; } "
    "#child { hanging-punctuation: none; } #next { font-size: 10px; }",
)
_BAD = (
    "<div id='page'>(A</div>",
    "#page { width: 40px; font-size: 10px; hanging-punctuation: center; }",
)
_BOTH = (
    "<div id='page'>(A</div>",
    "#page { width: 40px; font-size: 10px; hanging-punctuation: force-end allow-end; }",
)
_INLINE = (
    "<div id='page'>A<span>B</span></div>",
    "#page { width: 80px; font-size: 10px; } span { hanging-punctuation: first; }",
)
_VERTICAL = (
    "<div id='page'>AB</div>",
    "#page { width: 40px; font-size: 10px; writing-mode: vertical-rl; hanging-punctuation: first; }",
)


def _place(function, markup: str, stylesheet: str) -> dict[str, object]:
    try:
        result = function(markup, stylesheet, viewport_width=400)
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
    return {"text": line.get("text"), "x": line.get("x"), "y": line.get("y"), "width": line.get("content_width")}


def _matches(lines: list[dict[str, object]], expected: list[tuple[str, int, int]]) -> bool:
    if len(lines) != len(expected):
        return False
    for line, (text, y, width) in zip(lines, expected):
        if line.get("text") != text or line.get("x") != 0 or line.get("y") != y or line.get("content_width") != width:
            return False
    return True


def _next_y(result: dict[str, object]) -> object:
    box = _box(result, "next")
    if box is None:
        return None
    return box.get("y")


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without the layout still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    opened = _place(layout_normal_flow, *_OPEN)
    quote = _place(layout_normal_flow, *_QUOTE)
    plain = _place(layout_normal_flow, *_PLAIN)
    closed = _place(layout_normal_flow, *_CLOSE)
    forced = _place(layout_normal_flow, *_FORCE)
    force_fit = _place(layout_normal_flow, *_FORCE_FIT)
    allow_fit = _place(layout_normal_flow, *_ALLOW_FIT)
    allowed = _place(layout_normal_flow, *_ALLOW)
    second = _place(layout_normal_flow, *_SECOND)
    inherited = _place(layout_normal_flow, *_INHERIT)
    cleared = _place(layout_normal_flow, *_CLEARED)
    bad = _place(layout_normal_flow, *_BAD)
    both = _place(layout_normal_flow, *_BOTH)
    inline = _place(layout_normal_flow, *_INLINE)
    vertical = _place(layout_normal_flow, *_VERTICAL)
    open_lines = _lines(_box(opened, "page"))
    quote_lines = _lines(_box(quote, "page"))
    plain_lines = _lines(_box(plain, "page"))
    close_lines = _lines(_box(closed, "page"))
    force_lines = _lines(_box(forced, "page"))
    force_fit_lines = _lines(_box(force_fit, "page"))
    allow_fit_lines = _lines(_box(allow_fit, "page"))
    allow_lines = _lines(_box(allowed, "page"))
    second_lines = _lines(_box(second, "page"))
    child_lines = _lines(_box(inherited, "child"))
    cleared_lines = _lines(_box(cleared, "child"))
    observed: dict[str, object] = {
        "first": [_pack(line) for line in open_lines],
        "first_next_y": _next_y(opened),
        "quote": [_pack(line) for line in quote_lines],
        "quote_next_y": _next_y(quote),
        "plain": [_pack(line) for line in plain_lines],
        "plain_next_y": _next_y(plain),
        "last": [_pack(line) for line in close_lines],
        "last_next_y": _next_y(closed),
        "force": [_pack(line) for line in force_lines],
        "force_fit": [_pack(line) for line in force_fit_lines],
        "allow_fit": [_pack(line) for line in allow_fit_lines],
        "allow": [_pack(line) for line in allow_lines],
        "second": [_pack(line) for line in second_lines],
        "second_next_y": _next_y(second),
        "inherit": [_pack(line) for line in child_lines],
        "inherit_next_y": _next_y(inherited),
        "cleared": [_pack(line) for line in cleared_lines],
        "cleared_next_y": _next_y(cleared),
        "center": bad.get("outcome"),
        "center_reason": bad.get("reason"),
        "both": both.get("outcome"),
        "both_reason": both.get("reason"),
        "inline": inline.get("outcome"),
        "inline_reason": inline.get("reason"),
        "vertical": vertical.get("outcome"),
        "vertical_reason": vertical.get("reason"),
    }
    passed = (
        opened.get("outcome") == "placed"
        and _matches(open_lines, [("(A B", 0, 30)])
        and observed["first_next_y"] == 10
        and quote.get("outcome") == "placed"
        and _matches(quote_lines, [("\u201cA B", 0, 30)])
        and observed["quote_next_y"] == 10
        and plain.get("outcome") == "placed"
        and _matches(plain_lines, [("(A", 0, 20), ("B", 10, 10)])
        and observed["plain_next_y"] == 20
        and closed.get("outcome") == "placed"
        and _matches(close_lines, [("AA BB)", 0, 50)])
        and observed["last_next_y"] == 10
        and forced.get("outcome") == "placed"
        and _matches(force_lines, [("AAAA.", 0, 40)])
        and force_fit.get("outcome") == "placed"
        and _matches(force_fit_lines, [("AAA.", 0, 30)])
        and allow_fit.get("outcome") == "placed"
        and _matches(allow_fit_lines, [("AAA.", 0, 40)])
        and allowed.get("outcome") == "placed"
        and _matches(allow_lines, [("AAAA.", 0, 40)])
        and second.get("outcome") == "placed"
        and _matches(second_lines, [("AAA", 0, 30), ("(B", 10, 20)])
        and observed["second_next_y"] == 20
        and inherited.get("outcome") == "placed"
        and _matches(child_lines, [("(A B", 0, 30)])
        and observed["inherit_next_y"] == 10
        and cleared.get("outcome") == "placed"
        and _matches(cleared_lines, [("(A", 0, 20), ("B", 10, 10)])
        and observed["cleared_next_y"] == 20
        and bad.get("outcome") == "invalid"
        and bad.get("reason") == "hanging-punctuation is invalid"
        and both.get("outcome") == "invalid"
        and both.get("reason") == "hanging-punctuation is invalid"
        and inline.get("outcome") == "invalid"
        and inline.get("reason") == "inline hanging-punctuation is unsupported"
        and vertical.get("outcome") == "invalid"
        and vertical.get("reason") == "hanging punctuation writing mode is unsupported"
    )
    return bool(passed), observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
