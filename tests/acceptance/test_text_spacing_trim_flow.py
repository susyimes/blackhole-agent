"""Trim a fullwidth opening punctuation glyph at the start of each line.

On a marginless page at 10px font and line-height, word-break break-all,
U+FF08 A in a 15px block is one 15px line when text-spacing-trim is
trim-start, and the following block starts at y 10. Omitting the property
leaves two 10px lines and starts the following block at y 20. U+201C and
U+300C trim the same way. An ASCII parenthesis does not. On a 20px block,
AA U+FF08 A stays two lines and the second line is 15px wide under
trim-start, 20px when the property is omitted. A child inherits the trim.
normal and trim-both are rejected.

Prints JSON with boolean passed and nonempty observed. Exit 0 either way.
"""

from __future__ import annotations

import json

_BASE = "html, body, div { margin: 0px; font-size: 10px; line-height: 10px; }\n"
_OPEN = "\uFF08"
_QUOTE = "\u201C"
_CORNER = "\u300C"


def _lay(markup: str, css: str) -> dict[str, object]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - a missing layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    try:
        placed = layout_normal_flow(markup, _BASE + css, viewport_width=400)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    if not isinstance(placed, dict):
        return {"outcome": "error", "reason": "layout is invalid", "boxes": None}
    return placed


def _box(placed: dict[str, object], ident: str) -> dict[str, object] | None:
    boxes = placed.get("boxes")
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if isinstance(item, dict) and item.get("id") == ident:
            return item
    return None


def _lines(box: dict[str, object] | None) -> list[dict[str, object]]:
    if box is None or not isinstance(box.get("lines"), list):
        return []
    found = []
    for item in box["lines"]:
        if isinstance(item, dict):
            found.append(
                {
                    "text": item.get("text"),
                    "y": item.get("y"),
                    "width": item.get("content_width"),
                    "height": item.get("height"),
                }
            )
    return found


def _row(text: str, width: int, trim: str | None) -> dict[str, object]:
    rule = f"#row {{ width: {width}px; word-break: break-all;"
    if trim is not None:
        rule += f" text-spacing-trim: {trim};"
    rule += " }\n"
    placed = _lay(f'<div id="row">{text}</div><div id="next">N</div>', rule)
    nxt = _box(placed, "next")
    return {
        "outcome": placed.get("outcome"),
        "reason": placed.get("reason"),
        "lines": _lines(_box(placed, "row")),
        "next_y": None if nxt is None else nxt.get("y"),
    }


def _one(lines: object, text: str, width: int) -> bool:
    return lines == [{"text": text, "y": 0, "width": width, "height": 10}]


def _two(lines: object, first: str, second: str, first_width: int, second_width: int, second_y: int) -> bool:
    return lines == [
        {"text": first, "y": 0, "width": first_width, "height": 10},
        {"text": second, "y": second_y, "width": second_width, "height": 10},
    ]


def main() -> None:
    opened = _OPEN + "A"
    quoted = _QUOTE + "A"
    corner = _CORNER + "A"
    later = "AA" + _OPEN + "A"
    ascii_paren = "(A"
    trimmed = _row(opened, 15, "trim-start")
    omitted = _row(opened, 15, None)
    spaced = _row(opened, 15, "space-all")
    quote = _row(quoted, 15, "trim-start")
    bracket = _row(corner, 15, "trim-start")
    plain = _row(ascii_paren, 15, "trim-start")
    second = _row(later, 20, "trim-start")
    second_plain = _row(later, 20, None)
    end_mark = _row("A" + _OPEN, 15, "trim-start")
    normal = _row(opened, 15, "normal")
    both = _row(opened, 15, "trim-both")
    inherited_markup = (
        f'<div id="host"><div id="kid">{opened}</div></div><div id="next">N</div>'
    )
    inherited_placed = _lay(
        inherited_markup,
        "#host { word-break: break-all; text-spacing-trim: trim-start; }\n#kid { width: 15px; }\n",
    )
    inherited_next = _box(inherited_placed, "next")
    inherited = {
        "outcome": inherited_placed.get("outcome"),
        "reason": inherited_placed.get("reason"),
        "lines": _lines(_box(inherited_placed, "kid")),
        "next_y": None if inherited_next is None else inherited_next.get("y"),
    }
    checks = {
        "trim_start_holds_the_next_character": _one(trimmed["lines"], opened, 15) and trimmed["next_y"] == 10,
        "omitted_value_wraps": _two(omitted["lines"], _OPEN, "A", 10, 10, 10) and omitted["next_y"] == 20,
        "space_all_stays_full_width": _two(spaced["lines"], _OPEN, "A", 10, 10, 10) and spaced["next_y"] == 20,
        "left_double_quote_trims": _one(quote["lines"], quoted, 15) and quote["next_y"] == 10,
        "cjk_corner_bracket_trims": _one(bracket["lines"], corner, 15) and bracket["next_y"] == 10,
        "ascii_parenthesis_stays_full_width": _two(plain["lines"], "(", "A", 10, 10, 10) and plain["next_y"] == 20,
        "later_line_trims_its_opening_mark": _two(second["lines"], "AA", _OPEN + "A", 20, 15, 10)
        and second["next_y"] == 20,
        "later_line_without_trim_stays_full": _two(second_plain["lines"], "AA", _OPEN + "A", 20, 20, 10)
        and second_plain["next_y"] == 20,
        "opening_mark_after_a_letter_trims_on_the_next_line": _two(end_mark["lines"], "A", _OPEN, 10, 5, 10)
        and end_mark["next_y"] == 20,
        "child_inherits_trim_start": _one(inherited["lines"], opened, 15) and inherited["next_y"] == 10,
        "normal_is_rejected": normal["outcome"] != "placed",
        "trim_both_is_rejected": both["outcome"] != "placed",
    }
    observed = {
        "checks": checks,
        "trimmed": trimmed,
        "omitted": omitted,
        "spaced": spaced,
        "quote": quote,
        "bracket": bracket,
        "plain": plain,
        "second": second,
        "second_plain": second_plain,
        "end_mark": end_mark,
        "inherited": inherited,
        "normal": {"outcome": normal["outcome"], "reason": normal["reason"]},
        "both": {"outcome": both["outcome"], "reason": both["reason"]},
    }
    print(json.dumps({"passed": all(checks.values()) and bool(observed), "observed": observed}, ensure_ascii=False))


if __name__ == "__main__":
    main()
