"""Lay out CSS table rows from alignment, rowspan, and the table height.

CSS Tables 3 §3.10.2 builds each row as a line box of the cells that
originate there. A cell that spans later rows contributes its baseline and
a zero height to that line box; its content height is distributed afterwards.
Baseline cells are placed first. The row baseline is the largest distance
from the top of those cell boxes to their baselines. Top cells then sit on
the row's top. A middle or bottom cell that is taller than that provisional
height lowers the bottom. If the row has no baseline cell, its baseline is
the bottom of that line box. Other ``vertical-align`` values align as
baseline. A baseline may sit below the row, which CSS allows when the first
line box ends past the cell's bottom border.

Specified row and single-row cell heights are ignored while the line box is
built. They then raise the span-1 size, and percentages count as zero until
the table height is a definite length. §3.10.2 distributes a taller spanning
cell with the §3.8.3 column measure. Span-1 min-content and max-content start
equal, so the min-content ratio is undefined and adds nothing. The extra is
split in proportion to those heights. A zero sum uses an equal share, the
same fallback §3.8.3 gives an undefined percentage ratio. Gaps inside the
span are reserved and are not given to the rows. The baseline stays put;
only the bottom moves.

§3.10.1 treats a definite table height as a minimum. Content that is already
taller wins. §3.10.5 then sets each row's reference size to the larger of its
content size and the second pass, where row and cell percentages resolve
against that table height. A table shorter than the reference sizes blends
each row between the two passes. A taller table gives the leftover in equal
shares to rows whose size comes only from content. When no such row exists,
every row shares it. Neither step moves a baseline.

The caller supplies content heights and baselines. This does not break text,
collapse borders, or size columns. ``border_spacing`` matches
``layout_auto_columns``: one gap before the first row, one after the last,
and one between each pair. Those outer gaps are part of the table height and
are not part of a cell's border box. A row listed in ``collapsed_rows`` has
height zero and does not keep the gap after itself, so a hidden empty row
leaves spacing on only one side. The leading gap stays, including when every
row is collapsed.
"""

from __future__ import annotations

from dataclasses import dataclass

_ALIGNS = frozenset({"baseline", "top", "middle", "bottom"})
_INF = float("inf")


class _Invalid(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class _Row:
    kind: str
    value: float


@dataclass(frozen=True)
class _Cell:
    id: str
    row: int
    rowspan: int
    content_height: float
    baseline: float
    align: str
    specified_kind: str
    specified: float


def layout_table_rows(
    rows: object,
    cells: object = (),
    *,
    table_height: object = "auto",
    border_spacing: object = 0,
    collapsed_rows: object = (),
) -> dict[str, object]:
    """Return used row heights and each cell's content position.

    ``rows`` is one entry per row: ``auto``, a non-negative length, a
    percentage string, or a mapping with ``height``. ``cells`` name ``id``,
    ``row``, ``content_height``, and optionally ``rowspan``, ``baseline``,
    ``vertical_align``, and ``height``. ``table_height`` is ``auto`` or a
    resolved length. ``border_spacing`` is the vertical border-spacing.
    ``collapsed_rows`` lists rows whose height is forced to zero and whose
    trailing border-spacing gap is omitted.
    """

    try:
        parsed_rows = _rows(rows)
        parsed_cells = _cells(cells, len(parsed_rows))
        collapsed = _collapsed(collapsed_rows, len(parsed_rows))
        specified = _table_height(table_height)
        spacing = _length(border_spacing, "border_spacing")
        bases, baselines, auto = _pass(parsed_rows, parsed_cells, specified, spacing, False)
        for index in collapsed:
            bases[index] = 0.0
            auto[index] = False
        if specified is None:
            refs = bases
        else:
            refs, _, _ = _pass(parsed_rows, parsed_cells, specified, spacing, True)
            for index in collapsed:
                refs[index] = 0.0
            refs = [max(base, ref) for base, ref in zip(bases, refs)]
        heights = _finalize(bases, refs, auto, specified, spacing, collapsed)
        for index in collapsed:
            heights[index] = 0.0
    except _Invalid as exc:
        return _invalid(exc.reason)

    placed = [
        _place(cell, heights, baselines, spacing, collapsed) for cell in parsed_cells
    ]
    edge = _spacing_slots(len(heights), collapsed) * spacing
    return {
        "outcome": "resolved",
        "reason": None,
        "row_heights": [_number(height) for height in heights],
        "row_baselines": [_number(baseline) for baseline in baselines],
        "used_table_height": _number(sum(heights) + edge),
        "border_spacing": _number(spacing),
        "cells": placed,
    }


def _pass(
    rows: list[_Row],
    cells: list[_Cell],
    table_height: float | None,
    spacing: float,
    resolve_percent: bool,
) -> tuple[list[float], list[float], list[bool]]:
    seeds: list[float] = []
    baselines: list[float] = []
    auto: list[bool] = []
    for index, row in enumerate(rows):
        originating = [cell for cell in cells if cell.row == index]
        height, baseline = _linebox(originating)
        floor = max(height, _specified_length(row.kind, row.value, table_height, resolve_percent))
        exclusive = True
        for cell in originating:
            if cell.rowspan != 1:
                continue
            floor = max(
                floor,
                _specified_length(cell.specified_kind, cell.specified, table_height, resolve_percent),
            )
            if cell.specified_kind != "auto":
                exclusive = False
        if row.kind != "auto":
            exclusive = False
        seeds.append(floor)
        baselines.append(baseline)
        auto.append(exclusive)
    heights = _span_extra(seeds, cells, spacing, table_height, resolve_percent)
    return heights, baselines, auto


def _linebox(cells: list[_Cell]) -> tuple[float, float]:
    baseline_cells = [cell for cell in cells if cell.align == "baseline"]
    top_cells = [cell for cell in cells if cell.align == "top"]
    rest = [cell for cell in cells if cell.align in {"middle", "bottom"}]
    bottoms: list[float] = []
    if baseline_cells:
        baseline = max(cell.baseline for cell in baseline_cells)
        for cell in baseline_cells:
            box = 0.0 if cell.rowspan > 1 else cell.content_height
            bottoms.append(baseline - cell.baseline + box)
    else:
        baseline = None
    for cell in top_cells:
        bottoms.append(0.0 if cell.rowspan > 1 else cell.content_height)
    height = max(bottoms, default=0.0)
    for cell in rest:
        box = 0.0 if cell.rowspan > 1 else cell.content_height
        if box > height:
            height = box
    if height < 0.0:
        height = 0.0
    if baseline is None:
        baseline = height
    return height, baseline


def _span_extra(
    seeds: list[float],
    cells: list[_Cell],
    spacing: float,
    table_height: float | None,
    resolve_percent: bool,
) -> list[float]:
    heights = list(seeds)
    grouped: dict[int, list[_Cell]] = {}
    for cell in cells:
        if cell.rowspan > 1:
            grouped.setdefault(cell.rowspan, []).append(cell)
    for span in range(2, len(heights) + 1):
        group = grouped.get(span)
        if not group:
            continue
        snapshot = list(heights)
        updated = list(heights)
        for cell in group:
            outer = max(
                cell.content_height,
                _specified_length(cell.specified_kind, cell.specified, table_height, resolve_percent),
            )
            covered = range(cell.row, cell.row + span)
            base = sum(snapshot[index] for index in covered)
            gaps = (span - 1) * spacing
            overflow = outer - base - gaps
            if overflow < 0.0:
                overflow = 0.0
            for index in covered:
                ratio = (1.0 / span) if base == 0.0 else snapshot[index] / base
                contribution = snapshot[index] + ratio * overflow
                if contribution > updated[index]:
                    updated[index] = contribution
        heights = updated
    return heights


def _finalize(
    bases: list[float],
    refs: list[float],
    auto: list[bool],
    table_height: float | None,
    spacing: float,
    collapsed: set[int],
) -> list[float]:
    count = len(bases)
    edge = _spacing_slots(count, collapsed) * spacing
    base_sum = sum(bases)
    ref_sum = sum(refs)
    base_grid = base_sum + edge
    ref_grid = ref_sum + edge
    target_grid = base_grid if table_height is None else max(table_height, base_grid)
    if target_grid <= ref_grid:
        target_rows = target_grid - edge
        if ref_sum <= base_sum:
            return list(bases)
        portion = (target_rows - base_sum) / (ref_sum - base_sum)
        if portion < 0.0:
            portion = 0.0
        if portion > 1.0:
            portion = 1.0
        return [base + portion * (ref - base) for base, ref in zip(bases, refs)]
    extra = target_grid - ref_grid
    chosen = [index for index, flag in enumerate(auto) if flag and index not in collapsed]
    if not chosen:
        chosen = [index for index in range(count) if index not in collapsed]
    if not chosen:
        chosen = list(range(count))
    share = extra / len(chosen)
    out = list(refs)
    for index in chosen:
        out[index] = refs[index] + share
    return out


def _place(
    cell: _Cell,
    heights: list[float],
    baselines: list[float],
    spacing: float,
    collapsed: set[int],
) -> dict[str, object]:
    block = _span_size(heights, spacing, cell.row, cell.rowspan, collapsed)
    if cell.align == "top":
        content_top = 0.0
    elif cell.align == "bottom":
        content_top = block - cell.content_height
    elif cell.align == "middle":
        content_top = (block - cell.content_height) / 2.0
    else:
        content_top = baselines[cell.row] - cell.baseline
    return {
        "id": cell.id,
        "content_top": _number(content_top),
        "border_top": _number(_border_top(heights, spacing, cell.row, collapsed)),
        "border_height": _number(block),
    }


def _span_size(
    heights: list[float], spacing: float, row: int, span: int, collapsed: set[int]
) -> float:
    size = 0.0
    for offset in range(span):
        size += heights[row + offset]
        if offset:
            size += _gap_after(row + offset - 1, spacing, collapsed)
    return size


def _border_top(heights: list[float], spacing: float, row: int, collapsed: set[int]) -> float:
    top = spacing
    for index in range(row):
        top += heights[index] + _gap_after(index, spacing, collapsed)
    return top


def _gap_after(index: int, spacing: float, collapsed: set[int]) -> float:
    if index in collapsed:
        return 0.0
    return spacing


def _spacing_slots(count: int, collapsed: set[int]) -> int:
    return 1 + sum(1 for index in range(count) if index not in collapsed)


def _collapsed(value: object, count: int) -> set[int]:
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple, set, frozenset)):
        raise _Invalid("collapsed_rows")
    chosen: set[int] = set()
    for item in value:
        index = _index(item, "collapsed_rows")
        if index >= count:
            raise _Invalid("collapsed_rows")
        chosen.add(index)
    return chosen


def _specified_length(
    kind: str,
    value: float,
    table_height: float | None,
    resolve_percent: bool,
) -> float:
    if kind == "length":
        return value
    if kind == "pct" and resolve_percent and table_height is not None:
        return value / 100.0 * table_height
    return 0.0


def _rows(value: object) -> list[_Row]:
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise _Invalid("rows")
    if not value:
        raise _Invalid("rows")
    return [_row(item, index) for index, item in enumerate(value)]


def _row(value: object, index: int) -> _Row:
    if isinstance(value, dict):
        if "height" not in value:
            raise _Invalid(f"row {index}")
        value = value["height"]
    return _size(value, f"row {index}")


def _cells(value: object, row_count: int) -> list[_Cell]:
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise _Invalid("cells")
    cells = [_cell(item, index, row_count) for index, item in enumerate(value)]
    seen: set[str] = set()
    for cell in cells:
        if cell.id in seen:
            raise _Invalid("cells")
        seen.add(cell.id)
    return cells


def _cell(value: object, index: int, row_count: int) -> _Cell:
    if not isinstance(value, dict):
        raise _Invalid(f"cell {index}")
    name = value.get("id")
    if not isinstance(name, str) or not name.strip():
        raise _Invalid(f"cell {index}")
    row = _index(value.get("row"), f"cell {index} row")
    span = _index(value.get("rowspan", 1), f"cell {index} rowspan")
    if span < 1 or row + span > row_count:
        raise _Invalid(f"cell {index} rowspan")
    content = _length(value.get("content_height"), f"cell {index} content_height")
    if "baseline" in value:
        baseline = _signed(value.get("baseline"), f"cell {index} baseline")
    else:
        baseline = content
    align = _align(value.get("vertical_align", "baseline"), f"cell {index} vertical_align")
    kind, specified = _optional_size(value.get("height", "auto"), f"cell {index} height")
    return _Cell(name, row, span, content, baseline, align, kind, specified)


def _size(value: object, name: str) -> _Row:
    kind, number = _optional_size(value, name)
    return _Row(kind, number)


def _optional_size(value: object, name: str) -> tuple[str, float]:
    if isinstance(value, str):
        text = value.strip().lower()
        if text == "auto":
            return "auto", 0.0
        if text.endswith("%"):
            number = _percent(text)
            if number is None:
                raise _Invalid(name)
            return "pct", number
        raise _Invalid(name)
    return "length", _length(value, name)


def _table_height(value: object) -> float | None:
    if isinstance(value, str):
        if value.strip().lower() == "auto":
            return None
        raise _Invalid("table_height")
    return _length(value, "table_height")


def _align(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise _Invalid(name)
    text = value.strip().lower()
    if text in _ALIGNS:
        return text
    if text:
        return "baseline"
    raise _Invalid(name)


def _percent(text: str) -> float | None:
    number = text[:-1].strip()
    if not number or number.count(".") > 1:
        return None
    try:
        value = float(number)
    except ValueError:
        return None
    if value != value or value < 0.0 or value == _INF:
        return None
    return value


def _index(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise _Invalid(name)
    if value < 0:
        raise _Invalid(name)
    return value


def _length(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _Invalid(name)
    number = float(value)
    if number != number or number == _INF or number < 0.0:
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
        "row_heights": None,
        "row_baselines": None,
        "used_table_height": None,
        "border_spacing": None,
        "cells": None,
    }
