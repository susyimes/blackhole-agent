"""Assign colspan and rowspan slots in a normal-flow table.

A colspan=2 cell whose text is wider than the two columns below it widens
both columns. A rowspan=2 cell occupies the next row's first slot, so the
cell in that row starts in the next column and the span box covers both
row heights. A colspan that would cover an occupied slot is rejected, and
colspan=0 is rejected. The following block starts under the table.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree that still rejects unequal rows exits 0 with passed
false.
"""

from __future__ import annotations

import json
import sys

_CSS = """
#page { font-size: 10px; line-height: 10px; }
#table { display: table; }
#r1, #r2 { display: table-row; }
#wide, #a, #b, #tall, #top, #low, #c { display: table-cell; }
"""
_FIXED_CSS = """
#page { font-size: 10px; line-height: 10px; }
#table { display: table; table-layout: fixed; width: 80px; }
#r1, #r2 { display: table-row; }
#wide { display: table-cell; width: 80px; }
#a, #b { display: table-cell; }
"""
_COLLAPSE_CSS = """
#page { font-size: 10px; line-height: 10px; }
#table { display: table; border-collapse: collapse; }
#r1, #r2 { display: table-row; }
#wide, #a, #b { display: table-cell; border-width: 4px; border-style: solid; }
"""
_WIDE = (
    '<div id="page"><div id="table"><div id="r1"><div id="wide" colspan="2">AAAA BBBB</div></div>'
    '<div id="r2"><div id="a">AA</div><div id="b">BB</div></div></div><p id="next">Z</p></div>'
)
_TALL = (
    '<div id="page"><div id="table"><div id="r1"><div id="tall" rowspan="2">AA</div>'
    '<div id="top">BBBB</div></div><div id="r2"><div id="low">C</div></div></div>'
    '<p id="next">Z</p></div>'
)
_SHORT = (
    '<div id="page"><div id="table"><div id="r1"><div id="a">AA</div></div>'
    '<div id="r2"><div id="b">B</div><div id="c">CCC</div></div></div><p id="next">Z</p></div>'
)
_FIXED = (
    '<div id="page"><div id="table"><div id="r1"><div id="wide" colspan="2">ZZ</div></div>'
    '<div id="r2"><div id="a">A</div><div id="b">B</div></div></div><p id="next">Z</p></div>'
)
_OVERLAP = (
    '<div id="page"><div id="table"><div id="r1"><div id="a">A</div>'
    '<div id="b" rowspan="2">B</div></div><div id="r2"><div id="wide" colspan="2">CC</div>'
    "</div></div></div>"
)
_ZERO = (
    '<div id="page"><div id="table"><div id="r1"><div id="a" colspan="0">AA</div>'
    '<div id="b">BB</div></div><div id="r2"><div id="c">CC</div><div id="a2">DD</div>'
    "</div></div></div>"
)
_COLLAPSE = _WIDE


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


def _lay(layout, markup: str, stylesheet: str) -> dict[str, object]:
    try:
        placed = layout(markup, stylesheet, viewport_width=200)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def _view(result: dict[str, object], ident: str) -> dict[str, object] | None:
    box = _box(result.get("boxes"), ident)
    if box is None:
        return None
    return {
        "x": box.get("x"),
        "y": box.get("y"),
        "content_width": box.get("content_width"),
        "content_height": box.get("content_height"),
    }


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without placement still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    wide = _lay(layout_normal_flow, _WIDE, _CSS)
    tall = _lay(layout_normal_flow, _TALL, _CSS)
    short = _lay(layout_normal_flow, _SHORT, _CSS)
    fixed = _lay(layout_normal_flow, _FIXED, _FIXED_CSS)
    overlap = _lay(layout_normal_flow, _OVERLAP, _CSS)
    zero = _lay(layout_normal_flow, _ZERO, _CSS)
    collapsed = _lay(layout_normal_flow, _COLLAPSE, _COLLAPSE_CSS)

    def take(result: dict[str, object], ident: str) -> dict[str, object] | None:
        return _box(result.get("boxes"), ident)

    observed: dict[str, object] = {
        "wide_outcome": wide.get("outcome"),
        "wide_reason": wide.get("reason"),
        "wide": _view(wide, "wide"),
        "wide_a": _view(wide, "a"),
        "wide_b": _view(wide, "b"),
        "wide_next_y": None if take(wide, "next") is None else take(wide, "next").get("y"),
        "tall_outcome": tall.get("outcome"),
        "tall_reason": tall.get("reason"),
        "tall": _view(tall, "tall"),
        "top": _view(tall, "top"),
        "low": _view(tall, "low"),
        "tall_next_y": None if take(tall, "next") is None else take(tall, "next").get("y"),
        "short_outcome": short.get("outcome"),
        "short_reason": short.get("reason"),
        "short_a": _view(short, "a"),
        "short_b": _view(short, "b"),
        "short_c": _view(short, "c"),
        "short_next_y": None if take(short, "next") is None else take(short, "next").get("y"),
        "fixed_outcome": fixed.get("outcome"),
        "fixed_reason": fixed.get("reason"),
        "fixed_wide": _view(fixed, "wide"),
        "fixed_a": _view(fixed, "a"),
        "fixed_b": _view(fixed, "b"),
        "fixed_next_y": None if take(fixed, "next") is None else take(fixed, "next").get("y"),
        "overlap_outcome": overlap.get("outcome"),
        "overlap_reason": overlap.get("reason"),
        "zero_outcome": zero.get("outcome"),
        "zero_reason": zero.get("reason"),
        "collapsed_outcome": collapsed.get("outcome"),
        "collapsed_reason": collapsed.get("reason"),
        "collapsed_wide": _view(collapsed, "wide"),
        "collapsed_a": _view(collapsed, "a"),
        "collapsed_b": _view(collapsed, "b"),
        "collapsed_next_y": None if take(collapsed, "next") is None else take(collapsed, "next").get("y"),
    }
    checks = {
        "colspan_spreads_max_content_across_both_columns": (
            wide.get("outcome") == "placed"
            and _near(take(wide, "wide"), x=0, y=0, content_width=90, content_height=10)
            and _near(take(wide, "a"), x=0, y=10, content_width=45, content_height=10)
            and _near(take(wide, "b"), x=45, y=10, content_width=45, content_height=10)
            and _near(take(wide, "next"), y=20)
        ),
        "rowspan_occupies_the_next_slot_and_covers_both_rows": (
            tall.get("outcome") == "placed"
            and _near(take(tall, "tall"), x=0, y=0, content_width=20, content_height=20)
            and _near(take(tall, "top"), x=20, y=0, content_width=40, content_height=10)
            and _near(take(tall, "low"), x=20, y=10, content_width=40, content_height=10)
            and _near(take(tall, "next"), y=20)
        ),
        "a_short_row_opens_the_next_column": (
            short.get("outcome") == "placed"
            and _near(take(short, "a"), x=0, y=0, content_width=20, content_height=10)
            and _near(take(short, "b"), x=0, y=10, content_width=20, content_height=10)
            and _near(take(short, "c"), x=20, y=10, content_width=30, content_height=10)
            and _near(take(short, "next"), y=20)
        ),
        "fixed_colspan_splits_its_width_across_the_span": (
            fixed.get("outcome") == "placed"
            and _near(take(fixed, "wide"), x=0, y=0, content_width=80, content_height=10)
            and _near(take(fixed, "a"), x=0, y=10, content_width=40, content_height=10)
            and _near(take(fixed, "b"), x=40, y=10, content_width=40, content_height=10)
            and _near(take(fixed, "next"), y=20)
        ),
        "overlap_is_rejected": overlap.get("outcome") == "invalid",
        "zero_span_is_rejected": zero.get("outcome") == "invalid",
        "collapsed_span_includes_the_internal_border": (
            collapsed.get("outcome") == "placed"
            and _near(take(collapsed, "wide"), x=0, y=0, content_width=94, content_height=10)
            and _near(take(collapsed, "a"), x=0, y=16, content_width=45, content_height=10)
            and _near(take(collapsed, "b"), x=51, y=16, content_width=45, content_height=10)
            and _near(take(collapsed, "next"), y=32)
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
