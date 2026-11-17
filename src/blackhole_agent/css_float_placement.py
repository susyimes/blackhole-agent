"""Place floats and block formatting contexts in one containing block.

CSS 2.1 §9.5 puts a left float on the left and a right float on the right of
the highest band whose outer margin box does not intersect an earlier float.
A float wider than the containing block takes a band of its own and overflows
the opposite edge. A later float cannot rise above the bottom of an earlier
in-flow formatting context.

A formatting context (``float: none``) must not intersect a float. Automatic
width consumes the open gap. A zero gap beside a float is not usable, so the
context drops. A fixed width that exceeds the gap drops to the next band, and
a fixed width wider than the containing block overflows on an empty band.
``clear`` raises the top under the earlier floats it names. Width and height
are outer margin-box sizes; this does not shorten line boxes inside a block
that does not form a formatting context.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

_FLOATS = frozenset({"left", "right", "none"})
_CLEARS = frozenset({"none", "left", "right", "both"})
_FIELDS = frozenset({"id", "float", "width", "height", "clear"})
_AUTO = "auto"


class _Invalid(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass
class _Item:
    id: str
    side: str
    width: int | float | None
    height: int | float
    clear: str


@dataclass
class _Float:
    side: str
    x: int | float
    y: int | float
    width: int | float
    height: int | float


def place_floats(containing_width: object, boxes: object) -> dict[str, object]:
    """Return each outer margin box as ``x``, ``y``, ``width``, and ``height``.

    ``containing_width`` is the content width of the containing block, in CSS
    pixels. Each box has ``id``, ``float`` (``left``, ``right``, or ``none``),
    ``width`` (a length, or ``auto`` only when the box is not a float), and
    ``height``. ``clear`` is ``none``, ``left``, ``right``, or ``both``.
    Coordinates start at the containing block's content top-left and grow
    rightward and downward. A repeated id is invalid.
    """

    try:
        width = _length(containing_width, "containing-width")
        items = _items(boxes)
    except _Invalid as exc:
        return _invalid(exc.reason)
    try:
        placed = _place_all(width, items)
    except _Invalid as exc:
        return _invalid(exc.reason)
    return {"outcome": "placed", "boxes": placed}


def _items(boxes: object) -> list[_Item]:
    if not isinstance(boxes, list):
        raise _Invalid("boxes")
    items: list[_Item] = []
    seen: set[str] = set()
    for box in boxes:
        item = _item(box)
        if item.id in seen:
            raise _Invalid("duplicate")
        seen.add(item.id)
        items.append(item)
    return items


def _item(box: object) -> _Item:
    if not isinstance(box, dict):
        raise _Invalid("box")
    unknown = set(box) - _FIELDS
    if unknown:
        raise _Invalid("field")
    raw_id = box.get("id")
    if not isinstance(raw_id, str) or raw_id == "":
        raise _Invalid("id")
    side = box.get("float")
    if side not in _FLOATS:
        raise _Invalid("float")
    height = _length(box.get("height"), "height")
    clear = box.get("clear", "none")
    if clear not in _CLEARS:
        raise _Invalid("clear")
    raw_width = box.get("width")
    if raw_width == _AUTO:
        if side != "none":
            raise _Invalid("width")
        width: int | float | None = None
    else:
        width = _length(raw_width, "width")
    return _Item(id=raw_id, side=str(side), width=width, height=height, clear=str(clear))


def _length(value: object, name: str) -> int | float:
    if type(value) is int:
        number: int | float = value
    elif type(value) is float:
        number = value
    else:
        raise _Invalid(name)
    if not math.isfinite(number) or number < 0:
        raise _Invalid(name)
    return number


def _place_all(containing_width: int | float, items: list[_Item]) -> list[dict[str, object]]:
    floats: list[_Float] = []
    flow_y: int | float = 0
    placed: list[dict[str, object]] = []
    for item in items:
        min_y = _higher(flow_y, _clearance(item.clear, floats))
        x, y, used = _choose(item.side, item.width, item.height, min_y, floats, containing_width)
        placed.append({"id": item.id, "x": x, "y": y, "width": used, "height": item.height})
        if item.side == "none":
            flow_y = y + item.height
        else:
            floats.append(_Float(side=item.side, x=x, y=y, width=used, height=item.height))
    return placed


def _clearance(clear: str, floats: list[_Float]) -> int | float:
    top: int | float = 0
    if clear in {"left", "both"}:
        top = _max_bottom(top, floats, "left")
    if clear in {"right", "both"}:
        top = _max_bottom(top, floats, "right")
    return top


def _max_bottom(top: int | float, floats: list[_Float], side: str) -> int | float:
    for item in floats:
        if item.side == side:
            top = _higher(top, item.y + item.height)
    return top


def _choose(
    side: str,
    width: int | float | None,
    height: int | float,
    min_y: int | float,
    floats: list[_Float],
    containing_width: int | float,
) -> tuple[int | float, int | float, int | float]:
    events = [min_y]
    for item in floats:
        bottom = item.y + item.height
        if bottom > min_y:
            events.append(bottom)
    for y in sorted(set(events)):
        left, right = _limits(y, height, floats, containing_width)
        fitted = _fit(side, width, left, right, containing_width)
        if fitted is not None:
            x, used = fitted
            return x, y, used
    raise _Invalid("unplaced")


def _limits(
    y: int | float,
    height: int | float,
    floats: list[_Float],
    containing_width: int | float,
) -> tuple[int | float, int | float]:
    left: int | float = 0
    right = containing_width
    for item in floats:
        if y < item.y + item.height and y + height > item.y:
            if item.side == "left":
                left = _higher(left, item.x + item.width)
            else:
                right = _lower(right, item.x)
    return left, right


def _fit(
    side: str,
    width: int | float | None,
    left: int | float,
    right: int | float,
    containing_width: int | float,
) -> tuple[int | float, int | float] | None:
    if width is None:
        gap = right - left
        beside_float = not (left == 0 and right == containing_width)
        if gap < 0 or (beside_float and gap <= 0):
            return None
        return left, gap
    if width > containing_width:
        if left == 0 and right == containing_width:
            return (containing_width - width, width) if side == "right" else (0, width)
        return None
    if side == "right":
        x = right - width
        if x >= left:
            return x, width
        return None
    if left + width <= right:
        return left, width
    return None


def _higher(left: int | float, right: int | float) -> int | float:
    return left if left >= right else right


def _lower(left: int | float, right: int | float) -> int | float:
    return left if left <= right else right


def _invalid(reason: str) -> dict[str, object]:
    return {"outcome": "invalid", "boxes": None, "reason": reason}
