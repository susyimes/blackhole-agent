"""Map a local point through a CSS 2D transform.

CSS Transforms Level 1. The used matrix sends a column vector through the
negated transform-origin, then each listed transform, then the origin.
``rotate()`` is clockwise because Y grows downward. ``skew()`` is one
matrix, not ``skewX()`` followed by ``skewY()``. An outer layer then maps
that parent point, including the layer's reference-box offset.

3D functions are rejected. Percentages in a translation use the reference
box: the width for X and the height for Y. ``calc()``, ``min()``,
``max()``, and ``clamp()`` resolve through the shared length math.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from blackhole_agent.css_length_math import is_length_math, resolve_length_math

_LAYER_FIELDS = frozenset({"x", "y", "width", "height", "transform", "origin"})
_POINT_FIELDS = frozenset({"x", "y"})
_HORIZONTAL = {"left": 0.0, "right": 100.0}
_VERTICAL = {"top": 0.0, "bottom": 100.0}
_NUMBER = re.compile(r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?")
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*")


class _Invalid(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class _Layer:
    x: float
    y: float
    matrix: tuple[float, float, float, float, float, float]


def map_transformed_point(layers: object, point: object) -> dict[str, object]:
    """Return parent coordinates and the innermost used matrix.

    ``layers`` is one mapping, or a list whose first item is the outer
    layer. Each layer has ``x``, ``y``, ``width``, ``height``, optional
    ``transform`` (default ``none``), and optional ``origin`` (default
    ``50% 50%``). ``point`` is ``x`` and ``y`` in the innermost reference
    box, whose origin is that box's top left. The matrix is
    ``matrix(a, b, c, d, e, f)`` with Y downward.
    """

    try:
        parsed = _layers(layers)
        local_x, local_y = _point(point)
        x, y = local_x, local_y
        for layer in reversed(parsed):
            x, y = _apply(layer.matrix, x, y)
            x += layer.x
            y += layer.y
    except _Invalid as exc:
        return _invalid(exc.reason)
    return {
        "outcome": "mapped",
        "x": _number(x),
        "y": _number(y),
        "matrix": [_number(item) for item in parsed[-1].matrix],
        "reason": None,
    }


def _layers(value: object) -> list[_Layer]:
    if isinstance(value, Mapping):
        items: Sequence[object] = (value,)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        items = value
    else:
        raise _Invalid("layers")
    if not items:
        raise _Invalid("layers")
    return [_layer(item) for item in items]


def _layer(value: object) -> _Layer:
    if not isinstance(value, Mapping):
        raise _Invalid("layer")
    unknown = set(value) - _LAYER_FIELDS
    if unknown:
        raise _Invalid("layer")
    width = _nonnegative(value.get("width"), "width")
    height = _nonnegative(value.get("height"), "height")
    origin_x, origin_y = _origin(value.get("origin", "50% 50%"), width, height)
    functions = _transforms(value.get("transform", "none"), width, height)
    matrix = _translate(-origin_x, -origin_y)
    for function in functions:
        matrix = _multiply(function, matrix)
    matrix = _multiply(_translate(origin_x, origin_y), matrix)
    if not all(math.isfinite(item) for item in matrix):
        raise _Invalid("matrix")
    return _Layer(
        _finite(value.get("x"), "x"),
        _finite(value.get("y"), "y"),
        matrix,
    )


def _point(value: object) -> tuple[float, float]:
    if not isinstance(value, Mapping) or set(value) - _POINT_FIELDS:
        raise _Invalid("point")
    return _finite(value.get("x"), "point"), _finite(value.get("y"), "point")


def _transforms(value: object, width: float, height: float) -> list[tuple[float, float, float, float, float, float]]:
    if not isinstance(value, str):
        raise _Invalid("transform")
    text = _comments_to_space(value).strip()
    if text.lower() == "none":
        return []
    if not text:
        raise _Invalid("transform")
    functions: list[tuple[float, float, float, float, float, float]] = []
    index = 0
    size = len(text)
    while index < size:
        index = _skip_space(text, index)
        if index >= size:
            break
        match = _IDENT.match(text, index)
        if match is None or match.end() >= size or text[match.end()] != "(":
            raise _Invalid("transform")
        inner, index = _inside(text, match.end())
        functions.append(_function(match.group(0).lower(), inner, width, height))
    if not functions:
        raise _Invalid("transform")
    return functions


def _function(
    name: str,
    inner: str,
    width: float,
    height: float,
) -> tuple[float, float, float, float, float, float]:
    args = _arguments(inner)
    if name == "matrix":
        if len(args) != 6:
            raise _Invalid("matrix")
        a, b, c, d, e, f = (_plain(arg) for arg in args)
        return (a, b, c, d, e, f)
    if name == "translate":
        if len(args) not in (1, 2):
            raise _Invalid("translate")
        ty = _length(args[1], height) if len(args) == 2 else 0.0
        return _translate(_length(args[0], width), ty)
    if name == "translatex":
        if len(args) != 1:
            raise _Invalid("translate")
        return _translate(_length(args[0], width), 0.0)
    if name == "translatey":
        if len(args) != 1:
            raise _Invalid("translate")
        return _translate(0.0, _length(args[0], height))
    if name == "scale":
        if len(args) not in (1, 2):
            raise _Invalid("scale")
        sx = _plain(args[0])
        sy = _plain(args[1]) if len(args) == 2 else sx
        return _scale(sx, sy)
    if name == "scalex":
        if len(args) != 1:
            raise _Invalid("scale")
        return _scale(_plain(args[0]), 1.0)
    if name == "scaley":
        if len(args) != 1:
            raise _Invalid("scale")
        return _scale(1.0, _plain(args[0]))
    if name == "rotate":
        if len(args) != 1:
            raise _Invalid("rotate")
        return _rotate(_angle(args[0]))
    if name == "skew":
        if len(args) not in (1, 2):
            raise _Invalid("skew")
        ay = _angle(args[1]) if len(args) == 2 else 0.0
        return _skew(_angle(args[0]), ay)
    if name == "skewx":
        if len(args) != 1:
            raise _Invalid("skew")
        return _skew(_angle(args[0]), 0.0)
    if name == "skewy":
        if len(args) != 1:
            raise _Invalid("skew")
        return _skew(0.0, _angle(args[0]))
    raise _Invalid("function")


def _origin(value: object, width: float, height: float) -> tuple[float, float]:
    if not isinstance(value, str):
        raise _Invalid("origin")
    parts = _split_space(_comments_to_space(value).strip())
    if len(parts) == 1:
        return _one_origin(parts[0], width, height)
    if len(parts) != 2:
        raise _Invalid("origin")
    return _two_origin(parts[0], parts[1], width, height)


def _one_origin(token: str, width: float, height: float) -> tuple[float, float]:
    key = token.lower()
    if key in _HORIZONTAL or key == "center":
        return _axis(token, width, "h"), _percent(50.0, height)
    if key in _VERTICAL:
        return _percent(50.0, width), _axis(token, height, "v")
    return _length(token, width), _percent(50.0, height)


def _two_origin(left: str, right: str, width: float, height: float) -> tuple[float, float]:
    pair = _assign_axes(left, right)
    if pair is None:
        raise _Invalid("origin")
    horizontal, vertical = pair
    return _axis(horizontal, width, "h"), _axis(vertical, height, "v")


def _assign_axes(left: str, right: str) -> tuple[str, str] | None:
    left_axis = _keyword_axis(left)
    right_axis = _keyword_axis(right)
    if left_axis == "h" and right_axis == "h":
        return None
    if left_axis == "v" and right_axis == "v":
        return None
    if left_axis == "h" and right_axis in {"v", "c", None}:
        return left, right
    if left_axis == "v" and right_axis in {"h", "c", None}:
        return right, left
    if left_axis == "c" and right_axis == "h":
        return right, left
    if left_axis == "c" and right_axis in {"v", "c", None}:
        return left, right
    if left_axis is None and right_axis in {"v", "c", None}:
        return left, right
    return None


def _keyword_axis(token: str) -> str | None:
    key = token.lower()
    if key in _HORIZONTAL:
        return "h"
    if key in _VERTICAL:
        return "v"
    if key == "center":
        return "c"
    return None


def _axis(token: str, basis: float, axis: str) -> float:
    key = token.lower()
    if key == "center":
        return _percent(50.0, basis)
    table = _HORIZONTAL if axis == "h" else _VERTICAL
    if key in table:
        return _percent(table[key], basis)
    if _keyword_axis(token) is not None:
        raise _Invalid("origin")
    return _length(token, basis)


def _arguments(inner: str) -> list[str]:
    if "," in _top_level(inner):
        parts = [part.strip() for part in _split_comma(inner)]
    else:
        parts = _split_space(inner.strip())
    if not parts or any(not part for part in parts):
        raise _Invalid("argument")
    return parts


def _top_level(text: str) -> str:
    chars: list[str] = []
    depth = 0
    for char in text:
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        elif depth == 0:
            chars.append(char)
    return "".join(chars)


def _split_comma(text: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    for char in text:
        if char == "(":
            depth += 1
            buf.append(char)
        elif char == ")":
            if depth == 0:
                raise _Invalid("parenthesis")
            depth -= 1
            buf.append(char)
        elif char == "," and depth == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(char)
    if depth != 0:
        raise _Invalid("parenthesis")
    parts.append("".join(buf))
    return parts


def _split_space(text: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    for char in text:
        if char == "(":
            depth += 1
            buf.append(char)
        elif char == ")":
            if depth == 0:
                raise _Invalid("parenthesis")
            depth -= 1
            buf.append(char)
        elif char.isspace() and depth == 0:
            if buf:
                parts.append("".join(buf))
                buf = []
        else:
            buf.append(char)
    if depth != 0:
        raise _Invalid("parenthesis")
    if buf:
        parts.append("".join(buf))
    return parts


def _inside(text: str, open_index: int) -> tuple[str, int]:
    depth = 1
    index = open_index + 1
    start = index
    while index < len(text):
        char = text[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return text[start:index], index + 1
        index += 1
    raise _Invalid("parenthesis")


def _length(text: str, basis: float) -> float:
    token = text.strip()
    if is_length_math(token):
        resolved = resolve_length_math(token, percentage_basis=basis)
        if resolved["outcome"] != "resolved" or not isinstance(resolved["px"], (int, float)):
            raise _Invalid("length")
        return float(resolved["px"])
    value, unit = _measure(token)
    if unit == "%":
        return value * basis / 100.0
    if unit == "px" or (unit == "" and value == 0.0):
        return value
    raise _Invalid("length")


def _angle(text: str) -> float:
    value, unit = _measure(text.strip())
    if unit == "deg" or (unit == "" and value == 0.0):
        return value
    if unit == "rad":
        return value * 180.0 / math.pi
    if unit == "grad":
        return value * 0.9
    if unit == "turn":
        return value * 360.0
    raise _Invalid("angle")


def _plain(text: str) -> float:
    value, unit = _measure(text.strip())
    if unit:
        raise _Invalid("number")
    return value


def _measure(text: str) -> tuple[float, str]:
    match = _NUMBER.fullmatch(text) if text else None
    if match is None:
        matched = _NUMBER.match(text)
        if matched is None or matched.end() == len(text):
            raise _Invalid("number")
        unit = text[matched.end():].lower()
        if not unit.isalpha() and unit != "%":
            raise _Invalid("number")
        return float(matched.group(0)), unit
    return float(match.group(0)), ""


def _percent(value: float, basis: float) -> float:
    return value * basis / 100.0


def _translate(tx: float, ty: float) -> tuple[float, float, float, float, float, float]:
    return (1.0, 0.0, 0.0, 1.0, tx, ty)


def _scale(sx: float, sy: float) -> tuple[float, float, float, float, float, float]:
    return (sx, 0.0, 0.0, sy, 0.0, 0.0)


def _rotate(degrees: float) -> tuple[float, float, float, float, float, float]:
    cosine, sine = _cosine_sine(degrees)
    return (cosine, sine, -sine, cosine, 0.0, 0.0)


def _skew(ax: float, ay: float) -> tuple[float, float, float, float, float, float]:
    return (1.0, _tangent(ay), _tangent(ax), 1.0, 0.0, 0.0)


def _cosine_sine(degrees: float) -> tuple[float, float]:
    quarter = degrees / 90.0
    nearest = round(quarter)
    if math.isfinite(quarter) and abs(quarter - nearest) <= 1e-9:
        return ((1.0, 0.0), (0.0, 1.0), (-1.0, 0.0), (0.0, -1.0))[nearest % 4]
    radians = math.radians(degrees)
    return math.cos(radians), math.sin(radians)


def _tangent(degrees: float) -> float:
    cosine, sine = _cosine_sine(degrees)
    if abs(cosine) <= 1e-12:
        raise _Invalid("skew")
    return sine / cosine


def _multiply(
    left: tuple[float, float, float, float, float, float],
    right: tuple[float, float, float, float, float, float],
) -> tuple[float, float, float, float, float, float]:
    a1, b1, c1, d1, e1, f1 = left
    a2, b2, c2, d2, e2, f2 = right
    return (
        a1 * a2 + c1 * b2,
        b1 * a2 + d1 * b2,
        a1 * c2 + c1 * d2,
        b1 * c2 + d1 * d2,
        a1 * e2 + c1 * f2 + e1,
        b1 * e2 + d1 * f2 + f1,
    )


def _apply(
    matrix: tuple[float, float, float, float, float, float],
    x: float,
    y: float,
) -> tuple[float, float]:
    a, b, c, d, e, f = matrix
    return a * x + c * y + e, b * x + d * y + f


def _comments_to_space(text: str) -> str:
    pieces: list[str] = []
    index = 0
    while index < len(text):
        if text.startswith("/*", index):
            end = text.find("*/", index + 2)
            if end < 0:
                raise _Invalid("comment")
            pieces.append(" ")
            index = end + 2
            continue
        pieces.append(text[index])
        index += 1
    return "".join(pieces)


def _skip_space(text: str, index: int) -> int:
    while index < len(text) and text[index].isspace():
        index += 1
    return index


def _nonnegative(value: object, name: str) -> float:
    number = _finite(value, name)
    if number < 0:
        raise _Invalid(name)
    return number


def _finite(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise _Invalid(name)
    return float(value)


def _number(value: float) -> int | float:
    nearest = round(value)
    if abs(value - nearest) <= 1e-9:
        return int(nearest)
    return value


def _invalid(reason: str) -> dict[str, object]:
    return {"outcome": "invalid", "x": None, "y": None, "matrix": None, "reason": reason}
