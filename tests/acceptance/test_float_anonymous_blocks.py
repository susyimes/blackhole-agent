"""Keep loose text when a float shares a block with an in-flow sibling.

A left float, the text AA, a block BB, and the text CC stack in source
order: AA and BB shorten beside the float, and CC starts under it. Text
before the float keeps the full width. A cleared sibling starts at the
float's bottom edge. Two left floats leave AA after both of them. An
inline-block in that mix shares the shortened anonymous line, and the
block sibling stays beside the rest of the float.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A layout that still drops the loose text exits 0 with
passed false.
"""

from __future__ import annotations

import json
import sys

_FONT = "#page { font-size: 10px; line-height: 10px; }\n"
_PAGE = '<div id="page">{body}<div id="next">Z</div></div>'


def _lay(layout, body: str, stylesheet: str, width: int = 200) -> dict[str, object]:
    try:
        placed = layout(_PAGE.format(body=body), _FONT + stylesheet, viewport_width=width)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def _box(boxes: object, ident: str) -> dict[str, object] | None:
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if isinstance(item, dict) and item.get("id") == ident:
            return item
    return None


def _line(boxes: object, text: str) -> dict[str, object] | None:
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if not isinstance(item, dict):
            continue
        for line in item.get("lines") or []:
            if isinstance(line, dict) and line.get("text") == text:
                return line
    return None


def _owner(boxes: object, text: str) -> dict[str, object] | None:
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if not isinstance(item, dict):
            continue
        for line in item.get("lines") or []:
            if isinstance(line, dict) and line.get("text") == text:
                return item
    return None


def _at(line: dict[str, object] | None) -> dict[str, object]:
    if line is None:
        return {"text": None, "x": None, "y": None, "h": None, "w": None}
    return {
        "text": line.get("text"),
        "x": line.get("x"),
        "y": line.get("y"),
        "h": line.get("height"),
        "w": line.get("content_width"),
    }


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without placement still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    cases = {
        "beside": _lay(
            layout_normal_flow,
            '<div id="p"><div id="f">F</div>AA<div id="b">BB</div>CC</div>',
            "#f { float: left; width: 30px; height: 20px; }\n",
        ),
        "before": _lay(
            layout_normal_flow,
            '<div id="p">AA<div id="f">F</div>BB<div id="b">CC</div></div>',
            "#f { float: left; width: 30px; height: 20px; }\n",
        ),
        "clear": _lay(
            layout_normal_flow,
            '<div id="p"><div id="f">F</div>AA<div id="b">BB</div></div>',
            "#f { float: left; width: 30px; height: 20px; }\n#b { clear: left; }\n",
        ),
        "pair": _lay(
            layout_normal_flow,
            '<div id="p"><div id="f">F</div><div id="g">G</div>AA<div id="b">BB</div></div>',
            "#f, #g { float: left; width: 30px; height: 10px; }\n",
        ),
        "blank": _lay(
            layout_normal_flow,
            '<div id="p"><div id="f">F</div>\n<div id="b">BB</div></div>',
            "#f { float: left; width: 30px; height: 20px; }\n",
        ),
        "atom": _lay(
            layout_normal_flow,
            '<div id="p"><div id="f">F</div>AA<span id="atom">BB</span><div id="b">CC</div></div>',
            "#f { float: left; width: 30px; height: 20px; }\n#atom { display: inline-block; }\n",
        ),
    }
    observed: dict[str, object] = {}
    for name, result in cases.items():
        boxes = result.get("boxes")
        observed[name] = {
            "outcome": result.get("outcome"),
            "reason": result.get("reason"),
            "p": None
            if _box(boxes, "p") is None
            else {
                "h": _box(boxes, "p").get("content_height"),
                "w": _box(boxes, "p").get("content_width"),
                "lines": len(_box(boxes, "p").get("lines") or []),
            },
            "f": None
            if _box(boxes, "f") is None
            else {"x": _box(boxes, "f").get("x"), "y": _box(boxes, "f").get("y"), "w": _box(boxes, "f").get("content_width"), "h": _box(boxes, "f").get("content_height")},
            "g": None
            if _box(boxes, "g") is None
            else {"x": _box(boxes, "g").get("x"), "y": _box(boxes, "g").get("y")},
            "b": None
            if _box(boxes, "b") is None
            else {"y": _box(boxes, "b").get("y"), "h": _box(boxes, "b").get("content_height")},
            "next": None if _box(boxes, "next") is None else {"y": _box(boxes, "next").get("y")},
            "lines": {text: _at(_line(boxes, text)) for text in ("AA", "BB", "CC")},
            "owner_w": None if _owner(boxes, "AA") is None else _owner(boxes, "AA").get("content_width"),
        }
    beside = cases["beside"]
    before = cases["before"]
    cleared = cases["clear"]
    pair = cases["pair"]
    blank = cases["blank"]
    atom = cases["atom"]
    beside_boxes = beside.get("boxes")
    before_boxes = before.get("boxes")
    clear_boxes = cleared.get("boxes")
    pair_boxes = pair.get("boxes")
    blank_boxes = blank.get("boxes")
    checks = {
        "float_then_text_shortens_both_lines_and_releases_the_tail": (
            beside.get("outcome") == "placed"
            and _box(beside_boxes, "p").get("lines") == []
            and _box(beside_boxes, "p").get("content_width") == 200
            and _box(beside_boxes, "p").get("content_height") == 30
            and _at(_line(beside_boxes, "AA")) == {"text": "AA", "x": 30, "y": 0, "h": 10, "w": 20}
            and _owner(beside_boxes, "AA").get("content_width") == 200
            and _box(beside_boxes, "b").get("y") == 10
            and _at(_line(beside_boxes, "BB")) == {"text": "BB", "x": 30, "y": 10, "h": 10, "w": 20}
            and _at(_line(beside_boxes, "CC")) == {"text": "CC", "x": 0, "y": 20, "h": 10, "w": 20}
            and _box(beside_boxes, "f").get("y") == 0
            and _box(beside_boxes, "next").get("y") == 30
        ),
        "text_before_the_float_keeps_the_full_line": (
            before.get("outcome") == "placed"
            and _at(_line(before_boxes, "AA")) == {"text": "AA", "x": 0, "y": 0, "h": 10, "w": 20}
            and _box(before_boxes, "f").get("y") == 10
            and _at(_line(before_boxes, "BB")) == {"text": "BB", "x": 30, "y": 10, "h": 10, "w": 20}
            and _box(before_boxes, "b").get("y") == 20
            and _at(_line(before_boxes, "CC")) == {"text": "CC", "x": 30, "y": 20, "h": 10, "w": 20}
            and _box(before_boxes, "next").get("y") == 30
        ),
        "cleared_sibling_starts_below_the_float": (
            cleared.get("outcome") == "placed"
            and _at(_line(clear_boxes, "AA")) == {"text": "AA", "x": 30, "y": 0, "h": 10, "w": 20}
            and _box(clear_boxes, "b").get("y") == 20
            and _at(_line(clear_boxes, "BB")) == {"text": "BB", "x": 0, "y": 20, "h": 10, "w": 20}
            and _box(clear_boxes, "next").get("y") == 30
        ),
        "second_left_float_pushes_the_anonymous_line": (
            pair.get("outcome") == "placed"
            and _box(pair_boxes, "f").get("x") == 0
            and _box(pair_boxes, "g").get("x") == 30
            and _box(pair_boxes, "g").get("y") == 0
            and _at(_line(pair_boxes, "AA")) == {"text": "AA", "x": 60, "y": 0, "h": 10, "w": 20}
            and _box(pair_boxes, "b").get("y") == 10
            and _at(_line(pair_boxes, "BB")) == {"text": "BB", "x": 0, "y": 10, "h": 10, "w": 20}
        ),
        "collapsible_whitespace_adds_no_anonymous_line": (
            blank.get("outcome") == "placed"
            and _line(blank_boxes, "AA") is None
            and _box(blank_boxes, "b").get("y") == 0
            and _at(_line(blank_boxes, "BB")) == {"text": "BB", "x": 30, "y": 0, "h": 10, "w": 20}
            and _box(blank_boxes, "p").get("content_height") == 20
        ),
        "inline_block_beside_a_float_and_a_block_shares_the_shortened_line": (
            atom.get("outcome") == "placed"
            and _at(_line(atom.get("boxes"), "AA")) == {"text": "AA", "x": 30, "y": 0, "h": 10, "w": 40}
            and _box(atom.get("boxes"), "b").get("y") == 10
            and _at(_line(atom.get("boxes"), "CC")) == {"text": "CC", "x": 30, "y": 10, "h": 10, "w": 20}
            and _box(atom.get("boxes"), "p").get("content_height") == 20
            and _box(atom.get("boxes"), "next").get("y") == 20
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
