"""Sample a viewport scroll timeline as a block's used opacity.

A marginless 100px page in a 100px viewport stacks a 20px subject on a 200px
follower, so the root border box is 220px and the scroll range is 120px.
``scroll()`` maps that range through a 100ms linear opacity animation. Scroll
0, 60, and 120 use opacities 0, 0.5, and 1. The follower stays at y 20. A
10px follower does not overflow, so the subject keeps its declared opacity
0.4. A broken keyframe block, a float, an absolute box, and a vertical
writing mode are invalid.

Prints JSON with boolean passed and nonempty observed. Exit 0 either way.
"""

from __future__ import annotations

import json
import sys

_PAGE = '<div id="page"><div id="subject"></div><div id="next"></div></div>'
_RESET = "#page, #subject, #next { margin: 0px; }"
_BOXES = "#page { width: 100px; } #subject { width: 20px; height: 20px; } "
_TAIL = "#next { height: 200px; }"
_SHORT = "#next { height: 10px; }"
_FRAMES = "@keyframes fade { from { opacity: 0; } to { opacity: 1; } }"
_TIMELINE = (
    " animation-name: fade; animation-duration: 100ms;"
    " animation-timing-function: linear; animation-fill-mode: both;"
    " animation-timeline: scroll();"
)


def _box(boxes: object, ident: str) -> dict[str, object] | None:
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if isinstance(item, dict) and item.get("id") == ident:
            return item
    return None


def _near(value: object, expected: float) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return abs(float(value) - expected) < 1e-9


def _lay(layout, stylesheet: str, scroll_y: int) -> dict[str, object]:
    try:
        placed = layout(
            _PAGE,
            stylesheet,
            viewport_width=100,
            viewport_height=100,
            scroll_y=scroll_y,
        )
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def _sheet(extra: str, *, opacity: str, tail: str) -> str:
    return (
        _FRAMES
        + " "
        + _RESET
        + " "
        + _BOXES
        + tail
        + " #subject { opacity: "
        + opacity
        + ";"
        + _TIMELINE
        + extra
        + " }"
    )


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without the walk still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    start = _lay(layout_normal_flow, _sheet("", opacity="0", tail=_TAIL), 0)
    middle = _lay(layout_normal_flow, _sheet("", opacity="0", tail=_TAIL), 60)
    end = _lay(layout_normal_flow, _sheet("", opacity="0", tail=_TAIL), 120)
    idle = _lay(layout_normal_flow, _sheet("", opacity="0.4", tail=_SHORT), 0)
    broken = _lay(
        layout_normal_flow,
        "@keyframes fade { from { opacity: 0; } to { " + _RESET + " " + _BOXES + _TAIL + " #subject { opacity: 0;" + _TIMELINE + " }",
        0,
    )
    floated = _lay(layout_normal_flow, _sheet(" float: left;", opacity="0", tail=_TAIL), 0)
    absolute = _lay(
        layout_normal_flow,
        _sheet(" position: absolute; left: 0px; top: 0px;", opacity="0", tail=_TAIL),
        0,
    )
    vertical = _lay(layout_normal_flow, _sheet(" writing-mode: vertical-rl;", opacity="0", tail=_TAIL), 0)

    def opacity_of(placed: dict[str, object]) -> object:
        box = _box(placed.get("boxes"), "subject")
        if box is None:
            return None
        return box.get("opacity")

    def next_y(placed: dict[str, object]) -> object:
        box = _box(placed.get("boxes"), "next")
        if box is None:
            return None
        return box.get("y")

    def subject_edge(placed: dict[str, object]) -> dict[str, object] | None:
        box = _box(placed.get("boxes"), "subject")
        if box is None:
            return None
        return {"x": box.get("x"), "y": box.get("y"), "border_width": box.get("border_width"), "border_height": box.get("border_height")}

    parked = {"x": 0, "y": 0, "border_width": 20, "border_height": 20}
    observed = {
        "start_opacity": opacity_of(start),
        "middle_opacity": opacity_of(middle),
        "end_opacity": opacity_of(end),
        "start_edge": subject_edge(start),
        "middle_edge": subject_edge(middle),
        "end_edge": subject_edge(end),
        "start_next_y": next_y(start),
        "middle_next_y": next_y(middle),
        "end_next_y": next_y(end),
        "idle_opacity": opacity_of(idle),
        "idle_next_y": next_y(idle),
        "broken": broken.get("reason"),
        "float": floated.get("reason"),
        "absolute": absolute.get("reason"),
        "vertical": vertical.get("reason"),
    }
    checks = {
        "scroll_start_is_the_from_opacity": start.get("outcome") == "placed" and _near(observed["start_opacity"], 0),
        "scroll_middle_is_halfway": middle.get("outcome") == "placed" and _near(observed["middle_opacity"], 0.5),
        "scroll_end_holds_the_to_opacity": end.get("outcome") == "placed" and _near(observed["end_opacity"], 1),
        "scroll_does_not_move_the_subject": observed["start_edge"] == parked
        and observed["middle_edge"] == parked
        and observed["end_edge"] == parked,
        "follower_stays_under_the_static_stack": observed["start_next_y"] == 20
        and observed["middle_next_y"] == 20
        and observed["end_next_y"] == 20,
        "short_page_keeps_the_underlying_opacity": idle.get("outcome") == "placed"
        and _near(observed["idle_opacity"], 0.4)
        and observed["idle_next_y"] == 20,
        "broken_keyframes_are_rejected": broken.get("outcome") == "invalid"
        and broken.get("reason") == "scroll animation is invalid",
        "float_timeline_is_rejected": floated.get("outcome") == "invalid"
        and floated.get("reason") == "scroll timeline position is unsupported",
        "absolute_timeline_is_rejected": absolute.get("outcome") == "invalid"
        and absolute.get("reason") == "scroll timeline position is unsupported",
        "vertical_timeline_is_rejected": vertical.get("outcome") == "invalid"
        and vertical.get("reason") == "scroll timeline writing mode is unsupported",
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
