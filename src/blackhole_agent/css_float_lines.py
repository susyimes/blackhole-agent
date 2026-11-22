"""Pack atomic inlines into line boxes shortened by floats.

CSS 2.1 §9.5 puts a line box next to a float when some point lies on the
line's closed vertical span and strictly inside the float's margin edges.
That line starts after every intersecting left float and ends before every
intersecting right float. ``place_floats`` still places the float boxes; it
does not split inline atoms across those changing gaps.

A float may set ``shape`` to a CSS ``shape-outside`` and ``shape_margin`` in
pixels. The shape replaces the margin rectangle: a circle leaves its corner
open, an inset can end before the margin box, and a polygon hypotenuse lets
an atom through before the box ends. ``shape-margin`` expands that shape, then
the float area is clipped to the margin box. With no shape, the line still
moves to the earliest bottom among the floats it touches. With a shape, the
line moves to the earliest y where the atom fits, because the exclusion can
shrink before the margin box ends.

An atom wider than the containing block is placed only after no float still
intersects the line, and the line box keeps the containing block's width. The
next line starts at the placed line's bottom. Atoms are already unbreakable.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from blackhole_agent.css_shape_outside import Prepared, ShapeError, exclusion_x_range, prepare_shape

_SIDES = frozenset({"left", "right"})
_ATOM_FIELDS = frozenset({"id", "width"})
_FLOAT_FIELDS = frozenset({"side", "x", "y", "width", "height"})
_FLOAT_OPTIONAL = frozenset({"shape", "shape_margin"})


class _Invalid(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class _Atom:
    id: str
    width: float


@dataclass(frozen=True)
class _Band:
    side: str
    x: float
    y: float
    width: float
    height: float
    prepared: Prepared | None = None


def pack_line_boxes(
    containing_width: object,
    atoms: object,
    floats: object,
    line_height: object,
) -> dict[str, object]:
    """Return line boxes for ``atoms`` in a block that does not form a new formatting context.

    ``containing_width`` and ``line_height`` are CSS pixels. Each atom has
    ``id`` and a positive ``width``. Each float has ``side`` (``left`` or
    ``right``), margin-box ``x`` and ``y``, and a non-negative ``width`` and
    ``height``. Optional ``shape`` is a CSS shape-outside string, and optional
    ``shape_margin`` is a non-negative length in pixels. Coordinates grow right
    and down from the containing block's content top-left. A repeated atom id
    is invalid.
    """

    try:
        containing, items, bands, height = _inputs(containing_width, atoms, floats, line_height)
    except _Invalid as exc:
        return _invalid(exc.reason)
    lines: list[dict[str, object]] = []
    index = 0
    y = 0.0
    while index < len(items):
        y, left, right = _seek(y, items[index].width, bands, containing, height)
        taken, nxt = _take(items, index, right - left)
        if nxt <= index:
            break
        lines.append(
            {
                "x": _number(left),
                "y": _number(y),
                "width": _number(right - left),
                "height": _number(height),
                "atoms": [atom.id for atom in taken],
            }
        )
        index = nxt
        y += height
    return {"outcome": "placed", "lines": lines, "reason": None}


def shaped_gap_at(
    containing_width: object,
    floats: object,
    line_height: object,
    y: object,
) -> dict[str, object]:
    """Return the float intrusion at one line, without moving that line.

    ``blocked`` is true when a float area intersects the line. A shape-outside
    that misses the line does not shrink it. Coordinates match ``pack_line_boxes``.
    """

    try:
        containing, bands, height, start = _gap_inputs(containing_width, floats, line_height, y)
        left, right, blocked = _shape_gap(start, height, bands, containing)
    except _Invalid as exc:
        return {"outcome": "invalid", "left": None, "right": None, "blocked": None, "reason": exc.reason}
    return {
        "outcome": "placed",
        "left": _number(left),
        "right": _number(right),
        "blocked": blocked,
        "reason": None,
    }


def seek_shaped_gap(
    containing_width: object,
    floats: object,
    line_height: object,
    y: object,
    need: object,
) -> dict[str, object]:
    """Return the first line at or below ``y`` whose gap can hold ``need``."""

    try:
        containing, bands, height, start = _gap_inputs(containing_width, floats, line_height, y)
        width = _finite(need, "need")
        if width < 0:
            raise _Invalid("need")
        found, left, right = _seek(start, width, bands, containing, height)
    except _Invalid as exc:
        return {"outcome": "invalid", "y": None, "left": None, "right": None, "reason": exc.reason}
    return {
        "outcome": "placed",
        "y": _number(found),
        "left": _number(left),
        "right": _number(right),
        "reason": None,
    }


def _gap_inputs(
    containing_width: object,
    floats: object,
    line_height: object,
    y: object,
) -> tuple[float, list[_Band], float, float]:
    containing = _finite(containing_width, "containing_width")
    if containing < 0:
        raise _Invalid("containing_width")
    height = _finite(line_height, "line_height")
    if height <= 0:
        raise _Invalid("line_height")
    start = _finite(y, "y")
    if start < 0:
        raise _Invalid("y")
    return containing, _bands(floats), height, start


def _inputs(
    containing_width: object,
    atoms: object,
    floats: object,
    line_height: object,
) -> tuple[float, list[_Atom], list[_Band], float]:
    containing = _finite(containing_width, "containing_width")
    if containing < 0:
        raise _Invalid("containing_width")
    height = _finite(line_height, "line_height")
    if height <= 0:
        raise _Invalid("line_height")
    return containing, _atoms(atoms), _bands(floats), height


def _atoms(value: object) -> list[_Atom]:
    if not isinstance(value, list):
        raise _Invalid("atoms")
    items: list[_Atom] = []
    seen: set[str] = set()
    for raw in value:
        if not isinstance(raw, dict) or set(raw) != _ATOM_FIELDS:
            raise _Invalid("atoms")
        identity = raw.get("id")
        if not isinstance(identity, str) or identity == "" or identity in seen:
            raise _Invalid("id")
        width = _finite(raw.get("width"), "width")
        if width <= 0:
            raise _Invalid("width")
        seen.add(identity)
        items.append(_Atom(identity, width))
    return items


def _bands(value: object) -> list[_Band]:
    if not isinstance(value, list):
        raise _Invalid("floats")
    bands: list[_Band] = []
    for raw in value:
        keys = set(raw) if isinstance(raw, dict) else set()
        if not isinstance(raw, dict) or not _FLOAT_FIELDS <= keys or not keys <= _FLOAT_FIELDS | _FLOAT_OPTIONAL:
            raise _Invalid("floats")
        side = raw.get("side")
        if side not in _SIDES:
            raise _Invalid("side")
        x = _finite(raw.get("x"), "x")
        y = _finite(raw.get("y"), "y")
        width = _finite(raw.get("width"), "width")
        height = _finite(raw.get("height"), "height")
        if width < 0 or height < 0:
            raise _Invalid("width" if width < 0 else "height")
        margin = 0.0
        if "shape_margin" in raw:
            margin = _finite(raw.get("shape_margin"), "shape_margin")
            if margin < 0:
                raise _Invalid("shape_margin")
        prepared = None
        if "shape" in raw:
            shape = raw.get("shape")
            if not isinstance(shape, str) or shape.strip() == "":
                raise _Invalid("shape")
            try:
                prepared = prepare_shape(shape, width, height, margin)
            except ShapeError as exc:
                raise _Invalid(exc.reason) from exc
        bands.append(_Band(str(side), x, y, width, height, prepared))
    return bands


def _seek(
    y: float,
    need: float,
    bands: list[_Band],
    containing: float,
    line_height: float,
) -> tuple[float, float, float]:
    if any(band.prepared is not None for band in bands):
        return _seek_shape(y, need, bands, containing, line_height)
    y_now = y
    for _ in range(len(bands) + 1):
        left, right, bottoms = _gap(y_now, line_height, bands, containing)
        if need <= right - left or not bottoms:
            return y_now, left, right
        nxt = min(bottoms)
        if nxt <= y_now:
            return y_now, left, right
        y_now = nxt
    left, right, _bottoms = _gap(y_now, line_height, bands, containing)
    return y_now, left, right


def _gap(
    y: float,
    line_height: float,
    bands: list[_Band],
    containing: float,
) -> tuple[float, float, list[float]]:
    left = 0.0
    right = containing
    bottoms: list[float] = []
    for band in bands:
        bottom = band.y + band.height
        if band.height <= 0 or not (y < bottom and y + line_height > band.y):
            continue
        bottoms.append(bottom)
        if band.side == "left":
            edge = band.x + band.width
            if edge > left:
                left = edge
        elif band.x < right:
            right = band.x
    return left, right, bottoms


def _seek_shape(
    y: float,
    need: float,
    bands: list[_Band],
    containing: float,
    line_height: float,
) -> tuple[float, float, float]:
    def measure(at: float) -> tuple[float, float, bool]:
        return _shape_gap(at, line_height, bands, containing)

    left, right, blocked = measure(y)
    if need <= right - left or not blocked:
        return y, left, right
    limit = max(band.y + band.height for band in bands)
    if limit <= y:
        return y, left, right
    prev = y
    for event in _shape_events(bands, y, limit, line_height):
        found = _fit_between(prev, event, need, measure, bands, containing, line_height)
        if found is not None:
            return found
        prev = event
    left, right, _blocked = measure(limit)
    return limit, left, right


def _shape_gap(
    y: float,
    line_height: float,
    bands: list[_Band],
    containing: float,
) -> tuple[float, float, bool]:
    left = 0.0
    right = containing
    blocked = False
    for band in bands:
        interval = _shape_interval(band, y, line_height)
        if interval is None:
            continue
        blocked = True
        xmin, xmax = interval
        if band.side == "left":
            if xmax > left:
                left = xmax
        elif xmin < right:
            right = xmin
    return left, right, blocked


def _shape_interval(band: _Band, y: float, line_height: float) -> tuple[float, float] | None:
    if band.prepared is None:
        bottom = band.y + band.height
        if band.height <= 0 or not (y < bottom and y + line_height > band.y):
            return None
        return band.x, band.x + band.width
    if band.height <= 0 or band.width < 0:
        return None
    local0 = y - band.y
    span = exclusion_x_range(band.width, band.height, band.prepared, local0, local0 + line_height)
    if span is None:
        return None
    return band.x + span[0], band.x + span[1]


def _shape_events(bands: list[_Band], start: float, limit: float, line_height: float) -> list[float]:
    found: set[float] = set()
    for band in bands:
        found.add(band.y + band.height)
        if band.prepared is not None:
            for local in band.prepared.events(line_height):
                found.add(band.y + local)
    return sorted(event for event in found if start < event <= limit)


def _fit_between(
    start: float,
    end: float,
    need: float,
    measure,
    bands: list[_Band],
    containing: float,
    line_height: float,
    depth: int = 0,
) -> tuple[float, float, float] | None:
    candidates = [_linear_cross(start, end, need, measure)]
    for band in bands:
        candidates.extend(_curve_crosses(band, containing, need, line_height))
    for candidate in sorted(item for item in candidates if item is not None):
        if _first_fit(candidate, start, end, need, measure):
            left, right, _blocked = measure(candidate)
            return candidate, left, right
    if depth < 24:
        mid = (start + end) / 2
        if mid > start and _fits(mid, need, measure):
            earlier = _fit_between(start, mid, need, measure, bands, containing, line_height, depth + 1)
            if earlier is not None:
                return earlier
    if _fits(end, need, measure):
        left, right, _blocked = measure(end)
        return end, left, right
    return None


def _fits(y: float, need: float, measure) -> bool:
    left, right, blocked = measure(y)
    return (not blocked) or need <= right - left


def _first_fit(y: float, start: float, end: float, need: float, measure) -> bool:
    if not (start < y <= end) or not _fits(y, need, measure):
        return False
    earlier = y - max(1e-6, (y - start) * 1e-9)
    return earlier <= start or not _fits(earlier, need, measure)


def _linear_cross(start: float, end: float, need: float, measure) -> float | None:
    def room(at: float) -> float:
        left, right, blocked = measure(at)
        if not blocked:
            return math.inf
        return right - left

    start_room = room(start)
    end_room = room(end)
    if math.isinf(start_room) or math.isinf(end_room):
        return None
    mid = (start + end) / 2
    mid_room = room(mid)
    if math.isinf(mid_room):
        return None
    scale = max(1.0, abs(start_room), abs(end_room), abs(mid_room))
    if abs(mid_room - (start_room + end_room) / 2) > 1e-9 * scale:
        return None
    if abs(end_room - start_room) <= 1e-12:
        return None
    return start + (need - start_room) * (end - start) / (end_room - start_room)


def _curve_crosses(band: _Band, containing: float, need: float, line_height: float) -> list[float]:
    prepared = band.prepared
    if prepared is None or prepared.kind not in {"circle", "ellipse"}:
        return []
    if prepared.kind == "circle":
        radius_x = prepared.rx
        radius_y = prepared.rx
    else:
        radius_x = prepared.rx
        radius_y = prepared.ry
    if radius_x <= 0 or radius_y <= 0:
        return []
    if band.side == "left":
        half = containing - need - band.x - prepared.cx
    else:
        half = band.x + prepared.cx - need
    if half < 0 or half > radius_x:
        return []
    ratio = half / radius_x
    if ratio > 1:
        return []
    dy = radius_y * math.sqrt(max(0.0, 1 - ratio * ratio))
    center = band.y + prepared.cy
    return [center + dy, center - dy - line_height]


def _take(atoms: list[_Atom], start: int, room: float) -> tuple[list[_Atom], int]:
    taken: list[_Atom] = []
    used = 0.0
    index = start
    while index < len(atoms):
        width = atoms[index].width
        if used + width > room:
            if not taken:
                taken.append(atoms[index])
                index += 1
            break
        taken.append(atoms[index])
        used += width
        index += 1
    return taken, index


def _finite(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise _Invalid(name)
    return float(value)


def _number(value: float) -> int | float:
    rounded = math.trunc(value)
    if value == rounded:
        return int(rounded)
    return value


def _invalid(reason: str) -> dict[str, object]:
    return {"outcome": "invalid", "lines": None, "reason": reason}
