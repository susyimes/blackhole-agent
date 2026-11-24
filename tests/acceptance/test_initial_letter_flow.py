"""Drop the first letter of a horizontal block into a square beside the line.

In a 200px viewport, an 80px paragraph at 10px font and line-height lays
ABCD EFGH IJKL as three lines at x 0, and the following block starts at y 30.
initial-letter: 2 pulls A into a 20 by 20 square at x 0 y 0, puts BCD at
x 20 y 0 and EFGH at x 20 y 10, then returns IJKL to x 0 y 20. A one-line
remainder still grows the block to that square. A two-value initial-letter,
a value of 1, a leading parenthesis, an inline first-letter, a vertical
writing mode, and a word wider than the gap stay rejected.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A layout that still rejects ::first-letter exits 0 with
passed false.
"""

from __future__ import annotations

import json

_PAGE = '<div id="page"><p id="copy">ABCD EFGH IJKL</p><p id="next">Z</p></div>'
_SHORT = '<div id="page"><p id="copy">AB CD</p><p id="next">Z</p></div>'
_MARK = '<div id="page"><p id="copy">(ABCD EFGH IJKL)</p><p id="next">Z</p></div>'
_WIDE_WORD = '<div id="page"><p id="copy">ABCD WXYZ</p><p id="next">Z</p></div>'
_INLINE = '<div id="page"><p id="copy">AB <span id="s">CD</span></p><p id="next">Z</p></div>'
_BASE = "html, body, div, p, span { margin: 0px; font-size: 10px; line-height: 10px; }\n"
_PLAIN = _BASE + "#copy { width: 80px; }\n"
_DROP = _PLAIN + "#copy::first-letter { initial-letter: 2; }\n"
_SHORT_CSS = _DROP
_NORMAL = _PLAIN + "#copy::first-letter { initial-letter: normal; }\n"
_TWO = _PLAIN + "#copy::first-letter { initial-letter: 2 1; }\n"
_ONE = _PLAIN + "#copy::first-letter { initial-letter: 1; }\n"
_VERTICAL = _BASE + "#copy { width: 80px; height: 80px; writing-mode: vertical-rl; }\n"
_VERTICAL += "#copy::first-letter { initial-letter: 2; }\n"
_INLINE_CSS = _BASE + "#copy { width: 80px; }\n#s::first-letter { initial-letter: 2; }\n"
_NARROW = _BASE + "#copy { width: 40px; }\n#copy::first-letter { initial-letter: 2; }\n"


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


def _invalid(placed: dict[str, object]) -> bool:
    return placed.get("outcome") == "invalid" and placed.get("reason") == "initial letter is unsupported"


def _compact(line: dict[str, object] | None) -> dict[str, object] | None:
    if line is None:
        return None
    return {
        "text": line.get("text"),
        "x": line.get("x"),
        "y": line.get("y"),
        "height": line.get("height"),
        "content_width": line.get("content_width"),
    }


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without the layout still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    plain = _lay(layout_normal_flow, _PAGE, _PLAIN)
    dropped = _lay(layout_normal_flow, _PAGE, _DROP)
    short = _lay(layout_normal_flow, _SHORT, _SHORT_CSS)
    normal = _lay(layout_normal_flow, _PAGE, _NORMAL)
    two = _lay(layout_normal_flow, _PAGE, _TWO)
    one = _lay(layout_normal_flow, _PAGE, _ONE)
    marked = _lay(layout_normal_flow, _MARK, _DROP)
    inline = _lay(layout_normal_flow, _INLINE, _INLINE_CSS)
    vertical = _lay(layout_normal_flow, _PAGE, _VERTICAL)
    narrow = _lay(layout_normal_flow, _WIDE_WORD, _NARROW)

    plain_box = _box(plain.get("boxes"), "copy")
    plain_next = _box(plain.get("boxes"), "next")
    drop_box = _box(dropped.get("boxes"), "copy")
    drop_next = _box(dropped.get("boxes"), "next")
    short_box = _box(short.get("boxes"), "copy")
    short_next = _box(short.get("boxes"), "next")
    normal_box = _box(normal.get("boxes"), "copy")
    cap = drop_box.get("initial_letter") if isinstance(drop_box, dict) else None
    short_cap = short_box.get("initial_letter") if isinstance(short_box, dict) else None

    checks = {
        "plain_lines_stay_at_the_content_start": (
            plain.get("outcome") == "placed"
            and _near(_line(plain_box, 0), text="ABCD", x=0, y=0, content_width=40, height=10)
            and _near(_line(plain_box, 1), text="EFGH", x=0, y=10, content_width=40, height=10)
            and _near(_line(plain_box, 2), text="IJKL", x=0, y=20, content_width=40, height=10)
            and _line(plain_box, 3) is None
            and _near(plain_next, y=30)
            and (plain_box or {}).get("initial_letter") is None
        ),
        "drop_cap_square_and_the_line_below_it": (
            dropped.get("outcome") == "placed"
            and _near(cap if isinstance(cap, dict) else None, text="A", x=0, y=0, width=20, height=20)
            and _near(_line(drop_box, 0), text="BCD", x=20, y=0, content_width=30, height=10)
            and _near(_line(drop_box, 1), text="EFGH", x=20, y=10, content_width=40, height=10)
            and _near(_line(drop_box, 2), text="IJKL", x=0, y=20, content_width=40, height=10)
            and _line(drop_box, 3) is None
            and _near(drop_box, content_width=80, content_height=30)
            and _near(drop_next, y=30)
        ),
        "short_remainder_grows_to_the_square": (
            short.get("outcome") == "placed"
            and _near(
                short_cap if isinstance(short_cap, dict) else None,
                text="A",
                x=0,
                y=0,
                width=20,
                height=20,
            )
            and _near(_line(short_box, 0), text="B CD", x=20, y=0, content_width=40, height=10)
            and _line(short_box, 1) is None
            and _near(short_box, content_height=20)
            and _near(short_next, y=20)
        ),
        "normal_keeps_the_letter_in_the_line": (
            normal.get("outcome") == "placed"
            and _near(_line(normal_box, 0), text="ABCD", x=0, y=0)
            and (normal_box or {}).get("initial_letter") is None
        ),
        "two_values_stay_rejected": _invalid(two),
        "one_line_value_stays_rejected": _invalid(one),
        "leading_punctuation_stays_rejected": _invalid(marked),
        "inline_first_letter_stays_rejected": _invalid(inline),
        "vertical_writing_mode_stays_rejected": _invalid(vertical),
        "word_wider_than_the_gap_stays_rejected": _invalid(narrow),
    }
    observed = {
        "checks": checks,
        "plain_lines": None if plain_box is None else [_compact(_line(plain_box, index)) for index in range(4)],
        "drop_outcome": dropped.get("outcome"),
        "drop_reason": dropped.get("reason"),
        "drop_cap": cap,
        "drop_lines": None if drop_box is None else [_compact(_line(drop_box, index)) for index in range(4)],
        "drop_height": None if drop_box is None else drop_box.get("content_height"),
        "drop_next_y": None if drop_next is None else drop_next.get("y"),
        "short_outcome": short.get("outcome"),
        "short_reason": short.get("reason"),
        "short_cap": short_cap,
        "short_lines": None if short_box is None else [_compact(_line(short_box, index)) for index in range(3)],
        "short_height": None if short_box is None else short_box.get("content_height"),
        "short_next_y": None if short_next is None else short_next.get("y"),
        "rejected": {
            "two": two.get("reason"),
            "one": one.get("reason"),
            "mark": marked.get("reason"),
            "inline": inline.get("reason"),
            "vertical": vertical.get("reason"),
            "narrow": narrow.get("reason"),
        },
    }
    return all(checks.values()), observed


def main() -> None:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - the probe must exit 0 either way
        passed, observed = False, {"error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps({"passed": bool(passed), "observed": observed}, sort_keys=True))


if __name__ == "__main__":
    main()
