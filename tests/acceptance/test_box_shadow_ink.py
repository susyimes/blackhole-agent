"""Paint CSS box-shadow ink without moving the border box.

A marginless page places a 40 by 20 subject, with 4px padding and a 2px
solid border, at (0, 0). The border box is 52 by 32 and the follower starts
at y 32. An outset shadow is that border box expanded by the spread and
shifted by the offsets. Blur stays a radius. An inset shadow's hole is the
padding box contracted by the spread and shifted by the offsets. none
records nothing. A negative blur and a non-replaced inline are rejected.

Prints JSON with boolean passed and nonempty observed. Exit 0 either way.
"""

from __future__ import annotations

import json

_PAGE = '<div id="page"><div id="subject"></div><div id="next"></div></div>'
_RESET = (
    "#page, #subject, #next { margin: 0px; }\n"
    "#subject { width: 40px; height: 20px; padding: 4px; border-width: 2px; border-style: solid; }\n"
    "#next { height: 8px; }\n"
)
_PLAIN = (
    "#page, #subject, #next { margin: 0px; }\n"
    "#subject { width: 40px; height: 20px; }\n"
    "#next { height: 8px; }\n"
)
_HOST = (
    '<div id="page"><div id="host"><div id="subject"></div>'
    '<div id="next"></div></div></div>'
)
_HOST_CSS = (
    "#page, #host, #subject, #next { margin: 0px; }\n"
    "#host { color: #c00; }\n"
    "#subject { width: 40px; height: 20px; box-shadow: 1px 2px; }\n"
    "#next { height: 8px; }\n"
)
_INLINE = '<div id="page"><p id="text"><span id="mark">Hi</span></p></div>'
_INLINE_CSS = "#page, #text, #mark { margin: 0px; }\n#mark { box-shadow: 1px 1px; }\n"
_EDGE = {"x": 0, "y": 0, "border_width": 52, "border_height": 32}
_PLAIN_EDGE = {"x": 0, "y": 0, "border_width": 40, "border_height": 20}


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


def _shadows(result: dict[str, object]) -> object:
    box = _box(result, "subject")
    if box is None:
        return None
    return box.get("shadows")


def _next_y(result: dict[str, object]) -> object:
    box = _box(result, "next")
    if box is None:
        return None
    return box.get("y")


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without layout still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    spread = _layout(
        layout_normal_flow,
        _PAGE,
        _RESET + "#subject { box-shadow: 4px 6px 0 2px #010203; }\n",
    )
    blurred = _layout(
        layout_normal_flow,
        _PAGE,
        _RESET + "#subject { box-shadow: 4px 6px 3px 2px #010203; }\n",
    )
    bare = _layout(layout_normal_flow, _PAGE, _RESET)
    inset = _layout(
        layout_normal_flow,
        _PAGE,
        _RESET + "#subject { box-shadow: inset 10px 0 0 4px #0a0b0c; }\n",
    )
    pair = _layout(
        layout_normal_flow,
        _PAGE,
        _RESET + "#subject { box-shadow: rgb(255, 0, 0) 4px 6px, inset 10px 0 0 4px #0a0b0c; }\n",
    )
    current = _layout(
        layout_normal_flow,
        _PAGE,
        _PLAIN + "#subject { color: #c00; box-shadow: 1px 2px; }\n",
    )
    inherited = _layout(layout_normal_flow, _HOST, _HOST_CSS)
    shrunk = _layout(
        layout_normal_flow,
        _PAGE,
        _PLAIN + "#subject { box-shadow: 0 0 0 -30px #010203; }\n",
    )
    absent = _layout(layout_normal_flow, _PAGE, _RESET + "#subject { box-shadow: none; }\n")
    broken = _layout(
        layout_normal_flow,
        _PAGE,
        _RESET + "#subject { box-shadow: 4px 6px -1px; }\n",
    )
    inline = _layout(layout_normal_flow, _INLINE, _INLINE_CSS)
    spread_ink = _shadows(spread)
    blurred_ink = _shadows(blurred)
    inset_ink = _shadows(inset)
    pair_ink = _shadows(pair)
    current_ink = _shadows(current)
    inherited_ink = _shadows(inherited)
    shrunk_ink = _shadows(shrunk)
    observed: dict[str, object] = {
        "spread": {
            "outcome": spread.get("outcome"),
            "reason": spread.get("reason"),
            "subject": _edge(_box(spread, "subject")),
            "next_y": _next_y(spread),
            "shadows": spread_ink,
        },
        "blurred": {"outcome": blurred.get("outcome"), "shadows": blurred_ink},
        "bare": {"subject": _edge(_box(bare, "subject")), "next_y": _next_y(bare)},
        "inset": {"outcome": inset.get("outcome"), "shadows": inset_ink},
        "pair": {"outcome": pair.get("outcome"), "shadows": pair_ink},
        "current": {"outcome": current.get("outcome"), "shadows": current_ink, "next_y": _next_y(current)},
        "inherited": {
            "outcome": inherited.get("outcome"),
            "shadows": inherited_ink,
            "subject": _edge(_box(inherited, "subject")),
            "next_y": _next_y(inherited),
        },
        "shrunk": {"outcome": shrunk.get("outcome"), "shadows": shrunk_ink},
        "absent": {
            "outcome": absent.get("outcome"),
            "has_shadows": "shadows" in (_box(absent, "subject") or {}),
            "next_y": _next_y(absent),
        },
        "broken": {"outcome": broken.get("outcome"), "reason": broken.get("reason")},
        "inline": {"outcome": inline.get("outcome"), "reason": inline.get("reason")},
    }
    shape = {
        "inset": False,
        "geometry": "shape",
        "color": "#010203",
        "offset_x": 4,
        "offset_y": 6,
        "blur": 0,
        "spread": 2,
        "x": 2,
        "y": 4,
        "width": 56,
        "height": 36,
    }
    hole = {
        "inset": True,
        "geometry": "hole",
        "color": "#0a0b0c",
        "offset_x": 10,
        "offset_y": 0,
        "blur": 0,
        "spread": 4,
        "x": 16,
        "y": 6,
        "width": 40,
        "height": 20,
        "clip_x": 2,
        "clip_y": 2,
        "clip_width": 48,
        "clip_height": 28,
    }
    checks = {
        "spread_keeps_the_border_box": spread.get("outcome") == "placed"
        and _edge(_box(spread, "subject")) == _EDGE
        and _edge(_box(bare, "subject")) == _EDGE
        and _next_y(spread) == 32
        and _next_y(spread) == _next_y(bare)
        and spread_ink == [shape],
        "blur_does_not_enlarge_the_shape": blurred.get("outcome") == "placed"
        and blurred_ink == [{**shape, "blur": 3}],
        "inset_hole_uses_the_padding_edge": inset.get("outcome") == "placed"
        and _edge(_box(inset, "subject")) == _EDGE
        and _next_y(inset) == 32
        and inset_ink == [hole],
        "comma_inside_a_color_keeps_source_order": pair.get("outcome") == "placed"
        and pair_ink
        == [
            {
                "inset": False,
                "geometry": "shape",
                "color": "#ff0000",
                "offset_x": 4,
                "offset_y": 6,
                "blur": 0,
                "spread": 0,
                "x": 4,
                "y": 6,
                "width": 52,
                "height": 32,
            },
            hole,
        ],
        "omitted_color_uses_currentcolor": current.get("outcome") == "placed"
        and _edge(_box(current, "subject")) == _PLAIN_EDGE
        and _next_y(current) == 20
        and current_ink
        == [
            {
                "inset": False,
                "geometry": "shape",
                "color": "#cc0000",
                "offset_x": 1,
                "offset_y": 2,
                "blur": 0,
                "spread": 0,
                "x": 1,
                "y": 2,
                "width": 40,
                "height": 20,
            }
        ],
        "inherited_color_paints_the_child": inherited.get("outcome") == "placed"
        and _edge(_box(inherited, "subject")) == _PLAIN_EDGE
        and _next_y(inherited) == 20
        and inherited_ink == current_ink,
        "negative_spread_shrinks_through_the_box": shrunk.get("outcome") == "placed"
        and shrunk_ink
        == [
            {
                "inset": False,
                "geometry": "shape",
                "color": "#010203",
                "offset_x": 0,
                "offset_y": 0,
                "blur": 0,
                "spread": -30,
                "x": 30,
                "y": 30,
                "width": -20,
                "height": -40,
            }
        ],
        "none_records_no_shadow": absent.get("outcome") == "placed"
        and "shadows" not in (_box(absent, "subject") or {})
        and _next_y(absent) == 32,
        "negative_blur_is_invalid": broken.get("outcome") == "invalid"
        and broken.get("reason") == "box-shadow is invalid",
        "inline_shadow_is_rejected": inline.get("outcome") == "invalid"
        and inline.get("reason") == "inline box-shadow is unsupported",
    }
    observed["checks"] = checks
    return all(checks.values()), observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
