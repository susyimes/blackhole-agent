"""Fit a replaced element's content object inside its content box.

CSS Images 3 sizes the concrete object with object-fit, then resolves
object-position the way CSS Backgrounds 3 resolves background-position.
The content box is an input. This does not compute the element's used
width or height, and it does not clip.

``fill`` uses the content box. ``contain`` and ``cover`` keep a positive
natural ratio; without one they use the content box. A zero content edge
collapses ``contain`` to zero, while ``cover`` still meets the other edge.
``none`` uses a natural width and height when they exist. A ratio with no
natural size is contained in the content box. ``scale-down`` uses whichever
of ``none`` and ``contain`` has the smaller area. A ratio is width divided
by height. A zero natural size has no ratio, and an explicit ratio beside
that zero is rejected.

A single keyword or length sets the other axis to center. Two values are
horizontal then vertical, except a keyword pair may be swapped. ``left
10px`` is therefore the left edge and a vertical length, not an inset from
the left. Three or four values are offsets inward from the named edges, and
a percentage offset is a share of the difference between the content box
and the concrete object. The resulting rectangle may start outside the box.
"""

from __future__ import annotations

import math
import re

_FITS = frozenset({"fill", "contain", "cover", "none", "scale-down"})
_HORIZONTAL = frozenset({"left", "right"})
_VERTICAL = frozenset({"top", "bottom"})
_LENGTH = re.compile(r"^([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)(px|%)$", re.IGNORECASE)
_ZERO = re.compile(r"^[+-]?(?:0+(?:\.0+)?|\.0+)(?:[eE][+-]?\d+)?$")


class _Invalid(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def fit_object(
    content_width: object,
    content_height: object,
    *,
    fit: object = "fill",
    position: object = "50% 50%",
    natural_width: object = None,
    natural_height: object = None,
    natural_ratio: object = None,
) -> dict[str, object]:
    """Return the concrete object's origin and size inside the content box.

    ``x`` and ``y`` are the object's top-left corner relative to the
    content box's top-left corner. A negative origin is outside that box.
    """

    try:
        box_w = _box(content_width, "content width")
        box_h = _box(content_height, "content height")
        mode = _fit(fit)
        width, height, chosen = _concrete(
            mode,
            box_w,
            box_h,
            _dimension(natural_width, "natural width"),
            _dimension(natural_height, "natural height"),
            _ratio(natural_ratio),
        )
        horizontal, vertical = _parse_position(position)
        return {
            "outcome": "fitted",
            "fit": mode,
            "chosen": chosen,
            "x": _number((box_w - width) * horizontal[0] + horizontal[1]),
            "y": _number((box_h - height) * vertical[0] + vertical[1]),
            "width": _number(width),
            "height": _number(height),
        }
    except _Invalid as exc:
        return _invalid(exc.reason)


def _concrete(
    mode: str,
    box_w: float,
    box_h: float,
    natural_w: float | None,
    natural_h: float | None,
    explicit_ratio: float | None,
) -> tuple[float, float, str]:
    ratio = _usable_ratio(natural_w, natural_h, explicit_ratio)
    if mode == "fill":
        return box_w, box_h, "fill"
    contained = _constrain(box_w, box_h, ratio, cover=False)
    if mode == "contain":
        return contained[0], contained[1], "contain"
    if mode == "cover":
        covered = _constrain(box_w, box_h, ratio, cover=True)
        return covered[0], covered[1], "cover"
    natural = _none(box_w, box_h, natural_w, natural_h, ratio)
    if mode == "none":
        return natural[0], natural[1], "none"
    if _not_larger(natural, contained):
        return natural[0], natural[1], "none"
    return contained[0], contained[1], "contain"


def _usable_ratio(
    natural_w: float | None,
    natural_h: float | None,
    explicit: float | None,
) -> float | None:
    if natural_w == 0 or natural_h == 0:
        if explicit is not None:
            raise _Invalid("natural ratio disagrees with natural size")
        return None
    if natural_w is not None and natural_h is not None:
        implied = natural_w / natural_h
        if explicit is not None and not _near(explicit, implied):
            raise _Invalid("natural ratio disagrees with natural size")
        return implied
    return explicit


def _constrain(box_w: float, box_h: float, ratio: float | None, *, cover: bool) -> tuple[float, float]:
    if ratio is None:
        return box_w, box_h
    if box_w == 0 and box_h == 0:
        return 0.0, 0.0
    if not cover and (box_w == 0 or box_h == 0):
        return 0.0, 0.0
    if box_h == 0:
        return box_w, box_w / ratio
    if box_w == 0:
        return box_h * ratio, box_h
    if (box_w / box_h > ratio) == cover:
        return box_w, box_w / ratio
    return box_h * ratio, box_h


def _none(
    box_w: float,
    box_h: float,
    natural_w: float | None,
    natural_h: float | None,
    ratio: float | None,
) -> tuple[float, float]:
    if natural_w is None and natural_h is None:
        return _constrain(box_w, box_h, ratio, cover=False)
    if natural_w is not None and natural_h is not None:
        return natural_w, natural_h
    if natural_w is not None:
        return natural_w, (natural_w / ratio if ratio is not None else box_h)
    assert natural_h is not None
    return (natural_h * ratio if ratio is not None else box_w), natural_h


def _parse_position(value: object) -> tuple[tuple[float, float], tuple[float, float]]:
    if not isinstance(value, str) or not value.strip():
        raise _Invalid("position is invalid")
    tokens = value.strip().split()
    parsed = [_token(token) for token in tokens]
    if any(item is None for item in parsed) or not 1 <= len(parsed) <= 4:
        raise _Invalid("position is invalid")
    items = [item for item in parsed if item is not None]
    if len(items) == 1:
        return _single(items[0])
    if len(items) == 2 and all(item[0] == "keyword" for item in items):
        return _keyword_pair(items[0][1], items[1][1])
    if len(items) == 2:
        return _horizontal(items[0]), _vertical(items[1])
    return _edges(items)


def _single(token: tuple[str, str]) -> tuple[tuple[float, float], tuple[float, float]]:
    kind, text = token
    if kind == "keyword":
        if text == "left":
            return (0.0, 0.0), (0.5, 0.0)
        if text == "right":
            return (1.0, 0.0), (0.5, 0.0)
        if text == "top":
            return (0.5, 0.0), (0.0, 0.0)
        if text == "bottom":
            return (0.5, 0.0), (1.0, 0.0)
        if text == "center":
            return (0.5, 0.0), (0.5, 0.0)
    return _horizontal(token), (0.5, 0.0)


def _keyword_pair(first: str, second: str) -> tuple[tuple[float, float], tuple[float, float]]:
    horizontal: tuple[float, float] | None = None
    vertical: tuple[float, float] | None = None
    centers = 0
    for text in (first, second):
        if text in _HORIZONTAL:
            if horizontal is not None:
                raise _Invalid("position is invalid")
            horizontal = (1.0 if text == "right" else 0.0, 0.0)
        elif text in _VERTICAL:
            if vertical is not None:
                raise _Invalid("position is invalid")
            vertical = (1.0 if text == "bottom" else 0.0, 0.0)
        elif text == "center":
            centers += 1
        else:
            raise _Invalid("position is invalid")
    for _ in range(centers):
        if horizontal is None:
            horizontal = (0.5, 0.0)
        elif vertical is None:
            vertical = (0.5, 0.0)
        else:
            raise _Invalid("position is invalid")
    if horizontal is None or vertical is None:
        raise _Invalid("position is invalid")
    return horizontal, vertical


def _edges(items: list[tuple[str, str]]) -> tuple[tuple[float, float], tuple[float, float]]:
    horizontal: tuple[float, float] | None = None
    vertical: tuple[float, float] | None = None
    index = 0
    while index < len(items):
        kind, text = items[index]
        if kind != "keyword":
            raise _Invalid("position is invalid")
        if text == "center":
            if index + 1 < len(items) and items[index + 1][0] != "keyword":
                raise _Invalid("position is invalid")
            if horizontal is None and vertical is not None:
                horizontal = (0.5, 0.0)
            elif vertical is None and horizontal is not None:
                vertical = (0.5, 0.0)
            elif horizontal is None and vertical is None and index + 1 < len(items):
                nxt = items[index + 1][1]
                if nxt in _VERTICAL:
                    horizontal = (0.5, 0.0)
                elif nxt in _HORIZONTAL:
                    vertical = (0.5, 0.0)
                else:
                    raise _Invalid("position is invalid")
            else:
                raise _Invalid("position is invalid")
            index += 1
            continue
        if text in _HORIZONTAL or text in _VERTICAL:
            offset = (0.0, 0.0)
            if index + 1 < len(items) and items[index + 1][0] != "keyword":
                offset = _offset(text, items[index + 1])
                index += 2
            else:
                offset = _offset(text, ("length", "0"))
                index += 1
            if text in _HORIZONTAL:
                if horizontal is not None:
                    raise _Invalid("position is invalid")
                horizontal = offset
            else:
                if vertical is not None:
                    raise _Invalid("position is invalid")
                vertical = offset
            continue
        raise _Invalid("position is invalid")
    if horizontal is None or vertical is None:
        raise _Invalid("position is invalid")
    return horizontal, vertical


def _horizontal(token: tuple[str, str]) -> tuple[float, float]:
    kind, text = token
    if kind == "keyword":
        if text == "left":
            return 0.0, 0.0
        if text == "right":
            return 1.0, 0.0
        if text == "center":
            return 0.5, 0.0
        raise _Invalid("position is invalid")
    return _start_offset(token)


def _vertical(token: tuple[str, str]) -> tuple[float, float]:
    kind, text = token
    if kind == "keyword":
        if text == "top":
            return 0.0, 0.0
        if text == "bottom":
            return 1.0, 0.0
        if text == "center":
            return 0.5, 0.0
        raise _Invalid("position is invalid")
    return _start_offset(token)


def _offset(edge: str, token: tuple[str, str]) -> tuple[float, float]:
    origin, length = _start_offset(token)
    if edge in {"left", "top"}:
        return origin, length
    if token[0] == "percent":
        return 1.0 - origin, 0.0
    return 1.0, -length


def _start_offset(token: tuple[str, str]) -> tuple[float, float]:
    kind, text = token
    if kind == "percent":
        return float(text) / 100.0, 0.0
    if kind == "length":
        return 0.0, float(text)
    raise _Invalid("position is invalid")


def _token(text: str) -> tuple[str, str] | None:
    lowered = text.lower()
    if lowered in {"left", "right", "top", "bottom", "center"}:
        return "keyword", lowered
    if _ZERO.fullmatch(text):
        return "length", "0"
    match = _LENGTH.fullmatch(text)
    if match is None:
        return None
    number = float(match.group(1))
    if not math.isfinite(number):
        return None
    unit = match.group(2).lower()
    return ("percent" if unit == "%" else "length"), str(number)


def _not_larger(left: tuple[float, float], right: tuple[float, float]) -> bool:
    if not _near(left[0] * left[1], right[0] * right[1]):
        return left[0] * left[1] < right[0] * right[1]
    if not _near(left[0], right[0]):
        return left[0] < right[0]
    return left[1] <= right[1] or _near(left[1], right[1])


def _near(left: float, right: float) -> bool:
    return abs(left - right) <= 1e-9 * max(1.0, abs(left), abs(right))


def _fit(value: object) -> str:
    if not isinstance(value, str) or value.strip().lower() not in _FITS:
        raise _Invalid("fit must be fill, contain, cover, none, or scale-down")
    return value.strip().lower()


def _box(value: object, name: str) -> float:
    number = _finite(value, name)
    if number < 0:
        raise _Invalid(f"{name} cannot be negative")
    return number


def _dimension(value: object, name: str) -> float | None:
    if value is None:
        return None
    number = _finite(value, name)
    if number < 0:
        raise _Invalid(f"{name} cannot be negative")
    return number


def _ratio(value: object) -> float | None:
    if value is None:
        return None
    number = _finite(value, "natural ratio")
    if number <= 0:
        raise _Invalid("natural ratio must be positive")
    return number


def _finite(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _Invalid(f"{name} is invalid")
    number = float(value)
    if not math.isfinite(number):
        raise _Invalid(f"{name} is invalid")
    return number


def _number(value: float) -> int | float:
    if not math.isfinite(value):
        raise _Invalid("concrete size is invalid")
    nearest = round(value)
    if abs(value - nearest) <= 1e-9:
        return int(nearest)
    return value


def _invalid(reason: str) -> dict[str, object]:
    return {
        "outcome": "invalid",
        "reason": reason,
        "fit": None,
        "chosen": None,
        "x": None,
        "y": None,
        "width": None,
        "height": None,
    }
