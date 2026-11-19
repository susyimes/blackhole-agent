"""Hit-test one physical point against CSS border boxes.

The search walks ``paint_order`` from front to back, so stacking is CSS 2.2
Appendix E rather than a second copy of it. A negative stack level that
escapes to an ancestor is painted before an in-flow parent, and that parent
is the target on the overlap. The same child is painted after a parent that
forms its own stacking context, and then the child is the target.

Coordinates are physical pixels of the border box, not offsets from the
parent. The box is half-open: it contains the top and left edges and excludes
the right and bottom edges. ``pointer-events`` and ``visibility`` inherit.
``none`` and ``hidden`` are not targets. A descendant that specifies ``auto``
or ``visible`` still is. Opacity zero does not remove a target.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from blackhole_agent.css_paint_order import paint_order

_POSITIONS = frozenset({"static", "relative", "absolute", "fixed", "sticky"})
_FLOATS = frozenset({"none", "left", "right"})
_DISPLAYS = frozenset({"block", "inline", "inline-block"})
_POINTER = frozenset({"auto", "none"})
_VISIBILITY = frozenset({"visible", "hidden"})
_FIELDS = frozenset(
    {
        "id",
        "position",
        "z_index",
        "opacity",
        "float",
        "display",
        "children",
        "x",
        "y",
        "width",
        "height",
        "pointer_events",
        "visibility",
    }
)


class _Invalid(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass
class _Box:
    id: str
    position: str
    z_index: int | None
    opacity: float
    float: str
    display: str
    x: float
    y: float
    width: float
    height: float
    pointer_events: str
    visibility: str
    children: list[_Box] = field(default_factory=list)


def element_from_point(tree: object, x: object, y: object) -> dict[str, object]:
    """Return the frontmost target whose border box contains ``(x, y)``.

    ``outcome`` is ``hit``, ``miss``, or ``invalid``. ``id`` is the element
    on a hit and ``None`` otherwise. An invalid tree or point also carries
    ``reason``.
    """

    try:
        point_x = _finite(x)
        point_y = _finite(y)
        boxes: dict[str, _Box] = {}
        root = _parse(tree, seen=set(), boxes=boxes, pointer="auto", visibility="visible")
    except _Invalid as exc:
        return {"outcome": "invalid", "id": None, "reason": exc.reason}
    painted = paint_order(_paint_node(root))
    order = painted.get("order")
    if painted.get("outcome") != "ordered" or not isinstance(order, list):
        return {"outcome": "invalid", "id": None, "reason": str(painted.get("reason") or "paint")}
    for ident in reversed(order):
        if not isinstance(ident, str):
            return {"outcome": "invalid", "id": None, "reason": "paint"}
        box = boxes.get(ident)
        if box is None:
            return {"outcome": "invalid", "id": None, "reason": "paint"}
        if box.pointer_events != "auto" or box.visibility != "visible":
            continue
        if box.x <= point_x < box.x + box.width and box.y <= point_y < box.y + box.height:
            return {"outcome": "hit", "id": ident}
    return {"outcome": "miss", "id": None}


def _paint_node(box: _Box) -> dict[str, object]:
    return {
        "id": box.id,
        "position": box.position,
        "z_index": "auto" if box.z_index is None else box.z_index,
        "opacity": box.opacity,
        "float": box.float,
        "display": box.display,
        "children": [_paint_node(child) for child in box.children],
    }


def _parse(
    value: object,
    *,
    seen: set[str],
    boxes: dict[str, _Box],
    pointer: str,
    visibility: str,
) -> _Box:
    if not isinstance(value, dict):
        raise _Invalid("box")
    unknown = set(value) - _FIELDS
    if unknown:
        raise _Invalid("field")
    raw_id = value.get("id")
    if not isinstance(raw_id, str) or raw_id == "":
        raise _Invalid("id")
    if raw_id in seen:
        raise _Invalid("duplicate")
    seen.add(raw_id)
    position = value.get("position", "static")
    if position not in _POSITIONS:
        raise _Invalid("position")
    z_index = _z_index(value.get("z_index", "auto"))
    opacity = _opacity(value.get("opacity", 1))
    floated = value.get("float", "none")
    if floated not in _FLOATS:
        raise _Invalid("float")
    display = value.get("display", "block")
    if display not in _DISPLAYS:
        raise _Invalid("display")
    if not {"x", "y", "width", "height"} <= set(value):
        raise _Invalid("geometry")
    x = _finite(value["x"])
    y = _finite(value["y"])
    width = _finite(value["width"])
    height = _finite(value["height"])
    if width < 0 or height < 0:
        raise _Invalid("size")
    if "pointer_events" in value:
        chosen = value["pointer_events"]
        if chosen not in _POINTER:
            raise _Invalid("pointer-events")
        pointer = str(chosen)
    if "visibility" in value:
        chosen_visibility = value["visibility"]
        if chosen_visibility not in _VISIBILITY:
            raise _Invalid("visibility")
        visibility = str(chosen_visibility)
    children = value.get("children", [])
    if not isinstance(children, list):
        raise _Invalid("children")
    box = _Box(
        id=raw_id,
        position=str(position),
        z_index=z_index,
        opacity=opacity,
        float=str(floated),
        display=str(display),
        x=x,
        y=y,
        width=width,
        height=height,
        pointer_events=pointer,
        visibility=visibility,
    )
    boxes[raw_id] = box
    box.children = [
        _parse(child, seen=seen, boxes=boxes, pointer=pointer, visibility=visibility) for child in children
    ]
    return box


def _z_index(value: object) -> int | None:
    if value == "auto":
        return None
    if type(value) is int:
        return value
    raise _Invalid("z-index")


def _opacity(value: object) -> float:
    if type(value) not in (int, float):
        raise _Invalid("opacity")
    number = float(value)
    if not math.isfinite(number) or not 0.0 <= number <= 1.0:
        raise _Invalid("opacity")
    return number


def _finite(value: object) -> float:
    if type(value) not in (int, float):
        raise _Invalid("number")
    number = float(value)
    if not math.isfinite(number):
        raise _Invalid("number")
    return number
