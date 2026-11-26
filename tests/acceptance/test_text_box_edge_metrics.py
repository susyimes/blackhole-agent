"""Trim a horizontal block to a synthetic cap-height or x-height.

A 10px font on a 20px line has 5px of half-leading around an em that sits
entirely above the baseline. text-box-edge text still stops at that em, so
trim-both leaves two 15px lines and the next block at y 30. The cap-height
is 7px and the x-height is 5px. cap alphabetic therefore removes 8px above
the first line and 5px below the last, and the next block starts at y 27.
ex alphabetic removes 10px above the first line, and the next block starts
at y 25. The alphabetic under edge matches the em bottom.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit.
"""

from __future__ import annotations

import json

_PAGE = '<div id="page"><p id="copy">AAAA BBBB</p><p id="next">Z</p></div>'
_BASE = (
    "html, body, div, p, span { margin: 0px; font-size: 10px; line-height: 20px; }\n"
    "#copy { width: 80px; }\n"
    "#next { height: 10px; }\n"
)
_TEXT = _BASE + "#copy { text-box-trim: trim-both; text-box-edge: text; }\n"
_PLAIN = _BASE + "#copy { text-box-trim: trim-both; }\n"
_CAP = _BASE + "#copy { text-box-trim: trim-both; text-box-edge: cap alphabetic; }\n"
_EX = _BASE + "#copy { text-box-trim: trim-both; text-box-edge: ex alphabetic; }\n"
_ALPHA = _BASE + "#copy { text-box-trim: trim-both; text-box-edge: text alphabetic; }\n"
_SHORT = _BASE + "#copy { text-box: trim-both cap alphabetic; }\n"
_LONE = _BASE + "#copy { text-box-trim: trim-both; text-box-edge: cap; }\n"
_IDEO = _BASE + "#copy { text-box-trim: trim-both; text-box-edge: ideographic; }\n"
_CENTRAL = _BASE + "#copy { text-box-trim: trim-both; text-box-edge: central; }\n"
_EDGE_ONLY = _BASE + "#copy { text-box-edge: cap alphabetic; }\n"
_EM = [
    {"text": "AAAA", "x": 0, "y": 0, "height": 15, "width": 40},
    {"text": "BBBB", "x": 0, "y": 15, "height": 15, "width": 40},
]
_CAP_LINES = [
    {"text": "AAAA", "x": 0, "y": 0, "height": 12, "width": 40},
    {"text": "BBBB", "x": 0, "y": 12, "height": 15, "width": 40},
]
_EX_LINES = [
    {"text": "AAAA", "x": 0, "y": 0, "height": 10, "width": 40},
    {"text": "BBBB", "x": 0, "y": 10, "height": 15, "width": 40},
]
_OPEN = [
    {"text": "AAAA", "x": 0, "y": 0, "height": 20, "width": 40},
    {"text": "BBBB", "x": 0, "y": 20, "height": 20, "width": 40},
]


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


def _lay(layout, stylesheet: str) -> dict[str, object]:
    try:
        placed = layout(_PAGE, stylesheet, viewport_width=200)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def _stack(placed: dict[str, object]) -> tuple[dict[str, object] | None, dict[str, object] | None, list[dict[str, object]]]:
    copy = _box(placed.get("boxes"), "copy")
    nxt = _box(placed.get("boxes"), "next")
    return copy, nxt, _lines(copy)


def _placed(box: dict[str, object] | None, nxt: dict[str, object] | None, lines: list[dict[str, object]], expected: list[dict[str, object]], height: int) -> bool:
    return lines == expected and (box or {}).get("content_height") == height and (nxt or {}).get("y") == height


def _rejected(placed: dict[str, object], reason: str) -> bool:
    return placed.get("outcome") == "invalid" and placed.get("reason") == reason


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without the layout still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    text = _lay(layout_normal_flow, _TEXT)
    plain = _lay(layout_normal_flow, _PLAIN)
    cap = _lay(layout_normal_flow, _CAP)
    ex = _lay(layout_normal_flow, _EX)
    alpha = _lay(layout_normal_flow, _ALPHA)
    short = _lay(layout_normal_flow, _SHORT)
    lone = _lay(layout_normal_flow, _LONE)
    ideo = _lay(layout_normal_flow, _IDEO)
    central = _lay(layout_normal_flow, _CENTRAL)
    edge_only = _lay(layout_normal_flow, _EDGE_ONLY)

    text_box, text_next, text_lines = _stack(text)
    plain_box, plain_next, plain_lines = _stack(plain)
    cap_box, cap_next, cap_lines = _stack(cap)
    ex_box, ex_next, ex_lines = _stack(ex)
    alpha_box, alpha_next, alpha_lines = _stack(alpha)
    short_box, short_next, short_lines = _stack(short)
    open_box, open_next, open_lines = _stack(edge_only)

    checks = {
        "text_edge_stays_on_the_em": text.get("outcome") == "placed" and _placed(text_box, text_next, text_lines, _EM, 30),
        "trim_both_without_an_edge_stays_on_the_em": (
            plain.get("outcome") == "placed" and _placed(plain_box, plain_next, plain_lines, _EM, 30)
        ),
        "cap_alphabetic_cuts_inside_the_em": cap.get("outcome") == "placed" and _placed(cap_box, cap_next, cap_lines, _CAP_LINES, 27),
        "shorthand_cap_alphabetic_matches": (
            short.get("outcome") == "placed" and _placed(short_box, short_next, short_lines, _CAP_LINES, 27)
        ),
        "ex_alphabetic_cuts_to_the_x_height": ex.get("outcome") == "placed" and _placed(ex_box, ex_next, ex_lines, _EX_LINES, 25),
        "alphabetic_under_edge_matches_the_em_bottom": (
            alpha.get("outcome") == "placed" and _placed(alpha_box, alpha_next, alpha_lines, _EM, 30)
        ),
        "edge_without_trim_keeps_the_leading": (
            edge_only.get("outcome") == "placed" and _placed(open_box, open_next, open_lines, _OPEN, 40)
        ),
        "lone_cap_is_invalid": _rejected(lone, "text-box-edge is invalid"),
        "ideographic_is_unsupported": _rejected(ideo, "text-box-edge is unsupported"),
        "central_is_invalid": _rejected(central, "text-box-edge is invalid"),
    }
    observed = {
        "checks": checks,
        "text_lines": text_lines,
        "text_next_y": None if text_next is None else text_next.get("y"),
        "cap_lines": cap_lines,
        "cap_outcome": cap.get("outcome"),
        "cap_reason": cap.get("reason"),
        "cap_height": None if cap_box is None else cap_box.get("content_height"),
        "cap_next_y": None if cap_next is None else cap_next.get("y"),
        "ex_lines": ex_lines,
        "ex_height": None if ex_box is None else ex_box.get("content_height"),
        "ex_next_y": None if ex_next is None else ex_next.get("y"),
        "alpha_next_y": None if alpha_next is None else alpha_next.get("y"),
        "shorthand_next_y": None if short_next is None else short_next.get("y"),
        "plain_next_y": None if plain_next is None else plain_next.get("y"),
        "rejected": {
            "lone": lone.get("reason"),
            "ideographic": ideo.get("reason"),
            "central": central.get("reason"),
        },
    }
    return all(checks.values()), observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
