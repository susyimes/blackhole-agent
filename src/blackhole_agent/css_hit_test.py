"""Hit-test one physical point against CSS border boxes.

The search walks ``paint_order`` from front to back, so stacking is CSS 2.2
Appendix E rather than a second copy of it. A negative stack level that
escapes to an ancestor is painted before an in-flow parent, and that parent
is the target on the overlap. The same child is painted after a parent that
forms its own stacking context, and then the child is the target.

Layout ``x`` and ``y`` are the border-box top left before transforms, in one
shared coordinate space. A CSS 2D transform moves the hit region. The point
passes through the inverse of each ancestor transform and then the element's
own transform. The half-open test then runs in that local box: it contains
the top and left edges and excludes the right and bottom edges. ``none``
leaves the axis-aligned rectangle. Any other transform also makes the element
a stacking context, so a negative-z child stays inside it. A singular matrix
hits nothing. An invalid transform rejects the tree.

``pointer-events`` and ``visibility`` inherit.
``none`` and ``hidden`` are not targets. A descendant that specifies ``auto``
or ``visible`` still is. Opacity zero does not remove a target.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from blackhole_agent.css_paint_order import paint_order
from blackhole_agent.css_transform import map_transformed_point

_IDENTITY = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
_DET = 1e-12
_SNAP = 1e-6

_POSITIONS = frozenset({"static", "relative", "absolute", "fixed", "sticky"})
_FLOATS = frozenset({"none", "left", "right"})
_DISPLAYS = frozenset(
    {
        "block",
        "inline",
        "inline-block",
        "inline-flex",
        "flex",
        "grid",
        "table",
        "table-row",
        "table-cell",
    }
)
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
        "transform",
        "origin",
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
    matrix: tuple[float, float, float, float, float, float]
    stacking: bool
    transform: str | None = None
    parent: _Box | None = None
    children: list[_Box] = field(default_factory=list)


def element_from_point(tree: object, x: object, y: object) -> dict[str, object]:
    """Return the frontmost target whose transformed border box contains ``(x, y)``.

    ``outcome`` is ``hit``, ``miss``, or ``invalid``. ``id`` is the element
    on a hit and ``None`` otherwise. An invalid tree or point also carries
    ``reason``. Layout coordinates stay untransformed; the test uses the
    inverse CSS 2D matrix, including ancestor transforms.
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
        local = _local_point(box, point_x, point_y)
        if local is not None and _covers(local[0], local[1], box.width, box.height):
            return {"outcome": "hit", "id": ident}
    return {"outcome": "miss", "id": None}


def _paint_node(box: _Box) -> dict[str, object]:
    node = {
        "id": box.id,
        "position": box.position,
        "z_index": "auto" if box.z_index is None else box.z_index,
        "opacity": box.opacity,
        "float": box.float,
        "display": box.display,
        "children": [_paint_node(child) for child in box.children],
    }
    if box.stacking and box.transform is not None:
        node["transform"] = box.transform
    return node


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
    matrix, stacking, transform = _matrix(value, width, height)
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
        matrix=matrix,
        stacking=stacking,
        transform=transform,
    )
    boxes[raw_id] = box
    box.children = []
    for child in children:
        parsed = _parse(child, seen=seen, boxes=boxes, pointer=pointer, visibility=visibility)
        parsed.parent = box
        box.children.append(parsed)
    return box


def _matrix(
    value: dict[str, object], width: float, height: float
) -> tuple[tuple[float, float, float, float, float, float], bool, str | None]:
    if "origin" in value and not isinstance(value["origin"], str):
        raise _Invalid("origin")
    if "transform" not in value:
        return _IDENTITY, False, None
    raw = value["transform"]
    if not isinstance(raw, str):
        raise _Invalid("transform")
    if _transform_none(raw):
        return _IDENTITY, False, None
    layer: dict[str, object] = {
        "x": 0,
        "y": 0,
        "width": width,
        "height": height,
        "transform": raw,
        "origin": value.get("origin", "50% 50%"),
    }
    result = map_transformed_point(layer, {"x": 0, "y": 0})
    if result.get("outcome") != "mapped" or not isinstance(result.get("matrix"), list):
        raise _Invalid(str(result.get("reason") or "transform"))
    numbers = result["matrix"]
    if len(numbers) != 6 or any(type(item) not in (int, float) for item in numbers):
        raise _Invalid("transform")
    return tuple(float(item) for item in numbers), True, raw


def _transform_none(value: str) -> bool:
    pieces: list[str] = []
    index = 0
    while index < len(value):
        if value.startswith("/*", index):
            end = value.find("*/", index + 2)
            if end < 0:
                return False
            pieces.append(" ")
            index = end + 2
            continue
        pieces.append(value[index])
        index += 1
    return "".join(pieces).strip().lower() == "none"


def _local_point(box: _Box, x: float, y: float) -> tuple[float, float] | None:
    chain: list[_Box] = []
    current: _Box | None = box
    while current is not None:
        chain.append(current)
        current = current.parent
    for item in reversed(chain):
        local = _inverse(item.matrix, x - item.x, y - item.y)
        if local is None:
            return None
        if item is box:
            return local
        x = item.x + local[0]
        y = item.y + local[1]
    return None


def _inverse(
    matrix: tuple[float, float, float, float, float, float], x: float, y: float
) -> tuple[float, float] | None:
    a, b, c, d, e, f = matrix
    det = a * d - c * b
    if not math.isfinite(det) or abs(det) <= _DET:
        return None
    x -= e
    y -= f
    local_x = (d * x - c * y) / det
    local_y = (a * y - b * x) / det
    if not math.isfinite(local_x) or not math.isfinite(local_y):
        return None
    return local_x, local_y


def _covers(x: float, y: float, width: float, height: float) -> bool:
    return 0.0 <= _snap(x) < width and 0.0 <= _snap(y) < height


def _snap(value: float) -> float:
    nearest = round(value)
    if abs(value - nearest) <= _SNAP:
        return float(nearest)
    return value


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
