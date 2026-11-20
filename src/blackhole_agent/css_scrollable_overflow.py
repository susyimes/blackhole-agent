"""Scrollable overflow rectangle of one CSS box.

CSS Overflow 3 §2.2 and §3.3. The rectangle is the union of the padding box,
the static-position margin edges of in-flow content plus the box's own end
padding, and the reachable border boxes of boxes it contains. A relative
offset or a 2D transform moves only the border box. A border box that lands
wholly before the scroll origin, and any border box with zero area, does not
enlarge the rectangle. Outline and box-shadow are ink and are ignored.

A child's scrollable overflow joins its parent after that child clips to its
padding edge on every axis whose overflow is not visible. Adjoining margins
on the scroll container's block axis collapse: the used end margin is the
largest positive margin plus the most negative margin, so two positive
margins do not add. Flex, grid, and float placement are rejected.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from blackhole_agent.css_transform import map_transformed_point
from blackhole_agent.css_writing_mode import resolve_writing_mode

_EPS = 1e-9
_OVERFLOW = frozenset({"visible", "hidden", "scroll", "auto", "clip"})
_POSITIONS = frozenset({"static", "relative", "absolute"})
_DISPLAYS = frozenset({"block", "inline-block"})
_SIDES = ("top", "right", "bottom", "left")
_FIELDS = frozenset(
    {
        "id",
        "writing_mode",
        "direction",
        "width",
        "height",
        "padding",
        "padding_top",
        "padding_right",
        "padding_bottom",
        "padding_left",
        "border",
        "border_top",
        "border_right",
        "border_bottom",
        "border_left",
        "margin",
        "margin_top",
        "margin_right",
        "margin_bottom",
        "margin_left",
        "overflow",
        "overflow_x",
        "overflow_y",
        "position",
        "display",
        "top",
        "right",
        "bottom",
        "left",
        "transform",
        "outline",
        "box_shadow",
        "children",
        "float",
    }
)


class _Invalid(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class _Flow:
    block_start: str
    block_end: str
    inline_start: str
    inline_end: str
    block_axis: str
    inline_axis: str


@dataclass(frozen=True)
class _Rect:
    left: float
    top: float
    right: float
    bottom: float

    def width(self) -> float:
        return self.right - self.left

    def height(self) -> float:
        return self.bottom - self.top

    def live(self) -> bool:
        return self.width() > _EPS and self.height() > _EPS


@dataclass(frozen=True)
class _Span:
    border: float
    margin_start: float
    margin_end: float


@dataclass(frozen=True)
class _Node:
    content_width: float | None
    content_height: float | None
    padding: dict[str, float]
    border: dict[str, float]
    margin: dict[str, float]
    overflow_x: str
    overflow_y: str
    position: str
    display: str
    inset: dict[str, float | None]
    transform: str | None
    children: tuple[_Node, ...]
    writing_mode: str
    direction: str


@dataclass(frozen=True)
class _Placed:
    node: _Node
    static_margin: _Rect
    shifted_border: _Rect
    border_size: tuple[float, float]


def scrollable_overflow(box: object) -> dict[str, object]:
    """Return the scrollable overflow rectangle in border-box coordinates.

    ``width`` and ``height`` are content-box sizes. Omit either one to size
    it from in-flow children. ``padding: 10px 5px`` follows the CSS
    shorthand. The rectangle's origin is the border-box top left, so a
    vertical-rl container can report a negative ``left``.
    """

    try:
        rect = _scroll_rect(_parse(box, seen=set()))
    except _Invalid as exc:
        return _invalid(exc.reason)
    return {
        "outcome": "ok",
        "scroll_width": _number(rect.width()),
        "scroll_height": _number(rect.height()),
        "left": _number(rect.left),
        "top": _number(rect.top),
        "right": _number(rect.right),
        "bottom": _number(rect.bottom),
        "reason": None,
    }


def _scroll_rect(node: _Node) -> _Rect:
    node = _concrete(node)
    flow = _flow(node.writing_mode, node.direction)
    width = _border_length(node, "width")
    height = _border_length(node, "height")
    padding = _box_rect(node, width, height, "padding")
    scroll = padding
    placed = _layout(node, flow, width, height)
    for item in placed:
        if item.node.position == "absolute":
            continue
        scroll = _expand_end(scroll, flow.inline_end, _coord(item.static_margin, flow.inline_end), node.padding[flow.inline_end])
        scroll = _expand_end(scroll, flow.block_end, _coord(item.static_margin, flow.block_end), node.padding[flow.block_end])
    for item in placed:
        border = _project_local(
            _Rect(0.0, 0.0, item.border_size[0], item.border_size[1]),
            item.shifted_border.left,
            item.shifted_border.top,
            item.border_size[0],
            item.border_size[1],
            item.node.transform,
        )
        scroll = _union_reachable(scroll, border, padding, flow)
        local = _child_scroll(item)
        if local is None:
            continue
        projected = _project_local(
            local,
            item.shifted_border.left,
            item.shifted_border.top,
            item.border_size[0],
            item.border_size[1],
            item.node.transform,
        )
        scroll = _union_reachable(scroll, projected, padding, flow)
    return scroll


def _child_scroll(item: _Placed) -> _Rect | None:
    local = _scroll_rect(item.node)
    if not local.live():
        return None
    local = _clip_overflow(_concrete(item.node), local)
    if not local.live():
        return None
    return local


def _concrete(node: _Node) -> _Node:
    flow = _flow(node.writing_mode, node.direction)
    width = node.content_width
    height = node.content_height
    if width is None:
        width = _used_content(node, flow, "width")
    if height is None:
        height = _used_content(node, flow, "height")
    if width < -_EPS or height < -_EPS:
        raise _Invalid("size")
    return replace(node, content_width=width, content_height=height)


def _used_content(node: _Node, flow: _Flow, axis: str) -> float:
    logical = "block" if flow.block_axis == axis else "inline"
    span = _span(node, flow, logical)
    start, end = _logical_sides(flow, logical)
    return span.border - _chrome(node, start, end)


def _layout(node: _Node, flow: _Flow, width: float, height: float) -> list[_Placed]:
    padding = _box_rect(node, width, height, "padding")
    content = _box_rect(node, width, height, "content")
    cursor = _coord(content, flow.block_start)
    inline_origin = _coord(content, flow.inline_start)
    placed: list[_Placed] = []
    for child in node.children:
        if child.position == "absolute":
            placed.append(_place_absolute(child, padding))
            continue
        block = _span(child, flow, "block")
        inline = _span(child, flow, "inline")
        border_block_start = _move(cursor, flow.block_end, block.margin_start)
        border_block_end = _move(border_block_start, flow.block_end, block.border)
        margin_block_end = _move(border_block_end, flow.block_end, block.margin_end)
        border_inline_start = _move(inline_origin, flow.inline_end, inline.margin_start)
        border_inline_end = _move(border_inline_start, flow.inline_end, inline.border)
        margin_inline_start = inline_origin
        margin_inline_end = _move(border_inline_end, flow.inline_end, inline.margin_end)
        border = _from_sides(
            {
                flow.block_start: border_block_start,
                flow.block_end: border_block_end,
                flow.inline_start: border_inline_start,
                flow.inline_end: border_inline_end,
            }
        )
        margin = _from_sides(
            {
                flow.block_start: cursor,
                flow.block_end: margin_block_end,
                flow.inline_start: margin_inline_start,
                flow.inline_end: margin_inline_end,
            }
        )
        shifted = _shift(border, child)
        placed.append(_Placed(child, margin, shifted, (border.width(), border.height())))
        cursor = margin_block_end
    return placed


def _place_absolute(child: _Node, padding: _Rect) -> _Placed:
    if child.inset["left"] is None or child.inset["top"] is None:
        raise _Invalid("absolute")
    if child.content_width is None or child.content_height is None:
        raise _Invalid("absolute")
    width = _border_length(child, "width")
    height = _border_length(child, "height")
    left = padding.left + child.inset["left"] + child.margin["left"]
    top = padding.top + child.inset["top"] + child.margin["top"]
    border = _Rect(left, top, left + width, top + height)
    return _Placed(child, border, _shift(border, child), (width, height))


def _span(node: _Node, flow: _Flow, logical: str) -> _Span:
    start, end = _logical_sides(flow, logical)
    axis = flow.block_axis if logical == "block" else flow.inline_axis
    content = node.content_width if axis == "width" else node.content_height
    chrome = _chrome(node, start, end)
    own_start = node.margin[start]
    own_end = node.margin[end]
    kids = _in_flow(node)
    if content is not None:
        return _Span(content + chrome, own_start, own_end)
    if logical == "inline" or not kids:
        grown = _shrink(kids, flow) if logical == "inline" else 0.0
        return _Span(grown + chrome, own_start, own_end)
    spans = [_span(child, flow, "block") for child in kids]
    absorb_start = _absorb(node, start)
    absorb_end = _absorb(node, end)
    content_extent = spans[0].border
    previous = spans[0].margin_end
    for span in spans[1:]:
        content_extent += _collapse(previous, span.margin_start) + span.border
        previous = span.margin_end
    if absorb_start:
        margin_start = _collapse(own_start, spans[0].margin_start)
    else:
        margin_start = own_start
        content_extent += spans[0].margin_start
    if absorb_end:
        margin_end = _collapse(own_end, previous)
    else:
        margin_end = own_end
        content_extent += previous
    return _Span(content_extent + chrome, margin_start, margin_end)


def _shrink(kids: tuple[_Node, ...] | list[_Node], flow: _Flow) -> float:
    if not kids:
        return 0.0
    return max(_span(child, flow, "inline").border + _outer_margin(child, flow) for child in kids)


def _outer_margin(child: _Node, flow: _Flow) -> float:
    return child.margin[flow.inline_start] + child.margin[flow.inline_end]


def _absorb(node: _Node, side: str) -> bool:
    return (
        node.display == "block"
        and node.position in {"static", "relative"}
        and node.overflow_x == "visible"
        and node.overflow_y == "visible"
        and node.padding[side] == 0.0
        and node.border[side] == 0.0
    )


def _collapse(*parts: float) -> float:
    positive = [part for part in parts if part > 0.0]
    negative = [part for part in parts if part < 0.0]
    high = max(positive) if positive else 0.0
    low = min(negative) if negative else 0.0
    return high + low


def _clip_overflow(node: _Node, rect: _Rect) -> _Rect:
    if node.content_width is None or node.content_height is None:
        raise _Invalid("size")
    pad = _box_rect(node, _border_length(node, "width"), _border_length(node, "height"), "padding")
    left, right = rect.left, rect.right
    top, bottom = rect.top, rect.bottom
    if node.overflow_x != "visible":
        left = max(left, pad.left)
        right = min(right, pad.right)
    if node.overflow_y != "visible":
        top = max(top, pad.top)
        bottom = min(bottom, pad.bottom)
    return _Rect(left, top, right, bottom)


def _union_reachable(scroll: _Rect, rect: _Rect, padding: _Rect, flow: _Flow) -> _Rect:
    clipped = _clip_reachable(rect, padding, flow)
    if clipped is None:
        return scroll
    scroll = _expand_end(scroll, flow.inline_end, _coord(clipped, flow.inline_end), 0.0)
    return _expand_end(scroll, flow.block_end, _coord(clipped, flow.block_end), 0.0)


def _clip_reachable(rect: _Rect, padding: _Rect, flow: _Flow) -> _Rect | None:
    if not rect.live():
        return None
    edges = {"left": rect.left, "right": rect.right, "top": rect.top, "bottom": rect.bottom}
    for start, end in ((flow.inline_start, flow.inline_end), (flow.block_start, flow.block_end)):
        origin = _coord(padding, start)
        if end in {"right", "bottom"}:
            edges[start] = max(edges[start], origin)
        else:
            edges[start] = min(edges[start], origin)
    clipped = _from_sides(edges)
    if not clipped.live():
        return None
    return clipped


def _expand_end(rect: _Rect, end: str, edge: float, padding: float) -> _Rect:
    if end == "right":
        return replace(rect, right=max(rect.right, edge + padding))
    if end == "bottom":
        return replace(rect, bottom=max(rect.bottom, edge + padding))
    if end == "left":
        return replace(rect, left=min(rect.left, edge - padding))
    return replace(rect, top=min(rect.top, edge - padding))


def _project_local(
    local: _Rect,
    origin_x: float,
    origin_y: float,
    box_width: float,
    box_height: float,
    transform: str | None,
) -> _Rect:
    if transform is None:
        return _Rect(local.left + origin_x, local.top + origin_y, local.right + origin_x, local.bottom + origin_y)
    if box_width <= _EPS or box_height <= _EPS:
        raise _Invalid("transform")
    xs: list[float] = []
    ys: list[float] = []
    for point_x, point_y in (
        (local.left, local.top),
        (local.right, local.top),
        (local.left, local.bottom),
        (local.right, local.bottom),
    ):
        mapped = map_transformed_point(
            {
                "x": origin_x,
                "y": origin_y,
                "width": box_width,
                "height": box_height,
                "transform": transform,
            },
            {"x": point_x, "y": point_y},
        )
        if mapped.get("outcome") != "mapped":
            raise _Invalid(str(mapped.get("reason") or "transform"))
        xs.append(float(mapped["x"]))
        ys.append(float(mapped["y"]))
    return _Rect(min(xs), min(ys), max(xs), max(ys))


def _shift(rect: _Rect, node: _Node) -> _Rect:
    if node.position != "relative":
        return rect
    left, right = node.inset["left"], node.inset["right"]
    top, bottom = node.inset["top"], node.inset["bottom"]
    dx = 0.0
    dy = 0.0
    if left is not None and right is not None:
        if node.direction == "rtl":
            left = None
        else:
            right = None
    if left is not None:
        dx = left
    elif right is not None:
        dx = -right
    if top is not None and bottom is not None:
        bottom = None
    if top is not None:
        dy = top
    elif bottom is not None:
        dy = -bottom
    return _Rect(rect.left + dx, rect.top + dy, rect.right + dx, rect.bottom + dy)


def _box_rect(node: _Node, width: float, height: float, kind: str) -> _Rect:
    if kind == "padding":
        return _Rect(
            node.border["left"],
            node.border["top"],
            width - node.border["right"],
            height - node.border["bottom"],
        )
    if kind == "content":
        return _Rect(
            node.border["left"] + node.padding["left"],
            node.border["top"] + node.padding["top"],
            width - node.border["right"] - node.padding["right"],
            height - node.border["bottom"] - node.padding["bottom"],
        )
    raise _Invalid("box")


def _border_length(node: _Node, axis: str) -> float:
    if axis == "width":
        content = node.content_width
        start, end = "left", "right"
    else:
        content = node.content_height
        start, end = "top", "bottom"
    if content is None:
        raise _Invalid("size")
    return content + _chrome(node, start, end)


def _chrome(node: _Node, start: str, end: str) -> float:
    return node.padding[start] + node.padding[end] + node.border[start] + node.border[end]


def _logical_sides(flow: _Flow, logical: str) -> tuple[str, str]:
    if logical == "block":
        return flow.block_start, flow.block_end
    return flow.inline_start, flow.inline_end


def _coord(rect: _Rect, side: str) -> float:
    return {"left": rect.left, "right": rect.right, "top": rect.top, "bottom": rect.bottom}[side]


def _from_sides(edges: dict[str, float]) -> _Rect:
    return _Rect(edges["left"], edges["top"], edges["right"], edges["bottom"])


def _move(coord: float, toward: str, distance: float) -> float:
    if toward in {"right", "bottom"}:
        return coord + distance
    return coord - distance


def _in_flow(node: _Node) -> list[_Node]:
    return [child for child in node.children if child.position != "absolute"]


def _flow(writing_mode: str, direction: str) -> _Flow:
    resolved = resolve_writing_mode(writing_mode, direction)
    if resolved.get("outcome") != "resolved":
        raise _Invalid(str(resolved.get("reason") or "writing-mode"))
    return _Flow(
        block_start=str(resolved["block_start"]),
        block_end=str(resolved["block_end"]),
        inline_start=str(resolved["inline_start"]),
        inline_end=str(resolved["inline_end"]),
        block_axis=str(resolved["block_size_axis"]),
        inline_axis=str(resolved["inline_size_axis"]),
    )


def _parse(value: object, seen: set[str]) -> _Node:
    if not isinstance(value, dict):
        raise _Invalid("box")
    if set(value) - _FIELDS:
        raise _Invalid("field")
    if value.get("float") not in (None, "none"):
        raise _Invalid("float")
    ident = value.get("id")
    if ident is not None:
        if not isinstance(ident, str) or ident == "" or ident in seen:
            raise _Invalid("id")
        seen.add(ident)
    writing_mode = _keyword(value.get("writing_mode", "horizontal-tb"), "writing-mode")
    direction = _keyword(value.get("direction", "ltr"), "direction")
    padding = _edges(value, "padding", nonnegative=True)
    border = _edges(value, "border", nonnegative=True)
    margin = _edges(value, "margin", nonnegative=False)
    overflow_x, overflow_y = _overflow(value)
    position = _choice(value.get("position", "static"), _POSITIONS, "position")
    display = _choice(value.get("display", "block"), _DISPLAYS, "display")
    children = value.get("children", [])
    if not isinstance(children, list):
        raise _Invalid("children")
    return _Node(
        content_width=_size(value.get("width", None), "width"),
        content_height=_size(value.get("height", None), "height"),
        padding=padding,
        border=border,
        margin=margin,
        overflow_x=overflow_x,
        overflow_y=overflow_y,
        position=position,
        display=display,
        inset={side: _inset(value.get(side, None), side) for side in _SIDES},
        transform=_transform(value.get("transform", None)),
        children=tuple(_parse(child, seen) for child in children),
        writing_mode=writing_mode,
        direction=direction,
    )


def _edges(value: dict[str, object], name: str, *, nonnegative: bool) -> dict[str, float]:
    longhands = [f"{name}_{side}" for side in _SIDES]
    present = [key for key in longhands if key in value]
    if name in value and present:
        raise _Invalid(name)
    if name in value:
        sides = _shorthand(value[name], name)
    else:
        sides = [0.0, 0.0, 0.0, 0.0]
    named = dict(zip(_SIDES, sides, strict=True))
    for side, key in zip(_SIDES, longhands, strict=True):
        if key in value:
            named[side] = _length(value[key], key, nonnegative=nonnegative)
    return named


def _shorthand(value: object, name: str) -> list[float]:
    if isinstance(value, bool) or isinstance(value, (int, float)):
        length = _length(value, name, nonnegative=name != "margin")
        return [length, length, length, length]
    if not isinstance(value, str):
        raise _Invalid(name)
    parts = value.replace("px", "").split()
    if len(parts) not in {1, 2, 3, 4}:
        raise _Invalid(name)
    lengths = [_length(float(part) if _numeric(part) else part, name, nonnegative=name != "margin") for part in parts]
    if len(lengths) == 1:
        return [lengths[0], lengths[0], lengths[0], lengths[0]]
    if len(lengths) == 2:
        return [lengths[0], lengths[1], lengths[0], lengths[1]]
    if len(lengths) == 3:
        return [lengths[0], lengths[1], lengths[2], lengths[1]]
    return [lengths[0], lengths[1], lengths[2], lengths[3]]


def _overflow(value: dict[str, object]) -> tuple[str, str]:
    if "overflow" in value and ("overflow_x" in value or "overflow_y" in value):
        raise _Invalid("overflow")
    if "overflow" in value:
        parts = _keyword(value["overflow"], "overflow").split()
        if len(parts) == 1:
            return parts[0], parts[0]
        if len(parts) == 2:
            return _choice(parts[0], _OVERFLOW, "overflow"), _choice(parts[1], _OVERFLOW, "overflow")
        raise _Invalid("overflow")
    return (
        _choice(value.get("overflow_x", "visible"), _OVERFLOW, "overflow"),
        _choice(value.get("overflow_y", "visible"), _OVERFLOW, "overflow"),
    )


def _size(value: object, name: str) -> float | None:
    if value is None or value == "auto":
        return None
    return _length(value, name, nonnegative=True)


def _inset(value: object, name: str) -> float | None:
    if value is None or value == "auto":
        return None
    return _length(value, name, nonnegative=False)


def _transform(value: object) -> str | None:
    if value is None or value == "none":
        return None
    if not isinstance(value, str) or value.strip() == "":
        raise _Invalid("transform")
    return value.strip()


def _keyword(value: object, name: str) -> str:
    if not isinstance(value, str) or value.strip() == "":
        raise _Invalid(name)
    return " ".join(value.split())


def _choice(value: object, allowed: frozenset[str], name: str) -> str:
    if isinstance(value, str):
        token = " ".join(value.split())
    else:
        token = ""
    if token not in allowed:
        raise _Invalid(name)
    return token


def _length(value: object, name: str, *, nonnegative: bool) -> float:
    if isinstance(value, str):
        text = value.strip()
        if text.endswith("px"):
            text = text[:-2].strip()
        if not _numeric(text):
            raise _Invalid(name)
        value = float(text)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _Invalid(name)
    number = float(value)
    if number != number or number in {float("inf"), float("-inf")}:
        raise _Invalid(name)
    if nonnegative and number < 0.0:
        raise _Invalid(name)
    return number


def _numeric(text: str) -> bool:
    try:
        float(text)
    except ValueError:
        return False
    return True


def _number(value: float) -> int | float:
    nearest = round(value)
    if abs(value - nearest) <= _EPS:
        return int(nearest)
    return value


def _invalid(reason: str) -> dict[str, object]:
    return {
        "outcome": "invalid",
        "reason": reason,
        "scroll_width": None,
        "scroll_height": None,
        "left": None,
        "top": None,
        "right": None,
        "bottom": None,
    }
