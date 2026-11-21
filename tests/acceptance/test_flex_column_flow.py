"""Place a flex column on the block axis in normal flow.

A definite column shares its height by flex factors and stretches items to
its inline size. column-reverse packs the first item against the bottom.
An automatic column keeps each hypothetical main size, so flex-grow does
not spend the inline size. The following block starts under that column.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree that still rejects flex-direction column exits 0
with passed false.
"""

from __future__ import annotations

import json
import sys

_PAGE = (
    '<div id="page"><div id="col"><span id="a"></span><span id="b"></span></div>'
    '<p id="next">Z</p></div>'
)
_SHARE = """
#page { font-size: 10px; line-height: 10px; }
#col { display: flex; flex-direction: column; width: 40px; height: 90px; }
#a { flex: 1; }
#b { flex: 2; }
"""
_REVERSE = """
#page { font-size: 10px; line-height: 10px; }
#col { display: flex; flex-direction: column-reverse; width: 40px; height: 90px; }
#a { flex: 1; }
#b { flex: 2; }
"""
_PACK = """
#page { font-size: 10px; line-height: 10px; }
#col { display: flex; flex-direction: column-reverse; width: 40px; height: 90px; }
#a { flex: none; height: 10px; }
#b { flex: none; height: 20px; }
"""
_AUTO = """
#page { font-size: 10px; line-height: 10px; }
#col { display: flex; flex-direction: column; width: 100px; }
#a { flex-grow: 1; height: 30px; }
#b { flex-grow: 1; height: 10px; }
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


def _lay(layout, stylesheet: str, width: int) -> dict[str, object]:
    try:
        placed = layout(_PAGE, stylesheet, viewport_width=width)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without placement still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    shared = _lay(layout_normal_flow, _SHARE, 200)
    reverse = _lay(layout_normal_flow, _REVERSE, 200)
    packed = _lay(layout_normal_flow, _PACK, 200)
    automatic = _lay(layout_normal_flow, _AUTO, 200)

    def take(result: dict[str, object], ident: str) -> dict[str, object] | None:
        return _box(result.get("boxes"), ident)

    column = take(shared, "col")
    nxt = take(shared, "next")
    rev_col = take(reverse, "col")
    rev_next = take(reverse, "next")
    pack_col = take(packed, "col")
    auto_col = take(automatic, "col")
    auto_next = take(automatic, "next")
    observed: dict[str, object] = {
        "share_outcome": shared.get("outcome"),
        "share_reason": shared.get("reason"),
        "col": _placed(column),
        "a": _placed(take(shared, "a")),
        "b": _placed(take(shared, "b")),
        "next": _placed(nxt),
        "reverse_outcome": reverse.get("outcome"),
        "reverse_reason": reverse.get("reason"),
        "reverse_a": _placed(take(reverse, "a")),
        "reverse_b": _placed(take(reverse, "b")),
        "reverse_col": _placed(rev_col),
        "pack_outcome": packed.get("outcome"),
        "pack_reason": packed.get("reason"),
        "pack_a": _placed(take(packed, "a")),
        "pack_b": _placed(take(packed, "b")),
        "pack_col": _placed(pack_col),
        "auto_outcome": automatic.get("outcome"),
        "auto_reason": automatic.get("reason"),
        "auto_col": _placed(auto_col),
        "auto_a": _placed(take(automatic, "a")),
        "auto_b": _placed(take(automatic, "b")),
        "auto_next": _placed(auto_next),
    }
    column_height = column.get("border_height") if isinstance(column, dict) else None
    auto_height = auto_col.get("border_height") if isinstance(auto_col, dict) else None
    checks = {
        "shares_definite_block_size": (
            shared.get("outcome") == "placed"
            and _near(column, x=0, y=0, content_width=40, content_height=90)
            and _near(take(shared, "a"), x=0, y=0, content_width=40, content_height=30)
            and _near(take(shared, "b"), x=0, y=30, content_width=40, content_height=60)
            and column_height == 90
            and isinstance(nxt, dict)
            and nxt.get("y") == 90
        ),
        "reverse_fills_from_bottom": (
            reverse.get("outcome") == "placed"
            and _near(take(reverse, "a"), x=0, y=60, content_width=40, content_height=30)
            and _near(take(reverse, "b"), x=0, y=0, content_width=40, content_height=60)
            and isinstance(rev_col, dict)
            and rev_col.get("border_height") == 90
            and isinstance(rev_next, dict)
            and rev_next.get("y") == 90
        ),
        "reverse_packs_leftover_above": (
            packed.get("outcome") == "placed"
            and _near(take(packed, "a"), x=0, y=80, content_width=40, content_height=10)
            and _near(take(packed, "b"), x=0, y=60, content_width=40, content_height=20)
            and isinstance(pack_col, dict)
            and pack_col.get("content_height") == 90
        ),
        "automatic_height_ignores_inline_free_space": (
            automatic.get("outcome") == "placed"
            and _near(auto_col, x=0, y=0, content_width=100, content_height=40)
            and _near(take(automatic, "a"), x=0, y=0, content_width=100, content_height=30)
            and _near(take(automatic, "b"), x=0, y=30, content_width=100, content_height=10)
            and auto_height == 40
            and isinstance(auto_next, dict)
            and auto_next.get("y") == 40
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
