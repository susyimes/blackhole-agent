"""Place one absolutely positioned non-replaced box.

CSS 2.1 §10.3.7 and §10.6.4 solve a different equation from a normal-flow
block. Both insets can be definite at once. An automatic size stretches
only then, and automatic margins become zero instead of sharing that
space. When the size is also definite, equal automatic margins share a
positive remainder; a negative horizontal remainder zeros the start margin
and gives the whole remainder to the end margin, while a negative vertical
remainder stays split. An over-constrained horizontal axis drops ``right``
when direction is ``ltr`` and drops ``left`` when direction is ``rtl``.
The vertical axis always drops ``bottom``.

Shrink-to-fit width is ``min(max(min-content, available), max-content)``.
``min-width`` and ``max-width`` are applied by solving that equation again,
so a maximum that loses a stretch moves the opposite inset. Percentage
padding and margins use the containing-block width, including the vertical
ones. Percentage ``top``, ``height``, and ``bottom`` use the
containing-block height, and an automatic height makes those percentages
automatic. This is not a float, a flex item, or a replaced box.
"""

from __future__ import annotations

import math

_AUTO = "auto"
_NONE = "none"
_CONTENT = "content-box"
_BORDER = "border-box"


class _Invalid(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def place_absolute(
    containing_width: object,
    *,
    containing_height: object = _AUTO,
    left: object = _AUTO,
    right: object = _AUTO,
    width: object = _AUTO,
    top: object = _AUTO,
    bottom: object = _AUTO,
    height: object = _AUTO,
    margin_left: object = 0,
    margin_right: object = 0,
    margin_top: object = 0,
    margin_bottom: object = 0,
    padding_left: object = 0,
    padding_right: object = 0,
    padding_top: object = 0,
    padding_bottom: object = 0,
    border_left: object = 0,
    border_right: object = 0,
    border_top: object = 0,
    border_bottom: object = 0,
    min_width: object = _AUTO,
    max_width: object = _NONE,
    min_height: object = _AUTO,
    max_height: object = _NONE,
    box_sizing: object = _CONTENT,
    direction: object = "ltr",
    static_left: object = 0,
    static_right: object = 0,
    static_top: object = 0,
    min_content: object = 0,
    max_content: object = 0,
    content_height: object = 0,
) -> dict[str, object]:
    """Return used insets, content size, and margins for one absolute box.

    Lengths are numbers or ``px``. Percentages of ``left``, ``right``, and
    ``width`` use ``containing_width``. Percentages of ``top``, ``bottom``,
    and ``height`` use ``containing_height``; when that height is ``auto``
    they become ``auto``. Padding and margin percentages use the width on
    both axes. ``min_content`` and ``max_content`` are the preferred minimum
    and preferred width for shrink-to-fit. ``content_height`` is the content
    height used when ``height`` is ``auto`` and the block is not stretched.
    ``static_left``, ``static_right``, and ``static_top`` are used offsets of
    the hypothetical margin edge. ``bottom`` is null when the containing
    height is automatic, because that inset cannot be solved.
    """

    try:
        cb_w = _length(containing_width, "containing-width", minimum=0)
        cb_h = _block_height(containing_height)
        sizing = _keyword(box_sizing, {_CONTENT, _BORDER}, "box-sizing")
        flow = _keyword(direction, {"ltr", "rtl"}, "direction")
        static = (
            _length(static_left, "static-left", allow_negative=True),
            _length(static_right, "static-right", allow_negative=True),
            _length(static_top, "static-top", allow_negative=True),
        )
        intrinsic = (
            _length(min_content, "min-content", minimum=0),
            _length(max_content, "max-content", minimum=0),
        )
        if intrinsic[1] < intrinsic[0]:
            raise _Invalid("max-content is smaller than min-content")
        content_h = _length(content_height, "content-height", minimum=0)
        horizontal = _parse_axis(
            left,
            width,
            right,
            margin_left,
            margin_right,
            "left",
            "width",
            "right",
            "margin-left",
            "margin-right",
            cb_w,
            cb_w,
        )
        vertical = _parse_axis(
            top,
            height,
            bottom,
            margin_top,
            margin_bottom,
            "top",
            "height",
            "bottom",
            "margin-top",
            "margin-bottom",
            cb_h,
            cb_w,
        )
        padding = (
            _resolve(_size(padding_left, name="padding-left"), cb_w),
            _resolve(_size(padding_right, name="padding-right"), cb_w),
            _resolve(_size(padding_top, name="padding-top"), cb_w),
            _resolve(_size(padding_bottom, name="padding-bottom"), cb_w),
        )
        border = (
            _length(border_left, "border-left", minimum=0),
            _length(border_right, "border-right", minimum=0),
            _length(border_top, "border-top", minimum=0),
            _length(border_bottom, "border-bottom", minimum=0),
        )
        min_w, max_w = _limits(min_width, max_width, cb_w, "min-width", "max-width")
        min_h, max_h = _limits(min_height, max_height, cb_h, "min-height", "max-height")
    except _Invalid as exc:
        return _invalid(exc.reason)

    h_chrome = padding[0] + padding[1] + border[0] + border[1]
    v_chrome = padding[2] + padding[3] + border[2] + border[3]
    h_size = None if horizontal[1] is None else _content_size(horizontal[1], h_chrome, sizing)
    v_size = None if vertical[1] is None else _content_size(vertical[1], v_chrome, sizing)

    def solve_h(forced: float | None) -> tuple[float, float, float, float, float]:
        start, size, end, margin_start, margin_end = _axis(
            cb_w,
            horizontal[0],
            h_size if forced is None else forced,
            horizontal[2],
            horizontal[3],
            horizontal[4],
            h_chrome,
            drop="end" if flow == "ltr" else "start",
            static_start=static[0],
            static_end=static[1],
            content_size=0.0,
            shrink=intrinsic,
            negative_margins="zero_start",
        )
        if end is None:
            raise _Invalid("right inset is unsolved")
        return start, size, end, margin_start, margin_end

    def solve_v(forced: float | None) -> tuple[float, float, float | None, float, float]:
        return _axis(
            cb_h,
            vertical[0],
            v_size if forced is None else forced,
            vertical[2],
            vertical[3],
            vertical[4],
            v_chrome,
            drop="end",
            static_start=static[2],
            static_end=0.0,
            content_size=content_h,
            shrink=None,
            negative_margins="split",
        )

    try:
        x0, width_px, x1, ml, mr = _limited(solve_h, min_w, max_w, h_chrome, sizing)
        y0, height_px, y1, mt, mb = _limited(solve_v, min_h, max_h, v_chrome, sizing)
    except _Invalid as exc:
        return _invalid(exc.reason)

    border_w = width_px + h_chrome
    border_h = height_px + v_chrome
    return {
        "outcome": "placed",
        "left": _number(x0),
        "right": _number(x1),
        "width": _number(width_px),
        "top": _number(y0),
        "bottom": None if y1 is None else _number(y1),
        "height": _number(height_px),
        "margin_left": _number(ml),
        "margin_right": _number(mr),
        "margin_top": _number(mt),
        "margin_bottom": _number(mb),
        "padding_left": _number(padding[0]),
        "padding_right": _number(padding[1]),
        "padding_top": _number(padding[2]),
        "padding_bottom": _number(padding[3]),
        "border_left": _number(border[0]),
        "border_right": _number(border[1]),
        "border_top": _number(border[2]),
        "border_bottom": _number(border[3]),
        "x": _number(x0 + ml),
        "y": _number(y0 + mt),
        "border_box_width": _number(border_w),
        "border_box_height": _number(border_h),
        "containing_width": _number(cb_w),
        "containing_height": None if cb_h is None else _number(cb_h),
    }


def _invalid(reason: str) -> dict[str, object]:
    return {
        "outcome": "invalid",
        "reason": reason,
        "left": None,
        "right": None,
        "width": None,
        "top": None,
        "bottom": None,
        "height": None,
    }


def _parse_axis(
    start: object,
    size: object,
    end: object,
    margin_start: object,
    margin_end: object,
    start_name: str,
    size_name: str,
    end_name: str,
    margin_start_name: str,
    margin_end_name: str,
    containing: float | None,
    margin_basis: float,
) -> tuple[float | None, float | None, float | None, float | None, float | None]:
    return (
        _inset(start, containing, start_name),
        _span(size, containing, size_name),
        _inset(end, containing, end_name),
        _margin(margin_start, margin_basis, margin_start_name),
        _margin(margin_end, margin_basis, margin_end_name),
    )


def _inset(value: object, containing: float | None, name: str) -> float | None:
    token = _size(value, allow_auto=True, allow_negative=True, name=name)
    return _against(token, containing, name)


def _span(value: object, containing: float | None, name: str) -> float | None:
    token = _size(value, allow_auto=True, name=name)
    return _against(token, containing, name)


def _against(token: tuple[str, float], containing: float | None, name: str) -> float | None:
    if token[0] == _AUTO:
        return None
    if token[0] == "px":
        return token[1]
    if containing is None:
        return None
    return _resolve(token, containing)


def _margin(value: object, containing: float | None, name: str) -> float | None:
    token = _size(value, allow_auto=True, allow_negative=True, name=name)
    if token[0] == _AUTO:
        return None
    # CSS 2.1 §8.3 resolves every margin percentage against the width.
    if containing is None:
        raise _Invalid(f"{name} needs a containing width")
    return _resolve(token, containing)


def _limits(
    minimum: object,
    maximum: object,
    containing: float | None,
    min_name: str,
    max_name: str,
) -> tuple[float, float | None]:
    low = _size(minimum, allow_auto=True, allow_negative=True, name=min_name)
    high = _size(maximum, allow_none=True, allow_negative=True, name=max_name)
    return _floor_limit(low, containing, missing=0.0), _ceil_limit(high, containing)


def _floor_limit(token: tuple[str, float], containing: float | None, *, missing: float) -> float:
    if token[0] == _AUTO:
        return 0.0
    if token[0] == "px":
        return max(0.0, token[1])
    if containing is None:
        return missing
    return max(0.0, _resolve(token, containing))


def _ceil_limit(token: tuple[str, float], containing: float | None) -> float | None:
    if token[0] == _NONE:
        return None
    if token[0] == "px":
        return max(0.0, token[1])
    if containing is None:
        return None
    return max(0.0, _resolve(token, containing))


def _limited(solve, min_limit: float, max_limit: float | None, chrome: float, box_sizing: str):
    start, size, end, margin_start, margin_end = solve(None)
    measured = _measured(size, chrome, box_sizing)
    if max_limit is not None and measured > max_limit:
        start, size, end, margin_start, margin_end = solve(_content_size(max_limit, chrome, box_sizing))
        measured = _measured(size, chrome, box_sizing)
    if measured < min_limit:
        start, size, end, margin_start, margin_end = solve(_content_size(min_limit, chrome, box_sizing))
    return start, size, end, margin_start, margin_end


def _axis(
    cb: float | None,
    start: float | None,
    size: float | None,
    end: float | None,
    margin_start: float | None,
    margin_end: float | None,
    chrome: float,
    *,
    drop: str,
    static_start: float,
    static_end: float,
    content_size: float,
    shrink: tuple[float, float] | None,
    negative_margins: str,
) -> tuple[float, float, float | None, float, float]:
    if cb is None:
        return _indefinite(start, size, margin_start, margin_end, static_start, content_size)

    if start is None and size is None and end is None:
        margin_start = 0.0 if margin_start is None else margin_start
        margin_end = 0.0 if margin_end is None else margin_end
        if drop == "end":
            start = static_start
        else:
            end = static_end

    if start is not None and size is not None and end is not None:
        return _overconstrained(
            cb, start, size, end, margin_start, margin_end, chrome, drop, negative_margins
        )

    margin_start = 0.0 if margin_start is None else margin_start
    margin_end = 0.0 if margin_end is None else margin_end

    if start is None and size is None and end is not None:
        size = _automatic(cb, end, margin_start, margin_end, chrome, content_size, shrink)
        start = cb - end - size - chrome - margin_start - margin_end
    elif start is None and end is None and size is not None:
        if drop == "end":
            start = static_start
            end = cb - start - size - chrome - margin_start - margin_end
        else:
            end = static_end
            start = cb - end - size - chrome - margin_start - margin_end
    elif size is None and end is None and start is not None:
        size = _automatic(cb, start, margin_start, margin_end, chrome, content_size, shrink)
        end = cb - start - size - chrome - margin_start - margin_end
    elif start is None and size is not None and end is not None:
        start = cb - end - size - chrome - margin_start - margin_end
    elif size is None and start is not None and end is not None:
        size = cb - start - end - chrome - margin_start - margin_end
        if size < 0.0:
            size = 0.0
    elif end is None and start is not None and size is not None:
        end = cb - start - size - chrome - margin_start - margin_end
    else:
        raise _Invalid("inset equation is incomplete")
    return start, size, end, margin_start, margin_end


def _indefinite(
    start: float | None,
    size: float | None,
    margin_start: float | None,
    margin_end: float | None,
    static_start: float,
    content_size: float,
) -> tuple[float, float, None, float, float]:
    if margin_start is None:
        margin_start = 0.0
    if margin_end is None:
        margin_end = 0.0
    if size is None:
        size = content_size
    if start is None:
        start = static_start
    if size < 0.0:
        size = 0.0
    return start, size, None, margin_start, margin_end


def _overconstrained(
    cb: float,
    start: float,
    size: float,
    end: float,
    margin_start: float | None,
    margin_end: float | None,
    chrome: float,
    drop: str,
    negative_margins: str,
) -> tuple[float, float, float, float, float]:
    known = start + size + end + chrome
    if margin_start is not None:
        known += margin_start
    if margin_end is not None:
        known += margin_end
    leftover = cb - known
    if margin_start is None and margin_end is None:
        if leftover >= 0.0 or negative_margins == "split":
            margin_start = leftover / 2.0
            margin_end = leftover - margin_start
        elif drop == "end":
            margin_start = 0.0
            margin_end = leftover
        else:
            margin_end = 0.0
            margin_start = leftover
        return start, size, end, margin_start, margin_end
    if margin_start is None:
        return start, size, end, leftover, margin_end if margin_end is not None else 0.0
    if margin_end is None:
        return start, size, end, margin_start, leftover
    if drop == "start":
        start = cb - end - size - chrome - margin_start - margin_end
    else:
        end = cb - start - size - chrome - margin_start - margin_end
    return start, size, end, margin_start, margin_end


def _automatic(
    cb: float,
    fixed_inset: float,
    margin_start: float,
    margin_end: float,
    chrome: float,
    content_size: float,
    shrink: tuple[float, float] | None,
) -> float:
    if shrink is None:
        return content_size if content_size > 0.0 else 0.0
    available = cb - fixed_inset - margin_start - margin_end - chrome
    preferred_min, preferred = shrink
    return min(max(preferred_min, available), preferred)


def _content_size(specified: float, chrome: float, box_sizing: str) -> float:
    if box_sizing == _BORDER:
        return max(0.0, specified - chrome)
    return specified


def _measured(content: float, chrome: float, box_sizing: str) -> float:
    if box_sizing == _BORDER:
        return content + chrome
    return content


def _block_height(value: object) -> float | None:
    if isinstance(value, str) and value.strip().lower() == _AUTO:
        return None
    return _length(value, "containing-height", minimum=0)


def _keyword(value: object, allowed: set[str], name: str) -> str:
    if not isinstance(value, str):
        raise _Invalid(f"{name} is invalid")
    token = value.strip().lower()
    if token not in allowed:
        raise _Invalid(f"{name} is invalid")
    return token


def _length(value: object, name: str, *, minimum: float | None = None, allow_negative: bool = False) -> float:
    token = _size(value, allow_negative=allow_negative or minimum is None, name=name)
    if token[0] != "px":
        raise _Invalid(f"{name} must be a length")
    number = token[1]
    if minimum is not None and number < minimum:
        raise _Invalid(f"{name} cannot be negative")
    return number


def _size(
    value: object,
    *,
    allow_auto: bool = False,
    allow_none: bool = False,
    allow_negative: bool = False,
    name: str,
) -> tuple[str, float]:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise _Invalid(f"{name} is invalid")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        if not math.isfinite(number):
            raise _Invalid(f"{name} is invalid")
        if number < 0.0 and not allow_negative:
            raise _Invalid(f"{name} cannot be negative")
        return ("px", number)
    if not isinstance(value, str):
        raise _Invalid(f"{name} is invalid")
    text = value.strip().lower()
    if allow_auto and text == _AUTO:
        return (_AUTO, 0.0)
    if allow_none and text == _NONE:
        return (_NONE, 0.0)
    if text.endswith("%"):
        try:
            number = float(text[:-1])
        except ValueError as exc:
            raise _Invalid(f"{name} is invalid") from exc
        if not math.isfinite(number):
            raise _Invalid(f"{name} is invalid")
        if number < 0.0 and not allow_negative:
            raise _Invalid(f"{name} cannot be negative")
        return ("pct", number)
    if text.endswith("px"):
        try:
            number = float(text[:-2])
        except ValueError as exc:
            raise _Invalid(f"{name} is invalid") from exc
        if not math.isfinite(number):
            raise _Invalid(f"{name} is invalid")
        if number < 0.0 and not allow_negative:
            raise _Invalid(f"{name} cannot be negative")
        return ("px", number)
    raise _Invalid(f"{name} is invalid")


def _resolve(size: tuple[str, float], containing: float) -> float:
    kind, number = size
    if kind == "pct":
        return containing * number / 100.0
    return number


def _number(value: float) -> int | float:
    nearest = round(value)
    if abs(value - nearest) <= 1e-9:
        return int(nearest)
    return value
