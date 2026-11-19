"""Resolve named grid areas and named lines, then place the items.

CSS Grid §7.3 reads ``grid-template-areas``. Every row has the same number of
cells. A name must fill one rectangle. ``.`` and ``....`` are the same empty
cell. Each area ``foo`` adds the lines ``foo-start`` and ``foo-end`` on both
axes. An explicit line with that same name stays in the list; the earliest
line wins.

§8.3 turns a placement into a line or a span. A bare name on the start side
uses the first ``name-start`` line, and a bare name on the end side uses the
first ``name-end`` line. That is how an area name beats a line that is
literally called ``name``. If that edged line does not exist, the bare name
is the first line called ``name``. ``name 2`` and ``2 name`` count lines
called ``name`` and do not append ``-start``. A missing count continues onto
implicit lines: forward counts the lines after the explicit grid, and a
negative count continues onto the lines before it.

A span with a name counts only lines of that name, starting from the
opposite definite line and moving toward this side. Implicit lines on the
other side of the explicit grid do not count. ``span foo / 4`` on a single
explicit column therefore starts on the line before that grid. Two spans
drop the end span. A named span with nothing on the other side becomes a
span of 1, so an automatic item cannot span to a name.

The explicit track count is the larger of the sized tracks and the template.
Resolved numbers are handed to ``place_grid_items``. ``order`` and anonymous
items are not applied.
"""

from __future__ import annotations

import re

from blackhole_agent.css_grid_placement import place_grid_items

_IDENT = re.compile(r"-?[A-Za-z_\u00A0-\U0010FFFF][A-Za-z0-9_\-\u00A0-\U0010FFFF]*\Z")
_DOTS = re.compile(r"\.+\Z")
_KEYWORDS = frozenset({"auto", "span"})
_LONGHANDS = ("column_start", "column_end", "row_start", "row_end")
_FIELDS = frozenset({"id", "area", *_LONGHANDS})


class _Invalid(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def place_named_grid(
    columns: object,
    rows: object,
    items: object,
    *,
    areas: object = None,
    column_lines: object = None,
    row_lines: object = None,
    flow: object = "row",
) -> dict[str, object]:
    """Place items after named areas and named lines become line numbers.

    ``columns`` and ``rows`` are the sized explicit track counts. ``areas``
    is a list of template strings. ``column_lines`` and ``row_lines`` name
    the explicit lines and must cover every explicit line once the template
    has been included. Item fields match ``place_grid_items``, plus ``area``.
    ``area`` sets every omitted longhand to that name.
    """

    try:
        sized_columns = _count(columns, "columns")
        sized_rows = _count(rows, "rows")
        area_columns, area_rows, column_extra, row_extra = _areas(areas)
        used_columns = max(sized_columns, area_columns)
        used_rows = max(sized_rows, area_rows)
        columns_named = _named_lines(
            column_lines, used_columns, column_extra, "column lines"
        )
        rows_named = _named_lines(row_lines, used_rows, row_extra, "row lines")
        resolved = _items(items, columns_named, rows_named, used_columns, used_rows)
    except _Invalid as exc:
        return _invalid(exc.reason)
    placed = place_grid_items(used_columns, used_rows, resolved, flow=flow)
    return placed if isinstance(placed, dict) else _invalid("placement failed")


def _areas(value: object) -> tuple[int, int, tuple[tuple[str, int, int], ...], tuple[tuple[str, int, int], ...]]:
    if value is None or value == []:
        return 0, 0, (), ()
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise _Invalid("areas must be a list of strings")
    grid: list[list[str | None]] = []
    width: int | None = None
    for index, raw in enumerate(value):
        if not isinstance(raw, str):
            raise _Invalid(f"areas row {index} must be a string")
        tokens = raw.split()
        if not tokens:
            raise _Invalid(f"areas row {index} is empty")
        row: list[str | None] = []
        for token in tokens:
            if _DOTS.fullmatch(token):
                row.append(None)
            elif _ident(token):
                row.append(token)
            else:
                raise _Invalid(f"areas row {index} has an invalid cell")
        if width is None:
            width = len(row)
        elif len(row) != width:
            raise _Invalid("areas rows have different lengths")
        grid.append(row)
    cells: dict[str, list[tuple[int, int]]] = {}
    for row_index, row in enumerate(grid):
        for column_index, name in enumerate(row):
            if name is not None:
                cells.setdefault(name, []).append((column_index, row_index))
    column_lines: list[tuple[str, int, int]] = []
    row_lines: list[tuple[str, int, int]] = []
    for name, spots in cells.items():
        columns = [column for column, _row in spots]
        rows = [row for _column, row in spots]
        min_column, max_column = min(columns), max(columns)
        min_row, max_row = min(rows), max(rows)
        rectangle = (max_column - min_column + 1) * (max_row - min_row + 1)
        if len(spots) != rectangle or len(set(spots)) != len(spots):
            raise _Invalid(f"area {name} is not a rectangle")
        column_lines.append((name, min_column + 1, max_column + 2))
        row_lines.append((name, min_row + 1, max_row + 2))
    return width or 0, len(grid), tuple(column_lines), tuple(row_lines)


def _named_lines(
    supplied: object,
    tracks: int,
    generated: tuple[tuple[str, int, int], ...],
    label: str,
) -> list[set[str]]:
    count = tracks + 1 if tracks or generated or supplied is not None else 1
    if tracks == 0 and not generated and supplied is None:
        count = 1
    lines = [set() for _ in range(max(count, 1))]
    if supplied is not None:
        if isinstance(supplied, (str, bytes)) or not isinstance(supplied, (list, tuple)):
            raise _Invalid(f"{label} must be a list")
        if len(supplied) != len(lines):
            raise _Invalid(f"{label} do not match the explicit grid")
        for index, raw in enumerate(supplied):
            if isinstance(raw, (str, bytes)) or not isinstance(raw, (list, tuple)):
                raise _Invalid(f"{label} {index} must be a list")
            for name in raw:
                if not isinstance(name, str) or not _ident(name):
                    raise _Invalid(f"{label} {index} has an invalid name")
                lines[index].add(name)
    for name, start, end in generated:
        _add_generated(lines, f"{name}-start", start)
        _add_generated(lines, f"{name}-end", end)
    return lines


def _add_generated(lines: list[set[str]], name: str, number: int) -> None:
    if number < 1 or number > len(lines):
        raise _Invalid("area line is outside the explicit grid")
    lines[number - 1].add(name)


def _items(
    value: object,
    columns: list[set[str]],
    rows: list[set[str]],
    explicit_columns: int,
    explicit_rows: int,
) -> list[dict[str, object]]:
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise _Invalid("items must be a list")
    resolved: list[dict[str, object]] = []
    for index, raw in enumerate(value):
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
        sides = {name: "auto" for name in _LONGHANDS}
        if "area" in raw:
            area = raw["area"]
            if not isinstance(area, str) or not _ident(area):
                raise _Invalid(f"item {index} area is invalid")
            for name in _LONGHANDS:
                sides[name] = area
        for name in _LONGHANDS:
            if name in raw:
                sides[name] = raw[name]
        column_start, column_span = _axis(
            sides["column_start"], sides["column_end"], columns, explicit_columns, f"item {index} column"
        )
        row_start, row_span = _axis(
            sides["row_start"], sides["row_end"], rows, explicit_rows, f"item {index} row"
        )
        column_token, column_limit = _encode(column_start, column_span, explicit_columns)
        row_token, row_limit = _encode(row_start, row_span, explicit_rows)
        resolved.append(
            {
                "id": ident,
                "column_start": column_token,
                "column_end": column_limit,
                "row_start": row_token,
                "row_end": row_limit,
            }
        )
    return resolved


def _axis(
    start_value: object,
    end_value: object,
    lines: list[set[str]],
    explicit: int,
    label: str,
) -> tuple[int | None, int]:
    start = _contrib(start_value, "start", lines, label)
    end = _contrib(end_value, "end", lines, label)
    if start[0] == "span" and end[0] == "span":
        end = ("auto",)
    if start[0] == "span" and start[2] and end[0] == "auto":
        start = ("span", 1, None)
    if end[0] == "span" and end[2] and start[0] == "auto":
        end = ("span", 1, None)
    start = _materialize(start, lines, explicit)
    end = _materialize(end, lines, explicit)
    if start[0] == "span" and start[2] and end[0] == "line":
        found = _span_line(lines, str(start[2]), int(end[3]), int(start[1]), endward=False)
        start = ("line", found, None, found)
    elif end[0] == "span" and end[2] and start[0] == "line":
        found = _span_line(lines, str(end[2]), int(start[3]), int(end[1]), endward=True)
        end = ("line", found, None, found)
    return _pair(start, end, label)


def _contrib(value: object, side: str, lines: list[set[str]], label: str) -> tuple:
    if value == "auto":
        return ("auto",)
    if isinstance(value, str) and value.lower() == "auto" and value != "auto":
        return ("auto",)
    if isinstance(value, bool) or isinstance(value, int):
        if isinstance(value, bool) or value == 0:
            raise _Invalid(f"{label} is invalid")
        return ("line", value, None, None)
    if not isinstance(value, str):
        raise _Invalid(f"{label} is invalid")
    text = " ".join(value.split())
    if not text:
        raise _Invalid(f"{label} is invalid")
    parts = text.split(" ")
    if parts[0].lower() == "span":
        count, name = _span_parts(parts[1:], label)
        return ("span", count, name)
    number, name = _line_parts(parts, label)
    if name is not None and len(parts) == 1:
        edged = f"{name}-start" if side == "start" else f"{name}-end"
        found = _first_line(lines, edged)
        if found is not None:
            return ("line", found, None, found)
    return ("line", number, name, None)


def _span_parts(parts: list[str], label: str) -> tuple[int, str | None]:
    if not parts or len(parts) > 2:
        raise _Invalid(f"{label} is invalid")
    count: int | None = None
    name: str | None = None
    for part in parts:
        if _integer_token(part):
            if count is not None or part.startswith("-"):
                raise _Invalid(f"{label} is invalid")
            count = int(part)
            if count < 1:
                raise _Invalid(f"{label} is invalid")
        elif name is not None or not _ident(part):
            raise _Invalid(f"{label} is invalid")
        else:
            name = part
    if count is None and name is None:
        raise _Invalid(f"{label} is invalid")
    return count or 1, name


def _line_parts(parts: list[str], label: str) -> tuple[int, str | None]:
    if not parts or len(parts) > 2:
        raise _Invalid(f"{label} is invalid")
    number: int | None = None
    name: str | None = None
    for part in parts:
        if _integer_token(part):
            if number is not None or int(part) == 0:
                raise _Invalid(f"{label} is invalid")
            number = int(part)
        elif name is not None or not _ident(part):
            raise _Invalid(f"{label} is invalid")
        else:
            name = part
    if number is None and name is None:
        raise _Invalid(f"{label} is invalid")
    return 1 if number is None else number, name


def _materialize(contrib: tuple, lines: list[set[str]], explicit: int) -> tuple:
    if contrib[0] != "line" or contrib[3] is not None:
        return contrib
    number = int(contrib[1])
    name = contrib[2]
    absolute = _nth_line(lines, str(name), number) if name else _numeric_line(number, explicit)
    return ("line", number, name, absolute)


def _pair(start: tuple, end: tuple, label: str) -> tuple[int | None, int]:
    if start[0] == "line" and end[0] == "line":
        first, second = int(start[3]), int(end[3])
        if first > second:
            first, second = second, first
        if first == second:
            return first, 1
        return first, second - first
    if start[0] == "line" and end[0] == "auto":
        return int(start[3]), 1
    if start[0] == "auto" and end[0] == "line":
        return int(end[3]) - 1, 1
    if start[0] == "line" and end[0] == "span" and not end[2]:
        return int(start[3]), int(end[1])
    if start[0] == "span" and not start[2] and end[0] == "line":
        return int(end[3]) - int(start[1]), int(start[1])
    if start[0] == "span" and end[0] == "auto":
        return None, int(start[1])
    if start[0] == "auto" and end[0] == "span":
        return None, int(end[1])
    if start[0] == "auto" and end[0] == "auto":
        return None, 1
    raise _Invalid(f"{label} is invalid")


def _encode(start: int | None, span: int, explicit: int) -> tuple[object, object]:
    if start is None:
        if span == 1:
            return "auto", "auto"
        return "auto", f"span {span}"
    end = start + span
    if start > 0 and end > 0:
        if span == 1:
            return start, "auto"
        return start, end
    end_token: object = end if end > 0 else end - explicit - 2
    return f"span {span}", end_token


def _first_line(lines: list[set[str]], name: str) -> int | None:
    for number, names in enumerate(lines, start=1):
        if name in names:
            return number
    return None


def _nth_line(lines: list[set[str]], name: str, index: int) -> int:
    last = len(lines)
    if index > 0:
        found = 0
        for number, names in enumerate(lines, start=1):
            if name in names:
                found += 1
                if found == index:
                    return number
        return last + (index - found)
    need = -index
    found = 0
    for number in range(last, 0, -1):
        if name in lines[number - 1]:
            found += 1
            if found == need:
                return number
    return found - need + 1


def _span_line(lines: list[set[str]], name: str, origin: int, count: int, *, endward: bool) -> int:
    last = len(lines)
    found = 0
    line = origin
    if endward:
        while line < last:
            line += 1
            if name in lines[line - 1]:
                found += 1
                if found == count:
                    return line
        while found < count:
            line += 1
            found += 1
        return line
    while line > 1:
        line -= 1
        if line <= last and name in lines[line - 1]:
            found += 1
            if found == count:
                return line
    while found < count:
        line -= 1
        found += 1
    return line


def _numeric_line(value: int, explicit: int) -> int:
    if value > 0:
        return value
    return explicit + value + 2


def _count(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise _Invalid(f"{label} is invalid")
    return value


def _ident(value: str) -> bool:
    if value.lower() in _KEYWORDS or value.startswith("--") or value == "-":
        return False
    return _IDENT.fullmatch(value) is not None


def _integer_token(value: str) -> bool:
    if value.startswith("-"):
        return value[1:].isdigit() and value != "-"
    return value.isdigit()


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
