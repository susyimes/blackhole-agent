"""Slide an in-flow box along an offset path inside its containing block.

A 20px pad puts the mover's static border box at y 20. ``path("M 30 10 L 70 10")``
is measured from the page border box, so distance 0px parks a top-left anchor
at (30, 10) and distance 40px parks it at (70, 10) even when relative insets
would have left it elsewhere. ``offset-anchor: auto`` uses the border-box
center, so distance 0px parks the origin at (20, 0). A circle's 0% point is
its rightmost point. The following block stays at y 40, and the inner child
moves with the mover. An unparsable path, a float, an absolute box, and a
vertical writing mode stay invalid.

Prints JSON with boolean passed and nonempty observed. Exit 0 either way.
"""

from __future__ import annotations

import json
import sys

_PAGE = (
    '<div id="page"><div id="pad"></div><div id="mover"><div id="inner"></div></div>'
    '<div id="next"></div></div>'
)
_RESET = "#page, #pad, #mover, #inner, #next { margin: 0px; }"
_BASE = (
    "#page { width: 200px; } #pad { height: 20px; } "
    "#mover { width: 20px; height: 20px; } #inner { width: 10px; height: 10px; } "
    "#next { height: 10px; }"
)
_LINE = ' path("M 30 10 L 70 10")'
_ANCHOR = " offset-rotate: 0deg; offset-anchor: 0px 0px; "


def _box(boxes: object, ident: str) -> dict[str, object] | None:
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
        "offset_angle": box.get("offset_angle"),
    }


def _lay(layout, stylesheet: str) -> dict[str, object]:
    try:
        placed = layout(_PAGE, stylesheet, viewport_width=200)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without the walk still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    end = _lay(
        layout_normal_flow,
        _RESET
        + _BASE
        + "#mover { position: relative; left: 15px; top: 4px; offset-path:"
        + _LINE
        + "; offset-distance: 40px;"
        + _ANCHOR
        + "}",
    )
    start = _lay(
        layout_normal_flow,
        _RESET + _BASE + "#mover { offset-path:" + _LINE + "; offset-distance: 0px;" + _ANCHOR + "}",
    )
    center = _lay(
        layout_normal_flow,
        _RESET
        + _BASE
        + "#mover { offset-path:"
        + _LINE
        + "; offset-distance: 0px; offset-rotate: 0deg; }",
    )
    circle = _lay(
        layout_normal_flow,
        _RESET
        + _BASE
        + "#mover { offset-path: circle(40px at 100px 40px); offset-distance: 0%;"
        + _ANCHOR
        + "}",
    )
    broken = _lay(
        layout_normal_flow,
        _RESET + _BASE + "#mover { offset-path: not-a-path; offset-distance: 0px; }",
    )
    floated = _lay(
        layout_normal_flow,
        _RESET + _BASE + "#mover { float: left; offset-path:" + _LINE + "; offset-distance: 0px;" + _ANCHOR + "}",
    )
    absolute = _lay(
        layout_normal_flow,
        _RESET
        + _BASE
        + "#mover { position: absolute; left: 0px; top: 0px; offset-path:"
        + _LINE
        + "; offset-distance: 0px;"
        + _ANCHOR
        + "}",
    )
    vertical = _lay(
        layout_normal_flow,
        _RESET
        + _BASE
        + "#mover { writing-mode: vertical-rl; offset-path:"
        + _LINE
        + "; offset-distance: 0px;"
        + _ANCHOR
        + "}",
    )

    def at(placed: dict[str, object], ident: str) -> dict[str, object] | None:
        return _edge(_box(placed.get("boxes"), ident))

    parked = {"x": 70, "y": 10, "border_width": 20, "border_height": 20, "offset_angle": 0}
    opened = {"x": 30, "y": 10, "border_width": 20, "border_height": 20, "offset_angle": 0}
    centered = {"x": 20, "y": 0, "border_width": 20, "border_height": 20, "offset_angle": 0}
    orbited = {"x": 140, "y": 40, "border_width": 20, "border_height": 20, "offset_angle": 0}
    observed = {
        "end": at(end, "mover"),
        "end_inner": at(end, "inner"),
        "end_next_y": None if _box(end.get("boxes"), "next") is None else _box(end.get("boxes"), "next").get("y"),
        "end_pad": at(end, "pad"),
        "start": at(start, "mover"),
        "start_next_y": None if _box(start.get("boxes"), "next") is None else _box(start.get("boxes"), "next").get("y"),
        "center": at(center, "mover"),
        "circle": at(circle, "mover"),
        "circle_next_y": None if _box(circle.get("boxes"), "next") is None else _box(circle.get("boxes"), "next").get("y"),
        "broken": broken.get("reason"),
        "float": floated.get("reason"),
        "absolute": absolute.get("reason"),
        "vertical": vertical.get("reason"),
    }
    checks = {
        "distance_meets_the_path_end": end.get("outcome") == "placed" and observed["end"] == parked,
        "relative_insets_do_not_add_to_the_path_point": observed["end"] == parked,
        "child_moves_with_the_box": observed["end_inner"]
        == {"x": 70, "y": 10, "border_width": 10, "border_height": 10, "offset_angle": None},
        "following_block_stays_under_the_static_stack": observed["end_next_y"] == 40,
        "containing_block_stays_put": observed["end_pad"]
        == {"x": 0, "y": 0, "border_width": 200, "border_height": 20, "offset_angle": None},
        "zero_distance_uses_the_path_start": start.get("outcome") == "placed" and observed["start"] == opened,
        "zero_distance_leaves_the_next_block": observed["start_next_y"] == 40,
        "auto_anchor_is_the_border_center": center.get("outcome") == "placed" and observed["center"] == centered,
        "circle_start_is_the_rightmost_point": circle.get("outcome") == "placed" and observed["circle"] == orbited,
        "circle_leaves_the_next_block": observed["circle_next_y"] == 40,
        "unparsable_path_is_rejected": broken.get("outcome") == "invalid"
        and broken.get("reason") == "offset path is invalid",
        "float_path_is_rejected": floated.get("outcome") == "invalid"
        and floated.get("reason") == "offset path position is unsupported",
        "absolute_path_is_rejected": absolute.get("outcome") == "invalid"
        and absolute.get("reason") == "offset path position is unsupported",
        "vertical_path_is_rejected": vertical.get("outcome") == "invalid"
        and vertical.get("reason") == "offset path writing mode is unsupported",
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
