"""Place CSS grid items with the automatic-placement cursor.

CSS Grid §8.3 resolves each axis before placement. Two line numbers swap when
the start line is further end-ward, equal lines drop the end, and two spans
drop the span on the end property. A negative line counts backward from the
explicit grid's end edge. A single span opposite a line becomes a definite
position. ``auto / span N`` stays automatic.

§8.5 then places the items, written here for ``grid-auto-flow: row`` and
executed with the axes swapped for ``column``. Definite areas occupy their
cells first and may overlap each other. An item locked to a row takes the
earliest positive column that fits; sparse packing also stays past items this
step already placed in that row, while dense packing may fill an earlier hole.
The implicit grid then grows at either end for definite columns and at the end
for an automatic span wider than the grid. The cursor starts on the start-most
implicit line. Sparse packing keeps that cursor: a later column behind the
cursor moves to the next row, and a span that does not fit the remaining
columns wraps. Dense packing restarts the search at the start-most line for
every remaining item. ``place_named_grid`` resolves named lines and named
areas into these numbers first. Anonymous items are not generated here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_FLOWS = {
    "row": ("row", False),
    "column": ("column", False),
    "dense": ("row", True),
    "row dense": ("row", True),
    "column dense": ("column", True),
}
_FIELDS = frozenset({"id", "column_start", "column_end", "row_start", "row_end"})
_SPAN = re.compile(r"^span\s+([1-9]\d*)$")
_AUTO = "auto"


class _Invalid(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass
class _Item:
    id: str
    col_line: int | None
    col_span: int
    row_line: int | None
    row_span: int
    column: int | None = None
    row: int | None = None

    @property
    def placed(self) -> bool:
        return self.column is not None


def place_grid_items(
    columns: object,
    rows: object,
    items: object,
    *,
    flow: object = "row",
) -> dict[str, object]:
    """Return the used grid area of every item.

    ``columns`` and ``rows`` are the explicit track counts. Each item maps
    ``id`` plus optional ``column_start``, ``column_end``, ``row_start``, and
    ``row_end``. A side is ``auto``, a nonzero line number, or ``span N``.
    ``flow`` is ``row``, ``column``, ``dense``, ``row dense``, or ``column dense``.
    Line numbers in the result are the placed start lines. Track counts include
    the explicit grid and any implicit tracks added before or after it.
    """

    try:
        explicit_columns = _count(columns, "columns")
        explicit_rows = _count(rows, "rows")
        axis, dense = _flow(flow)
        parsed = _items(items, explicit_columns, explicit_rows)
        if axis == "column":
            for item in parsed:
                item.col_line, item.row_line = item.row_line, item.col_line
                item.col_span, item.row_span = item.row_span, item.col_span
            explicit_columns, explicit_rows = explicit_rows, explicit_columns
        _place(parsed, explicit_columns, explicit_rows, dense)
        if axis == "column":
            for item in parsed:
                item.column, item.row = item.row, item.column
                item.col_span, item.row_span = item.row_span, item.col_span
            explicit_columns, explicit_rows = explicit_rows, explicit_columns
    except _Invalid as exc:
        return _invalid(exc.reason)

    col_lo, col_count, row_lo, row_count = _bounds(parsed, explicit_columns, explicit_rows)
    return {
        "outcome": "placed",
        "flow": "column" if axis == "column" else "row",
        "dense": dense,
        "column_start_line": col_lo,
        "column_count": col_count,
        "row_start_line": row_lo,
        "row_count": row_count,
        "placements": [
            {
                "id": item.id,
                "column": item.column,
                "row": item.row,
                "column_span": item.col_span,
                "row_span": item.row_span,
            }
            for item in parsed
        ],
    }


def _place(items: list[_Item], columns: int, rows: int, dense: bool) -> None:
    occupied: set[tuple[int, int]] = set()
    for item in items:
        if item.col_line is not None and item.row_line is not None:
            _occupy(occupied, item, item.col_line, item.row_line)
    floors: dict[int, int] = {}
    for item in items:
        if item.placed or item.row_line is None or item.col_line is not None:
            continue
        column = 1 if dense else floors.get(item.row_line, 1)
        while _hits(occupied, column, item.row_line, item.col_span, item.row_span):
            column += 1
        _occupy(occupied, item, column, item.row_line)
        if not dense:
            floors[item.row_line] = column + item.col_span

    col_lo, col_hi = 1, 1 + columns
    row_lo = 1
    auto_span = 0
    for item in items:
        if item.column is not None:
            col_lo = min(col_lo, item.column)
            col_hi = max(col_hi, item.column + item.col_span)
            if item.row is not None:
                row_lo = min(row_lo, item.row)
        elif item.col_line is not None:
            col_lo = min(col_lo, item.col_line)
            col_hi = max(col_hi, item.col_line + item.col_span)
        else:
            auto_span = max(auto_span, item.col_span)
        if item.row is None and item.row_line is not None:
            row_lo = min(row_lo, item.row_line)
    if auto_span > col_hi - col_lo:
        col_hi = col_lo + auto_span
    if col_hi <= col_lo and any(not item.placed for item in items):
        raise _Invalid("column span exceeds the grid")

    cursor_column = col_lo
    cursor_row = row_lo
    for item in items:
        if item.placed:
            continue
        if item.col_span > col_hi - col_lo:
            raise _Invalid("column span exceeds the grid")
        if dense:
            cursor_column = item.col_line if item.col_line is not None else col_lo
            cursor_row = row_lo
        elif item.col_line is not None:
            if item.col_line < cursor_column:
                cursor_row += 1
            cursor_column = item.col_line
        if item.col_line is not None:
            while _hits(occupied, cursor_column, cursor_row, item.col_span, item.row_span):
                cursor_row += 1
            _occupy(occupied, item, cursor_column, cursor_row)
            continue
        while True:
            fits = cursor_column + item.col_span <= col_hi
            if fits and not _hits(occupied, cursor_column, cursor_row, item.col_span, item.row_span):
                _occupy(occupied, item, cursor_column, cursor_row)
                break
            if fits:
                cursor_column += 1
            else:
                cursor_row += 1
                cursor_column = col_lo
    if any(not item.placed for item in items):
        raise _Invalid("item was not placed")


def _occupy(occupied: set[tuple[int, int]], item: _Item, column: int, row: int) -> None:
    item.column = column
    item.row = row
    for column_line in range(column, column + item.col_span):
        for row_line in range(row, row + item.row_span):
            occupied.add((column_line, row_line))


def _hits(
    occupied: set[tuple[int, int]],
    column: int,
    row: int,
    column_span: int,
    row_span: int,
) -> bool:
    for column_line in range(column, column + column_span):
        for row_line in range(row, row + row_span):
            if (column_line, row_line) in occupied:
                return True
    return False


def _bounds(items: list[_Item], columns: int, rows: int) -> tuple[int, int, int, int]:
    col_lo, col_hi = 1, 1 + columns
    row_lo, row_hi = 1, 1 + rows
    for item in items:
        if item.column is None or item.row is None:
            continue
        col_lo = min(col_lo, item.column)
        col_hi = max(col_hi, item.column + item.col_span)
        row_lo = min(row_lo, item.row)
        row_hi = max(row_hi, item.row + item.row_span)
    return col_lo, col_hi - col_lo, row_lo, row_hi - row_lo


def _items(value: object, columns: int, rows: int) -> list[_Item]:
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise _Invalid("items must be a list")
    items: list[_Item] = []
    seen: set[str] = set()
    for index, raw in enumerate(value):
        item = _item(raw, index, columns, rows)
        if item.id in seen:
            raise _Invalid(f"item {index} repeats {item.id}")
        seen.add(item.id)
        items.append(item)
    return items


def _item(raw: object, index: int, columns: int, rows: int) -> _Item:
    if not isinstance(raw, dict):
        raise _Invalid(f"item {index} must be a mapping")
    unknown = set(raw) - _FIELDS
    if unknown:
        raise _Invalid(f"item {index} has an unknown field")
    if "id" not in raw:
        raise _Invalid(f"item {index} needs an id")
    ident = raw["id"]
    if not isinstance(ident, str) or not ident or ident.strip() != ident:
        raise _Invalid(f"item {index} needs an id")
    col_line, col_span = _axis(
        raw.get("column_start", _AUTO),
        raw.get("column_end", _AUTO),
        columns,
        f"item {index} column",
    )
    row_line, row_span = _axis(
        raw.get("row_start", _AUTO),
        raw.get("row_end", _AUTO),
        rows,
        f"item {index} row",
    )
    return _Item(ident, col_line, col_span, row_line, row_span)


def _axis(start: object, end: object, explicit: int, name: str) -> tuple[int | None, int]:
    kind_start, start_value = _token(start, name)
    kind_end, end_value = _token(end, name)
    if kind_start == "span" and kind_end == "span":
        kind_end, end_value = "auto", None
    if kind_start == "line" and kind_end == "line":
        start_line = _line(int(start_value or 0), explicit)
        end_line = _line(int(end_value or 0), explicit)
        if start_line > end_line:
            start_line, end_line = end_line, start_line
        if start_line == end_line:
            return start_line, 1
        return start_line, end_line - start_line
    if kind_start == "line" and kind_end == "auto":
        return _line(int(start_value or 0), explicit), 1
    if kind_start == "line" and kind_end == "span":
        return _line(int(start_value or 0), explicit), int(end_value or 0)
    if kind_start == "auto" and kind_end == "line":
        end_line = _line(int(end_value or 0), explicit)
        return end_line - 1, 1
    if kind_start == "span" and kind_end == "line":
        end_line = _line(int(end_value or 0), explicit)
        span = int(start_value or 0)
        return end_line - span, span
    if kind_start == "span" and kind_end == "auto":
        return None, int(start_value or 0)
    if kind_start == "auto" and kind_end == "span":
        return None, int(end_value or 0)
    if kind_start == "auto" and kind_end == "auto":
        return None, 1
    raise _Invalid(f"{name} is invalid")


def _token(value: object, name: str) -> tuple[str, int | None]:
    if value == _AUTO:
        return "auto", None
    if isinstance(value, str):
        match = _SPAN.fullmatch(value.strip())
        if match is None:
            raise _Invalid(f"{name} is invalid")
        return "span", int(match.group(1))
    if isinstance(value, bool) or not isinstance(value, int) or value == 0:
        raise _Invalid(f"{name} is invalid")
    return "line", value


def _line(value: int, explicit: int) -> int:
    if value > 0:
        return value
    return explicit + value + 2


def _flow(value: object) -> tuple[str, bool]:
    if not isinstance(value, str):
        raise _Invalid("flow is invalid")
    chosen = _FLOWS.get(" ".join(value.split()).lower())
    if chosen is None:
        raise _Invalid("flow is invalid")
    return chosen


def _count(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise _Invalid(f"{name} is invalid")
    return value


def _invalid(reason: str) -> dict[str, object]:
    return {
        "outcome": "invalid",
        "reason": reason,
        "flow": None,
        "dense": None,
        "column_start_line": None,
        "column_count": None,
        "row_start_line": None,
        "row_count": None,
        "placements": None,
    }
