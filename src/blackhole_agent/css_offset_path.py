"""Place a point at an arc length along a CSS offset path.

CSS Motion Path. ``circle()`` and ``ellipse()`` start at the rightmost point
and run clockwise. ``inset()``, ``xywh()``, and ``polygon()`` start on the
top edge or the first vertex and close. ``path()`` follows the SVG outline
and is closed only when the final command is a closepath. A percentage is a
fraction of that length. A closed outline wraps with a non-negative modulo,
and a zero length stays on the anchor. An open outline clamps into its ends.
``ray()`` is a bearing, 0deg pointing up, and it is not clamped: a negative
distance travels backward along the same bearing. ``closest-side`` and
``farthest-side`` ignore the bearing; ``sides`` is the forward hit on the box.

``offset-rotate: auto`` aims along the tangent, the angle from the positive
x axis with y growing downward. ``reverse`` adds 180deg. A bare angle stays
fixed. SVG arc commands, rounded insets, ``ray()`` ``contain``, and
coordinate-box keywords are rejected.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

_EPS = 1e-9
_FILL = frozenset({"nonzero", "evenodd"})
_RAY_SIZES = frozenset({"closest-side", "closest-corner", "farthest-side", "farthest-corner", "sides"})
_HORIZONTAL = frozenset({"left", "right"})
_VERTICAL = frozenset({"top", "bottom"})
_SVG_ARGS = {
    "M": 2,
    "m": 2,
    "L": 2,
    "l": 2,
    "H": 1,
    "h": 1,
    "V": 1,
    "v": 1,
    "C": 6,
    "c": 6,
    "S": 4,
    "s": 4,
    "Q": 4,
    "q": 4,
    "T": 2,
    "t": 2,
    "Z": 0,
    "z": 0,
}


class _Bad(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def travel_offset_path(
    path: object,
    distance: object,
    *,
    rotate: object = "auto",
    box_width: object = None,
    box_height: object = None,
) -> dict[str, object]:
    """Return the point and rotation at ``distance`` along ``path``."""

    try:
        return _travel(path, distance, rotate, box_width, box_height)
    except _Bad as exc:
        return _invalid(exc.reason)


def _travel(
    path: object,
    distance: object,
    rotate: object,
    box_width: object,
    box_height: object,
) -> dict[str, object]:
    spin = _parse_rotate(rotate)
    kind, amount = _parse_distance(distance)
    box = _box(box_width, box_height)
    outline = _parse_outline(path, box)
    pixels = amount / 100.0 * outline.length if kind == "pct" else amount
    if outline.ray is not None:
        origin_x, origin_y, unit_x, unit_y, length = outline.ray
        point_x = origin_x + unit_x * pixels
        point_y = origin_y + unit_y * pixels
        return _resolved(point_x, point_y, _bearing(unit_x, unit_y), length, False, spin)
    point, tangent = outline.locate(pixels)
    return _resolved(point[0], point[1], tangent, outline.length, outline.closed, spin)


@dataclass
class _Walk:
    segments: list[object]
    closed: bool
    anchor: tuple[float, float]
    length: float
    ray: tuple[float, float, float, float, float] | None = None

    def locate(self, pixels: float) -> tuple[tuple[float, float], float | None]:
        used = self._used(pixels)
        if not self.segments or self.length <= _EPS:
            return self.anchor, None
        if not self.closed and used >= self.length - 1e-9:
            return self.segments[-1].at_distance(self.segments[-1].length)
        remaining = used
        last = len(self.segments) - 1
        for index, segment in enumerate(self.segments):
            if remaining < segment.length or index == last:
                return segment.at_distance(min(max(remaining, 0.0), segment.length))
            remaining -= segment.length
        return self.segments[-1].at_distance(self.segments[-1].length)

    def _used(self, pixels: float) -> float:
        if self.length <= _EPS:
            return 0.0
        if self.closed:
            return pixels % self.length
        if pixels < 0.0:
            return 0.0
        if pixels > self.length:
            return self.length
        return pixels


@dataclass(frozen=True)
class _Line:
    x0: float
    y0: float
    x1: float
    y1: float
    length: float

    def at_distance(self, dist: float) -> tuple[tuple[float, float], float | None]:
        if self.length <= _EPS:
            return (self.x0, self.y0), None
        ratio = min(max(dist / self.length, 0.0), 1.0)
        dx = self.x1 - self.x0
        dy = self.y1 - self.y0
        return (self.x0 + dx * ratio, self.y0 + dy * ratio), _bearing(dx, dy)


@dataclass(frozen=True)
class _Cubic:
    points: tuple[tuple[float, float], tuple[float, float], tuple[float, float], tuple[float, float]]
    length: float

    def at_distance(self, dist: float) -> tuple[tuple[float, float], float | None]:
        if self.length <= _EPS:
            return self.points[0], None
        target = min(max(dist, 0.0), self.length)
        if target <= _EPS:
            return self._sample(0.0, forward=True)
        if target >= self.length - _EPS:
            return self._sample(1.0, forward=False)
        lo = 0.0
        hi = 1.0
        for _ in range(60):
            mid = (lo + hi) * 0.5
            if _curve_length(self._deriv, 0.0, mid) < target:
                lo = mid
            else:
                hi = mid
        return self._sample((lo + hi) * 0.5, forward=True)

    def _sample(self, t: float, *, forward: bool) -> tuple[tuple[float, float], float | None]:
        dx, dy = self._deriv(t)
        if math.hypot(dx, dy) <= _EPS:
            nudge = 1e-4 if forward else -1e-4
            dx, dy = self._deriv(min(max(t + nudge, 0.0), 1.0))
        return self._point(t), _bearing(dx, dy)

    def _point(self, t: float) -> tuple[float, float]:
        p0, p1, p2, p3 = self.points
        u = 1.0 - t
        return (
            u * u * u * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t * t * t * p3[0],
            u * u * u * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t * t * t * p3[1],
        )

    def _deriv(self, t: float) -> tuple[float, float]:
        p0, p1, p2, p3 = self.points
        u = 1.0 - t
        return (
            3 * u * u * (p1[0] - p0[0]) + 6 * u * t * (p2[0] - p1[0]) + 3 * t * t * (p3[0] - p2[0]),
            3 * u * u * (p1[1] - p0[1]) + 6 * u * t * (p2[1] - p1[1]) + 3 * t * t * (p3[1] - p2[1]),
        )


@dataclass(frozen=True)
class _Ellipse:
    cx: float
    cy: float
    rx: float
    ry: float
    length: float

    def at_distance(self, dist: float) -> tuple[tuple[float, float], float | None]:
        if self.length <= _EPS:
            return (self.cx, self.cy), None
        target = min(max(dist, 0.0), self.length)
        theta = _theta_at(self.rx, self.ry, target, self.length)
        dx = -self.rx * math.sin(theta)
        dy = self.ry * math.cos(theta)
        if math.hypot(dx, dy) <= _EPS:
            nudge = min(theta + 1e-4, math.tau)
            dx = -self.rx * math.sin(nudge)
            dy = self.ry * math.cos(nudge)
        return (self.cx + self.rx * math.cos(theta), self.cy + self.ry * math.sin(theta)), _bearing(dx, dy)


def _parse_outline(path: object, box: tuple[float, float] | None) -> _Walk:
    if not isinstance(path, str) or not path.strip():
        raise _Bad("path")
    name, args = _function(path)
    if name == "path":
        return _svg_walk(_path_data(args))
    if name == "circle":
        return _circle_walk(args, box)
    if name == "ellipse":
        return _ellipse_walk(args, box)
    if name == "inset":
        return _inset_walk(args, box)
    if name == "xywh":
        return _xywh_walk(args, box)
    if name == "polygon":
        return _polygon_walk(args, box)
    if name == "ray":
        return _ray_walk(args, box)
    raise _Bad("path")


def _circle_walk(args: list[str], box: tuple[float, float] | None) -> _Walk:
    radii, position = _split_at(args)
    if len(radii) > 1:
        raise _Bad("path")
    cx, cy = _position(position, box)
    if not radii:
        rx = ry = _circle_side(cx, cy, _need_box(box), farthest=False)
    else:
        rx = ry = _circle_radius(radii[0], cx, cy, box)
    return _ellipse_outline(cx, cy, rx, ry)


def _ellipse_walk(args: list[str], box: tuple[float, float] | None) -> _Walk:
    radii, position = _split_at(args)
    if len(radii) != 2:
        raise _Bad("path")
    cx, cy = _position(position, box)
    rx = _ellipse_radius(radii[0], cx, box, horizontal=True)
    ry = _ellipse_radius(radii[1], cy, box, horizontal=False)
    return _ellipse_outline(cx, cy, rx, ry)


def _ellipse_outline(cx: float, cy: float, rx: float, ry: float) -> _Walk:
    if rx < 0 or ry < 0 or not math.isfinite(rx) or not math.isfinite(ry):
        raise _Bad("path")
    anchor = (cx + rx, cy)
    if rx <= _EPS and ry <= _EPS:
        return _Walk([], True, (cx, cy), 0.0)
    if abs(rx - ry) <= 1e-12:
        segment = _Ellipse(cx, cy, rx, ry, math.tau * rx)
    else:
        segment = _Ellipse(cx, cy, rx, ry, _ellipse_length(rx, ry))
    if segment.length <= _EPS:
        return _Walk([], True, anchor, 0.0)
    return _Walk([segment], True, anchor, segment.length)


def _inset_walk(args: list[str], box: tuple[float, float] | None) -> _Walk:
    if any(token.lower() == "round" for token in args):
        raise _Bad("round")
    width, height = _need_box(box)
    edges = [token for token in args if token != ","]
    if not edges or len(edges) > 4:
        raise _Bad("path")
    top, right, bottom, left = _insets(edges, width, height)
    return _rectangle(left, top, width - right, height - bottom)


def _xywh_walk(args: list[str], box: tuple[float, float] | None) -> _Walk:
    if any(token.lower() == "round" for token in args):
        raise _Bad("round")
    edges = [token for token in args if token != ","]
    if len(edges) != 4:
        raise _Bad("path")
    x = _length(edges[0], box, horizontal=True)
    y = _length(edges[1], box, horizontal=False)
    width = _length(edges[2], box, horizontal=True)
    height = _length(edges[3], box, horizontal=False)
    if width < 0 or height < 0:
        raise _Bad("path")
    return _rectangle(x, y, x + width, y + height)


def _rectangle(left: float, top: float, right: float, bottom: float) -> _Walk:
    if right < left or bottom < top:
        raise _Bad("path")
    anchor = (left, top)
    if right - left <= _EPS or bottom - top <= _EPS:
        return _Walk([], True, anchor, 0.0)
    segments = [
        _line(left, top, right, top),
        _line(right, top, right, bottom),
        _line(right, bottom, left, bottom),
        _line(left, bottom, left, top),
    ]
    return _Walk(segments, True, anchor, sum(segment.length for segment in segments))


def _polygon_walk(args: list[str], box: tuple[float, float] | None) -> _Walk:
    tokens = list(args)
    if tokens and tokens[0].lower() in _FILL:
        if len(tokens) < 2 or tokens[1] != ",":
            raise _Bad("path")
        tokens = tokens[2:]
    groups: list[list[str]] = []
    current: list[str] = []
    for token in tokens:
        if token == ",":
            if not current:
                raise _Bad("path")
            groups.append(current)
            current = []
            continue
        current.append(token)
    if current:
        groups.append(current)
    if len(groups) < 3:
        raise _Bad("path")
    points: list[tuple[float, float]] = []
    for group in groups:
        if len(group) != 2:
            raise _Bad("path")
        points.append((_length(group[0], box, horizontal=True), _length(group[1], box, horizontal=False)))
    segments = []
    for index, point in enumerate(points):
        nxt = points[(index + 1) % len(points)]
        segments.append(_line(point[0], point[1], nxt[0], nxt[1]))
    segments = [segment for segment in segments if segment.length > _EPS]
    length = sum(segment.length for segment in segments)
    return _Walk(segments, True, points[0], length)


def _ray_walk(args: list[str], box: tuple[float, float] | None) -> _Walk:
    width, height = _need_box(box)
    angle: float | None = None
    size = "closest-side"
    position: list[str] | None = None
    index = 0
    while index < len(args):
        token = args[index]
        lower = token.lower()
        if lower == "contain":
            raise _Bad("contain")
        if lower == "at":
            if position is not None:
                raise _Bad("ray")
            index += 1
            taken: list[str] = []
            while index < len(args) and len(taken) < 2 and _position_token(args[index]):
                taken.append(args[index])
                index += 1
            if not taken:
                raise _Bad("ray")
            position = taken
            continue
        if lower in _RAY_SIZES:
            size = lower
            index += 1
            continue
        if _is_angle(token):
            if angle is not None:
                raise _Bad("ray")
            angle = _angle(token)
            index += 1
            continue
        raise _Bad("ray")
    if angle is None:
        raise _Bad("ray")
    origin_x, origin_y = _position(position or [], box)
    radians = math.radians(angle)
    unit_x = math.sin(radians)
    unit_y = -math.cos(radians)
    if size == "sides":
        length = _ray_hit(origin_x, origin_y, unit_x, unit_y, width, height)
    elif size == "closest-side":
        length = min(_side_distances(origin_x, origin_y, width, height))
    elif size == "farthest-side":
        length = max(_side_distances(origin_x, origin_y, width, height))
    elif size == "closest-corner":
        length = min(_corner_distances(origin_x, origin_y, width, height))
    else:
        length = max(_corner_distances(origin_x, origin_y, width, height))
    return _Walk([], False, (origin_x, origin_y), length, (origin_x, origin_y, unit_x, unit_y, length))


def _svg_walk(data: str) -> _Walk:
    tokens = _svg_tokens(data)
    if not tokens:
        raise _Bad("path")
    cx = cy = sx = sy = 0.0
    anchor: tuple[float, float] | None = None
    command: str | None = None
    final = ""
    prev = ""
    cubic_control: tuple[float, float] | None = None
    quad_control: tuple[float, float] | None = None
    segments: list[object] = []
    index = 0
    while index < len(tokens):
        kind, value = tokens[index]
        if kind == "cmd":
            command = str(value)
            index += 1
            if command in {"Z", "z"}:
                if anchor is None:
                    anchor = (0.0, 0.0)
                segment = _line(cx, cy, sx, sy)
                if segment.length > _EPS:
                    segments.append(segment)
                cx, cy = sx, sy
                final = command
                prev = "Z"
                cubic_control = None
                quad_control = None
                continue
            if command not in _SVG_ARGS:
                raise _Bad("arc" if command in {"A", "a"} else "path")
        elif command is None:
            raise _Bad("path")
        count = _SVG_ARGS[command]
        numbers, index = _take_numbers(tokens, index, count)
        if numbers is None:
            raise _Bad("path")
        final = command
        if command in {"M", "m"}:
            moved = _add(cx, cy, numbers[0], numbers[1], absolute=command == "M")
            cx, cy = moved
            sx, sy = cx, cy
            anchor = moved if anchor is None else anchor
            prev = "M"
            cubic_control = None
            quad_control = None
            command = "L" if command == "M" else "l"
            continue
        if command in {"L", "l"}:
            end = _add(cx, cy, numbers[0], numbers[1], absolute=command == "L")
            _append_line(segments, cx, cy, end[0], end[1])
            cx, cy = end
            prev = "L"
        elif command in {"H", "h"}:
            end_x = numbers[0] if command == "H" else cx + numbers[0]
            _append_line(segments, cx, cy, end_x, cy)
            cx = end_x
            prev = "L"
        elif command in {"V", "v"}:
            end_y = numbers[0] if command == "V" else cy + numbers[0]
            _append_line(segments, cx, cy, cx, end_y)
            cy = end_y
            prev = "L"
        elif command in {"C", "c"}:
            c1 = _add(cx, cy, numbers[0], numbers[1], absolute=command == "C")
            c2 = _add(cx, cy, numbers[2], numbers[3], absolute=command == "C")
            end = _add(cx, cy, numbers[4], numbers[5], absolute=command == "C")
            _append_cubic(segments, (cx, cy), c1, c2, end)
            cubic_control = c2
            quad_control = None
            cx, cy = end
            prev = "C"
        elif command in {"S", "s"}:
            c2 = _add(cx, cy, numbers[0], numbers[1], absolute=command == "S")
            end = _add(cx, cy, numbers[2], numbers[3], absolute=command == "S")
            c1 = _reflect(cubic_control, (cx, cy)) if prev == "C" and cubic_control is not None else (cx, cy)
            _append_cubic(segments, (cx, cy), c1, c2, end)
            cubic_control = c2
            quad_control = None
            cx, cy = end
            prev = "C"
        elif command in {"Q", "q"}:
            control = _add(cx, cy, numbers[0], numbers[1], absolute=command == "Q")
            end = _add(cx, cy, numbers[2], numbers[3], absolute=command == "Q")
            _append_cubic(segments, (cx, cy), *_quad_controls((cx, cy), control, end), end)
            quad_control = control
            cubic_control = None
            cx, cy = end
            prev = "Q"
        else:
            end = _add(cx, cy, numbers[0], numbers[1], absolute=command == "T")
            control = _reflect(quad_control, (cx, cy)) if prev == "Q" and quad_control is not None else (cx, cy)
            _append_cubic(segments, (cx, cy), *_quad_controls((cx, cy), control, end), end)
            quad_control = control
            cubic_control = None
            cx, cy = end
            prev = "Q"
        if anchor is None:
            anchor = (0.0, 0.0)
    if anchor is None:
        raise _Bad("path")
    length = sum(segment.length for segment in segments)
    return _Walk(segments, final in {"Z", "z"}, anchor, length)


def _append_line(segments: list[object], x0: float, y0: float, x1: float, y1: float) -> None:
    segment = _line(x0, y0, x1, y1)
    if segment.length > _EPS:
        segments.append(segment)


def _append_cubic(
    segments: list[object],
    start: tuple[float, float],
    c1: tuple[float, float],
    c2: tuple[float, float],
    end: tuple[float, float],
) -> None:
    for point in (start, c1, c2, end):
        if not math.isfinite(point[0]) or not math.isfinite(point[1]):
            raise _Bad("path")
    segment = _Cubic((start, c1, c2, end), 0.0)
    length = _curve_length(segment._deriv, 0.0, 1.0)
    if not math.isfinite(length):
        raise _Bad("path")
    if length > _EPS:
        segments.append(_Cubic((start, c1, c2, end), length))


def _line(x0: float, y0: float, x1: float, y1: float) -> _Line:
    if not all(math.isfinite(value) for value in (x0, y0, x1, y1)):
        raise _Bad("path")
    return _Line(x0, y0, x1, y1, math.hypot(x1 - x0, y1 - y0))


def _quad_controls(
    start: tuple[float, float], control: tuple[float, float], end: tuple[float, float]
) -> tuple[tuple[float, float], tuple[float, float]]:
    return (
        (start[0] + 2.0 / 3.0 * (control[0] - start[0]), start[1] + 2.0 / 3.0 * (control[1] - start[1])),
        (end[0] + 2.0 / 3.0 * (control[0] - end[0]), end[1] + 2.0 / 3.0 * (control[1] - end[1])),
    )


def _reflect(point: tuple[float, float] | None, about: tuple[float, float]) -> tuple[float, float]:
    if point is None:
        return about
    return (2.0 * about[0] - point[0], 2.0 * about[1] - point[1])


def _add(cx: float, cy: float, x: float, y: float, *, absolute: bool) -> tuple[float, float]:
    if not math.isfinite(x) or not math.isfinite(y):
        raise _Bad("path")
    if absolute:
        return x, y
    return cx + x, cy + y


def _take_numbers(tokens: list[tuple[str, object]], index: int, count: int) -> tuple[list[float] | None, int]:
    numbers: list[float] = []
    for _ in range(count):
        if index >= len(tokens) or tokens[index][0] != "num":
            return None, index
        numbers.append(float(tokens[index][1]))
        index += 1
    return numbers, index


def _svg_tokens(data: str) -> list[tuple[str, object]]:
    tokens: list[tuple[str, object]] = []
    index = 0
    size = len(data)
    while index < size:
        char = data[index]
        if char.isspace() or char == ",":
            index += 1
            continue
        if char.isalpha():
            tokens.append(("cmd", char))
            index += 1
            continue
        start = index
        if char in "+-":
            index += 1
        saw_digit = False
        saw_dot = False
        while index < size and (data[index].isdigit() or data[index] == "."):
            if data[index] == ".":
                if saw_dot:
                    break
                saw_dot = True
            else:
                saw_digit = True
            index += 1
        if index < size and data[index] in "eE" and saw_digit:
            cursor = index + 1
            if cursor < size and data[cursor] in "+-":
                cursor += 1
            digit_end = cursor
            while digit_end < size and data[digit_end].isdigit():
                digit_end += 1
            if digit_end > cursor:
                index = digit_end
        if not saw_digit or index == start:
            raise _Bad("path")
        number = float(data[start:index])
        if not math.isfinite(number):
            raise _Bad("path")
        tokens.append(("num", number))
    return tokens


def _function(text: str) -> tuple[str, list[str]]:
    tokens = _css_tokens(text.strip())
    if len(tokens) < 3 or tokens[1] != "(" or tokens[-1] != ")":
        raise _Bad("path")
    name = tokens[0].lower()
    if not name or any(not (char.isalnum() or char == "-") for char in name):
        raise _Bad("path")
    return name, tokens[2:-1]


def _path_data(args: list[str]) -> str:
    if len(args) == 1 and args[0].startswith("STR:"):
        return args[0][4:]
    if len(args) == 3 and args[0].lower() in _FILL and args[1] == "," and args[2].startswith("STR:"):
        return args[2][4:]
    raise _Bad("path")


def _css_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    index = 0
    size = len(text)
    while index < size:
        if text.startswith("/*", index):
            end = text.find("*/", index + 2)
            if end < 0:
                raise _Bad("path")
            index = end + 2
            continue
        char = text[index]
        if char.isspace():
            index += 1
            continue
        if char in "(),":
            tokens.append(char)
            index += 1
            continue
        if char in "\"'":
            quote = char
            index += 1
            chars: list[str] = []
            while index < size and text[index] != quote:
                if text[index] == "\\":
                    raise _Bad("path")
                chars.append(text[index])
                index += 1
            if index >= size:
                raise _Bad("path")
            index += 1
            tokens.append("STR:" + "".join(chars))
            continue
        end = index + 1
        while end < size and not text[end].isspace() and text[end] not in "(),\"'":
            end += 1
        tokens.append(text[index:end])
        index = end
    return tokens


def _split_at(args: list[str]) -> tuple[list[str], list[str]]:
    if args.count("at") > 1:
        raise _Bad("path")
    if "at" not in args:
        return [token for token in args if token != ","], []
    index = args.index("at")
    radii = [token for token in args[:index] if token != ","]
    return radii, args[index + 1 :]


def _position(tokens: list[str], box: tuple[float, float] | None) -> tuple[float, float]:
    values = [token for token in tokens if token != ","]
    if not values or values == ["center"]:
        width, height = _need_box(box)
        return width / 2.0, height / 2.0
    if len(values) == 1:
        horizontal, vertical = _single_position(values[0])
    elif len(values) == 2:
        horizontal, vertical = _pair_position(values[0], values[1])
    else:
        raise _Bad("path")
    return (
        _axis(horizontal, box, horizontal=True),
        _axis(vertical, box, horizontal=False),
    )


def _single_position(token: str) -> tuple[str, str]:
    lower = token.lower()
    if lower in _HORIZONTAL or lower == "center":
        return lower, "center"
    if lower in _VERTICAL:
        return "center", lower
    raise _Bad("path")


def _pair_position(first: str, second: str) -> tuple[str, str]:
    a = first.lower()
    b = second.lower()
    a_horizontal = a in _HORIZONTAL
    b_horizontal = b in _HORIZONTAL
    a_vertical = a in _VERTICAL
    b_vertical = b in _VERTICAL
    if a_horizontal and b_vertical:
        return first, second
    if a_vertical and b_horizontal:
        return second, first
    if a_vertical and not b_vertical:
        return second, first
    if b_horizontal and not a_horizontal:
        return second, first
    return first, second


def _axis(token: str, box: tuple[float, float] | None, *, horizontal: bool) -> float:
    lower = token.lower()
    size = None if box is None else (box[0] if horizontal else box[1])
    if lower == "center":
        if size is None:
            raise _Bad("box")
        return size / 2.0
    if horizontal and lower == "left":
        return 0.0
    if horizontal and lower == "right":
        if size is None:
            raise _Bad("box")
        return size
    if not horizontal and lower == "top":
        return 0.0
    if not horizontal and lower == "bottom":
        if size is None:
            raise _Bad("box")
        return size
    if lower in _HORIZONTAL or lower in _VERTICAL:
        raise _Bad("path")
    return _length(token, box, horizontal=horizontal)


def _insets(edges: list[str], width: float, height: float) -> tuple[float, float, float, float]:
    box = (width, height)

    def vertical(token: str) -> float:
        return _length(token, box, horizontal=False)

    def horizontal(token: str) -> float:
        return _length(token, box, horizontal=True)

    if len(edges) == 1:
        return vertical(edges[0]), horizontal(edges[0]), vertical(edges[0]), horizontal(edges[0])
    if len(edges) == 2:
        return vertical(edges[0]), horizontal(edges[1]), vertical(edges[0]), horizontal(edges[1])
    if len(edges) == 3:
        return vertical(edges[0]), horizontal(edges[1]), vertical(edges[2]), horizontal(edges[1])
    return vertical(edges[0]), horizontal(edges[1]), vertical(edges[2]), horizontal(edges[3])


def _circle_radius(token: str, cx: float, cy: float, box: tuple[float, float] | None) -> float:
    lower = token.lower()
    if lower in {"closest-side", "farthest-side"}:
        return _circle_side(cx, cy, _need_box(box), farthest=lower == "farthest-side")
    if lower.endswith("%"):
        width, height = _need_box(box)
        return _finite(lower[:-1], "path") / 100.0 * math.hypot(width, height) / math.sqrt(2.0)
    return _length(token, box, horizontal=True)


def _ellipse_radius(token: str, center: float, box: tuple[float, float] | None, *, horizontal: bool) -> float:
    lower = token.lower()
    if lower in {"closest-side", "farthest-side"}:
        width, height = _need_box(box)
        size = width if horizontal else height
        near = min(center, size - center)
        far = max(center, size - center)
        return far if lower == "farthest-side" else near
    return _length(token, box, horizontal=horizontal)


def _circle_side(cx: float, cy: float, box: tuple[float, float], *, farthest: bool) -> float:
    distances = _side_distances(cx, cy, box[0], box[1])
    return max(distances) if farthest else min(distances)


def _side_distances(x: float, y: float, width: float, height: float) -> list[float]:
    return [abs(x), abs(width - x), abs(y), abs(height - y)]


def _corner_distances(x: float, y: float, width: float, height: float) -> list[float]:
    return [math.hypot(x - px, y - py) for px, py in ((0.0, 0.0), (width, 0.0), (0.0, height), (width, height))]


def _ray_hit(x: float, y: float, unit_x: float, unit_y: float, width: float, height: float) -> float:
    hits: list[float] = []
    if abs(unit_x) > _EPS:
        for edge in (0.0, width):
            time = (edge - x) / unit_x
            if time > _EPS and -_EPS <= y + unit_y * time <= height + _EPS:
                hits.append(time)
    if abs(unit_y) > _EPS:
        for edge in (0.0, height):
            time = (edge - y) / unit_y
            if time > _EPS and -_EPS <= x + unit_x * time <= width + _EPS:
                hits.append(time)
    return min(hits) if hits else 0.0


def _length(token: str, box: tuple[float, float] | None, *, horizontal: bool) -> float:
    lower = token.lower()
    if lower in {"0", "+0", "-0"}:
        return 0.0
    if lower.endswith("px"):
        return _finite(lower[:-2], "path")
    if lower.endswith("%"):
        if box is None:
            raise _Bad("box")
        basis = box[0] if horizontal else box[1]
        return _finite(lower[:-1], "path") * basis / 100.0
    raise _Bad("path")


def _position_token(token: str) -> bool:
    lower = token.lower()
    if lower in {"contain"} or lower in _RAY_SIZES:
        return False
    if lower in {"left", "right", "top", "bottom", "center", "0", "+0", "-0"}:
        return True
    if any(lower.endswith(unit) for unit in ("turn", "grad", "deg", "rad")) and lower != "0":
        return False
    return lower.endswith("px") or lower.endswith("%")


def _need_box(box: tuple[float, float] | None) -> tuple[float, float]:
    if box is None:
        raise _Bad("box")
    return box


def _box(width: object, height: object) -> tuple[float, float] | None:
    if width is None and height is None:
        return None
    if width is None or height is None or isinstance(width, bool) or isinstance(height, bool):
        raise _Bad("box")
    if not isinstance(width, (int, float, str)) or not isinstance(height, (int, float, str)):
        raise _Bad("box")
    box = (_finite(width, "box"), _finite(height, "box"))
    if box[0] < 0 or box[1] < 0:
        raise _Bad("box")
    return box


def _parse_distance(value: object) -> tuple[str, float]:
    if isinstance(value, bool) or value is None:
        raise _Bad("distance")
    if isinstance(value, (int, float)):
        number = float(value)
        if not math.isfinite(number):
            raise _Bad("distance")
        return "px", number
    if not isinstance(value, str):
        raise _Bad("distance")
    text = value.strip().lower()
    if text.endswith("%"):
        return "pct", _finite(text[:-1], "distance")
    if text.endswith("px"):
        return "px", _finite(text[:-2], "distance")
    if text in {"0", "+0", "-0"}:
        return "px", 0.0
    raise _Bad("distance")


def _parse_rotate(value: object) -> tuple[str, float]:
    if value is None:
        return "auto", 0.0
    if not isinstance(value, str):
        raise _Bad("rotate")
    parts = value.split()
    if not parts:
        raise _Bad("rotate")
    head = parts[0].lower()
    if head in {"auto", "reverse"}:
        if len(parts) == 1:
            return head, 0.0
        if len(parts) == 2:
            return head, _angle(parts[1])
        raise _Bad("rotate")
    if len(parts) == 1:
        return "fixed", _angle(parts[0])
    raise _Bad("rotate")


def _is_angle(token: str) -> bool:
    lower = token.lower()
    return lower in {"0", "+0", "-0"} or any(lower.endswith(unit) for unit in ("turn", "grad", "deg", "rad"))


def _angle(token: str) -> float:
    lower = token.strip().lower()
    for unit, scale in (("turn", 360.0), ("grad", 0.9), ("deg", 1.0), ("rad", 180.0 / math.pi)):
        if lower.endswith(unit) and lower != unit:
            return _finite(lower[: -len(unit)], "rotate") * scale
    if lower in {"0", "+0", "-0"}:
        return 0.0
    raise _Bad("rotate")


def _finite(value: object, reason: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise _Bad(reason)
    try:
        number = float(value)
    except ValueError:
        raise _Bad(reason) from None
    if not math.isfinite(number):
        raise _Bad(reason)
    return number


def _bearing(dx: float, dy: float) -> float | None:
    if math.hypot(dx, dy) <= _EPS:
        return None
    return math.degrees(math.atan2(dy, dx)) % 360.0


def _ellipse_length(rx: float, ry: float) -> float:
    length = _integrate(lambda theta: math.hypot(-rx * math.sin(theta), ry * math.cos(theta)), 0.0, math.tau)
    if not math.isfinite(length):
        raise _Bad("path")
    return length


def _theta_at(rx: float, ry: float, dist: float, total: float) -> float:
    if abs(rx - ry) <= 1e-12:
        radius = rx if rx > _EPS else 1.0
        return dist / radius
    if dist <= _EPS:
        return 0.0
    if dist >= total - _EPS:
        return math.tau
    lo = 0.0
    hi = math.tau
    for _ in range(64):
        mid = (lo + hi) * 0.5
        covered = _integrate(lambda theta: math.hypot(-rx * math.sin(theta), ry * math.cos(theta)), 0.0, mid)
        if covered < dist:
            lo = mid
        else:
            hi = mid
    return (lo + hi) * 0.5


def _curve_length(deriv, start: float, end: float) -> float:
    if end <= start:
        return 0.0
    return _integrate(lambda t: math.hypot(*deriv(t)), start, end)


def _integrate(func, start: float, end: float) -> float:
    if end <= start:
        return 0.0

    def adapt(
        left: float,
        right: float,
        f_left: float,
        f_mid: float,
        f_right: float,
        whole: float,
        depth: int,
    ) -> float:
        mid = (left + right) * 0.5
        left_mid = (left + mid) * 0.5
        right_mid = (mid + right) * 0.5
        f_left_mid = func(left_mid)
        f_right_mid = func(right_mid)
        left_area = (mid - left) / 6.0 * (f_left + 4.0 * f_left_mid + f_mid)
        right_area = (right - mid) / 6.0 * (f_mid + 4.0 * f_right_mid + f_right)
        if depth <= 0 or abs(left_area + right_area - whole) <= 15.0 * 1e-10 * max(1.0, abs(whole)):
            return left_area + right_area + (left_area + right_area - whole) / 15.0
        return adapt(left, mid, f_left, f_left_mid, f_mid, left_area, depth - 1) + adapt(
            mid, right, f_mid, f_right_mid, f_right, right_area, depth - 1
        )

    f_left = func(start)
    f_right = func(end)
    mid = (start + end) * 0.5
    f_mid = func(mid)
    whole = (end - start) / 6.0 * (f_left + 4.0 * f_mid + f_right)
    return adapt(start, end, f_left, f_mid, f_right, whole, 18)


def _resolved(
    x: float,
    y: float,
    tangent: float | None,
    length: float,
    closed: bool,
    spin: tuple[str, float],
) -> dict[str, object]:
    mode, extra = spin
    if mode == "fixed":
        angle = extra
    else:
        base = 0.0 if tangent is None else tangent
        if mode == "reverse":
            base += 180.0
        angle = base + extra
    return {
        "outcome": "resolved",
        "x": _num(x),
        "y": _num(y),
        "angle": _num(_wrap(angle)),
        "tangent": None if tangent is None else _num(_wrap(tangent)),
        "length": _num(length),
        "closed": closed,
        "reason": "",
    }


def _invalid(reason: str) -> dict[str, object]:
    return {
        "outcome": "invalid",
        "x": None,
        "y": None,
        "angle": None,
        "tangent": None,
        "length": None,
        "closed": None,
        "reason": reason,
    }


def _wrap(angle: float) -> float:
    value = angle % 360.0
    rounded = round(value, 9)
    if rounded >= 360.0 or rounded == 0.0:
        return 0.0
    return rounded


def _num(value: float) -> int | float:
    cleaned = round(float(value), 9)
    if cleaned == 0:
        return 0
    if cleaned == math.trunc(cleaned):
        return int(cleaned)
    return cleaned
