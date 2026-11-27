"""Drop a visibility-collapse table row without forgetting its column width.

On a marginless page at font-size 10px and line-height 10px, WWWW in a
collapsed first row keeps the table 40px wide, puts A at y 0, and the
following block at y 10. The collapsed cell has no line. The same rows
without collapse put A at y 10 and the following block at y 20.
border-spacing 0 12px puts A at y 12 and the following block at y 34, or
at y 34 and y 56 when the row stays. A collapsed middle WWWW puts C at
y 10 and the following block at y 20. Hidden keeps the row. A collapsed
cell and an ordinary block do not. Collapse with collapsed borders, a
fixed table, a rowspan, or a specified height is rejected.

Prints JSON with boolean passed and nonempty observed. Exit 0 either way.
"""

from __future__ import annotations

import json
import sys

_BASE = "html, body, div, p { margin: 0px; font-size: 10px; line-height: 10px; }\n"
_ROWS = "#r1, #r2, #r3 { display: table-row; }\n#a, #b, #c { display: table-cell; }\n"
_TWO = (
    '<div id="page"><div id="table"><div id="r1"><div id="a">WWWW</div></div>'
    '<div id="r2"><div id="b">A</div></div></div><p id="next">Z</p></div>'
)
_THREE = (
    '<div id="page"><div id="table"><div id="r1"><div id="a">A</div></div>'
    '<div id="r2"><div id="b">WWWW</div></div>'
    '<div id="r3"><div id="c">C</div></div></div><p id="next">Z</p></div>'
)
_ONE = (
    '<div id="page"><div id="table"><div id="r1"><div id="a">AA</div></div>'
    '</div><p id="next">Z</p></div>'
)
_BLOCK = '<div id="page"><div id="box">AA</div><p id="next">Z</p></div>'
_SPAN = (
    '<div id="page"><div id="table"><div id="r1"><div id="a" rowspan="2">WWWW</div></div>'
    '<div id="r2"><div id="b">A</div></div></div><p id="next">Z</p></div>'
)


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


def _lay(layout, markup: str, stylesheet: str) -> dict[str, object]:
    try:
        placed = layout(markup, stylesheet, viewport_width=240)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def _spot(result: dict[str, object], ident: str) -> dict[str, object]:
    box = _box(result.get("boxes"), ident)
    line = _line(box)
    return {
        "outcome": result.get("outcome"),
        "reason": result.get("reason"),
        "x": None if line is None else line.get("x"),
        "y": None if line is None else line.get("y"),
        "text": None if line is None else line.get("text"),
        "lines": 0 if box is None or not isinstance(box.get("lines"), list) else len(box["lines"]),
        "width": None if box is None else box.get("content_width"),
        "next_y": None if _box(result.get("boxes"), "next") is None else _box(result.get("boxes"), "next").get("y"),
    }


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import element_from_document, layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without placement still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    sheets = {
        "plain": _BASE + "#table { display: table; }\n" + _ROWS,
        "collapse": _BASE + "#table { display: table; }\n#r1 { visibility: collapse; }\n" + _ROWS,
        "space": _BASE + "#table { display: table; border-spacing: 0 12px; }\n" + _ROWS,
        "space_collapse": _BASE
        + "#table { display: table; border-spacing: 0 12px; }\n#r1 { visibility: collapse; }\n"
        + _ROWS,
        "middle": _BASE + "#table { display: table; }\n#r2 { visibility: collapse; }\n" + _ROWS,
        "hidden": _BASE + "#table { display: table; }\n#r1 { visibility: hidden; }\n" + _ROWS,
        "cell": _BASE + "#table { display: table; }\n#a { visibility: collapse; }\n" + _ROWS,
        "block": _BASE + "#box { visibility: collapse; }\n",
        "borders": _BASE
        + "#table { display: table; border-collapse: collapse; }\n#r1 { visibility: collapse; }\n"
        + _ROWS,
        "fixed": _BASE
        + "#table { display: table; table-layout: fixed; width: 80px; }\n#r1 { visibility: collapse; }\n"
        + _ROWS,
        "height": _BASE + "#table { display: table; height: 40px; }\n#r1 { visibility: collapse; }\n" + _ROWS,
        "span": _BASE + "#table { display: table; }\n#r1 { visibility: collapse; }\n" + _ROWS,
    }
    markup = {
        "plain": _TWO,
        "collapse": _TWO,
        "space": _TWO,
        "space_collapse": _TWO,
        "middle": _THREE,
        "hidden": _TWO,
        "cell": _ONE,
        "block": _BLOCK,
        "borders": _TWO,
        "fixed": _TWO,
        "height": _TWO,
        "span": _SPAN,
    }
    cases = {name: _lay(layout_normal_flow, markup[name], sheets[name]) for name in sheets}
    observed = {name: _spot(cases[name], "a") for name in cases}
    observed["collapse_b"] = _spot(cases["collapse"], "b")
    observed["space_b"] = _spot(cases["space"], "b")
    observed["space_collapse_b"] = _spot(cases["space_collapse"], "b")
    observed["middle_b"] = _spot(cases["middle"], "b")
    observed["middle_c"] = _spot(cases["middle"], "c")
    observed["table_widths"] = {
        name: None if _box(cases[name].get("boxes"), "table") is None else _box(cases[name].get("boxes"), "table").get("content_width")
        for name in ("collapse", "plain", "space_collapse", "middle")
    }
    observed["hidden_b"] = _spot(cases["hidden"], "b")
    observed["cell_a"] = _spot(cases["cell"], "a")
    observed["block"] = _spot(cases["block"], "box")
    hit = element_from_document(markup["collapse"], sheets["collapse"], 1, 1, viewport_width=240)
    block_hit = element_from_document(markup["block"], sheets["block"], 1, 1, viewport_width=240)
    observed["hit"] = {"outcome": hit.get("outcome"), "id": hit.get("id"), "reason": hit.get("reason")}
    observed["block_hit"] = {
        "outcome": block_hit.get("outcome"),
        "id": block_hit.get("id"),
        "reason": block_hit.get("reason"),
    }

    def at(name: str, field: str) -> object:
        return observed[name].get(field)

    def rejected(name: str) -> bool:
        return cases[name].get("outcome") == "invalid" and cases[name].get("reason") == "table row visibility is unsupported"

    checks = {
        "collapsed_row_keeps_width_and_drops_height": (
            at("collapse", "lines") == 0
            and observed["table_widths"]["collapse"] == 40
            and at("collapse_b", "y") == 0
            and at("collapse_b", "text") == "A"
            and at("collapse_b", "next_y") == 10
        ),
        "visible_row_keeps_both_lines": (
            at("plain", "y") == 0
            and at("plain", "text") == "WWWW"
            and _spot(cases["plain"], "b").get("y") == 10
            and at("plain", "next_y") == 20
            and at("plain", "width") == 40
        ),
        "spacing_moves_with_the_collapsed_row": (
            at("space_collapse", "lines") == 0
            and at("space_collapse_b", "y") == 12
            and at("space_collapse_b", "next_y") == 34
            and observed["table_widths"]["space_collapse"] == 40
            and _spot(cases["space"], "b").get("y") == 34
            and at("space", "next_y") == 56
        ),
        "middle_row_drops_out_and_keeps_the_column": (
            at("middle_b", "lines") == 0
            and observed["table_widths"]["middle"] == 40
            and at("middle_c", "y") == 10
            and at("middle_c", "text") == "C"
            and at("middle_c", "next_y") == 20
        ),
        "hidden_keeps_the_row": (
            at("hidden", "y") == 0
            and at("hidden", "lines") == 1
            and at("hidden_b", "y") == 10
            and at("hidden_b", "next_y") == 20
        ),
        "collapsed_cell_keeps_the_line": (
            at("cell_a", "y") == 0 and at("cell_a", "text") == "AA" and at("cell_a", "next_y") == 10
        ),
        "ordinary_block_stays_in_flow_and_is_not_a_target": (
            at("block", "y") == 0
            and at("block", "next_y") == 10
            and observed["block_hit"]["outcome"] == "hit"
            and observed["block_hit"]["id"] == "page"
        ),
        "visible_cell_receives_the_point": observed["hit"]["outcome"] == "hit" and observed["hit"]["id"] == "b",
        "collapsed_borders_are_rejected": rejected("borders"),
        "fixed_table_is_rejected": rejected("fixed"),
        "specified_height_is_rejected": rejected("height"),
        "rowspan_is_rejected": rejected("span"),
    }
    return all(checks.values()), {"checks": checks, "observed": observed}


def main() -> None:
    passed, observed = observe()
    json.dump({"passed": passed, "observed": observed}, sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
