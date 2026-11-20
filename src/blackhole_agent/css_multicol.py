"""Flow unbreakable boxes through one continuous CSS multicol container.

CSS Multi-column §3.4 chooses the used column-count N and column-width W
from the available inline size U. A specified count with an automatic width
uses that count. An automatic count uses as many column-width slots as fit,
and at least one. When both are specified, the count is clamped to the slots
that fit, and still at least one. Columns then stretch so N widths and the
gaps between them fill U. A non-positive column-width plus gap would divide
by zero; this reader rejects that instead of inventing a 1px floor. When
both properties are auto, the element is not a multicol container.

§6.1 and §7.1 then fill those columns. Each box is an unbreakable block
with an integer block size. ``column-span: all`` ends the current multicol
line, balances that line, and starts the next line below the spanner.
``column-fill: balance`` and ``balance-all`` use the same shortest line
size here, because this container is not fragmented further. That size is
the smallest block size that can hold the run in N columns. The boxes are
then filled in source order: a later box stays in the current column when
it still fits, so a shorter last column is not rearranged to look even.
``column-fill: auto`` needs a constrained column block size and is rejected
here. ``fragment_columns`` fills that fixed block size and honors column
breaks. This balancer does not break text, measure an inline min-content,
collapse margins, or paint a column rule. Fragment heights are CSS pixels
and are already the unbreakable border-box block size.
"""

from __future__ import annotations

from dataclasses import dataclass

_FILLS = frozenset({"balance", "balance-all"})
_SPANS = frozenset({"none", "all"})
_FIELDS = frozenset({"id", "height", "span"})


class _Invalid(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class _Frag:
    id: str
    height: int
    span: str


def layout_multicol(
    available_inline: object,
    fragments: object,
    *,
    column_width: object = "auto",
    column_count: object = "auto",
    column_gap: object = 0,
    column_fill: object = "balance",
) -> dict[str, object]:
    """Place fragments and spanners into used multicol lines.

    ``available_inline`` is the multicol content inline size U.
    ``column_width`` and ``column_count`` are non-negative and positive
    integers, or ``auto``. ``column_gap`` is a non-negative integer.
    ``column_fill`` is ``balance`` or ``balance-all``. Each fragment has
    ``id``, ``height``, and an optional ``span`` of ``none`` or ``all``.
    """

    try:
        available = _length(available_inline, "available_inline", minimum=0)
        gap = _length(column_gap, "column_gap", minimum=0)
        width = _auto_length(column_width, "column_width", minimum=0)
        count = _auto_length(column_count, "column_count", minimum=1)
        if column_fill not in _FILLS:
            raise _Invalid("column_fill")
        items = _fragments(fragments)
        used_count, used_width = _used_columns(available, width, count, gap)
    except _Invalid as exc:
        return _invalid(exc.reason)

    placed, block_size = _flow(items, available, gap, used_count, used_width)
    return {
        "outcome": "flowed",
        "column_count": used_count,
        "column_width": used_width,
        "column_gap": gap,
        "block_size": block_size,
        "boxes": placed,
    }


def _used_columns(
    available: int,
    width: int | None,
    count: int | None,
    gap: int,
) -> tuple[int, int | float]:
    if width is None:
        if count is None:
            raise _Invalid("not a multicol container")
        used = count
    else:
        divisor = width + gap
        if divisor <= 0:
            raise _Invalid("column size")
        fitted = (available + gap) // divisor
        if count is None:
            used = max(1, fitted)
        else:
            used = min(count, max(1, fitted))
    return used, _column_width(available, gap, used)


def _column_width(available: int, gap: int, count: int) -> int | float:
    raw = available - gap * (count - 1)
    if raw <= 0:
        return 0
    if raw % count == 0:
        return raw // count
    return raw / count


def _column_inline(index: int, available: int, gap: int, count: int) -> int | float:
    raw = available - gap * (count - 1)
    if raw <= 0:
        return index * gap
    product = index * (available + gap)
    if product % count == 0:
        return product // count
    return product / count


def _flow(
    items: list[_Frag],
    available: int,
    gap: int,
    count: int,
    width: int | float,
) -> tuple[list[dict[str, object]], int]:
    placed: list[dict[str, object]] = []
    run: list[_Frag] = []
    cursor = 0
    line = 0

    def flush() -> None:
        nonlocal cursor, line, run
        if not run:
            return
        heights = [item.height for item in run]
        limit = _min_block(heights, count)
        for column, group in enumerate(_pack(heights, limit)):
            offset = 0
            for position in group:
                item = run[position]
                placed.append(
                    _box(
                        item,
                        column=column,
                        line=line,
                        inline=_column_inline(column, available, gap, count),
                        block=cursor + offset,
                        width=width,
                    )
                )
                offset += item.height
        cursor += limit
        line += 1
        run = []

    for item in items:
        if item.span == "all":
            flush()
            placed.append(
                _box(
                    item,
                    column=None,
                    line=None,
                    inline=0,
                    block=cursor,
                    width=available,
                )
            )
            cursor += item.height
            continue
        run.append(item)
    flush()
    return placed, cursor


def _min_block(heights: list[int], columns: int) -> int:
    low = max(heights)
    high = sum(heights)
    while low < high:
        mid = (low + high) // 2
        if _fits(heights, mid, columns):
            high = mid
        else:
            low = mid + 1
    return low


def _fits(heights: list[int], limit: int, columns: int) -> bool:
    used = 1
    running = 0
    started = False
    for height in heights:
        if height > limit:
            return False
        if started and running + height > limit:
            used += 1
            if used > columns:
                return False
            running = 0
        started = True
        running += height
    return True


def _pack(heights: list[int], limit: int) -> list[list[int]]:
    columns: list[list[int]] = []
    current: list[int] = []
    running = 0
    for index, height in enumerate(heights):
        if current and running + height > limit:
            columns.append(current)
            current = []
            running = 0
        current.append(index)
        running += height
    if current:
        columns.append(current)
    return columns


def _box(
    item: _Frag,
    *,
    column: int | None,
    line: int | None,
    inline: int | float,
    block: int,
    width: int | float,
) -> dict[str, object]:
    return {
        "id": item.id,
        "span": item.span,
        "column": column,
        "line": line,
        "inline": inline,
        "block": block,
        "width": width,
        "height": item.height,
    }


def _fragments(value: object) -> list[_Frag]:
    if type(value) is not list:
        raise _Invalid("fragments")
    parsed: list[_Frag] = []
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
        span = raw.get("span", "none")
        if type(span) is not str or span not in _SPANS:
            raise _Invalid("span")
        parsed.append(_Frag(ident, height, span))
    return parsed


def _auto_length(value: object, name: str, *, minimum: int) -> int | None:
    if value == "auto":
        return None
    return _length(value, name, minimum=minimum)


def _length(value: object, name: str, *, minimum: int) -> int:
    if type(value) is not int or value < minimum:
        raise _Invalid(name)
    return value


def _invalid(reason: str) -> dict[str, object]:
    return {
        "outcome": "invalid",
        "reason": reason,
        "column_count": None,
        "column_width": None,
        "column_gap": None,
        "block_size": None,
        "boxes": None,
    }
