"""Place a wrapping flex column in normal flow.

Three 40px items in a 90px column occupy two columns, and the next block
starts under that definite height. wrap-reverse paints the first column at
the inline end. column-reverse packs each column from the bottom. A 90px
basis stays 90px tall instead of shrinking beside a 20px neighbor. An
automatic height has no definite block size, so the items stay one column.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree that still rejects column wrap exits 0 with passed
false.
"""

from __future__ import annotations

import json
import sys

_PAGE = (
    '<div id="page"><div id="col"><span id="a"></span><span id="b"></span>'
    '<span id="c"></span></div><p id="next">Z</p></div>'
)
_WRAP = """
#page { font-size: 10px; line-height: 10px; }
#col { display: flex; flex-direction: column; flex-wrap: wrap; width: 80px; height: 90px; }
#a { flex: none; width: 40px; height: 40px; }
#b { flex: none; width: 40px; height: 40px; }
#c { flex: none; width: 40px; height: 40px; }
"""
_REVERSE = """
#page { font-size: 10px; line-height: 10px; }
#col { display: flex; flex-direction: column; flex-wrap: wrap-reverse; width: 80px; height: 90px; }
#a { flex: none; width: 40px; height: 40px; }
#b { flex: none; width: 40px; height: 40px; }
#c { flex: none; width: 40px; height: 40px; }
"""
_BOTTOM = """
#page { font-size: 10px; line-height: 10px; }
#col { display: flex; flex-direction: column-reverse; flex-wrap: wrap; width: 80px; height: 90px; }
#a { flex: none; width: 40px; height: 40px; }
#b { flex: none; width: 40px; height: 40px; }
#c { flex: none; width: 40px; height: 40px; }
"""
_AUTO = """
#page { font-size: 10px; line-height: 10px; }
#col { display: flex; flex-direction: column; flex-wrap: wrap; width: 80px; }
#a { flex: none; width: 40px; height: 40px; }
#b { flex: none; width: 40px; height: 40px; }
#c { flex: none; width: 40px; height: 40px; }
"""
_HOLD = '<div id="hold"><span id="wide"></span><span id="tail"></span></div>'
_HOLD_CSS = """
#hold { display: flex; flex-direction: column; flex-wrap: wrap; width: 60px; height: 100px; }
#wide { flex-grow: 0; flex-shrink: 1; flex-basis: 90px; width: 30px; }
#tail { flex-grow: 0; flex-shrink: 1; flex-basis: 20px; width: 30px; }
"""


def _box(boxes: object, ident: str) -> dict[str, object] | None:
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if isinstance(item, dict) and item.get("id") == ident:
            return item
    return None


def _near(item: dict[str, object] | None, **expected: object) -> bool:
    if item is None:
        return False
    return all(item.get(key) == value for key, value in expected.items())


def _placed(box: dict[str, object] | None) -> dict[str, object] | None:
    if box is None:
        return None
    return {
        "x": box.get("x"),
        "y": box.get("y"),
        "content_width": box.get("content_width"),
        "content_height": box.get("content_height"),
    }


def _lay(layout, markup: str, stylesheet: str, width: int) -> dict[str, object]:
    try:
        placed = layout(markup, stylesheet, viewport_width=width)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without placement still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    wrapped = _lay(layout_normal_flow, _PAGE, _WRAP, 200)
    reverse = _lay(layout_normal_flow, _PAGE, _REVERSE, 200)
    bottom = _lay(layout_normal_flow, _PAGE, _BOTTOM, 200)
    automatic = _lay(layout_normal_flow, _PAGE, _AUTO, 200)
    held = _lay(layout_normal_flow, _HOLD, _HOLD_CSS, 200)

    def take(result: dict[str, object], ident: str) -> dict[str, object] | None:
        return _box(result.get("boxes"), ident)

    column = take(wrapped, "col")
    nxt = take(wrapped, "next")
    auto_col = take(automatic, "col")
    auto_next = take(automatic, "next")
    observed: dict[str, object] = {
        "wrap_outcome": wrapped.get("outcome"),
        "wrap_reason": wrapped.get("reason"),
        "a": _placed(take(wrapped, "a")),
        "b": _placed(take(wrapped, "b")),
        "c": _placed(take(wrapped, "c")),
        "col": _placed(column),
        "next": _placed(nxt),
        "reverse_outcome": reverse.get("outcome"),
        "reverse_reason": reverse.get("reason"),
        "reverse_a": _placed(take(reverse, "a")),
        "reverse_b": _placed(take(reverse, "b")),
        "reverse_c": _placed(take(reverse, "c")),
        "bottom_outcome": bottom.get("outcome"),
        "bottom_reason": bottom.get("reason"),
        "bottom_a": _placed(take(bottom, "a")),
        "bottom_b": _placed(take(bottom, "b")),
        "bottom_c": _placed(take(bottom, "c")),
        "auto_outcome": automatic.get("outcome"),
        "auto_reason": automatic.get("reason"),
        "auto_a": _placed(take(automatic, "a")),
        "auto_b": _placed(take(automatic, "b")),
        "auto_c": _placed(take(automatic, "c")),
        "auto_col": _placed(auto_col),
        "auto_next": _placed(auto_next),
        "hold_outcome": held.get("outcome"),
        "hold_reason": held.get("reason"),
        "wide": _placed(take(held, "wide")),
        "tail": _placed(take(held, "tail")),
    }
    checks = {
        "wraps_on_block_size": (
            wrapped.get("outcome") == "placed"
            and _near(take(wrapped, "a"), x=0, y=0, content_width=40, content_height=40)
            and _near(take(wrapped, "b"), x=0, y=40, content_width=40, content_height=40)
            and _near(take(wrapped, "c"), x=40, y=0, content_width=40, content_height=40)
            and _near(column, x=0, y=0, content_width=80, content_height=90)
            and isinstance(nxt, dict)
            and nxt.get("y") == 90
        ),
        "wrap_reverse": (
            reverse.get("outcome") == "placed"
            and _near(take(reverse, "c"), x=0, y=0, content_width=40, content_height=40)
            and _near(take(reverse, "a"), x=40, y=0, content_width=40, content_height=40)
            and _near(take(reverse, "b"), x=40, y=40, content_width=40, content_height=40)
        ),
        "column_reverse_packs_bottom": (
            bottom.get("outcome") == "placed"
            and _near(take(bottom, "a"), x=0, y=50, content_width=40, content_height=40)
            and _near(take(bottom, "b"), x=0, y=10, content_width=40, content_height=40)
            and _near(take(bottom, "c"), x=40, y=50, content_width=40, content_height=40)
        ),
        "hypothetical_stays": (
            held.get("outcome") == "placed"
            and _near(take(held, "wide"), x=0, y=0, content_width=30, content_height=90)
            and _near(take(held, "tail"), x=30, y=0, content_width=30, content_height=20)
        ),
        "automatic_height_stays_one_column": (
            automatic.get("outcome") == "placed"
            and _near(take(automatic, "a"), x=0, y=0, content_width=40, content_height=40)
            and _near(take(automatic, "b"), x=0, y=40, content_width=40, content_height=40)
            and _near(take(automatic, "c"), x=0, y=80, content_width=40, content_height=40)
            and _near(auto_col, content_width=80, content_height=120)
            and isinstance(auto_next, dict)
            and auto_next.get("y") == 120
        ),
    }
    observed["checks"] = checks
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
