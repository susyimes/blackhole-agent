"""Break a horizontal line when overflow-wrap or word-break says the word may split.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree that still keeps ABCDEF on one 60px line reports
passed false.
"""

from __future__ import annotations

import json

_ANYWHERE = (
    "<div id='page'>ABCDEF</div><div id='next'>Z</div>",
    "#page { width: 30px; font-size: 10px; overflow-wrap: anywhere; } #next { font-size: 10px; }",
    80,
)
_BREAK_ALL = (
    "<div id='page'>ABCDEF</div><div id='next'>Z</div>",
    "#page { width: 30px; font-size: 10px; word-break: break-all; } #next { font-size: 10px; }",
    80,
)
_BREAK_WORD = (
    "<div id='page'>ABCDEF</div>",
    "#page { width: 30px; font-size: 10px; overflow-wrap: break-word; }",
    80,
)
_WORD_WRAP = (
    "<div id='page'>ABCDEF</div><div id='next'>Z</div>",
    "#page { width: 30px; font-size: 10px; word-wrap: anywhere; } #next { font-size: 10px; }",
    80,
)
_PLAIN = (
    "<div id='page'>ABCDEF</div>",
    "#page { width: 30px; font-size: 10px; }",
    80,
)
_ANYWHERE_FLOAT = (
    "<div id='host'><div id='float'>ABCDEF</div></div>",
    "#host { width: 30px; font-size: 10px; } #float { float: left; overflow-wrap: anywhere; }",
    80,
)
_BREAK_WORD_FLOAT = (
    "<div id='host'><div id='float'>ABCDEF</div></div>",
    "#host { width: 30px; font-size: 10px; } #float { float: left; overflow-wrap: break-word; }",
    80,
)
_KEEP_FLOAT = (
    "<div id='host'><div id='float'>\u6c49\u5b57\u6c49\u5b57</div></div>",
    "#host { width: 20px; font-size: 10px; } #float { float: left; word-break: keep-all; }",
    80,
)
_KEEP_BLOCK = (
    "<div id='page'>\u6c49\u5b57\u6c49\u5b57</div><div id='next'>Z</div>",
    "#page { width: 20px; font-size: 10px; word-break: keep-all; } #next { font-size: 10px; }",
    80,
)
_INHERIT = (
    "<div id='page'><div id='child'>ABCDEF</div><div id='plain'>ABCDEF</div></div>",
    "#page { width: 80px; font-size: 10px; overflow-wrap: anywhere; } "
    "#child { width: 30px; } #plain { width: 30px; overflow-wrap: normal; }",
    80,
)
_INVALID = (
    "<div id='page'>AB</div>",
    "#page { width: 40px; font-size: 10px; overflow-wrap: 50%; }",
    80,
)
_INLINE = (
    "<div id='page'>AA<span>BB</span></div>",
    "#page { width: 80px; font-size: 10px; } span { overflow-wrap: anywhere; }",
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


def _split(lines: list[dict[str, object]]) -> bool:
    return (
        len(lines) == 2
        and lines[0].get("text") == "ABC"
        and lines[0].get("x") == 0
        and lines[0].get("y") == 0
        and lines[0].get("content_width") == 30
        and lines[1].get("text") == "DEF"
        and lines[1].get("x") == 0
        and lines[1].get("y") == 10
        and lines[1].get("content_width") == 30
    )


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without the layout still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    anywhere = _place(layout_normal_flow, *_ANYWHERE)
    break_all = _place(layout_normal_flow, *_BREAK_ALL)
    break_word = _place(layout_normal_flow, *_BREAK_WORD)
    word_wrap = _place(layout_normal_flow, *_WORD_WRAP)
    plain = _place(layout_normal_flow, *_PLAIN)
    anywhere_float = _place(layout_normal_flow, *_ANYWHERE_FLOAT)
    break_word_float = _place(layout_normal_flow, *_BREAK_WORD_FLOAT)
    keep_float = _place(layout_normal_flow, *_KEEP_FLOAT)
    keep_block = _place(layout_normal_flow, *_KEEP_BLOCK)
    inherited = _place(layout_normal_flow, *_INHERIT)
    invalid = _place(layout_normal_flow, *_INVALID)
    inline = _place(layout_normal_flow, *_INLINE)
    anywhere_lines = _lines(_box(anywhere, "page"))
    break_all_lines = _lines(_box(break_all, "page"))
    break_word_lines = _lines(_box(break_word, "page"))
    word_wrap_lines = _lines(_box(word_wrap, "page"))
    plain_lines = _lines(_box(plain, "page"))
    anywhere_float_box = _box(anywhere_float, "float")
    break_word_float_box = _box(break_word_float, "float")
    keep_float_box = _box(keep_float, "float")
    keep_lines = _lines(_box(keep_block, "page"))
    child_lines = _lines(_box(inherited, "child"))
    plain_child_lines = _lines(_box(inherited, "plain"))
    anywhere_float_lines = _lines(anywhere_float_box)
    break_word_float_lines = _lines(break_word_float_box)
    keep_float_lines = _lines(keep_float_box)
    observed: dict[str, object] = {
        "anywhere": [_pack(line) for line in anywhere_lines],
        "anywhere_next_y": None if _box(anywhere, "next") is None else _box(anywhere, "next").get("y"),
        "break_all": [_pack(line) for line in break_all_lines],
        "break_word": [_pack(line) for line in break_word_lines],
        "word_wrap": [_pack(line) for line in word_wrap_lines],
        "plain": [_pack(line) for line in plain_lines],
        "anywhere_float": {
            "width": None if anywhere_float_box is None else anywhere_float_box.get("content_width"),
            "lines": [_pack(line) for line in anywhere_float_lines],
        },
        "break_word_float": {
            "width": None if break_word_float_box is None else break_word_float_box.get("content_width"),
            "lines": [_pack(line) for line in break_word_float_lines],
        },
        "keep_float": {
            "width": None if keep_float_box is None else keep_float_box.get("content_width"),
            "lines": [_pack(line) for line in keep_float_lines],
        },
        "keep_block": [_pack(line) for line in keep_lines],
        "keep_next_y": None if _box(keep_block, "next") is None else _box(keep_block, "next").get("y"),
        "child": [_pack(line) for line in child_lines],
        "plain_child": [_pack(line) for line in plain_child_lines],
        "invalid": invalid.get("outcome"),
        "invalid_reason": invalid.get("reason"),
        "inline": inline.get("outcome"),
        "inline_reason": inline.get("reason"),
    }
    han = "\u6c49\u5b57"
    passed = (
        anywhere.get("outcome") == "placed"
        and _split(anywhere_lines)
        and observed["anywhere_next_y"] == 20
        and break_all.get("outcome") == "placed"
        and _split(break_all_lines)
        and break_word.get("outcome") == "placed"
        and _split(break_word_lines)
        and word_wrap.get("outcome") == "placed"
        and _split(word_wrap_lines)
        and observed["anywhere_next_y"] == 20
        and plain.get("outcome") == "placed"
        and len(plain_lines) == 1
        and plain_lines[0].get("text") == "ABCDEF"
        and plain_lines[0].get("content_width") == 60
        and anywhere_float.get("outcome") == "placed"
        and anywhere_float_box is not None
        and anywhere_float_box.get("content_width") == 30
        and _split(anywhere_float_lines)
        and break_word_float.get("outcome") == "placed"
        and break_word_float_box is not None
        and break_word_float_box.get("content_width") == 60
        and len(break_word_float_lines) == 1
        and break_word_float_lines[0].get("text") == "ABCDEF"
        and break_word_float_lines[0].get("content_width") == 60
        and keep_float.get("outcome") == "placed"
        and keep_float_box is not None
        and keep_float_box.get("content_width") == 40
        and len(keep_float_lines) == 1
        and keep_float_lines[0].get("text") == han + han
        and keep_float_lines[0].get("content_width") == 40
        and keep_block.get("outcome") == "placed"
        and len(keep_lines) == 2
        and keep_lines[0].get("text") == han
        and keep_lines[0].get("y") == 0
        and keep_lines[0].get("content_width") == 20
        and keep_lines[1].get("text") == han
        and keep_lines[1].get("y") == 10
        and keep_lines[1].get("content_width") == 20
        and observed["keep_next_y"] == 20
        and inherited.get("outcome") == "placed"
        and _split(child_lines)
        and len(plain_child_lines) == 1
        and plain_child_lines[0].get("text") == "ABCDEF"
        and plain_child_lines[0].get("content_width") == 60
        and invalid.get("outcome") == "invalid"
        and invalid.get("reason") == "overflow-wrap is invalid"
        and inline.get("outcome") == "invalid"
        and inline.get("reason") == "inline overflow-wrap is unsupported"
    )
    return bool(passed), observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
