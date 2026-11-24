"""Place a nested inline-block on the line inside its parent inline-block.

In a 200px viewport at 10px, W, BB, and Q make the outer box 40 by 10.
W is at x 10, BB at x 20, Q at x 40, C at x 50, and the next block at y 10.
A 20px outer width wraps BB under W: W at y 0, BB at y 10, A and C at y 10,
and the next block at y 20. A 40px inner box widens the outer box to 40 and
keeps BB on a 20px line. A different font beside the nested box, a right
float, and positioned content stay unplaced.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A layout that still rejects the nested box exits 0 with
passed false.
"""

from __future__ import annotations

import json
import sys

_FIT = (
    '<div id="page"><div id="row">A<span id="atom">W<span id="inner">BB</span>Q</span>C</div>'
    '<div id="next">Z</div></div>'
)
_WRAP = (
    '<div id="page"><div id="row">A<span id="atom">W<span id="inner">BB</span></span>C</div>'
    '<div id="next">Z</div></div>'
)
_WIDE = (
    '<div id="page"><div id="row">A<span id="atom"><span id="inner">BB</span></span>C</div>'
    '<div id="next">Z</div></div>'
)
_MIXED = (
    '<div id="page"><div id="row"><span id="atom">X<span id="big">Q</span>'
    '<span id="inner">BB</span></span></div></div>'
)
_RIGHT = '<div id="page"><div id="row"><span id="atom"><span id="fl">F</span>WW</span></div></div>'
_ABS = '<div id="page"><div id="row"><span id="atom"><span id="rel">BB</span></span></div></div>'
_BASE = """
#page { font-size: 10px; line-height: 10px; }
#row { font-size: 10px; line-height: 10px; }
#next { font-size: 10px; line-height: 10px; }
#atom { display: inline-block; font-size: 10px; line-height: 10px; }
#inner { display: inline-block; font-size: 10px; line-height: 10px; }
"""
_WRAP_CSS = _BASE + "#atom { width: 20px; }\n"
_WIDE_CSS = _BASE + "#inner { width: 40px; }\n"
_MIXED_CSS = _BASE + "#big { font-size: 20px; }\n"
_RIGHT_CSS = _BASE + "#fl { float: right; width: 20px; height: 10px; }\n"
_ABS_CSS = _BASE + "#rel { position: absolute; left: 5px; }\n"


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
    wrap = _lay(layout_normal_flow, _WRAP, _WRAP_CSS)
    wide = _lay(layout_normal_flow, _WIDE, _WIDE_CSS)
    mixed = _lay(layout_normal_flow, _MIXED, _MIXED_CSS)
    right = _lay(layout_normal_flow, _RIGHT, _RIGHT_CSS)
    absolute = _lay(layout_normal_flow, _ABS, _ABS_CSS)

    fit_row = _box(fit.get("boxes"), "row")
    fit_atom = _box(fit.get("boxes"), "atom")
    fit_inner = _box(fit.get("boxes"), "inner")
    fit_next = _box(fit.get("boxes"), "next")
    wrap_row = _box(wrap.get("boxes"), "row")
    wrap_atom = _box(wrap.get("boxes"), "atom")
    wrap_inner = _box(wrap.get("boxes"), "inner")
    wrap_next = _box(wrap.get("boxes"), "next")
    wide_row = _box(wide.get("boxes"), "row")
    wide_atom = _box(wide.get("boxes"), "atom")
    wide_inner = _box(wide.get("boxes"), "inner")
    wide_next = _box(wide.get("boxes"), "next")

    checks = {
        "words_beside_the_nested_box_share_one_line": (
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
            and _near(
                _line(fit_atom, 0),
                text="WQ",
                x=10,
                y=0,
                height=10,
                content_width=40,
                runs=[
                    {"text": "W", "x": 10, "font_size": 10, "width": 10},
                    {"text": "Q", "x": 40, "font_size": 10, "width": 10},
                ],
                atoms=[{"id": "inner", "x": 20, "width": 20}],
            )
            and _near(fit_inner, x=20, y=0, content_width=20, content_height=10)
            and _near(_line(fit_inner, 0), text="BB", x=20, y=0, height=10, content_width=20)
            and _near(fit_next, x=0, y=10, content_height=10)
        ),
        "narrow_outer_wraps_the_nested_box": (
            wrap.get("outcome") == "placed"
            and _near(wrap_row, content_height=20)
            and _near(
                _line(wrap_row, 0),
                text="AC",
                height=20,
                content_width=40,
                runs=[
                    {"text": "A", "x": 0, "font_size": 10, "width": 10, "y": 10},
                    {"text": "C", "x": 30, "font_size": 10, "width": 10, "y": 10},
                ],
                atoms=[{"id": "atom", "x": 10, "width": 20}],
            )
            and _near(wrap_atom, x=10, y=0, content_width=20, content_height=20)
            and _near(
                _line(wrap_atom, 0),
                text="W",
                x=10,
                y=0,
                height=10,
                content_width=10,
                runs=[{"text": "W", "x": 10, "font_size": 10, "width": 10}],
            )
            and _near(
                _line(wrap_atom, 1),
                text="",
                x=10,
                y=10,
                height=10,
                content_width=20,
                atoms=[{"id": "inner", "x": 10, "width": 20}],
            )
            and _near(wrap_inner, x=10, y=10, content_width=20, content_height=10)
            and _near(_line(wrap_inner, 0), text="BB", x=10, y=10, height=10, content_width=20)
            and _near(wrap_next, y=20)
        ),
        "specified_inner_width_widens_the_outer_box": (
            wide.get("outcome") == "placed"
            and _near(wide_row, content_height=10)
            and _near(
                _line(wide_row, 0),
                text="AC",
                content_width=60,
                runs=[
                    {"text": "A", "x": 0, "font_size": 10, "width": 10},
                    {"text": "C", "x": 50, "font_size": 10, "width": 10},
                ],
                atoms=[{"id": "atom", "x": 10, "width": 40}],
            )
            and _near(wide_atom, x=10, y=0, content_width=40, content_height=10)
            and _near(wide_inner, x=10, y=0, content_width=40, content_height=10)
            and _near(_line(wide_inner, 0), text="BB", x=10, y=0, height=10, content_width=20)
            and _near(wide_next, y=10)
        ),
        "mixed_font_beside_the_nested_box_is_rejected": _rejected(mixed),
        "right_float_is_rejected": _rejected(right),
        "positioned_content_is_rejected": _rejected(absolute),
    }
    observed = {
        "fit": {
            "outcome": fit.get("outcome"),
            "reason": fit.get("reason"),
            "atom": _spot(fit_atom),
            "inner": _spot(fit_inner),
            "q_x": None
            if _line(fit_atom, 0) is None or not isinstance(_line(fit_atom, 0).get("runs"), list)
            else _line(fit_atom, 0)["runs"][1].get("x"),
            "c_x": None
            if _line(fit_row, 0) is None or not isinstance(_line(fit_row, 0).get("runs"), list)
            else _line(fit_row, 0)["runs"][1].get("x"),
            "next_y": None if fit_next is None else fit_next.get("y"),
        },
        "wrap": {
            "outcome": wrap.get("outcome"),
            "reason": wrap.get("reason"),
            "atom": _spot(wrap_atom),
            "inner": _spot(wrap_inner),
            "word_y": None
            if _line(wrap_row, 0) is None or not isinstance(_line(wrap_row, 0).get("runs"), list)
            else _line(wrap_row, 0)["runs"][0].get("y"),
            "next_y": None if wrap_next is None else wrap_next.get("y"),
        },
        "wide": {
            "outcome": wide.get("outcome"),
            "reason": wide.get("reason"),
            "atom": _spot(wide_atom),
            "inner": _spot(wide_inner),
            "line_w": None if _line(wide_inner, 0) is None else _line(wide_inner, 0).get("content_width"),
            "next_y": None if wide_next is None else wide_next.get("y"),
        },
        "mixed": {"outcome": mixed.get("outcome"), "reason": mixed.get("reason")},
        "right": {"outcome": right.get("outcome"), "reason": right.get("reason")},
        "absolute": {"outcome": absolute.get("outcome"), "reason": absolute.get("reason")},
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
