"""Lay out one CSS inline line from the strut and its inline boxes.

CSS 2.1 §10.8. The strut is a zero-width box with the block's font metrics
and line-height, so a shorter child cannot collapse the line. A text box
contributes its own line-height, half-leading split above the ascent and
below the descent. An atomic box contributes its margin box. Baseline
alignment puts that margin edge on the parent baseline, and a positive
length raises the box. Middle aligns the box midpoint with the baseline
plus half the parent's x-height. Text-top and text-bottom meet the strut's
content edges, leaving the half-leading outside them.

Top and bottom are placed after that extent. The line is only as tall as
the larger of the aligned extent, the tallest top box, and the tallest
bottom box. When the bottom box is what sets that height, the aligned
extent stays on the bottom edge. Otherwise it stays on the top edge. Top
boxes then sit on the line top and bottom boxes on the line bottom. CSS 2.1
does not define that choice when both edge boxes are taller than the
aligned extent; this rule does. ``sub`` and ``super`` are rejected because
the specification does not define their offset.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

_KINDS = frozenset({"text", "atomic"})
_WORDS = frozenset({"baseline", "middle", "text-top", "text-bottom", "top", "bottom"})
_TEXT_FIELDS = frozenset({"id", "kind", "vertical_align", "ascent", "descent", "line_height"})
_ATOMIC_FIELDS = frozenset(
    {"id", "kind", "vertical_align", "height", "margin_top", "margin_bottom"}
)
_STRUT_FIELDS = frozenset({"ascent", "descent", "line_height", "x_height"})
_EDGE = frozenset({"top", "bottom"})
_INF = math.inf


class _Invalid(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass
class _Box:
    id: str
    align: str
    height: float
    top: float


def layout_inline_line(strut: object, boxes: object = ()) -> dict[str, object]:
    """Return the line height, the baseline, and each box top.

    ``strut`` carries ``ascent``, ``descent``, ``line_height``, and
    ``x_height``. Each box has ``id`` and ``kind`` of ``text`` or
    ``atomic``. Text carries its own ``ascent``, ``descent``, and
    ``line_height``. Atomic carries ``height`` and optional non-negative
    ``margin_top`` and ``margin_bottom``. ``vertical_align`` is a keyword
    or a length; a missing value is baseline. Coordinates increase downward
    from the line top. The baseline is that same offset.
    """

    try:
        ascent, descent, line_height, x_height = _strut(strut)
        parsed = _boxes(boxes)
        strut_top, strut_bottom = _text_bounds(0.0, ascent, descent, line_height)
        for box in parsed:
            if box.align not in _EDGE:
                box.top = _aligned_top(box, ascent, descent, x_height)
        line_top, line_bottom = _line_edges(parsed, strut_top, strut_bottom)
    except _Invalid as exc:
        return _invalid(exc.reason)

    placed = []
    for box in parsed:
        if box.align == "top":
            top = line_top
        elif box.align == "bottom":
            top = line_bottom - box.height
        else:
            top = box.top
        placed.append(
            {
                "id": box.id,
                "top": _number(top - line_top),
                "height": _number(box.height),
            }
        )
    return {
        "outcome": "resolved",
        "reason": None,
        "line_height": _number(line_bottom - line_top),
        "baseline": _number(-line_top),
        "boxes": placed,
    }


def _line_edges(boxes: list[_Box], strut_top: float, strut_bottom: float) -> tuple[float, float]:
    aligned_top = strut_top
    aligned_bottom = strut_bottom
    top_height = 0.0
    bottom_height = 0.0
    for box in boxes:
        if box.align == "top":
            top_height = max(top_height, box.height)
        elif box.align == "bottom":
            bottom_height = max(bottom_height, box.height)
        else:
            aligned_top = min(aligned_top, box.top)
            aligned_bottom = max(aligned_bottom, box.top + box.height)
    aligned_height = aligned_bottom - aligned_top
    final_height = max(aligned_height, top_height, bottom_height)
    if bottom_height >= final_height and top_height < final_height:
        return aligned_bottom - final_height, aligned_bottom
    return aligned_top, aligned_top + final_height


def _aligned_top(box: _Box, ascent: float, descent: float, x_height: float) -> float:
    if box.align == "middle":
        return (x_height / 2.0) - (box.height / 2.0)
    if box.align == "text-top":
        return -ascent
    if box.align == "text-bottom":
        return descent - box.height
    return box.top


def _text_bounds(baseline: float, ascent: float, descent: float, line_height: float) -> tuple[float, float]:
    half = (line_height - ascent - descent) / 2.0
    return baseline - ascent - half, baseline + descent + half


def _strut(value: object) -> tuple[float, float, float, float]:
    if not isinstance(value, dict):
        raise _Invalid("strut")
    unknown = set(value) - _STRUT_FIELDS
    if unknown or len(value) != len(_STRUT_FIELDS):
        raise _Invalid("strut")
    ascent = _length(value.get("ascent"), "strut ascent")
    descent = _length(value.get("descent"), "strut descent")
    line_height = _length(value.get("line_height"), "strut line_height")
    x_height = _length(value.get("x_height"), "strut x_height")
    return ascent, descent, line_height, x_height


def _boxes(value: object) -> list[_Box]:
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise _Invalid("boxes")
    boxes = [_box(item, index) for index, item in enumerate(value)]
    seen: set[str] = set()
    for box in boxes:
        if box.id in seen:
            raise _Invalid("boxes")
        seen.add(box.id)
    return boxes


def _box(value: object, index: int) -> _Box:
    if not isinstance(value, dict):
        raise _Invalid(f"box {index}")
    name = value.get("id")
    if not isinstance(name, str) or not name.strip() or name != name.strip():
        raise _Invalid(f"box {index}")
    kind = value.get("kind")
    if kind not in _KINDS:
        raise _Invalid(f"box {index} kind")
    fields = _TEXT_FIELDS if kind == "text" else _ATOMIC_FIELDS
    if set(value) - fields:
        raise _Invalid(f"box {index}")
    align, shift = _alignment(value.get("vertical_align", "baseline"), f"box {index} vertical_align")
    if kind == "text":
        ascent = _length(value.get("ascent"), f"box {index} ascent")
        descent = _length(value.get("descent"), f"box {index} descent")
        line_height = _length(value.get("line_height"), f"box {index} line_height")
        top, bottom = _text_bounds(-shift, ascent, descent, line_height)
        return _Box(name, align, bottom - top, top)
    height = _length(value.get("height"), f"box {index} height")
    margin_top = _length(value.get("margin_top", 0), f"box {index} margin_top")
    margin_bottom = _length(value.get("margin_bottom", 0), f"box {index} margin_bottom")
    margin_box = margin_top + height + margin_bottom
    if align == "baseline":
        top = -margin_box - shift
    else:
        top = 0.0
    return _Box(name, align, margin_box, top)


def _alignment(value: object, name: str) -> tuple[str, float]:
    if isinstance(value, str):
        text = value.strip().lower()
        if text not in _WORDS:
            raise _Invalid(name)
        return text, 0.0
    return "baseline", _signed(value, name)


def _length(value: object, name: str) -> float:
    number = _signed(value, name)
    if number < 0.0:
        raise _Invalid(name)
    return number


def _signed(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _Invalid(name)
    number = float(value)
    if number != number or number in {_INF, -_INF}:
        raise _Invalid(name)
    return number


def _number(value: float) -> int | float:
    nearest = round(value)
    if abs(value - nearest) <= 1e-9:
        return int(nearest)
    return value


def _invalid(reason: str) -> dict[str, object]:
    return {
        "outcome": "invalid",
        "reason": reason,
        "line_height": None,
        "baseline": None,
        "boxes": None,
    }
