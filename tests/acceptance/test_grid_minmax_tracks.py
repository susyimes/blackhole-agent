"""Size normal-flow grid tracks from minmax floors and ceilings.

A length ceiling is filled before a flexible sibling takes what remains.
A flexible ceiling keeps a floor that already exceeds its share, and a
ceiling below its floor is ignored. A definite block size does the same
for rows. An indefinite block size uses the length ceiling. A flexible
floor is rejected, and a flexible row without a definite block size stays
rejected. The following block stays under the grid.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree that still rejects minmax exits 0.
"""

from __future__ import annotations

import json

_PAIR = '<div id="page"><div id="grid"><div id="a"></div><div id="b"></div></div><div id="after"></div></div>'
_ONE = '<div id="page"><div id="grid"><div id="a"></div></div><div id="after"></div></div>'
_FONT = "#page { font-size: 10px; line-height: 10px; }\n"
_AFTER = "#after { height: 8px; }\n"


def _columns(width: int, tracks: str, extra: str = "") -> str:
    return (
        _FONT
        + f"#grid {{ display: grid; width: {width}px; grid-template-columns: {tracks}; "
        + "grid-template-rows: 10px; "
        + extra
        + "}\n"
        + _AFTER
    )


def _rows(height: int | None, tracks: str) -> str:
    block = "" if height is None else f" height: {height}px;"
    return (
        _FONT
        + "#grid { display: grid; width: 40px;"
        + block
        + f" grid-template-columns: 40px; grid-template-rows: {tracks}; }}\n"
        + _AFTER
    )


_CEILING = _columns(200, "minmax(40px, 80px) 1fr")
_FLOOR = _columns(100, "minmax(80px, 1fr) 1fr")
_SHARE = _columns(200, "minmax(40px, 1fr) 1fr")
_INVERTED = _columns(200, "minmax(80px, 40px) 1fr")
_GAP = _columns(210, "minmax(40px, 80px) 1fr", "column-gap: 10px; ")
_TIGHT = _columns(30, "minmax(40px, 80px) 1fr")
_SPAN = _columns(200, "minmax(40px, 80px) 20px") + "#a { grid-column: span 2; }\n"
_NAMED = _columns(200, "[start] minmax(40px, 80px) [end] 1fr") + "#a { grid-column: start / end; }\n"
_ROWS = _rows(100, "minmax(20px, 40px) 1fr")
_ROW_FLOOR = _rows(100, "minmax(80px, 1fr) 1fr")
_ROW_INVERTED = _rows(200, "minmax(80px, 40px) 1fr")
_AUTO_ROW = _rows(None, "minmax(20px, 40px)")
_BAD_FLOOR = _columns(200, "minmax(1fr, 40px) 1fr")
_BAD_ROW = _rows(None, "minmax(20px, 1fr)")
_PLAIN = _columns(100, "40px 1fr")


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
        placed = layout(markup, stylesheet, viewport_width=240)
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

    ceiling = _lay(layout_normal_flow, _PAIR, _CEILING)
    floor = _lay(layout_normal_flow, _PAIR, _FLOOR)
    share = _lay(layout_normal_flow, _PAIR, _SHARE)
    inverted = _lay(layout_normal_flow, _PAIR, _INVERTED)
    gap = _lay(layout_normal_flow, _PAIR, _GAP)
    tight = _lay(layout_normal_flow, _PAIR, _TIGHT)
    span = _lay(layout_normal_flow, _ONE, _SPAN)
    named = _lay(layout_normal_flow, _ONE, _NAMED)
    rows = _lay(layout_normal_flow, _PAIR, _ROWS)
    row_floor = _lay(layout_normal_flow, _PAIR, _ROW_FLOOR)
    row_inverted = _lay(layout_normal_flow, _PAIR, _ROW_INVERTED)
    auto_row = _lay(layout_normal_flow, _ONE, _AUTO_ROW)
    bad_floor = _lay(layout_normal_flow, _PAIR, _BAD_FLOOR)
    bad_row = _lay(layout_normal_flow, _ONE, _BAD_ROW)
    plain = _lay(layout_normal_flow, _PAIR, _PLAIN)
    observed: dict[str, object] = {
        "ceiling_outcome": ceiling.get("outcome"),
        "ceiling_reason": ceiling.get("reason"),
        "ceiling_a": _view(ceiling, "a"),
        "ceiling_b": _view(ceiling, "b"),
        "ceiling_after": _view(ceiling, "after"),
        "floor_outcome": floor.get("outcome"),
        "floor_a": _view(floor, "a"),
        "floor_b": _view(floor, "b"),
        "share_outcome": share.get("outcome"),
        "share_a": _view(share, "a"),
        "share_b": _view(share, "b"),
        "inverted_outcome": inverted.get("outcome"),
        "inverted_a": _view(inverted, "a"),
        "inverted_b": _view(inverted, "b"),
        "gap_outcome": gap.get("outcome"),
        "gap_a": _view(gap, "a"),
        "gap_b": _view(gap, "b"),
        "tight_outcome": tight.get("outcome"),
        "tight_reason": tight.get("reason"),
        "tight_grid": _view(tight, "grid"),
        "tight_a": _view(tight, "a"),
        "tight_b": _view(tight, "b"),
        "tight_after": _view(tight, "after"),
        "span_outcome": span.get("outcome"),
        "span_a": _view(span, "a"),
        "named_outcome": named.get("outcome"),
        "named_reason": named.get("reason"),
        "named_a": _view(named, "a"),
        "rows_outcome": rows.get("outcome"),
        "rows_a": _view(rows, "a"),
        "rows_b": _view(rows, "b"),
        "rows_grid": _view(rows, "grid"),
        "rows_after": _view(rows, "after"),
        "row_floor_outcome": row_floor.get("outcome"),
        "row_floor_a": _view(row_floor, "a"),
        "row_floor_b": _view(row_floor, "b"),
        "row_floor_after": _view(row_floor, "after"),
        "row_inverted_a": _view(row_inverted, "a"),
        "row_inverted_b": _view(row_inverted, "b"),
        "row_inverted_after": _view(row_inverted, "after"),
        "auto_row_outcome": auto_row.get("outcome"),
        "auto_row_a": _view(auto_row, "a"),
        "auto_row_grid": _view(auto_row, "grid"),
        "auto_row_after": _view(auto_row, "after"),
        "bad_floor_outcome": bad_floor.get("outcome"),
        "bad_floor_reason": bad_floor.get("reason"),
        "bad_row_outcome": bad_row.get("outcome"),
        "bad_row_reason": bad_row.get("reason"),
        "plain_outcome": plain.get("outcome"),
        "plain_a": _view(plain, "a"),
        "plain_b": _view(plain, "b"),
    }
    checks = {
        "ceiling_fills_before_the_flexible_sibling": (
            ceiling.get("outcome") == "placed"
            and _near(_box(ceiling.get("boxes"), "a"), x=0, y=0, content_width=80, content_height=10)
            and _near(_box(ceiling.get("boxes"), "b"), x=80, y=0, content_width=120, content_height=10)
            and _near(_box(ceiling.get("boxes"), "after"), y=10)
        ),
        "flexible_ceiling_keeps_a_floor_past_its_share": (
            floor.get("outcome") == "placed"
            and _near(_box(floor.get("boxes"), "a"), x=0, content_width=80)
            and _near(_box(floor.get("boxes"), "b"), x=80, content_width=20)
        ),
        "equal_shares_stay_when_the_floor_fits": (
            share.get("outcome") == "placed"
            and _near(_box(share.get("boxes"), "a"), x=0, content_width=100)
            and _near(_box(share.get("boxes"), "b"), x=100, content_width=100)
        ),
        "ceiling_below_the_floor_is_ignored": (
            inverted.get("outcome") == "placed"
            and _near(_box(inverted.get("boxes"), "a"), content_width=80)
            and _near(_box(inverted.get("boxes"), "b"), x=80, content_width=120)
        ),
        "gap_sits_between_the_ceiling_and_the_remainder": (
            gap.get("outcome") == "placed"
            and _near(_box(gap.get("boxes"), "a"), x=0, content_width=80)
            and _near(_box(gap.get("boxes"), "b"), x=90, content_width=120)
        ),
        "tight_container_keeps_the_floor_and_its_own_width": (
            tight.get("outcome") == "placed"
            and _near(_box(tight.get("boxes"), "grid"), content_width=30)
            and _near(_box(tight.get("boxes"), "a"), x=0, content_width=40)
            and _near(_box(tight.get("boxes"), "b"), x=40, content_width=0)
            and _near(_box(tight.get("boxes"), "after"), y=10)
        ),
        "span_uses_the_ceiling_instead_of_the_free_space": (
            span.get("outcome") == "placed"
            and _near(_box(span.get("boxes"), "a"), x=0, content_width=100)
            and _near(_box(span.get("boxes"), "after"), y=10)
        ),
        "named_line_selects_the_minmax_column": (
            named.get("outcome") == "placed"
            and _near(_box(named.get("boxes"), "a"), x=0, content_width=80)
        ),
        "definite_rows_fill_the_ceiling_then_the_remainder": (
            rows.get("outcome") == "placed"
            and _near(_box(rows.get("boxes"), "grid"), content_height=100)
            and _near(_box(rows.get("boxes"), "a"), y=0, content_height=40, content_width=40)
            and _near(_box(rows.get("boxes"), "b"), y=40, content_height=60)
            and _near(_box(rows.get("boxes"), "after"), y=100)
        ),
        "row_floor_past_its_share_stays": (
            row_floor.get("outcome") == "placed"
            and _near(_box(row_floor.get("boxes"), "a"), y=0, content_height=80)
            and _near(_box(row_floor.get("boxes"), "b"), y=80, content_height=20)
            and _near(_box(row_floor.get("boxes"), "after"), y=100)
        ),
        "row_ceiling_below_the_floor_is_ignored": (
            row_inverted.get("outcome") == "placed"
            and _near(_box(row_inverted.get("boxes"), "a"), content_height=80)
            and _near(_box(row_inverted.get("boxes"), "b"), y=80, content_height=120)
            and _near(_box(row_inverted.get("boxes"), "after"), y=200)
        ),
        "indefinite_row_uses_the_length_ceiling": (
            auto_row.get("outcome") == "placed"
            and _near(_box(auto_row.get("boxes"), "grid"), content_height=40)
            and _near(_box(auto_row.get("boxes"), "a"), y=0, content_height=40)
            and _near(_box(auto_row.get("boxes"), "after"), y=40)
        ),
        "flexible_floor_is_rejected": (
            bad_floor.get("outcome") == "invalid" and bool(bad_floor.get("reason"))
        ),
        "flexible_row_without_a_definite_block_size_is_rejected": (
            bad_row.get("outcome") == "invalid" and bool(bad_row.get("reason"))
        ),
        "plain_lengths_still_share_with_a_flexible_track": (
            plain.get("outcome") == "placed"
            and _near(_box(plain.get("boxes"), "a"), x=0, content_width=40)
            and _near(_box(plain.get("boxes"), "b"), x=40, content_width=60)
            and _near(_box(plain.get("boxes"), "after"), y=10)
        ),
    }
    observed["checks"] = {name: bool(value) for name, value in checks.items()}
    return all(checks.values()), observed


def main() -> int:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - the probe must exit 0 either way
        passed, observed = False, {"error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps({"passed": bool(passed), "observed": observed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
