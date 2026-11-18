"""Used column widths for a fixed CSS table.

CSS 2.2 §17.5.2.1 sizes a fixed table from the table width, the columns, and
the first row. css-tables-3 §3.5.1 keeps that layout only for a definite
table width: ``auto`` and ``max-content`` stay on automatic layout, and cell
content is ignored. A column width other than ``auto`` wins over the cell
that covers it. A first-row cell divides its specified width equally across
the still-open columns in its span.

Pixel columns keep those lengths. Percentages resolve against the assignable
width, which is the table width minus one inter-column spacing per gap.
Percentages shrink together when they would overflow the room left by the
pixel columns. If the pixel columns alone overflow, percentages and open
columns become zero and the used table width grows. Open columns share any
positive remainder and stay at zero when none is left. When every column is
already specified and the table is still wider, the extra goes to the
nonzero lengths in proportion, otherwise to the nonzero percentages, otherwise
equally to the zero columns.

This does not measure cell content, row heights, captions, or the border
conflict of collapsed borders. ``spacing`` is only the gap between adjacent
columns.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_AUTOMATIC = frozenset({"auto", "max-content"})
_PERCENT = re.compile(r"^(\d+(?:\.\d+)?)%$")


class _Invalid(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass
class _Slot:
    kind: str
    value: float


def layout_fixed_columns(
    table_width: object,
    columns: object,
    *,
    cells: object = None,
    spacing: object = 0,
) -> dict[str, object]:
    """Return the used width of each column and of the table.

    ``columns`` are ``auto``, a length, or a percentage string such as
    ``\"50%\"``. ``cells`` is the first row, in order, each with ``span`` and
    ``width``. ``spacing`` is the horizontal border-spacing between columns.
    """

    try:
        specified = _table_width(table_width)
        slots = _columns(columns)
        _apply_cells(slots, cells, len(slots))
        gutter = _length(spacing, name="spacing")
    except _Invalid as exc:
        return _invalid(exc.reason)
    if specified is None:
        return {
            "outcome": "automatic",
            "reason": "fixed layout requires a definite table width",
            "column_widths": None,
            "table_width": None,
            "used_table_width": None,
            "assignable": None,
            "spacing": None,
        }
    widths, assignable, used = _resolve(slots, specified, gutter)
    return {
        "outcome": "resolved",
        "reason": None,
        "column_widths": [_number(width) for width in widths],
        "table_width": _number(specified),
        "used_table_width": _number(used),
        "assignable": _number(assignable),
        "spacing": _number(gutter),
    }


def _invalid(reason: str) -> dict[str, object]:
    return {
        "outcome": "invalid",
        "reason": reason,
        "column_widths": None,
        "table_width": None,
        "used_table_width": None,
        "assignable": None,
        "spacing": None,
    }


def _table_width(value: object) -> float | None:
    if isinstance(value, str):
        keyword = value.strip().lower()
        if keyword in _AUTOMATIC:
            return None
        raise _Invalid("table width is invalid")
    return _length(value, name="table width")


def _columns(value: object) -> list[_Slot]:
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)) or not value:
        raise _Invalid("columns must be a non-empty list")
    return [_width(raw, f"column {index}") for index, raw in enumerate(value)]


def _apply_cells(slots: list[_Slot], cells: object, count: int) -> None:
    if cells is None:
        return
    if isinstance(cells, (str, bytes)) or not isinstance(cells, (list, tuple)):
        raise _Invalid("cells must be a list")
    cursor = 0
    for index, raw in enumerate(cells):
        span, width = _cell(raw, index)
        if cursor + span > count:
            raise _Invalid(f"cell {index} span is outside the columns")
        open_columns = [slot for slot in range(cursor, cursor + span) if slots[slot].kind == "auto"]
        if width.kind != "auto" and open_columns:
            share = width.value / len(open_columns)
            for slot in open_columns:
                slots[slot] = _Slot(width.kind, share)
        cursor += span


def _cell(raw: object, index: int) -> tuple[int, _Slot]:
    if not isinstance(raw, dict):
        raise _Invalid(f"cell {index} must be a mapping")
    unknown = set(raw) - {"span", "width"}
    if unknown:
        raise _Invalid(f"cell {index} has an unknown field")
    if "width" not in raw:
        raise _Invalid(f"cell {index} needs a width")
    span = raw.get("span", 1)
    if isinstance(span, bool) or not isinstance(span, int) or span < 1:
        raise _Invalid(f"cell {index} span must be positive")
    return span, _width(raw["width"], f"cell {index} width")


def _width(value: object, name: str) -> _Slot:
    if isinstance(value, str):
        text = value.strip().lower()
        if text == "auto":
            return _Slot("auto", 0.0)
        match = _PERCENT.fullmatch(text)
        if match is None:
            raise _Invalid(f"{name} is invalid")
        return _Slot("pct", float(match.group(1)))
    return _Slot("px", _length(value, name=name))


def _resolve(slots: list[_Slot], table_width: float, spacing: float) -> tuple[list[float], float, float]:
    count = len(slots)
    gaps = spacing * (count - 1) if count > 1 else 0.0
    assignable = table_width - gaps
    fit = 0.0 if assignable < 0 else assignable
    widths = [0.0] * count
    pixel_sum = 0.0
    percent_raw = [0.0] * count
    percent_sum = 0.0
    for index, slot in enumerate(slots):
        if slot.kind == "px":
            widths[index] = slot.value
            pixel_sum += slot.value
        elif slot.kind == "pct":
            resolved = (slot.value * fit) / 100.0
            percent_raw[index] = resolved
            percent_sum += resolved
    if pixel_sum < fit and pixel_sum + percent_sum <= fit:
        for index, slot in enumerate(slots):
            if slot.kind == "pct":
                widths[index] = percent_raw[index]
        remainder = fit - pixel_sum - percent_sum
        open_columns = [index for index, slot in enumerate(slots) if slot.kind == "auto"]
        if open_columns:
            share = remainder / len(open_columns)
            for index in open_columns:
                widths[index] = share
        elif remainder > 0:
            _give_excess(slots, widths, remainder)
    elif pixel_sum < fit and percent_sum > 0:
        scale = (fit - pixel_sum) / percent_sum
        for index, slot in enumerate(slots):
            if slot.kind == "pct":
                widths[index] = percent_raw[index] * scale
    used = sum(widths) + gaps
    return widths, fit, used


def _give_excess(slots: list[_Slot], widths: list[float], excess: float) -> None:
    lengths = [index for index, slot in enumerate(slots) if slot.kind == "px" and slot.value > 0]
    if lengths:
        _add_share(widths, lengths, excess, [slots[index].value for index in lengths])
        return
    percentages = [index for index, slot in enumerate(slots) if slot.kind == "pct" and slot.value > 0]
    if percentages:
        _add_share(widths, percentages, excess, [slots[index].value for index in percentages])
        return
    share = excess / len(widths)
    for index in range(len(widths)):
        widths[index] += share


def _add_share(widths: list[float], indexes: list[int], excess: float, weights: list[float]) -> None:
    total = sum(weights)
    for index, weight in zip(indexes, weights):
        widths[index] += excess * (weight / total)


def _length(value: object, *, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _Invalid(f"{name} is invalid")
    number = float(value)
    if number != number or number in {float("inf"), float("-inf")}:
        raise _Invalid(f"{name} is invalid")
    if number < 0:
        raise _Invalid(f"{name} cannot be negative")
    return number


def _number(value: float) -> int | float:
    nearest = round(value)
    if abs(value - nearest) <= 1e-9:
        return int(nearest)
    return value
