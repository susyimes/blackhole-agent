"""Hyphenate an English word in normal flow when hyphens is auto.

A 70px line of 10px letters cannot hold hyphenation. auto and lang=en end
the first line with U+2010 after hyphen and put ation on the next line, and
the following block starts under both. manual leaves one overflowing line.
A soft hyphen still breaks under manual and stays hidden under none. French
and a missing language do not invent a break. computation breaks before
tion. A floated hyphenation inside a 70px container keeps the 110px word.
An inline whose language differs from the block is not hyphenated as English.

Prints JSON with boolean passed and nonempty observed. Exit 0 either way.
"""

from __future__ import annotations

import json

_HYPHEN = "\u2010"
_SIZE = "font-size: 10px; line-height: 10px;"


def _box(boxes: object, ident: str) -> dict[str, object] | None:
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if isinstance(item, dict) and item.get("id") == ident:
            return item
    return None


def _lines(box: dict[str, object] | None) -> list[dict[str, object]]:
    if box is None or not isinstance(box.get("lines"), list):
        return []
    return [item for item in box["lines"] if isinstance(item, dict)]


def _lay(layout, markup: str, stylesheet: str) -> dict[str, object]:
    try:
        placed = layout(markup, stylesheet, viewport_width=400)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def _packed(box: dict[str, object] | None) -> list[dict[str, object]]:
    return [
        {"text": line.get("text"), "content_width": line.get("content_width"), "y": line.get("y")}
        for line in _lines(box)
    ]


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - a missing layout still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    auto = _lay(
        layout_normal_flow,
        "<div lang='en' id='host'><div id='word'>hyphenation</div><div id='next'>Z</div></div>",
        f"#host {{ hyphens: auto; {_SIZE} }} #word {{ width: 70px; }}",
    )
    manual = _lay(
        layout_normal_flow,
        "<div lang='en' id='host'><div id='word'>hyphenation</div><div id='next'>Z</div></div>",
        f"#host {{ hyphens: manual; {_SIZE} }} #word {{ width: 70px; }}",
    )
    shy = _lay(
        layout_normal_flow,
        "<div id='word'>hyphen\u00adation</div><div id='next'>Z</div>",
        f"#word {{ hyphens: manual; {_SIZE} width: 70px; }} #next {{ {_SIZE} }}",
    )
    hidden = _lay(
        layout_normal_flow,
        "<div id='word'>hyphen\u00adation</div><div id='next'>Z</div>",
        f"#word {{ hyphens: none; {_SIZE} width: 70px; }}",
    )
    french = _lay(
        layout_normal_flow,
        "<div lang='fr' id='word'>hyphenation</div>",
        f"#word {{ hyphens: auto; {_SIZE} width: 70px; }}",
    )
    missing = _lay(
        layout_normal_flow,
        "<div id='word'>hyphenation</div>",
        f"#word {{ hyphens: auto; {_SIZE} width: 70px; }}",
    )
    computation = _lay(
        layout_normal_flow,
        "<div lang='en' id='word'>computation</div>",
        f"#word {{ hyphens: auto; {_SIZE} width: 80px; }}",
    )
    floated = _lay(
        layout_normal_flow,
        "<div lang='en' id='host'><div id='float'>hyphenation</div></div>",
        f"#host {{ width: 70px; hyphens: auto; {_SIZE} }} #float {{ float: left; }}",
    )
    mixed = _lay(
        layout_normal_flow,
        "<div lang='en' id='word'>hy<span lang='fr'>phenation</span></div>",
        f"#word {{ hyphens: auto; {_SIZE} width: 70px; }}",
    )

    auto_word = _box(auto.get("boxes"), "word")
    auto_next = _box(auto.get("boxes"), "next")
    manual_word = _box(manual.get("boxes"), "word")
    manual_next = _box(manual.get("boxes"), "next")
    shy_word = _box(shy.get("boxes"), "word")
    shy_next = _box(shy.get("boxes"), "next")
    hidden_word = _box(hidden.get("boxes"), "word")
    french_word = _box(french.get("boxes"), "word")
    missing_word = _box(missing.get("boxes"), "word")
    computation_word = _box(computation.get("boxes"), "word")
    float_box = _box(floated.get("boxes"), "float")

    observed: dict[str, object] = {
        "auto_outcome": auto.get("outcome"),
        "auto_lines": _packed(auto_word),
        "auto_height": None if auto_word is None else auto_word.get("content_height"),
        "auto_next_y": None if auto_next is None else auto_next.get("y"),
        "manual_lines": _packed(manual_word),
        "manual_next_y": None if manual_next is None else manual_next.get("y"),
        "shy_lines": _packed(shy_word),
        "shy_next_y": None if shy_next is None else shy_next.get("y"),
        "hidden_lines": _packed(hidden_word),
        "french_lines": _packed(french_word),
        "missing_lines": _packed(missing_word),
        "computation_lines": _packed(computation_word),
        "float_outcome": floated.get("outcome"),
        "float_width": None if float_box is None else float_box.get("content_width"),
        "float_lines": _packed(float_box),
        "mixed_outcome": mixed.get("outcome"),
        "mixed_reason": mixed.get("reason"),
    }
    intact = [{"text": "hyphenation", "content_width": 110, "y": 0}]
    passed = (
        auto.get("outcome") == "placed"
        and observed["auto_lines"]
        == [
            {"text": f"hyphen{_HYPHEN}", "content_width": 70, "y": 0},
            {"text": "ation", "content_width": 50, "y": 10},
        ]
        and auto_word is not None
        and auto_word.get("content_height") == 20
        and auto_next is not None
        and auto_next.get("y") == 20
        and manual.get("outcome") == "placed"
        and observed["manual_lines"] == intact
        and manual_word is not None
        and manual_word.get("content_width") == 70
        and manual_next is not None
        and manual_next.get("y") == 10
        and shy.get("outcome") == "placed"
        and observed["shy_lines"]
        == [
            {"text": f"hyphen{_HYPHEN}", "content_width": 70, "y": 0},
            {"text": "ation", "content_width": 50, "y": 10},
        ]
        and shy_next is not None
        and shy_next.get("y") == 20
        and hidden.get("outcome") == "placed"
        and observed["hidden_lines"] == intact
        and french.get("outcome") == "placed"
        and observed["french_lines"] == intact
        and missing.get("outcome") == "placed"
        and observed["missing_lines"] == intact
        and computation.get("outcome") == "placed"
        and observed["computation_lines"]
        == [
            {"text": f"computa{_HYPHEN}", "content_width": 80, "y": 0},
            {"text": "tion", "content_width": 40, "y": 10},
        ]
        and floated.get("outcome") == "placed"
        and float_box is not None
        and float_box.get("content_width") == 110
        and observed["float_lines"] == intact
        and mixed.get("outcome") == "invalid"
        and mixed.get("reason") == "hyphenation language is unsupported"
    )
    return bool(passed), observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
