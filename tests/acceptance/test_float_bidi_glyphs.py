"""Paint Unicode bidi glyphs on lines a left float shortens.

In a 200px viewport, a 60px paragraph at 10px places אבגד beside a 20 by 20
left float: the line is at x 20 y 0 and the glyphs are ד ג ב א at x 20, 30,
40, and 50. The following block starts at y 20. A 50px paragraph places aa
at x 20 y 0 with no glyphs and אבגד at x 0 y 20 with those glyphs at x 0, 10,
20, and 30. The following block starts at y 30. A 70px paragraph places
``a אב`` beside a 20 by 10 float at x 20 y 0 with a, space, ב, and א at x 20,
30, 40, and 50. The following block starts at y 10. A justified Hebrew line,
a relative inline beside the float, and direction rtl stay without those
glyphs or rejected.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree that omits the float glyphs exits 0 with passed false.
"""

from __future__ import annotations

import json

_BESIDE = '<div id="page"><div id="line"><div id="flo"></div>אבגד</div><div id="next">Z</div></div>'
_BESIDE_CSS = (
    "#line, #next { font-size: 10px; line-height: 10px; } "
    "#line { width: 60px; } #flo { float: left; width: 20px; height: 20px; }"
)
_UNDER = '<div id="page"><div id="line"><div id="flo"></div>aa אבגד</div><div id="next">Z</div></div>'
_UNDER_CSS = (
    "#line, #next { font-size: 10px; line-height: 10px; } "
    "#line { width: 50px; } #flo { float: left; width: 20px; height: 20px; }"
)
_MIXED = '<div id="page"><div id="line"><div id="flo"></div>a אב</div><div id="next">Z</div></div>'
_MIXED_CSS = (
    "#line, #next { font-size: 10px; line-height: 10px; } "
    "#line { width: 70px; } #flo { float: left; width: 20px; height: 10px; }"
)
_JUSTIFY = '<div id="page"><div id="line">aa אבגד bb</div><div id="next">Z</div></div>'
_JUSTIFY_CSS = (
    "#line, #next { font-size: 10px; line-height: 10px; } "
    "#line { width: 110px; text-align: justify; }"
)
_RELATIVE = (
    '<div id="page"><div id="line"><div id="flo"></div>'
    '<span id="rel">אבגד</span></div><div id="next">Z</div></div>'
)
_RELATIVE_CSS = (
    "#line, #next { font-size: 10px; line-height: 10px; } "
    "#line { width: 60px; } #flo { float: left; width: 20px; height: 20px; } "
    "#rel { position: relative; left: 4px; }"
)
_RTL = '<div id="page"><div id="line"><div id="flo"></div>אבגד</div><div id="next">Z</div></div>'
_RTL_CSS = (
    "#line, #next { font-size: 10px; line-height: 10px; } "
    "#line { direction: rtl; width: 60px; } #flo { float: left; width: 20px; height: 20px; }"
)


def _box(boxes: object, ident: str) -> dict[str, object] | None:
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if isinstance(item, dict) and item.get("id") == ident:
            return item
    return None


def _lines(box: dict[str, object] | None) -> list[dict[str, object]] | None:
    if box is None or not isinstance(box.get("lines"), list):
        return None
    lines = box["lines"]
    if not lines or not all(isinstance(item, dict) for item in lines):
        return None
    return lines


def _placed(markup: str, stylesheet: str) -> dict[str, object]:
    from blackhole_agent.css_normal_flow import layout_normal_flow

    placed = layout_normal_flow(markup, stylesheet, viewport_width=200)
    return placed if isinstance(placed, dict) else {"outcome": "error", "boxes": None}


def _observe_case(markup: str, stylesheet: str) -> dict[str, object]:
    placed = _placed(markup, stylesheet)
    line = _box(placed.get("boxes"), "line")
    nxt = _box(placed.get("boxes"), "next")
    flo = _box(placed.get("boxes"), "flo")
    return {
        "outcome": placed.get("outcome"),
        "reason": placed.get("reason"),
        "lines": _lines(line),
        "next_y": None if nxt is None else nxt.get("y"),
        "flo": None
        if flo is None
        else {"x": flo.get("x"), "y": flo.get("y")},
    }


def _glyphs(row: dict[str, object]) -> object:
    return row.get("glyphs")


def observe() -> tuple[bool, dict[str, object]]:
    try:
        beside = _observe_case(_BESIDE, _BESIDE_CSS)
        under = _observe_case(_UNDER, _UNDER_CSS)
        mixed = _observe_case(_MIXED, _MIXED_CSS)
        justified = _observe_case(_JUSTIFY, _JUSTIFY_CSS)
        relative = _observe_case(_RELATIVE, _RELATIVE_CSS)
        rtl = _observe_case(_RTL, _RTL_CSS)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    beside_lines = beside["lines"] if isinstance(beside["lines"], list) else []
    under_lines = under["lines"] if isinstance(under["lines"], list) else []
    mixed_lines = mixed["lines"] if isinstance(mixed["lines"], list) else []
    justified_lines = justified["lines"] if isinstance(justified["lines"], list) else []
    relative_lines = relative["lines"] if isinstance(relative["lines"], list) else []
    under_first = under_lines[0] if under_lines else {}
    under_second = under_lines[1] if len(under_lines) > 1 else {}
    beside_line = beside_lines[0] if beside_lines else {}
    mixed_line = mixed_lines[0] if mixed_lines else {}
    justified_line = justified_lines[0] if justified_lines else {}
    relative_line = relative_lines[0] if relative_lines else {}
    hebrew = [
        {"ch": "ד", "x": 20, "width": 10},
        {"ch": "ג", "x": 30, "width": 10},
        {"ch": "ב", "x": 40, "width": 10},
        {"ch": "א", "x": 50, "width": 10},
    ]
    restored = [
        {"ch": "ד", "x": 0, "width": 10},
        {"ch": "ג", "x": 10, "width": 10},
        {"ch": "ב", "x": 20, "width": 10},
        {"ch": "א", "x": 30, "width": 10},
    ]
    embedded = [
        {"ch": "a", "x": 20, "width": 10},
        {"ch": " ", "x": 30, "width": 10},
        {"ch": "ב", "x": 40, "width": 10},
        {"ch": "א", "x": 50, "width": 10},
    ]
    observed: dict[str, object] = {
        "beside": beside,
        "under": under,
        "mixed": mixed,
        "justified": justified,
        "relative": relative,
        "rtl": rtl,
    }
    checks = {
        "beside_line": len(beside_lines) == 1
        and beside["outcome"] == "placed"
        and beside_line.get("text") == "אבגד"
        and beside_line.get("x") == 20
        and beside_line.get("y") == 0
        and beside_line.get("height") == 10
        and _glyphs(beside_line) == hebrew,
        "beside_float": beside["flo"] == {"x": 0, "y": 0} and beside["next_y"] == 20,
        "under_latin": len(under_lines) == 2
        and under["outcome"] == "placed"
        and under_first.get("text") == "aa"
        and under_first.get("x") == 20
        and under_first.get("y") == 0
        and "glyphs" not in under_first,
        "under_hebrew": under_second.get("text") == "אבגד"
        and under_second.get("x") == 0
        and under_second.get("y") == 20
        and _glyphs(under_second) == restored
        and under["next_y"] == 30,
        "mixed_line": len(mixed_lines) == 1
        and mixed["outcome"] == "placed"
        and mixed_line.get("text") == "a אב"
        and mixed_line.get("x") == 20
        and mixed_line.get("y") == 0
        and _glyphs(mixed_line) == embedded
        and mixed["next_y"] == 10,
        "justify_omits": justified["outcome"] == "placed"
        and len(justified_lines) == 1
        and justified_line.get("text") == "aa אבגד bb"
        and "glyphs" not in justified_line,
        "relative_omits": relative["outcome"] == "placed"
        and len(relative_lines) == 1
        and relative_line.get("text") == "אבגד"
        and "glyphs" not in relative_line,
        "rtl_rejected": rtl["outcome"] == "invalid",
    }
    observed["checks"] = checks
    return all(checks.values()), observed


def main() -> None:
    passed, observed = observe()
    print(json.dumps({"passed": bool(passed), "observed": observed}, ensure_ascii=False))


if __name__ == "__main__":
    main()
