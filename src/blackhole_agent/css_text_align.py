"""Align inline boxes inside one already broken line.

CSS Text Level 3 aligns the inline content of a line box when that content
does not fill it. ``start`` and ``end`` follow ``direction``. ``left`` and
``right`` stay on those physical sides, including when ``match-parent``
computes against the parent direction. ``center`` splits the leftover.

``justify`` and ``justify-all`` distribute positive free space in equal
shares. ``inter-word`` and the ``auto`` method expand only an interior
``space_after`` that is already a word separator. ``inter-character`` also
opens a boundary whose separator width is zero. ``text-justify: none``
does not expand. A last line uses ``text-align-last``; ``auto`` keeps the
line alignment, except a ``justify`` line falls back to the start edge.
``justify-all`` still justifies that last line. Free space that is zero or
negative is not compressed.

Under ``normal``, ``nowrap``, and ``pre-line``, the trailing separator is
removed before alignment and is not an opportunity. Under ``pre``,
``pre-wrap``, and ``break-spaces``, that separator stays in the content
width and still does not expand. This is one line, not a line breaker.
"""

from __future__ import annotations

_ALIGNS = frozenset(
    {"start", "end", "left", "right", "center", "justify", "justify-all", "match-parent"}
)
_LAST = frozenset({"auto", "start", "end", "left", "right", "center", "justify"})
_JUSTIFY = frozenset({"auto", "none", "inter-word", "inter-character"})
_DIRECTIONS = frozenset({"ltr", "rtl"})
_WHITE = frozenset({"normal", "nowrap", "pre", "pre-wrap", "pre-line", "break-spaces"})
_DISCARD_TRAILING = frozenset({"normal", "nowrap", "pre-line"})


class _Invalid(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class _Item:
    def __init__(self, item_id: str, width: float, space_after: float) -> None:
        self.id = item_id
        self.width = width
        self.space_after = space_after


def align_inline_line(
    line_width: object,
    items: object,
    *,
    text_align: object = "start",
    text_align_last: object = "auto",
    text_justify: object = "auto",
    direction: object = "ltr",
    parent_direction: object = None,
    white_space: object = "normal",
    last_line: object = False,
) -> dict[str, object]:
    """Return each box's x inside ``line_width``.

    Coordinates grow from the physical left of the line. ``items`` are the
    boxes in logical order. Each has ``id``, a non-negative ``width``, and
    an optional non-negative ``space_after``. A positive interior
    ``space_after`` is one word separator. The last ``space_after`` is the
    trailing separator.
    """

    try:
        return _align(
            line_width,
            items,
            text_align=text_align,
            text_align_last=text_align_last,
            text_justify=text_justify,
            direction=direction,
            parent_direction=parent_direction,
            white_space=white_space,
            last_line=last_line,
        )
    except _Invalid as exc:
        return _invalid(exc.reason)


def _align(
    line_width: object,
    items: object,
    *,
    text_align: object,
    text_align_last: object,
    text_justify: object,
    direction: object,
    parent_direction: object,
    white_space: object,
    last_line: object,
) -> dict[str, object]:
    width = _nonneg(line_width, "line width")
    flow = _choice(direction, _DIRECTIONS, "direction")
    align = _choice(text_align, _ALIGNS, "text-align")
    last_align = _choice(text_align_last, _LAST, "text-align-last")
    justify = _choice(text_justify, _JUSTIFY, "text-justify")
    spacing = _choice(white_space, _WHITE, "white-space")
    if not isinstance(last_line, bool):
        raise _Invalid("last line is invalid")
    parent = _parent(parent_direction, align)
    boxes = _items(items)
    trailing = boxes[-1].space_after if boxes else 0.0
    included = bool(boxes) and spacing not in _DISCARD_TRAILING and trailing > 0.0
    gaps = _gaps(boxes)
    method = _method(align, last_align, last_line, flow, parent)
    character = method == "justify" and justify == "inter-character"
    word = method == "justify" and justify in {"auto", "inter-word"}
    opportunities = _opportunities(gaps, character=character, word=word)
    justified = False
    if opportunities and width > _content(boxes, gaps, included, trailing):
        _expand(gaps, width - _content(boxes, gaps, included, trailing), opportunities)
        justified = True
        method = "justify"
    elif method == "justify":
        method = "left" if flow == "ltr" else "right"
    content = _content(boxes, gaps, included, trailing)
    pack = _pack(method, width, content)
    placed = _place(boxes, gaps, pack, content, flow)
    trailing_x = None
    if included:
        trailing_x = _number(pack if flow == "rtl" else pack + content - trailing)
    return {
        "outcome": "aligned",
        "alignment": method,
        "justified": justified,
        "direction": flow,
        "white_space": spacing,
        "line_width": _number(width),
        "content_width": _number(content),
        "trailing_included": included,
        "trailing_width": _number(trailing) if boxes else 0,
        "trailing_x": trailing_x,
        "items": placed,
    }


def _method(align: str, last_align: str, last_line: bool, flow: str, parent: str | None) -> str:
    if align == "justify-all":
        chosen = "justify"
    elif last_line:
        if last_align == "auto":
            chosen = "start" if align == "justify" else align
        else:
            chosen = last_align
    else:
        chosen = align
    if chosen == "start":
        return "left" if flow == "ltr" else "right"
    if chosen == "end":
        return "right" if flow == "ltr" else "left"
    if chosen == "match-parent":
        if parent is None:
            raise _Invalid("parent direction is required")
        return "left" if parent == "ltr" else "right"
    return chosen


def _parent(value: object, align: str) -> str | None:
    if value is None:
        if align == "match-parent":
            raise _Invalid("parent direction is required")
        return None
    return _choice(value, _DIRECTIONS, "parent direction")


def _items(value: object) -> list[_Item]:
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise _Invalid("items are invalid")
    items: list[_Item] = []
    seen: set[str] = set()
    for entry in value:
        if not isinstance(entry, dict):
            raise _Invalid("items are invalid")
        item_id = entry.get("id")
        if not isinstance(item_id, str) or not item_id.strip():
            raise _Invalid("item id is invalid")
        if item_id in seen:
            raise _Invalid("item id is duplicated")
        seen.add(item_id)
        items.append(
            _Item(
                item_id,
                _nonneg(entry.get("width", 0), "item width"),
                _nonneg(entry.get("space_after", 0), "space after"),
            )
        )
    return items


def _gaps(items: list[_Item]) -> list[float]:
    gaps = [0.0]
    for item in items[:-1]:
        gaps.append(item.space_after)
    return gaps


def _opportunities(gaps: list[float], *, character: bool, word: bool) -> list[int]:
    found: list[int] = []
    for index, gap in enumerate(gaps):
        if index == 0:
            continue
        if character or (word and gap > 0.0):
            found.append(index)
    return found


def _expand(gaps: list[float], free: float, opportunities: list[int]) -> None:
    count = len(opportunities)
    share = free / count
    consumed = 0.0
    for offset, index in enumerate(opportunities):
        extra = free - consumed if offset == count - 1 else share
        gaps[index] += extra
        consumed += extra


def _content(items: list[_Item], gaps: list[float], included: bool, trailing: float) -> float:
    total = sum(item.width for item in items) + sum(gaps)
    if included:
        total += trailing
    return total


def _pack(method: str, line_width: float, content: float) -> float:
    if method == "right":
        return line_width - content
    if method == "center":
        return (line_width - content) / 2.0
    return 0.0


def _place(
    items: list[_Item],
    gaps: list[float],
    pack: float,
    content: float,
    direction: str,
) -> list[dict[str, object]]:
    placed: list[dict[str, object]] = []
    if direction == "ltr":
        cursor = pack
        for item, gap in zip(items, gaps):
            cursor += gap
            placed.append({"id": item.id, "x": _number(cursor), "width": _number(item.width)})
            cursor += item.width
        return placed
    # The physical right is the inline start. A preserved trailing separator
    # is the unused span on the inline end, so it stays on the physical left.
    cursor = pack + content
    for index, item in enumerate(items):
        cursor -= item.width
        placed.append({"id": item.id, "x": _number(cursor), "width": _number(item.width)})
        if index + 1 < len(items):
            cursor -= gaps[index + 1]
    return placed


def _choice(value: object, allowed: frozenset[str], name: str) -> str:
    if not isinstance(value, str):
        raise _Invalid(f"{name} is invalid")
    token = " ".join(value.strip().lower().split())
    if token not in allowed:
        raise _Invalid(f"{name} is invalid")
    return token


def _nonneg(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _Invalid(f"{name} is invalid")
    number = float(value)
    if number != number or number in {float("inf"), float("-inf")}:
        raise _Invalid(f"{name} is invalid")
    if number < 0.0:
        raise _Invalid(f"{name} cannot be negative")
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
        "alignment": None,
        "justified": False,
        "direction": None,
        "white_space": None,
        "line_width": None,
        "content_width": None,
        "trailing_included": False,
        "trailing_width": None,
        "trailing_x": None,
        "items": None,
    }
