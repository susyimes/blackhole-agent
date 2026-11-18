"""Content-based automatic minimum of one flex item.

CSS Flexbox §4.5 gives a main-axis ``min-width`` or ``min-height`` of ``auto``
a content-based floor when the item's overflow is not scrollable. A scrollable
main axis stays at zero. The caller passes lengths that are already definite:
this does not resolve percentages, measure text, or choose a flex base.

A non-replaced item uses the larger of the content suggestion and the
transferred size, when a preferred aspect ratio and a definite cross size
produce one. A replaced item uses the smaller of those two. A definite
preferred main size caps that result, and a definite maximum main size caps
it again. ``ratio`` is the main size divided by the cross size. A minimum
cross size that converts above the maximum cross size wins, matching the
used-value rule that the minimum wins when the two disagree.
"""

from __future__ import annotations

_AUTO = "auto"
_NONE = "none"


class _Invalid(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def automatic_flex_minimum(
    content: object,
    *,
    specified: object = _AUTO,
    maximum: object = _NONE,
    ratio: object = _NONE,
    cross: object = _AUTO,
    cross_minimum: object = _AUTO,
    cross_maximum: object = _NONE,
    replaced: object = False,
    scrollable: object = False,
) -> dict[str, object]:
    """Return the used automatic minimum on the main axis.

    ``content`` is the min-content main size. ``specified`` is the preferred
    main size, or ``auto`` when that size is not definite. ``maximum`` is the
    maximum main size, or ``none``. ``ratio`` is ``none`` or a positive
    main/cross ratio. ``cross`` is the preferred cross size, or ``auto``.
    ``cross_minimum`` and ``cross_maximum`` clamp that cross size and, through
    the ratio, the content suggestion. ``replaced`` selects the smaller
    suggestion. ``scrollable`` is true when the main axis is a scroll container.
    """

    try:
        return _definite(*_compute(
            content,
            specified=specified,
            maximum=maximum,
            ratio=ratio,
            cross=cross,
            cross_minimum=cross_minimum,
            cross_maximum=cross_maximum,
            replaced=replaced,
            scrollable=scrollable,
        ))
    except _Invalid as exc:
        return _invalid(exc.reason)


def _compute(
    content: object,
    *,
    specified: object,
    maximum: object,
    ratio: object,
    cross: object,
    cross_minimum: object,
    cross_maximum: object,
    replaced: object,
    scrollable: object,
) -> tuple[float, float | None, float | None, float | None]:
    content_size = _nonneg(content, "content")
    specified_size = _optional(specified, "specified", absent=_AUTO)
    maximum_size = _optional(maximum, "maximum", absent=_NONE)
    ratio_size = _positive_optional(ratio, "ratio")
    cross_size = _optional(cross, "cross", absent=_AUTO)
    cross_min = _optional(cross_minimum, "cross minimum", absent=_AUTO)
    cross_max = _optional(cross_maximum, "cross maximum", absent=_NONE)
    is_replaced = _flag(replaced, "replaced")
    if _flag(scrollable, "scrollable"):
        return 0.0, None, None, None

    content_suggestion = content_size
    if ratio_size is not None:
        low = None if cross_min is None else cross_min * ratio_size
        high = None if cross_max is None else cross_max * ratio_size
        content_suggestion = _clamp(content_size, low, high)

    transferred: float | None = None
    if ratio_size is not None and cross_size is not None:
        transferred = _clamp(cross_size, cross_min, cross_max) * ratio_size

    if is_replaced:
        size = content_suggestion if transferred is None else min(content_suggestion, transferred)
    else:
        size = content_suggestion if transferred is None else max(content_suggestion, transferred)
    if specified_size is not None:
        size = min(size, specified_size)
    if maximum_size is not None:
        size = min(size, maximum_size)
    if size < 0:
        size = 0.0
    return size, content_suggestion, specified_size, transferred


def _invalid(reason: str) -> dict[str, object]:
    return {
        "outcome": "invalid",
        "reason": reason,
        "minimum": None,
        "content_suggestion": None,
        "specified_suggestion": None,
        "transferred_suggestion": None,
    }


def _definite(
    minimum: float,
    content: float | None,
    specified: float | None,
    transferred: float | None,
) -> dict[str, object]:
    return {
        "outcome": "definite",
        "minimum": _number(minimum),
        "content_suggestion": None if content is None else _number(content),
        "specified_suggestion": None if specified is None else _number(specified),
        "transferred_suggestion": None if transferred is None else _number(transferred),
    }


def _clamp(value: float, low: float | None, high: float | None) -> float:
    if high is not None and value > high:
        value = high
    if low is not None and value < low:
        value = low
    return value


def _optional(value: object, name: str, *, absent: str) -> float | None:
    if isinstance(value, str) and " ".join(value.strip().lower().split()) == absent:
        return None
    return _nonneg(value, name)


def _positive_optional(value: object, name: str) -> float | None:
    if isinstance(value, str) and " ".join(value.strip().lower().split()) == _NONE:
        return None
    number = _nonneg(value, name)
    if number <= 0:
        raise _Invalid(f"{name} must be positive")
    return number


def _flag(value: object, name: str) -> bool:
    if not isinstance(value, bool):
        raise _Invalid(f"{name} is invalid")
    return value


def _nonneg(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _Invalid(f"{name} is invalid")
    number = float(value)
    if number != number or number in {float("inf"), float("-inf")} or number < 0:
        raise _Invalid(f"{name} is invalid")
    return number


def _number(value: float) -> int | float:
    nearest = round(value)
    if abs(value - nearest) <= 1e-9:
        return int(nearest)
    return value
