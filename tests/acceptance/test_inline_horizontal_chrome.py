"""Place a non-replaced inline's horizontal margin, border, and padding.

In a 200px viewport at 10px, A, a span of B with 10px padding on each side,
and C share one line of content width 50, and the next block starts at y 10.
A 30px measure wraps A, then each B at width 20, then C, and the next block
starts at y 40. A 10px solid border on each side of those two glyphs wraps
the same way. A 20px margin-left on B makes AA B 60 wide, and a 40px measure
wraps B at width 30. Percentage padding and a negative margin stay rejected.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A layout that still ignores the chrome exits 0 with passed
false.
"""

from __future__ import annotations

import json
import sys

_FIT = '<div id="page"><div id="row">A<span id="s">B</span>C</div><div id="next">Z</div></div>'
_SPLIT = '<div id="page"><div id="row">A <span id="s">B B</span> C</div><div id="next">Z</div></div>'
_MARGIN = '<div id="page"><div id="row">AA <span id="s">B</span></div><div id="next">Z</div></div>'
_UNEVEN = '<div id="page"><div id="row">A <span id="s">B B</span></div><div id="next">Z</div></div>'
_PERCENT = '<div id="page"><div id="row">A<span id="s">B</span>C</div></div>'
_NEGATIVE = '<div id="page"><div id="row">A<span id="s">B</span>C</div></div>'
_BASE = "#page, #row, #next, #s { font-size: 10px; line-height: 10px; }\n"
_PAD = _BASE + "#s { padding-left: 10px; padding-right: 10px; }\n"
_NARROW = _PAD + "#row { width: 30px; }\n"
_BORDER = _BASE + "#row { width: 30px; }\n#s { border-left: 10px solid; border-right: 10px solid; }\n"
_MARGIN_CSS = _BASE + "#s { margin-left: 20px; }\n"
_MARGIN_NARROW = _MARGIN_CSS + "#row { width: 40px; }\n"
_UNEVEN_CSS = _BASE + "#row { width: 40px; }\n#s { padding-left: 20px; }\n"
_PERCENT_CSS = _BASE + "#s { padding-left: 10%; }\n"
_NEGATIVE_CSS = _BASE + "#s { margin-left: -10px; }\n"


def _box(boxes: object, ident: str) -> dict[str, object] | None:
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if isinstance(item, dict) and item.get("id") == ident:
            return item
    return None


def _line(box: dict[str, object] | None, index: int) -> dict[str, object] | None:
    if box is None or not isinstance(box.get("lines"), list):
        return None
    lines = box["lines"]
    if index >= len(lines) or not isinstance(lines[index], dict):
        return None
    return lines[index]


def _near(item: dict[str, object] | None, **expected: object) -> bool:
    if item is None:
        return False
    return all(item.get(key) == value for key, value in expected.items())


def _lay(layout, markup: str, stylesheet: str) -> dict[str, object]:
    try:
        placed = layout(markup, stylesheet, viewport_width=200)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def _lines(box: dict[str, object] | None) -> list[dict[str, object]]:
    if box is None or not isinstance(box.get("lines"), list):
        return []
    found = []
    for line in box["lines"]:
        if not isinstance(line, dict):
            continue
        found.append({"text": line.get("text"), "w": line.get("content_width"), "y": line.get("y")})
    return found


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without placement still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    fit = _lay(layout_normal_flow, _FIT, _PAD)
    split = _lay(layout_normal_flow, _SPLIT, _NARROW)
    border = _lay(layout_normal_flow, _SPLIT, _BORDER)
    margin = _lay(layout_normal_flow, _MARGIN, _MARGIN_CSS)
    narrow = _lay(layout_normal_flow, _MARGIN, _MARGIN_NARROW)
    uneven = _lay(layout_normal_flow, _UNEVEN, _UNEVEN_CSS)
    percent = _lay(layout_normal_flow, _PERCENT, _PERCENT_CSS)
    negative = _lay(layout_normal_flow, _NEGATIVE, _NEGATIVE_CSS)

    fit_row = _box(fit.get("boxes"), "row")
    fit_next = _box(fit.get("boxes"), "next")
    split_row = _box(split.get("boxes"), "row")
    split_next = _box(split.get("boxes"), "next")
    border_row = _box(border.get("boxes"), "row")
    border_next = _box(border.get("boxes"), "next")
    margin_row = _box(margin.get("boxes"), "row")
    narrow_row = _box(narrow.get("boxes"), "row")
    uneven_row = _box(uneven.get("boxes"), "row")

    checks = {
        "padding_shares_one_line": (
            fit.get("outcome") == "placed"
            and _near(_line(fit_row, 0), text="ABC", x=0, y=0, content_width=50, height=10)
            and _line(fit_row, 1) is None
            and _near(fit_next, y=10)
        ),
        "padding_wraps_each_fragment": (
            split.get("outcome") == "placed"
            and _near(_line(split_row, 0), text="A", content_width=10, y=0)
            and _near(_line(split_row, 1), text="B", content_width=20, y=10)
            and _near(_line(split_row, 2), text="B", content_width=20, y=20)
            and _near(_line(split_row, 3), text="C", content_width=10, y=30)
            and _line(split_row, 4) is None
            and _near(split_next, y=40)
        ),
        "border_wraps_the_same_way": (
            border.get("outcome") == "placed"
            and _near(_line(border_row, 0), text="A", content_width=10, y=0)
            and _near(_line(border_row, 1), text="B", content_width=20, y=10)
            and _near(_line(border_row, 2), text="B", content_width=20, y=20)
            and _near(_line(border_row, 3), text="C", content_width=10, y=30)
            and _near(border_next, y=40)
        ),
        "margin_left_widens_the_line": (
            margin.get("outcome") == "placed"
            and _near(_line(margin_row, 0), text="AA B", content_width=60, y=0)
            and _line(margin_row, 1) is None
        ),
        "margin_left_wraps_the_glyph": (
            narrow.get("outcome") == "placed"
            and _near(_line(narrow_row, 0), text="AA", content_width=20, y=0)
            and _near(_line(narrow_row, 1), text="B", content_width=30, y=10)
            and _line(narrow_row, 2) is None
        ),
        "start_chrome_stays_on_the_first_fragment": (
            uneven.get("outcome") == "placed"
            and _near(_line(uneven_row, 0), text="A", content_width=10)
            and _near(_line(uneven_row, 1), text="B", content_width=30)
            and _near(_line(uneven_row, 2), text="B", content_width=10)
        ),
        "percentage_padding_is_rejected": (
            percent.get("outcome") == "invalid" and percent.get("reason") == "inline padding is unsupported"
        ),
        "negative_margin_is_rejected": (
            negative.get("outcome") == "invalid" and negative.get("reason") == "inline margin is unsupported"
        ),
    }
    observed = {
        "fit": _lines(fit_row),
        "fit_next": None if fit_next is None else fit_next.get("y"),
        "split": _lines(split_row),
        "split_next": None if split_next is None else split_next.get("y"),
        "border": _lines(border_row),
        "margin": _lines(margin_row),
        "narrow": _lines(narrow_row),
        "uneven": _lines(uneven_row),
        "percent": {"outcome": percent.get("outcome"), "reason": percent.get("reason")},
        "negative": {"outcome": negative.get("outcome"), "reason": negative.get("reason")},
        "checks": checks,
    }
    return all(checks.values()), observed


def main() -> None:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - the probe must exit 0 even when it fails
        passed, observed = False, {"error": f"{type(exc).__name__}: {exc}"}
    payload = {"passed": bool(passed), "observed": observed if observed else {"error": "empty"}}
    try:
        encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    except (UnicodeEncodeError, TypeError) as exc:
        encoded = json.dumps(
            {"passed": False, "observed": {"error": f"{type(exc).__name__}: {exc}"}},
            separators=(",", ":"),
        ).encode("ascii")
    sys.stdout.buffer.write(encoded + b"\n")


if __name__ == "__main__":
    main()
