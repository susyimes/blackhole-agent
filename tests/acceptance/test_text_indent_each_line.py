"""Indent the first line of each preserved segment.

text-indent:each-line restarts the indent after a preserved newline and
leaves a soft wrap on the content edge. hanging each-line does the opposite
inside each segment. A plain indent still ignores the preserved break.
A repeated each-line keyword is invalid.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree that rejects each-line reports passed false.
"""

from __future__ import annotations

import json

_PAGE = "#page { font-size: 10px; }\n"
_STORY = '<div id="page"><div id="story">AAAA BBBB\nCCCC DDDD</div><div id="next"></div></div>'
_EACH = _PAGE + "#story { width: 70px; white-space: pre-line; text-indent: 20px each-line; } #next { height: 10px; }"
_HANG = _PAGE + "#story { width: 70px; white-space: pre-line; text-indent: hanging each-line 20px; } #next { height: 10px; }"
_PLAIN = _PAGE + "#story { width: 70px; white-space: pre-line; text-indent: 20px; } #next { height: 10px; }"
_SOFT = (
    '<div id="page"><div id="soft">AAAA BBBB</div></div>',
    _PAGE + "#soft { width: 100px; text-indent: each-line 20px; }",
)
_PULL = (
    '<div id="page"><div id="pull">AA\nBB</div></div>',
    _PAGE + "#pull { width: 100px; white-space: pre-line; text-indent: -10px each-line; }",
)
_DUP = (
    '<div id="page"><div id="bad">AA</div></div>',
    _PAGE + "#bad { text-indent: 20px each-line each-line; }",
)


def _place(function, markup: str, stylesheet: str) -> dict[str, object]:
    try:
        result = function(markup, stylesheet, viewport_width=200)
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


def _pack(line: dict[str, object]) -> dict[str, object]:
    return {
        "text": line.get("text"),
        "x": line.get("x"),
        "y": line.get("y"),
        "width": line.get("content_width"),
    }


def _quad(result: dict[str, object]) -> list[dict[str, object]]:
    return [_pack(line) for line in _lines(_box(result, "story"))]


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without the layout still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    each = _place(layout_normal_flow, _STORY, _EACH)
    hanging = _place(layout_normal_flow, _STORY, _HANG)
    plain = _place(layout_normal_flow, _STORY, _PLAIN)
    soft = _place(layout_normal_flow, *_SOFT)
    pulled = _place(layout_normal_flow, *_PULL)
    duplicate = _place(layout_normal_flow, *_DUP)
    each_lines = _quad(each)
    hang_lines = _quad(hanging)
    plain_lines = _quad(plain)
    soft_lines = [_pack(line) for line in _lines(_box(soft, "soft"))]
    pull_lines = [_pack(line) for line in _lines(_box(pulled, "pull"))]
    nxt = _box(each, "next")
    observed: dict[str, object] = {
        "each": each_lines,
        "each_outcome": each.get("outcome"),
        "next_y": None if nxt is None else nxt.get("y"),
        "hanging": hang_lines,
        "hanging_outcome": hanging.get("outcome"),
        "plain": plain_lines,
        "plain_outcome": plain.get("outcome"),
        "soft": soft_lines,
        "soft_outcome": soft.get("outcome"),
        "negative": pull_lines,
        "negative_outcome": pulled.get("outcome"),
        "duplicate_outcome": duplicate.get("outcome"),
        "duplicate_reason": duplicate.get("reason"),
    }
    passed = (
        each.get("outcome") == "placed"
        and each_lines
        == [
            {"text": "AAAA", "x": 20, "y": 0, "width": 40},
            {"text": "BBBB", "x": 0, "y": 10, "width": 40},
            {"text": "CCCC", "x": 20, "y": 20, "width": 40},
            {"text": "DDDD", "x": 0, "y": 30, "width": 40},
        ]
        and nxt is not None
        and nxt.get("y") == 40
        and hanging.get("outcome") == "placed"
        and hang_lines
        == [
            {"text": "AAAA", "x": 0, "y": 0, "width": 40},
            {"text": "BBBB", "x": 20, "y": 10, "width": 40},
            {"text": "CCCC", "x": 0, "y": 20, "width": 40},
            {"text": "DDDD", "x": 20, "y": 30, "width": 40},
        ]
        and plain.get("outcome") == "placed"
        and plain_lines
        == [
            {"text": "AAAA", "x": 20, "y": 0, "width": 40},
            {"text": "BBBB", "x": 0, "y": 10, "width": 40},
            {"text": "CCCC", "x": 0, "y": 20, "width": 40},
            {"text": "DDDD", "x": 0, "y": 30, "width": 40},
        ]
        and soft.get("outcome") == "placed"
        and soft_lines
        == [
            {"text": "AAAA", "x": 20, "y": 0, "width": 40},
            {"text": "BBBB", "x": 0, "y": 10, "width": 40},
        ]
        and pulled.get("outcome") == "placed"
        and pull_lines
        == [
            {"text": "AA", "x": -10, "y": 0, "width": 20},
            {"text": "BB", "x": -10, "y": 10, "width": 20},
        ]
        and duplicate.get("outcome") == "invalid"
        and "text-indent is invalid" in str(duplicate.get("reason") or "")
    )
    return bool(passed), observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
