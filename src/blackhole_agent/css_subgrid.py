"""Place stretched items on the parent tracks a CSS subgrid shares.

CSS Grid Level 2 §9. The subgrid does not size its own tracks. Each of its
tracks is the parent track it spans, parent gutters included. ``subgrid_gap``
of ``normal`` keeps that parent gutter. Any other gap differs by the same
amount on both sides of the gutter: half of ``subgrid_gap - parent gap`` is
an extra margin on every item side that faces a gutter inside the subgrid.
The outer sides keep the subgrid's own edge (margin, border, padding, and
scrollbar gutter summed by the caller).

The published 300px example is tracks ``100`` and ``150`` with a parent gap
of ``50``. Gap ``0`` places the items at sizes ``125`` and ``175`` so they
touch. Gap ``75`` places them at ``87.5`` and ``137.5``. Gap ``normal``
leaves ``100`` and ``150``.

Items use subgrid line numbers. A negative line counts back from the explicit
grid's end. A line past that grid is clamped to it; the subgrid grows no
implicit track. ``2 / span 3`` on a one-track subgrid occupies that only
track. This places stretched items on one axis. It does not run the
track-sizing algorithm or honor ``justify-self``.
"""

from __future__ import annotations

_NORMAL = "normal"


class _Invalid(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def place_subgrid_items(
    tracks: object,
    items: object,
    *,
    gap: object = 0,
    span_start: object = 1,
    span: object | None = None,
    subgrid_gap: object = _NORMAL,
    edge_start: object = 0,
    edge_end: object = 0,
) -> dict[str, object]:
    """Return each stretched item's start and size in parent-track coordinates.

    ``tracks`` are the parent sizes and ``gap`` is the parent gutter. The
    subgrid covers ``span`` tracks beginning at the 1-based ``span_start``.
    Each item maps ``id``, ``start`` (a subgrid line number), and ``span``.
    Coordinates start at the parent grid's content edge. The first parent
    track begins at 0.
    """

    try:
        return _place(tracks, items, gap, span_start, span, subgrid_gap, edge_start, edge_end)
    except _Invalid as exc:
        return {"outcome": "invalid", "items": None, "reason": exc.reason}


def _place(
    tracks: object,
    items: object,
    gap: object,
    span_start: object,
    span: object | None,
    subgrid_gap: object,
    edge_start: object,
    edge_end: object,
) -> dict[str, object]:
    sizes = _tracks(tracks)
    parent_gap = _nonneg(gap, "gap")
    begin = _index(span_start, "span_start")
    covered = _index(len(sizes) - begin + 1, "span") if span is None else _index(span, "span")
    if begin + covered - 1 > len(sizes):
        raise _Invalid("span is outside the parent grid")
    sub_gap = _subgrid_gap(subgrid_gap)
    start_edge = _signed(edge_start, "edge_start")
    end_edge = _signed(edge_end, "edge_end")
    half = 0.0 if sub_gap is None else (sub_gap - parent_gap) / 2.0
    positions = _positions(sizes, parent_gap)
    last_line = covered + 1
    placed: list[dict[str, object]] = []
    for item in _items(items):
        line, item_span = _clamp(item["start"], item["span"], last_line)
        local = line - 1
        parent = begin - 1 + local
        area_start = positions[parent][0]
        last = positions[parent + item_span - 1]
        area_end = last[0] + last[1]
        extra_start = start_edge if local == 0 else half
        extra_end = end_edge if local + item_span == covered else half
        size = area_end - area_start - extra_start - extra_end
        if size < 0:
            size = 0.0
        placed.append(
            {
                "id": item["id"],
                "start": _number(area_start + extra_start),
                "size": _number(size),
                "line_start": line,
                "line_end": line + item_span,
            }
        )
    return {"outcome": "placed", "items": placed}


def _positions(tracks: list[float], gap: float) -> list[tuple[float, float]]:
    positions: list[tuple[float, float]] = []
    cursor = 0.0
    for size in tracks:
        positions.append((cursor, size))
        cursor += size + gap
    return positions


def _clamp(start: int, span: int, last_line: int) -> tuple[int, int]:
    """Resolve one area onto the explicit subgrid and return its track span."""

    if start < 0:
        start = last_line + 1 + start
    end = start + span
    if end > last_line:
        end = last_line
    if start < 1:
        start = 1
    if start >= last_line or end <= start:
        if start >= last_line:
            start = last_line - 1
        else:
            start = 1
        end = start + 1
    return start, end - start


def _items(value: object) -> list[dict[str, int | str]]:
    if not isinstance(value, list):
        raise _Invalid("items are invalid")
    parsed: list[dict[str, int | str]] = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            raise _Invalid(f"item {index} is invalid")
        ident = item.get("id")
        if not isinstance(ident, str) or not ident or ident.strip() != ident:
            raise _Invalid(f"item {index} id is invalid")
        parsed.append(
            {
                "id": ident,
                "start": _line(item.get("start", 1), f"item {index} start"),
                "span": _index(item.get("span", 1), f"item {index} span"),
            }
        )
    return parsed


def _line(value: object, name: str) -> int:
    number = _integer(value, name)
    if number == 0:
        raise _Invalid(f"{name} is invalid")
    return number


def _tracks(value: object) -> list[float]:
    if not isinstance(value, list) or not value:
        raise _Invalid("tracks are invalid")
    return [_nonneg(item, "track") for item in value]


def _subgrid_gap(value: object) -> float | None:
    if value == _NORMAL:
        return None
    return _nonneg(value, "subgrid_gap")


def _index(value: object, name: str) -> int:
    number = _integer(value, name)
    if number < 1:
        raise _Invalid(f"{name} is invalid")
    return number


def _integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise _Invalid(f"{name} is invalid")
    return value


def _signed(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _Invalid(f"{name} is invalid")
    number = float(value)
    if number != number or number in {float("inf"), float("-inf")}:
        raise _Invalid(f"{name} is invalid")
    return number


def _nonneg(value: object, name: str) -> float:
    number = _signed(value, name)
    if number < 0:
        raise _Invalid(f"{name} is invalid")
    return number


def _number(value: float) -> int | float:
    nearest = round(value)
    if abs(value - nearest) <= 1e-9:
        return int(nearest)
    return value
