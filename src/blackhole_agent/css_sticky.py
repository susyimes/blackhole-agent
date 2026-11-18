"""Used sticky offset of one box on one axis.

CSS Positioned Layout Level 3 §3.4 insets a sticky box from the scrollport,
not from its containing block. The border box keeps the size it was laid out
with. A definite start inset only shifts that border edge toward the end, and
a definite end inset only shifts the opposite border edge toward the start.
The containing block stops a shift that would carry the border box outside
it. Nested sticky ancestors are not composed here: the caller passes the
border box, the scrollport, and the containing block in one coordinate space
whose positive direction is toward the end of the axis.

If both insets are ``auto``, the offset is zero. Otherwise an automatic inset
is a zero edge of the sticky view rectangle and does not itself shift the box.
When that rectangle is shorter than the border box, the end inset is reduced,
possibly below zero, until the rectangle matches the border box. The
block-start inset then still meets its edge. A scrollport of 300 with a
border box of 200 and a start inset of 20 leaves the end inset at 0, so the
view is 280. The same box in a scrollport of 100 reduces the end inset to
-120, so the view is 200.
"""

from __future__ import annotations

_AUTO = "auto"


class _Invalid(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def sticky_offset(
    border_start: object,
    border_size: object,
    port_size: object,
    containing_start: object,
    containing_end: object,
    *,
    scroll: object = 0,
    port_origin: object = 0,
    start: object = _AUTO,
    end: object = _AUTO,
) -> dict[str, object]:
    """Return the used sticky shift along one axis.

    ``border_start`` and ``border_size`` are the laid-out border box.
    ``port_size`` is the scrollport length. ``port_origin`` is the content
    coordinate of the scrollport's start edge at scroll zero, and ``scroll``
    moves that edge toward the end. ``start`` and ``end`` are definite
    insets or ``auto``. ``containing_start`` and ``containing_end`` bound
    the border box. The offset is added to ``border_start``.
    """

    try:
        return _resolved(*_compute(
            border_start,
            border_size,
            port_size,
            containing_start,
            containing_end,
            scroll=scroll,
            port_origin=port_origin,
            start=start,
            end=end,
        ))
    except _Invalid as exc:
        return _invalid(exc.reason)


def _compute(
    border_start: object,
    border_size: object,
    port_size: object,
    containing_start: object,
    containing_end: object,
    *,
    scroll: object,
    port_origin: object,
    start: object,
    end: object,
) -> tuple[float, float, float | None, float | None, float | None, bool, bool]:
    origin = _signed(border_start, "border start")
    size = _nonneg(border_size, "border size")
    port = _nonneg(port_size, "scrollport size")
    block_start = _signed(containing_start, "containing start")
    block_end = _signed(containing_end, "containing end")
    if block_end < block_start:
        raise _Invalid("containing end is before its start")
    scrolled = _signed(scroll, "scroll")
    port_start = _signed(port_origin, "scrollport origin")
    start_inset = _inset(start, "start inset")
    end_inset = _inset(end, "end inset")
    if start_inset is None and end_inset is None:
        return 0.0, origin, None, None, None, False, False

    view_start = 0.0 if start_inset is None else start_inset
    view_end = 0.0 if end_inset is None else end_inset
    view = port - view_start - view_end
    if view < size:
        view_end = port - view_start - size
        view = size

    offset = 0.0
    clip_start = port_start + scrolled
    if end_inset is not None:
        end_delta = min(0.0, (clip_start + port - view_end) - (origin + size))
        room = min(0.0, block_start - origin)
        if end_delta < room:
            end_delta = room
        offset += end_delta
    if start_inset is not None:
        start_delta = max(0.0, (clip_start + start_inset) - origin)
        room = max(0.0, block_end - (origin + size))
        if start_delta > room:
            start_delta = room
        offset += start_delta
    return (
        offset,
        origin + offset,
        view,
        view_start,
        view_end,
        start_inset is not None,
        end_inset is not None,
    )


def _resolved(
    offset: float,
    border: float,
    view: float | None,
    view_start: float | None,
    view_end: float | None,
    start_anchored: bool,
    end_anchored: bool,
) -> dict[str, object]:
    return {
        "outcome": "resolved",
        "offset": _number(offset),
        "border_start": _number(border),
        "sticky_view_size": None if view is None else _number(view),
        "effective_start_inset": None if view_start is None else _number(view_start),
        "effective_end_inset": None if view_end is None else _number(view_end),
        "start_anchored": start_anchored,
        "end_anchored": end_anchored,
    }


def _invalid(reason: str) -> dict[str, object]:
    return {
        "outcome": "invalid",
        "reason": reason,
        "offset": None,
        "border_start": None,
        "sticky_view_size": None,
        "effective_start_inset": None,
        "effective_end_inset": None,
        "start_anchored": False,
        "end_anchored": False,
    }


def _inset(value: object, name: str) -> float | None:
    if isinstance(value, str) and " ".join(value.strip().lower().split()) == _AUTO:
        return None
    return _signed(value, name)


def _signed(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _Invalid(f"{name} is invalid")
    number = float(value)
    if number != number or number in {float("inf"), float("-inf")}:
        raise _Invalid(f"{name} is invalid")
    return number


def _nonneg(value: object, name: str) -> float:
    number = _signed(value, name)
    if number < 0:
        raise _Invalid(f"{name} is invalid")
    return number


def _number(value: float) -> int | float:
    nearest = round(value)
    if abs(value - nearest) <= 1e-9:
        return int(nearest)
    return value
