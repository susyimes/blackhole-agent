"""Paint a document from back to front.

CSS 2.2 Appendix E paints one stacking context in this order: the context
itself, positioned descendants with a negative stack, in-flow blocks, floats,
inlines, positioned descendants whose stack is automatic or zero, then
positioned descendants with a positive stack. A float, an inline-block, and a
positioned box with an automatic z-index are painted as their own group, but
a positioned descendant and any descendant that forms a real stacking context
join the ancestor instead. An explicit zero is atomic, so those descendants
stay inside it.

CSS Color 3 paints a non-positioned box with opacity below one on the same
band as stack zero, and a positioned box with opacity below one treats an
automatic z-index as zero. A transform other than ``none`` also forms a
stacking context: a static box, and a positioned box with an automatic
z-index, then keep their descendants and paint on that same zero band. A
z-index on a static box is ignored. Float is ignored once the box is
positioned. Each entry is the element's own background and border; outlines
and text decorations are not separate entries.
"""

from __future__ import annotations

from dataclasses import dataclass, field

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
_FIELDS = frozenset(
    {"id", "position", "z_index", "opacity", "float", "display", "transform", "children"}
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
    transformed: bool
    children: list[_Box] = field(default_factory=list)


@dataclass
class _Bands:
    negative: list[tuple[int, int, list[str]]] = field(default_factory=list)
    blocks: list[tuple[int, list[str]]] = field(default_factory=list)
    floats: list[tuple[int, list[str]]] = field(default_factory=list)
    inlines: list[tuple[int, list[str]]] = field(default_factory=list)
    zeros: list[tuple[int, list[str]]] = field(default_factory=list)
    positive: list[tuple[int, int, list[str]]] = field(default_factory=list)


def paint_order(tree: object) -> dict[str, object]:
    """Return element ids from back to front.

    ``tree`` is a nested object. ``id`` is a non-empty string. ``position``
    is ``static``, ``relative``, ``absolute``, ``fixed``, or ``sticky``.
    ``z_index`` is ``auto`` or an integer.     ``opacity`` is a number from 0 to
    1. ``float`` is ``none``, ``left``, or ``right``. ``display`` is
    ``block``, ``inline``, ``inline-block``, ``inline-flex``, ``flex``,
    ``grid``, ``table``, ``table-row``, or ``table-cell``. ``transform`` other than
    ``none`` forms a stacking context. ``children`` is a list of the same
    shape. A repeated id is invalid.
    """

    try:
        root = _parse(tree, seen=set())
    except _Invalid as exc:
        return {"outcome": "invalid", "order": None, "reason": exc.reason}
    return {"outcome": "ordered", "order": _paint_real(root)}


def _parse(value: object, *, seen: set[str]) -> _Box:
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
    transformed = _transformed(value.get("transform", "none"))
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
        transformed=transformed,
    )
    box.children = [_parse(child, seen=seen) for child in children]
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
    if not 0.0 <= number <= 1.0:
        raise _Invalid("opacity")
    return number


def _transformed(value: object) -> bool:
    if not isinstance(value, str):
        raise _Invalid("transform")
    text = value.strip().lower()
    if not text:
        raise _Invalid("transform")
    return text != "none"


def _real(box: _Box) -> bool:
    if box.transformed or box.opacity < 1:
        return True
    return box.position != "static" and box.z_index is not None


def _stack_z(box: _Box) -> int:
    """Stack used when ``box`` forms a real stacking context."""

    if box.position != "static" and box.z_index is not None:
        return box.z_index
    # Opacity, or a transform other than none, paints a static box on the
    # zero band. A positioned automatic z-index does the same once the box
    # forms a real stacking context.
    return 0


def _paint_real(box: _Box) -> list[str]:
    bands = _Bands()
    _walk(box, bands, None, 0)
    return [box.id, *_flatten(bands)]


def _walk(parent: _Box, real: _Bands, group: _Bands | None, seq: int) -> int:
    target = group if group is not None else real
    for child in parent.children:
        if _real(child):
            seq = _place_real(child, real, seq)
            continue
        if child.position != "static":
            seq = _place_auto(child, real, seq)
            continue
        if child.float != "none":
            seq = _place_group(child, real, target.floats, seq)
            continue
        if child.display in {"inline-block", "inline-flex"}:
            seq = _place_group(child, real, target.inlines, seq)
            continue
        if child.display == "inline":
            target.inlines.append((seq, [child.id]))
            seq += 1
            seq = _walk(child, real, group, seq)
            continue
        target.blocks.append((seq, [child.id]))
        seq += 1
        seq = _walk(child, real, group, seq)
    return seq


def _place_real(box: _Box, real: _Bands, seq: int) -> int:
    painted = _paint_real(box)
    z = _stack_z(box)
    if z < 0:
        real.negative.append((z, seq, painted))
    elif z > 0:
        real.positive.append((z, seq, painted))
    else:
        real.zeros.append((seq, painted))
    return seq + 1


def _place_auto(box: _Box, real: _Bands, seq: int) -> int:
    """Automatic z-index joins the ancestor's zero band and lets descendants out."""

    mine = seq
    group = _Bands()
    seq = _walk(box, real, group, seq + 1)
    real.zeros.append((mine, [box.id, *_flatten(group)]))
    return seq


def _place_group(box: _Box, real: _Bands, bucket: list[tuple[int, list[str]]], seq: int) -> int:
    """Floats and inline-blocks keep ordinary descendants and release the rest."""

    mine = seq
    group = _Bands()
    seq = _walk(box, real, group, seq + 1)
    bucket.append((mine, [box.id, *_flatten(group)]))
    return seq


def _flatten(bands: _Bands) -> list[str]:
    order: list[str] = []
    for _z, _seq, ids in sorted(bands.negative, key=lambda item: (item[0], item[1])):
        order.extend(ids)
    for _seq, ids in sorted(bands.blocks, key=lambda item: item[0]):
        order.extend(ids)
    for _seq, ids in sorted(bands.floats, key=lambda item: item[0]):
        order.extend(ids)
    for _seq, ids in sorted(bands.inlines, key=lambda item: item[0]):
        order.extend(ids)
    for _seq, ids in sorted(bands.zeros, key=lambda item: item[0]):
        order.extend(ids)
    for _z, _seq, ids in sorted(bands.positive, key=lambda item: (item[0], item[1])):
        order.extend(ids)
    return order
