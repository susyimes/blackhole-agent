"""Place a grid's tracks in normal flow and start the next block after them.

A 10px item in a 40px column stays at the track start, and the next item
begins after that column plus the 20px gutter. Three items in a 200px grid
with only two columns wrap to the next row instead of using the leftover
inline space. A span of two columns occupies both tracks and the gutter.
A 1fr column takes the content box left after a fixed column and the gutter.
An explicit second row keeps its height when no item is placed there.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree that still rejects display grid exits 0 with passed
false.
"""

from __future__ import annotations

import json
import sys

_PAIR = (
    '<div id="page"><div id="grid"><span id="a"></span><span id="b"></span></div>'
    '<p id="next">Z</p></div>'
)
_THREE = (
    '<div id="page"><div id="grid"><span id="a"></span><span id="b"></span>'
    '<span id="c"></span></div><p id="next">Z</p></div>'
)
_NARROW = """
#page { font-size: 10px; line-height: 10px; }
#grid { display: grid; width: 200px; grid-template-columns: 40px 40px; column-gap: 20px; grid-auto-rows: 10px; }
#a { width: 10px; height: 10px; }
#b { height: 10px; }
"""
_WRAP = """
#page { font-size: 10px; line-height: 10px; }
#grid { display: grid; width: 200px; grid-template-columns: 40px 40px; gap: 8px 20px; grid-auto-rows: 10px; }
"""
_SPAN = """
#page { font-size: 10px; line-height: 10px; }
#grid { display: grid; width: 200px; grid-template-columns: 40px 40px; column-gap: 20px; grid-auto-rows: 10px; }
#a { grid-column: span 2; }
"""
_FLEXIBLE = """
#page { font-size: 10px; line-height: 10px; }
#grid { display: grid; width: 100px; grid-template-columns: 40px 1fr; column-gap: 20px; grid-auto-rows: 10px; }
"""
_ROWS = """
#page { font-size: 10px; line-height: 10px; }
#grid { display: grid; width: 80px; grid-template-columns: 40px 40px; grid-template-rows: 12px 18px; column-gap: 0px; row-gap: 4px; }
"""
_ZERO = """
#page { font-size: 10px; line-height: 10px; }
#grid { display: grid; width: 100px; grid-template-columns: 40px 40px; gap: 0px; grid-auto-rows: 10px; }
"""


def _box(boxes: object, ident: str) -> dict[str, object] | None:
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if isinstance(item, dict) and item.get("id") == ident:
            return item
    return None


def _near(item: dict[str, object] | None, **expected: object) -> bool:
    if item is None:
        return False
    return all(item.get(key) == value for key, value in expected.items())


def _placed(box: dict[str, object] | None) -> dict[str, object] | None:
    if box is None:
        return None
    return {
        "x": box.get("x"),
        "y": box.get("y"),
        "content_width": box.get("content_width"),
        "content_height": box.get("content_height"),
    }


def _lay(layout, markup: str, stylesheet: str, width: int) -> dict[str, object]:
    try:
        placed = layout(markup, stylesheet, viewport_width=width)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without placement still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    narrow = _lay(layout_normal_flow, _PAIR, _NARROW, 240)
    wrapped = _lay(layout_normal_flow, _THREE, _WRAP, 240)
    spanned = _lay(layout_normal_flow, _PAIR, _SPAN, 240)
    flexible = _lay(layout_normal_flow, _PAIR, _FLEXIBLE, 240)
    rows = _lay(layout_normal_flow, _PAIR, _ROWS, 240)
    zero = _lay(layout_normal_flow, _PAIR, _ZERO, 240)

    def take(result: dict[str, object], ident: str) -> dict[str, object] | None:
        return _box(result.get("boxes"), ident)

    observed: dict[str, object] = {
        "narrow_outcome": narrow.get("outcome"),
        "narrow_reason": narrow.get("reason"),
        "narrow_a": _placed(take(narrow, "a")),
        "narrow_b": _placed(take(narrow, "b")),
        "narrow_next": _placed(take(narrow, "next")),
        "wrap_outcome": wrapped.get("outcome"),
        "wrap_reason": wrapped.get("reason"),
        "wrap_a": _placed(take(wrapped, "a")),
        "wrap_b": _placed(take(wrapped, "b")),
        "wrap_c": _placed(take(wrapped, "c")),
        "wrap_grid": _placed(take(wrapped, "grid")),
        "wrap_next": _placed(take(wrapped, "next")),
        "span_outcome": spanned.get("outcome"),
        "span_reason": spanned.get("reason"),
        "span_a": _placed(take(spanned, "a")),
        "span_b": _placed(take(spanned, "b")),
        "span_next": _placed(take(spanned, "next")),
        "flex_outcome": flexible.get("outcome"),
        "flex_reason": flexible.get("reason"),
        "flex_a": _placed(take(flexible, "a")),
        "flex_b": _placed(take(flexible, "b")),
        "rows_outcome": rows.get("outcome"),
        "rows_reason": rows.get("reason"),
        "rows_a": _placed(take(rows, "a")),
        "rows_b": _placed(take(rows, "b")),
        "rows_grid": _placed(take(rows, "grid")),
        "rows_next": _placed(take(rows, "next")),
        "zero_outcome": zero.get("outcome"),
        "zero_reason": zero.get("reason"),
        "zero_a": _placed(take(zero, "a")),
        "zero_b": _placed(take(zero, "b")),
    }
    checks = {
        "narrow_item_stays_on_its_track": (
            narrow.get("outcome") == "placed"
            and _near(take(narrow, "a"), x=0, y=0, content_width=10, content_height=10)
            and _near(take(narrow, "b"), x=60, y=0, content_width=40, content_height=10)
            and isinstance(take(narrow, "next"), dict)
            and take(narrow, "next").get("y") == 10
        ),
        "third_item_wraps_despite_leftover_inline_space": (
            wrapped.get("outcome") == "placed"
            and _near(take(wrapped, "a"), x=0, y=0, content_width=40, content_height=10)
            and _near(take(wrapped, "b"), x=60, y=0, content_width=40, content_height=10)
            and _near(take(wrapped, "c"), x=0, y=18, content_width=40, content_height=10)
            and _near(take(wrapped, "grid"), content_width=200, content_height=28)
            and isinstance(take(wrapped, "next"), dict)
            and take(wrapped, "next").get("y") == 28
        ),
        "span_covers_both_tracks_and_the_gutter": (
            spanned.get("outcome") == "placed"
            and _near(take(spanned, "a"), x=0, y=0, content_width=100, content_height=10)
            and _near(take(spanned, "b"), x=0, y=10, content_width=40, content_height=10)
            and isinstance(take(spanned, "next"), dict)
            and take(spanned, "next").get("y") == 20
        ),
        "flexible_column_grows_after_the_gutter": (
            flexible.get("outcome") == "placed"
            and _near(take(flexible, "a"), x=0, y=0, content_width=40, content_height=10)
            and _near(take(flexible, "b"), x=60, y=0, content_width=40, content_height=10)
        ),
        "empty_explicit_row_keeps_its_height": (
            rows.get("outcome") == "placed"
            and _near(take(rows, "a"), x=0, y=0, content_width=40, content_height=12)
            and _near(take(rows, "b"), x=40, y=0, content_width=40, content_height=12)
            and _near(take(rows, "grid"), content_width=80, content_height=34)
            and isinstance(take(rows, "next"), dict)
            and take(rows, "next").get("y") == 34
        ),
        "zero_gap_keeps_tracks_adjacent": (
            zero.get("outcome") == "placed"
            and _near(take(zero, "a"), x=0, y=0, content_width=40, content_height=10)
            and _near(take(zero, "b"), x=40, y=0, content_width=40, content_height=10)
        ),
    }
    observed["checks"] = checks
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
