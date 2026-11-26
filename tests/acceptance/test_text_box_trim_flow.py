"""Trim half-leading outside the em box of a horizontal block.

A 10px font on a 20px line has 5px of half-leading above the em and 5px
below the baseline. text-box-trim: trim-both drops both, so two wrapped
lines become a 30px stack and the following block starts at y 30.
trim-start and trim-end each leave 35px. An omitted trim leaves 40px.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A layout that still ignores text-box-trim exits 0 with
passed false.
"""

from __future__ import annotations

import json

_PAGE = '<div id="page"><p id="copy">AAAA BBBB</p><p id="next">Z</p></div>'
_SHORT = '<div id="page"><p id="copy">AA</p><p id="next">Z</p></div>'
_CHILD = '<div id="page"><div id="copy"><p id="inner">AA</p></div></div>'
_INLINE = '<div id="page"><p id="copy">A<span id="s">B</span></p></div>'
_BASE = (
    "html, body, div, p, span { margin: 0px; font-size: 10px; line-height: 20px; }\n"
    "#copy { width: 80px; }\n"
    "#next { height: 10px; }\n"
)
_NONE = _BASE
_BOTH = _BASE + "#copy { text-box-trim: trim-both; }\n"
_START = _BASE + "#copy { text-box-trim: trim-start; }\n"
_END = _BASE + "#copy { text-box-trim: trim-end; }\n"
_SHORT_BOTH = _BASE + "#copy { text-box-trim: trim-both; }\n"
_SHORTHAND = _BASE + "#copy { text-box: trim-both text; }\n"
_CANCEL = _BASE + "#copy { text-box: trim-both; text-box-trim: none; }\n"
_LATER = _BASE + "#copy { text-box-trim: none; text-box: trim-both; }\n"
_BAD = _BASE + "#copy { text-box-trim: sideways; }\n"
_CAP = _BASE + "#copy { text-box-trim: trim-both; text-box-edge: cap; }\n"
_VERTICAL = _BASE + "#copy { writing-mode: vertical-rl; text-box-trim: trim-both; }\n"
_FIXED = _BASE + "#copy { height: 40px; text-box-trim: trim-both; }\n"
_NESTED = "div, p { margin: 0px; font-size: 10px; line-height: 20px; }\n#copy { text-box-trim: trim-both; }\n"
_SPAN = _BASE + "#s { text-box-trim: trim-both; }\n"


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
    packed = []
    for line in box["lines"]:
        if not isinstance(line, dict):
            return []
        packed.append(
            {
                "text": line.get("text"),
                "x": line.get("x"),
                "y": line.get("y"),
                "height": line.get("height"),
                "width": line.get("content_width"),
            }
        )
    return packed


def _lay(layout, markup: str, stylesheet: str) -> dict[str, object]:
    try:
        placed = layout(markup, stylesheet, viewport_width=200)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def _stack(placed: dict[str, object]) -> tuple[dict[str, object] | None, dict[str, object] | None, list[dict[str, object]]]:
    copy = _box(placed.get("boxes"), "copy")
    nxt = _box(placed.get("boxes"), "next")
    return copy, nxt, _lines(copy)


def _rejected(placed: dict[str, object], reason: str) -> bool:
    return placed.get("outcome") == "invalid" and placed.get("reason") == reason


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without the layout still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    plain = _lay(layout_normal_flow, _PAGE, _NONE)
    both = _lay(layout_normal_flow, _PAGE, _BOTH)
    start = _lay(layout_normal_flow, _PAGE, _START)
    end = _lay(layout_normal_flow, _PAGE, _END)
    short = _lay(layout_normal_flow, _SHORT, _SHORT_BOTH)
    shorthand = _lay(layout_normal_flow, _PAGE, _SHORTHAND)
    cancel = _lay(layout_normal_flow, _PAGE, _CANCEL)
    later = _lay(layout_normal_flow, _PAGE, _LATER)
    bad = _lay(layout_normal_flow, _PAGE, _BAD)
    cap = _lay(layout_normal_flow, _PAGE, _CAP)
    vertical = _lay(layout_normal_flow, _PAGE, _VERTICAL)
    fixed = _lay(layout_normal_flow, _PAGE, _FIXED)
    nested = _lay(layout_normal_flow, _CHILD, _NESTED)
    inline = _lay(layout_normal_flow, _INLINE, _SPAN)

    plain_box, plain_next, plain_lines = _stack(plain)
    both_box, both_next, both_lines = _stack(both)
    start_box, start_next, start_lines = _stack(start)
    end_box, end_next, end_lines = _stack(end)
    short_box, short_next, short_lines = _stack(short)
    hand_box, hand_next, hand_lines = _stack(shorthand)
    cancel_box, cancel_next, cancel_lines = _stack(cancel)
    later_box, later_next, later_lines = _stack(later)

    untrimmed = [
        {"text": "AAAA", "x": 0, "y": 0, "height": 20, "width": 40},
        {"text": "BBBB", "x": 0, "y": 20, "height": 20, "width": 40},
    ]
    trimmed = [
        {"text": "AAAA", "x": 0, "y": 0, "height": 15, "width": 40},
        {"text": "BBBB", "x": 0, "y": 15, "height": 15, "width": 40},
    ]
    start_only = [
        {"text": "AAAA", "x": 0, "y": 0, "height": 15, "width": 40},
        {"text": "BBBB", "x": 0, "y": 15, "height": 20, "width": 40},
    ]
    end_only = [
        {"text": "AAAA", "x": 0, "y": 0, "height": 20, "width": 40},
        {"text": "BBBB", "x": 0, "y": 20, "height": 15, "width": 40},
    ]
    checks = {
        "omitted_trim_keeps_the_half_leading": (
            plain.get("outcome") == "placed"
            and plain_lines == untrimmed
            and (plain_box or {}).get("content_height") == 40
            and (plain_next or {}).get("y") == 40
        ),
        "trim_both_meets_the_em_box": (
            both.get("outcome") == "placed"
            and both_lines == trimmed
            and (both_box or {}).get("content_height") == 30
            and (both_next or {}).get("y") == 30
        ),
        "trim_start_drops_only_the_first_half_leading": (
            start.get("outcome") == "placed"
            and start_lines == start_only
            and (start_box or {}).get("content_height") == 35
            and (start_next or {}).get("y") == 35
        ),
        "trim_end_drops_only_the_last_half_leading": (
            end.get("outcome") == "placed"
            and end_lines == end_only
            and (end_box or {}).get("content_height") == 35
            and (end_next or {}).get("y") == 35
        ),
        "one_line_trim_both_is_the_em": (
            short.get("outcome") == "placed"
            and short_lines == [{"text": "AA", "x": 0, "y": 0, "height": 10, "width": 20}]
            and (short_box or {}).get("content_height") == 10
            and (short_next or {}).get("y") == 10
        ),
        "shorthand_with_text_edge_matches_trim_both": (
            shorthand.get("outcome") == "placed"
            and hand_lines == trimmed
            and (hand_box or {}).get("content_height") == 30
            and (hand_next or {}).get("y") == 30
        ),
        "later_longhand_none_cancels_the_shorthand": (
            cancel.get("outcome") == "placed"
            and cancel_lines == untrimmed
            and (cancel_box or {}).get("content_height") == 40
            and (cancel_next or {}).get("y") == 40
        ),
        "later_shorthand_trim_both_wins": (
            later.get("outcome") == "placed"
            and later_lines == trimmed
            and (later_box or {}).get("content_height") == 30
            and (later_next or {}).get("y") == 30
        ),
        "invalid_keyword_is_rejected": _rejected(bad, "text-box-trim is invalid"),
        "cap_edge_is_unsupported": _rejected(cap, "text-box-edge is unsupported"),
        "vertical_writing_mode_is_rejected": _rejected(vertical, "text-box-trim writing mode is unsupported"),
        "specified_height_is_rejected": _rejected(fixed, "text-box-trim specified height is unsupported"),
        "block_child_is_rejected": _rejected(nested, "text-box-trim block children are unsupported"),
        "inline_declaration_is_rejected": _rejected(inline, "inline text-box-trim is unsupported"),
    }
    observed = {
        "checks": checks,
        "plain": plain_lines,
        "plain_height": None if plain_box is None else plain_box.get("content_height"),
        "plain_next_y": None if plain_next is None else plain_next.get("y"),
        "both": both_lines,
        "both_outcome": both.get("outcome"),
        "both_reason": both.get("reason"),
        "both_height": None if both_box is None else both_box.get("content_height"),
        "both_next_y": None if both_next is None else both_next.get("y"),
        "start": start_lines,
        "start_height": None if start_box is None else start_box.get("content_height"),
        "start_next_y": None if start_next is None else start_next.get("y"),
        "end": end_lines,
        "end_height": None if end_box is None else end_box.get("content_height"),
        "end_next_y": None if end_next is None else end_next.get("y"),
        "short": short_lines,
        "short_height": None if short_box is None else short_box.get("content_height"),
        "short_next_y": None if short_next is None else short_next.get("y"),
        "shorthand_height": None if hand_box is None else hand_box.get("content_height"),
        "rejected": {
            "bad": bad.get("reason"),
            "cap": cap.get("reason"),
            "vertical": vertical.get("reason"),
            "fixed": fixed.get("reason"),
            "nested": nested.get("reason"),
            "inline": inline.get("reason"),
        },
    }
    return all(checks.values()), observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
