"""Align one CSS grid item inside the grid area it occupies.

CSS Grid §11 and CSS Box Alignment §6 place the item's margin box in that
area. ``normal`` stretches a non-replaced item and start-aligns a replaced
item at its natural size. ``stretch`` fills the area only when the size is
automatic and neither margin is automatic; a definite size, or a maximum
that stops the fill, falls back to the start. Any other keyword keeps a
definite size, or the natural size when the size is automatic.

An automatic margin absorbs positive free space and disables self-alignment.
Negative free space sets automatic margins to zero, then honors the
alignment. The default overflow mode is unsafe, so ``center`` may cross the
start edge. ``safe`` packs an overflowing margin box against the start.
``left`` and ``right`` are physical on a horizontal inline axis and behave
as ``start`` when that axis is vertical. ``self-start`` uses the item's own
start side, including a vertical-rl item's block start. ``first baseline``
and ``last baseline`` use the safe self-start and safe self-end fallbacks
because this reader does not form a baseline-sharing group.

``start`` is the border-box offset from the area's start edge toward its
end edge. The area size already includes gutters between the tracks it
spans. Percentages are not resolved here.
"""

from __future__ import annotations

_EPS = 1e-9
_AUTO = "auto"
_NONE = "none"
_AXES = frozenset({"inline", "block"})
_DIRECTIONS = frozenset({"ltr", "rtl"})
_MODES = frozenset({"horizontal-tb", "vertical-rl", "vertical-lr"})
_PLAIN = frozenset({"auto", "normal", "stretch"})
_BASELINES = frozenset({"baseline", "first baseline", "last baseline"})
_PLACED = {
    "center": "center",
    "start": "start",
    "end": "end",
    "self-start": "self-start",
    "self-end": "self-end",
    "flow-start": "start",
    "flow-end": "end",
    "flex-start": "start",
    "flex-end": "end",
    "left": "left",
    "right": "right",
    "stretch": "start",
}
_OPPOSITE = {"left": "right", "right": "left", "top": "bottom", "bottom": "top"}


class _Invalid(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def align_grid_item(
    area: object,
    *,
    size: object = _AUTO,
    automatic: object = None,
    margin_start: object = 0,
    margin_end: object = 0,
    min_size: object = 0,
    max_size: object = _NONE,
    align: object = "normal",
    items: object = "normal",
    replaced: object = False,
    axis: object = "inline",
    container_direction: object = "ltr",
    item_direction: object = "ltr",
    container_writing_mode: object = "horizontal-tb",
    item_writing_mode: object = "horizontal-tb",
) -> dict[str, object]:
    """Return the used border box of one grid item inside ``area``.

    ``size`` ``auto`` uses ``automatic`` unless stretch fills the area.
    ``min_size`` and ``max_size`` are resolved lengths; ``max_size`` may be
    ``none``. When they disagree, the minimum wins. ``align`` ``auto`` uses
    ``items``. ``axis`` ``inline`` is ``justify-self`` and ``block`` is
    ``align-self``.
    """

    try:
        return _align(
            area,
            size,
            automatic,
            margin_start,
            margin_end,
            min_size,
            max_size,
            align,
            items,
            replaced,
            axis,
            container_direction,
            item_direction,
            container_writing_mode,
            item_writing_mode,
        )
    except _Invalid as exc:
        return {
            "outcome": "invalid",
            "start": None,
            "size": None,
            "margin_start": None,
            "margin_end": None,
            "reason": exc.reason,
        }


def _align(
    area: object,
    size: object,
    automatic: object,
    margin_start: object,
    margin_end: object,
    min_size: object,
    max_size: object,
    align: object,
    items: object,
    replaced: object,
    axis: object,
    container_direction: object,
    item_direction: object,
    container_writing_mode: object,
    item_writing_mode: object,
) -> dict[str, object]:
    container = _nonneg(area, "area")
    floor, ceiling = _bounds(min_size, max_size)
    chosen_axis = _choice(axis, _AXES, "axis")
    container_mode = _choice(container_writing_mode, _MODES, "container_writing_mode")
    item_mode = _choice(item_writing_mode, _MODES, "item_writing_mode")
    container_dir = _choice(container_direction, _DIRECTIONS, "container_direction")
    item_dir = _choice(item_direction, _DIRECTIONS, "item_direction")
    if not isinstance(replaced, bool):
        raise _Invalid("replaced is invalid")
    overflow, keyword = _alignment(align, items, chosen_axis)
    if keyword == "normal":
        keyword = "start" if replaced else "stretch"
    elif keyword in _BASELINES:
        overflow = "safe"
        keyword = "self-end" if keyword == "last baseline" else "self-start"
    start_auto = _is_auto(margin_start)
    end_auto = _is_auto(margin_end)
    start_margin = 0.0 if start_auto else _signed(margin_start, "margin_start")
    end_margin = 0.0 if end_auto else _signed(margin_end, "margin_end")
    logical = _logical_side(
        keyword,
        chosen_axis,
        container_mode,
        container_dir,
        item_mode,
        item_dir,
    )
    if keyword == "stretch" and _is_auto(size) and not start_auto and not end_auto:
        border = _clamp(container - start_margin - end_margin, floor, ceiling)
        used_start, used_end = start_margin, end_margin
        placed = "start"
        filled = abs(border + used_start + used_end - container) <= _EPS
        mode = "stretch" if filled else "start"
    else:
        border = _clamp(_border(size, automatic), floor, ceiling)
        if start_auto or end_auto:
            free = container - border - start_margin - end_margin
            if free > _EPS:
                slots = int(start_auto) + int(end_auto)
                share = free / slots
                used_start = share if start_auto else start_margin
                used_end = share if end_auto else end_margin
                return _result(used_start, border, used_start, used_end, "auto-margin")
            used_start = 0.0 if start_auto else start_margin
            used_end = 0.0 if end_auto else end_margin
        else:
            used_start, used_end = start_margin, end_margin
        placed = logical
        mode = logical
    if overflow == "safe" and used_start + border + used_end > container + _EPS:
        placed = "start"
        mode = "start"
    origin = _origin(container, border, used_start, used_end, placed)
    return _result(origin + used_start, border, used_start, used_end, mode)


def _alignment(align: object, items: object, axis: str) -> tuple[str, str]:
    overflow, keyword = _parse(align, axis, "align")
    if keyword != _AUTO:
        return overflow, keyword
    overflow, keyword = _parse(items, axis, "items")
    if keyword == _AUTO:
        return "unsafe", "normal"
    return overflow, keyword


def _parse(value: object, axis: str, name: str) -> tuple[str, str]:
    if not isinstance(value, str) or not value.strip():
        raise _Invalid(f"{name} is invalid")
    tokens = value.lower().split()
    if len(tokens) > 2:
        raise _Invalid(f"{name} is invalid")
    overflow = "unsafe"
    explicit_overflow = False
    if tokens[0] in {"safe", "unsafe"}:
        if len(tokens) == 1:
            raise _Invalid(f"{name} is invalid")
        overflow = tokens[0]
        explicit_overflow = True
        tokens = tokens[1:]
    keyword = " ".join(tokens)
    if explicit_overflow and (keyword in _PLAIN or keyword in _BASELINES):
        raise _Invalid(f"{name} is invalid")
    if keyword in _PLAIN or keyword in _BASELINES or keyword in _PLACED:
        if keyword in {"left", "right"} and axis == "block":
            raise _Invalid(f"{name} is invalid")
        return overflow, keyword
    raise _Invalid(f"{name} is invalid")


def _logical_side(
    keyword: str,
    axis: str,
    container_mode: str,
    container_direction: str,
    item_mode: str,
    item_direction: str,
) -> str:
    if keyword in {"left", "right"}:
        if not _horizontal(axis, container_mode):
            return "start"
        physical = keyword
    elif keyword == "self-start":
        physical = _subject_start(axis, container_mode, item_mode, item_direction)
    elif keyword == "self-end":
        physical = _OPPOSITE[_subject_start(axis, container_mode, item_mode, item_direction)]
    else:
        return _PLACED[keyword]
    start, end = _axis_edges(axis, container_mode, container_direction)
    if physical == start:
        return "start"
    if physical == end:
        return "end"
    raise _Invalid("align is invalid")


def _subject_start(axis: str, container_mode: str, item_mode: str, item_direction: str) -> str:
    horizontal = _horizontal(axis, container_mode)
    if horizontal == (item_mode == "horizontal-tb"):
        return _inline_start(item_mode, item_direction)
    return _block_start(item_mode)


def _horizontal(axis: str, mode: str) -> bool:
    start, _end = _axis_edges(axis, mode, "ltr")
    return start in {"left", "right"}


def _axis_edges(axis: str, mode: str, direction: str) -> tuple[str, str]:
    start = _inline_start(mode, direction) if axis == "inline" else _block_start(mode)
    return start, _OPPOSITE[start]


def _inline_start(mode: str, direction: str) -> str:
    if mode == "horizontal-tb":
        return "left" if direction == "ltr" else "right"
    return "top" if direction == "ltr" else "bottom"


def _block_start(mode: str) -> str:
    if mode == "horizontal-tb":
        return "top"
    if mode == "vertical-rl":
        return "right"
    return "left"


def _origin(area: float, border: float, margin_start: float, margin_end: float, placed: str) -> float:
    free = area - (margin_start + border + margin_end)
    if placed == "start":
        return 0.0
    if placed == "end":
        return free
    if placed == "center":
        return free / 2.0
    raise _Invalid("align is invalid")


def _border(size: object, automatic: object) -> float:
    if _is_auto(size):
        if automatic is None:
            raise _Invalid("automatic is invalid")
        return _nonneg(automatic, "automatic")
    return _nonneg(size, "size")


def _bounds(min_size: object, max_size: object) -> tuple[float, float | None]:
    floor = _nonneg(min_size, "min_size")
    if isinstance(max_size, str) and max_size.lower() == _NONE:
        return floor, None
    ceiling = _nonneg(max_size, "max_size")
    if floor > ceiling:
        return floor, None
    return floor, ceiling


def _clamp(size: float, floor: float, ceiling: float | None) -> float:
    if size < floor:
        size = floor
    if ceiling is not None and size > ceiling:
        size = ceiling
    return size


def _result(
    start: float,
    size: float,
    margin_start: float,
    margin_end: float,
    used: str,
) -> dict[str, object]:
    return {
        "outcome": "aligned",
        "start": _number(start),
        "size": _number(size),
        "margin_start": _number(margin_start),
        "margin_end": _number(margin_end),
        "used": used,
    }


def _is_auto(value: object) -> bool:
    return isinstance(value, str) and value.lower() == _AUTO


def _choice(value: object, allowed: frozenset[str], name: str) -> str:
    if not isinstance(value, str) or value.lower() not in allowed:
        raise _Invalid(f"{name} is invalid")
    return value.lower()


def _nonneg(value: object, name: str) -> float:
    number = _signed(value, name)
    if number < 0:
        raise _Invalid(f"{name} is invalid")
    return number


def _signed(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _Invalid(f"{name} is invalid")
    number = float(value)
    if number != number or number in {float("inf"), float("-inf")}:
        raise _Invalid(f"{name} is invalid")
    return number


def _number(value: float) -> int | float:
    nearest = round(value)
    if abs(value - nearest) <= _EPS:
        return int(nearest)
    return value
