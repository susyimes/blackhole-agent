"""Resolve used CSS border radii, including overlap and inner curves.

CSS Backgrounds and Borders Level 3. Percentages resolve against the border
box: the horizontal radius uses the width and the vertical radius uses the
height. One to four values expand in the usual order, and a slash separates
horizontal radii from vertical radii. ``calc()`` and the other length math
functions resolve before overlap.

When the sum of two adjacent radii exceeds that side, every radius is
multiplied by the smallest side ratio. A corner that already fit still
shrinks. The padding-edge radius is the used outer radius minus the adjoining
border thickness, and the content-edge radius subtracts padding the same way.
A negative result of either subtraction is zero. ``border-collapse: collapse``
gives the radii no effect. ``em``, ``rem``, and viewport units are rejected
because this function has no font or viewport.
"""

from __future__ import annotations

import math
import re

from blackhole_agent.css_length_math import is_length_math, resolve_length_math

_WS = " \t\n\r\f"
_EPS = 1e-9
_CORNERS = ("top-left", "top-right", "bottom-right", "bottom-left")
_CURVES = ("outer_x", "outer_y", "inner_x", "inner_y", "content_x", "content_y")
_NUMBER = re.compile(r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?")
_ABSOLUTE_PX = {
    "px": 1.0,
    "in": 96.0,
    "cm": 96.0 / 2.54,
    "mm": 96.0 / 25.4,
    "pt": 96.0 / 72.0,
    "pc": 16.0,
    "q": 96.0 / 2.54 / 40.0,
}
# Horizontal inset uses the left or right border. Vertical inset uses top or bottom.
_X_SIDE = (3, 1, 1, 3)
_Y_SIDE = (0, 0, 2, 2)


class _Invalid(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def used_border_radii(
    width: object,
    height: object,
    radius: object,
    *,
    border: object = 0,
    padding: object = 0,
    border_collapse: object = "separate",
) -> dict[str, object]:
    """Return used outer, padding-edge, and content-edge corner radii.

    ``width`` and ``height`` are the border box in px. ``radius`` is a
    ``border-radius`` shorthand, or a unitless zero. ``border`` and
    ``padding`` are px lengths in top/right/bottom/left order. Percentages
    are invalid there: padding percentages need the containing block.
    """

    try:
        return _resolve(width, height, radius, border, padding, border_collapse)
    except _Invalid as exc:
        return {
            "outcome": "invalid",
            "reason": exc.reason,
            "scale": None,
            "applied": False,
            "corners": None,
        }


def _resolve(
    width: object,
    height: object,
    radius: object,
    border: object,
    padding: object,
    border_collapse: object,
) -> dict[str, object]:
    box_width = _box_size(width)
    box_height = _box_size(height)
    borders = _edges(border, "border is invalid")
    pads = _edges(padding, "padding is invalid")
    collapse = _collapse(border_collapse)
    horizontal, vertical = _radius_pairs(radius, box_width, box_height)
    if collapse == "collapse":
        return _payload(scale=None, applied=False, corners=_zero_corners())
    scale = _overlap_scale(box_width, box_height, horizontal, vertical)
    outer_x = [value * scale for value in horizontal]
    outer_y = [value * scale for value in vertical]
    corners = {}
    for index, name in enumerate(_CORNERS):
        inner_x = _inset(outer_x[index], borders[_X_SIDE[index]])
        inner_y = _inset(outer_y[index], borders[_Y_SIDE[index]])
        corners[name] = {
            "outer_x": _snap(outer_x[index]),
            "outer_y": _snap(outer_y[index]),
            "inner_x": _snap(inner_x),
            "inner_y": _snap(inner_y),
            "content_x": _snap(_inset(inner_x, pads[_X_SIDE[index]])),
            "content_y": _snap(_inset(inner_y, pads[_Y_SIDE[index]])),
        }
    return _payload(scale=_snap(scale), applied=True, corners=corners)


def _payload(scale: object, applied: bool, corners: dict[str, dict[str, int | float]]) -> dict[str, object]:
    return {
        "outcome": "resolved",
        "reason": None,
        "scale": scale,
        "applied": applied,
        "corners": corners,
    }


def _zero_corners() -> dict[str, dict[str, int]]:
    return {name: {key: 0 for key in _CURVES} for name in _CORNERS}


def _box_size(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _Invalid("box is invalid")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise _Invalid("box is invalid")
    return number


def _collapse(value: object) -> str:
    if not isinstance(value, str):
        raise _Invalid("border-collapse is invalid")
    name = value.strip().lower()
    if name not in {"separate", "collapse"}:
        raise _Invalid("border-collapse is invalid")
    return name


def _edges(value: object, reason: str) -> tuple[float, float, float, float]:
    if isinstance(value, bool):
        raise _Invalid(reason)
    if isinstance(value, (int, float)):
        return _expand(_edge_number(value, reason), reason)
    if isinstance(value, (list, tuple)):
        if not 1 <= len(value) <= 4:
            raise _Invalid(reason)
        return _expand([_edge_number(item, reason) for item in value], reason)
    if isinstance(value, dict):
        if set(value) != {"top", "right", "bottom", "left"}:
            raise _Invalid(reason)
        return (
            _edge_number(value["top"], reason),
            _edge_number(value["right"], reason),
            _edge_number(value["bottom"], reason),
            _edge_number(value["left"], reason),
        )
    if isinstance(value, str):
        tokens = _components(_strip_comments(value, reason), reason, slash=False)
        if tokens[1] is not None or not tokens[0]:
            raise _Invalid(reason)
        return _expand([_plain_or_math(token, 0.0, reason, allow_percentage=False) for token in tokens[0]], reason)
    raise _Invalid(reason)


def _edge_number(value: object, reason: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _Invalid(reason)
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise _Invalid(reason)
    return number


def _expand(values: list[float] | float, reason: str) -> tuple[float, float, float, float]:
    if isinstance(values, float):
        return (values, values, values, values)
    if len(values) == 1:
        return (values[0], values[0], values[0], values[0])
    if len(values) == 2:
        return (values[0], values[1], values[0], values[1])
    if len(values) == 3:
        return (values[0], values[1], values[2], values[1])
    if len(values) == 4:
        return (values[0], values[1], values[2], values[3])
    raise _Invalid(reason)


def _radius_pairs(radius: object, width: float, height: float) -> tuple[list[float], list[float]]:
    reason = "radius is invalid"
    if isinstance(radius, bool) or not isinstance(radius, (int, float, str)):
        raise _Invalid(reason)
    if isinstance(radius, (int, float)):
        if float(radius) != 0.0 or not math.isfinite(float(radius)):
            raise _Invalid(reason)
        return [0.0, 0.0, 0.0, 0.0], [0.0, 0.0, 0.0, 0.0]
    horizontal, vertical = _components(_strip_comments(radius, reason), reason, slash=True)
    if vertical is None:
        vertical = horizontal
    return (
        _expand_radius(horizontal, width, reason),
        _expand_radius(vertical, height, reason),
    )


def _expand_radius(tokens: list[str], basis: float, reason: str) -> list[float]:
    values = [_plain_or_math(token, basis, reason, allow_percentage=True) for token in tokens]
    expanded = _expand(values, reason)
    return [expanded[0], expanded[1], expanded[2], expanded[3]]


def _plain_or_math(token: str, basis: float, reason: str, *, allow_percentage: bool) -> float:
    if is_length_math(token):
        resolved = resolve_length_math(
            token,
            percentage_basis=basis,
            allow_percentage=allow_percentage,
        )
        px = resolved.get("px") if isinstance(resolved, dict) else None
        if resolved.get("outcome") != "resolved" or isinstance(px, bool) or not isinstance(px, (int, float)):
            raise _Invalid(reason)
        return _nonnegative(float(px), reason)
    return _dimension(token, basis, reason, allow_percentage=allow_percentage)


def _dimension(token: str, basis: float, reason: str, *, allow_percentage: bool) -> float:
    match = re.fullmatch(r"(?P<number>[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)(?P<unit>%|[A-Za-z]+)?", token)
    if match is None:
        raise _Invalid(reason)
    try:
        number = float(match.group("number"))
    except ValueError as exc:
        raise _Invalid(reason) from exc
    if not math.isfinite(number):
        raise _Invalid(reason)
    unit = match.group("unit")
    if unit is None:
        if number != 0.0:
            raise _Invalid(reason)
        return 0.0
    if unit == "%":
        if not allow_percentage:
            raise _Invalid(reason)
        return _nonnegative(number * basis / 100.0, reason)
    scale = _ABSOLUTE_PX.get(unit.lower())
    if scale is None:
        raise _Invalid(reason)
    return _nonnegative(number * scale, reason)


def _nonnegative(value: float, reason: str) -> float:
    if not math.isfinite(value) or value < -_EPS:
        raise _Invalid(reason)
    if value < 0:
        return 0.0
    return value


def _components(text: str, reason: str, *, slash: bool) -> tuple[list[str], list[str] | None]:
    horizontal: list[str] = []
    vertical: list[str] = []
    seen_slash = False
    target = horizontal
    index = 0
    length = len(text)
    while index < length:
        if text[index] in _WS:
            index += 1
            continue
        if text[index] == "/":
            if not slash or seen_slash or not horizontal:
                raise _Invalid(reason)
            seen_slash = True
            target = vertical
            index += 1
            continue
        token, index = _component(text, index, reason)
        if len(target) == 4:
            raise _Invalid(reason)
        target.append(token)
    if not horizontal or (seen_slash and not vertical):
        raise _Invalid(reason)
    return horizontal, vertical if seen_slash else None


def _component(text: str, index: int, reason: str) -> tuple[str, int]:
    if _ident_at(text, index):
        end = index + 1
        while end < len(text) and (text[end].isalnum() or text[end] in "-_"):
            end += 1
        if end >= len(text) or text[end] != "(":
            raise _Invalid(reason)
        close = _close_paren(text, end, reason)
        return text[index:close], close
    match = _NUMBER.match(text, index)
    if match is None:
        raise _Invalid(reason)
    end = match.end()
    if end < len(text) and text[end] == "%":
        return text[index : end + 1], end + 1
    unit = end
    while unit < len(text) and text[unit].isalpha():
        unit += 1
    return text[index:unit], unit


def _ident_at(text: str, index: int) -> bool:
    char = text[index]
    if char.isalpha() or char == "_":
        return True
    return char == "-" and index + 1 < len(text) and (text[index + 1].isalpha() or text[index + 1] == "_")


def _close_paren(text: str, open_index: int, reason: str) -> int:
    depth = 1
    index = open_index + 1
    quote = ""
    while index < len(text):
        char = text[index]
        if quote:
            if char == "\\":
                index += 2
                continue
            if char == quote:
                quote = ""
            index += 1
            continue
        if char in "\"'":
            quote = char
            index += 1
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    raise _Invalid(reason)


def _strip_comments(text: str, reason: str) -> str:
    pieces: list[str] = []
    index = 0
    while index < len(text):
        if text.startswith("/*", index):
            end = text.find("*/", index + 2)
            if end < 0:
                raise _Invalid(reason)
            pieces.append(" ")
            index = end + 2
            continue
        pieces.append(text[index])
        index += 1
    return "".join(pieces)


def _overlap_scale(width: float, height: float, horizontal: list[float], vertical: list[float]) -> float:
    sides = (
        (width, horizontal[0] + horizontal[1]),
        (height, vertical[1] + vertical[2]),
        (width, horizontal[2] + horizontal[3]),
        (height, vertical[0] + vertical[3]),
    )
    scale = 1.0
    for length, total in sides:
        if total > length + _EPS:
            scale = min(scale, length / total)
    return scale


def _inset(radius: float, thickness: float) -> float:
    reduced = radius - thickness
    if reduced < 0:
        return 0.0
    return reduced


def _snap(value: float) -> int | float:
    nearest = round(value)
    if abs(value - nearest) <= _EPS:
        return int(nearest)
    return value
