"""Indent only the first line of a block.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree that still starts every line at the content edge
reports passed false.
"""

from __future__ import annotations

import json

_WRAP = (
    '<div id="page"><div id="story">AAAA BBBB</div><div id="next"></div></div>',
    "#page { width: 100px; font-size: 10px; } #story { text-indent: 20px; } #next { height: 10px; }",
    100,
)
_ANON = (
    '<div id="page">AAAA BBBB<div id="after"></div></div>',
    "#page { width: 100px; font-size: 10px; text-indent: 20px; } #after { height: 10px; }",
    100,
)
_INHERIT = (
    '<div id="page"><div id="outer"><div id="kid">EEEE</div></div><div id="reset">FFFF</div></div>',
    "#page { width: 200px; font-size: 10px; } #outer { text-indent: 20px; } #reset { text-indent: 0px; }",
    200,
)
_PERCENT = (
    '<div id="page"><div id="narrow">GG</div></div>',
    "#page { width: 200px; font-size: 10px; } #narrow { width: 80px; text-indent: 50%; }",
    400,
)
_NEGATIVE = (
    '<div id="page">AAAA BBBB</div>',
    "#page { width: 100px; font-size: 10px; text-indent: -20px; }",
    100,
)
_HANGING = (
    '<div id="page">AAAA</div>',
    "#page { width: 100px; font-size: 10px; text-indent: 20px hanging; }",
    100,
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


def _line_with(result: dict[str, object], text: str) -> dict[str, object] | None:
    boxes = result.get("boxes")
    if not isinstance(boxes, list):
        return None
    for box in boxes:
        if not isinstance(box, dict):
            continue
        for line in _lines(box):
            if line.get("text") == text:
                return line
    return None


def _pack(line: dict[str, object] | None) -> dict[str, object] | None:
    if line is None:
        return None
    return {"text": line.get("text"), "x": line.get("x"), "y": line.get("y"), "width": line.get("content_width")}


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without the layout still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    wrapped = _place(layout_normal_flow, *_WRAP)
    anonymous = _place(layout_normal_flow, *_ANON)
    inherited = _place(layout_normal_flow, *_INHERIT)
    percent = _place(layout_normal_flow, *_PERCENT)
    negative = _place(layout_normal_flow, *_NEGATIVE)
    hanging = _place(layout_normal_flow, *_HANGING)

    story = _lines(_box(wrapped, "story"))
    nxt = _box(wrapped, "next")
    anon_first = _line_with(anonymous, "AAAA")
    anon_second = _line_with(anonymous, "BBBB")
    after = _box(anonymous, "after")
    kid = _lines(_box(inherited, "kid"))
    reset = _lines(_box(inherited, "reset"))
    narrow = _lines(_box(percent, "narrow"))
    pulled = _lines(_box(negative, "page"))

    observed: dict[str, object] = {
        "wrap": [_pack(line) for line in story],
        "next_y": None if nxt is None else nxt.get("y"),
        "anonymous_first": _pack(anon_first),
        "anonymous_second": _pack(anon_second),
        "after_y": None if after is None else after.get("y"),
        "kid": [_pack(line) for line in kid],
        "reset": [_pack(line) for line in reset],
        "percent": [_pack(line) for line in narrow],
        "negative": [_pack(line) for line in pulled],
        "hanging": hanging.get("outcome"),
        "hanging_reason": hanging.get("reason"),
    }
    passed = (
        wrapped.get("outcome") == "placed"
        and len(story) == 2
        and story[0].get("text") == "AAAA"
        and story[0].get("x") == 20
        and story[0].get("y") == 0
        and story[0].get("content_width") == 40
        and story[1].get("text") == "BBBB"
        and story[1].get("x") == 0
        and story[1].get("y") == 10
        and story[1].get("content_width") == 40
        and nxt is not None
        and nxt.get("y") == 20
        and anonymous.get("outcome") == "placed"
        and anon_first is not None
        and anon_first.get("x") == 20
        and anon_first.get("y") == 0
        and anon_second is not None
        and anon_second.get("x") == 0
        and anon_second.get("y") == 10
        and after is not None
        and after.get("y") == 20
        and inherited.get("outcome") == "placed"
        and len(kid) == 1
        and kid[0].get("text") == "EEEE"
        and kid[0].get("x") == 20
        and kid[0].get("y") == 0
        and len(reset) == 1
        and reset[0].get("text") == "FFFF"
        and reset[0].get("x") == 0
        and percent.get("outcome") == "placed"
        and len(narrow) == 1
        and narrow[0].get("text") == "GG"
        and narrow[0].get("x") == 100
        and negative.get("outcome") == "placed"
        and len(pulled) == 1
        and pulled[0].get("text") == "AAAA BBBB"
        and pulled[0].get("x") == -20
        and pulled[0].get("y") == 0
        and hanging.get("outcome") == "invalid"
        and hanging.get("reason") == "text-indent is unsupported"
    )
    return bool(passed), observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
