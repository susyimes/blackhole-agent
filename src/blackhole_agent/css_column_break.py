"""Fill one fixed-height CSS column row and honor column breaks.

CSS Multi-column ``column-fill: auto`` gives every column the same used
block size. CSS Fragmentation 3 then places unbreakable boxes in source
order. ``column``, ``always``, and ``all`` force the next box into the
next column. A forced break that would leave a column empty is dropped, and
two forced values on the same boundary are one break. ``page``, ``left``,
``right``, ``recto``, ``verso``, and ``region`` do not move a column.

``avoid`` and ``avoid-column`` keep the longest joined suffix with the next
box when that group fits in an empty column and the next box does not fit
in the space that remains. ``avoid-page`` and ``avoid-region`` do not.
A forced break wins over an avoid on the same boundary. A box taller than
the column stays in the column where it started and overflows it. Content
that still does not fit in the last column overflows that column instead of
opening another one. ``break-inside`` does not split an unbreakable box.
"""

from __future__ import annotations

from dataclasses import dataclass

_BREAKS = frozenset(
    {
        "auto",
        "avoid",
        "always",
        "all",
        "avoid-page",
        "page",
        "left",
        "right",
        "recto",
        "verso",
        "avoid-column",
        "column",
        "avoid-region",
        "region",
    }
)
_FORCED = frozenset({"always", "all", "column"})
_AVOID = frozenset({"avoid", "avoid-column"})
_FIELDS = frozenset({"id", "height", "break_before", "break_after", "break_inside"})


class _Invalid(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class _Piece:
    id: str
    height: int
    break_before: str
    break_after: str
    break_inside: str


def fragment_columns(
    column_count: object,
    column_block_size: object,
    fragments: object,
) -> dict[str, object]:
    """Place unbreakable boxes into a fixed-height column row.

    ``column_count`` is a positive integer. ``column_block_size`` is a
    non-negative integer. Each fragment has ``id``, ``height``, and optional
    ``break_before``, ``break_after``, and ``break_inside`` values from CSS
    Fragmentation 3. Heights are CSS pixels.
    """

    try:
        count = _length(column_count, "column_count", minimum=1)
        limit = _length(column_block_size, "column_block_size", minimum=0)
        items = _pieces(fragments)
    except _Invalid as exc:
        return _invalid(exc.reason)
    return {
        "outcome": "fragmented",
        "column_count": count,
        "column_block_size": limit,
        "boxes": _place(items, count, limit),
    }


def _place(items: list[_Piece], count: int, limit: int) -> list[dict[str, object]]:
    columns: list[list[_Piece]] = [[] for _ in range(count)]
    column = 0
    used = 0
    for index, piece in enumerate(items):
        previous = items[index - 1] if index else None
        force = previous is not None and (_forced(previous.break_after) or _forced(piece.break_before))
        avoid = previous is not None and not force and _avoided(previous, piece)
        if columns[column] and (force or used + piece.height > limit):
            if avoid and column + 1 < count and _suffix_count(columns[column], piece.height, limit):
                column, used = _move_suffix(columns, column, piece, limit)
                continue
            if column + 1 < count:
                column += 1
                used = 0
        columns[column].append(piece)
        used += piece.height
    return _boxes(items, columns, limit)


def _move_suffix(
    columns: list[list[_Piece]],
    column: int,
    piece: _Piece,
    limit: int,
) -> tuple[int, int]:
    taken = _suffix_count(columns[column], piece.height, limit)
    moved = columns[column][-taken:]
    del columns[column][-taken:]
    column += 1
    used = 0
    for item in moved:
        columns[column].append(item)
        used += item.height
    columns[column].append(piece)
    return column, used + piece.height


def _suffix_count(column: list[_Piece], incoming: int, limit: int) -> int:
    chain = 1
    while chain < len(column) and _joins(column[-chain - 1], column[-chain]):
        chain += 1
    total = incoming
    chosen = 0
    for size in range(1, chain + 1):
        total += column[-size].height
        if total <= limit:
            chosen = size
            continue
        break
    return chosen


def _joins(left: _Piece, right: _Piece) -> bool:
    if _forced(left.break_after) or _forced(right.break_before):
        return False
    return _avoided(left, right)


def _avoided(left: _Piece, right: _Piece) -> bool:
    return left.break_after in _AVOID or right.break_before in _AVOID


def _forced(value: str) -> bool:
    return value in _FORCED


def _boxes(items: list[_Piece], columns: list[list[_Piece]], limit: int) -> list[dict[str, object]]:
    located: dict[str, tuple[int, int]] = {}
    for index, column in enumerate(columns):
        offset = 0
        for item in column:
            located[item.id] = (index, offset)
            offset += item.height
    boxes: list[dict[str, object]] = []
    for item in items:
        column, offset = located[item.id]
        boxes.append(
            {
                "id": item.id,
                "column": column,
                "block": offset,
                "height": item.height,
                "overflow": offset + item.height > limit,
            }
        )
    return boxes


def _pieces(value: object) -> list[_Piece]:
    if type(value) is not list:
        raise _Invalid("fragments")
    parsed: list[_Piece] = []
    seen: set[str] = set()
    for raw in value:
        if type(raw) is not dict or not set(raw).issubset(_FIELDS):
            raise _Invalid("fragment")
        if "id" not in raw or "height" not in raw:
            raise _Invalid("fragment")
        ident = raw["id"]
        if type(ident) is not str or ident == "":
            raise _Invalid("id")
        if ident in seen:
            raise _Invalid("duplicate id")
        seen.add(ident)
        height = raw["height"]
        if type(height) is not int or height < 0:
            raise _Invalid("height")
        parsed.append(
            _Piece(
                ident,
                height,
                _break(raw.get("break_before", "auto"), "break_before"),
                _break(raw.get("break_after", "auto"), "break_after"),
                _break(raw.get("break_inside", "auto"), "break_inside"),
            )
        )
    return parsed


def _break(value: object, name: str) -> str:
    if type(value) is not str or value not in _BREAKS:
        raise _Invalid(name)
    return value


def _length(value: object, name: str, *, minimum: int) -> int:
    if type(value) is not int or value < minimum:
        raise _Invalid(name)
    return value


def _invalid(reason: str) -> dict[str, object]:
    return {
        "outcome": "invalid",
        "reason": reason,
        "column_count": None,
        "column_block_size": None,
        "boxes": None,
    }
