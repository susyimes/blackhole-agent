"""Used width of a non-replaced block box in normal flow.

CSS2.1 §10.3.3 makes the margin box match the containing block. A fixed
size is a content-box or border-box length (css-sizing-3). The content box
never goes negative: a border-box smaller than its padding and border grows
to that chrome, and an auto width floors at zero instead of pulling a
margin negative. min-width and max-width are sizes in the same box and
restart the solution. This is not a float, a flex item, or a replaced box.
"""

from __future__ import annotations

_AUTO = "auto"
_NONE = "none"
_CONTENT = "content-box"
_BORDER = "border-box"


class _Invalid(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def used_block_width(
    containing_block: object,
    *,
    width: object = _AUTO,
    margin_left: object = 0,
    margin_right: object = 0,
    padding_left: object = 0,
    padding_right: object = 0,
    border_left: object = 0,
    border_right: object = 0,
    box_sizing: object = _CONTENT,
    min_width: object = _AUTO,
    max_width: object = _NONE,
    direction: object = "ltr",
) -> dict[str, object]:
    """Solve content width and the two horizontal margins.

    Numbers and ``px`` lengths are pixels. A percentage resolves against
    the containing block. ``margin_left`` and ``margin_right`` accept
    ``auto``. ``width`` accepts ``auto``. ``min_width`` accepts ``auto``
    (computed as zero). ``max_width`` accepts ``none``. ``box_sizing`` is
    ``content-box`` or ``border-box``. ``direction`` is ``ltr`` or ``rtl``
    and chooses which margin gives way when the box is over-constrained.
    """

    try:
        cb = _containing_block(containing_block)
        sizing = _keyword(box_sizing, {_CONTENT, _BORDER}, "box-sizing")
        flow = _keyword(direction, {"ltr", "rtl"}, "direction")
        specified = _size(width, allow_auto=True, name="width")
        minimum = _size(min_width, allow_auto=True, allow_negative=True, name="min-width")
        maximum = _size(max_width, allow_auto=False, allow_none=True, allow_negative=True, name="max-width")
        margins = (
            _size(margin_left, allow_auto=True, allow_negative=True, name="margin-left"),
            _size(margin_right, allow_auto=True, allow_negative=True, name="margin-right"),
        )
        padding = (
            _size(padding_left, name="padding-left"),
            _size(padding_right, name="padding-right"),
        )
        border = (
            _px_only(border_left, "border-left"),
            _px_only(border_right, "border-right"),
        )
    except _Invalid as exc:
        return _invalid(exc.reason)

    padding_px = (_resolve(padding[0], cb), _resolve(padding[1], cb))
    chrome = padding_px[0] + padding_px[1] + border[0] + border[1]
    # auto min-width computes to 0; a negative min or max computes to 0.
    min_limit = 0.0 if minimum[0] == _AUTO else max(0.0, _resolve(minimum, cb))
    max_limit = None if maximum[0] == _NONE else max(0.0, _resolve(maximum, cb))
    width_token = _resolve(specified, cb) if specified[0] != _AUTO else None

    content, left, right = _apply_limits(
        cb,
        width_token,
        margins,
        chrome,
        sizing,
        flow,
        min_limit,
        max_limit,
    )
    border_box = content + chrome
    return {
        "outcome": "sized",
        "content": _number(content),
        "margin_left": _number(left),
        "margin_right": _number(right),
        "padding_left": _number(padding_px[0]),
        "padding_right": _number(padding_px[1]),
        "border_left": _number(border[0]),
        "border_right": _number(border[1]),
        "border_box": _number(border_box),
        "margin_box": _number(left + border_box + right),
        "containing_block": _number(cb),
    }


def _invalid(reason: str) -> dict[str, object]:
    return {
        "outcome": "invalid",
        "reason": reason,
        "content": None,
        "margin_left": None,
        "margin_right": None,
        "border_box": None,
        "margin_box": None,
    }


def _containing_block(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _Invalid("containing block must be a non-negative length")
    width = float(value)
    if width < 0:
        raise _Invalid("containing block must be a non-negative length")
    return width


def _keyword(value: object, allowed: set[str], name: str) -> str:
    if not isinstance(value, str):
        raise _Invalid(f"{name} is invalid")
    token = value.strip().lower()
    if token not in allowed:
        raise _Invalid(f"{name} is invalid")
    return token


def _size(
    value: object,
    *,
    allow_auto: bool = False,
    allow_none: bool = False,
    allow_negative: bool = False,
    name: str,
) -> tuple[str, float]:
    if isinstance(value, bool):
        raise _Invalid(f"{name} is invalid")
    if isinstance(value, (int, float)):
        number = float(value)
        if number < 0 and not allow_negative:
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
        if number < 0 and not allow_negative:
            raise _Invalid(f"{name} cannot be negative")
        return ("pct", number)
    if text.endswith("px"):
        try:
            number = float(text[:-2])
        except ValueError as exc:
            raise _Invalid(f"{name} is invalid") from exc
        if number < 0 and not allow_negative:
            raise _Invalid(f"{name} cannot be negative")
        return ("px", number)
    raise _Invalid(f"{name} is invalid")


def _px_only(value: object, name: str) -> float:
    kind, number = _size(value, name=name)
    if kind != "px":
        raise _Invalid(f"{name} must be a length")
    return number


def _resolve(size: tuple[str, float], containing_block: float) -> float:
    kind, number = size
    if kind == "pct":
        return containing_block * number / 100.0
    return number


def _apply_limits(
    containing_block: float,
    specified: float | None,
    margins: tuple[tuple[str, float], tuple[str, float]],
    chrome: float,
    box_sizing: str,
    direction: str,
    min_limit: float,
    max_limit: float | None,
) -> tuple[float, float, float]:
    content, left, right = _solve(containing_block, specified, margins, chrome, box_sizing, direction)
    measured = _measured(content, chrome, box_sizing)
    if max_limit is not None and measured > max_limit:
        content, left, right = _solve(containing_block, max_limit, margins, chrome, box_sizing, direction)
        measured = _measured(content, chrome, box_sizing)
    if measured < min_limit:
        content, left, right = _solve(containing_block, min_limit, margins, chrome, box_sizing, direction)
    return content, left, right


def _measured(content: float, chrome: float, box_sizing: str) -> float:
    if box_sizing == _BORDER:
        return content + chrome
    return content


def _content_width(specified: float, chrome: float, box_sizing: str) -> float:
    if box_sizing == _BORDER:
        return max(0.0, specified - chrome)
    return specified


def _solve(
    containing_block: float,
    specified: float | None,
    margins: tuple[tuple[str, float], tuple[str, float]],
    chrome: float,
    box_sizing: str,
    direction: str,
) -> tuple[float, float, float]:
    left_auto = margins[0][0] == _AUTO
    right_auto = margins[1][0] == _AUTO
    left = 0.0 if left_auto else _resolve(margins[0], containing_block)
    right = 0.0 if right_auto else _resolve(margins[1], containing_block)
    if specified is None:
        # width:auto sets the other autos to zero, then floors the content.
        return max(0.0, containing_block - left - right - chrome), left, right

    content = _content_width(specified, chrome, box_sizing)
    fixed = content + chrome
    if not left_auto:
        fixed += left
    if not right_auto:
        fixed += right
    if fixed > containing_block:
        left_auto = False
        right_auto = False
    if left_auto and right_auto:
        leftover = containing_block - content - chrome
        left = leftover / 2.0
        right = leftover - left
        return content, left, right
    if left_auto:
        return content, containing_block - right - content - chrome, right
    if right_auto:
        return content, left, containing_block - left - content - chrome
    if direction == "rtl":
        left = containing_block - right - content - chrome
    else:
        right = containing_block - left - content - chrome
    return content, left, right


def _number(value: float) -> int | float:
    nearest = round(value)
    if abs(value - nearest) <= 1e-9:
        return int(nearest)
    return value
