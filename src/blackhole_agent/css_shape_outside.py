"""Float area of a CSS shape-outside clipped to the margin box.

CSS Shapes Level 1. ``shape-margin`` expands the shape by a perpendicular
offset, with a disk at every sharp corner, and the result is clipped to the
margin box. A shape can only shrink the float area. A contact of zero height
does not shorten a line. Left floats use the rightmost x of that area; right
floats use the leftmost x. Percentages in a basic shape resolve against the
reference box. The reference box here is the margin box; other boxes are
rejected. ``inset()`` rounding and a positive ``shape-margin`` on an ellipse
are rejected rather than approximated.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

_BOXES = frozenset({"margin-box", "border-box", "padding-box", "content-box"})
_FUNCTIONS = frozenset({"circle", "ellipse", "inset", "polygon"})
_FILL = frozenset({"nonzero", "evenodd"})


class ShapeError(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class Prepared:
    kind: str
    cx: float = 0.0
    cy: float = 0.0
    rx: float = 0.0
    ry: float = 0.0
    points: tuple[tuple[float, float], ...] = ()
    margin: float = 0.0

    def events(self, line_height: float) -> list[float]:
        marks: list[float] = []
        if self.kind == "circle":
            marks.extend((self.cy - self.rx, self.cy + self.rx, self.cy))
        elif self.kind == "ellipse":
            marks.extend((self.cy - self.ry, self.cy + self.ry, self.cy))
        else:
            for _x, y in self.points:
                marks.append(y)
                if self.margin > 0:
                    marks.append(y - self.margin)
                    marks.append(y + self.margin)
        found: list[float] = []
        for mark in marks:
            found.append(mark)
            found.append(mark - line_height)
        return found

    def span(self, y0: float, y1: float) -> tuple[float, float] | None:
        if self.kind == "circle":
            return _disk_span(self.cx, self.cy, self.rx, y0, y1)
        if self.kind == "ellipse":
            return _ellipse_span(self.cx, self.cy, self.rx, self.ry, y0, y1)
        if self.margin > 0:
            return _offset_span(self.points, self.margin, y0, y1)
        return _poly_span(self.points, y0, y1)


def prepare_shape(shape: str, width: float, height: float, margin: float) -> Prepared:
    """Parse one shape-outside value in the margin box of ``width`` by ``height``."""

    if not math.isfinite(margin) or margin < 0:
        raise ShapeError("shape_margin")
    tokens = _tokenize(shape)
    body: list[str] = []
    saw_box = False
    for token in tokens:
        if token in _BOXES:
            if saw_box or token != "margin-box":
                raise ShapeError("reference" if token != "margin-box" else "shape")
            saw_box = True
            continue
        body.append(token)
    if not body:
        return _rectangle(0.0, 0.0, width, height, 0.0)
    if (
        len(body) < 3
        or body[0] not in _FUNCTIONS
        or body[1] != "("
        or body[-1] != ")"
        or body.count("(") != 1
        or body.count(")") != 1
    ):
        raise ShapeError("shape")
    inner = body[2:-1]
    if body[0] == "circle":
        return _circle(inner, width, height, margin)
    if body[0] == "ellipse":
        return _ellipse(inner, width, height, margin)
    if body[0] == "inset":
        return _inset(inner, width, height, margin)
    return _polygon(inner, width, height, margin)


def exclusion_x_range(
    width: float,
    height: float,
    shape: Prepared,
    y0: float,
    y1: float,
) -> tuple[float, float] | None:
    """Local x edges of the clipped float area on the closed span ``[y0, y1]``."""

    if width < 0 or height <= 0 or y1 < y0:
        return None
    lo = max(y0, 0.0)
    hi = min(y1, height)
    if hi <= lo:
        return None
    span = shape.span(lo, hi)
    if span is None:
        return None
    left = max(span[0], 0.0)
    right = min(span[1], width)
    if right < left:
        return None
    return left, right


def _circle(inner: list[str], width: float, height: float, margin: float) -> Prepared:
    radius_tokens, position = _split_at(inner)
    cx, cy = _position(position, width, height)
    if not radius_tokens:
        radius = _circle_side(cx, cy, width, height, farthest=False)
    elif len(radius_tokens) == 1:
        radius = _circle_radius(radius_tokens[0], cx, cy, width, height)
    else:
        raise ShapeError("shape")
    if radius < 0:
        raise ShapeError("shape")
    grown = radius + margin
    return Prepared(kind="circle", cx=cx, cy=cy, rx=grown, ry=grown)


def _ellipse(inner: list[str], width: float, height: float, margin: float) -> Prepared:
    if margin > 0:
        raise ShapeError("shape_margin")
    radius_tokens, position = _split_at(inner)
    if len(radius_tokens) != 2:
        raise ShapeError("shape")
    cx, cy = _position(position, width, height)
    rx = _ellipse_radius(radius_tokens[0], cx, width, horizontal=True)
    ry = _ellipse_radius(radius_tokens[1], cy, height, horizontal=False)
    if rx < 0 or ry < 0:
        raise ShapeError("shape")
    return Prepared(kind="ellipse", cx=cx, cy=cy, rx=rx, ry=ry)


def _inset(inner: list[str], width: float, height: float, margin: float) -> Prepared:
    if any(token == "round" for token in inner):
        raise ShapeError("shape")
    if not inner or len(inner) > 4 or any(token in {",", "at"} for token in inner):
        raise ShapeError("shape")
    top, right, bottom, left = _inset_edges(inner, width, height)
    return _rectangle(left, top, width - right, height - bottom, margin)


def _polygon(inner: list[str], width: float, height: float, margin: float) -> Prepared:
    tokens = list(inner)
    if tokens and tokens[0] in _FILL:
        if len(tokens) < 2 or tokens[1] != ",":
            raise ShapeError("shape")
        tokens = tokens[2:]
    groups = _split_commas(tokens)
    if len(groups) < 3:
        raise ShapeError("shape")
    points: list[tuple[float, float]] = []
    for group in groups:
        if len(group) != 2:
            raise ShapeError("shape")
        points.append((_length(group[0], width), _length(group[1], height)))
    return Prepared(kind="polygon", points=tuple(points), margin=margin)


def _rectangle(left: float, top: float, right: float, bottom: float, margin: float) -> Prepared:
    if left > right or top > bottom:
        return Prepared(kind="polygon", points=(), margin=0.0)
    if left == right or top == bottom:
        return Prepared(kind="polygon", points=((left, top), (right, bottom)), margin=margin)
    return Prepared(
        kind="polygon",
        points=((left, top), (right, top), (right, bottom), (left, bottom)),
        margin=margin,
    )


def _inset_edges(tokens: list[str], width: float, height: float) -> tuple[float, float, float, float]:
    def vertical(token: str) -> float:
        return _length(token, height)

    def horizontal(token: str) -> float:
        return _length(token, width)

    if len(tokens) == 1:
        return vertical(tokens[0]), horizontal(tokens[0]), vertical(tokens[0]), horizontal(tokens[0])
    if len(tokens) == 2:
        return vertical(tokens[0]), horizontal(tokens[1]), vertical(tokens[0]), horizontal(tokens[1])
    if len(tokens) == 3:
        return vertical(tokens[0]), horizontal(tokens[1]), vertical(tokens[2]), horizontal(tokens[1])
    return vertical(tokens[0]), horizontal(tokens[1]), vertical(tokens[2]), horizontal(tokens[3])


def _circle_radius(token: str, cx: float, cy: float, width: float, height: float) -> float:
    if token == "closest-side":
        return _circle_side(cx, cy, width, height, farthest=False)
    if token == "farthest-side":
        return _circle_side(cx, cy, width, height, farthest=True)
    if token.endswith("%"):
        return _number(token[:-1]) / 100 * math.hypot(width, height) / math.sqrt(2)
    return _length(token, width)


def _ellipse_radius(token: str, center: float, size: float, *, horizontal: bool) -> float:
    del horizontal
    if token == "closest-side":
        return min(center, size - center)
    if token == "farthest-side":
        return max(center, size - center)
    return _length(token, size)


def _circle_side(cx: float, cy: float, width: float, height: float, *, farthest: bool) -> float:
    distances = (cx, width - cx, cy, height - cy)
    return max(distances) if farthest else min(distances)


def _position(tokens: list[str], width: float, height: float) -> tuple[float, float]:
    if not tokens:
        return width / 2, height / 2
    if tokens == ["center"]:
        return width / 2, height / 2
    if len(tokens) != 2:
        raise ShapeError("shape")
    horizontal, vertical = tokens
    if _vertical_keyword(horizontal) and _horizontal_keyword(vertical):
        horizontal, vertical = vertical, horizontal
    return _axis(horizontal, width, horizontal_axis=True), _axis(vertical, height, horizontal_axis=False)


def _axis(token: str, size: float, *, horizontal_axis: bool) -> float:
    if token == "center":
        return size / 2
    if horizontal_axis and token == "left":
        return 0.0
    if horizontal_axis and token == "right":
        return size
    if not horizontal_axis and token == "top":
        return 0.0
    if not horizontal_axis and token == "bottom":
        return size
    if token in {"left", "right", "top", "bottom"}:
        raise ShapeError("shape")
    return _length(token, size)


def _horizontal_keyword(token: str) -> bool:
    return token in {"left", "right"}


def _vertical_keyword(token: str) -> bool:
    return token in {"top", "bottom"}


def _split_at(tokens: list[str]) -> tuple[list[str], list[str]]:
    if tokens.count("at") > 1:
        raise ShapeError("shape")
    if "at" not in tokens:
        return tokens, []
    index = tokens.index("at")
    return tokens[:index], tokens[index + 1 :]


def _split_commas(tokens: list[str]) -> list[list[str]]:
    groups: list[list[str]] = []
    current: list[str] = []
    for token in tokens:
        if token == ",":
            if not current:
                raise ShapeError("shape")
            groups.append(current)
            current = []
            continue
        current.append(token)
    if current:
        groups.append(current)
    if not groups:
        raise ShapeError("shape")
    return groups


def _length(token: str, size: float) -> float:
    if token.endswith("%"):
        return _number(token[:-1]) * size / 100
    if token.endswith("px"):
        return _number(token[:-2])
    if token == "0":
        return 0.0
    raise ShapeError("shape")


def _number(token: str) -> float:
    try:
        value = float(token)
    except ValueError as exc:
        raise ShapeError("shape") from exc
    if not math.isfinite(value):
        raise ShapeError("shape")
    return value


def _tokenize(text: str) -> list[str]:
    if not isinstance(text, str):
        raise ShapeError("shape")
    tokens: list[str] = []
    index = 0
    length = len(text)
    while index < length:
        if text.startswith("/*", index):
            end = text.find("*/", index + 2)
            if end < 0:
                raise ShapeError("shape")
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
        end = index + 1
        while end < length and not text[end].isspace() and text[end] not in "(),":
            end += 1
        tokens.append(text[index:end])
        index = end
    return tokens


def _edge_pairs(points: tuple[tuple[float, float], ...]) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    count = len(points)
    if count < 2:
        return []
    last = count if count > 2 else 1
    return [(points[index], points[(index + 1) % count]) for index in range(last)]


def _poly_span(points: tuple[tuple[float, float], ...], y0: float, y1: float) -> tuple[float, float] | None:
    if y1 <= y0:
        return None
    xs: list[float] = []
    ys: list[float] = []

    def add(x: float, y: float) -> None:
        if y0 <= y <= y1:
            xs.append(x)
            ys.append(y)

    for (x1, yy1), (x2, yy2) in _edge_pairs(points):
        add(x1, yy1)
        if yy1 == yy2:
            add(x2, yy2)
            continue
        for edge_y in (y0, y1):
            if (yy1 <= edge_y <= yy2) or (yy2 <= edge_y <= yy1):
                t = (edge_y - yy1) / (yy2 - yy1)
                add(x1 + t * (x2 - x1), edge_y)
    if not ys or max(ys) <= min(ys):
        return None
    return min(xs), max(xs)


def _offset_span(
    points: tuple[tuple[float, float], ...],
    margin: float,
    y0: float,
    y1: float,
) -> tuple[float, float] | None:
    spans = [_poly_span(points, y0, y1)]
    for x, y in points:
        spans.append(_disk_span(x, y, margin, y0, y1))
    for (x1, yy1), (x2, yy2) in _edge_pairs(points):
        spans.append(_capsule(x1, yy1, x2, yy2, margin, y0, y1))
    return _union(spans)


def _capsule(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    margin: float,
    y0: float,
    y1b: float,
) -> tuple[float, float] | None:
    dx = x2 - x1
    dy = y2 - y1
    length = math.hypot(dx, dy)
    if length == 0 or margin <= 0:
        return None
    nx = -dy / length
    ny = dx / length
    spans = []
    for sign in (1.0, -1.0):
        ox = nx * margin * sign
        oy = ny * margin * sign
        spans.append(_segment_span(x1 + ox, y1 + oy, x2 + ox, y2 + oy, y0, y1b))
    return _union(spans)


def _segment_span(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    y0: float,
    y1b: float,
) -> tuple[float, float] | None:
    if y1 == y2 or y1b <= y0:
        return None
    if y1 > y2:
        x1, y1, x2, y2 = x2, y2, x1, y1
    if y2 <= y0 or y1 >= y1b:
        return None
    lo = max(y1, y0)
    hi = min(y2, y1b)
    if hi <= lo:
        return None
    span = y2 - y1

    def x_at(y: float) -> float:
        return x1 + (y - y1) * (x2 - x1) / span

    left = x_at(lo)
    right = x_at(hi)
    return min(left, right), max(left, right)


def _disk_span(cx: float, cy: float, radius: float, y0: float, y1: float) -> tuple[float, float] | None:
    if radius <= 0 or y1 <= y0:
        return None
    lo = max(y0, cy - radius)
    hi = min(y1, cy + radius)
    if hi <= lo:
        return None
    nearest = min(max(cy, lo), hi)
    half = math.sqrt(max(0.0, radius * radius - (nearest - cy) * (nearest - cy)))
    return cx - half, cx + half


def _ellipse_span(
    cx: float,
    cy: float,
    rx: float,
    ry: float,
    y0: float,
    y1: float,
) -> tuple[float, float] | None:
    if rx < 0 or ry <= 0 or y1 <= y0:
        return None
    lo = max(y0, cy - ry)
    hi = min(y1, cy + ry)
    if hi <= lo:
        return None
    nearest = min(max(cy, lo), hi)
    dy = (nearest - cy) / ry
    if abs(dy) > 1:
        return None
    half = rx * math.sqrt(max(0.0, 1 - dy * dy))
    return cx - half, cx + half


def _union(spans: list[tuple[float, float] | None]) -> tuple[float, float] | None:
    valid = [span for span in spans if span is not None]
    if not valid:
        return None
    return min(span[0] for span in valid), max(span[1] for span in valid)
