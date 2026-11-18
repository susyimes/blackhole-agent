"""Used column widths for an automatic CSS table.

CSS Tables 3 §§3.8–3.9 size columns from content. Fixed layout does not:
``layout_fixed_columns`` returns no widths when the table width is automatic.
This is that missing pass. The caller supplies content measures. Text,
row heights, captions, border collapse, column groups, and vertical writing
modes stay outside.

A column length raises that column's floor. A cell length on one column does
not. It constrains the column and caps its maximum, so a larger content
maximum is dropped. Minimum content still wins when it exceeds the cap or a
maximum width. A cell that covers several columns adds its extra floor or
cap on top of those columns. The extra is split in proportion to their caps,
or equally when every cap in the span is zero. Gaps inside the span are
reserved and are not given to the columns.

Percentages are a separate track, clamped from the start edge so the columns
never claim more than 100%. An automatic table width is the sum of the caps.
A containing block can limit it. The used width never drops below the sum of
the floors. Border spacing is the gap times one more than the column count,
covering both edges and every gap between columns. That total is removed
before the remainder is assigned.

The remainder interpolates the floor guess, the percentage guess, the
constrained-cap guess, and the cap guess. Anything wider than the cap guess
is given to unconstrained columns that a cell covers, in proportion to those
caps. A percentage column keeps its share of the assignable width and does
not take that leftover.
"""

from __future__ import annotations

from dataclasses import dataclass

_EPS = 1e-9
_INF = float("inf")
_KEYWORDS = frozenset({"auto", "min-content", "max-content"})


class _Invalid(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class _Spec:
    kind: str
    value: float


@dataclass(frozen=True)
class _Box:
    width: _Spec
    min_width: float
    max_width: float | None
    max_percent: float | None


@dataclass(frozen=True)
class _Cell:
    column: int
    span: int
    min_content: float
    max_content: float
    box: _Box
    percent: float


@dataclass
class _Column:
    min_w: float
    max_w: float
    percent: float
    constrained: bool
    has_origin: bool
    span1_max: float


def layout_auto_columns(
    table_width: object,
    columns: object,
    cells: object = (),
    *,
    spacing: object = 0,
    containing: object = None,
) -> dict[str, object]:
    """Return used column widths for ``table-layout: auto``.

    ``columns`` is one entry per column: ``auto``, a length, a percentage
    string, or a mapping with ``width``, ``min_width``, and ``max_width``.
    ``cells`` may come from every row. Each cell names ``column``, ``span``,
    ``min_content``, and ``max_content``. ``spacing`` is the horizontal
    border-spacing. ``containing`` limits an automatic table width.
    """

    try:
        kind, specified = _table_width(table_width)
        boxes = _columns(columns)
        parsed = _cells(cells, len(boxes))
        gutter = _length(spacing, "spacing")
        limit = None if containing is None else _length(containing, "containing block")
        built = _measures(boxes, parsed, gutter)
        _clamp_percent(built)
        used, assignable, border = _table_used(kind, specified, limit, gutter, built)
        widths = _distribute(built, assignable)
    except _Invalid as exc:
        return _invalid(exc.reason)
    return {
        "outcome": "resolved",
        "reason": None,
        "column_widths": [_number(width) for width in widths],
        "column_min": [_number(column.min_w) for column in built],
        "column_max": [_number(column.max_w) for column in built],
        "table_width": None if specified is None else _number(specified),
        "used_table_width": _number(used),
        "assignable": _number(assignable),
        "spacing": _number(gutter),
        "border_total": _number(border),
        "grid_min": _number(sum(column.min_w for column in built) + border),
        "grid_max": _number(sum(column.max_w for column in built) + border),
    }


def _invalid(reason: str) -> dict[str, object]:
    return {
        "outcome": "invalid",
        "reason": reason,
        "column_widths": None,
        "column_min": None,
        "column_max": None,
        "table_width": None,
        "used_table_width": None,
        "assignable": None,
        "spacing": None,
        "border_total": None,
        "grid_min": None,
        "grid_max": None,
    }


def _table_width(value: object) -> tuple[str, float | None]:
    if isinstance(value, str):
        keyword = value.strip().lower()
        if keyword in _KEYWORDS:
            return keyword, None
        raise _Invalid("table width is invalid")
    return "length", _length(value, "table width")


def _columns(value: object) -> list[_Box]:
    if isinstance(value, (str, bytes, dict)) or not isinstance(value, (list, tuple)) or not value:
        raise _Invalid("columns must be a non-empty list")
    return [_column_box(item, f"column {index}") for index, item in enumerate(value)]


def _column_box(raw: object, name: str) -> _Box:
    if isinstance(raw, dict):
        unknown = set(raw) - {"width", "min_width", "max_width"}
        if unknown:
            raise _Invalid(f"{name} has an unknown field")
        width = _spec(raw.get("width", "auto"), f"{name} width")
        maximum, max_percent = _max_width(raw.get("max_width", "none"), name)
        return _Box(width, _min_width(raw.get("min_width", "auto"), name), maximum, max_percent)
    return _Box(_spec(raw, name), 0.0, None, None)


def _cells(value: object, count: int) -> list[_Cell]:
    if isinstance(value, (str, bytes, dict)) or not isinstance(value, (list, tuple)):
        raise _Invalid("cells must be a list")
    parsed: list[_Cell] = []
    for index, raw in enumerate(value):
        parsed.append(_cell(raw, index, count))
    return parsed


def _cell(raw: object, index: int, count: int) -> _Cell:
    if not isinstance(raw, dict):
        raise _Invalid(f"cell {index} must be a mapping")
    unknown = set(raw) - {"column", "span", "min_content", "max_content", "width", "min_width", "max_width"}
    if unknown:
        raise _Invalid(f"cell {index} has an unknown field")
    if "column" not in raw or "min_content" not in raw or "max_content" not in raw:
        raise _Invalid(f"cell {index} needs a column and content measures")
    column = _index(raw["column"], f"cell {index} column")
    span = _index(raw.get("span", 1), f"cell {index} span")
    if column + span > count:
        raise _Invalid(f"cell {index} span is outside the columns")
    minimum = _length(raw["min_content"], f"cell {index} min_content")
    maximum = _length(raw["max_content"], f"cell {index} max_content")
    if maximum < minimum:
        raise _Invalid(f"cell {index} max_content is below min_content")
    box = _box(raw, f"cell {index}")
    return _Cell(column, span, minimum, maximum, box, _percent_of(box))


def _box(raw: object, name: str) -> _Box:
    if isinstance(raw, dict):
        unknown = set(raw) - {"width", "min_width", "max_width", "column", "span", "min_content", "max_content"}
        if unknown:
            raise _Invalid(f"{name} has an unknown field")
        width = _spec(raw.get("width", "auto"), f"{name} width")
        minimum = _min_width(raw.get("min_width", "auto"), name)
        maximum, max_percent = _max_width(raw.get("max_width", "none"), name)
        return _Box(width, minimum, maximum, max_percent)
    return _Box(_spec(raw, name), 0.0, None, None)


def _spec(value: object, name: str) -> _Spec:
    if isinstance(value, str):
        text = value.strip().lower()
        if text == "auto":
            return _Spec("auto", 0.0)
        if text.endswith("%") and _percent_text(text) is not None:
            return _Spec("pct", _percent_text(text) or 0.0)
        raise _Invalid(f"{name} is invalid")
    return _Spec("px", _length(value, name))


def _min_width(value: object, name: str) -> float:
    if isinstance(value, str):
        text = value.strip().lower()
        if text == "auto":
            return 0.0
        if text.endswith("%"):
            raise _Invalid(f"{name} min_width percentage is not a column floor")
    return _length(value, f"{name} min_width")


def _max_width(value: object, name: str) -> tuple[float | None, float | None]:
    if isinstance(value, str):
        text = value.strip().lower()
        if text == "none":
            return None, None
        if text.endswith("%") and _percent_text(text) is not None:
            return None, _percent_text(text)
        raise _Invalid(f"{name} max_width is invalid")
    return _length(value, f"{name} max_width"), None


def _percent_text(text: str) -> float | None:
    number = text[:-1].strip()
    if not number or number.count(".") > 1:
        return None
    try:
        value = float(number)
    except ValueError:
        return None
    if value != value or value < 0 or value in {_INF}:
        return None
    return value


def _percent_of(box: _Box) -> float:
    width = box.width.value if box.width.kind == "pct" else 0.0
    cap = _INF if box.max_percent is None else box.max_percent
    if box.width.kind != "pct":
        return 0.0
    return min(width, cap)


def _measures(boxes: list[_Box], cells: list[_Cell], gutter: float) -> list[_Column]:
    columns = [_new_column(box, index, cells) for index, box in enumerate(boxes)]
    for cell in cells:
        if cell.span != 1:
            continue
        column = columns[cell.column]
        outer_min, outer_max = _outer(cell, column.constrained)
        column.min_w = max(column.min_w, outer_min)
        column.max_w = max(column.max_w, outer_max)
        column.percent = max(column.percent, cell.percent)
    for column in columns:
        column.max_w = max(column.max_w, column.min_w)
        column.span1_max = column.max_w
    span1_max = [column.span1_max for column in columns]
    widest = max((cell.span for cell in cells), default=1)
    for span in range(2, widest + 1):
        group = [cell for cell in cells if cell.span == span]
        if not group:
            continue
        base_min = [column.min_w for column in columns]
        base_max = [column.max_w for column in columns]
        base_percent = [column.percent for column in columns]
        merged_min = base_min[:]
        merged_max = base_max[:]
        merged_percent = base_percent[:]
        for cell in group:
            grown_min, grown_max = _span_growth(columns, cell, base_min, base_max, gutter)
            for index in range(len(columns)):
                merged_min[index] = max(merged_min[index], grown_min[index])
                merged_max[index] = max(merged_max[index], grown_max[index])
            for index, value in _span_percent(cell, base_percent, span1_max).items():
                merged_percent[index] = max(merged_percent[index], value)
        for index, column in enumerate(columns):
            column.min_w = merged_min[index]
            column.max_w = max(merged_max[index], merged_min[index])
            column.percent = merged_percent[index]
    return columns


def _new_column(box: _Box, index: int, cells: list[_Cell]) -> _Column:
    outer_min, outer_max = _column_outer(box)
    covered = any(cell.column <= index < cell.column + cell.span for cell in cells)
    return _Column(
        min_w=outer_min,
        max_w=max(outer_max, outer_min),
        percent=_percent_of(box),
        constrained=_constrained(box, index, cells),
        has_origin=covered or box.width.kind != "auto",
        span1_max=0.0,
    )


def _constrained(box: _Box, index: int, cells: list[_Cell]) -> bool:
    if box.width.kind == "px":
        return True
    return any(cell.span == 1 and cell.column == index and cell.box.width.kind == "px" for cell in cells)


def _column_outer(box: _Box) -> tuple[float, float]:
    if box.width.kind != "px":
        floor = box.min_width
        return floor, floor
    cap = box.width.value if box.max_width is None else min(box.max_width, box.width.value)
    outer_min = max(box.min_width, box.width.value)
    outer_max = max(box.min_width, cap)
    return outer_min, max(outer_max, outer_min)


def _outer(cell: _Cell, constrained: bool) -> tuple[float, float]:
    length = cell.box.width.value if cell.box.width.kind == "px" else 0.0
    cap = _INF if cell.box.max_width is None else cell.box.max_width
    outer_min = max(cell.box.min_width, cell.min_content)
    if constrained:
        outer_max = max(cell.box.min_width, length, cell.min_content, min(cap, length))
    else:
        outer_max = max(cell.box.min_width, length, cell.min_content, min(cap, cell.max_content))
    return outer_min, max(outer_max, outer_min)


def _span_growth(
    columns: list[_Column],
    cell: _Cell,
    base_min: list[float],
    base_max: list[float],
    gutter: float,
) -> tuple[list[float], list[float]]:
    indexes = list(range(cell.column, cell.column + cell.span))
    grown_min = base_min[:]
    grown_max = base_max[:]
    border = gutter * (cell.span - 1)
    outer_min, outer_max = _outer(cell, False)
    min_excess = outer_min - sum(base_min[index] for index in indexes) - border
    max_excess = outer_max - sum(base_max[index] for index in indexes) - border
    if min_excess > _EPS:
        _give(grown_min, min_excess, indexes, columns, False)
    if max_excess > _EPS:
        _give(grown_max, max_excess, indexes, columns, False)
    return grown_min, grown_max


def _span_percent(cell: _Cell, baseline: list[float], span1_max: list[float]) -> dict[int, float]:
    if cell.percent <= _EPS:
        return {}
    indexes = list(range(cell.column, cell.column + cell.span))
    subtracted = cell.percent - sum(baseline[index] for index in indexes)
    if subtracted <= _EPS:
        return {}
    receivers = [index for index in indexes if baseline[index] <= _EPS]
    if not receivers:
        return {}
    total = sum(span1_max[index] for index in receivers)
    if total <= _EPS:
        share = subtracted / len(receivers)
        return {index: share for index in receivers}
    return {index: subtracted * (span1_max[index] / total) for index in receivers}


def _clamp_percent(columns: list[_Column]) -> None:
    remaining = 100.0
    for column in columns:
        if column.percent < 0:
            column.percent = 0.0
        if column.percent > remaining:
            column.percent = remaining
        remaining -= column.percent


def _table_used(
    kind: str,
    specified: float | None,
    containing: float | None,
    gutter: float,
    columns: list[_Column],
) -> tuple[float, float, float]:
    border = gutter * (len(columns) + 1)
    grid_min = sum(column.min_w for column in columns) + border
    grid_max = sum(column.max_w for column in columns) + border
    if kind == "auto":
        cap = _INF if containing is None else containing
        used = max(min(grid_max, cap), grid_min)
    elif kind == "min-content":
        used = grid_min
    elif kind == "max-content":
        used = grid_max
    else:
        used = max(specified or 0.0, grid_min)
    assignable = used - border
    if assignable < 0:
        assignable = 0.0
    return used, assignable, border


def _distribute(columns: list[_Column], assignable: float) -> list[float]:
    guesses = _guesses(columns, assignable)
    sums = [sum(row) for row in guesses]
    if assignable <= sums[0] + _EPS:
        return guesses[0]
    for index in range(1, 4):
        if assignable <= sums[index] + _EPS:
            return _blend(guesses[index - 1], guesses[index], sums[index - 1], sums[index], assignable)
    widths = guesses[3][:]
    _give(widths, assignable - sums[3], list(range(len(columns))), columns, True)
    return widths


def _guesses(columns: list[_Column], assignable: float) -> list[list[float]]:
    def percent_size(column: _Column) -> float | None:
        if column.percent <= _EPS:
            return None
        return max(column.percent * assignable / 100.0, column.min_w)

    minimum = [column.min_w for column in columns]
    percentage = [column.min_w if percent_size(column) is None else percent_size(column) or 0.0 for column in columns]
    specified: list[float] = []
    maximum: list[float] = []
    for column in columns:
        sized = percent_size(column)
        if sized is not None:
            specified.append(sized)
            maximum.append(sized)
        else:
            specified.append(column.max_w if column.constrained else column.min_w)
            maximum.append(column.max_w)
    rows = [minimum, percentage, specified, maximum]
    for index in range(len(columns)):
        for guess in range(1, 4):
            if rows[guess][index] < rows[guess - 1][index]:
                rows[guess][index] = rows[guess - 1][index]
    return rows


def _blend(low: list[float], high: list[float], low_sum: float, high_sum: float, target: float) -> list[float]:
    span = high_sum - low_sum
    if span <= _EPS:
        return high[:]
    portion = (target - low_sum) / span
    if portion < 0:
        portion = 0.0
    if portion > 1:
        portion = 1.0
    return [low[index] + portion * (high[index] - low[index]) for index in range(len(low))]


def _give(
    widths: list[float],
    excess: float,
    indexes: list[int],
    columns: list[_Column],
    require_origin: bool,
) -> None:
    if excess <= _EPS or not indexes:
        return

    def choose(pred, origin: bool) -> list[int]:
        found: list[int] = []
        for index in indexes:
            column = columns[index]
            if origin and require_origin and not column.has_origin:
                continue
            if pred(column):
                found.append(index)
        return found

    steps = (
        (lambda column: (not column.constrained) and column.percent <= _EPS and column.max_w > _EPS, True, "max"),
        (lambda column: (not column.constrained) and column.percent <= _EPS, True, "equal"),
        (lambda column: column.constrained and column.percent <= _EPS and column.max_w > _EPS, True, "max"),
        (lambda column: column.percent > _EPS, False, "percent"),
        (lambda column: True, True, "equal"),
        (lambda column: True, False, "equal"),
    )
    for pred, origin, mode in steps:
        chosen = choose(pred, origin)
        if not chosen:
            continue
        if mode == "max":
            weights = [columns[index].max_w for index in chosen]
        elif mode == "percent":
            weights = [columns[index].percent for index in chosen]
        else:
            weights = None
        _add(widths, chosen, excess, weights)
        return


def _add(widths: list[float], indexes: list[int], excess: float, weights: list[float] | None) -> None:
    if weights is None or sum(weights) <= _EPS:
        share = excess / len(indexes)
        for index in indexes:
            widths[index] += share
        return
    total = sum(weights)
    for index, weight in zip(indexes, weights):
        widths[index] += excess * (weight / total)


def _index(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or isinstance(value, bool):
        raise _Invalid(f"{name} is invalid")
    if value < 1 and "span" in name:
        raise _Invalid(f"{name} must be positive")
    if value < 0:
        raise _Invalid(f"{name} is invalid")
    return value


def _length(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _Invalid(f"{name} is invalid")
    number = float(value)
    if number != number or number in {_INF, -_INF} or number < 0:
        raise _Invalid(f"{name} is invalid")
    return number


def _number(value: float) -> int | float:
    nearest = round(value)
    if abs(value - nearest) <= 1e-9:
        return int(nearest)
    return value
