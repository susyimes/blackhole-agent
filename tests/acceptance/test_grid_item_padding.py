"""Inset a grid item's content by padding and its used border.

A stretched item keeps the padding and solid border inside a fixed area.
An automatic row grows by uneven vertical edges. A max-content column grows
by the horizontal edges. A specified width stays the content width. A hidden
border style contributes no inset. A block child starts inside the padding.
A definite grid height keeps an empty implicit row at its content size and
places the following block at that used height.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree that still rejects grid item padding exits 0.
"""

from __future__ import annotations

import json
import sys

_FONT = "#page { font-size: 10px; line-height: 10px; }\n"
_ITEM = '<div id="page"><div id="grid"><div id="item">AB</div></div><div id="after"></div></div>'
_WIDE = '<div id="page"><div id="grid"><div id="item">ABCD</div></div><div id="after"></div></div>'
_FIXED = '<div id="page"><div id="grid"><div id="item"></div></div><div id="after"></div></div>'
_CHILD = (
    '<div id="page"><div id="grid"><div id="item"><div id="child">AA</div></div></div>'
    '<div id="after"></div></div>'
)
_STRETCH = (
    _FONT
    + "#grid { display: grid; width: 100px; grid-template-columns: 100px; grid-template-rows: 40px; }\n"
    + "#item { padding: 6px 10px; border-width: 4px; border-style: solid; }\n"
    + "#after { height: 8px; }\n"
)
_UNEVEN = (
    _FONT
    + "#grid { display: grid; width: 100px; grid-template-columns: 100px; }\n"
    + "#item { padding-top: 5px; padding-right: 9px; padding-bottom: 7px; padding-left: 3px; "
    + "border-top-width: 2px; border-right-width: 6px; border-bottom-width: 1px; "
    + "border-left-width: 4px; border-style: solid; }\n"
)
_MAX = (
    _FONT
    + "#grid { display: grid; width: 200px; grid-template-columns: max-content; }\n"
    + "#item { padding-left: 8px; padding-right: 8px; border-left-width: 2px; "
    + "border-right-width: 2px; border-left-style: solid; border-right-style: solid; }\n"
)
_SPECIFIED = (
    _FONT
    + "#grid { display: grid; width: 100px; grid-template-columns: 100px; }\n"
    + "#item { width: 30px; padding: 5px; border-width: 2px; border-style: solid; }\n"
)
_HIDDEN = (
    _FONT
    + "#grid { display: grid; width: 100px; grid-template-columns: 100px; }\n"
    + "#item { border-width: 8px; border-style: none; }\n"
)
_NESTED = (
    _FONT
    + "#grid { display: grid; width: 80px; grid-template-columns: 80px; }\n"
    + "#item { padding: 10px; }\n"
)
_HEIGHT = _FONT + "#grid { display: grid; width: 40px; height: 40px; grid-template-columns: 40px; }\n"


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


def _line(box: dict[str, object] | None) -> dict[str, object] | None:
    if box is None or not isinstance(box.get("lines"), list) or not box["lines"]:
        return None
    line = box["lines"][0]
    if not isinstance(line, dict):
        return None
    return {"text": line.get("text"), "x": line.get("x"), "y": line.get("y")}


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
        "border_width": box.get("border_width"),
        "border_height": box.get("border_height"),
        "line": _line(box),
    }


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without placement still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    stretch = _lay(layout_normal_flow, _ITEM, _STRETCH)
    uneven = _lay(layout_normal_flow, _ITEM, _UNEVEN)
    packed = _lay(layout_normal_flow, _WIDE, _MAX)
    specified = _lay(layout_normal_flow, _ITEM, _SPECIFIED)
    hidden = _lay(layout_normal_flow, _ITEM, _HIDDEN)
    nested = _lay(layout_normal_flow, _CHILD, _NESTED)
    tall = _lay(layout_normal_flow, _FIXED, _HEIGHT)
    stretch_item = _box(stretch.get("boxes"), "item")
    uneven_item = _box(uneven.get("boxes"), "item")
    packed_item = _box(packed.get("boxes"), "item")
    specified_item = _box(specified.get("boxes"), "item")
    hidden_item = _box(hidden.get("boxes"), "item")
    nested_item = _box(nested.get("boxes"), "item")
    child = _box(nested.get("boxes"), "child")
    observed: dict[str, object] = {
        "stretch_outcome": stretch.get("outcome"),
        "stretch_reason": stretch.get("reason"),
        "stretch_item": _view(stretch, "item"),
        "stretch_line": _line(stretch_item),
        "stretch_after": _view(stretch, "after"),
        "uneven_outcome": uneven.get("outcome"),
        "uneven_reason": uneven.get("reason"),
        "uneven_item": _view(uneven, "item"),
        "uneven_line": _line(uneven_item),
        "uneven_after": _view(uneven, "after"),
        "packed_outcome": packed.get("outcome"),
        "packed_reason": packed.get("reason"),
        "packed_item": _view(packed, "item"),
        "packed_line": _line(packed_item),
        "packed_after": _view(packed, "after"),
        "specified_outcome": specified.get("outcome"),
        "specified_reason": specified.get("reason"),
        "specified_item": _view(specified, "item"),
        "specified_line": _line(specified_item),
        "specified_after": _view(specified, "after"),
        "hidden_outcome": hidden.get("outcome"),
        "hidden_reason": hidden.get("reason"),
        "hidden_item": _view(hidden, "item"),
        "hidden_line": _line(hidden_item),
        "nested_outcome": nested.get("outcome"),
        "nested_reason": nested.get("reason"),
        "nested_item": _view(nested, "item"),
        "child": _view(nested, "child"),
        "nested_after": _view(nested, "after"),
        "height_outcome": tall.get("outcome"),
        "height_reason": tall.get("reason"),
        "height_grid": _view(tall, "grid"),
        "height_item": _view(tall, "item"),
        "height_after": _view(tall, "after"),
    }
    checks = {
        "stretched_edges_inset_the_line": (
            stretch.get("outcome") == "placed"
            and _near(
                stretch_item,
                x=0,
                y=0,
                content_width=72,
                content_height=20,
                border_width=100,
                border_height=40,
            )
            and _near(_line(stretch_item), text="AB", x=14, y=10)
            and _near(_box(stretch.get("boxes"), "after"), y=40)
        ),
        "automatic_row_grows_by_uneven_edges": (
            uneven.get("outcome") == "placed"
            and _near(uneven_item, x=0, y=0, content_width=78, content_height=10, border_width=100, border_height=25)
            and _near(_line(uneven_item), text="AB", x=7, y=7)
            and _near(_box(uneven.get("boxes"), "after"), y=25)
        ),
        "max_content_column_includes_horizontal_edges": (
            packed.get("outcome") == "placed"
            and _near(packed_item, x=0, y=0, content_width=40, content_height=10, border_width=60, border_height=10)
            and _near(_line(packed_item), text="ABCD", x=10, y=0)
            and _near(_box(packed.get("boxes"), "after"), y=10)
        ),
        "specified_width_stays_the_content_width": (
            specified.get("outcome") == "placed"
            and _near(
                specified_item,
                x=0,
                y=0,
                content_width=30,
                content_height=10,
                border_width=44,
                border_height=24,
            )
            and _near(_line(specified_item), text="AB", x=7, y=7)
            and _near(_box(specified.get("boxes"), "after"), y=24)
        ),
        "hidden_border_style_does_not_inset": (
            hidden.get("outcome") == "placed"
            and _near(hidden_item, x=0, y=0, content_width=100, content_height=10, border_width=100)
            and _near(_line(hidden_item), text="AB", x=0, y=0)
        ),
        "block_child_starts_inside_the_padding": (
            nested.get("outcome") == "placed"
            and _near(nested_item, x=0, y=0, content_width=60, content_height=10, border_width=80, border_height=30)
            and _near(child, x=10, y=10, content_width=60, content_height=10)
            and _near(_box(nested.get("boxes"), "after"), y=30)
        ),
        "definite_grid_height_keeps_the_used_edge": (
            tall.get("outcome") == "placed"
            and _near(_box(tall.get("boxes"), "grid"), y=0, content_height=40, border_height=40)
            and _near(_box(tall.get("boxes"), "item"), y=0, content_height=0, border_height=0)
            and _near(_box(tall.get("boxes"), "after"), y=40)
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
