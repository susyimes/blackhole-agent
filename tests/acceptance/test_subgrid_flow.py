"""Place a nested column subgrid on the parent tracks it shares.

A 100px and 150px parent grid with a 50px gutter keeps those tracks when the
subgrid omits column-gap, and pulls the children together when that gap is
zero. A line past a single spanned column clamps onto that column. A subgrid
that is not a grid item, and a row subgrid, are invalid. A plain grid item
stays on its own column.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit.
"""

from __future__ import annotations

import json

_PAGE = (
    '<div id="page"><div id="shell"><div id="nested"><div id="left"></div>'
    '<div id="right"></div></div></div><p id="next">Z</p></div>'
)
_SHARED = (
    "#page { font-size: 10px; line-height: 10px; }"
    "#shell { display: grid; width: 300px; grid-template-columns: 100px 150px;"
    " column-gap: 50px; grid-auto-rows: 20px; }"
    "#nested { display: grid; grid-column: span 2; grid-template-columns: subgrid; }"
    "#left { height: 20px; }"
    "#right { height: 20px; }"
)
_JOINED = _SHARED + "#nested { column-gap: 0px; }"
_CLAMP = (
    '<div id="page"><div id="shell"><div id="nested"><div id="left"></div>'
    "</div></div></div>"
)
_CLAMP_CSS = (
    "#page { font-size: 10px; line-height: 10px; }"
    "#shell { display: grid; width: 80px; grid-template-columns: 80px;"
    " column-gap: 0px; grid-auto-rows: 20px; }"
    "#nested { display: grid; grid-template-columns: subgrid; }"
    "#left { grid-column: 2 / span 3; height: 20px; }"
)
_ORPHAN = (
    '<div id="shell"></div>',
    "#shell { display: grid; width: 100px; grid-template-columns: subgrid; grid-auto-rows: 20px; }",
)
_ROW = (
    '<div id="shell"><div id="cell"></div></div>',
    "#shell { display: grid; width: 40px; grid-template-columns: 40px;"
    " grid-template-rows: subgrid; }"
    "#cell { height: 10px; }",
)
_PLAIN = (
    '<div id="page"><div id="shell"><div id="cell"></div></div><p id="next">Z</p></div>',
    "#page { font-size: 10px; line-height: 10px; }"
    "#shell { display: grid; width: 80px; grid-template-columns: 40px 40px;"
    " column-gap: 0px; grid-auto-rows: 10px; }"
    "#cell { height: 10px; }",
)


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


def _lay(layout, markup: str, stylesheet: str) -> dict[str, object]:
    try:
        placed = layout(markup, stylesheet, viewport_width=400)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without the walk still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    joined = _lay(layout_normal_flow, _PAGE, _JOINED)
    shared = _lay(layout_normal_flow, _PAGE, _SHARED)
    clamped = _lay(layout_normal_flow, _CLAMP, _CLAMP_CSS)
    orphan = _lay(layout_normal_flow, _ORPHAN[0], _ORPHAN[1])
    row = _lay(layout_normal_flow, _ROW[0], _ROW[1])
    plain = _lay(layout_normal_flow, _PLAIN[0], _PLAIN[1])

    def take(result: dict[str, object], ident: str) -> dict[str, object] | None:
        return _box(result.get("boxes"), ident)

    observed: dict[str, object] = {
        "joined_outcome": joined.get("outcome"),
        "joined_reason": joined.get("reason"),
        "joined_left": _placed(take(joined, "left")),
        "joined_right": _placed(take(joined, "right")),
        "joined_nested": _placed(take(joined, "nested")),
        "joined_next": _placed(take(joined, "next")),
        "shared_outcome": shared.get("outcome"),
        "shared_reason": shared.get("reason"),
        "shared_left": _placed(take(shared, "left")),
        "shared_right": _placed(take(shared, "right")),
        "shared_next": _placed(take(shared, "next")),
        "clamp_outcome": clamped.get("outcome"),
        "clamp_reason": clamped.get("reason"),
        "clamp_left": _placed(take(clamped, "left")),
        "orphan_outcome": orphan.get("outcome"),
        "orphan_reason": orphan.get("reason"),
        "row_outcome": row.get("outcome"),
        "row_reason": row.get("reason"),
        "plain_outcome": plain.get("outcome"),
        "plain_reason": plain.get("reason"),
        "plain_cell": _placed(take(plain, "cell")),
        "plain_next": _placed(take(plain, "next")),
    }
    checks = {
        "zero_gap_pulls_children_across_the_parent_gutter": (
            joined.get("outcome") == "placed"
            and _near(take(joined, "left"), x=0, y=0, content_width=125, content_height=20)
            and _near(take(joined, "right"), x=125, y=0, content_width=175, content_height=20)
            and _near(take(joined, "nested"), x=0, y=0, content_width=300, content_height=20)
            and isinstance(take(joined, "next"), dict)
            and take(joined, "next").get("y") == 20
        ),
        "omitted_gap_keeps_each_child_on_its_parent_track": (
            shared.get("outcome") == "placed"
            and _near(take(shared, "left"), x=0, y=0, content_width=100, content_height=20)
            and _near(take(shared, "right"), x=150, y=0, content_width=150, content_height=20)
            and isinstance(take(shared, "next"), dict)
            and take(shared, "next").get("y") == 20
        ),
        "line_past_the_spanned_column_clamps": (
            clamped.get("outcome") == "placed"
            and _near(take(clamped, "left"), x=0, y=0, content_width=80, content_height=20)
        ),
        "subgrid_outside_a_grid_is_invalid": (
            orphan.get("outcome") == "invalid" and orphan.get("reason") == "subgrid is not a grid item"
        ),
        "row_subgrid_is_invalid": (
            row.get("outcome") == "invalid" and row.get("reason") == "row subgrid is unsupported"
        ),
        "plain_grid_item_stays_on_its_column": (
            plain.get("outcome") == "placed"
            and _near(take(plain, "cell"), x=0, y=0, content_width=40, content_height=10)
            and isinstance(take(plain, "next"), dict)
            and take(plain, "next").get("y") == 10
        ),
    }
    observed["checks"] = checks
    return all(checks.values()), observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
