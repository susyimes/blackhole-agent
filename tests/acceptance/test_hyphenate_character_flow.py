"""Draw hyphenate-character at a taken hyphen break.

An empty string keeps the break and drops the hyphen advance, so hyphenation
ends the first line at hyphena. A two-character string prevents that break
and moves the following block down. A soft hyphen uses the same string.
Prints JSON with boolean passed and nonempty observed. Exit 0 either way.
"""

from __future__ import annotations

import json

_HYPHEN = "\u2010"
_SIZE = "font-size: 10px; line-height: 10px;"
_WORD = "<div lang='en' id='host'><div id='word'>hyphenation</div><div id='next'>Z</div></div>"


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


def _case(layout, stylesheet: str, markup: str = _WORD) -> dict[str, object]:
    placed = _lay(layout, markup, stylesheet)
    word = _box(placed.get("boxes"), "word")
    nxt = _box(placed.get("boxes"), "next")
    return {
        "outcome": placed.get("outcome"),
        "reason": placed.get("reason"),
        "lines": _packed(word),
        "next_y": None if nxt is None else nxt.get("y"),
    }


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - a missing layout still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    omitted = _case(
        layout_normal_flow,
        f"#host {{ hyphens: auto; {_SIZE} }} #word {{ width: 70px; }} #next {{ {_SIZE} }}",
    )
    empty = _case(
        layout_normal_flow,
        f"#host {{ hyphens: auto; hyphenate-character: \"\"; {_SIZE} }} #word {{ width: 70px; }} #next {{ {_SIZE} }}",
    )
    longer = _case(
        layout_normal_flow,
        f"#host {{ hyphens: auto; hyphenate-character: \"<>\"; {_SIZE} }} #word {{ width: 70px; }} #next {{ {_SIZE} }}",
    )
    restored = _case(
        layout_normal_flow,
        f"#host {{ hyphens: auto; hyphenate-character: \"\"; {_SIZE} }} "
        f"#word {{ width: 70px; hyphenate-character: auto; }}",
        "<div lang='en' id='host'><div id='word'>hyphenation</div></div>",
    )
    shy = _case(
        layout_normal_flow,
        f"#word {{ hyphens: manual; hyphenate-character: \"<>\"; {_SIZE} width: 70px; }} #next {{ {_SIZE} }}",
        f"<div id='word'>hyphen\u00adation</div><div id='next'>Z</div>",
    )
    shy_empty = _case(
        layout_normal_flow,
        f"#word {{ hyphens: manual; hyphenate-character: \"\"; {_SIZE} width: 70px; }} #next {{ {_SIZE} }}",
        f"<div id='word'>hyphen\u00adation</div><div id='next'>Z</div>",
    )
    hidden = _case(
        layout_normal_flow,
        f"#word {{ hyphens: none; hyphenate-character: \"<>\"; {_SIZE} width: 70px; }}",
        f"<div id='word'>hyphen\u00adation</div>",
    )
    floated = _lay(
        layout_normal_flow,
        "<div lang='en' id='host'><div id='float'>hyphenation</div></div>",
        f"#host {{ width: 70px; hyphens: auto; hyphenate-character: \"<>\"; {_SIZE} }} #float {{ float: left; }}",
    )
    float_box = _box(floated.get("boxes"), "float")
    invalid = _case(
        layout_normal_flow,
        f"#word {{ hyphenate-character: none; {_SIZE} width: 70px; }}",
        "<div id='word'>hyphenation</div>",
    )
    inline = _lay(
        layout_normal_flow,
        "<div id='page'>AA<span>BB</span></div>",
        f"#page {{ width: 80px; {_SIZE} }} span {{ hyphenate-character: \"\"; }}",
    )
    vertical = _lay(
        layout_normal_flow,
        "<div id='page'>AA</div>",
        f"#page {{ writing-mode: vertical-rl; height: 40px; {_SIZE} hyphenate-character: \"\"; }}",
    )
    observed: dict[str, object] = {
        "omitted": omitted,
        "empty": empty,
        "longer": longer,
        "restored": restored,
        "shy": shy,
        "shy_empty": shy_empty,
        "hidden": hidden,
        "float_outcome": floated.get("outcome"),
        "float_width": None if float_box is None else float_box.get("content_width"),
        "float_lines": _packed(float_box),
        "invalid": invalid.get("reason"),
        "inline": inline.get("reason"),
        "vertical": vertical.get("reason"),
    }
    default_lines = [
        {"text": f"hyphen{_HYPHEN}", "content_width": 70, "y": 0},
        {"text": "ation", "content_width": 50, "y": 10},
    ]
    passed = (
        omitted == {"outcome": "placed", "reason": None, "lines": default_lines, "next_y": 20}
        and empty
        == {
            "outcome": "placed",
            "reason": None,
            "lines": [
                {"text": "hyphena", "content_width": 70, "y": 0},
                {"text": "tion", "content_width": 40, "y": 10},
            ],
            "next_y": 20,
        }
        and longer
        == {
            "outcome": "placed",
            "reason": None,
            "lines": [
                {"text": "hy<>", "content_width": 40, "y": 0},
                {"text": "phena<>", "content_width": 70, "y": 10},
                {"text": "tion", "content_width": 40, "y": 20},
            ],
            "next_y": 30,
        }
        and restored.get("outcome") == "placed"
        and restored.get("lines") == default_lines
        and shy
        == {
            "outcome": "placed",
            "reason": None,
            "lines": [
                {"text": "hyphen<>", "content_width": 80, "y": 0},
                {"text": "ation", "content_width": 50, "y": 10},
            ],
            "next_y": 20,
        }
        and shy_empty
        == {
            "outcome": "placed",
            "reason": None,
            "lines": [
                {"text": "hyphen", "content_width": 60, "y": 0},
                {"text": "ation", "content_width": 50, "y": 10},
            ],
            "next_y": 20,
        }
        and hidden.get("outcome") == "placed"
        and hidden.get("lines") == [{"text": "hyphenation", "content_width": 110, "y": 0}]
        and floated.get("outcome") == "placed"
        and float_box is not None
        and float_box.get("content_width") == 110
        and observed["float_lines"] == [{"text": "hyphenation", "content_width": 110, "y": 0}]
        and invalid.get("outcome") == "invalid"
        and invalid.get("reason") == "hyphenate-character is invalid"
        and inline.get("outcome") == "invalid"
        and inline.get("reason") == "inline hyphenate-character is unsupported"
        and vertical.get("outcome") == "invalid"
        and vertical.get("reason") == "hyphenate-character writing mode is unsupported"
    )
    return bool(passed), observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
