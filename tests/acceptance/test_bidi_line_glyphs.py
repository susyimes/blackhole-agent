"""Place horizontal text at its Unicode bidi visual x.

An LTR line ``aאבb`` keeps source text and reports glyphs left to right as
``a``, bet, alef, ``b``. An 80px RTL line ``אב`` is parked on the inline end
and reports bet then alef. The following block stays at y 10.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree that still paints source order exits 0 with passed
false.
"""

from __future__ import annotations

import json

_MIXED_MARKUP = '<div id="page"><div id="line">aאבb</div><div id="next">Z</div></div>'
_MIXED_CSS = "#line, #next { font-size: 10px; }"
_RTL_MARKUP = '<div id="page"><div id="line">אב</div><div id="next">Z</div></div>'
_RTL_CSS = "#line, #next { font-size: 10px; } #line { direction: rtl; width: 80px; }"


def _box(boxes: object, ident: str) -> dict[str, object] | None:
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if isinstance(item, dict) and item.get("id") == ident:
            return item
    return None


def _line(box: dict[str, object] | None) -> dict[str, object] | None:
    if box is None or not isinstance(box.get("lines"), list):
        return None
    lines = box["lines"]
    if not lines or not isinstance(lines[0], dict):
        return None
    return lines[0]


def _glyphs(box: dict[str, object] | None) -> list[dict[str, object]] | None:
    line = _line(box)
    glyphs = None if line is None else line.get("glyphs")
    if not isinstance(glyphs, list) or not glyphs:
        return None
    if not all(isinstance(item, dict) for item in glyphs):
        return None
    return glyphs


def _placed(markup: str, stylesheet: str) -> dict[str, object]:
    from blackhole_agent.css_normal_flow import layout_normal_flow

    placed = layout_normal_flow(markup, stylesheet, viewport_width=200)
    return placed if isinstance(placed, dict) else {"outcome": "error", "boxes": None}


def observe() -> tuple[bool, dict[str, object]]:
    try:
        mixed = _placed(_MIXED_MARKUP, _MIXED_CSS)
        rtl = _placed(_RTL_MARKUP, _RTL_CSS)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    mixed_line = _box(mixed.get("boxes"), "line")
    mixed_next = _box(mixed.get("boxes"), "next")
    rtl_line = _box(rtl.get("boxes"), "line")
    rtl_next = _box(rtl.get("boxes"), "next")
    mixed_glyphs = _glyphs(mixed_line)
    rtl_glyphs = _glyphs(rtl_line)
    mixed_text = None if _line(mixed_line) is None else _line(mixed_line).get("text")
    rtl_text = None if _line(rtl_line) is None else _line(rtl_line).get("text")
    observed: dict[str, object] = {
        "mixed_outcome": mixed.get("outcome"),
        "mixed_reason": mixed.get("reason"),
        "mixed_text": mixed_text,
        "mixed_glyphs": mixed_glyphs,
        "mixed_next_y": None if mixed_next is None else mixed_next.get("y"),
        "rtl_outcome": rtl.get("outcome"),
        "rtl_reason": rtl.get("reason"),
        "rtl_text": rtl_text,
        "rtl_glyphs": rtl_glyphs,
        "rtl_x": None if rtl_line is None else rtl_line.get("x"),
        "rtl_next_y": None if rtl_next is None else rtl_next.get("y"),
    }
    checks = {
        "mixed_placed": mixed.get("outcome") == "placed",
        "mixed_source": mixed_text == "aאבb",
        "mixed_glyphs": mixed_glyphs
        == [
            {"ch": "a", "x": 0, "width": 10},
            {"ch": "ב", "x": 10, "width": 10},
            {"ch": "א", "x": 20, "width": 10},
            {"ch": "b", "x": 30, "width": 10},
        ],
        "mixed_next": observed["mixed_next_y"] == 10,
        "rtl_placed": rtl.get("outcome") == "placed",
        "rtl_source": rtl_text == "אב",
        "rtl_glyphs": rtl_glyphs
        == [
            {"ch": "ב", "x": 180, "width": 10},
            {"ch": "א", "x": 190, "width": 10},
        ],
        "rtl_next": observed["rtl_next_y"] == 10,
    }
    observed["checks"] = checks
    return all(checks.values()), observed


def main() -> None:
    passed, observed = observe()
    print(json.dumps({"passed": bool(passed), "observed": observed}, ensure_ascii=False))


if __name__ == "__main__":
    main()
