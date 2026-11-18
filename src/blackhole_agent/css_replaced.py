"""Used size of a replaced element in normal flow or as a float.

CSS 2.1 §10.3.2 and §10.6.2 resolve a replaced content box from its intrinsic
width, height, and ratio. §10.3.4 then solves a block's horizontal margins.
§10.3.6 and §10.3.10 keep automatic inline, inline-block, and float margins
at zero. When both axes are automatic and a ratio exists, §10.4 resolves
min and max violations with the ratio table. A specified axis does not use
that table: the definite axis wins, and a min or max on the automatic axis
may break the ratio. This is not the non-replaced block or absolute solver.
"""

from __future__ import annotations

import math

from blackhole_agent.css_block_width import used_block_width

_AUTO = "auto"
_NONE = "none"
_LAYOUTS = frozenset({"inline", "block", "inline-block", "float"})
_FALLBACK_WIDTH = 300.0
_FALLBACK_HEIGHT = 150.0


class _Invalid(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def used_replaced_size(
    containing_width: object,
    *,
    containing_height: object = _AUTO,
    width: object = _AUTO,
    height: object = _AUTO,
    min_width: object = _AUTO,
    max_width: object = _NONE,
    min_height: object = _AUTO,
    max_height: object = _NONE,
    margin_left: object = 0,
    margin_right: object = 0,
    margin_top: object = 0,
    margin_bottom: object = 0,
    padding_left: object = 0,
    padding_right: object = 0,
    border_left: object = 0,
    border_right: object = 0,
    intrinsic_width: object = None,
    intrinsic_height: object = None,
    intrinsic_ratio: object = None,
    device_width: object = None,
    layout: object = "inline",
    direction: object = "ltr",
) -> dict[str, object]:
    """Return the used content size and margins of one replaced box.

    Lengths are CSS pixels or percentages. ``containing_width`` is definite.
    ``containing_height`` may be ``auto``; a percentage height then becomes
    automatic, a percentage ``min-height`` becomes zero, and a percentage
    ``max-height`` becomes ``none``. ``intrinsic_width`` and
    ``intrinsic_height`` are absent when ``None``. ``intrinsic_ratio`` is
    width divided by height. ``device_width`` selects the 300 by 150 fallback
    when it is wide enough, and a narrower 2:1 rectangle when it is not.
    ``layout`` is ``inline``, ``block``, ``inline-block``, or ``float``.
    """

    try:
        cb_width = _containing_width(containing_width)
        cb_height = _containing_height(containing_height)
        box = _keyword(layout, _LAYOUTS, "layout")
        flow = _keyword(direction, {"ltr", "rtl"}, "direction")
        specified_width = _axis(width, "width", cb_width)
        specified_height = _axis(height, "height", cb_height)
        minimum_width = _min_axis(min_width, "min-width", cb_width)
        maximum_width = _max_axis(max_width, "max-width", cb_width)
        minimum_height = _min_axis(min_height, "min-height", cb_height, percent_auto_is_zero=True)
        maximum_height = _max_axis(max_height, "max-height", cb_height, percent_auto_is_none=True)
        intrinsic_w = _optional_length(intrinsic_width, "intrinsic width")
        intrinsic_h = _optional_length(intrinsic_height, "intrinsic height")
        ratio = _optional_ratio(intrinsic_ratio)
        device = _optional_length(device_width, "device width")
        padding = (
            _resolve_box_edge(padding_left, "padding-left", cb_width),
            _resolve_box_edge(padding_right, "padding-right", cb_width),
        )
        border = (
            _px_only(border_left, "border-left"),
            _px_only(border_right, "border-right"),
        )
        vertical_margins = (
            _resolve_margin(margin_top, "margin-top", cb_width),
            _resolve_margin(margin_bottom, "margin-bottom", cb_width),
        )
        horizontal_margins = (
            _resolve_margin(margin_left, "margin-left", cb_width),
            _resolve_margin(margin_right, "margin-right", cb_width),
        )
    except _Invalid as exc:
        return _invalid(exc.reason)

    usable_ratio = ratio
    if usable_ratio is None and intrinsic_w is not None and intrinsic_h is not None and intrinsic_h > 0:
        usable_ratio = intrinsic_w / intrinsic_h
    available = max(
        0.0,
        cb_width - horizontal_margins[0] - horizontal_margins[1] - padding[0] - padding[1] - border[0] - border[1],
    )
    content_width, content_height = _content_size(
        specified_width,
        specified_height,
        minimum_width,
        maximum_width,
        minimum_height,
        maximum_height,
        intrinsic_w,
        intrinsic_h,
        usable_ratio,
        available,
        device,
    )
    if box == "block":
        solved = used_block_width(
            cb_width,
            width=content_width,
            margin_left=margin_left,
            margin_right=margin_right,
            padding_left=padding_left,
            padding_right=padding_right,
            border_left=border_left,
            border_right=border_right,
            box_sizing="content-box",
            min_width=_AUTO,
            max_width=_NONE,
            direction=flow,
        )
        if solved.get("outcome") != "sized":
            return _invalid(str(solved.get("reason") or "margin"))
        left = solved["margin_left"]
        right = solved["margin_right"]
    else:
        left = _number(horizontal_margins[0])
        right = _number(horizontal_margins[1])
    return {
        "outcome": "sized",
        "reason": "",
        "width": _number(content_width),
        "height": _number(content_height),
        "margin_left": left,
        "margin_right": right,
        "margin_top": _number(vertical_margins[0]),
        "margin_bottom": _number(vertical_margins[1]),
        "layout": box,
    }


def _content_size(
    specified_width: float | None,
    specified_height: float | None,
    minimum_width: float,
    maximum_width: float | None,
    minimum_height: float,
    maximum_height: float | None,
    intrinsic_w: float | None,
    intrinsic_h: float | None,
    ratio: float | None,
    available: float,
    device: float | None,
) -> tuple[float, float]:
    width_auto = specified_width is None
    height_auto = specified_height is None
    if width_auto and height_auto and ratio is not None:
        tentative_w, tentative_h = _automatic_pair(intrinsic_w, intrinsic_h, ratio, available)
        if tentative_w > 0 and tentative_h > 0:
            return _ratio_table(
                tentative_w,
                tentative_h,
                minimum_width,
                maximum_width,
                minimum_height,
                maximum_height,
            )
        return (
            _clamp(tentative_w, minimum_width, maximum_width),
            _clamp(tentative_h, minimum_height, maximum_height),
        )

    if not width_auto:
        width = specified_width
    elif height_auto and intrinsic_w is not None:
        width = intrinsic_w
    elif height_auto and intrinsic_w is None and intrinsic_h is not None and ratio is not None:
        width = intrinsic_h * ratio
    elif (not height_auto) and ratio is not None:
        width = specified_height * ratio
    elif intrinsic_w is not None:
        width = intrinsic_w
    else:
        width = _fallback_width(device)
    width = _clamp(width, minimum_width, maximum_width)

    if not height_auto:
        height = specified_height
    elif width_auto and intrinsic_h is not None:
        height = intrinsic_h
    elif ratio is not None:
        height = width / ratio
    elif intrinsic_h is not None:
        height = intrinsic_h
    else:
        height = _fallback_height(device)
    return width, _clamp(height, minimum_height, maximum_height)


def _automatic_pair(
    intrinsic_w: float | None,
    intrinsic_h: float | None,
    ratio: float,
    available: float,
) -> tuple[float, float]:
    if intrinsic_w is not None:
        width = intrinsic_w
    elif intrinsic_h is not None:
        width = intrinsic_h * ratio
    else:
        width = available
    if intrinsic_h is not None:
        height = intrinsic_h
    elif width > 0:
        height = width / ratio
    else:
        height = 0.0
    return width, height


def _ratio_table(
    width: float,
    height: float,
    minimum_width: float,
    maximum_width: float | None,
    minimum_height: float,
    maximum_height: float | None,
) -> tuple[float, float]:
    if maximum_width is not None:
        maximum_width = max(minimum_width, maximum_width)
    if maximum_height is not None:
        maximum_height = max(minimum_height, maximum_height)
    wide = maximum_width is not None and width > maximum_width
    narrow = width < minimum_width
    tall = maximum_height is not None and height > maximum_height
    short = height < minimum_height
    if wide and tall:
        if maximum_width / width <= maximum_height / height:
            return maximum_width, max(minimum_height, maximum_width * height / width)
        return max(minimum_width, maximum_height * width / height), maximum_height
    if narrow and short:
        if minimum_width / width <= minimum_height / height:
            return _at_most(minimum_height * width / height, maximum_width), minimum_height
        return minimum_width, _at_most(minimum_width * height / width, maximum_height)
    if narrow and tall:
        return minimum_width, maximum_height
    if wide and short:
        return maximum_width, minimum_height
    if wide:
        return maximum_width, max(maximum_width * height / width, minimum_height)
    if narrow:
        return minimum_width, _at_most(minimum_width * height / width, maximum_height)
    if tall:
        return max(maximum_height * width / height, minimum_width), maximum_height
    if short:
        return _at_most(minimum_height * width / height, maximum_width), minimum_height
    return width, height


def _fallback_width(device: float | None) -> float:
    if device is None or device >= _FALLBACK_WIDTH:
        return _FALLBACK_WIDTH
    return device


def _fallback_height(device: float | None) -> float:
    if device is None:
        return _FALLBACK_HEIGHT
    return min(_FALLBACK_HEIGHT, device / 2.0)


def _clamp(value: float, low: float, high: float | None) -> float:
    if high is not None and value > high:
        value = high
    if value < low:
        value = low
    return value


def _at_most(value: float, limit: float | None) -> float:
    if limit is None:
        return value
    return min(value, limit)


def _invalid(reason: str) -> dict[str, object]:
    return {
        "outcome": "invalid",
        "reason": reason,
        "width": None,
        "height": None,
        "margin_left": None,
        "margin_right": None,
        "margin_top": None,
        "margin_bottom": None,
        "layout": None,
    }


def _containing_width(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _Invalid("containing width must be a non-negative length")
    width = float(value)
    if not math.isfinite(width) or width < 0:
        raise _Invalid("containing width must be a non-negative length")
    return width


def _containing_height(value: object) -> float | None:
    if isinstance(value, str) and value.strip().lower() == _AUTO:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise _Invalid("containing height is invalid")
    kind, number = _size(value, name="containing height")
    if kind != "px":
        raise _Invalid("containing height is invalid")
    return number


def _keyword(value: object, allowed: set[str] | frozenset[str], name: str) -> str:
    if not isinstance(value, str):
        raise _Invalid(f"{name} is invalid")
    token = value.strip().lower()
    if token not in allowed:
        raise _Invalid(f"{name} is invalid")
    return token


def _size(value: object, *, allow_auto: bool = False, allow_none: bool = False, name: str) -> tuple[str, float]:
    if isinstance(value, bool):
        raise _Invalid(f"{name} is invalid")
    if isinstance(value, (int, float)):
        number = float(value)
        if not math.isfinite(number) or number < 0:
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
        if not math.isfinite(number) or number < 0:
            raise _Invalid(f"{name} cannot be negative")
        return ("pct", number)
    if text.endswith("px"):
        try:
            number = float(text[:-2])
        except ValueError as exc:
            raise _Invalid(f"{name} is invalid") from exc
        if not math.isfinite(number) or number < 0:
            raise _Invalid(f"{name} cannot be negative")
        return ("px", number)
    raise _Invalid(f"{name} is invalid")


def _axis(value: object, name: str, containing: float | None) -> float | None:
    kind, number = _size(value, allow_auto=True, name=name)
    if kind == _AUTO:
        return None
    if kind == "pct":
        if containing is None:
            return None
        return containing * number / 100.0
    return number


def _min_axis(
    value: object,
    name: str,
    containing: float | None,
    *,
    percent_auto_is_zero: bool = False,
) -> float:
    kind, number = _size(value, allow_auto=True, name=name)
    if kind == _AUTO:
        return 0.0
    if kind == "pct":
        if containing is None and percent_auto_is_zero:
            return 0.0
        if containing is None:
            raise _Invalid(f"{name} is invalid")
        return containing * number / 100.0
    return number


def _max_axis(
    value: object,
    name: str,
    containing: float | None,
    *,
    percent_auto_is_none: bool = False,
) -> float | None:
    kind, number = _size(value, allow_none=True, name=name)
    if kind == _NONE:
        return None
    if kind == "pct":
        if containing is None and percent_auto_is_none:
            return None
        if containing is None:
            raise _Invalid(f"{name} is invalid")
        return containing * number / 100.0
    return number


def _optional_length(value: object, name: str) -> float | None:
    if value is None:
        return None
    kind, number = _size(value, name=name)
    if kind != "px":
        raise _Invalid(f"{name} is invalid")
    return number


def _optional_ratio(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _Invalid("intrinsic ratio is invalid")
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise _Invalid("intrinsic ratio must be positive")
    return number


def _resolve_box_edge(value: object, name: str, containing_width: float) -> float:
    kind, number = _size(value, name=name)
    if kind == "pct":
        return containing_width * number / 100.0
    return number


def _px_only(value: object, name: str) -> float:
    kind, number = _size(value, name=name)
    if kind != "px":
        raise _Invalid(f"{name} must be a length")
    return number


def _resolve_margin(value: object, name: str, containing_width: float) -> float:
    if isinstance(value, str) and value.strip().lower() == _AUTO:
        return 0.0
    if isinstance(value, bool):
        raise _Invalid(f"{name} is invalid")
    if isinstance(value, (int, float)):
        number = float(value)
        if not math.isfinite(number):
            raise _Invalid(f"{name} is invalid")
        return number
    if not isinstance(value, str):
        raise _Invalid(f"{name} is invalid")
    text = value.strip().lower()
    if text.endswith("%"):
        try:
            number = float(text[:-1])
        except ValueError as exc:
            raise _Invalid(f"{name} is invalid") from exc
        if not math.isfinite(number):
            raise _Invalid(f"{name} is invalid")
        return containing_width * number / 100.0
    if text.endswith("px"):
        try:
            number = float(text[:-2])
        except ValueError as exc:
            raise _Invalid(f"{name} is invalid") from exc
        if not math.isfinite(number):
            raise _Invalid(f"{name} is invalid")
        return number
    raise _Invalid(f"{name} is invalid")


def _number(value: float) -> int | float:
    nearest = round(value)
    if abs(value - nearest) <= 1e-9:
        return int(nearest)
    return value
