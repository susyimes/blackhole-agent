"""Place text runs inside a flex container as anonymous flex items.

A word between items takes its own max-content slot. Whitespace-only text
does not. display:contents joins the surrounding text. order 0 paints a
following run before a later item. Preserved spaces keep their width. A
preserved newline stacks that item. A vertical flex container and a
different font stay invalid.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit.
"""

from __future__ import annotations

import json
import sys

_ROW = (
    '<div id="page"><div id="row">Hi<span id="item"></span>Yo</div>'
    '<p id="next">Z</p></div>'
)
_ROW_CSS = """
#page { font-size: 10px; line-height: 10px; }
#row { display: flex; }
#item { flex: 0 0 30px; }
#next { height: 10px; }
"""
_GAP = '<div id="row"><span id="a">A</span> <span id="b">B</span></div>'
_GAP_CSS = """
#row { display: flex; font-size: 10px; line-height: 10px; }
#a, #b { flex: none; }
"""
_MERGE = '<div id="row">AA<span id="hole">BB</span></div>'
_MERGE_CSS = """
#row { display: flex; font-size: 10px; line-height: 10px; }
#hole { display: contents; }
"""
_SPLIT = '<div id="row">AA<span id="hole"><b id="item"></b>BB</span></div>'
_SPLIT_CSS = """
#row { display: flex; font-size: 10px; line-height: 10px; }
#hole { display: contents; }
#item { flex: 0 0 30px; }
"""
_ORDER = '<div id="row"><span id="item"></span>Hi</div>'
_ORDER_CSS = """
#row { display: flex; font-size: 10px; line-height: 10px; }
#item { flex: 0 0 30px; order: 1; }
"""
_PRE = '<div id="pre">A  B</div>'
_PRE_CSS = """
#pre { display: flex; white-space: pre; font-size: 10px; line-height: 10px; }
"""
_COLUMN = (
    '<div id="page"><div id="col">Hi<span id="item"></span></div>'
    '<p id="next">Z</p></div>'
)
_COLUMN_CSS = """
#page { font-size: 10px; line-height: 10px; }
#col { display: flex; flex-direction: column; width: 80px; }
#item { flex: 0 0 20px; width: 40px; }
#next { height: 10px; }
"""
_BLANK = '<div id="page"><div id="row">   </div><p id="next">Z</p></div>'
_BLANK_CSS = """
#page { font-size: 10px; line-height: 10px; }
#row { display: flex; }
#next { height: 10px; }
"""
_VERTICAL = '<div id="vert">Hi</div>'
_VERTICAL_CSS = """
#vert { display: flex; writing-mode: vertical-rl; font-size: 10px; }
"""
_BREAK = "<div id=\"break\">A\nB</div>"
_BREAK_CSS = """
#break { display: flex; white-space: pre; font-size: 10px; line-height: 10px; }
"""
_FONT = '<div id="font">AA<span id="hole">BB</span></div>'
_FONT_CSS = """
#font { display: flex; font-size: 10px; line-height: 10px; }
#hole { display: contents; font-size: 20px; }
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


def _line_text(box: dict[str, object] | None) -> str:
    if not isinstance(box, dict):
        return ""
    lines = box.get("lines")
    if not isinstance(lines, list) or not lines or not isinstance(lines[0], dict):
        return ""
    return str(lines[0].get("text") or "")


def _anons(result: dict[str, object]) -> list[dict[str, object]]:
    boxes = result.get("boxes")
    if not isinstance(boxes, list):
        return []
    return [
        box
        for box in boxes
        if isinstance(box, dict) and str(box.get("id") or "").startswith("anon-")
    ]


def _anon_text(result: dict[str, object], text: str) -> dict[str, object] | None:
    found = [box for box in _anons(result) if _line_text(box) == text]
    if len(found) != 1:
        return None
    return found[0]


def _lay(layout, markup: str, stylesheet: str, width: int = 200) -> dict[str, object]:
    try:
        placed = layout(markup, stylesheet, viewport_width=width)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without the walk still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    row = _lay(layout_normal_flow, _ROW, _ROW_CSS)
    gap = _lay(layout_normal_flow, _GAP, _GAP_CSS)
    merged = _lay(layout_normal_flow, _MERGE, _MERGE_CSS)
    split = _lay(layout_normal_flow, _SPLIT, _SPLIT_CSS)
    ordered = _lay(layout_normal_flow, _ORDER, _ORDER_CSS)
    preserved = _lay(layout_normal_flow, _PRE, _PRE_CSS)
    column = _lay(layout_normal_flow, _COLUMN, _COLUMN_CSS)
    blank = _lay(layout_normal_flow, _BLANK, _BLANK_CSS)
    vertical = _lay(layout_normal_flow, _VERTICAL, _VERTICAL_CSS)
    broken = _lay(layout_normal_flow, _BREAK, _BREAK_CSS)
    font = _lay(layout_normal_flow, _FONT, _FONT_CSS)

    hi = _anon_text(row, "Hi")
    yo = _anon_text(row, "Yo")
    item = _box(row.get("boxes"), "item")
    nxt = _box(row.get("boxes"), "next")
    joined = _anons(merged)
    left = _anon_text(split, "AA")
    right = _anon_text(split, "BB")
    split_item = _box(split.get("boxes"), "item")
    lead = _anon_text(ordered, "Hi")
    ordered_item = _box(ordered.get("boxes"), "item")
    spaces = _anons(preserved)
    column_text = _anons(column)
    column_item = _box(column.get("boxes"), "item")
    column_next = _box(column.get("boxes"), "next")

    observed: dict[str, object] = {
        "row_outcome": row.get("outcome"),
        "row_reason": row.get("reason"),
        "hi": _placed(hi),
        "item": _placed(item),
        "yo": _placed(yo),
        "next": _placed(nxt),
        "gap_outcome": gap.get("outcome"),
        "gap_reason": gap.get("reason"),
        "gap_a": _placed(_box(gap.get("boxes"), "a")),
        "gap_b": _placed(_box(gap.get("boxes"), "b")),
        "gap_anons": len(_anons(gap)),
        "merge_outcome": merged.get("outcome"),
        "merge_reason": merged.get("reason"),
        "merge_text": _line_text(joined[0]) if len(joined) == 1 else None,
        "merge_box": _placed(joined[0]) if len(joined) == 1 else None,
        "merge_anons": len(joined),
        "split_outcome": split.get("outcome"),
        "split_aa": _placed(left),
        "split_item": _placed(split_item),
        "split_bb": _placed(right),
        "order_outcome": ordered.get("outcome"),
        "order_hi": _placed(lead),
        "order_item": _placed(ordered_item),
        "pre_outcome": preserved.get("outcome"),
        "pre_reason": preserved.get("reason"),
        "pre_text": _line_text(spaces[0]) if len(spaces) == 1 else None,
        "pre_box": _placed(spaces[0]) if len(spaces) == 1 else None,
        "column_outcome": column.get("outcome"),
        "column_reason": column.get("reason"),
        "column_text": _placed(column_text[0]) if len(column_text) == 1 else None,
        "column_item": _placed(column_item),
        "column_next": _placed(column_next),
        "blank_outcome": blank.get("outcome"),
        "blank_reason": blank.get("reason"),
        "blank_row": _placed(_box(blank.get("boxes"), "row")),
        "blank_next": _placed(_box(blank.get("boxes"), "next")),
        "blank_anons": len(_anons(blank)),
        "vertical_outcome": vertical.get("outcome"),
        "vertical_reason": vertical.get("reason"),
        "break_outcome": broken.get("outcome"),
        "break_reason": broken.get("reason"),
        "break_box": _placed(_anons(broken)[0]) if len(_anons(broken)) == 1 else None,
        "break_lines": [
            {"text": line.get("text"), "y": line.get("y"), "height": line.get("height")}
            for line in (_anons(broken)[0].get("lines") or [])
            if isinstance(line, dict)
        ]
        if len(_anons(broken)) == 1
        else None,
        "font_outcome": font.get("outcome"),
        "font_reason": font.get("reason"),
    }
    checks = {
        "row_slots": (
            row.get("outcome") == "placed"
            and _near(hi, x=0, y=0, content_width=20, content_height=10)
            and _near(item, x=20, y=0, content_width=30, content_height=10)
            and _near(yo, x=50, y=0, content_width=20, content_height=10)
            and _near(nxt, y=10)
        ),
        "whitespace_omitted": (
            gap.get("outcome") == "placed"
            and observed["gap_anons"] == 0
            and _near(_box(gap.get("boxes"), "a"), x=0, y=0, content_width=10)
            and _near(_box(gap.get("boxes"), "b"), x=10, y=0, content_width=10)
        ),
        "contents_joins": (
            merged.get("outcome") == "placed"
            and len(joined) == 1
            and _line_text(joined[0]) == "AABB"
            and _near(joined[0], x=0, y=0, content_width=40, content_height=10)
        ),
        "contents_box_splits": (
            split.get("outcome") == "placed"
            and _near(left, x=0, y=0, content_width=20, content_height=10)
            and _near(split_item, x=20, y=0, content_width=30, content_height=10)
            and _near(right, x=50, y=0, content_width=20, content_height=10)
        ),
        "order_puts_run_first": (
            ordered.get("outcome") == "placed"
            and _near(lead, x=0, y=0, content_width=20, content_height=10)
            and _near(ordered_item, x=20, y=0, content_width=30, content_height=10)
        ),
        "preserved_spaces": (
            preserved.get("outcome") == "placed"
            and len(spaces) == 1
            and _line_text(spaces[0]) == "A  B"
            and _near(spaces[0], x=0, y=0, content_width=40, content_height=10)
        ),
        "column_stacks": (
            column.get("outcome") == "placed"
            and len(column_text) == 1
            and _near(column_text[0], x=0, y=0, content_width=80, content_height=10)
            and _near(column_item, x=0, y=10, content_width=40, content_height=20)
            and _near(column_next, y=30)
        ),
        "blank_adds_no_item": (
            blank.get("outcome") == "placed"
            and observed["blank_anons"] == 0
            and _near(_box(blank.get("boxes"), "row"), y=0, content_height=0)
            and _near(_box(blank.get("boxes"), "next"), y=0)
        ),
        "vertical_rejected": vertical.get("outcome") == "invalid",
        "break_stacks": (
            broken.get("outcome") == "placed"
            and observed["break_lines"]
            == [
                {"text": "A", "y": 0, "height": 10},
                {"text": "B", "y": 10, "height": 10},
            ]
            and _near(_anons(broken)[0], x=0, y=0, content_width=10, content_height=20)
        ),
        "font_rejected": font.get("outcome") == "invalid",
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
