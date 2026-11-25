"""Rest a scrollport on the snap edges of its children.

A marginless page places a 100px overflow scroll port. Two 20px children
sit at y 0 and y 40, then a tail. Mandatory snap of an intended y 20
resolves to 40, the later edge. Proximity keeps 150. Padding and margin
move that rest. The children and the following block stay in flow.

Prints JSON with boolean passed and nonempty observed. Exit 0 either way.
"""

from __future__ import annotations

import json

_PAGE = (
    '<div id="page"><div id="port"><div id="low"></div><div id="high"></div>'
    '<div id="tail"></div></div><div id="next"></div></div>'
)
_RESET = (
    "#page, #port, #low, #high, #tail, #next { margin: 0px; }\n"
    "#port { overflow: scroll; height: 100px; }\n"
    "#low { height: 20px; }\n"
    "#high { height: 20px; margin-top: 20px; }\n"
    "#tail { height: 200px; }\n"
    "#next { height: 8px; }\n"
)
_MANDATORY = _RESET + (
    "#port { scroll-snap-type: y mandatory; }\n"
    "#low, #high { scroll-snap-align: start; }\n"
)
_PROXIMITY = (
    "#page, #port, #low, #tail, #next { margin: 0px; }\n"
    "#port { overflow: scroll; height: 100px; scroll-snap-type: y proximity; }\n"
    "#low { height: 20px; scroll-snap-align: start; }\n"
    "#tail { height: 400px; }\n"
    "#next { height: 8px; }\n"
)
_PAD_PAGE = (
    '<div id="page"><div id="port"><div id="only"></div>'
    '<div id="tail"></div></div><div id="next"></div></div>'
)
_PAD = (
    "#page, #port, #only, #tail, #next { margin: 0px; }\n"
    "#port { overflow: scroll; height: 100px; scroll-snap-type: y mandatory; scroll-padding-top: 10px; }\n"
    "#only { height: 20px; margin-top: 30px; scroll-snap-align: start; }\n"
    "#tail { height: 200px; }\n"
    "#next { height: 8px; }\n"
)
_MARGIN = (
    "#page, #port, #only, #tail, #next { margin: 0px; }\n"
    "#port { overflow: scroll; height: 100px; scroll-snap-type: y mandatory; }\n"
    "#only { height: 20px; margin-top: 30px; scroll-snap-align: start; scroll-margin-top: 15px; }\n"
    "#tail { height: 200px; }\n"
    "#next { height: 8px; }\n"
)
_VISIBLE = (
    "#page, #port, #low, #next { margin: 0px; }\n"
    "#port { overflow: visible; height: 100px; scroll-snap-type: y mandatory; }\n"
    "#low { height: 20px; scroll-snap-align: start; }\n"
    "#next { height: 8px; }\n"
)
_VERTICAL = (
    "#page, #port, #low, #next { margin: 0px; }\n"
    "#port { overflow: scroll; width: 100px; height: 100px; writing-mode: vertical-rl; scroll-snap-type: y mandatory; }\n"
    "#low { height: 20px; scroll-snap-align: start; }\n"
    "#next { height: 8px; }\n"
)
_SIMPLE = (
    '<div id="page"><div id="port"><div id="low"></div></div><div id="next"></div></div>'
)
_PROX_PAGE = (
    '<div id="page"><div id="port"><div id="low"></div>'
    '<div id="tail"></div></div><div id="next"></div></div>'
)


def _layout(function, markup: str, stylesheet: str, **kwargs: object) -> dict[str, object]:
    try:
        placed = function(markup, stylesheet, viewport_width=200, **kwargs)
    except TypeError as exc:
        return {"outcome": "invalid", "reason": str(exc), "boxes": None}
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


def _point(result: dict[str, object], ident: str) -> dict[str, object] | None:
    box = _box(result, ident)
    if box is None:
        return None
    return {"y": box.get("y"), "border_height": box.get("border_height")}


def _snap(result: dict[str, object]) -> object:
    box = _box(result, "port")
    if box is None:
        return None
    return box.get("snap")


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without layout still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    mandatory = _layout(
        layout_normal_flow, _PAGE, _MANDATORY, port_scroll={"port": (0, 20)}
    )
    proximity = _layout(
        layout_normal_flow, _PROX_PAGE, _PROXIMITY, port_scroll={"port": (0, 150)}
    )
    padded = _layout(layout_normal_flow, _PAD_PAGE, _PAD)
    margined = _layout(layout_normal_flow, _PAD_PAGE, _MARGIN)
    plain = _layout(layout_normal_flow, _PAGE, _RESET, port_scroll={"port": (0, 20)})
    broken = _layout(
        layout_normal_flow,
        _PAGE,
        _RESET + "#port { scroll-snap-type: sideways; }\n",
    )
    visible = _layout(layout_normal_flow, _SIMPLE, _VISIBLE)
    vertical = _layout(layout_normal_flow, _SIMPLE, _VERTICAL)
    observed: dict[str, object] = {
        "mandatory": {
            "outcome": mandatory.get("outcome"),
            "reason": mandatory.get("reason"),
            "low": _point(mandatory, "low"),
            "high": _point(mandatory, "high"),
            "next": _point(mandatory, "next"),
            "port": _point(mandatory, "port"),
            "snap": _snap(mandatory),
        },
        "proximity": {
            "outcome": proximity.get("outcome"),
            "low": _point(proximity, "low"),
            "next": _point(proximity, "next"),
            "snap": _snap(proximity),
        },
        "padded": {
            "outcome": padded.get("outcome"),
            "only": _point(padded, "only"),
            "snap": _snap(padded),
        },
        "margined": {
            "outcome": margined.get("outcome"),
            "only": _point(margined, "only"),
            "snap": _snap(margined),
        },
        "plain": {
            "outcome": plain.get("outcome"),
            "has_snap": "snap" in (_box(plain, "port") or {}),
            "high": _point(plain, "high"),
        },
        "broken": {"outcome": broken.get("outcome"), "reason": broken.get("reason")},
        "visible": {"outcome": visible.get("outcome"), "reason": visible.get("reason")},
        "vertical": {"outcome": vertical.get("outcome"), "reason": vertical.get("reason")},
    }
    checks = {
        "mandatory_rests_on_the_later_edge": mandatory.get("outcome") == "placed"
        and _point(mandatory, "low") == {"y": 0, "border_height": 20}
        and _point(mandatory, "high") == {"y": 40, "border_height": 20}
        and _point(mandatory, "port") == {"y": 0, "border_height": 100}
        and _point(mandatory, "next") == {"y": 100, "border_height": 8}
        and _snap(mandatory) == {"x": 0, "y": 40, "inline": None, "block": "high"},
        "proximity_keeps_a_distant_offset": proximity.get("outcome") == "placed"
        and _point(proximity, "low") == {"y": 0, "border_height": 20}
        and _point(proximity, "next") == {"y": 100, "border_height": 8}
        and _snap(proximity) == {"x": 0, "y": 150, "inline": None, "block": None},
        "padding_insets_the_snapport": padded.get("outcome") == "placed"
        and _point(padded, "only") == {"y": 30, "border_height": 20}
        and _snap(padded) == {"x": 0, "y": 20, "inline": None, "block": "only"},
        "margin_outsets_the_area": margined.get("outcome") == "placed"
        and _point(margined, "only") == {"y": 30, "border_height": 20}
        and _snap(margined) == {"x": 0, "y": 15, "inline": None, "block": "only"},
        "an_untyped_port_records_no_snap": plain.get("outcome") == "placed"
        and "snap" not in (_box(plain, "port") or {})
        and _point(plain, "high") == {"y": 40, "border_height": 20},
        "unparsable_snap_is_invalid": broken.get("outcome") == "invalid"
        and broken.get("reason") == "scroll snap is invalid",
        "visible_overflow_is_rejected": visible.get("outcome") == "invalid"
        and visible.get("reason") == "scroll snap is unsupported",
        "vertical_writing_mode_is_rejected": vertical.get("outcome") == "invalid"
        and vertical.get("reason") == "scroll snap is unsupported",
    }
    observed["checks"] = checks
    return all(checks.values()), observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
