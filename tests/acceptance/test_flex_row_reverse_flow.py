"""Place a row-reverse flex line from the inline end.

The first item's margin box ends on the right content edge. A definite
margin-left stays on that item's left. flex-end leaves free space on the
right, and an auto margin-right absorbs positive free space before packing.
A wrapped line uses the same end edge, and the following block starts under
the last line.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree that still rejects row-reverse exits 0 with passed
false.
"""

from __future__ import annotations

import json
import sys

_PAGE = "#page { font-size: 10px; line-height: 10px; }\n"
_PAIR = (
    '<div id="page"><div id="row"><span id="a"></span><span id="b"></span></div>'
    '<p id="next">Z</p></div>'
)
_ONE = '<div id="page"><div id="row"><span id="a"></span></div><p id="next">Z</p></div>'
_START = (
    _PAGE
    + "#row { display: flex; flex-direction: row-reverse; width: 100px; }\n"
    + "#a { flex: none; width: 20px; height: 10px; margin-left: 10px; }\n"
    + "#b { flex: none; width: 30px; height: 10px; }\n"
)
_END = (
    _PAGE
    + "#row { display: flex; flex-direction: row-reverse; justify-content: flex-end; width: 100px; }\n"
    + "#a { flex: none; width: 20px; height: 10px; margin-left: 10px; }\n"
    + "#b { flex: none; width: 30px; height: 10px; }\n"
)
_AUTO = (
    _PAGE
    + "#row { display: flex; flex-direction: row-reverse; justify-content: flex-start; width: 100px; }\n"
    + "#a { flex: none; width: 20px; height: 10px; margin-right: auto; }\n"
)
_WRAP = (
    _PAGE
    + "#row { display: flex; flex-direction: row-reverse; flex-wrap: wrap; width: 40px; }\n"
    + "#a { flex: none; width: 30px; height: 10px; }\n"
    + "#b { flex: none; width: 20px; height: 10px; }\n"
)


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


def _lay(layout, markup: str, stylesheet: str) -> dict[str, object]:
    try:
        placed = layout(markup, stylesheet, viewport_width=200)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without placement still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    cases = {
        "start": _lay(layout_normal_flow, _PAIR, _START),
        "end": _lay(layout_normal_flow, _PAIR, _END),
        "auto": _lay(layout_normal_flow, _ONE, _AUTO),
        "wrap": _lay(layout_normal_flow, _PAIR, _WRAP),
    }

    def take(name: str, ident: str) -> dict[str, object] | None:
        return _box(cases[name].get("boxes"), ident)

    observed: dict[str, object] = {
        name: {
            "outcome": result.get("outcome"),
            "reason": result.get("reason"),
            "a": _placed(take(name, "a")),
            "b": _placed(take(name, "b")),
            "next": _placed(take(name, "next")),
        }
        for name, result in cases.items()
    }
    checks = {
        "first_item_ends_on_the_right": (
            cases["start"].get("outcome") == "placed"
            and _near(take("start", "a"), x=80, y=0, content_width=20, content_height=10)
            and _near(take("start", "b"), x=40, y=0, content_width=30, content_height=10)
            and _near(take("start", "next"), y=10)
        ),
        "flex_end_leaves_free_space_on_the_right": (
            cases["end"].get("outcome") == "placed"
            and _near(take("end", "a"), x=40, y=0, content_width=20, content_height=10)
            and _near(take("end", "b"), x=0, y=0, content_width=30, content_height=10)
            and _near(take("end", "next"), y=10)
        ),
        "auto_main_start_margin_moves_to_the_left": (
            cases["auto"].get("outcome") == "placed"
            and _near(take("auto", "a"), x=0, y=0, content_width=20, content_height=10)
            and _near(take("auto", "next"), y=10)
        ),
        "wrapped_line_keeps_the_end_edge": (
            cases["wrap"].get("outcome") == "placed"
            and _near(take("wrap", "a"), x=10, y=0, content_width=30, content_height=10)
            and _near(take("wrap", "b"), x=20, y=10, content_width=20, content_height=10)
            and _near(take("wrap", "next"), y=20)
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
