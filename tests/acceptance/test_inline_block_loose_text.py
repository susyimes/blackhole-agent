"""Stack loose text beside a block child inside an inline-block.

In a 200px viewport at 10px, X above BB paints an anonymous block at x 10 y 0
sized 20 by 10 and BB at x 10 y 10. The atomic box is 20 by 20, A and C sit
at y 10, and the next block starts at y 20. WWWW widens the atomic box and
BB to 40, with C at x 50. A 20px atomic width wraps WW WW after BB onto y 10
and y 20, and A and C align to that last line. A 10px top and bottom margin
on BB keeps X at y 0, BB at y 20, and the next block at y 40. A mixed
font stays unplaced. A lone left float is contained.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A layout that still rejects the loose text exits 0 with
passed false.
"""

from __future__ import annotations

import json
import sys

_FIT = (
    '<div id="page"><div id="row">A<span id="atom">X<span id="inner">BB</span></span>C</div>'
    '<div id="next">Z</div></div>'
)
_WIDE = (
    '<div id="page"><div id="row">A<span id="atom">WWWW<span id="inner">BB</span></span>C</div>'
    '<div id="next">Z</div></div>'
)
_AFTER = (
    '<div id="page"><div id="row">A<span id="atom"><span id="inner">BB</span>WW WW</span>C</div>'
    '<div id="next">Z</div></div>'
)
_BASE = """
#page { font-size: 10px; line-height: 10px; }
#row { font-size: 10px; line-height: 10px; }
#next { font-size: 10px; line-height: 10px; }
#atom { display: inline-block; font-size: 10px; line-height: 10px; }
#inner { display: block; font-size: 10px; line-height: 10px; }
"""
_NARROW = _BASE + "#atom { width: 20px; }\n"
_MARGIN = _BASE + "#inner { margin-top: 10px; margin-bottom: 10px; }\n"
_NESTED = '<div id="page"><div id="row"><span id="atom"><span id="inner">BB</span></span></div></div>'
_NESTED_CSS = """
#page { font-size: 10px; line-height: 10px; }
#atom { display: inline-block; font-size: 10px; line-height: 10px; }
#inner { display: inline-block; font-size: 10px; line-height: 10px; }
"""
_FLOAT = '<div id="page"><div id="row"><span id="atom"><span id="inner">BB</span></span></div></div>'
_FLOAT_CSS = """
#page { font-size: 10px; line-height: 10px; }
#atom { display: inline-block; font-size: 10px; line-height: 10px; }
#inner { float: left; width: 20px; height: 10px; }
"""
_MIXED = (
    '<div id="page"><div id="row"><span id="atom">X<span id="big">Q</span>'
    '<span id="inner">BB</span></span></div></div>'
)
_MIXED_CSS = _BASE + "#big { font-size: 20px; }\n"


def _box(boxes: object, ident: str) -> dict[str, object] | None:
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if isinstance(item, dict) and item.get("id") == ident:
            return item
    return None


def _anon(boxes: object, text: str) -> dict[str, object] | None:
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if not isinstance(item, dict) or not str(item.get("id") or "").startswith("anon-"):
            continue
        line = _line(item, 0)
        if line is not None and line.get("text") == text:
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

    fit = _lay(layout_normal_flow, _FIT, _BASE)
    wide = _lay(layout_normal_flow, _WIDE, _BASE)
    after = _lay(layout_normal_flow, _AFTER, _NARROW)
    margin = _lay(layout_normal_flow, _FIT, _MARGIN)
    nested = _lay(layout_normal_flow, _NESTED, _NESTED_CSS)
    floated = _lay(layout_normal_flow, _FLOAT, _FLOAT_CSS)
    mixed = _lay(layout_normal_flow, _MIXED, _MIXED_CSS)

    fit_row = _box(fit.get("boxes"), "row")
    fit_atom = _box(fit.get("boxes"), "atom")
    fit_text = _anon(fit.get("boxes"), "X")
    fit_inner = _box(fit.get("boxes"), "inner")
    fit_next = _box(fit.get("boxes"), "next")
    wide_row = _box(wide.get("boxes"), "row")
    wide_atom = _box(wide.get("boxes"), "atom")
    wide_text = _anon(wide.get("boxes"), "WWWW")
    wide_inner = _box(wide.get("boxes"), "inner")
    wide_next = _box(wide.get("boxes"), "next")
    after_row = _box(after.get("boxes"), "row")
    after_atom = _box(after.get("boxes"), "atom")
    after_text = _anon(after.get("boxes"), "WW")
    after_inner = _box(after.get("boxes"), "inner")
    after_next = _box(after.get("boxes"), "next")
    margin_row = _box(margin.get("boxes"), "row")
    margin_atom = _box(margin.get("boxes"), "atom")
    margin_text = _anon(margin.get("boxes"), "X")
    margin_inner = _box(margin.get("boxes"), "inner")
    margin_next = _box(margin.get("boxes"), "next")

    checks = {
        "text_stacks_above_the_block": (
            fit.get("outcome") == "placed"
            and _near(fit_row, content_width=200, content_height=20)
            and _near(
                _line(fit_row, 0),
                text="AC",
                x=0,
                y=0,
                height=20,
                content_width=40,
                runs=[
                    {"text": "A", "x": 0, "font_size": 10, "width": 10, "y": 10},
                    {"text": "C", "x": 30, "font_size": 10, "width": 10, "y": 10},
                ],
                atoms=[{"id": "atom", "x": 10, "width": 20}],
            )
            and _near(fit_atom, x=10, y=0, content_width=20, content_height=20)
            and _near(fit_text, x=10, y=0, content_width=20, content_height=10)
            and _near(_line(fit_text, 0), text="X", x=10, y=0, height=10, content_width=10)
            and _near(fit_inner, x=10, y=10, content_width=20, content_height=10)
            and _near(_line(fit_inner, 0), text="BB", x=10, y=10, height=10, content_width=20)
            and _near(fit_next, x=0, y=20, content_height=10)
        ),
        "wider_text_stretches_the_block": (
            wide.get("outcome") == "placed"
            and _near(wide_atom, x=10, y=0, content_width=40, content_height=20)
            and _near(wide_text, x=10, y=0, content_width=40, content_height=10)
            and _near(_line(wide_text, 0), text="WWWW", x=10, y=0, height=10, content_width=40)
            and _near(wide_inner, x=10, y=10, content_width=40, content_height=10)
            and _near(_line(wide_inner, 0), text="BB", x=10, y=10, height=10, content_width=20)
            and _near(
                _line(wide_row, 0),
                height=20,
                runs=[
                    {"text": "A", "x": 0, "font_size": 10, "width": 10, "y": 10},
                    {"text": "C", "x": 50, "font_size": 10, "width": 10, "y": 10},
                ],
            )
            and _near(wide_next, y=20)
        ),
        "trailing_wrap_aligns_to_its_last_line": (
            after.get("outcome") == "placed"
            and _near(after_row, content_height=30)
            and _near(after_atom, x=10, y=0, content_width=20, content_height=30)
            and _near(after_inner, x=10, y=0, content_width=20, content_height=10)
            and _near(_line(after_inner, 0), text="BB", x=10, y=0, height=10, content_width=20)
            and _near(after_text, x=10, y=10, content_width=20, content_height=20)
            and _near(_line(after_text, 0), text="WW", x=10, y=10, height=10, content_width=20)
            and _near(_line(after_text, 1), text="WW", x=10, y=20, height=10, content_width=20)
            and _near(
                _line(after_row, 0),
                height=30,
                runs=[
                    {"text": "A", "x": 0, "font_size": 10, "width": 10, "y": 20},
                    {"text": "C", "x": 30, "font_size": 10, "width": 10, "y": 20},
                ],
            )
            and _near(after_next, y=30)
        ),
        "block_margin_stays_inside": (
            margin.get("outcome") == "placed"
            and _near(margin_atom, x=10, y=0, content_width=20, content_height=40)
            and _near(margin_text, x=10, y=0, content_width=20, content_height=10)
            and _near(margin_inner, x=10, y=20, content_width=20, content_height=10)
            and _near(
                _line(margin_row, 0),
                height=40,
                runs=[
                    {"text": "A", "x": 0, "font_size": 10, "width": 10, "y": 20},
                    {"text": "C", "x": 30, "font_size": 10, "width": 10, "y": 20},
                ],
            )
            and _near(margin_next, y=40)
        ),
        "lone_float_is_contained": (
            floated.get("outcome") == "placed"
            and _near(_box(floated.get("boxes"), "atom"), x=0, y=0, content_width=20, content_height=10)
            and _near(_box(floated.get("boxes"), "inner"), x=0, y=0, content_width=20, content_height=10)
            and _near(_line(_box(floated.get("boxes"), "inner"), 0), text="BB", x=0, y=0, height=10, content_width=20)
        ),
        "mixed_font_is_rejected": _rejected(mixed),
    }
    observed = {
        "fit": {
            "outcome": fit.get("outcome"),
            "reason": fit.get("reason"),
            "atom": _spot(fit_atom),
            "text": _spot(fit_text),
            "inner": _spot(fit_inner),
            "runs": None if _line(fit_row, 0) is None else _line(fit_row, 0).get("runs"),
            "next_y": None if fit_next is None else fit_next.get("y"),
        },
        "wide": {
            "outcome": wide.get("outcome"),
            "reason": wide.get("reason"),
            "atom": _spot(wide_atom),
            "inner": _spot(wide_inner),
            "line_w": None if _line(wide_inner, 0) is None else _line(wide_inner, 0).get("content_width"),
            "c_x": None
            if _line(wide_row, 0) is None or not isinstance(_line(wide_row, 0).get("runs"), list)
            else _line(wide_row, 0)["runs"][1].get("x"),
        },
        "after": {
            "outcome": after.get("outcome"),
            "reason": after.get("reason"),
            "atom": _spot(after_atom),
            "second_y": None if _line(after_text, 1) is None else _line(after_text, 1).get("y"),
            "word_y": None
            if _line(after_row, 0) is None or not isinstance(_line(after_row, 0).get("runs"), list)
            else _line(after_row, 0)["runs"][0].get("y"),
            "next_y": None if after_next is None else after_next.get("y"),
        },
        "margin": {
            "outcome": margin.get("outcome"),
            "reason": margin.get("reason"),
            "atom_h": None if margin_atom is None else margin_atom.get("content_height"),
            "inner_y": None if margin_inner is None else margin_inner.get("y"),
            "next_y": None if margin_next is None else margin_next.get("y"),
        },
        "nested": {"outcome": nested.get("outcome"), "reason": nested.get("reason")},
        "floated": {"outcome": floated.get("outcome"), "reason": floated.get("reason")},
        "mixed": {"outcome": mixed.get("outcome"), "reason": mixed.get("reason")},
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
