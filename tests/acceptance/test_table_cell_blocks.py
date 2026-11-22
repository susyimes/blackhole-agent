"""Lay static block children inside a normal-flow table cell.

The cell keeps the child's margin, collapses adjoining child margins, wraps
the child's text in a narrow fixed column, and sizes an automatic column
from that text. A text sibling starts in the next column. The following
block starts under the table. A float inside the cell is rejected.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A table that still rejects cell children exits 0 with
passed false.
"""

from __future__ import annotations

import json
import sys

_FONT = "#page { font-size: 10px; line-height: 10px; }\n"
_FIXED = (
    "#table { display: table; table-layout: fixed; width: 200px; }\n"
    "#row { display: table-row; }\n"
    "#a { display: table-cell; }\n"
)
_NARROW = (
    "#table { display: table; table-layout: fixed; width: 40px; }\n"
    "#row { display: table-row; }\n"
    "#a { display: table-cell; }\n"
)
_AUTO = (
    "#table { display: table; }\n"
    "#row { display: table-row; }\n"
    "#a, #side { display: table-cell; }\n"
)
_ONE = (
    '<div id="page"><div id="table"><div id="row"><div id="a"><div id="b">AA</div>'
    "</div></div></div><p id=\"next\">Z</p></div>"
)
_TWO = (
    '<div id="page"><div id="table"><div id="row"><div id="a"><div id="b">AA</div>'
    '<div id="c">BB</div></div></div></div><p id="next">Z</p></div>'
)
_WRAP = (
    '<div id="page"><div id="table"><div id="row"><div id="a"><div id="b">AA BB</div>'
    "</div></div></div><p id=\"next\">Z</p></div>"
)
_PAIR = (
    '<div id="page"><div id="table"><div id="row"><div id="a"><div id="b">AA</div></div>'
    '<div id="side">ZZ</div></div></div><p id="next">Z</p></div>'
)
_FLOAT = (
    '<div id="page"><div id="table"><div id="row"><div id="a"><div id="b">AA</div>'
    "</div></div></div></div>"
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


def _lay(layout, markup: str, stylesheet: str) -> dict[str, object]:
    try:
        placed = layout(markup, _FONT + stylesheet, viewport_width=240)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def _placed(result: dict[str, object], ident: str) -> dict[str, object] | None:
    box = _box(result.get("boxes"), ident)
    if box is None:
        return None
    lines = box.get("lines")
    return {
        "x": box.get("x"),
        "y": box.get("y"),
        "content_width": box.get("content_width"),
        "content_height": box.get("content_height"),
        "lines": [line.get("text") for line in lines if isinstance(line, dict)] if isinstance(lines, list) else None,
    }


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without placement still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    cases = {
        "plain": _lay(layout_normal_flow, _ONE, _FIXED),
        "margin": _lay(layout_normal_flow, _ONE, _FIXED + "#b { margin: 10px; }\n"),
        "stack": _lay(layout_normal_flow, _TWO, _FIXED),
        "collapse": _lay(
            layout_normal_flow,
            _TWO,
            _FIXED + "#b { margin-bottom: 10px; }\n#c { margin-top: 10px; }\n",
        ),
        "wrap": _lay(layout_normal_flow, _WRAP, _NARROW),
        "pair": _lay(layout_normal_flow, _PAIR, _AUTO),
        "floated": _lay(layout_normal_flow, _FLOAT, _FIXED + "#b { float: left; width: 20px; height: 10px; }\n"),
    }
    observed: dict[str, object] = {
        name: {
            "outcome": result.get("outcome"),
            "reason": result.get("reason"),
            "a": _placed(result, "a"),
            "b": _placed(result, "b"),
            "c": _placed(result, "c"),
            "side": _placed(result, "side"),
            "next": _placed(result, "next"),
        }
        for name, result in cases.items()
    }
    wrap_lines = (observed["wrap"]["b"] or {}).get("lines") if isinstance(observed["wrap"]["b"], dict) else None
    checks = {
        "child_block_fills_the_cell_and_the_next_block_follows": (
            cases["plain"].get("outcome") == "placed"
            and _near(_box(cases["plain"].get("boxes"), "b"), x=0, y=0, content_width=200, content_height=10)
            and _near(_box(cases["plain"].get("boxes"), "a"), content_width=200, content_height=10)
            and _near(_box(cases["plain"].get("boxes"), "next"), y=10)
        ),
        "child_margin_stays_inside_the_cell": (
            cases["margin"].get("outcome") == "placed"
            and _near(_box(cases["margin"].get("boxes"), "b"), x=10, y=10, content_width=180, content_height=10)
            and _near(_box(cases["margin"].get("boxes"), "a"), content_height=30)
            and _near(_box(cases["margin"].get("boxes"), "next"), y=30)
        ),
        "stacked_children_grow_the_row": (
            cases["stack"].get("outcome") == "placed"
            and _near(_box(cases["stack"].get("boxes"), "c"), x=0, y=10, content_height=10)
            and _near(_box(cases["stack"].get("boxes"), "a"), content_height=20)
            and _near(_box(cases["stack"].get("boxes"), "next"), y=20)
        ),
        "adjoining_child_margins_collapse": (
            cases["collapse"].get("outcome") == "placed"
            and _near(_box(cases["collapse"].get("boxes"), "b"), y=0, content_height=10)
            and _near(_box(cases["collapse"].get("boxes"), "c"), y=20, content_height=10)
            and _near(_box(cases["collapse"].get("boxes"), "a"), content_height=30)
            and _near(_box(cases["collapse"].get("boxes"), "next"), y=30)
        ),
        "narrow_column_wraps_the_child_text": (
            cases["wrap"].get("outcome") == "placed"
            and _near(_box(cases["wrap"].get("boxes"), "b"), x=0, y=0, content_width=40, content_height=20)
            and wrap_lines == ["AA", "BB"]
            and _near(_box(cases["wrap"].get("boxes"), "next"), y=20)
        ),
        "automatic_column_uses_the_child_and_the_sibling_starts_after_it": (
            cases["pair"].get("outcome") == "placed"
            and _near(_box(cases["pair"].get("boxes"), "b"), x=0, y=0, content_width=20, content_height=10)
            and _near(_box(cases["pair"].get("boxes"), "a"), content_width=20, content_height=10)
            and _near(_box(cases["pair"].get("boxes"), "side"), x=20, y=0, content_width=20, content_height=10)
            and _near(_box(cases["pair"].get("boxes"), "next"), y=10)
        ),
        "a_float_inside_the_cell_is_rejected": cases["floated"].get("outcome") == "invalid",
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
