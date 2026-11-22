"""Place a list item marker from the list-item counter.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree that still lays an li out as a plain block reports
passed false.
"""

from __future__ import annotations

import json

_OUTSIDE = (
    '<ol id="one"><li id="a">A</li><li id="gap"></li><li id="b">B</li></ol>'
    '<ol id="two"><li id="c">C</li></ol><div id="next"></div>',
    "",
)
_DISC = ('<ul><li id="a">A</li></ul>', "")
_INITIAL = ('<div id="a">A</div>', "#a { display: list-item; }")
_INSIDE = (
    '<ol id="page"><li id="a">A B</li><div id="next"></div></ol>',
    "#page { width: 64px; } li { list-style-position: inside; }",
)
_NESTED = (
    '<ol id="outer"><li id="a">A</li><li id="mid"><ol id="inner"><li id="b">B</li></ol></li>'
    '<li id="c">C</li></ol>',
    "",
)
_REVERSED = (
    '<ol id="page"><li id="a">A</li><li id="b">B</li><li id="c">C</li></ol>',
    "#page { counter-reset: reversed(list-item); }",
)
_ALPHA = (
    '<ol id="page"><li id="a">A</li><li id="b">B</li></ol>',
    "#page { list-style-type: lower-alpha; }",
)
_RELATIVE = (
    '<ol><li id="a">A</li><li id="b">B</li></ol>',
    "#b { position: relative; left: 7px; top: 5px; }",
)
_NONE = ('<ol><li id="a">A</li></ol>', "li { list-style-type: none; }")
_BAD_TYPE = ('<ol><li id="a">A</li></ol>', "li { list-style-type: hebrew; }")
_BAD_INSIDE = (
    '<ol><li id="bad"><div id="kid"></div></li></ol>',
    "li { list-style-position: inside; }",
)
_PLAIN = ('<div id="page"></div>', "#page { width: 40px; height: 10px; }")


def _place(function, markup: str, stylesheet: str) -> dict[str, object]:
    try:
        result = function(markup, stylesheet, viewport_width=200)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}"}
    if not isinstance(result, dict):
        return {"outcome": "error", "reason": "result"}
    return result


def _box(result: dict[str, object], box_id: str) -> dict[str, object] | None:
    boxes = result.get("boxes")
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if isinstance(item, dict) and item.get("id") == box_id:
            return item
    return None


def _line(box: dict[str, object] | None, index: int = 0) -> dict[str, object] | None:
    if box is None or not isinstance(box.get("lines"), list):
        return None
    lines = box["lines"]
    if index >= len(lines) or not isinstance(lines[index], dict):
        return None
    line = lines[index]
    return {
        "text": line.get("text"),
        "x": line.get("x"),
        "y": line.get("y"),
        "content_width": line.get("content_width"),
    }


def _marker(box: dict[str, object] | None) -> dict[str, object] | None:
    if box is None or not isinstance(box.get("marker"), dict):
        return None
    marker = box["marker"]
    return {
        "text": marker.get("text"),
        "x": marker.get("x"),
        "y": marker.get("y"),
        "width": marker.get("width"),
    }


def _pack(box: dict[str, object] | None) -> dict[str, object] | None:
    if box is None:
        return None
    return {
        "x": box.get("x"),
        "y": box.get("y"),
        "content_height": box.get("content_height"),
        "marker": _marker(box),
        "line": _line(box, 0),
        "next_line": _line(box, 1),
    }


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without the layout still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    outside = _place(layout_normal_flow, *_OUTSIDE)
    disc = _place(layout_normal_flow, *_DISC)
    initial = _place(layout_normal_flow, *_INITIAL)
    inside = _place(layout_normal_flow, *_INSIDE)
    nested = _place(layout_normal_flow, *_NESTED)
    reversed_list = _place(layout_normal_flow, *_REVERSED)
    alpha = _place(layout_normal_flow, *_ALPHA)
    relative = _place(layout_normal_flow, *_RELATIVE)
    blank = _place(layout_normal_flow, *_NONE)
    bad_type = _place(layout_normal_flow, *_BAD_TYPE)
    bad_inside = _place(layout_normal_flow, *_BAD_INSIDE)
    plain = _place(layout_normal_flow, *_PLAIN)

    boxes = {
        "a": _box(outside, "a"),
        "gap": _box(outside, "gap"),
        "b": _box(outside, "b"),
        "c": _box(outside, "c"),
        "next": _box(outside, "next"),
        "disc": _box(disc, "a"),
        "initial": _box(initial, "a"),
        "inside": _box(inside, "a"),
        "inside_next": _box(inside, "next"),
        "nested_a": _box(nested, "a"),
        "mid": _box(nested, "mid"),
        "nested_b": _box(nested, "b"),
        "nested_c": _box(nested, "c"),
        "rev_a": _box(reversed_list, "a"),
        "rev_b": _box(reversed_list, "b"),
        "rev_c": _box(reversed_list, "c"),
        "alpha_a": _box(alpha, "a"),
        "alpha_b": _box(alpha, "b"),
        "rel_b": _box(relative, "b"),
        "none": _box(blank, "a"),
        "plain": _box(plain, "page"),
    }
    observed: dict[str, object] = {
        name: _pack(box) for name, box in boxes.items() if name not in {"next", "inside_next", "plain"}
    }
    observed["next_y"] = None if boxes["next"] is None else boxes["next"].get("y")
    observed["inside_next_y"] = None if boxes["inside_next"] is None else boxes["inside_next"].get("y")
    observed["plain"] = None if boxes["plain"] is None else {
        "content_width": boxes["plain"].get("content_width"),
        "content_height": boxes["plain"].get("content_height"),
    }
    observed["bad_type"] = {"outcome": bad_type.get("outcome"), "reason": bad_type.get("reason")}
    observed["bad_inside"] = {"outcome": bad_inside.get("outcome"), "reason": bad_inside.get("reason")}
    observed["outcomes"] = {
        "outside": outside.get("outcome"),
        "disc": disc.get("outcome"),
        "initial": initial.get("outcome"),
        "inside": inside.get("outcome"),
        "nested": nested.get("outcome"),
        "reversed": reversed_list.get("outcome"),
        "alpha": alpha.get("outcome"),
        "relative": relative.get("outcome"),
        "none": blank.get("outcome"),
        "plain": plain.get("outcome"),
    }

    def marker_ends_on_line(box: dict[str, object] | None, text: str, line_text: str, y: int) -> bool:
        marker = _marker(box)
        line = _line(box)
        return (
            marker is not None
            and line is not None
            and marker["text"] == text
            and marker["width"] == 48
            and marker["y"] == y
            and line["text"] == line_text
            and isinstance(marker["x"], int)
            and isinstance(line["x"], int)
            and marker["x"] + 48 == line["x"]
            and line["y"] == y
        )

    first = boxes["a"]
    gap = boxes["gap"]
    second = boxes["b"]
    restarted = boxes["c"]
    inside_box = boxes["inside"]
    inside_line = _line(inside_box, 0)
    inside_next = _line(inside_box, 1)
    inside_marker = _marker(inside_box)
    none_box = boxes["none"]
    rel = boxes["rel_b"]
    passed = (
        outside.get("outcome") == "placed"
        and marker_ends_on_line(first, "1. ", "A", 0)
        and first is not None
        and first.get("x") == 0
        and first.get("content_height") == 16
        and _line(first) is not None
        and _line(first)["x"] == 0
        and gap is not None
        and gap.get("y") == 16
        and gap.get("content_height") == 16
        and _marker(gap) == {"text": "2. ", "x": -48, "y": 16, "width": 48}
        and not gap.get("lines")
        and marker_ends_on_line(second, "3. ", "B", 32)
        and second is not None
        and second.get("y") == 32
        and marker_ends_on_line(restarted, "1. ", "C", 48)
        and restarted is not None
        and restarted.get("y") == 48
        and boxes["next"] is not None
        and boxes["next"].get("y") == 64
        and disc.get("outcome") == "placed"
        and _marker(boxes["disc"]) == {"text": "\u2022 ", "x": -32, "y": 0, "width": 32}
        and _line(boxes["disc"]) is not None
        and _line(boxes["disc"])["x"] == 0
        and initial.get("outcome") == "placed"
        and _marker(boxes["initial"]) == {"text": "\u2022 ", "x": -32, "y": 0, "width": 32}
        and inside.get("outcome") == "placed"
        and inside_marker == {"text": "1. ", "x": 0, "y": 0, "width": 48}
        and inside_line == {"text": "A", "x": 48, "y": 0, "content_width": 16}
        and inside_next == {"text": "B", "x": 0, "y": 16, "content_width": 16}
        and inside_box is not None
        and inside_box.get("content_height") == 32
        and boxes["inside_next"] is not None
        and boxes["inside_next"].get("y") == 32
        and nested.get("outcome") == "placed"
        and _marker(boxes["nested_a"]) is not None
        and _marker(boxes["nested_a"])["text"] == "1. "
        and _marker(boxes["mid"]) is not None
        and _marker(boxes["mid"])["text"] == "2. "
        and boxes["mid"] is not None
        and boxes["mid"].get("y") == 16
        and _marker(boxes["nested_b"]) is not None
        and _marker(boxes["nested_b"])["text"] == "1. "
        and boxes["nested_b"] is not None
        and boxes["nested_b"].get("y") == 16
        and _marker(boxes["nested_c"]) is not None
        and _marker(boxes["nested_c"])["text"] == "3. "
        and boxes["nested_c"] is not None
        and boxes["nested_c"].get("y") == 32
        and reversed_list.get("outcome") == "placed"
        and _marker(boxes["rev_a"]) is not None
        and _marker(boxes["rev_a"])["text"] == "3. "
        and _marker(boxes["rev_b"]) is not None
        and _marker(boxes["rev_b"])["text"] == "2. "
        and _marker(boxes["rev_c"]) is not None
        and _marker(boxes["rev_c"])["text"] == "1. "
        and alpha.get("outcome") == "placed"
        and _marker(boxes["alpha_a"]) == {"text": "a. ", "x": -48, "y": 0, "width": 48}
        and _marker(boxes["alpha_b"]) is not None
        and _marker(boxes["alpha_b"])["text"] == "b. "
        and _marker(boxes["alpha_b"])["y"] == 16
        and relative.get("outcome") == "placed"
        and rel is not None
        and rel.get("x") == 7
        and rel.get("y") == 21
        and _line(rel) is not None
        and _line(rel)["x"] == 7
        and _marker(rel) == {"text": "2. ", "x": -41, "y": 21, "width": 48}
        and blank.get("outcome") == "placed"
        and none_box is not None
        and "marker" not in none_box
        and _line(none_box) is not None
        and _line(none_box)["text"] == "A"
        and _line(none_box)["x"] == 0
        and bad_type.get("outcome") == "invalid"
        and bad_type.get("reason") == "list-style-type is invalid"
        and bad_inside.get("outcome") == "invalid"
        and bad_inside.get("reason") == "inside marker content is unsupported"
        and plain.get("outcome") == "placed"
        and boxes["plain"] is not None
        and boxes["plain"].get("content_width") == 40
        and boxes["plain"].get("content_height") == 10
    )
    return bool(passed), observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
