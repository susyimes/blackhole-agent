"""Share collapsed table borders in normal flow.

Two 4px solid cells keep one 4px edge between them, so the second line
starts at x 28 and the following block at y 18. A 6px solid beats a 2px
dotted. Hidden removes a 10px edge. Two stacked 4px rows put the second
line at y 18 and the following block at y 32. A table's own 6px edge
insets the first line to x 6. Separate cell borders stay rejected.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree that still rejects border-collapse exits 0 with
passed false.
"""

from __future__ import annotations

import json
import sys

_FONT = "#page { font-size: 10px; line-height: 10px; }\n"
_TABLE = "#table { display: table; border-collapse: collapse; }\n#row, #row2 { display: table-row; }\n"
_CELLS = "#a, #b, #c { display: table-cell; }\n"
_PAIR = (
    '<div id="page"><div id="table"><div id="row"><div id="a">AA</div>'
    '<div id="b">BBB</div></div></div><p id="next">Z</p></div>'
)
_STACK = (
    '<div id="page"><div id="table"><div id="row"><div id="a">AA</div></div>'
    '<div id="row2"><div id="b">BB</div></div></div><p id="next">Z</p></div>'
)
_SHARED = _FONT + _TABLE + _CELLS + "#a, #b { border-width: 4px; border-style: solid; }\n"
_WIDER = (
    _FONT
    + _TABLE
    + _CELLS
    + "#a { border-right-width: 2px; border-right-style: dotted; }\n"
    + "#b { border-left-width: 6px; border-left-style: solid; }\n"
)
_HIDDEN = (
    _FONT
    + _TABLE
    + _CELLS
    + "#a { border-right-width: 10px; border-right-style: solid; }\n"
    + "#b { border-left-width: 4px; border-left-style: hidden; }\n"
)
_DOUBLE = (
    _FONT
    + _TABLE
    + _CELLS
    + "#a { border-right-width: 4px; border-right-style: dotted; }\n"
    + "#b { border-left-width: 4px; border-left-style: double; }\n"
)
_STACKED = _FONT + _TABLE + _CELLS + "#a, #b { border-width: 4px; border-style: solid; }\n"
_TABLE_EDGE = _FONT + _TABLE + _CELLS + "#table { border-left-width: 6px; border-left-style: solid; }\n"
_SEPARATE = _FONT + "#table { display: table; }\n#row { display: table-row; }\n" + _CELLS
_SEPARATE += "#a { border-width: 4px; border-style: solid; }\n"


def _box(boxes: object, ident: str) -> dict[str, object] | None:
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if isinstance(item, dict) and item.get("id") == ident:
            return item
    return None


def _line(box: dict[str, object] | None) -> dict[str, object] | None:
    if box is None or not isinstance(box.get("lines"), list) or not box["lines"]:
        return None
    line = box["lines"][0]
    return line if isinstance(line, dict) else None


def _edge(box: dict[str, object] | None, side: str) -> dict[str, object] | None:
    if box is None or not isinstance(box.get("collapsed_borders"), dict):
        return None
    edge = box["collapsed_borders"].get(side)
    return edge if isinstance(edge, dict) else None


def _lay(layout, markup: str, stylesheet: str) -> dict[str, object]:
    try:
        placed = layout(markup, stylesheet, viewport_width=200)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def _paint(result: dict[str, object], ident: str) -> dict[str, object] | None:
    box = _box(result.get("boxes"), ident)
    line = _line(box)
    if box is None or line is None:
        return None
    return {"x": line.get("x"), "y": line.get("y"), "text": line.get("text")}


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without placement still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    shared = _lay(layout_normal_flow, _PAIR, _SHARED)
    wider = _lay(layout_normal_flow, _PAIR, _WIDER)
    hidden = _lay(layout_normal_flow, _PAIR, _HIDDEN)
    doubled = _lay(layout_normal_flow, _PAIR, _DOUBLE)
    stacked = _lay(layout_normal_flow, _STACK, _STACKED)
    table_edge = _lay(layout_normal_flow, _PAIR, _TABLE_EDGE)
    separate = _lay(layout_normal_flow, _PAIR, _SEPARATE)

    def take(result: dict[str, object], ident: str) -> dict[str, object] | None:
        return _box(result.get("boxes"), ident)

    shared_b = take(shared, "b")
    wider_b = take(wider, "b")
    hidden_b = take(hidden, "b")
    observed: dict[str, object] = {
        "shared_outcome": shared.get("outcome"),
        "shared_reason": shared.get("reason"),
        "shared_a": _paint(shared, "a"),
        "shared_b": _paint(shared, "b"),
        "shared_next_y": None if take(shared, "next") is None else take(shared, "next").get("y"),
        "shared_b_left": _edge(shared_b, "left"),
        "wider_outcome": wider.get("outcome"),
        "wider_b": _paint(wider, "b"),
        "wider_b_left": _edge(wider_b, "left"),
        "hidden_outcome": hidden.get("outcome"),
        "hidden_b": _paint(hidden, "b"),
        "hidden_b_left": _edge(hidden_b, "left"),
        "hidden_next_y": None if take(hidden, "next") is None else take(hidden, "next").get("y"),
        "double_outcome": doubled.get("outcome"),
        "double_b": _paint(doubled, "b"),
        "double_b_left": _edge(take(doubled, "b"), "left"),
        "stacked_outcome": stacked.get("outcome"),
        "stacked_b": _paint(stacked, "b"),
        "stacked_next_y": None if take(stacked, "next") is None else take(stacked, "next").get("y"),
        "table_edge_a": _paint(table_edge, "a"),
        "table_edge_left": _edge(take(table_edge, "table"), "left"),
        "separate_outcome": separate.get("outcome"),
    }
    checks = {
        "shared_edge_is_one_border": (
            shared.get("outcome") == "placed"
            and _paint(shared, "a") == {"x": 4, "y": 4, "text": "AA"}
            and _paint(shared, "b") == {"x": 28, "y": 4, "text": "BBB"}
            and observed["shared_next_y"] == 18
            and _edge(shared_b, "left") is not None
            and _edge(shared_b, "left").get("width") == 4
            and _edge(shared_b, "left").get("style") == "solid"
        ),
        "wider_border_beats_style": (
            wider.get("outcome") == "placed"
            and _paint(wider, "b") == {"x": 26, "y": 0, "text": "BBB"}
            and _edge(wider_b, "left") is not None
            and _edge(wider_b, "left").get("width") == 6
            and _edge(wider_b, "left").get("style") == "solid"
        ),
        "equal_width_prefers_double": (
            doubled.get("outcome") == "placed"
            and _paint(doubled, "b") == {"x": 24, "y": 0, "text": "BBB"}
            and _edge(take(doubled, "b"), "left") is not None
            and _edge(take(doubled, "b"), "left").get("width") == 4
            and _edge(take(doubled, "b"), "left").get("style") == "double"
        ),
        "hidden_suppresses_the_edge": (
            hidden.get("outcome") == "placed"
            and _paint(hidden, "b") == {"x": 20, "y": 0, "text": "BBB"}
            and observed["hidden_next_y"] == 10
            and _edge(hidden_b, "left") is not None
            and _edge(hidden_b, "left").get("width") == 0
            and _edge(hidden_b, "left").get("style") == "hidden"
        ),
        "stacked_rows_share_one_edge": (
            stacked.get("outcome") == "placed"
            and _paint(stacked, "b") == {"x": 4, "y": 18, "text": "BB"}
            and observed["stacked_next_y"] == 32
        ),
        "table_edge_insets_the_first_line": (
            table_edge.get("outcome") == "placed"
            and _paint(table_edge, "a") == {"x": 6, "y": 0, "text": "AA"}
            and _edge(take(table_edge, "table"), "left") is not None
            and _edge(take(table_edge, "table"), "left").get("width") == 6
            and _edge(take(table_edge, "table"), "left").get("source") == "table"
        ),
        "separate_cell_border_stays_rejected": separate.get("outcome") == "invalid",
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
