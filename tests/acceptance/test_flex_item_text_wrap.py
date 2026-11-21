"""Wrap text inside a row flex item.

A definite main size breaks the item's text into line boxes and the
automatic cross size is those lines, so the following block starts under
the row. Automatic width keeps the text on one max-content line. A
stretched sibling grows to the wrapped row, and align-self flex-start
keeps a shorter item at its own height.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree that still sizes the item as one strut exits 0
with passed false.
"""

from __future__ import annotations

import json
import sys

_PAGE = "#page { font-size: 10px; line-height: 10px; }\n"
_WRAP = (
    '<div id="page"><div id="row"><span id="item">AA BB</span></div>'
    '<p id="next">Z</p></div>'
)
_WRAP_CSS = (
    _PAGE
    + "#row { display: flex; width: 100px; }\n"
    + "#item { flex: none; width: 20px; font-size: 10px; line-height: 10px; }\n"
    + "#next { font-size: 10px; line-height: 10px; }\n"
)
_AUTO_CSS = (
    _PAGE
    + "#row { display: flex; width: 200px; }\n"
    + "#item { flex: none; font-size: 10px; line-height: 10px; }\n"
    + "#next { font-size: 10px; line-height: 10px; }\n"
)
_ROW = (
    '<div id="page"><div id="row"><span id="wrap">AA BB</span>'
    '<span id="short"></span><span id="grow"></span></div><p id="next">Z</p></div>'
)
_ROW_CSS = (
    _PAGE
    + "#row { display: flex; width: 100px; }\n"
    + "#wrap { flex: none; width: 20px; font-size: 10px; line-height: 10px; }\n"
    + "#short { flex: none; width: 10px; height: 10px; align-self: flex-start; }\n"
    + "#grow { flex: 1 1 0px; }\n"
    + "#next { font-size: 10px; line-height: 10px; }\n"
)


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


def _lay(layout, markup: str, stylesheet: str, viewport_width: int) -> dict[str, object]:
    try:
        placed = layout(markup, stylesheet, viewport_width=viewport_width)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def _public(box: dict[str, object] | None) -> dict[str, object] | None:
    if box is None:
        return None
    return {
        "x": box.get("x"),
        "y": box.get("y"),
        "content_width": box.get("content_width"),
        "content_height": box.get("content_height"),
        "lines": box.get("lines"),
    }


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without placement still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    wrapped = _lay(layout_normal_flow, _WRAP, _WRAP_CSS, 200)
    automatic = _lay(layout_normal_flow, _WRAP, _AUTO_CSS, 300)
    shared = _lay(layout_normal_flow, _ROW, _ROW_CSS, 200)
    item = _box(wrapped.get("boxes"), "item")
    auto = _box(automatic.get("boxes"), "item")
    wrap = _box(shared.get("boxes"), "wrap")
    short = _box(shared.get("boxes"), "short")
    grow = _box(shared.get("boxes"), "grow")
    observed: dict[str, object] = {
        "wrapped_outcome": wrapped.get("outcome"),
        "wrapped_reason": wrapped.get("reason"),
        "item": _public(item),
        "next": _public(_box(wrapped.get("boxes"), "next")),
        "row": _public(_box(wrapped.get("boxes"), "row")),
        "automatic_outcome": automatic.get("outcome"),
        "automatic_item": _public(auto),
        "automatic_next": _public(_box(automatic.get("boxes"), "next")),
        "shared_outcome": shared.get("outcome"),
        "shared_reason": shared.get("reason"),
        "wrap": _public(wrap),
        "short": _public(short),
        "grow": _public(grow),
        "shared_next": _public(_box(shared.get("boxes"), "next")),
    }
    checks = {
        "definite_width_wraps_onto_two_lines": (
            wrapped.get("outcome") == "placed"
            and _near(item, x=0, y=0, content_width=20, content_height=20)
            and _near(_line(item, 0), text="AA", x=0, y=0, height=10, content_width=20)
            and _near(_line(item, 1), text="BB", x=0, y=10, height=10, content_width=20)
            and _near(_box(wrapped.get("boxes"), "row"), content_height=20)
            and _near(_box(wrapped.get("boxes"), "next"), x=0, y=20)
        ),
        "automatic_width_stays_one_max_content_line": (
            automatic.get("outcome") == "placed"
            and _near(auto, x=0, y=0, content_width=50, content_height=10)
            and _near(_line(auto, 0), text="AA BB", x=0, y=0, height=10, content_width=50)
            and _line(auto, 1) is None
            and _near(_box(automatic.get("boxes"), "next"), y=10)
        ),
        "row_stretches_and_keeps_flex_start_height": (
            shared.get("outcome") == "placed"
            and _near(wrap, x=0, y=0, content_width=20, content_height=20)
            and _near(short, x=20, y=0, content_width=10, content_height=10)
            and _near(grow, x=30, y=0, content_width=70, content_height=20)
            and _near(_box(shared.get("boxes"), "next"), y=20)
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
