"""Shift relatively positioned boxes without reflowing their siblings.

CSS 2.1 §9.4.3 keeps the border box a relative box already occupied in
normal flow. ``left`` and ``top`` move that border box; ``right`` and
``bottom`` are the opposite edges, so a solved pair always sums to zero.
Later boxes keep the static positions the caller laid out. Relative
positioning can overlap the next in-flow box, and it does not remove
either box from flow or change either box's size.

Percentages of ``left`` and ``right`` use the containing-block width.
Percentages of ``top`` and ``bottom`` use the containing-block height and
compute to ``auto`` when that height is ``auto``. An over-constrained
horizontal pair keeps ``left`` when the containing block's direction is
``ltr`` and keeps ``right`` when it is ``rtl``. An over-constrained
vertical pair keeps ``top``.
"""

from __future__ import annotations

import math

_AUTO = "auto"
_POSITIONS = frozenset({"static", "relative"})
_DIRECTIONS = frozenset({"ltr", "rtl"})


class _Invalid(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def place_relative(
    boxes: object,
    *,
    containing_width: object,
    containing_height: object = _AUTO,
) -> dict[str, object]:
    """Return each box's used border origin after relative offsets.

    ``x`` and ``y`` on the input are the static border origin. A static box
    ignores ``left``, ``right``, ``top``, and ``bottom``. A relative box
    adds its used ``left`` and ``top`` to that origin. Width and height are
    copied through unchanged.
    """

    try:
        width = _length(containing_width, "containing width", minimum=0)
        height = _block_height(containing_height)
        items = _boxes(boxes)
    except _Invalid as exc:
        return _invalid(exc.reason)
    placed: list[dict[str, object]] = []
    seen: set[str] = set()
    try:
        for item in items:
            placed.append(_place(item, width, height, seen))
    except _Invalid as exc:
        return _invalid(exc.reason)
    return {"outcome": "placed", "boxes": placed}


def _boxes(value: object) -> list[dict[str, object]]:
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise _Invalid("boxes must be a list")
    items: list[dict[str, object]] = []
    for entry in value:
        if not isinstance(entry, dict):
            raise _Invalid("box must be an object")
        items.append(dict(entry))
    return items


def _place(
    box: dict[str, object],
    width: float,
    height: float | None,
    seen: set[str],
) -> dict[str, object]:
    identifier = box.get("id")
    if not isinstance(identifier, str) or not identifier.strip():
        raise _Invalid("id must be a non-empty string")
    if identifier in seen:
        raise _Invalid("duplicate id")
    seen.add(identifier)
    position = _keyword(box.get("position"), _POSITIONS, "position must be static or relative")
    static_x = _length(box.get("x"), "x", allow_negative=True)
    static_y = _length(box.get("y"), "y", allow_negative=True)
    box_width = _length(box.get("width"), "width", minimum=0)
    box_height = _length(box.get("height"), "height", minimum=0)
    if position == "static":
        left = right = top = bottom = 0.0
    else:
        direction = _keyword(box.get("direction"), _DIRECTIONS, "direction must be ltr or rtl")
        left, right = _pair(
            _inset(box.get("left", _AUTO), "left", containing=width),
            _inset(box.get("right", _AUTO), "right", containing=width),
            end_wins=direction == "rtl",
        )
        top, bottom = _pair(
            _inset(box.get("top", _AUTO), "top", containing=height),
            _inset(box.get("bottom", _AUTO), "bottom", containing=height),
            end_wins=False,
        )
    return {
        "id": identifier,
        "x": _number(static_x + left),
        "y": _number(static_y + top),
        "width": _number(box_width),
        "height": _number(box_height),
        "left": _number(left),
        "right": _number(right),
        "top": _number(top),
        "bottom": _number(bottom),
        "static_x": _number(static_x),
        "static_y": _number(static_y),
    }


def _pair(start: float | None, end: float | None, *, end_wins: bool) -> tuple[float, float]:
    if start is None and end is None:
        return 0.0, 0.0
    if start is None:
        assert end is not None
        return -end, end
    if end is None:
        return start, -start
    if end_wins:
        return -end, end
    return start, -start


def _inset(value: object, name: str, *, containing: float | None) -> float | None:
    if isinstance(value, str) and value.strip().lower() == _AUTO:
        return None
    kind, number = _size(value, name)
    if kind == "pct":
        if containing is None:
            return None
        return containing * number / 100.0
    return number


def _block_height(value: object) -> float | None:
    if isinstance(value, str) and value.strip().lower() == _AUTO:
        return None
    return _length(value, "containing height", minimum=0)


def _keyword(value: object, allowed: frozenset[str], reason: str) -> str:
    if not isinstance(value, str):
        raise _Invalid(reason)
    token = value.strip().lower()
    if token not in allowed:
        raise _Invalid(reason)
    return token


def _length(
    value: object,
    name: str,
    *,
    minimum: float | None = None,
    allow_negative: bool = False,
) -> float:
    kind, number = _size(value, name, allow_negative=allow_negative or minimum is None)
    if kind != "px":
        raise _Invalid(f"{name} must be a length")
    if minimum is not None and number < minimum:
        raise _Invalid(f"{name} cannot be negative")
    return number


def _size(value: object, name: str, *, allow_negative: bool = True) -> tuple[str, float]:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise _Invalid(f"{name} must be a length, a percentage, or auto")
    if isinstance(value, (int, float)):
        number = float(value)
        if not math.isfinite(number):
            raise _Invalid(f"{name} must be a length, a percentage, or auto")
        if number < 0.0 and not allow_negative:
            raise _Invalid(f"{name} cannot be negative")
        return ("px", number)
    text = value.strip().lower()
    if text.endswith("%"):
        token = text[:-1]
        kind = "pct"
    elif text.endswith("px"):
        token = text[:-2]
        kind = "px"
    else:
        raise _Invalid(f"{name} must be a length, a percentage, or auto")
    try:
        number = float(token)
    except ValueError as exc:
        raise _Invalid(f"{name} must be a length, a percentage, or auto") from exc
    if not math.isfinite(number):
        raise _Invalid(f"{name} must be a length, a percentage, or auto")
    if number < 0.0 and not allow_negative:
        raise _Invalid(f"{name} cannot be negative")
    return (kind, number)


def _number(value: float) -> int | float:
    nearest = round(value)
    if abs(value - nearest) <= 1e-9:
        return int(nearest)
    return value


def _invalid(reason: str) -> dict[str, object]:
    return {"outcome": "invalid", "reason": reason, "boxes": None}
