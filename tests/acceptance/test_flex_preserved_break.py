"""Stack a preserved newline inside a flex item.

white-space:pre keeps the spaces on the first line and sizes the item to the
longest line. pre-line collapses those spaces but keeps the break. A flex
item's own pre value does the same beside a shorter sibling. A column grows
by the stacked lines. A tab stays invalid.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit.
"""

from __future__ import annotations

import json
import sys

_PAGE = "#page { font-size: 10px; line-height: 10px; }\n"
_PRE = '<div id="page"><div id="row">A  B\nC</div><p id="next">Q</p></div>'
_PRE_CSS = _PAGE + "#row { display: flex; width: 200px; white-space: pre; }\n"
_LINE = '<div id="page"><div id="row">A \n BB</div><p id="next">Q</p></div>'
_LINE_CSS = _PAGE + "#row { display: flex; width: 200px; white-space: pre-line; }\n"
_ITEM = '<div id="page"><div id="row"><span id="item">A\nBB</span><span id="tail">Z</span></div><p id="next">Q</p></div>'
_ITEM_CSS = (
    _PAGE
    + "#row { display: flex; width: 200px; }\n"
    + "#item { white-space: pre; flex: none; }\n"
    + "#tail { flex: none; align-self: flex-start; }\n"
)
_COLUMN = '<div id="page"><div id="col">A\nBB</div><p id="next">Q</p></div>'
_COLUMN_CSS = (
    _PAGE
    + "#col { display: flex; flex-direction: column; width: 80px; white-space: pre; }\n"
)
_FLAT = '<div id="page"><div id="row">ABB</div><p id="next">Q</p></div>'
_FLAT_CSS = _PAGE + "#row { display: flex; width: 200px; white-space: pre; }\n"
_TAB = '<div id="page"><div id="row">A\tB</div></div>'
_TAB_CSS = _PAGE + "#row { display: flex; width: 200px; white-space: pre; }\n"


def _box(boxes: object, ident: str) -> dict[str, object] | None:
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if isinstance(item, dict) and item.get("id") == ident:
            return item
    return None


def _anons(result: dict[str, object]) -> list[dict[str, object]]:
    boxes = result.get("boxes")
    if not isinstance(boxes, list):
        return []
    return [
        box
        for box in boxes
        if isinstance(box, dict) and str(box.get("id") or "").startswith("anon-")
    ]


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


def _public(box: dict[str, object] | None) -> dict[str, object] | None:
    if box is None:
        return None
    lines = box.get("lines")
    shown = []
    if isinstance(lines, list):
        for line in lines:
            if isinstance(line, dict):
                shown.append(
                    {
                        "text": line.get("text"),
                        "x": line.get("x"),
                        "y": line.get("y"),
                        "height": line.get("height"),
                        "content_width": line.get("content_width"),
                    }
                )
    return {
        "x": box.get("x"),
        "y": box.get("y"),
        "content_width": box.get("content_width"),
        "content_height": box.get("content_height"),
        "lines": shown,
    }


def _lay(layout, markup: str, stylesheet: str) -> dict[str, object]:
    try:
        placed = layout(markup, stylesheet, viewport_width=200)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without the walk still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    preserved = _lay(layout_normal_flow, _PRE, _PRE_CSS)
    collapsed = _lay(layout_normal_flow, _LINE, _LINE_CSS)
    itemized = _lay(layout_normal_flow, _ITEM, _ITEM_CSS)
    column = _lay(layout_normal_flow, _COLUMN, _COLUMN_CSS)
    flat = _lay(layout_normal_flow, _FLAT, _FLAT_CSS)
    tabbed = _lay(layout_normal_flow, _TAB, _TAB_CSS)
    pre_items = _anons(preserved)
    line_items = _anons(collapsed)
    column_items = _anons(column)
    flat_items = _anons(flat)
    pre_box = pre_items[0] if len(pre_items) == 1 else None
    line_box = line_items[0] if len(line_items) == 1 else None
    column_box = column_items[0] if len(column_items) == 1 else None
    flat_box = flat_items[0] if len(flat_items) == 1 else None
    item = _box(itemized.get("boxes"), "item")
    tail = _box(itemized.get("boxes"), "tail")
    observed: dict[str, object] = {
        "pre_outcome": preserved.get("outcome"),
        "pre_reason": preserved.get("reason"),
        "pre": _public(pre_box),
        "pre_next": _public(_box(preserved.get("boxes"), "next")),
        "line_outcome": collapsed.get("outcome"),
        "line_reason": collapsed.get("reason"),
        "line": _public(line_box),
        "line_next": _public(_box(collapsed.get("boxes"), "next")),
        "item_outcome": itemized.get("outcome"),
        "item_reason": itemized.get("reason"),
        "item": _public(item),
        "tail": _public(tail),
        "item_next": _public(_box(itemized.get("boxes"), "next")),
        "column_outcome": column.get("outcome"),
        "column_reason": column.get("reason"),
        "column": _public(column_box),
        "column_next": _public(_box(column.get("boxes"), "next")),
        "flat_outcome": flat.get("outcome"),
        "flat_reason": flat.get("reason"),
        "flat": _public(flat_box),
        "flat_next": _public(_box(flat.get("boxes"), "next")),
        "tab_outcome": tabbed.get("outcome"),
        "tab_reason": tabbed.get("reason"),
    }
    checks = {
        "pre_keeps_spaces_and_stacks": (
            preserved.get("outcome") == "placed"
            and len(pre_items) == 1
            and _near(pre_box, x=0, y=0, content_width=40, content_height=20)
            and _near(_line(pre_box, 0), text="A  B", x=0, y=0, height=10, content_width=40)
            and _near(_line(pre_box, 1), text="C", x=0, y=10, height=10, content_width=10)
            and _line(pre_box, 2) is None
            and _near(_box(preserved.get("boxes"), "next"), x=0, y=20)
        ),
        "pre_line_collapses_spaces_around_the_break": (
            collapsed.get("outcome") == "placed"
            and len(line_items) == 1
            and _near(line_box, x=0, y=0, content_width=20, content_height=20)
            and _near(_line(line_box, 0), text="A", x=0, y=0, height=10, content_width=10)
            and _near(_line(line_box, 1), text="BB", x=0, y=10, height=10, content_width=20)
            and _near(_box(collapsed.get("boxes"), "next"), x=0, y=20)
        ),
        "item_pre_stacks_beside_a_short_tail": (
            itemized.get("outcome") == "placed"
            and _near(item, x=0, y=0, content_width=20, content_height=20)
            and _near(_line(item, 0), text="A", x=0, y=0, height=10, content_width=10)
            and _near(_line(item, 1), text="BB", x=0, y=10, height=10, content_width=20)
            and _near(tail, x=20, y=0, content_width=10, content_height=10)
            and _near(_box(itemized.get("boxes"), "next"), x=0, y=20)
        ),
        "column_grows_to_the_stacked_lines": (
            column.get("outcome") == "placed"
            and len(column_items) == 1
            and _near(column_box, x=0, y=0, content_width=80, content_height=20)
            and _near(_line(column_box, 0), text="A", y=0, height=10)
            and _near(_line(column_box, 1), text="BB", y=10, height=10)
            and _near(_box(column.get("boxes"), "next"), x=0, y=20)
        ),
        "unbroken_pre_stays_one_line": (
            flat.get("outcome") == "placed"
            and len(flat_items) == 1
            and _near(flat_box, x=0, y=0, content_width=30, content_height=10)
            and _near(_line(flat_box, 0), text="ABB", x=0, y=0, height=10, content_width=30)
            and _line(flat_box, 1) is None
            and _near(_box(flat.get("boxes"), "next"), y=10)
        ),
        "tab_stays_invalid": tabbed.get("outcome") == "invalid",
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
