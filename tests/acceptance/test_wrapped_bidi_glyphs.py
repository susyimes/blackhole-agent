"""Paint wrapped horizontal lines at their Unicode bidi visual x.

An RTL paragraph ``אבגד הוזח`` in a 40px box keeps both source lines and
parks each visual line on the inline end. An LTR paragraph ``aa אבגד`` in a
30px box keeps ``aa`` without glyphs and paints the wrapped Hebrew word
reversed. The following block stays at y 20. A one-line RTL paragraph still
parks on the inline end.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree that omits wrapped glyphs exits 0 with passed false.
"""

from __future__ import annotations

import json

_RTL_MARKUP = '<div id="page"><div id="line">אבגד הוזח</div><div id="next">Z</div></div>'
_RTL_CSS = "#line, #next { font-size: 10px; } #line { direction: rtl; width: 40px; }"
_LTR_MARKUP = '<div id="page"><div id="line">aa אבגד</div><div id="next">Z</div></div>'
_LTR_CSS = "#line, #next { font-size: 10px; } #line { width: 30px; }"
_ONE_MARKUP = '<div id="page"><div id="line">אב</div><div id="next">Z</div></div>'
_ONE_CSS = "#line, #next { font-size: 10px; } #line { direction: rtl; width: 80px; }"


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
    return {
        "outcome": placed.get("outcome"),
        "reason": placed.get("reason"),
        "lines": _lines(line),
        "next_y": None if nxt is None else nxt.get("y"),
    }


def observe() -> tuple[bool, dict[str, object]]:
    try:
        rtl = _observe_case(_RTL_MARKUP, _RTL_CSS)
        ltr = _observe_case(_LTR_MARKUP, _LTR_CSS)
        one = _observe_case(_ONE_MARKUP, _ONE_CSS)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    rtl_lines = rtl["lines"] if isinstance(rtl["lines"], list) else []
    ltr_lines = ltr["lines"] if isinstance(ltr["lines"], list) else []
    one_lines = one["lines"] if isinstance(one["lines"], list) else []
    observed: dict[str, object] = {"rtl": rtl, "ltr": ltr, "one": one}
    checks = {
        "rtl_placed": rtl["outcome"] == "placed" and len(rtl_lines) == 2,
        "rtl_source": [row.get("text") for row in rtl_lines] == ["אבגד", "הוזח"],
        "rtl_first": bool(rtl_lines)
        and rtl_lines[0].get("glyphs")
        == [
            {"ch": "ד", "x": 160, "width": 10},
            {"ch": "ג", "x": 170, "width": 10},
            {"ch": "ב", "x": 180, "width": 10},
            {"ch": "א", "x": 190, "width": 10},
        ],
        "rtl_second": len(rtl_lines) > 1
        and rtl_lines[1].get("y") == 10
        and rtl_lines[1].get("glyphs")
        == [
            {"ch": "ח", "x": 160, "width": 10},
            {"ch": "ז", "x": 170, "width": 10},
            {"ch": "ו", "x": 180, "width": 10},
            {"ch": "ה", "x": 190, "width": 10},
        ],
        "rtl_next": rtl["next_y"] == 20,
        "ltr_placed": ltr["outcome"] == "placed" and len(ltr_lines) == 2,
        "ltr_source": [row.get("text") for row in ltr_lines] == ["aa", "אבגד"],
        "ltr_plain": bool(ltr_lines) and "glyphs" not in ltr_lines[0],
        "ltr_hebrew": len(ltr_lines) > 1
        and ltr_lines[1].get("y") == 10
        and ltr_lines[1].get("glyphs")
        == [
            {"ch": "ד", "x": 0, "width": 10},
            {"ch": "ג", "x": 10, "width": 10},
            {"ch": "ב", "x": 20, "width": 10},
            {"ch": "א", "x": 30, "width": 10},
        ],
        "ltr_next": ltr["next_y"] == 20,
        "one_parked": len(one_lines) == 1
        and one_lines[0].get("text") == "אב"
        and one_lines[0].get("glyphs")
        == [
            {"ch": "ב", "x": 180, "width": 10},
            {"ch": "א", "x": 190, "width": 10},
        ]
        and one["next_y"] == 10,
    }
    observed["checks"] = checks
    return all(checks.values()), observed


def main() -> None:
    passed, observed = observe()
    print(json.dumps({"passed": bool(passed), "observed": observed}, ensure_ascii=False))


if __name__ == "__main__":
    main()
