"""Place a wrapping flex container in normal flow.

Three 100px items in a 200px wrap row occupy two lines, and the next block
starts under the second line. A 90px basis stays 90px wide instead of shrinking
beside a 20px neighbor. wrap-reverse paints the later line at the cross start.
Two items that fit stay on one line. A nowrap row still shares free space.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree that still rejects flex-wrap exits 0 with passed false.
"""

from __future__ import annotations

import json
import sys

_WRAP = (
    '<div id="page"><div id="row"><span id="a"></span><span id="b"></span>'
    '<span id="c"></span></div><p id="next">Z</p></div>'
)
_WRAP_CSS = """
#page { font-size: 10px; line-height: 10px; }
#row { display: flex; flex-wrap: wrap; }
#a { flex: none; width: 100px; height: 10px; }
#b { flex: none; width: 100px; height: 10px; }
#c { flex: none; width: 100px; height: 10px; }
"""

_REVERSE_CSS = """
#page { font-size: 10px; line-height: 10px; }
#row { display: flex; flex-wrap: wrap-reverse; }
#a { flex: none; width: 100px; height: 10px; }
#b { flex: none; width: 100px; height: 10px; }
#c { flex: none; width: 100px; height: 10px; }
"""

_HOLD = '<div id="hold"><span id="wide"></span><span id="tail"></span></div>'
_HOLD_CSS = """
#hold { display: flex; flex-wrap: wrap; }
#wide { flex-grow: 0; flex-shrink: 1; flex-basis: 90px; height: 10px; }
#tail { flex-grow: 0; flex-shrink: 1; flex-basis: 20px; height: 10px; }
"""

_PAIR = '<div id="pair"><span id="left"></span><span id="right"></span></div>'
_PAIR_CSS = """
#pair { display: flex; flex-wrap: wrap; }
#left { flex: none; width: 40px; height: 10px; }
#right { flex: none; width: 40px; height: 10px; }
"""

_ROW = (
    '<div id="page"><div id="row"><span id="grow"></span>'
    '<span id="more"></span></div><p id="next">Z</p></div>'
)
_ROW_CSS = """
#page { font-size: 10px; line-height: 10px; }
#row { display: flex; height: 10px; }
#grow { flex: 1; }
#more { flex: 2; }
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

    wrapped = _lay(layout_normal_flow, _WRAP, _WRAP_CSS, 200)
    reverse = _lay(layout_normal_flow, _WRAP, _REVERSE_CSS, 200)
    held = _lay(layout_normal_flow, _HOLD, _HOLD_CSS, 100)
    pair = _lay(layout_normal_flow, _PAIR, _PAIR_CSS, 100)
    shared = _lay(layout_normal_flow, _ROW, _ROW_CSS, 300)

    def take(result: dict[str, object], ident: str) -> dict[str, object] | None:
        return _box(result.get("boxes"), ident)

    row = take(wrapped, "row")
    nxt = take(wrapped, "next")
    rev_row = take(reverse, "row")
    rev_next = take(reverse, "next")
    hold = take(held, "hold")
    observed: dict[str, object] = {
        "wrap_outcome": wrapped.get("outcome"),
        "wrap_reason": wrapped.get("reason"),
        "a": _placed(take(wrapped, "a")),
        "b": _placed(take(wrapped, "b")),
        "c": _placed(take(wrapped, "c")),
        "row": _placed(row),
        "next": _placed(nxt),
        "reverse_outcome": reverse.get("outcome"),
        "reverse_reason": reverse.get("reason"),
        "reverse_a": _placed(take(reverse, "a")),
        "reverse_b": _placed(take(reverse, "b")),
        "reverse_c": _placed(take(reverse, "c")),
        "reverse_row": _placed(rev_row),
        "hold_outcome": held.get("outcome"),
        "hold_reason": held.get("reason"),
        "wide": _placed(take(held, "wide")),
        "tail": _placed(take(held, "tail")),
        "hold": _placed(hold),
        "pair_outcome": pair.get("outcome"),
        "left": _placed(take(pair, "left")),
        "right": _placed(take(pair, "right")),
        "nowrap_outcome": shared.get("outcome"),
        "grow": _placed(take(shared, "grow")),
        "more": _placed(take(shared, "more")),
    }
    row_height = row.get("border_height") if isinstance(row, dict) else None
    reverse_height = rev_row.get("border_height") if isinstance(rev_row, dict) else None
    checks = {
        "wraps_before_flexing": (
            wrapped.get("outcome") == "placed"
            and _near(take(wrapped, "a"), x=0, y=0, content_width=100, content_height=10)
            and _near(take(wrapped, "b"), x=100, y=0, content_width=100, content_height=10)
            and _near(take(wrapped, "c"), x=0, y=10, content_width=100, content_height=10)
            and row_height == 20
            and isinstance(nxt, dict)
            and nxt.get("y") == 20
        ),
        "hypothetical_stays": (
            held.get("outcome") == "placed"
            and _near(take(held, "wide"), x=0, y=0, content_width=90, content_height=10)
            and _near(take(held, "tail"), x=0, y=10, content_width=20, content_height=10)
            and isinstance(hold, dict)
            and hold.get("border_height") == 20
        ),
        "wrap_reverse": (
            reverse.get("outcome") == "placed"
            and _near(take(reverse, "c"), x=0, y=0, content_width=100, content_height=10)
            and _near(take(reverse, "a"), x=0, y=10, content_width=100, content_height=10)
            and _near(take(reverse, "b"), x=100, y=10, content_width=100, content_height=10)
            and reverse_height == 20
            and isinstance(rev_next, dict)
            and rev_next.get("y") == 20
        ),
        "fits_one_line": (
            pair.get("outcome") == "placed"
            and _near(take(pair, "left"), x=0, y=0, content_width=40, content_height=10)
            and _near(take(pair, "right"), x=40, y=0, content_width=40, content_height=10)
        ),
        "nowrap_unchanged": (
            shared.get("outcome") == "placed"
            and _near(take(shared, "grow"), x=0, y=0, content_width=100, content_height=10)
            and _near(take(shared, "more"), x=100, y=0, content_width=200, content_height=10)
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
