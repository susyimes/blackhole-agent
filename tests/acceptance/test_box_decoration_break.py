"""Clone an inline's horizontal edges onto every line fragment.

In a 200px viewport at 10px, AA BB CC with 10px of padding on each side and
box-decoration-break clone paints three 40px lines in a 50px block and the
next block at y 30. The same span without clone paints widths 30, 20, and 30.
In a 65px block, clone still uses three 40px lines and the next block at y 30,
while slice keeps AA BB at width 60 and CC at width 30 with the next block at
y 20. An unfragmented AA stays one 40px line under both values. A 10px solid
border clones the same three 40px lines. slice matches the omitted property.
inherit is rejected, and a vertical writing mode stays rejected.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit.
"""

from __future__ import annotations

import json
import sys

_WORDS = '<div id="page"><div id="row"><span id="s">AA BB CC</span></div><div id="next">Z</div></div>'
_SHORT = '<div id="page"><div id="row"><span id="s">AA</span></div><div id="next">Z</div></div>'
_BASE = "#page, #row, #next, #s { font-size: 10px; line-height: 10px; }\n"
_PAD = "#s { padding-left: 10px; padding-right: 10px; }\n"
_CLONE = _PAD + "#s { box-decoration-break: clone; }\n"
_SLICE = _PAD + "#s { box-decoration-break: slice; }\n"
_NARROW = "#row { width: 50px; }\n"
_WIDE = "#row { width: 65px; }\n"
_BORDER = (
    "#row { width: 50px; }\n"
    "#s { border-left: 10px solid; border-right: 10px solid; box-decoration-break: clone; }\n"
)
_INHERIT = _PAD + "#s { box-decoration-break: inherit; }\n"
_VERTICAL = "#row { writing-mode: vertical-rl; }\n" + _CLONE


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
        if isinstance(line, dict):
            found.append({"text": line.get("text"), "w": line.get("content_width"), "y": line.get("y")})
    return found


def _three(box: dict[str, object] | None, widths: tuple[int, int, int]) -> bool:
    return (
        _near(_line(box, 0), text="AA", content_width=widths[0], y=0)
        and _near(_line(box, 1), text="BB", content_width=widths[1], y=10)
        and _near(_line(box, 2), text="CC", content_width=widths[2], y=20)
        and _line(box, 3) is None
    )


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without placement still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    narrow_clone = _lay(layout_normal_flow, _WORDS, _BASE + _NARROW + _CLONE)
    narrow_slice = _lay(layout_normal_flow, _WORDS, _BASE + _NARROW + _PAD)
    wide_clone = _lay(layout_normal_flow, _WORDS, _BASE + _WIDE + _CLONE)
    wide_slice = _lay(layout_normal_flow, _WORDS, _BASE + _WIDE + _PAD)
    wide_named = _lay(layout_normal_flow, _WORDS, _BASE + _WIDE + _SLICE)
    whole_clone = _lay(layout_normal_flow, _SHORT, _BASE + _CLONE)
    whole_slice = _lay(layout_normal_flow, _SHORT, _BASE + _PAD)
    border = _lay(layout_normal_flow, _WORDS, _BASE + _BORDER)
    inherited = _lay(layout_normal_flow, _WORDS, _BASE + _NARROW + _INHERIT)
    vertical = _lay(layout_normal_flow, _WORDS, _BASE + _VERTICAL)

    def row(placed: dict[str, object]) -> dict[str, object] | None:
        return _box(placed.get("boxes"), "row")

    def nxt(placed: dict[str, object]) -> dict[str, object] | None:
        return _box(placed.get("boxes"), "next")

    checks = {
        "clone_pays_both_edges_in_a_narrow_measure": (
            narrow_clone.get("outcome") == "placed"
            and _three(row(narrow_clone), (40, 40, 40))
            and _near(nxt(narrow_clone), y=30)
        ),
        "slice_keeps_one_pair_of_edges": (
            narrow_slice.get("outcome") == "placed"
            and _three(row(narrow_slice), (30, 20, 30))
            and _near(nxt(narrow_slice), y=30)
        ),
        "clone_wraps_earlier_than_slice": (
            wide_clone.get("outcome") == "placed"
            and _three(row(wide_clone), (40, 40, 40))
            and _near(nxt(wide_clone), y=30)
            and wide_slice.get("outcome") == "placed"
            and _near(_line(row(wide_slice), 0), text="AA BB", content_width=60, y=0)
            and _near(_line(row(wide_slice), 1), text="CC", content_width=30, y=10)
            and _line(row(wide_slice), 2) is None
            and _near(nxt(wide_slice), y=20)
        ),
        "named_slice_matches_the_omitted_property": (
            wide_named.get("outcome") == "placed"
            and _lines(row(wide_named)) == _lines(row(wide_slice))
            and _near(nxt(wide_named), y=20)
        ),
        "an_unbroken_span_stays_one_line": (
            whole_clone.get("outcome") == "placed"
            and _near(_line(row(whole_clone), 0), text="AA", content_width=40, y=0)
            and _line(row(whole_clone), 1) is None
            and _near(nxt(whole_clone), y=10)
            and whole_slice.get("outcome") == "placed"
            and _near(_line(row(whole_slice), 0), text="AA", content_width=40, y=0)
            and _near(nxt(whole_slice), y=10)
        ),
        "a_solid_border_clones_the_same_way": (
            border.get("outcome") == "placed"
            and _three(row(border), (40, 40, 40))
            and _near(nxt(border), y=30)
        ),
        "inherit_is_rejected": (
            inherited.get("outcome") == "invalid"
            and inherited.get("reason") == "box-decoration-break is unsupported"
        ),
        "vertical_writing_mode_stays_rejected": (
            vertical.get("outcome") == "invalid" and vertical.get("reason") == "inline chrome is unsupported"
        ),
    }
    observed = {
        "narrow_clone": _lines(row(narrow_clone)),
        "narrow_slice": _lines(row(narrow_slice)),
        "wide_clone": _lines(row(wide_clone)),
        "wide_slice": _lines(row(wide_slice)),
        "wide_named": _lines(row(wide_named)),
        "whole_clone": _lines(row(whole_clone)),
        "whole_slice": _lines(row(whole_slice)),
        "border": _lines(row(border)),
        "inherit": {"outcome": inherited.get("outcome"), "reason": inherited.get("reason")},
        "vertical": {"outcome": vertical.get("outcome"), "reason": vertical.get("reason")},
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
