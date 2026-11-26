"""Compress upright digits into one em inside a vertical column.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A column that still gives every digit its own em reports
passed false.
"""

from __future__ import annotations

import json

from blackhole_agent.css_normal_flow import layout_normal_flow

_PAGE = '<div id="page"><div id="v">{text}</div><p id="next">Z</p></div>'
_BASE = "html, body, p { margin: 0px } #page { font-size: 10px; line-height: 10px }\n"


def _lay(text: str, css: str) -> dict[str, object]:
    try:
        result = layout_normal_flow(_PAGE.format(text=text), _BASE + css, viewport_width=120)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}"}
    return result if isinstance(result, dict) else {"outcome": "error", "reason": "result"}


def _box(result: dict[str, object], box_id: str) -> dict[str, object] | None:
    boxes = result.get("boxes")
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if isinstance(item, dict) and item.get("id") == box_id:
            return item
    return None


def _line(result: dict[str, object]) -> dict[str, object] | None:
    box = _box(result, "v")
    lines = box.get("lines") if isinstance(box, dict) else None
    if not isinstance(lines, list) or len(lines) != 1 or not isinstance(lines[0], dict):
        return None
    return lines[0]


def _geometry(result: dict[str, object]) -> dict[str, object] | None:
    if result.get("outcome") != "placed":
        return None
    box = _box(result, "v")
    nxt = _box(result, "next")
    line = _line(result)
    if box is None or nxt is None or line is None:
        return None
    return {
        "border": [box.get("x"), box.get("y"), box.get("border_width"), box.get("border_height")],
        "line": [
            line.get("text"),
            line.get("x"),
            line.get("y"),
            line.get("content_width"),
            line.get("height"),
        ],
        "combines": line.get("combines"),
        "next_y": nxt.get("y"),
    }


def _cluster(text: str, y: int, glyph_y: int) -> dict[str, object]:
    return {
        "text": text,
        "x": 0,
        "y": y,
        "width": 10,
        "height": 10,
        "glyphs": [
            {"text": text[0], "x": 0, "y": glyph_y, "width": 5, "height": 5},
            {"text": text[1], "x": 5, "y": glyph_y, "width": 5, "height": 5},
        ],
    }


def observe() -> tuple[bool, dict[str, object]]:
    upright_css = "#v { writing-mode: vertical-rl } #c { text-combine-upright: all }\n"
    upright = _geometry(_lay('A<span id="c">12</span>B', upright_css))
    left = _geometry(
        _lay(
            'A<span id="c">12</span>B',
            "#v { writing-mode: vertical-lr } #c { text-combine-upright: all }\n",
        )
    )
    pairs = _geometry(
        _lay(
            '<span id="c">A12B34C</span>',
            "#v { writing-mode: vertical-rl } #c { text-combine-upright: digits }\n",
        )
    )
    horizontal = _geometry(_lay('A<span id="c">12</span>B', "#c { text-combine-upright: all }\n"))
    digits_one = _lay('A<span id="c">12</span>B', "#v { writing-mode: vertical-rl } #c { text-combine-upright: digits 1 }\n")
    triple = _lay('<span id="c">123</span>', "#v { writing-mode: vertical-rl } #c { text-combine-upright: all }\n")
    nested = _lay(
        '<span id="c">1<b>2</b></span>',
        "#v { writing-mode: vertical-rl } #c { text-combine-upright: all }\n",
    )
    sideways = _lay(
        'A<span id="c">12</span>B',
        "#v { writing-mode: sideways-lr } #c { text-combine-upright: all }\n",
    )
    expected = {
        "border": [0, 0, 10, 30],
        "line": ["A12B", 0, 0, 10, 30],
        "combines": [_cluster("12", 10, 12)],
        "next_y": 30,
    }
    pair_expected = {
        "border": [0, 0, 10, 50],
        "line": ["A12B34C", 0, 0, 10, 50],
        "combines": [_cluster("12", 10, 12), _cluster("34", 30, 32)],
        "next_y": 50,
    }
    horizontal_expected = {
        "border": [0, 0, 120, 10],
        "line": ["A12B", 0, 0, 40, 10],
        "combines": None,
        "next_y": 10,
    }
    observed = {
        "upright": upright,
        "left": left,
        "pairs": pairs,
        "horizontal": horizontal,
        "digits_one": digits_one.get("reason"),
        "triple": triple.get("reason"),
        "nested": nested.get("reason"),
        "sideways": sideways.get("reason"),
    }
    passed = (
        upright == expected
        and left == expected
        and pairs == pair_expected
        and horizontal == horizontal_expected
        and digits_one.get("outcome") != "placed"
        and digits_one.get("reason") == "text-combine-upright is invalid"
        and triple.get("outcome") != "placed"
        and triple.get("reason") == "text-combine scale is not integral"
        and nested.get("outcome") != "placed"
        and nested.get("reason") == "text-combine content is unsupported"
        and sideways.get("outcome") != "placed"
        and sideways.get("reason") == "text-combine writing mode is unsupported"
    )
    return passed, observed


if __name__ == "__main__":
    try:
        passed, observed = observe()
    except Exception as error:  # noqa: BLE001 - the probe must exit 0 when the outcome is unmet
        passed, observed = False, {"probe_error": f"{type(error).__name__}: {error}"}
    print(json.dumps({"passed": passed, "observed": observed}, separators=(",", ":")))
