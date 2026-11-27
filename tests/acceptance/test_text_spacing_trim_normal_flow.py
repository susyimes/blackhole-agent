"""Collapse adjacent fullwidth punctuation when text-spacing-trim is normal.

On a marginless page at 10px font and line-height, word-break break-all:
two U+FF09 marks in a 15px block are one 15px line under normal, and the
next block starts at y 10. Omitting the property wraps that pair and starts
the next block at y 20. AA plus U+FF09 fills a 25px line at 25px under
normal and wraps when the property is omitted. A plus U+FF09 in a 25px line
stays 20px. A line-start U+FF08 before A stays 10px and the next block
starts at y 20. A katakana middle dot before U+FF08, an ASCII Ps before
U+FF08, and U+FF09 before an ASCII Pe each fit a 15px line at 15px. U+FF09
before a same-size U+FF08 also fits at 15px, with only the opening halved.
AA plus
U+FF1A wraps a 25px line. AA plus U+3001 fills that line at 25px. trim-both
is rejected.

Prints JSON with boolean passed and nonempty observed. Exit 0 either way.
"""

from __future__ import annotations

import json

_BASE = "html, body, div { margin: 0px; font-size: 10px; line-height: 10px; }\n"
_OPEN = "\uFF08"
_CLOSE = "\uFF09"
_DOT = "\u30FB"
_COLON = "\uFF1A"
_COMMA = "\u3001"


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


def _two(
    lines: object,
    first: str,
    second: str,
    first_width: int,
    second_width: int,
    second_y: int,
) -> bool:
    return lines == [
        {"text": first, "y": 0, "width": first_width, "height": 10},
        {"text": second, "y": second_y, "width": second_width, "height": 10},
    ]


def main() -> None:
    pair = _CLOSE + _CLOSE
    pair_normal = _row(pair, 15, "normal")
    pair_omitted = _row(pair, 15, None)
    overflow = "AA" + _CLOSE
    overflow_normal = _row(overflow, 25, "normal")
    overflow_omitted = _row(overflow, 25, None)
    fitted = _row("A" + _CLOSE, 25, "normal")
    opening = _row(_OPEN + "A", 15, "normal")
    middle = _row(_DOT + _OPEN, 15, "normal")
    any_ps = _row("(" + _OPEN, 15, "normal")
    any_pe = _row(_CLOSE + ")", 15, "normal")
    closing_opening = _row(_CLOSE + _OPEN, 15, "normal")
    colon = _row("AA" + _COLON, 25, "normal")
    comma = _row("AA" + _COMMA, 25, "normal")
    both = _row(pair, 15, "trim-both")
    checks = {
        "adjacent_closings_share_one_line": _one(pair_normal["lines"], pair, 15) and pair_normal["next_y"] == 10,
        "omitted_pair_wraps": _two(pair_omitted["lines"], _CLOSE, _CLOSE, 10, 10, 10) and pair_omitted["next_y"] == 20,
        "overflowing_closing_trims_onto_the_line": _one(overflow_normal["lines"], overflow, 25)
        and overflow_normal["next_y"] == 10,
        "omitted_overflow_wraps": _two(overflow_omitted["lines"], "AA", _CLOSE, 20, 10, 10)
        and overflow_omitted["next_y"] == 20,
        "closing_that_already_fits_stays_full": _one(fitted["lines"], "A" + _CLOSE, 20) and fitted["next_y"] == 10,
        "line_start_opening_stays_full": _two(opening["lines"], _OPEN, "A", 10, 10, 10) and opening["next_y"] == 20,
        "middle_dot_collapses_the_next_opening": _one(middle["lines"], _DOT + _OPEN, 15) and middle["next_y"] == 10,
        "any_opening_punctuation_collapses_the_next_fullwidth_opening": _one(any_ps["lines"], "(" + _OPEN, 15)
        and any_ps["next_y"] == 10,
        "any_closing_punctuation_collapses_the_previous_fullwidth_closing": _one(any_pe["lines"], _CLOSE + ")", 15)
        and any_pe["next_y"] == 10,
        "same_size_closing_then_opening_halves_only_the_opening": _one(
            closing_opening["lines"], _CLOSE + _OPEN, 15
        )
        and closing_opening["next_y"] == 10,
        "fullwidth_colon_at_line_end_stays_full_and_wraps": _two(colon["lines"], "AA", _COLON, 20, 10, 10)
        and colon["next_y"] == 20,
        "ideographic_comma_at_line_end_trims_to_fit": _one(comma["lines"], "AA" + _COMMA, 25) and comma["next_y"] == 10,
        "trim_both_is_rejected": both["outcome"] != "placed",
    }
    observed = {
        "checks": checks,
        "pair_normal": pair_normal,
        "pair_omitted": pair_omitted,
        "overflow_normal": overflow_normal,
        "overflow_omitted": overflow_omitted,
        "fitted": fitted,
        "opening": opening,
        "middle": middle,
        "any_ps": any_ps,
        "any_pe": any_pe,
        "closing_opening": closing_opening,
        "colon": colon,
        "comma": comma,
        "both": {"outcome": both["outcome"], "reason": both["reason"]},
    }
    print(json.dumps({"passed": all(checks.values()) and bool(observed), "observed": observed}, ensure_ascii=False))


if __name__ == "__main__":
    main()
