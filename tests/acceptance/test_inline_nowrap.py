"""Keep a nowrap inline together while the surrounding words still wrap.

In a 40px line at 10px per glyph, A <span>B C</span> D puts A on the first
line, the 30px span on the second, and D on the third. The following block
starts at y 30. The same words without nowrap put A B on the first line and
C D on the second, and the following block starts at y 20. A line wide enough
for every word keeps A B C D together. A 20px line lets B C overflow instead
of breaking. white-space:pre, nowrap inside pre, and nowrap beside a float
stay rejected.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A layout that still rejects nowrap exits 0 with passed false.
"""

from __future__ import annotations

import json

_PAGE = '<div id="page"><p id="row">A <span id="keep">B C</span> D</p><p id="next">Z</p></div>'
_FLOAT = '<div id="page"><p id="row"><span id="fl">XX</span>A <span id="keep">B C</span></p><p id="next">Z</p></div>'
_BASE = "html, body, div, p, span { margin: 0px; font-size: 10px; line-height: 10px; }\n"
_NARROW = _BASE + "#row { width: 40px; }\n"
_HELD = _NARROW + "#keep { white-space: nowrap; }\n"
_WIDE = _BASE + "#row { width: 80px; } #keep { white-space: nowrap; }\n"
_TIGHT = _BASE + "#row { width: 20px; } #keep { white-space: nowrap; }\n"
_PRE = _BASE + "#keep { white-space: pre; }\n"
_PARENT_PRE = _BASE + "#row { white-space: pre; width: 80px; } #keep { white-space: nowrap; }\n"
_FLOAT_CSS = _BASE + "#fl { float: left; } #row { width: 80px; } #keep { white-space: nowrap; }\n"


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


def _invalid(placed: dict[str, object], reason: str) -> bool:
    return placed.get("outcome") == "invalid" and placed.get("reason") == reason


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without the layout still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    held = _lay(layout_normal_flow, _PAGE, _HELD)
    plain = _lay(layout_normal_flow, _PAGE, _NARROW)
    wide = _lay(layout_normal_flow, _PAGE, _WIDE)
    tight = _lay(layout_normal_flow, _PAGE, _TIGHT)
    preserved = _lay(layout_normal_flow, _PAGE, _PRE)
    parent_pre = _lay(layout_normal_flow, _PAGE, _PARENT_PRE)
    floated = _lay(layout_normal_flow, _FLOAT, _FLOAT_CSS)

    held_row = _box(held.get("boxes"), "row")
    held_next = _box(held.get("boxes"), "next")
    plain_row = _box(plain.get("boxes"), "row")
    plain_next = _box(plain.get("boxes"), "next")
    wide_row = _box(wide.get("boxes"), "row")
    wide_next = _box(wide.get("boxes"), "next")
    tight_row = _box(tight.get("boxes"), "row")
    tight_next = _box(tight.get("boxes"), "next")

    checks = {
        "nowrap_span_moves_intact": (
            held.get("outcome") == "placed"
            and _near(_line(held_row, 0), text="A", x=0, y=0, content_width=10, height=10)
            and _near(_line(held_row, 1), text="B C", x=0, y=10, content_width=30, height=10)
            and _near(_line(held_row, 2), text="D", x=0, y=20, content_width=10, height=10)
            and _line(held_row, 3) is None
            and _near(held_row, content_width=40, content_height=30)
            and _near(held_next, y=30)
        ),
        "words_outside_still_wrap_without_nowrap": (
            plain.get("outcome") == "placed"
            and _near(_line(plain_row, 0), text="A B", x=0, y=0, content_width=30, height=10)
            and _near(_line(plain_row, 1), text="C D", x=0, y=10, content_width=30, height=10)
            and _line(plain_row, 2) is None
            and _near(plain_next, y=20)
        ),
        "wide_line_keeps_the_span_with_its_neighbors": (
            wide.get("outcome") == "placed"
            and _near(_line(wide_row, 0), text="A B C D", x=0, y=0, content_width=70, height=10)
            and _line(wide_row, 1) is None
            and _near(wide_next, y=10)
        ),
        "span_overflows_instead_of_splitting": (
            tight.get("outcome") == "placed"
            and _near(_line(tight_row, 0), text="A", content_width=10)
            and _near(_line(tight_row, 1), text="B C", content_width=30)
            and _near(_line(tight_row, 2), text="D", content_width=10)
            and _line(tight_row, 3) is None
            and _near(tight_row, content_width=20, content_height=30)
            and _near(tight_next, y=30)
        ),
        "pre_on_the_span_stays_rejected": _invalid(preserved, "inline white-space is unsupported"),
        "nowrap_inside_pre_stays_rejected": _invalid(parent_pre, "inline white-space is unsupported"),
        "nowrap_beside_a_float_stays_rejected": _invalid(floated, "nowrap inline is unsupported"),
    }
    observed = {
        "checks": checks,
        "held": {"outcome": held.get("outcome"), "reason": held.get("reason"), "lines": None if held_row is None else held_row.get("lines")},
        "plain_lines": None if plain_row is None else plain_row.get("lines"),
        "wide_lines": None if wide_row is None else wide_row.get("lines"),
        "tight_lines": None if tight_row is None else tight_row.get("lines"),
    }
    return all(checks.values()), observed


def main() -> None:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - the probe must exit 0 either way
        passed, observed = False, {"error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps({"passed": bool(passed), "observed": observed}, sort_keys=True))


if __name__ == "__main__":
    main()
