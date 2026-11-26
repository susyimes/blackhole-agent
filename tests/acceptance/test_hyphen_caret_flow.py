"""Keep a source caret on a line that took a hyphen break.

A 70px English block of hyphenation at 10px paints hyphen and U+2010, then
ation. A pointer on the first letter, on the hyphen glyph, and on the next
fragment reports the original text offsets. A two-character hyphen mark in an
80px measure maps both glyphs to that same break, an empty mark keeps the
letter carets, and an unbroken word keeps its caret. A manual soft hyphen
painted as the same two-character mark reports the offset after that soft
hyphen, and the following fragment reports the next letter. Prints JSON with
boolean passed and nonempty observed. Exit 0 either way.
"""

from __future__ import annotations

import json

_SIZE = "font-size: 10px; line-height: 10px;"
_AUTO = "<div lang='en' id='host'><div id='word'>hyphenation</div><div id='next'>Z</div></div>"
_SOFT = "<div id='word'>hyphen\u00adation</div><div id='next'>Z</div>"
_PLAIN = "<div id='word'>hyphenation</div>"


def _caret(layout, markup: str, stylesheet: str, x: float, y: float) -> dict[str, object]:
    try:
        found = layout(markup, stylesheet, x, y, viewport_width=400)
    except Exception as exc:  # noqa: BLE001 - a raised hit is an unmet outcome
        return {"outcome": "error", "id": None, "caret": None, "reason": f"{type(exc).__name__}: {exc}"}
    if not isinstance(found, dict):
        return {"outcome": "error", "id": None, "caret": None, "reason": "hit is invalid"}
    return {
        "outcome": found.get("outcome"),
        "id": found.get("id"),
        "caret": found.get("caret"),
        "reason": found.get("reason"),
    }


def _sheet(width: int, extra: str = "") -> str:
    return f"#host {{ hyphens: auto; {_SIZE} }} #word {{ width: {width}px; {extra} }} #next {{ {_SIZE} }}"


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import element_from_document
    except Exception as exc:  # noqa: BLE001 - a missing hit still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    default = _sheet(70)
    longer = _sheet(80, 'hyphenate-character: "<>";')
    empty = _sheet(70, 'hyphenate-character: "";')
    whole = f"#word {{ width: 200px; hyphens: auto; {_SIZE} }}"
    soft = f'#word {{ width: 80px; hyphens: manual; hyphenate-character: "<>"; {_SIZE} }} #next {{ {_SIZE} }}'
    points = {
        "default_letter": _caret(element_from_document, _AUTO, default, 5, 5),
        "default_mark": _caret(element_from_document, _AUTO, default, 65, 5),
        "default_next": _caret(element_from_document, _AUTO, default, 5, 15),
        "longer_letter": _caret(element_from_document, _AUTO, longer, 5, 5),
        "longer_mark_left": _caret(element_from_document, _AUTO, longer, 65, 5),
        "longer_mark_right": _caret(element_from_document, _AUTO, longer, 75, 5),
        "longer_next": _caret(element_from_document, _AUTO, longer, 5, 15),
        "empty_letter": _caret(element_from_document, _AUTO, empty, 5, 5),
        "empty_last": _caret(element_from_document, _AUTO, empty, 65, 5),
        "plain_letter": _caret(element_from_document, _PLAIN, whole, 5, 5),
        "soft_letter": _caret(element_from_document, _SOFT, soft, 5, 5),
        "soft_mark": _caret(element_from_document, _SOFT, soft, 65, 5),
        "soft_next": _caret(element_from_document, _SOFT, soft, 5, 15),
    }
    observed = {name: item.get("caret") for name, item in points.items()}
    observed["outcomes"] = {name: item.get("outcome") for name, item in points.items()}
    passed = (
        observed["default_letter"] == {"line": 0, "offset": 1}
        and observed["default_mark"] == {"line": 0, "offset": 6}
        and observed["default_next"] == {"line": 1, "offset": 7}
        and observed["longer_letter"] == {"line": 0, "offset": 1}
        and observed["longer_mark_left"] == {"line": 0, "offset": 6}
        and observed["longer_mark_right"] == {"line": 0, "offset": 6}
        and observed["longer_next"] == {"line": 1, "offset": 7}
        and observed["empty_letter"] == {"line": 0, "offset": 1}
        and observed["empty_last"] == {"line": 0, "offset": 7}
        and observed["plain_letter"] == {"line": 0, "offset": 1}
        and observed["soft_letter"] == {"line": 0, "offset": 1}
        and observed["soft_mark"] == {"line": 0, "offset": 7}
        and observed["soft_next"] == {"line": 1, "offset": 8}
        and all(item.get("outcome") == "hit" and item.get("id") == "word" for item in points.values())
    )
    return bool(passed), observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
