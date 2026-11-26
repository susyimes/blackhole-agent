"""Fragment one multicol paragraph across a fixed column-fill auto height.

widows 2 and orphans 2 put two lines in each column of a three-line column.
widows 1 and orphans 1 fill the first column and carry the last line over.
orphans 3, and a widows 2 pair that cannot break, move the paragraph into the
next column. Two lines that fit stay together. An omitted pair keeps four
lines in the first column. A sibling, column-height, and widows 0 are rejected.
The next block stays under the specified multicol height.

Prints JSON with boolean passed and nonempty observed. Exit 0 either way.
"""

from __future__ import annotations

import json

_PAGE = (
    "html, body, div, p { margin: 0px; }\n"
    "#page { font-size: 10px; line-height: 10px; width: 200px; }\n"
    "#next { height: 8px; }\n"
)
_COLS = "#cols { column-count: 2; column-gap: 0px; column-fill: auto; width: 40px; height: 30px; }\n"
_SHORT = "#cols { column-count: 2; column-gap: 0px; column-fill: auto; width: 40px; height: 20px; }\n"


def _markup(text: str) -> str:
    return f'<div id="page"><div id="cols"><p id="a">{text}</p></div><div id="next"></div></div>'


def _layout(function, markup: str, stylesheet: str) -> dict[str, object]:
    try:
        placed = function(markup, stylesheet, viewport_width=200)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    if not isinstance(placed, dict):
        return {"outcome": "error", "reason": "layout is invalid", "boxes": None}
    return placed


def _box(result: dict[str, object], ident: str) -> dict[str, object] | None:
    boxes = result.get("boxes")
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if isinstance(item, dict) and item.get("id") == ident:
            return item
    return None


def _lines(result: dict[str, object]) -> object:
    box = _box(result, "a")
    if box is None:
        return None
    lines = box.get("lines")
    if not isinstance(lines, list):
        return None
    recorded = []
    for line in lines:
        if not isinstance(line, dict):
            return None
        recorded.append(
            {
                "height": line.get("height"),
                "text": line.get("text"),
                "x": line.get("x"),
                "y": line.get("y"),
            }
        )
    return recorded


def _line(text: str, x: int, y: int) -> dict[str, object]:
    return {"height": 10, "text": text, "x": x, "y": y}


def _next_y(result: dict[str, object]) -> object:
    box = _box(result, "next")
    if box is None:
        return None
    return box.get("y")


def _rules(result: dict[str, object]) -> object:
    box = _box(result, "cols")
    if box is None:
        return None
    return box.get("rules")


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without layout still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    pair = _PAGE + _COLS + "#a { widows: 2; orphans: 2; }\n"
    split = _layout(layout_normal_flow, _markup("AA BB CC DD"), pair)
    inherited = _layout(
        layout_normal_flow,
        _markup("AA BB CC DD"),
        _PAGE + _COLS + "#cols { widows: 2; orphans: 2; }\n",
    )
    filled = _layout(
        layout_normal_flow,
        _markup("AA BB CC DD"),
        _PAGE + _COLS + "#a { widows: 1; orphans: 1; }\n",
    )
    moved = _layout(
        layout_normal_flow,
        _markup("AA BB CC"),
        _PAGE + _SHORT + "#a { widows: 1; orphans: 3; }\n",
    )
    blocked = _layout(
        layout_normal_flow,
        _markup("AA BB CC"),
        _PAGE + _SHORT + "#a { widows: 2; orphans: 2; }\n",
    )
    fitted = _layout(
        layout_normal_flow,
        _markup("AA BB"),
        _PAGE + _COLS + "#a { widows: 2; orphans: 2; }\n",
    )
    omitted = _layout(layout_normal_flow, _markup("AA BB CC DD"), _PAGE + _COLS)
    reset = _layout(
        layout_normal_flow,
        _markup("AA BB CC DD"),
        _PAGE + _COLS + "#cols { widows: 2; orphans: 2; }\n#a { widows: initial; orphans: initial; }\n",
    )
    ruled = _layout(
        layout_normal_flow,
        _markup("AA BB CC DD"),
        _PAGE + _COLS + "#cols { column-rule: 4px solid #010203; }\n#a { widows: 2; orphans: 2; }\n",
    )
    sibling = _layout(
        layout_normal_flow,
        '<div id="page"><div id="cols"><p id="a">AA BB</p><p id="b">CC</p></div><div id="next"></div></div>',
        _PAGE + _COLS + "#a { widows: 2; orphans: 2; }\n",
    )
    tall = _layout(
        layout_normal_flow,
        _markup("AA BB CC DD"),
        _PAGE
        + "#cols { column-count: 2; column-gap: 0px; column-height: 30px; width: 40px; }\n"
        + "#a { widows: 2; orphans: 2; }\n",
    )
    broken = _layout(
        layout_normal_flow,
        _markup("AA BB CC DD"),
        _PAGE + _COLS + "#a { widows: 0; orphans: 2; }\n",
    )
    negative = _layout(
        layout_normal_flow,
        _markup("AA"),
        _PAGE + _COLS + "#a { orphans: -1; }\n",
    )

    two_and_two = [_line("AA", 0, 0), _line("BB", 0, 10), _line("CC", 20, 0), _line("DD", 20, 10)]
    three_and_one = [_line("AA", 0, 0), _line("BB", 0, 10), _line("CC", 0, 20), _line("DD", 20, 0)]
    carried = [_line("AA", 20, 0), _line("BB", 20, 10), _line("CC", 20, 20)]
    together = [_line("AA", 0, 0), _line("BB", 0, 10)]
    whole = [_line("AA", 0, 0), _line("BB", 0, 10), _line("CC", 0, 20), _line("DD", 0, 30)]
    rule = [{"color": "#010203", "height": 30, "style": "solid", "width": 4, "x": 18, "y": 0}]

    observed: dict[str, object] = {
        "blocked_lines": _lines(blocked),
        "broken": {"outcome": broken.get("outcome"), "reason": broken.get("reason")},
        "filled_height": None if _box(filled, "a") is None else _box(filled, "a").get("content_height"),
        "filled_lines": _lines(filled),
        "fitted_lines": _lines(fitted),
        "inherited_lines": _lines(inherited),
        "moved_lines": _lines(moved),
        "negative": {"outcome": negative.get("outcome"), "reason": negative.get("reason")},
        "omitted_lines": _lines(omitted),
        "reset_lines": _lines(reset),
        "ruled": _rules(ruled),
        "sibling": {"outcome": sibling.get("outcome"), "reason": sibling.get("reason")},
        "split_height": None if _box(split, "a") is None else _box(split, "a").get("content_height"),
        "split_lines": _lines(split),
        "split_next_y": _next_y(split),
        "tall": {"outcome": tall.get("outcome"), "reason": tall.get("reason")},
    }
    checks = {
        "widows_pull_two_lines_into_each_column": (
            split.get("outcome") == "placed"
            and _lines(split) == two_and_two
            and observed["split_height"] == 20
            and observed["split_next_y"] == 30
        ),
        "inherited_counts_fragment_the_same_way": inherited.get("outcome") == "placed"
        and _lines(inherited) == two_and_two,
        "a_widow_of_one_fills_the_column_before_the_break": (
            filled.get("outcome") == "placed"
            and _lines(filled) == three_and_one
            and observed["filled_height"] == 30
            and _next_y(filled) == 30
        ),
        "orphans_move_a_short_start_into_the_next_column": moved.get("outcome") == "placed"
        and _lines(moved) == carried
        and _next_y(moved) == 20,
        "an_illegal_break_keeps_the_paragraph_together": blocked.get("outcome") == "placed"
        and _lines(blocked) == carried,
        "a_paragraph_that_fits_stays_in_the_first_column": fitted.get("outcome") == "placed"
        and _lines(fitted) == together,
        "an_omitted_pair_stays_one_unbreakable_box": omitted.get("outcome") == "placed"
        and _lines(omitted) == whole
        and (_box(omitted, "a") or {}).get("content_height") == 40
        and _next_y(omitted) == 30,
        "initial_resets_an_inherited_pair": reset.get("outcome") == "placed" and _lines(reset) == whole,
        "a_split_occupies_both_columns_for_the_rule": ruled.get("outcome") == "placed" and _rules(ruled) == rule,
        "a_sibling_is_rejected": sibling.get("outcome") == "invalid"
        and sibling.get("reason") == "column line fragmentation is unsupported",
        "column_height_is_rejected": tall.get("outcome") == "invalid"
        and tall.get("reason") == "column line fragmentation is unsupported",
        "zero_and_negative_counts_are_invalid": (
            broken.get("outcome") == "invalid"
            and broken.get("reason") == "widows is invalid"
            and negative.get("outcome") == "invalid"
            and negative.get("reason") == "orphans is invalid"
        ),
    }
    observed["checks"] = checks
    return all(checks.values()), observed


def main() -> int:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - the probe must exit 0 even when it fails
        passed, observed = False, {"error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps({"passed": passed, "observed": observed}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
