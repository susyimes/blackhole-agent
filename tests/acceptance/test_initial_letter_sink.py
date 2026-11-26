"""Sink an initial letter by a line count that can be shorter than its size.

On a 200px page, an 80px paragraph at 10px font and line-height lays
ABCD EFGH IJKL as three 40px lines. initial-letter: 2 still drops A into a
20px square with the first line at y 0. initial-letter: 3 2 keeps a 30px
square at the content origin and starts the first line at y 10, so only two
lines sit beside it. initial-letter: 3 raise and raise 3 start that line at
y 20 and exclude only the first line. initial-letter: 3 drop matches a size
of 3. A sink deeper than the size, a size of 1, and a non-integer stay
rejected.

Prints JSON with boolean passed and nonempty observed. Exit 0 either way.
"""

from __future__ import annotations

import json

_PAGE = '<div id="page"><p id="copy">ABCD EFGH IJKL</p><p id="next">Z</p></div>'
_SHORT = '<div id="page"><p id="copy">AB CD</p><p id="next">Z</p></div>'
_BASE = "html, body, div, p { margin: 0px; font-size: 10px; line-height: 10px; }\n#copy { width: 80px; }\n"
_EQUAL = _BASE + "#copy::first-letter { initial-letter: 2; }\n"
_SUNKEN = _BASE + "#copy::first-letter { initial-letter: 3 2; }\n"
_RAISE = _BASE + "#copy::first-letter { initial-letter: 3 raise; }\n"
_RAISE_FIRST = _BASE + "#copy::first-letter { initial-letter: raise 3; }\n"
_DROP = _BASE + "#copy::first-letter { initial-letter: 3 drop; }\n"
_DROP_FIRST = _BASE + "#copy::first-letter { initial-letter: drop 3; }\n"
_SIZE = _BASE + "#copy::first-letter { initial-letter: 3; }\n"
_DEEP = _BASE + "#copy::first-letter { initial-letter: 2 3; }\n"
_ONE = _BASE + "#copy::first-letter { initial-letter: 1; }\n"
_FRACTION = _BASE + "#copy::first-letter { initial-letter: 2.5; }\n"
_NARROW = (
    "html, body, div, p { margin: 0px; font-size: 10px; line-height: 10px; }\n"
    "#copy { width: 40px; }\n"
    "#copy::first-letter { initial-letter: 3 2; }\n"
)


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


def _cap(box: dict[str, object] | None) -> dict[str, object] | None:
    if box is None or not isinstance(box.get("initial_letter"), dict):
        return None
    return box["initial_letter"]


def _compact(line: dict[str, object] | None) -> dict[str, object] | None:
    if line is None:
        return None
    return {"text": line.get("text"), "x": line.get("x"), "y": line.get("y"), "content_width": line.get("content_width")}


def _same_lines(left: dict[str, object], right: dict[str, object]) -> bool:
    left_box = _box(left.get("boxes"), "copy")
    right_box = _box(right.get("boxes"), "copy")
    if left.get("outcome") != "placed" or right.get("outcome") != "placed":
        return False
    if _cap(left_box) != _cap(right_box):
        return False
    return all(_compact(_line(left_box, index)) == _compact(_line(right_box, index)) for index in range(4))


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without placement still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    equal = _lay(layout_normal_flow, _PAGE, _EQUAL)
    sunken = _lay(layout_normal_flow, _PAGE, _SUNKEN)
    short = _lay(layout_normal_flow, _SHORT, _SUNKEN)
    raised = _lay(layout_normal_flow, _PAGE, _RAISE)
    raised_first = _lay(layout_normal_flow, _PAGE, _RAISE_FIRST)
    dropped = _lay(layout_normal_flow, _PAGE, _DROP)
    dropped_first = _lay(layout_normal_flow, _PAGE, _DROP_FIRST)
    sized = _lay(layout_normal_flow, _PAGE, _SIZE)
    deep = _lay(layout_normal_flow, _PAGE, _DEEP)
    one = _lay(layout_normal_flow, _PAGE, _ONE)
    fraction = _lay(layout_normal_flow, _PAGE, _FRACTION)
    narrow = _lay(layout_normal_flow, '<div id="page"><p id="copy">ABCD WXYZ</p><p id="next">Z</p></div>', _NARROW)

    equal_box = _box(equal.get("boxes"), "copy")
    sunken_box = _box(sunken.get("boxes"), "copy")
    sunken_next = _box(sunken.get("boxes"), "next")
    short_box = _box(short.get("boxes"), "copy")
    short_next = _box(short.get("boxes"), "next")
    raised_box = _box(raised.get("boxes"), "copy")
    raised_next = _box(raised.get("boxes"), "next")

    checks = {
        "equal_sink_stays_on_the_first_line": (
            equal.get("outcome") == "placed"
            and _near(_cap(equal_box), text="A", x=0, y=0, width=20, height=20)
            and _near(_line(equal_box, 0), text="BCD", x=20, y=0, content_width=30)
            and _near(_line(equal_box, 1), text="EFGH", x=20, y=10, content_width=40)
            and _near(_line(equal_box, 2), text="IJKL", x=0, y=20, content_width=40)
        ),
        "sunken_letter_shifts_the_first_line": (
            sunken.get("outcome") == "placed"
            and _near(_cap(sunken_box), text="A", x=0, y=0, width=30, height=30)
            and _near(_line(sunken_box, 0), text="BCD", x=30, y=10, content_width=30)
            and _near(_line(sunken_box, 1), text="EFGH", x=30, y=20, content_width=40)
            and _near(_line(sunken_box, 2), text="IJKL", x=0, y=30, content_width=40)
            and _line(sunken_box, 3) is None
            and _near(sunken_box, content_height=40)
            and _near(sunken_next, y=40)
        ),
        "short_sunken_remainder_grows_to_the_square": (
            short.get("outcome") == "placed"
            and _near(_cap(short_box), text="A", x=0, y=0, width=30, height=30)
            and _near(_line(short_box, 0), text="B CD", x=30, y=10, content_width=40)
            and _line(short_box, 1) is None
            and _near(short_box, content_height=30)
            and _near(short_next, y=30)
        ),
        "raise_excludes_only_the_first_line": (
            raised.get("outcome") == "placed"
            and _near(_cap(raised_box), text="A", x=0, y=0, width=30, height=30)
            and _near(_line(raised_box, 0), text="BCD", x=30, y=20, content_width=30)
            and _near(_line(raised_box, 1), text="EFGH", x=0, y=30, content_width=40)
            and _near(_line(raised_box, 2), text="IJKL", x=0, y=40, content_width=40)
            and _near(raised_box, content_height=50)
            and _near(raised_next, y=50)
            and _same_lines(raised, raised_first)
        ),
        "drop_keyword_matches_the_size": _same_lines(dropped, sized) and _same_lines(dropped_first, sized),
        "deeper_sink_stays_rejected": _invalid(deep),
        "one_line_size_stays_rejected": _invalid(one),
        "non_integer_stays_rejected": _invalid(fraction),
        "word_wider_than_the_gap_stays_rejected": _invalid(narrow),
    }
    observed = {
        "checks": checks,
        "equal_lines": None if equal_box is None else [_compact(_line(equal_box, index)) for index in range(3)],
        "sunken_cap": _cap(sunken_box),
        "sunken_lines": None if sunken_box is None else [_compact(_line(sunken_box, index)) for index in range(4)],
        "sunken_height": None if sunken_box is None else sunken_box.get("content_height"),
        "sunken_next_y": None if sunken_next is None else sunken_next.get("y"),
        "sunken_reason": sunken.get("reason"),
        "raised_lines": None if raised_box is None else [_compact(_line(raised_box, index)) for index in range(4)],
        "raised_height": None if raised_box is None else raised_box.get("content_height"),
        "raised_next_y": None if raised_next is None else raised_next.get("y"),
        "raised_reason": raised.get("reason"),
        "short_lines": None if short_box is None else [_compact(_line(short_box, index)) for index in range(2)],
        "short_height": None if short_box is None else short_box.get("content_height"),
        "rejected": {
            "deep": deep.get("reason"),
            "one": one.get("reason"),
            "fraction": fraction.get("reason"),
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
