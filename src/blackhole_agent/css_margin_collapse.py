"""Used vertical margins of in-flow blocks.

CSS 2.1 §8.3.1 collapses adjoining vertical margins into one separation.
Positive margins contribute their maximum and negative margins contribute
their most negative value. Those pieces stay separate until the adjoining
set is closed: collapsing a subset first would drop a positive piece that
a later neighbor still needs.

A parent with no top padding and no top border takes its first child's top
margin outside the border edge. An empty block with no padding, border, or
line box lets its own margins collapse through it. A float, an absolute or
fixed box, an inline-block, a flow-root, and a block whose overflow is not
visible keep child margins inside.

Float and absolute children are out of flow and are rejected. Clearance is
supplied by the caller. It stops a top margin from collapsing with the
parent or the previous sibling. A collapsed-through clearance box still
collapses with following siblings, and that result stays inside the parent.
``trim_block_start`` and ``trim_block_end`` discard the descendant margins
that adjoin those edges, including margins collapsed with them. The box's
own margin, and a sibling margin that does not adjoin the trimmed edge,
stay. Horizontal margins are untouched. After the content span is known,
``max_height`` clamps it and ``min_height`` raises it, so the minimum wins
when both apply. An absent maximum does not clamp. A maximum alone does not
stop a zero minimum from collapsing through.
"""

from __future__ import annotations

from dataclasses import dataclass, field

_AUTO = "auto"
_FIELDS = frozenset(
    {
        "id",
        "margin_top",
        "margin_bottom",
        "padding_top",
        "padding_bottom",
        "border_top",
        "border_bottom",
        "height",
        "min_height",
        "max_height",
        "overflow",
        "float",
        "position",
        "display",
        "clearance",
        "trim_block_start",
        "trim_block_end",
        "children",
    }
)
_OVERFLOWS = frozenset({"visible", "hidden", "auto", "scroll", "clip"})
_FLOATS = frozenset({"none", "left", "right"})
_POSITIONS = frozenset({"static", "relative", "absolute", "fixed"})
_DISPLAYS = frozenset({"block", "flow-root", "inline-block"})


class _Invalid(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass
class _Spec:
    id: str
    margin_top: int
    margin_bottom: int
    padding_top: int
    padding_bottom: int
    border_top: int
    border_bottom: int
    height: int | None
    min_height: int
    max_height: int | None
    overflow: str
    float: str
    position: str
    display: str
    clearance: bool
    trim_block_start: bool
    trim_block_end: bool
    children: list[_Spec]


@dataclass
class _Node:
    id: str
    y: int
    border_height: int
    through: bool
    margin_top: int
    margin_bottom: int
    parts_top: list[int]
    parts_bottom: list[int]
    parts: list[int]
    top_parts: list[int]
    clearance: bool
    blocks_bottom: bool
    kids: list[_Node] = field(default_factory=list)


def place_collapsed_margins(box: object) -> dict[str, object]:
    """Place one in-flow block and the blocks inside it.

    ``y`` is the top border edge measured from this box's top border edge.
    ``margin_top`` and ``margin_bottom`` are the used margins outside that
    border edge. A box that collapses through reports one ``margin_top``,
    a zero ``margin_bottom``, and a zero border height. A repeated id is
    invalid.
    """

    try:
        spec = _spec(box, nested=False, seen=set())
        node = _layout(spec)
    except _Invalid as exc:
        return _invalid(exc.reason)
    boxes: list[dict[str, object]] = []
    _flatten(node, 0, boxes)
    return {
        "outcome": "placed",
        "margin_top": node.margin_top,
        "margin_bottom": node.margin_bottom,
        "boxes": boxes,
    }


def _spec(box: object, *, nested: bool, seen: set[str]) -> _Spec:
    if not isinstance(box, dict):
        raise _Invalid("box")
    if set(box) - _FIELDS:
        raise _Invalid("field")
    raw_id = box.get("id")
    if not isinstance(raw_id, str) or raw_id == "":
        raise _Invalid("id")
    if raw_id in seen:
        raise _Invalid("duplicate")
    seen.add(raw_id)
    spec = _Spec(
        id=raw_id,
        margin_top=_margin(box.get("margin_top", 0)),
        margin_bottom=_margin(box.get("margin_bottom", 0)),
        padding_top=_gap(box.get("padding_top", 0), "padding"),
        padding_bottom=_gap(box.get("padding_bottom", 0), "padding"),
        border_top=_gap(box.get("border_top", 0), "border"),
        border_bottom=_gap(box.get("border_bottom", 0), "border"),
        height=_height(box.get("height", _AUTO)),
        min_height=_gap(box.get("min_height", 0), "min-height"),
        max_height=_max_height(box.get("max_height", "none")),
        overflow=_choice(box.get("overflow", "visible"), _OVERFLOWS, "overflow"),
        float=_choice(box.get("float", "none"), _FLOATS, "float"),
        position=_choice(box.get("position", "static"), _POSITIONS, "position"),
        display=_choice(box.get("display", "block"), _DISPLAYS, "display"),
        clearance=_flag(box.get("clearance", False)),
        trim_block_start=_flag(box.get("trim_block_start", False)),
        trim_block_end=_flag(box.get("trim_block_end", False)),
        children=_children(box.get("children", []), seen),
    )
    if nested and (spec.float != "none" or spec.position in {"absolute", "fixed"}):
        raise _Invalid("out-of-flow")
    return spec


def _children(value: object, seen: set[str]) -> list[_Spec]:
    if not isinstance(value, list):
        raise _Invalid("children")
    return [_spec(child, nested=True, seen=seen) for child in value]


def _layout(spec: _Spec) -> _Node:
    kids = [_layout(child) for child in spec.children]
    if _bfc(spec):
        return _contained(spec, kids)
    if _can_through(spec, kids):
        return _through_node(spec, kids)
    return _block_node(spec, kids)


def _bfc(spec: _Spec) -> bool:
    return (
        spec.float != "none"
        or spec.overflow != "visible"
        or spec.position in {"absolute", "fixed"}
        or spec.display in {"inline-block", "flow-root"}
    )


def _can_through(spec: _Spec, kids: list[_Node]) -> bool:
    return (
        spec.min_height == 0
        and spec.padding_top == spec.padding_bottom == 0
        and spec.border_top == spec.border_bottom == 0
        and (spec.height is None or spec.height == 0)
        and all(child.through for child in kids)
        and not _bottom_blocked(kids)
    )


def _through_node(spec: _Spec, kids: list[_Node]) -> _Node:
    parts: list[int] = [spec.margin_top, spec.margin_bottom]
    top_parts = [spec.margin_top]
    # A through box joins every descendant margin into both edges. Trimming
    # either edge drops those descendant pieces and keeps the box's own.
    discard = spec.trim_block_start or spec.trim_block_end
    for child in kids:
        child.y = 0
        if discard:
            continue
        parts.extend(child.parts)
        top_parts.extend(child.parts)
    blocked = spec.clearance or any(child.blocks_bottom for child in kids)
    collapsed = _collapse(parts)
    return _Node(
        id=spec.id,
        y=0,
        border_height=0,
        through=True,
        margin_top=collapsed,
        margin_bottom=0,
        parts_top=parts,
        parts_bottom=[],
        parts=parts,
        top_parts=top_parts,
        clearance=spec.clearance,
        blocks_bottom=blocked,
        kids=kids,
    )


def _contained(spec: _Spec, kids: list[_Node]) -> _Node:
    content_y = spec.border_top + spec.padding_top
    flow_end = _place(kids, content_y=content_y, absorb_top=False, absorb_bottom=False, spec=spec)[0]
    return _box(spec, kids, flow_end, [spec.margin_top], [spec.margin_bottom])


def _block_node(spec: _Spec, kids: list[_Node]) -> _Node:
    absorb_top = bool(kids) and spec.border_top == 0 and spec.padding_top == 0 and not kids[0].clearance
    absorb_bottom = (
        bool(kids)
        and spec.height is None
        and spec.min_height == 0
        and spec.border_bottom == 0
        and spec.padding_bottom == 0
        and not _bottom_blocked(kids)
    )
    content_y = spec.border_top + spec.padding_top
    flow_end, top_parts, bottom_parts = _place(
        kids,
        content_y=content_y,
        absorb_top=absorb_top,
        absorb_bottom=absorb_bottom,
        spec=spec,
    )
    return _box(spec, kids, flow_end, top_parts, bottom_parts)


def _box(
    spec: _Spec,
    kids: list[_Node],
    flow_end: int,
    top_parts: list[int],
    bottom_parts: list[int],
) -> _Node:
    content_y = spec.border_top + spec.padding_top
    span = spec.height if spec.height is not None else max(0, flow_end - content_y)
    if spec.max_height is not None and span > spec.max_height:
        span = spec.max_height
    if spec.min_height > span:
        span = spec.min_height
    return _Node(
        id=spec.id,
        y=0,
        border_height=content_y + span + spec.padding_bottom + spec.border_bottom,
        through=False,
        margin_top=_collapse(top_parts),
        margin_bottom=_collapse(bottom_parts),
        parts_top=top_parts,
        parts_bottom=bottom_parts,
        parts=[],
        top_parts=top_parts,
        clearance=spec.clearance,
        blocks_bottom=False,
        kids=kids,
    )


def _bottom_blocked(kids: list[_Node]) -> bool:
    if not kids:
        return False
    tail: list[_Node] = []
    for child in reversed(kids):
        tail.append(child)
        if not child.through:
            break
    return any(child.blocks_bottom for child in tail)


def _place(
    kids: list[_Node],
    *,
    content_y: int,
    absorb_top: bool,
    absorb_bottom: bool,
    spec: _Spec,
) -> tuple[int, list[int], list[int]]:
    top_parts = [spec.margin_top]
    bottom_parts = [spec.margin_bottom]
    if not kids:
        return content_y, top_parts, bottom_parts
    prev_end: int | None = None
    carried = 0
    for index, segment in enumerate(_segments(kids)):
        leading, blocks, trailing = _partition(segment)
        if not blocks:
            prev_end, carried, top_parts = _through_segment(
                leading,
                index=index,
                content_y=content_y,
                absorb_top=absorb_top,
                prev_end=prev_end,
                carried=carried,
                top_parts=top_parts,
                spec=spec,
            )
            if index == len(_segments(kids)) - 1 and spec.trim_block_end:
                carried = 0
            continue
        first = blocks[0][0]
        trim_start = index == 0 and spec.trim_block_start
        if index == 0 and absorb_top:
            if trim_start:
                top_parts = [spec.margin_top]
                for child in leading:
                    child.y = content_y
            else:
                top_parts = [spec.margin_top, *_parts(leading), *_edge(first, top=True)]
                for child in leading:
                    child.y = 0
            first.y = content_y
            base = content_y
            extra = 0
        elif prev_end is None:
            base = content_y
            extra = 0
            if trim_start:
                first.y = content_y
                for child in leading:
                    child.y = content_y
            else:
                first.y = base + _collapse([*_parts(leading), *_edge(first, top=True)])
                _mark_leading(leading, base)
        else:
            base = prev_end
            extra = carried
            first.y = base + extra + _collapse([*_parts(leading), *_edge(first, top=True)])
            _mark_leading(leading, base + extra)
        previous = first
        for block, between in blocks[1:]:
            block.y = previous.y + previous.border_height + _collapse(
                [*_edge(previous, top=False), *_parts(between), *_edge(block, top=True)]
            )
            _mark_between(between, previous)
            previous = block
        _mark_between(trailing, previous)
        prev_end = previous.y + previous.border_height
        trail = [*_edge(previous, top=False), *_parts(trailing)]
        at_end = index == len(_segments(kids)) - 1 and not _segment_blocks(trailing)
        if at_end and absorb_bottom:
            bottom_parts = [spec.margin_bottom] if spec.trim_block_end else [*trail, spec.margin_bottom]
            carried = 0
        elif at_end and spec.trim_block_end:
            carried = 0
        else:
            carried = _collapse(trail)
    flow_end = content_y if prev_end is None else prev_end
    return flow_end + carried, top_parts, bottom_parts


def _through_segment(
    leading: list[_Node],
    *,
    index: int,
    content_y: int,
    absorb_top: bool,
    prev_end: int | None,
    carried: int,
    top_parts: list[int],
    spec: _Spec,
) -> tuple[int | None, int, list[int]]:
    parts = _parts(leading)
    if index == 0 and absorb_top and not _segment_blocks(leading):
        for child in leading:
            child.y = 0
        if spec.trim_block_start:
            return None, 0, [spec.margin_top]
        return None, 0, [spec.margin_top, *parts]
    if index == 0 and spec.trim_block_start and prev_end is None:
        for child in leading:
            child.y = content_y
        return content_y, 0, top_parts
    origin = content_y if prev_end is None else prev_end + carried
    _mark_leading(leading, origin)
    end = content_y if prev_end is None else prev_end
    if prev_end is not None:
        end = prev_end + carried
    return end, _collapse(parts), top_parts


def _segments(kids: list[_Node]) -> list[list[_Node]]:
    segments: list[list[_Node]] = [[]]
    for child in kids:
        if child.clearance and segments[-1]:
            segments.append([])
        segments[-1].append(child)
    return [segment for segment in segments if segment]


def _partition(segment: list[_Node]) -> tuple[list[_Node], list[tuple[_Node, list[_Node]]], list[_Node]]:
    leading: list[_Node] = []
    blocks: list[tuple[_Node, list[_Node]]] = []
    pending: list[_Node] = []
    seen_block = False
    for child in segment:
        if child.through:
            if seen_block:
                pending.append(child)
            else:
                leading.append(child)
            continue
        seen_block = True
        blocks.append((child, pending))
        pending = []
    return leading, blocks, pending


def _mark_leading(leading: list[_Node], origin: int) -> None:
    earlier: list[int] = []
    for child in leading:
        child.y = origin + _collapse([*earlier, *child.top_parts])
        earlier.extend(child.parts)


def _mark_between(between: list[_Node], previous: _Node) -> None:
    origin = previous.y + previous.border_height
    earlier = [*_edge(previous, top=False)]
    for child in between:
        child.y = origin + _collapse([*earlier, *child.top_parts])
        earlier.extend(child.parts)


def _segment_blocks(nodes: list[_Node]) -> bool:
    return any(node.blocks_bottom for node in nodes)


def _parts(nodes: list[_Node]) -> list[int]:
    parts: list[int] = []
    for node in nodes:
        parts.extend(node.parts)
    return parts


def _edge(node: _Node, *, top: bool) -> list[int]:
    return node.parts_top if top else node.parts_bottom


def _collapse(margins: list[int]) -> int:
    if not margins:
        return 0
    positive = max((margin for margin in margins if margin > 0), default=0)
    negative = min((margin for margin in margins if margin < 0), default=0)
    return positive + negative


def _flatten(node: _Node, origin: int, boxes: list[dict[str, object]]) -> None:
    boxes.append(
        {
            "id": node.id,
            "y": origin + node.y,
            "border_height": node.border_height,
            "through": node.through,
        }
    )
    for child in node.kids:
        _flatten(child, origin + node.y, boxes)


def _margin(value: object) -> int:
    return _number(value, "margin")


def _gap(value: object, name: str) -> int:
    number = _number(value, name)
    if number < 0:
        raise _Invalid(name)
    return number


def _max_height(value: object) -> int | None:
    if value is None or value == "none":
        return None
    number = _number(value, "max-height")
    if number < 0:
        raise _Invalid("max-height")
    return number


def _height(value: object) -> int | None:
    if value == _AUTO:
        return None
    number = _number(value, "height")
    if number < 0:
        raise _Invalid("height")
    return number


def _number(value: object, name: str) -> int:
    if type(value) is not int:
        raise _Invalid(name)
    return value


def _choice(value: object, allowed: frozenset[str], name: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise _Invalid(name)
    return value


def _flag(value: object) -> bool:
    if type(value) is not bool:
        raise _Invalid("clearance")
    return value


def _invalid(reason: str) -> dict[str, object]:
    return {"outcome": "invalid", "boxes": None, "reason": reason}
