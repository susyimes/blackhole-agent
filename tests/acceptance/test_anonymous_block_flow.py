"""Keep inline content that shares a block container with a block sibling.

AA, a block BB, and CC stack as an anonymous line, the block, and another
anonymous line. A vertical margin on BB stays between those lines. A 40px
container wraps AA BB before the sibling. text-align center paints AA inside
the anonymous box. An inline-block stays on that line. Whitespace between
blocks adds no line. An inline-block beside a float and a block is rejected.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A layout that still drops the inline runs exits 0 with
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


def _line_with(boxes: object, text: str) -> dict[str, object] | None:
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
        "stack": _lay(layout_normal_flow, '<div id="p">AA<div id="b">BB</div>CC</div>', ""),
        "margin": _lay(
            layout_normal_flow,
            '<div id="p">AA<div id="b">BB</div>CC</div>',
            "#b { margin-top: 10px; margin-bottom: 10px; }\n",
        ),
        "wrap": _lay(
            layout_normal_flow,
            '<div id="p">AA BB<div id="b">CC</div></div>',
            "#p { width: 40px; }\n",
        ),
        "center": _lay(
            layout_normal_flow,
            '<div id="p">AA<div id="b">BB</div></div>',
            "#p { width: 100px; text-align: center; }\n",
        ),
        "atom": _lay(
            layout_normal_flow,
            '<div id="p">AA<span id="atom">BB</span><div id="b">CC</div></div>',
            "#atom { display: inline-block; }\n",
        ),
        "blank": _lay(layout_normal_flow, '<div id="p">\n<div id="b">BB</div>\n</div>', ""),
        "float": _lay(
            layout_normal_flow,
            '<div id="p"><div id="f">F</div>AA<span id="atom">BB</span><div id="b">CC</div></div>',
            "#f { float: left; }\n#atom { display: inline-block; }\n",
        ),
    }
    observed: dict[str, object] = {}
    for name, result in cases.items():
        boxes = result.get("boxes")
        observed[name] = {
            "outcome": result.get("outcome"),
            "reason": result.get("reason"),
            "p": None if _box(boxes, "p") is None else {
                "y": _box(boxes, "p").get("y"),
                "h": _box(boxes, "p").get("content_height"),
                "w": _box(boxes, "p").get("content_width"),
                "lines": len(_box(boxes, "p").get("lines") or []),
            },
            "b": None if _box(boxes, "b") is None else {
                "y": _box(boxes, "b").get("y"),
                "h": _box(boxes, "b").get("content_height"),
            },
            "next": None if _box(boxes, "next") is None else {"y": _box(boxes, "next").get("y")},
            "lines": {
                text: _at(_line_with(boxes, text))
                for text in ("AA", "BB", "CC", "AA BB")
            },
        }
    stack = cases["stack"]
    margin = cases["margin"]
    wrap = cases["wrap"]
    center = cases["center"]
    atom = cases["atom"]
    blank = cases["blank"]
    floated = cases["float"]
    stack_aa = _line_with(stack.get("boxes"), "AA")
    stack_cc = _line_with(stack.get("boxes"), "CC")
    margin_aa = _line_with(margin.get("boxes"), "AA")
    margin_cc = _line_with(margin.get("boxes"), "CC")
    wrap_aa = _line_with(wrap.get("boxes"), "AA")
    wrap_bb = _line_with(wrap.get("boxes"), "BB")
    center_aa = _line_with(center.get("boxes"), "AA")
    center_owner = _owner(center.get("boxes"), "AA")
    atom_box = _box(atom.get("boxes"), "atom")
    atom_aa = _line_with(atom.get("boxes"), "AA")
    stack_p = _box(stack.get("boxes"), "p")
    checks = {
        "stack_paints_the_inline_runs_around_the_block": (
            stack.get("outcome") == "placed"
            and stack_p is not None
            and stack_p.get("lines") == []
            and stack_p.get("content_height") == 30
            and _at(stack_aa) == {"text": "AA", "x": 0, "y": 0, "h": 10, "w": 20}
            and _box(stack.get("boxes"), "b").get("y") == 10
            and _at(stack_cc) == {"text": "CC", "x": 0, "y": 20, "h": 10, "w": 20}
            and _box(stack.get("boxes"), "next").get("y") == 30
            and _owner(stack.get("boxes"), "AA").get("content_width") == stack_p.get("content_width")
        ),
        "block_margin_stays_between_the_anonymous_lines": (
            margin.get("outcome") == "placed"
            and _at(margin_aa)["y"] == 0
            and _box(margin.get("boxes"), "b").get("y") == 20
            and _at(margin_cc)["y"] == 40
            and _box(margin.get("boxes"), "next").get("y") == 50
            and _box(margin.get("boxes"), "p").get("content_height") == 50
        ),
        "narrow_container_wraps_the_anonymous_line": (
            wrap.get("outcome") == "placed"
            and _box(wrap.get("boxes"), "p").get("content_width") == 40
            and _at(wrap_aa) == {"text": "AA", "x": 0, "y": 0, "h": 10, "w": 20}
            and _at(wrap_bb) == {"text": "BB", "x": 0, "y": 10, "h": 10, "w": 20}
            and _box(wrap.get("boxes"), "b").get("y") == 20
            and _box(wrap.get("boxes"), "next").get("y") == 30
        ),
        "centered_anonymous_line_uses_the_container_width": (
            center.get("outcome") == "placed"
            and center_owner is not None
            and center_owner.get("content_width") == 100
            and _at(center_aa)["x"] == 40
            and _at(center_aa)["y"] == 0
            and _box(center.get("boxes"), "b").get("y") == 10
        ),
        "inline_block_stays_on_the_anonymous_line": (
            atom.get("outcome") == "placed"
            and _at(atom_aa)["x"] == 0
            and _at(atom_aa)["y"] == 0
            and atom_box is not None
            and atom_box.get("x") == 20
            and atom_box.get("y") == 0
            and atom_box.get("content_width") == 20
            and atom_box.get("content_height") == 10
            and _box(atom.get("boxes"), "b").get("y") == 10
            and _box(atom.get("boxes"), "next").get("y") == 20
        ),
        "collapsible_whitespace_adds_no_line": (
            blank.get("outcome") == "placed"
            and _box(blank.get("boxes"), "b").get("y") == 0
            and _box(blank.get("boxes"), "p").get("content_height") == 10
            and _box(blank.get("boxes"), "next").get("y") == 10
        ),
        "inline_block_beside_a_float_and_a_block_is_rejected": (
            floated.get("outcome") == "invalid" and floated.get("boxes") is None
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
