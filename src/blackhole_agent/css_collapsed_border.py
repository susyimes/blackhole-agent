"""Choose the used border where collapsed CSS table borders meet.

CSS 2.2 §17.6.2.1 looks at every element that paints the same grid edge:
the table, a column group, a column, a row group, a row, and the cells.
``hidden`` prevents every other style and leaves the edge with no width.
``none`` loses to any other style, including a zero-width solid. A wider
border then beats a narrower one, before style is considered, so a wide
dotted border beats a narrow double. Equal widths prefer ``double``, then
``solid``, ``dashed``, ``dotted``, ``ridge``, ``outset``, ``groove``, and
``inset``. Equal width and style prefer a cell over a row, a row group, a
column, a column group, and the table. Two contributors of the same kind
prefer the one further toward the top, then the one further toward the
start side: left when direction is ``ltr``, right when it is ``rtl``.
"""

from __future__ import annotations

_STYLES = ("double", "solid", "dashed", "dotted", "ridge", "outset", "groove", "inset")
_STYLE_RANK = {name: len(_STYLES) - index for index, name in enumerate(_STYLES)}
_SOURCES = ("cell", "row", "row-group", "column", "column-group", "table")
_SOURCE_RANK = {name: index for index, name in enumerate(_SOURCES)}
_FIELDS = frozenset({"source", "style", "width", "color", "row", "column"})
_NONE = "none"
_HIDDEN = "hidden"


class _Invalid(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def resolve_collapsed_border(borders: object, *, direction: object = "ltr") -> dict[str, object]:
    """Return the one border that wins at a shared collapsed edge.

    Each contributor maps ``source``, ``style``, ``width``, ``color``,
    ``row``, and ``column``. ``source`` is ``cell``, ``row``, ``row-group``,
    ``column``, ``column-group``, or ``table``. ``style`` is a CSS border
    style. ``width`` is a non-negative length. ``row`` and ``column`` are
    the contributor's position, with smaller numbers further toward the top
    and the left. ``direction`` is ``ltr`` or ``rtl``.
    """

    try:
        inline = _direction(direction)
        parsed = _borders(borders)
    except _Invalid as exc:
        return _invalid(exc.reason)

    hidden = [item for item in parsed if item["style"] == _HIDDEN]
    if hidden:
        winner = _prefer(hidden, inline)
        return _resolved(winner, width=0, suppressed=True)
    visible = [item for item in parsed if item["style"] != _NONE]
    if not visible:
        return _resolved(_prefer(parsed, inline), width=0, suppressed=False)

    widest = max(float(item["width"]) for item in visible)
    pool = [item for item in visible if float(item["width"]) == widest]
    best_style = max(int(item["style_rank"]) for item in pool)
    pool = [item for item in pool if int(item["style_rank"]) == best_style]
    winner = _prefer(pool, inline)
    return _resolved(winner, width=float(winner["width"]), suppressed=False)


def _prefer(items: list[dict[str, object]], direction: str) -> dict[str, object]:
    return min(items, key=lambda item: _key(item, direction))


def _key(item: dict[str, object], direction: str) -> tuple[int, int, int, int]:
    column = int(item["column"])
    if direction == "rtl":
        column = -column
    return (int(item["source_rank"]), int(item["row"]), column, int(item["index"]))


def _resolved(winner: dict[str, object], *, width: float, suppressed: bool) -> dict[str, object]:
    return {
        "outcome": "resolved",
        "style": winner["style"],
        "width": _number(width),
        "color": winner["color"],
        "source": winner["source"],
        "suppressed": suppressed,
    }


def _invalid(reason: str) -> dict[str, object]:
    return {
        "outcome": "invalid",
        "reason": reason,
        "style": None,
        "width": None,
        "color": None,
        "source": None,
        "suppressed": None,
    }


def _borders(value: object) -> list[dict[str, object]]:
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise _Invalid("borders must be a list")
    if not value:
        raise _Invalid("borders must not be empty")
    return [_border(raw, index) for index, raw in enumerate(value)]


def _border(raw: object, index: int) -> dict[str, object]:
    if not isinstance(raw, dict):
        raise _Invalid(f"border {index} must be a mapping")
    unknown = set(raw) - _FIELDS
    if unknown:
        raise _Invalid(f"border {index} has an unknown field")
    missing = _FIELDS - set(raw)
    if missing:
        raise _Invalid(f"border {index} is missing a field")
    source = _token(raw["source"], _SOURCE_RANK, f"border {index} source")
    style = _style(raw["style"], index)
    return {
        "index": index,
        "source": source,
        "source_rank": _SOURCE_RANK[source],
        "style": style,
        "style_rank": _STYLE_RANK.get(style, 0),
        "width": _width(raw["width"], index),
        "color": _color(raw["color"], index),
        "row": _coordinate(raw["row"], f"border {index} row"),
        "column": _coordinate(raw["column"], f"border {index} column"),
    }


def _style(value: object, index: int) -> str:
    if not isinstance(value, str):
        raise _Invalid(f"border {index} style is invalid")
    style = _normalize(value)
    if style not in _STYLE_RANK and style not in {_NONE, _HIDDEN}:
        raise _Invalid(f"border {index} style is invalid")
    return style


def _width(value: object, index: int) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _Invalid(f"border {index} width is invalid")
    number = float(value)
    if number != number or number in {float("inf"), float("-inf")} or number < 0:
        raise _Invalid(f"border {index} width is invalid")
    return number


def _color(value: object, index: int) -> str:
    if not isinstance(value, str):
        raise _Invalid(f"border {index} color is invalid")
    return " ".join(value.split())


def _coordinate(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise _Invalid(f"{name} is invalid")
    return value


def _direction(value: object) -> str:
    if not isinstance(value, str):
        raise _Invalid("direction is invalid")
    direction = value.strip().lower()
    if direction not in {"ltr", "rtl"}:
        raise _Invalid("direction is invalid")
    return direction


def _token(value: object, allowed: dict[str, int], name: str) -> str:
    if not isinstance(value, str):
        raise _Invalid(f"{name} is invalid")
    token = _normalize(value)
    if token not in allowed:
        raise _Invalid(f"{name} is invalid")
    return token


def _normalize(value: str) -> str:
    return "-".join(value.strip().lower().split())


def _number(value: float) -> int | float:
    nearest = round(value)
    if abs(value - nearest) <= 1e-9:
        return int(nearest)
    return value


_SIDES = ("top", "right", "bottom", "left")


def resolve_collapsed_grid(
    column_count: object,
    row_count: object,
    *,
    table: object = None,
    rows: object = None,
    cells: object = None,
    direction: object = "ltr",
) -> dict[str, object]:
    """Resolve every vertical and horizontal line of a collapsed table.

    ``column_count`` and ``row_count`` are the grid. ``table`` and each row
    map ``top``, ``right``, ``bottom``, and ``left`` to ``style`` and
    ``width``. Each cell maps ``row``, ``column``, optional ``span`` and
    ``rowspan``, and ``borders``. Column groups and row groups are absent.
    A line with no real border is ``none`` at width 0. The result is one
    edge per grid line, including both outer lines.
    """

    try:
        columns = _count(column_count, "column count")
        row_total = _count(row_count, "row count")
        table_sides = _side_map(table, "table")
        row_sides = _row_maps(rows, row_total)
        parsed = _grid_cells(cells, columns, row_total)
        inline = _direction(direction)
    except _Invalid as exc:
        return _grid_invalid(exc.reason)
    vertical = [
        _line(
            _vertical_contributors(index, columns, table_sides, row_sides, parsed),
            inline,
        )
        for index in range(columns + 1)
    ]
    horizontal = [
        _line(
            _horizontal_contributors(index, row_total, table_sides, row_sides, parsed),
            inline,
        )
        for index in range(row_total + 1)
    ]
    if any(edge.get("outcome") == "invalid" for edge in (*vertical, *horizontal)):
        reason = next(
            str(edge.get("reason") or "collapsed border failed")
            for edge in (*vertical, *horizontal)
            if edge.get("outcome") == "invalid"
        )
        return _grid_invalid(reason)
    return {
        "outcome": "resolved",
        "reason": None,
        "vertical": [_public_edge(edge) for edge in vertical],
        "horizontal": [_public_edge(edge) for edge in horizontal],
    }


def _grid_invalid(reason: str) -> dict[str, object]:
    return {"outcome": "invalid", "reason": reason, "vertical": None, "horizontal": None}


def _count(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise _Invalid(f"{name} is invalid")
    return value


def _side_map(value: object, name: str) -> dict[str, tuple[str, float]]:
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise _Invalid(f"{name} borders are invalid")
    unknown = set(value) - set(_SIDES)
    if unknown:
        raise _Invalid(f"{name} borders are invalid")
    sides: dict[str, tuple[str, float]] = {}
    for side in _SIDES:
        raw = value.get(side)
        if raw is None:
            sides[side] = (_NONE, 0.0)
            continue
        if not isinstance(raw, dict):
            raise _Invalid(f"{name} {side} border is invalid")
        unknown = set(raw) - {"style", "width", "color"}
        if unknown:
            raise _Invalid(f"{name} {side} border is invalid")
        sides[side] = (_style(raw.get("style", _NONE), 0), _width(raw.get("width", 0), 0))
    return sides


def _row_maps(value: object, count: int) -> list[dict[str, tuple[str, float]]]:
    if value is None:
        value = []
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise _Invalid("row borders are invalid")
    if len(value) != count:
        raise _Invalid("row borders are invalid")
    return [_side_map(item, f"row {index}") for index, item in enumerate(value)]


def _grid_cells(value: object, columns: int, rows: int) -> list[dict[str, object]]:
    if value is None:
        value = []
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise _Invalid("cells are invalid")
    parsed: list[dict[str, object]] = []
    for index, raw in enumerate(value):
        if not isinstance(raw, dict):
            raise _Invalid(f"cell {index} is invalid")
        unknown = set(raw) - {"row", "column", "span", "rowspan", "borders"}
        if unknown:
            raise _Invalid(f"cell {index} is invalid")
        row = _coordinate(raw.get("row"), f"cell {index} row")
        column = _coordinate(raw.get("column"), f"cell {index} column")
        span = _coordinate(raw.get("span", 1), f"cell {index} span")
        rowspan = _coordinate(raw.get("rowspan", 1), f"cell {index} rowspan")
        if span < 1 or rowspan < 1 or column + span > columns or row + rowspan > rows:
            raise _Invalid(f"cell {index} is outside the grid")
        parsed.append(
            {
                "row": row,
                "column": column,
                "span": span,
                "rowspan": rowspan,
                "borders": _side_map(raw.get("borders"), f"cell {index}"),
            }
        )
    return parsed


def _contributor(
    source: str,
    side: tuple[str, float],
    row: int,
    column: int,
) -> dict[str, object] | None:
    style, width = side
    if style == _NONE:
        return None
    return {
        "source": source,
        "style": style,
        "width": width,
        "color": "currentcolor",
        "row": row,
        "column": column,
    }


def _vertical_contributors(
    line: int,
    columns: int,
    table: dict[str, tuple[str, float]],
    row_sides: list[dict[str, tuple[str, float]]],
    cells: list[dict[str, object]],
) -> list[dict[str, object]]:
    found: list[dict[str, object]] = []
    if line == 0:
        _add(found, _contributor("table", table["left"], 0, 0))
        for index, sides in enumerate(row_sides):
            _add(found, _contributor("row", sides["left"], index, 0))
    if line == columns:
        _add(found, _contributor("table", table["right"], 0, 0))
        for index, sides in enumerate(row_sides):
            _add(found, _contributor("row", sides["right"], index, 0))
    for cell in cells:
        column = int(cell["column"])
        span = int(cell["span"])
        borders = cell["borders"]
        if not isinstance(borders, dict):
            continue
        if column == line:
            _add(found, _contributor("cell", borders["left"], int(cell["row"]), column))
        if column + span == line:
            _add(found, _contributor("cell", borders["right"], int(cell["row"]), column))
    return found


def _horizontal_contributors(
    line: int,
    rows: int,
    table: dict[str, tuple[str, float]],
    row_sides: list[dict[str, tuple[str, float]]],
    cells: list[dict[str, object]],
) -> list[dict[str, object]]:
    found: list[dict[str, object]] = []
    if line == 0:
        _add(found, _contributor("table", table["top"], 0, 0))
    if line == rows:
        _add(found, _contributor("table", table["bottom"], 0, 0))
    if line < rows:
        _add(found, _contributor("row", row_sides[line]["top"], line, 0))
    if line > 0:
        _add(found, _contributor("row", row_sides[line - 1]["bottom"], line - 1, 0))
    for cell in cells:
        row = int(cell["row"])
        rowspan = int(cell["rowspan"])
        borders = cell["borders"]
        if not isinstance(borders, dict):
            continue
        if row == line:
            _add(found, _contributor("cell", borders["top"], row, int(cell["column"])))
        if row + rowspan == line:
            _add(found, _contributor("cell", borders["bottom"], row, int(cell["column"])))
    return found


def _add(found: list[dict[str, object]], item: dict[str, object] | None) -> None:
    if item is not None:
        found.append(item)


def _line(contributors: list[dict[str, object]], direction: str) -> dict[str, object]:
    if not contributors:
        return {"outcome": "resolved", "width": 0, "style": _NONE, "source": "none", "suppressed": False}
    return resolve_collapsed_border(contributors, direction=direction)


def _public_edge(edge: dict[str, object]) -> dict[str, object]:
    return {
        "width": edge.get("width"),
        "style": edge.get("style"),
        "source": edge.get("source"),
        "suppressed": edge.get("suppressed"),
    }
