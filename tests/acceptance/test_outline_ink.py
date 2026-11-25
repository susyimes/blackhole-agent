"""Paint a CSS outline outside a block without moving the border box.

A marginless page places a 40 by 20 subject at (0, 0) and a follower at y 20.
The outline's outer edge is the border box outset by offset plus thickness.
``none`` records no outline. A non-replaced inline and an unparsable style
are invalid.

Prints JSON with boolean passed and nonempty observed. Exit 0 either way.
"""

from __future__ import annotations

import json

_PAGE = '<div id="page"><div id="subject"></div><div id="next"></div></div>'
_RESET = (
    "#page, #subject, #next { margin: 0px; }\n"
    "#subject { width: 40px; height: 20px; }\n"
    "#next { height: 8px; }\n"
)
_HOST = (
    '<div id="page"><div id="host"><div id="subject"></div>'
    '<div id="next"></div></div></div>'
)
_HOST_RESET = (
    "#page, #host, #subject, #next { margin: 0px; }\n"
    "#host { color: #c00; }\n"
    "#subject { width: 40px; height: 20px; outline: solid; }\n"
    "#next { height: 8px; }\n"
)
_INLINE = '<div id="page"><p id="text"><span id="mark">Hi</span></p></div>'
_INLINE_CSS = "#page, #text, #mark { margin: 0px; }\n#mark { outline: solid; }\n"


def _layout(function, markup: str, stylesheet: str) -> dict[str, object]:
    try:
        placed = function(markup, stylesheet, viewport_width=200)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    if not isinstance(placed, dict):
        return {"outcome": "error", "reason": "layout is invalid", "boxes": None}
    return placed


def _box(result: dict[str, object], ident: str) -> dict[str, object] | None:
    boxes = result.get("boxes")
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if isinstance(item, dict) and item.get("id") == ident:
            return item
    return None


def _edge(box: dict[str, object] | None) -> dict[str, object] | None:
    if box is None:
        return None
    return {
        "x": box.get("x"),
        "y": box.get("y"),
        "border_width": box.get("border_width"),
        "border_height": box.get("border_height"),
    }


def _still(result: dict[str, object]) -> bool:
    subject = _edge(_box(result, "subject"))
    follower = _edge(_box(result, "next"))
    page = _edge(_box(result, "page"))
    return (
        result.get("outcome") == "placed"
        and subject == {"x": 0, "y": 0, "border_width": 40, "border_height": 20}
        and follower is not None
        and follower.get("y") == 20
        and page is not None
        and page.get("border_width") == 200
        and page.get("border_height") == 28
    )


def _outline(result: dict[str, object]) -> object:
    box = _box(result, "subject")
    if box is None:
        return None
    return box.get("outline")


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without layout still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    offset = _layout(
        layout_normal_flow,
        _PAGE,
        _RESET + "#subject { outline: 3px solid #00f; outline-offset: 4px; }\n",
    )
    current = _layout(
        layout_normal_flow,
        _PAGE,
        _RESET + "#subject { color: #c00; outline: solid; }\n",
    )
    inherited = _layout(layout_normal_flow, _HOST, _HOST_RESET)
    wider = _layout(
        layout_normal_flow,
        _PAGE,
        _RESET + "#subject { outline: 3px solid #00f; outline-offset: 4px; outline-width: 5px; }\n",
    )
    absent = _layout(layout_normal_flow, _PAGE, _RESET + "#subject { outline: none; }\n")
    broken = _layout(layout_normal_flow, _PAGE, _RESET + "#subject { outline: not-a-style; }\n")
    inline = _layout(layout_normal_flow, _INLINE, _INLINE_CSS)
    observed: dict[str, object] = {
        "offset": {
            "outcome": offset.get("outcome"),
            "reason": offset.get("reason"),
            "subject": _edge(_box(offset, "subject")),
            "next": _edge(_box(offset, "next")),
            "page": _edge(_box(offset, "page")),
            "outline": _outline(offset),
        },
        "current": {
            "outcome": current.get("outcome"),
            "outline": _outline(current),
            "subject": _edge(_box(current, "subject")),
            "next_y": None if _box(current, "next") is None else _box(current, "next").get("y"),
        },
        "inherited": {
            "outcome": inherited.get("outcome"),
            "outline": _outline(inherited),
            "subject": _edge(_box(inherited, "subject")),
            "next_y": None if _box(inherited, "next") is None else _box(inherited, "next").get("y"),
        },
        "wider": {"outcome": wider.get("outcome"), "outline": _outline(wider)},
        "absent": {
            "outcome": absent.get("outcome"),
            "has_outline": "outline" in (_box(absent, "subject") or {}),
            "next_y": None if _box(absent, "next") is None else _box(absent, "next").get("y"),
        },
        "broken": {"outcome": broken.get("outcome"), "reason": broken.get("reason")},
        "inline": {"outcome": inline.get("outcome"), "reason": inline.get("reason")},
    }
    offset_ink = _outline(offset)
    current_ink = _outline(current)
    inherited_ink = _outline(inherited)
    wider_ink = _outline(wider)
    checks = {
        "offset_keeps_the_border_box": _still(offset),
        "offset_outer_edge": offset_ink
        == {
            "style": "solid",
            "color": "#0000ff",
            "thickness": 3,
            "offset": 4,
            "x": -7,
            "y": -7,
            "width": 54,
            "height": 34,
        },
        "currentcolor_uses_the_declared_color": _still(current)
        and current_ink
        == {
            "style": "solid",
            "color": "#cc0000",
            "thickness": 3,
            "offset": 0,
            "x": -3,
            "y": -3,
            "width": 46,
            "height": 26,
        },
        "inherited_color_paints_the_child": inherited.get("outcome") == "placed"
        and _edge(_box(inherited, "subject")) == {"x": 0, "y": 0, "border_width": 40, "border_height": 20}
        and _box(inherited, "next") is not None
        and _box(inherited, "next").get("y") == 20
        and inherited_ink
        == {
            "style": "solid",
            "color": "#cc0000",
            "thickness": 3,
            "offset": 0,
            "x": -3,
            "y": -3,
            "width": 46,
            "height": 26,
        },
        "later_width_replaces_the_shorthand": _still(wider)
        and wider_ink
        == {
            "style": "solid",
            "color": "#0000ff",
            "thickness": 5,
            "offset": 4,
            "x": -9,
            "y": -9,
            "width": 58,
            "height": 38,
        },
        "none_records_no_outline": _still(absent) and "outline" not in (_box(absent, "subject") or {}),
        "unparsable_outline_is_invalid": broken.get("outcome") == "invalid"
        and broken.get("reason") == "outline is invalid",
        "inline_outline_is_invalid": inline.get("outcome") == "invalid"
        and inline.get("reason") == "inline outline is unsupported",
    }
    observed["checks"] = checks
    return all(checks.values()), observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
