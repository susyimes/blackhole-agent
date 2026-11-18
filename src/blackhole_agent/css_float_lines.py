"""Pack atomic inlines into line boxes shortened by floats.

CSS 2.1 §9.5 puts a line box next to a float when some point lies on the
line's closed vertical span and strictly inside the float's margin edges.
That line starts after every intersecting left float and ends before every
intersecting right float. ``place_floats`` still places the float boxes; it
does not split inline atoms across those changing gaps.

If the next atom does not fit, the line moves to the earliest bottom among
the floats it currently touches and the gap is measured again. An atom wider
than the containing block is placed only after no float still intersects the
line, and the line box keeps the containing block's width. The next line
starts at the placed line's bottom, so a float that ended there no longer
narrows it. Atoms are already unbreakable: this does not break characters.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

_SIDES = frozenset({"left", "right"})
_ATOM_FIELDS = frozenset({"id", "width"})
_FLOAT_FIELDS = frozenset({"side", "x", "y", "width", "height"})


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
    ``height``. Coordinates grow right and down from the containing block's
    content top-left. A repeated atom id is invalid.
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
        if not isinstance(raw, dict) or set(raw) != _FLOAT_FIELDS:
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
        bands.append(_Band(str(side), x, y, width, height))
    return bands


def _seek(
    y: float,
    need: float,
    bands: list[_Band],
    containing: float,
    line_height: float,
) -> tuple[float, float, float]:
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
