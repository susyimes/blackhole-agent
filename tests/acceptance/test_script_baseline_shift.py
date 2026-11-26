"""Shift sub and super by the parent font's script ratios.

On a marginless horizontal page, a 15px font and line-height place super at
y 0 with the neighbors at y 5, a 20px line, and the next block at y 20. Sub
places the glyph at y 3, an 18px line, and the next block at y 18. A 30px
parent with a 15px super glyph places that glyph at y 5 inside a 30px line.
A 30px glyph inside that 15px parent at super grows the line to 35px, which
is the parent's 5px raise rather than the glyph's 10px raise. A 15px
inline-block at super starts the next block at y 20. An omitted value keeps
the next block at y 15. inherit stays invalid.

Prints JSON with boolean passed and nonempty observed. Exit 0 either way.
"""

from __future__ import annotations

import json

_PAGE = '<div id="page"><p id="row">A<span id="b">B</span>C</p><p id="next">Z</p></div>'
_ATOM = '<div id="page"><p id="row">A<span id="atom">B</span></p><p id="next">Z</p></div>'
_BASE = "html, body, div, p, span { margin: 0px; font-size: 15px; line-height: 15px; }\n"
_SUPER = _BASE + "#b { vertical-align: super; }\n"
_SUB = _BASE + "#b { vertical-align: sub; }\n"
_LENGTH = _BASE + "#b { vertical-align: 5px; }\n"
_PLAIN = _BASE
_PARENT = (
    _BASE
    + "#row { font-size: 30px; line-height: 30px; }\n"
    + "#b { font-size: 15px; line-height: 15px; vertical-align: super; }\n"
)
_CHILD = _BASE + "#b { font-size: 30px; line-height: 30px; vertical-align: super; }\n"
_ATOMIC = (
    _BASE
    + "#atom { display: inline-block; font-size: 15px; line-height: 15px; vertical-align: super; }\n"
)
_INHERIT = _BASE + "#b { vertical-align: inherit; }\n"


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
        placed = layout(markup, stylesheet, viewport_width=400)
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

    raised = _lay(layout_normal_flow, _PAGE, _SUPER)
    lowered = _lay(layout_normal_flow, _PAGE, _SUB)
    length = _lay(layout_normal_flow, _PAGE, _LENGTH)
    plain = _lay(layout_normal_flow, _PAGE, _PLAIN)
    parent = _lay(layout_normal_flow, _PAGE, _PARENT)
    child = _lay(layout_normal_flow, _PAGE, _CHILD)
    atomic = _lay(layout_normal_flow, _ATOM, _ATOMIC)
    inherited = _lay(layout_normal_flow, _PAGE, _INHERIT)

    raise_row = _box(raised.get("boxes"), "row")
    raise_next = _box(raised.get("boxes"), "next")
    lower_row = _box(lowered.get("boxes"), "row")
    lower_next = _box(lowered.get("boxes"), "next")
    length_row = _box(length.get("boxes"), "row")
    plain_row = _box(plain.get("boxes"), "row")
    plain_next = _box(plain.get("boxes"), "next")
    parent_row = _box(parent.get("boxes"), "row")
    parent_next = _box(parent.get("boxes"), "next")
    child_row = _box(child.get("boxes"), "row")
    child_next = _box(child.get("boxes"), "next")
    atom = _box(atomic.get("boxes"), "atom")
    atom_row = _box(atomic.get("boxes"), "row")
    atom_next = _box(atomic.get("boxes"), "next")
    raise_line = _line(raise_row, 0)
    lower_line = _line(lower_row, 0)
    length_line = _line(length_row, 0)
    plain_line = _line(plain_row, 0)
    parent_line = _line(parent_row, 0)
    child_line = _line(child_row, 0)
    equal_runs = [
        {"text": "A", "x": 0, "font_size": 15, "width": 15, "y": 5},
        {"text": "B", "x": 15, "font_size": 15, "width": 15, "y": 0},
        {"text": "C", "x": 30, "font_size": 15, "width": 15, "y": 5},
    ]

    checks = {
        "super_uses_one_third_of_the_parent_em": (
            raised.get("outcome") == "placed"
            and _near(raise_line, text="ABC", x=0, y=0, content_width=45, height=20)
            and _line(raise_row, 1) is None
            and _runs(raise_line) == equal_runs
            and _near(raise_next, y=20)
        ),
        "five_px_length_matches_super": (
            length.get("outcome") == "placed"
            and _runs(length_line) == equal_runs
            and _near(length_line, height=20)
        ),
        "sub_uses_one_fifth_of_the_parent_em": (
            lowered.get("outcome") == "placed"
            and _near(lower_line, text="ABC", x=0, y=0, content_width=45, height=18)
            and _runs(lower_line)
            == [
                {"text": "A", "x": 0, "font_size": 15, "width": 15, "y": 0},
                {"text": "B", "x": 15, "font_size": 15, "width": 15, "y": 3},
                {"text": "C", "x": 30, "font_size": 15, "width": 15, "y": 0},
            ]
            and _near(lower_next, y=18)
        ),
        "larger_parent_em_raises_by_ten_pixels": (
            parent.get("outcome") == "placed"
            and _near(parent_line, text="ABC", content_width=75, height=30)
            and _runs(parent_line)
            == [
                {"text": "A", "x": 0, "font_size": 30, "width": 30, "y": 0},
                {"text": "B", "x": 30, "font_size": 15, "width": 15, "y": 5},
                {"text": "C", "x": 45, "font_size": 30, "width": 30, "y": 0},
            ]
            and _near(parent_next, y=30)
        ),
        "child_em_does_not_set_the_shift": (
            child.get("outcome") == "placed"
            and _near(child_line, text="ABC", content_width=60, height=35)
            and _runs(child_line)
            == [
                {"text": "A", "x": 0, "font_size": 15, "width": 15, "y": 20},
                {"text": "B", "x": 15, "font_size": 30, "width": 30, "y": 0},
                {"text": "C", "x": 45, "font_size": 15, "width": 15, "y": 20},
            ]
            and _near(child_next, y=35)
        ),
        "inline_block_super_moves_the_next_block": (
            atomic.get("outcome") == "placed"
            and _near(atom, x=15, y=0, content_height=15, content_width=15)
            and _near(atom_row, content_height=20)
            and _near(atom_next, y=20)
        ),
        "omitted_value_stays_on_the_strut": (
            plain.get("outcome") == "placed"
            and _near(plain_line, text="ABC", content_width=45, height=15)
            and _near(plain_next, y=15)
        ),
        "inherit_stays_rejected": _invalid(inherited, "vertical-align inherit is unsupported"),
    }
    observed = {
        "checks": checks,
        "super": {
            "outcome": raised.get("outcome"),
            "reason": raised.get("reason"),
            "runs": _runs(raise_line),
            "height": None if raise_line is None else raise_line.get("height"),
            "next": None if raise_next is None else raise_next.get("y"),
        },
        "sub": {
            "outcome": lowered.get("outcome"),
            "reason": lowered.get("reason"),
            "runs": _runs(lower_line),
            "next": None if lower_next is None else lower_next.get("y"),
        },
        "parent": {
            "outcome": parent.get("outcome"),
            "reason": parent.get("reason"),
            "runs": _runs(parent_line),
            "next": None if parent_next is None else parent_next.get("y"),
        },
        "child": {
            "outcome": child.get("outcome"),
            "reason": child.get("reason"),
            "runs": _runs(child_line),
            "height": None if child_line is None else child_line.get("height"),
            "next": None if child_next is None else child_next.get("y"),
        },
        "atom": {
            "outcome": atomic.get("outcome"),
            "reason": atomic.get("reason"),
            "y": None if atom is None else atom.get("y"),
            "row": None if atom_row is None else atom_row.get("content_height"),
            "next": None if atom_next is None else atom_next.get("y"),
        },
    }
    return all(checks.values()), observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
