"""Lay a block child out inside an inline-block.

In a 200px viewport at 10px, A, the atomic box, and C share one line. The
block BB is at x 10 y 0 and 20 by 10, C is at x 30, and the next block is
at y 10. A 10px margin-bottom keeps BB at y 0, grows the atomic content to
20, and starts the next block at y 20. A 20px width wraps BB CC onto y 0
and y 10, and paints A and C at y 10. Two blocks with 10px vertical margins
collapse the gap between them to 10px: AA at y 10, BB at y 30, the
surrounding words at y 30, and the next block at y 50. A nested
inline-block, loose text beside the block, and a float inside the atomic
box stay unplaced.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A layout that still rejects the block child exits 0 with
passed false.
"""

from __future__ import annotations

import json
import sys

_FIT = (
    '<div id="page"><div id="row">A<span id="atom"><span id="inner">BB</span></span>C</div>'
    '<div id="next">Z</div></div>'
)
_FIT_CSS = """
#page { font-size: 10px; line-height: 10px; }
#row { font-size: 10px; line-height: 10px; }
#next { font-size: 10px; line-height: 10px; }
#atom { display: inline-block; }
#inner { display: block; font-size: 10px; line-height: 10px; }
"""
_MARGIN_CSS = """
#page { font-size: 10px; line-height: 10px; }
#row { font-size: 10px; line-height: 10px; }
#next { font-size: 10px; line-height: 10px; }
#atom { display: inline-block; }
#inner { display: block; font-size: 10px; line-height: 10px; margin-bottom: 10px; }
"""
_WRAP = (
    '<div id="page"><div id="row">A<span id="atom"><span id="inner">BB CC</span></span>C</div>'
    '<div id="next">Z</div></div>'
)
_WRAP_CSS = """
#page { font-size: 10px; line-height: 10px; }
#row { font-size: 10px; line-height: 10px; }
#next { font-size: 10px; line-height: 10px; }
#atom { display: inline-block; width: 20px; }
#inner { display: block; font-size: 10px; line-height: 10px; }
"""
_STACK = (
    '<div id="page"><div id="row">A<span id="atom"><span id="a">AA</span>'
    '<span id="b">BB</span></span>C</div><div id="next">Z</div></div>'
)
_STACK_CSS = """
#page { font-size: 10px; line-height: 10px; }
#row { font-size: 10px; line-height: 10px; }
#next { font-size: 10px; line-height: 10px; }
#atom { display: inline-block; }
#a { display: block; font-size: 10px; line-height: 10px; margin-top: 10px; margin-bottom: 10px; }
#b { display: block; font-size: 10px; line-height: 10px; margin-top: 10px; margin-bottom: 10px; }
"""
_NESTED = '<div id="page"><div id="row"><span id="atom"><span id="inner">BB</span></span></div></div>'
_NESTED_CSS = """
#page { font-size: 10px; line-height: 10px; }
#atom { display: inline-block; }
#inner { display: inline-block; font-size: 10px; line-height: 10px; }
"""
_LOOSE = '<div id="page"><div id="row"><span id="atom">X<span id="inner">BB</span></span></div></div>'
_FLOAT = '<div id="page"><div id="row"><span id="atom"><span id="inner">BB</span></span></div></div>'
_FLOAT_CSS = """
#page { font-size: 10px; line-height: 10px; }
#atom { display: inline-block; }
#inner { float: left; width: 20px; height: 10px; }
"""


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


def _spot(box: dict[str, object] | None) -> dict[str, object] | None:
    if box is None:
        return None
    return {
        "x": box.get("x"),
        "y": box.get("y"),
        "w": box.get("content_width"),
        "h": box.get("content_height"),
    }


def _rejected(placed: dict[str, object]) -> bool:
    return placed.get("outcome") == "invalid" and placed.get("reason") == "inline-block content is unsupported"


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without placement still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    fit = _lay(layout_normal_flow, _FIT, _FIT_CSS)
    margin = _lay(layout_normal_flow, _FIT, _MARGIN_CSS)
    wrap = _lay(layout_normal_flow, _WRAP, _WRAP_CSS)
    stack = _lay(layout_normal_flow, _STACK, _STACK_CSS)
    nested = _lay(layout_normal_flow, _NESTED, _NESTED_CSS)
    loose = _lay(layout_normal_flow, _LOOSE, _FIT_CSS)
    floated = _lay(layout_normal_flow, _FLOAT, _FLOAT_CSS)

    fit_row = _box(fit.get("boxes"), "row")
    fit_atom = _box(fit.get("boxes"), "atom")
    fit_inner = _box(fit.get("boxes"), "inner")
    fit_next = _box(fit.get("boxes"), "next")
    margin_row = _box(margin.get("boxes"), "row")
    margin_atom = _box(margin.get("boxes"), "atom")
    margin_inner = _box(margin.get("boxes"), "inner")
    margin_next = _box(margin.get("boxes"), "next")
    wrap_row = _box(wrap.get("boxes"), "row")
    wrap_atom = _box(wrap.get("boxes"), "atom")
    wrap_inner = _box(wrap.get("boxes"), "inner")
    wrap_next = _box(wrap.get("boxes"), "next")
    stack_row = _box(stack.get("boxes"), "row")
    stack_atom = _box(stack.get("boxes"), "atom")
    stack_a = _box(stack.get("boxes"), "a")
    stack_b = _box(stack.get("boxes"), "b")
    stack_next = _box(stack.get("boxes"), "next")

    checks = {
        "shrink_to_the_block": (
            fit.get("outcome") == "placed"
            and _near(fit_row, content_width=200, content_height=10)
            and _near(
                _line(fit_row, 0),
                text="AC",
                x=0,
                y=0,
                height=10,
                content_width=40,
                runs=[
                    {"text": "A", "x": 0, "font_size": 10, "width": 10},
                    {"text": "C", "x": 30, "font_size": 10, "width": 10},
                ],
                atoms=[{"id": "atom", "x": 10, "width": 20}],
            )
            and _near(fit_atom, x=10, y=0, content_width=20, content_height=10)
            and _near(_line(fit_inner, 0), text="BB", x=10, y=0, height=10, content_width=20)
            and _near(fit_next, x=0, y=10, content_height=10)
        ),
        "margin_stays_inside": (
            margin.get("outcome") == "placed"
            and _near(margin_row, content_height=20)
            and _near(
                _line(margin_row, 0),
                text="AC",
                x=0,
                y=0,
                height=20,
                runs=[
                    {"text": "A", "x": 0, "font_size": 10, "width": 10},
                    {"text": "C", "x": 30, "font_size": 10, "width": 10},
                ],
            )
            and _near(margin_atom, x=10, y=0, content_width=20, content_height=20)
            and _near(_line(margin_inner, 0), text="BB", x=10, y=0, height=10)
            and _near(margin_next, y=20)
        ),
        "specified_width_wraps_to_the_last_line": (
            wrap.get("outcome") == "placed"
            and _near(wrap_row, content_height=20)
            and _near(
                _line(wrap_row, 0),
                text="AC",
                y=0,
                height=20,
                runs=[
                    {"text": "A", "x": 0, "font_size": 10, "width": 10, "y": 10},
                    {"text": "C", "x": 30, "font_size": 10, "width": 10, "y": 10},
                ],
            )
            and _near(wrap_atom, x=10, y=0, content_width=20, content_height=20)
            and _near(_line(wrap_inner, 0), text="BB", x=10, y=0, height=10, content_width=20)
            and _near(_line(wrap_inner, 1), text="CC", x=10, y=10, height=10, content_width=20)
            and _near(wrap_next, y=20)
        ),
        "sibling_margins_collapse_inside": (
            stack.get("outcome") == "placed"
            and _near(stack_atom, x=10, y=0, content_width=20, content_height=50)
            and _near(stack_a, x=10, y=10, content_width=20, content_height=10)
            and _near(_line(stack_a, 0), text="AA", x=10, y=10, height=10)
            and _near(stack_b, x=10, y=30, content_width=20, content_height=10)
            and _near(_line(stack_b, 0), text="BB", x=10, y=30, height=10)
            and _near(
                _line(stack_row, 0),
                height=50,
                runs=[
                    {"text": "A", "x": 0, "font_size": 10, "width": 10, "y": 30},
                    {"text": "C", "x": 30, "font_size": 10, "width": 10, "y": 30},
                ],
            )
            and _near(stack_next, y=50)
        ),
        "nested_inline_block_is_rejected": _rejected(nested),
        "loose_text_is_rejected": _rejected(loose),
        "float_inside_is_rejected": _rejected(floated),
    }
    observed = {
        "fit": {
            "outcome": fit.get("outcome"),
            "reason": fit.get("reason"),
            "row": _spot(fit_row),
            "line": None if _line(fit_row, 0) is None else _line(fit_row, 0).get("runs"),
            "atom": _spot(fit_atom),
            "inner": _spot(fit_inner),
            "next_y": None if fit_next is None else fit_next.get("y"),
        },
        "margin": {
            "outcome": margin.get("outcome"),
            "reason": margin.get("reason"),
            "atom": _spot(margin_atom),
            "inner_line_y": None if _line(margin_inner, 0) is None else _line(margin_inner, 0).get("y"),
            "next_y": None if margin_next is None else margin_next.get("y"),
        },
        "wrap": {
            "outcome": wrap.get("outcome"),
            "reason": wrap.get("reason"),
            "runs": None if _line(wrap_row, 0) is None else _line(wrap_row, 0).get("runs"),
            "first": None if _line(wrap_inner, 0) is None else _line(wrap_inner, 0).get("text"),
            "second": None if _line(wrap_inner, 1) is None else _line(wrap_inner, 1).get("text"),
            "second_y": None if _line(wrap_inner, 1) is None else _line(wrap_inner, 1).get("y"),
            "next_y": None if wrap_next is None else wrap_next.get("y"),
        },
        "stack": {
            "outcome": stack.get("outcome"),
            "reason": stack.get("reason"),
            "a_y": None if stack_a is None else stack_a.get("y"),
            "b_y": None if stack_b is None else stack_b.get("y"),
            "atom_h": None if stack_atom is None else stack_atom.get("content_height"),
            "word_y": None
            if _line(stack_row, 0) is None or not isinstance(_line(stack_row, 0).get("runs"), list)
            else _line(stack_row, 0)["runs"][0].get("y"),
            "next_y": None if stack_next is None else stack_next.get("y"),
        },
        "nested": {"outcome": nested.get("outcome"), "reason": nested.get("reason")},
        "loose": {"outcome": loose.get("outcome"), "reason": loose.get("reason")},
        "floated": {"outcome": floated.get("outcome"), "reason": floated.get("reason")},
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
