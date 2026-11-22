"""Pack a grid item inside its area from justify-items and align-items.

A definite item sits at the end or the center of a larger area. justify-self
and align-self override the container. An automatic item still stretches
unless the inline keyword is start, which keeps the max-content line.
space-between stays invalid on an item axis, and left stays invalid on the
block axis. The next sibling stays under the grid.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree that still rejects end or center exits 0.
"""

from __future__ import annotations

import json
import sys

_FONT = "#page { font-size: 10px; line-height: 10px; }\n"
_MARKUP = '<div id="page"><div id="grid"><div id="a">AB</div></div><div id="after"></div></div>'
_GRID = (
    "#grid { display: grid; width: 100px; height: 80px; "
    "grid-template-columns: 100px; grid-template-rows: 80px; "
)
_AFTER = "#after { height: 8px; }\n"
_DEFINITE = "#a { width: 20px; height: 10px; }\n"
_END = _FONT + _GRID + "justify-items: end; align-items: end; }\n" + _DEFINITE + _AFTER
_CENTER = _FONT + _GRID + "justify-items: center; align-items: center; }\n" + _DEFINITE + _AFTER
_SELF = (
    _FONT
    + _GRID
    + "justify-items: start; align-items: end; }\n"
    + "#a { width: 20px; height: 10px; justify-self: end; align-self: start; }\n"
    + _AFTER
)
_RIGHT = _FONT + _GRID + "justify-items: right; align-items: start; }\n" + _DEFINITE + _AFTER
_STRETCH = _FONT + _GRID + "}\n" + _AFTER
_START = _FONT + _GRID + "justify-items: start; }\n" + _AFTER
_DISTRIBUTED = _FONT + _GRID + "justify-items: space-between; }\n" + _DEFINITE + _AFTER
_BLOCK_LEFT = _FONT + _GRID + "align-items: left; }\n" + _DEFINITE + _AFTER


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


def _line(box: dict[str, object] | None) -> dict[str, object] | None:
    if box is None or not isinstance(box.get("lines"), list) or not box["lines"]:
        return None
    line = box["lines"][0]
    if not isinstance(line, dict):
        return None
    return {"text": line.get("text"), "x": line.get("x"), "y": line.get("y")}


def _lay(layout, stylesheet: str) -> dict[str, object]:
    try:
        placed = layout(_MARKUP, stylesheet, viewport_width=240)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def _view(result: dict[str, object], ident: str) -> dict[str, object] | None:
    box = _box(result.get("boxes"), ident)
    if box is None:
        return None
    return {
        "x": box.get("x"),
        "y": box.get("y"),
        "content_width": box.get("content_width"),
        "content_height": box.get("content_height"),
        "border_width": box.get("border_width"),
        "border_height": box.get("border_height"),
        "line": _line(box),
    }


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without placement still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    end = _lay(layout_normal_flow, _END)
    center = _lay(layout_normal_flow, _CENTER)
    self_aligned = _lay(layout_normal_flow, _SELF)
    right = _lay(layout_normal_flow, _RIGHT)
    stretch = _lay(layout_normal_flow, _STRETCH)
    start = _lay(layout_normal_flow, _START)
    distributed = _lay(layout_normal_flow, _DISTRIBUTED)
    block_left = _lay(layout_normal_flow, _BLOCK_LEFT)
    observed: dict[str, object] = {
        "end_outcome": end.get("outcome"),
        "end_reason": end.get("reason"),
        "end_grid": _view(end, "grid"),
        "end_a": _view(end, "a"),
        "end_after": _view(end, "after"),
        "center_outcome": center.get("outcome"),
        "center_a": _view(center, "a"),
        "center_after": _view(center, "after"),
        "self_outcome": self_aligned.get("outcome"),
        "self_reason": self_aligned.get("reason"),
        "self_a": _view(self_aligned, "a"),
        "right_outcome": right.get("outcome"),
        "right_a": _view(right, "a"),
        "stretch_outcome": stretch.get("outcome"),
        "stretch_a": _view(stretch, "a"),
        "stretch_after": _view(stretch, "after"),
        "start_outcome": start.get("outcome"),
        "start_a": _view(start, "a"),
        "start_after": _view(start, "after"),
        "distributed_outcome": distributed.get("outcome"),
        "distributed_reason": distributed.get("reason"),
        "block_left_outcome": block_left.get("outcome"),
        "block_left_reason": block_left.get("reason"),
    }
    checks = {
        "end_packs_the_definite_item_into_the_far_corner": (
            end.get("outcome") == "placed"
            and _near(_box(end.get("boxes"), "grid"), y=0, content_height=80, border_height=80)
            and _near(
                _box(end.get("boxes"), "a"),
                x=80,
                y=70,
                content_width=20,
                content_height=10,
                border_width=20,
                border_height=10,
            )
            and _near(_line(_box(end.get("boxes"), "a")), text="AB", x=80, y=70)
            and _near(_box(end.get("boxes"), "after"), y=80)
        ),
        "center_packs_the_definite_item_in_the_area": (
            center.get("outcome") == "placed"
            and _near(
                _box(center.get("boxes"), "a"),
                x=40,
                y=35,
                content_width=20,
                content_height=10,
            )
            and _near(_line(_box(center.get("boxes"), "a")), text="AB", x=40, y=35)
            and _near(_box(center.get("boxes"), "after"), y=80)
        ),
        "self_keywords_override_the_container": (
            self_aligned.get("outcome") == "placed"
            and _near(
                _box(self_aligned.get("boxes"), "a"),
                x=80,
                y=0,
                content_width=20,
                content_height=10,
            )
            and _near(_line(_box(self_aligned.get("boxes"), "a")), text="AB", x=80, y=0)
        ),
        "physical_right_uses_the_inline_end": (
            right.get("outcome") == "placed"
            and _near(_box(right.get("boxes"), "a"), x=80, y=0, content_width=20, content_height=10)
            and _near(_line(_box(right.get("boxes"), "a")), text="AB", x=80, y=0)
        ),
        "automatic_item_still_stretches": (
            stretch.get("outcome") == "placed"
            and _near(
                _box(stretch.get("boxes"), "a"),
                x=0,
                y=0,
                content_width=100,
                content_height=80,
            )
            and _near(_line(_box(stretch.get("boxes"), "a")), text="AB", x=0, y=0)
            and _near(_box(stretch.get("boxes"), "after"), y=80)
        ),
        "start_keeps_the_max_content_line": (
            start.get("outcome") == "placed"
            and _near(
                _box(start.get("boxes"), "a"),
                x=0,
                y=0,
                content_width=20,
                content_height=80,
            )
            and _near(_line(_box(start.get("boxes"), "a")), text="AB", x=0, y=0)
            and _near(_box(start.get("boxes"), "after"), y=80)
        ),
        "item_axis_rejects_distribution": (
            distributed.get("outcome") == "invalid"
            and distributed.get("boxes") is None
            and distributed.get("reason") == "justify-items is invalid"
        ),
        "block_axis_rejects_left": (
            block_left.get("outcome") == "invalid"
            and block_left.get("boxes") is None
            and block_left.get("reason") == "align-items is invalid"
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
