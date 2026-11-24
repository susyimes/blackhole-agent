"""Contain a left float inside an inline-block.

In a 200px viewport at 10px, A, the atomic box, and C share one line. A 20
by 10 left float and the word WW beside it make that box 40 by 10 at x 10
y 0. The float is at x 10 y 0, WW is at x 30 y 0, C is at x 50, and the
next block starts at y 10. A 20px atomic width puts the float at x 10 y 0
and wraps WW WW under it at y 10 and y 20, with A and C at y 20 and the
next block at y 30. A 40px width and a 20px-tall float keep both WW words
at x 30, on y 0 and y 10, with A and C at y 10 and the next block at y 20.
A nested inline-block, a mixed font, and a right float stay unplaced.
Words before the float keep the full-width line above it.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A layout that still rejects the float exits 0 with passed
false.
"""

from __future__ import annotations

import json
import sys

_FIT = (
    '<div id="page"><div id="row">A<span id="atom"><span id="fl">F</span>WW</span>C</div>'
    '<div id="next">Z</div></div>'
)
_WRAP = (
    '<div id="page"><div id="row">A<span id="atom"><span id="fl">F</span>WW WW</span>C</div>'
    '<div id="next">Z</div></div>'
)
_BASE = """
#page { font-size: 10px; line-height: 10px; }
#row { font-size: 10px; line-height: 10px; }
#next { font-size: 10px; line-height: 10px; }
#atom { display: inline-block; font-size: 10px; line-height: 10px; }
#fl { float: left; width: 20px; height: 10px; font-size: 10px; line-height: 10px; }
"""
_NARROW = _BASE + "#atom { width: 20px; }\n"
_TALL = _BASE + "#atom { width: 40px; }\n#fl { height: 20px; }\n"
_NESTED = '<div id="page"><div id="row"><span id="atom"><span id="inner">BB</span></span></div></div>'
_NESTED_CSS = """
#page { font-size: 10px; line-height: 10px; }
#atom { display: inline-block; font-size: 10px; line-height: 10px; }
#inner { display: inline-block; font-size: 10px; line-height: 10px; }
"""
_MIXED = '<div id="page"><div id="row"><span id="atom">X<span id="big">Q</span><span id="inner">BB</span></span></div></div>'
_MIXED_CSS = """
#page { font-size: 10px; line-height: 10px; }
#atom { display: inline-block; font-size: 10px; line-height: 10px; }
#big { font-size: 20px; }
#inner { display: block; font-size: 10px; line-height: 10px; }
"""
_RIGHT = _FIT
_RIGHT_CSS = _BASE.replace("float: left", "float: right")
_BEFORE = (
    '<div id="page"><div id="row">A<span id="atom">WW<span id="fl">F</span></span>C</div>'
    '<div id="next">Z</div></div>'
)


def _box(boxes: object, ident: str) -> dict[str, object] | None:
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if isinstance(item, dict) and item.get("id") == ident:
            return item
    return None


def _anon(boxes: object) -> dict[str, object] | None:
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if not isinstance(item, dict) or not str(item.get("id") or "").startswith("anon-"):
            continue
        line = _line(item, 0)
        if line is not None and line.get("text") == "WW":
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


def _rejected(placed: dict[str, object]) -> bool:
    return placed.get("outcome") == "invalid" and placed.get("reason") == "inline-block content is unsupported"


def _spot(box: dict[str, object] | None) -> dict[str, object] | None:
    if box is None:
        return None
    return {
        "x": box.get("x"),
        "y": box.get("y"),
        "w": box.get("content_width"),
        "h": box.get("content_height"),
    }


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without placement still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    fit = _lay(layout_normal_flow, _FIT, _BASE)
    narrow = _lay(layout_normal_flow, _WRAP, _NARROW)
    tall = _lay(layout_normal_flow, _WRAP, _TALL)
    nested = _lay(layout_normal_flow, _NESTED, _NESTED_CSS)
    mixed = _lay(layout_normal_flow, _MIXED, _MIXED_CSS)
    right = _lay(layout_normal_flow, _RIGHT, _RIGHT_CSS)
    before = _lay(layout_normal_flow, _BEFORE, _BASE)

    fit_row = _box(fit.get("boxes"), "row")
    fit_atom = _box(fit.get("boxes"), "atom")
    fit_float = _box(fit.get("boxes"), "fl")
    fit_text = _anon(fit.get("boxes"))
    fit_next = _box(fit.get("boxes"), "next")
    narrow_row = _box(narrow.get("boxes"), "row")
    narrow_atom = _box(narrow.get("boxes"), "atom")
    narrow_float = _box(narrow.get("boxes"), "fl")
    narrow_text = _anon(narrow.get("boxes"))
    narrow_next = _box(narrow.get("boxes"), "next")
    tall_row = _box(tall.get("boxes"), "row")
    tall_atom = _box(tall.get("boxes"), "atom")
    tall_float = _box(tall.get("boxes"), "fl")
    tall_text = _anon(tall.get("boxes"))
    tall_next = _box(tall.get("boxes"), "next")

    checks = {
        "float_and_word_share_the_shrink_width": (
            fit.get("outcome") == "placed"
            and _near(fit_row, content_width=200, content_height=10)
            and _near(
                _line(fit_row, 0),
                text="AC",
                x=0,
                y=0,
                height=10,
                content_width=60,
                runs=[
                    {"text": "A", "x": 0, "font_size": 10, "width": 10},
                    {"text": "C", "x": 50, "font_size": 10, "width": 10},
                ],
                atoms=[{"id": "atom", "x": 10, "width": 40}],
            )
            and _near(fit_atom, x=10, y=0, content_width=40, content_height=10)
            and _near(fit_float, x=10, y=0, content_width=20, content_height=10)
            and _near(fit_text, x=10, y=0, content_width=40, content_height=10)
            and _near(_line(fit_text, 0), text="WW", x=30, y=0, height=10, content_width=20)
            and _near(fit_next, x=0, y=10, content_height=10)
        ),
        "narrow_box_wraps_words_under_the_float": (
            narrow.get("outcome") == "placed"
            and _near(narrow_row, content_height=30)
            and _near(
                _line(narrow_row, 0),
                text="AC",
                height=30,
                content_width=40,
                runs=[
                    {"text": "A", "x": 0, "font_size": 10, "width": 10, "y": 20},
                    {"text": "C", "x": 30, "font_size": 10, "width": 10, "y": 20},
                ],
                atoms=[{"id": "atom", "x": 10, "width": 20}],
            )
            and _near(narrow_atom, x=10, y=0, content_width=20, content_height=30)
            and _near(narrow_float, x=10, y=0, content_width=20, content_height=10)
            and _near(_line(narrow_text, 0), text="WW", x=10, y=10, height=10, content_width=20)
            and _near(_line(narrow_text, 1), text="WW", x=10, y=20, height=10, content_width=20)
            and _near(narrow_next, y=30)
        ),
        "taller_float_shortens_both_words": (
            tall.get("outcome") == "placed"
            and _near(tall_row, content_height=20)
            and _near(
                _line(tall_row, 0),
                text="AC",
                height=20,
                content_width=60,
                runs=[
                    {"text": "A", "x": 0, "font_size": 10, "width": 10, "y": 10},
                    {"text": "C", "x": 50, "font_size": 10, "width": 10, "y": 10},
                ],
                atoms=[{"id": "atom", "x": 10, "width": 40}],
            )
            and _near(tall_atom, x=10, y=0, content_width=40, content_height=20)
            and _near(tall_float, x=10, y=0, content_width=20, content_height=20)
            and _near(_line(tall_text, 0), text="WW", x=30, y=0, height=10, content_width=20)
            and _near(_line(tall_text, 1), text="WW", x=30, y=10, height=10, content_width=20)
            and _near(tall_next, y=20)
        ),
        "nested_inline_block_is_rejected": _rejected(nested),
        "mixed_font_is_rejected": _rejected(mixed),
        "right_float_is_rejected": _rejected(right),
        "words_before_the_float_keep_the_full_line": (
            before.get("outcome") == "placed"
            and _near(_box(before.get("boxes"), "atom"), x=10, y=0, content_width=20, content_height=20)
            and _near(_box(before.get("boxes"), "fl"), x=10, y=10, content_width=20, content_height=10)
            and _near(_line(_anon(before.get("boxes")), 0), text="WW", x=10, y=0, height=10, content_width=20)
            and _near(_box(before.get("boxes"), "next"), y=20)
        ),
    }
    observed = {
        "fit": {
            "outcome": fit.get("outcome"),
            "reason": fit.get("reason"),
            "atom": _spot(fit_atom),
            "float": _spot(fit_float),
            "word": None if _line(fit_text, 0) is None else _line(fit_text, 0).get("x"),
            "c_x": None
            if _line(fit_row, 0) is None or not isinstance(_line(fit_row, 0).get("runs"), list)
            else _line(fit_row, 0)["runs"][1].get("x"),
            "next_y": None if fit_next is None else fit_next.get("y"),
        },
        "narrow": {
            "outcome": narrow.get("outcome"),
            "reason": narrow.get("reason"),
            "atom": _spot(narrow_atom),
            "first_y": None if _line(narrow_text, 0) is None else _line(narrow_text, 0).get("y"),
            "second_y": None if _line(narrow_text, 1) is None else _line(narrow_text, 1).get("y"),
            "word_y": None
            if _line(narrow_row, 0) is None or not isinstance(_line(narrow_row, 0).get("runs"), list)
            else _line(narrow_row, 0)["runs"][0].get("y"),
            "next_y": None if narrow_next is None else narrow_next.get("y"),
        },
        "tall": {
            "outcome": tall.get("outcome"),
            "reason": tall.get("reason"),
            "atom": _spot(tall_atom),
            "float_h": None if tall_float is None else tall_float.get("content_height"),
            "second_x": None if _line(tall_text, 1) is None else _line(tall_text, 1).get("x"),
            "word_y": None
            if _line(tall_row, 0) is None or not isinstance(_line(tall_row, 0).get("runs"), list)
            else _line(tall_row, 0)["runs"][0].get("y"),
            "next_y": None if tall_next is None else tall_next.get("y"),
        },
        "nested": {"outcome": nested.get("outcome"), "reason": nested.get("reason")},
        "mixed": {"outcome": mixed.get("outcome"), "reason": mixed.get("reason")},
        "right": {"outcome": right.get("outcome"), "reason": right.get("reason")},
        "before": {"outcome": before.get("outcome"), "reason": before.get("reason")},
        "checks": checks,
    }
    return all(checks.values()), observed


def main() -> None:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - the probe must exit 0 even when it fails
        passed, observed = False, {"error": f"{type(exc).__name__}: {exc}"}
    payload = {"passed": bool(passed), "observed": observed if observed else {"error": "empty"}}
    try:
        encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    except (UnicodeEncodeError, TypeError) as exc:
        encoded = json.dumps(
            {"passed": False, "observed": {"error": f"{type(exc).__name__}: {exc}"}},
            separators=(",", ":"),
        ).encode("ascii")
    sys.stdout.buffer.write(encoded + b"\n")


if __name__ == "__main__":
    main()
