"""Pack leftover flex space in normal flow after flex factors and gaps.

Two 20px items in a 100px row sit at the center, the inline end, or the two
edges. A 10px gap stays between end-packed items. One item with space-between
stays at the start. Equal growth consumes the leftover, so center does not
split the grown items. A shorter item is centered or end-aligned on the cross
axis, wrapped lines are pushed apart, each wrapped line is centered on its
own, and a column packs its leftover against the bottom. The following block
starts at the flex border edge.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree that still rejects justify-content exits 0 with
passed false.
"""

from __future__ import annotations

import json
import sys

_PAIR = (
    '<div id="page"><div id="row"><span id="a"></span><span id="b"></span></div>'
    '<p id="next">Z</p></div>'
)
_ONE = '<div id="page"><div id="row"><span id="a"></span></div><p id="next">Z</p></div>'
_THREE = (
    '<div id="page"><div id="row"><span id="a"></span><span id="b"></span>'
    '<span id="c"></span></div><p id="next">Z</p></div>'
)
_PAGE = "#page { font-size: 10px; line-height: 10px; }\n"
_FIXED = "#a, #b, #c { flex: none; width: 20px; height: 10px; }\n"
_CENTER = _PAGE + "#row { display: flex; width: 100px; justify-content: center; }\n" + _FIXED
_END = _PAGE + "#row { display: flex; width: 100px; justify-content: flex-end; }\n" + _FIXED
_BETWEEN = _PAGE + "#row { display: flex; width: 100px; justify-content: space-between; }\n" + _FIXED
_AROUND = _PAGE + "#row { display: flex; width: 100px; justify-content: space-around; }\n" + _FIXED
_EVENLY = _PAGE + "#row { display: flex; width: 100px; justify-content: space-evenly; }\n" + _FIXED
_GAP_END = (
    _PAGE
    + "#row { display: flex; width: 100px; justify-content: flex-end; gap: 10px; }\n"
    + _FIXED
)
_SINGLE = (
    _PAGE
    + "#row { display: flex; width: 100px; justify-content: space-between; }\n"
    + "#a { flex: none; width: 20px; height: 10px; }\n"
)
_GROW = (
    _PAGE
    + "#row { display: flex; width: 100px; justify-content: center; }\n"
    + "#a, #b { flex: 1 1 20px; height: 10px; }\n"
)
_CROSS = (
    _PAGE
    + "#row { display: flex; width: 100px; height: 40px; align-items: center; }\n"
    + _FIXED
)
_SELF = (
    _PAGE
    + "#row { display: flex; width: 100px; height: 40px; align-items: flex-start; }\n"
    + "#a { flex: none; width: 20px; height: 10px; }\n"
    + "#b { flex: none; width: 20px; height: 10px; align-self: flex-end; }\n"
)
_LINES = (
    _PAGE
    + "#row { display: flex; flex-wrap: wrap; width: 90px; height: 100px;"
    + " align-content: space-between; }\n"
    + "#a, #b, #c { flex: none; width: 40px; height: 10px; }\n"
)
_WRAP = (
    _PAGE
    + "#row { display: flex; flex-wrap: wrap; width: 100px; justify-content: center; }\n"
    + "#a, #b, #c { flex: none; width: 40px; height: 10px; }\n"
)
_COLUMN = (
    _PAGE
    + "#row { display: flex; flex-direction: column; width: 40px; height: 100px;"
    + " justify-content: flex-end; }\n"
    + "#a { flex: none; width: 40px; height: 30px; }\n"
    + "#b { flex: none; width: 40px; height: 20px; }\n"
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
        placed = layout(markup, stylesheet, viewport_width=200)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without placement still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    cases = {
        "center": _lay(layout_normal_flow, _PAIR, _CENTER),
        "end": _lay(layout_normal_flow, _PAIR, _END),
        "between": _lay(layout_normal_flow, _PAIR, _BETWEEN),
        "around": _lay(layout_normal_flow, _PAIR, _AROUND),
        "evenly": _lay(layout_normal_flow, _PAIR, _EVENLY),
        "gap_end": _lay(layout_normal_flow, _PAIR, _GAP_END),
        "single": _lay(layout_normal_flow, _ONE, _SINGLE),
        "grow": _lay(layout_normal_flow, _PAIR, _GROW),
        "cross": _lay(layout_normal_flow, _PAIR, _CROSS),
        "self": _lay(layout_normal_flow, _PAIR, _SELF),
        "lines": _lay(layout_normal_flow, _THREE, _LINES),
        "wrap": _lay(layout_normal_flow, _THREE, _WRAP),
        "column": _lay(layout_normal_flow, _PAIR, _COLUMN),
    }

    def take(name: str, ident: str) -> dict[str, object] | None:
        return _box(cases[name].get("boxes"), ident)

    observed: dict[str, object] = {
        name: {
            "outcome": result.get("outcome"),
            "reason": result.get("reason"),
            "a": _placed(take(name, "a")),
            "b": _placed(take(name, "b")),
            "c": _placed(take(name, "c")),
            "row": _placed(take(name, "row")),
            "next": _placed(take(name, "next")),
        }
        for name, result in cases.items()
    }
    checks = {
        "center_packs_the_pair": (
            cases["center"].get("outcome") == "placed"
            and _near(take("center", "a"), x=30, y=0, content_width=20, content_height=10)
            and _near(take("center", "b"), x=50, y=0, content_width=20, content_height=10)
            and _near(take("center", "next"), y=10)
        ),
        "flex_end_packs_against_the_inline_end": (
            cases["end"].get("outcome") == "placed"
            and _near(take("end", "a"), x=60, y=0, content_width=20, content_height=10)
            and _near(take("end", "b"), x=80, y=0, content_width=20, content_height=10)
        ),
        "space_between_uses_the_two_edges": (
            cases["between"].get("outcome") == "placed"
            and _near(take("between", "a"), x=0, y=0, content_width=20)
            and _near(take("between", "b"), x=80, y=0, content_width=20)
        ),
        "space_around_splits_the_leftover": (
            cases["around"].get("outcome") == "placed"
            and _near(take("around", "a"), x=15, content_width=20)
            and _near(take("around", "b"), x=65, content_width=20)
        ),
        "space_evenly_shares_the_leading_gap": (
            cases["evenly"].get("outcome") == "placed"
            and _near(take("evenly", "a"), x=20, content_width=20)
            and _near(take("evenly", "b"), x=60, content_width=20)
        ),
        "end_packing_keeps_the_gap": (
            cases["gap_end"].get("outcome") == "placed"
            and _near(take("gap_end", "a"), x=50, content_width=20)
            and _near(take("gap_end", "b"), x=80, content_width=20)
        ),
        "one_item_space_between_stays_at_the_start": (
            cases["single"].get("outcome") == "placed"
            and _near(take("single", "a"), x=0, y=0, content_width=20, content_height=10)
        ),
        "growth_consumes_leftover_before_packing": (
            cases["grow"].get("outcome") == "placed"
            and _near(take("grow", "a"), x=0, y=0, content_width=50, content_height=10)
            and _near(take("grow", "b"), x=50, y=0, content_width=50, content_height=10)
        ),
        "align_items_centers_the_cross_axis": (
            cases["cross"].get("outcome") == "placed"
            and _near(take("cross", "a"), x=0, y=15, content_width=20, content_height=10)
            and _near(take("cross", "b"), x=20, y=15, content_width=20, content_height=10)
            and _near(take("cross", "row"), content_height=40)
            and _near(take("cross", "next"), y=40)
        ),
        "align_self_overrides_the_line": (
            cases["self"].get("outcome") == "placed"
            and _near(take("self", "a"), x=0, y=0, content_height=10)
            and _near(take("self", "b"), x=20, y=30, content_height=10)
            and _near(take("self", "next"), y=40)
        ),
        "align_content_separates_wrapped_lines": (
            cases["lines"].get("outcome") == "placed"
            and _near(take("lines", "a"), x=0, y=0, content_width=40, content_height=10)
            and _near(take("lines", "b"), x=40, y=0, content_width=40, content_height=10)
            and _near(take("lines", "c"), x=0, y=90, content_width=40, content_height=10)
            and _near(take("lines", "row"), content_width=90, content_height=100)
            and _near(take("lines", "next"), y=100)
        ),
        "each_wrapped_line_is_centered": (
            cases["wrap"].get("outcome") == "placed"
            and _near(take("wrap", "a"), x=10, y=0, content_width=40, content_height=10)
            and _near(take("wrap", "b"), x=50, y=0, content_width=40, content_height=10)
            and _near(take("wrap", "c"), x=30, y=10, content_width=40, content_height=10)
            and _near(take("wrap", "next"), y=20)
        ),
        "column_flex_end_packs_against_the_bottom": (
            cases["column"].get("outcome") == "placed"
            and _near(take("column", "a"), x=0, y=50, content_width=40, content_height=30)
            and _near(take("column", "b"), x=0, y=80, content_width=40, content_height=20)
            and _near(take("column", "row"), content_height=100)
            and _near(take("column", "next"), y=100)
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
