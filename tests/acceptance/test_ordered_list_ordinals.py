"""Number ordered-list markers from start, reversed, and value.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree that ignores those attributes reports passed false.
"""

from __future__ import annotations

import json

_PAGE = "#page { width: 40px; font-size: 10px; line-height: 10px; } li { list-style-position: inside; }"


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


def _line(box: dict[str, object] | None) -> dict[str, object] | None:
    if box is None or not isinstance(box.get("lines"), list) or not box["lines"]:
        return None
    line = box["lines"][0]
    if not isinstance(line, dict):
        return None
    return {
        "text": line.get("text"),
        "x": line.get("x"),
        "y": line.get("y"),
        "content_width": line.get("content_width"),
    }


def _texts(result: dict[str, object], *ids: str) -> list[object]:
    return [None if _marker(_box(result, ident)) is None else _marker(_box(result, ident))["text"] for ident in ids]


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without the layout still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    started = _place(layout_normal_flow, '<ol start="3"><li id="a">A</li><li id="b">B</li></ol>', "")
    reversed_list = _place(
        layout_normal_flow,
        '<ol reversed><li id="a">A</li><li id="b">B</li><li id="c">C</li></ol>',
        "",
    )
    reversed_word = _place(
        layout_normal_flow,
        '<ol reversed="false"><li id="a">A</li><li id="b">B</li><li id="c">C</li></ol>',
        "",
    )
    reversed_start = _place(
        layout_normal_flow,
        '<ol reversed start="1"><li id="a">A</li><li id="b">B</li><li id="c">C</li></ol>',
        "",
    )
    valued = _place(
        layout_normal_flow,
        '<ol><li id="a">A</li><li id="b" value="9">B</li><li id="c">C</li></ol>',
        "",
    )
    parsed = _place(layout_normal_flow, '<ol start=" +3x"><li id="a">A</li><li id="b">B</li></ol>', "")
    invalid = _place(layout_normal_flow, '<ol start="+"><li id="a">A</li></ol>', "")
    bullets = _place(
        layout_normal_flow,
        '<ul id="u" start="5"><li id="a">A</li><li id="b">B</li></ul>',
        "#u { list-style-type: decimal; }",
    )
    author_reset = _place(
        layout_normal_flow,
        '<ol id="o" start="3"><li id="a">A</li></ol>',
        "#o { counter-reset: list-item 7; }",
    )
    author_set = _place(
        layout_normal_flow,
        '<ol><li id="a">A</li><li id="b" value="9">B</li></ol>',
        "#b { counter-set: list-item 4; }",
    )
    author_none = _place(
        layout_normal_flow,
        '<ol id="o" start="3"><li id="a">A</li><li id="b">B</li></ol>',
        "#o { counter-reset: none; }",
    )
    blocked = _place(
        layout_normal_flow,
        '<ol><li id="a" value="9">A</li><li id="b">B</li></ol>',
        "#a { display: block; }",
    )
    inside = _place(
        layout_normal_flow,
        '<ol id="page" start="10"><li id="a">A</li><div id="next"></div></ol>',
        _PAGE,
    )
    plain = _place(
        layout_normal_flow,
        '<ol id="page"><li id="a">A</li><div id="next"></div></ol>',
        _PAGE,
    )

    inside_item = _box(inside, "a")
    inside_next = _box(inside, "next")
    plain_item = _box(plain, "a")
    plain_next = _box(plain, "next")
    started_a = _box(started, "a")
    observed = {
        "started": _texts(started, "a", "b"),
        "started_line_x": None if _line(started_a) is None else _line(started_a)["x"],
        "reversed": _texts(reversed_list, "a", "b", "c"),
        "reversed_word": _texts(reversed_word, "a", "b", "c"),
        "reversed_start": _texts(reversed_start, "a", "b", "c"),
        "valued": _texts(valued, "a", "b", "c"),
        "parsed": _texts(parsed, "a", "b"),
        "invalid": _texts(invalid, "a"),
        "ul": _texts(bullets, "a", "b"),
        "author_reset": _texts(author_reset, "a"),
        "author_set": _texts(author_set, "a", "b"),
        "author_none": _texts(author_none, "a", "b"),
        "blocked": _texts(blocked, "b"),
        "inside": {
            "marker": _marker(inside_item),
            "line": _line(inside_item),
            "height": None if inside_item is None else inside_item.get("content_height"),
            "next_y": None if inside_next is None else inside_next.get("y"),
            "lines": None if inside_item is None else len(inside_item.get("lines") or []),
        },
        "plain": {
            "marker": _marker(plain_item),
            "line": _line(plain_item),
            "height": None if plain_item is None else plain_item.get("content_height"),
            "next_y": None if plain_next is None else plain_next.get("y"),
        },
        "outcomes": {
            "started": started.get("outcome"),
            "reversed": reversed_list.get("outcome"),
            "inside": inside.get("outcome"),
            "plain": plain.get("outcome"),
            "blocked": blocked.get("outcome"),
        },
    }
    passed = (
        started.get("outcome") == "placed"
        and observed["started"] == ["3. ", "4. "]
        and observed["started_line_x"] == 0
        and reversed_list.get("outcome") == "placed"
        and observed["reversed"] == ["3. ", "2. ", "1. "]
        and observed["reversed_word"] == ["3. ", "2. ", "1. "]
        and observed["reversed_start"] == ["1. ", "0. ", "-1. "]
        and observed["valued"] == ["1. ", "9. ", "10. "]
        and observed["parsed"] == ["3. ", "4. "]
        and observed["invalid"] == ["1. "]
        and observed["ul"] == ["1. ", "2. "]
        and observed["author_reset"] == ["8. "]
        and observed["author_set"] == ["1. ", "4. "]
        and observed["author_none"] == ["1. ", "2. "]
        and blocked.get("outcome") == "placed"
        and _marker(_box(blocked, "a")) is None
        and observed["blocked"] == ["10. "]
        and inside.get("outcome") == "placed"
        and observed["inside"]["marker"] == {"text": "10. ", "x": 0, "y": 0, "width": 40}
        and observed["inside"]["line"] == {"text": "A", "x": 0, "y": 10, "content_width": 10}
        and observed["inside"]["lines"] == 1
        and observed["inside"]["height"] == 20
        and observed["inside"]["next_y"] == 20
        and plain.get("outcome") == "placed"
        and observed["plain"]["marker"] == {"text": "1. ", "x": 0, "y": 0, "width": 30}
        and observed["plain"]["line"] == {"text": "A", "x": 30, "y": 0, "content_width": 10}
        and observed["plain"]["height"] == 10
        and observed["plain"]["next_y"] == 10
    )
    return bool(passed), observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
