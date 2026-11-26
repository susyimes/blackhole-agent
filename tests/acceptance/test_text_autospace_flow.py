"""Open an eighth-ideograph gap at a CJK and Latin or digit boundary.

text-autospace: normal breaks AあB inside a 33px line and pushes the next
block down. The same value leaves AB flush. ideograph-alpha and
ideograph-numeric each open only their own boundary. An omitted value and
no-autospace stay on the font-size advance. insert keeps a real space;
replace spends it on the gap.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A layout that still ignores text-autospace exits 0 with
passed false.
"""

from __future__ import annotations

import json

_BASE = "div { margin: 0px; font-size: 16px; line-height: 20px; }\n"
_STORY = '<div id="page">AあB</div><div id="next">Z</div>'
_OMIT = _BASE + "#page { width: 33px; }\n"
_NORMAL = _BASE + "#page { width: 33px; text-autospace: normal; }\n"
_PAIR = (
    '<div id="page">Aあ</div>',
    _BASE + "#page { width: 200px; text-autospace: normal; }\n",
)
_LATIN = (
    '<div id="page">AB</div>',
    _BASE + "#page { width: 200px; text-autospace: normal; }\n",
)
_ALPHA_LETTER = (
    '<div id="page">Aあ</div>',
    _BASE + "#page { width: 200px; text-autospace: ideograph-alpha; }\n",
)
_ALPHA_DIGIT = (
    '<div id="page">あ1</div>',
    _BASE + "#page { width: 200px; text-autospace: ideograph-alpha; }\n",
)
_NUMERIC_LETTER = (
    '<div id="page">Aあ</div>',
    _BASE + "#page { width: 200px; text-autospace: ideograph-numeric; }\n",
)
_NUMERIC_DIGIT = (
    '<div id="page">あ1</div>',
    _BASE + "#page { width: 200px; text-autospace: ideograph-numeric; }\n",
)
_OFF = (
    '<div id="page">Aあ</div>',
    _BASE + "#page { width: 200px; text-autospace: no-autospace; }\n",
)
_INSERT = (
    '<div id="page">A あ</div>',
    _BASE + "#page { width: 200px; text-autospace: ideograph-alpha insert; }\n",
)
_REPLACE = (
    '<div id="page">A あ</div>',
    _BASE + "#page { width: 200px; text-autospace: ideograph-alpha replace; }\n",
)
_INHERIT = (
    '<div id="page"><div id="child">Aあ</div><div id="reset">Aあ</div></div>',
    _BASE + "#page { width: 200px; text-autospace: normal; } #reset { text-autospace: no-autospace; }\n",
)
_AUTO = (
    '<div id="page">A</div>',
    _BASE + "#page { text-autospace: auto; }\n",
)
_PUNCT = (
    '<div id="page">A</div>',
    _BASE + "#page { text-autospace: punctuation; }\n",
)
_BAD = (
    '<div id="page">A</div>',
    _BASE + "#page { text-autospace: sideways; }\n",
)
_VERTICAL = (
    '<div id="page">Aあ</div>',
    _BASE + "#page { width: 100px; writing-mode: vertical-rl; text-autospace: normal; }\n",
)
_INLINE = (
    '<div id="page">A<span id="s">あ</span></div>',
    _BASE + "#page { width: 200px; } #s { text-autospace: normal; }\n",
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
    return {"text": line.get("text"), "width": line.get("content_width"), "y": line.get("y")}


def _ink(result: dict[str, object], box_id: str = "page") -> list[dict[str, object]]:
    return [_pack(line) for line in _lines(_box(result, box_id))]


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without the layout still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    omitted = _place(layout_normal_flow, _STORY, _OMIT)
    opened = _place(layout_normal_flow, _STORY, _NORMAL)
    pair = _place(layout_normal_flow, *_PAIR)
    latin = _place(layout_normal_flow, *_LATIN)
    alpha_letter = _place(layout_normal_flow, *_ALPHA_LETTER)
    alpha_digit = _place(layout_normal_flow, *_ALPHA_DIGIT)
    numeric_letter = _place(layout_normal_flow, *_NUMERIC_LETTER)
    numeric_digit = _place(layout_normal_flow, *_NUMERIC_DIGIT)
    off = _place(layout_normal_flow, *_OFF)
    inserted = _place(layout_normal_flow, *_INSERT)
    replaced = _place(layout_normal_flow, *_REPLACE)
    inherited = _place(layout_normal_flow, *_INHERIT)
    auto = _place(layout_normal_flow, *_AUTO)
    punct = _place(layout_normal_flow, *_PUNCT)
    bad = _place(layout_normal_flow, *_BAD)
    vertical = _place(layout_normal_flow, *_VERTICAL)
    inline = _place(layout_normal_flow, *_INLINE)
    omitted_lines = _ink(omitted)
    opened_lines = _ink(opened)
    observed: dict[str, object] = {
        "omitted": omitted_lines,
        "omitted_next_y": (_box(omitted, "next") or {}).get("y"),
        "opened": opened_lines,
        "opened_next_y": (_box(opened, "next") or {}).get("y"),
        "pair": _ink(pair),
        "latin": _ink(latin),
        "alpha_letter": _ink(alpha_letter),
        "alpha_digit": _ink(alpha_digit),
        "numeric_letter": _ink(numeric_letter),
        "numeric_digit": _ink(numeric_digit),
        "off": _ink(off),
        "insert": _ink(inserted),
        "replace": _ink(replaced),
        "child": _ink(inherited, "child"),
        "reset": _ink(inherited, "reset"),
        "auto": auto.get("reason"),
        "punctuation": punct.get("reason"),
        "invalid": bad.get("reason"),
        "vertical": vertical.get("reason"),
        "inline": inline.get("reason"),
    }
    passed = (
        omitted.get("outcome") == "placed"
        and omitted_lines == [{"text": "AあB", "width": 48, "y": 0}]
        and observed["omitted_next_y"] == 20
        and opened.get("outcome") == "placed"
        and opened_lines
        == [
            {"text": "A", "width": 16, "y": 0},
            {"text": "あ", "width": 16, "y": 20},
            {"text": "B", "width": 16, "y": 40},
        ]
        and observed["opened_next_y"] == 60
        and _ink(pair) == [{"text": "Aあ", "width": 34, "y": 0}]
        and _ink(latin) == [{"text": "AB", "width": 32, "y": 0}]
        and _ink(alpha_letter) == [{"text": "Aあ", "width": 34, "y": 0}]
        and _ink(alpha_digit) == [{"text": "あ1", "width": 32, "y": 0}]
        and _ink(numeric_letter) == [{"text": "Aあ", "width": 32, "y": 0}]
        and _ink(numeric_digit) == [{"text": "あ1", "width": 34, "y": 0}]
        and _ink(off) == [{"text": "Aあ", "width": 32, "y": 0}]
        and _ink(inserted) == [{"text": "A あ", "width": 48, "y": 0}]
        and _ink(replaced) == [{"text": "A あ", "width": 34, "y": 0}]
        and _ink(inherited, "child") == [{"text": "Aあ", "width": 34, "y": 0}]
        and _ink(inherited, "reset") == [{"text": "Aあ", "width": 32, "y": 20}]
        and auto.get("outcome") == "invalid"
        and auto.get("reason") == "text-autospace is unsupported"
        and punct.get("outcome") == "invalid"
        and punct.get("reason") == "text-autospace is unsupported"
        and bad.get("outcome") == "invalid"
        and bad.get("reason") == "text-autospace is invalid"
        and vertical.get("outcome") == "invalid"
        and vertical.get("reason") == "text-autospace writing mode is unsupported"
        and inline.get("outcome") == "invalid"
        and inline.get("reason") == "inline text-autospace is unsupported"
    )
    return bool(passed), observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
