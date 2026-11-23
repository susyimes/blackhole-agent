"""Space characters and words on a horizontal line.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree that still measures AB as two glyph advances reports
passed false.
"""

from __future__ import annotations

import json

_PAIR = (
    "<div id='page'>AB</div>",
    "#page { width: 200px; font-size: 10px; letter-spacing: 5px; }",
    200,
)
_WRAP = (
    "<div id='page'>AB C</div>",
    "#page { width: 40px; font-size: 10px; letter-spacing: 5px; }",
    40,
)
_WORDS = (
    "<div id='page'>A B</div>",
    "#page { width: 200px; font-size: 10px; word-spacing: 8px; }",
    200,
)
_NEGATIVE = (
    "<div id='page'>AB</div>",
    "#page { width: 200px; font-size: 10px; letter-spacing: -5px; }",
    200,
)
_INHERIT = (
    "<div id='page'><div id='spaced'>AB</div><div id='reset'>AB</div></div>",
    "#page { width: 200px; font-size: 10px; letter-spacing: 5px; } #reset { letter-spacing: 0px; }",
    200,
)
_PERCENT = (
    "<div id='page'>AB</div>",
    "#page { width: 200px; font-size: 10px; letter-spacing: 50%; }",
    200,
)
_JUSTIFY = (
    "<div id='page'>AA BB</div>",
    "#page { width: 80px; font-size: 10px; letter-spacing: 2px; text-align: justify-all; }",
    80,
)


def _place(function, markup: str, stylesheet: str, viewport_width: int) -> dict[str, object]:
    try:
        result = function(markup, stylesheet, viewport_width=viewport_width)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    if not isinstance(result, dict):
        return {"outcome": "error", "reason": "result", "boxes": None}
    return result


def _box(result: dict[str, object], box_id: str) -> dict[str, object] | None:
    boxes = result.get("boxes")
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if isinstance(item, dict) and item.get("id") == box_id:
            return item
    return None


def _lines(box: dict[str, object] | None) -> list[dict[str, object]]:
    if box is None or not isinstance(box.get("lines"), list):
        return []
    return [item for item in box["lines"] if isinstance(item, dict)]


def _pack(line: dict[str, object] | None) -> dict[str, object] | None:
    if line is None:
        return None
    return {
        "text": line.get("text"),
        "x": line.get("x"),
        "y": line.get("y"),
        "width": line.get("content_width"),
    }


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without the layout still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    pair = _place(layout_normal_flow, *_PAIR)
    wrapped = _place(layout_normal_flow, *_WRAP)
    words = _place(layout_normal_flow, *_WORDS)
    negative = _place(layout_normal_flow, *_NEGATIVE)
    inherited = _place(layout_normal_flow, *_INHERIT)
    percent = _place(layout_normal_flow, *_PERCENT)
    justified = _place(layout_normal_flow, *_JUSTIFY)
    pair_lines = _lines(_box(pair, "page"))
    wrap_lines = _lines(_box(wrapped, "page"))
    word_lines = _lines(_box(words, "page"))
    negative_lines = _lines(_box(negative, "page"))
    spaced = _lines(_box(inherited, "spaced"))
    reset = _lines(_box(inherited, "reset"))
    observed: dict[str, object] = {
        "pair": [_pack(line) for line in pair_lines],
        "wrap": [_pack(line) for line in wrap_lines],
        "words": [_pack(line) for line in word_lines],
        "negative": [_pack(line) for line in negative_lines],
        "spaced": [_pack(line) for line in spaced],
        "reset": [_pack(line) for line in reset],
        "percent": percent.get("outcome"),
        "percent_reason": percent.get("reason"),
        "justify": justified.get("outcome"),
        "justify_reason": justified.get("reason"),
    }
    passed = (
        pair.get("outcome") == "placed"
        and len(pair_lines) == 1
        and pair_lines[0].get("text") == "AB"
        and pair_lines[0].get("x") == 0
        and pair_lines[0].get("content_width") == 25
        and wrapped.get("outcome") == "placed"
        and len(wrap_lines) == 2
        and wrap_lines[0].get("text") == "AB"
        and wrap_lines[0].get("content_width") == 25
        and wrap_lines[0].get("y") == 0
        and wrap_lines[1].get("text") == "C"
        and wrap_lines[1].get("content_width") == 10
        and wrap_lines[1].get("x") == 0
        and wrap_lines[1].get("y") == 10
        and words.get("outcome") == "placed"
        and len(word_lines) == 1
        and word_lines[0].get("text") == "A B"
        and word_lines[0].get("content_width") == 38
        and negative.get("outcome") == "placed"
        and len(negative_lines) == 1
        and negative_lines[0].get("text") == "AB"
        and negative_lines[0].get("content_width") == 15
        and inherited.get("outcome") == "placed"
        and len(spaced) == 1
        and spaced[0].get("text") == "AB"
        and spaced[0].get("content_width") == 25
        and len(reset) == 1
        and reset[0].get("text") == "AB"
        and reset[0].get("content_width") == 20
        and percent.get("outcome") == "invalid"
        and percent.get("reason") == "letter-spacing is invalid"
        and justified.get("outcome") == "invalid"
        and justified.get("reason") == "spaced justification is unsupported"
    )
    return bool(passed), observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
