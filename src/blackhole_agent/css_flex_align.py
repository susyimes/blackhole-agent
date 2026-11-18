"""Place resolved flex items on the main and cross axes.

CSS Flexbox aligns a line only after its main sizes exist. ``justify-content``
packs those outer main sizes. The fixed gap stays between items, and a
positive leftover is what the distribution shares. ``space-between`` falls
back to ``flex-start`` for one item or a negative leftover. ``space-around``
and ``space-evenly`` fall back to ``center`` in those same cases. A negative
leftover still shifts ``flex-end`` and ``center``.

``align-items`` and ``align-self`` place each item inside its line.
``stretch`` changes an automatic cross size only when both cross margins are
definite, then ``min-cross`` and ``max-cross`` clamp it and the minimum wins.
An automatic cross margin consumes a positive leftover and suppresses stretch.
A missing baseline falls back to ``flex-start``.

A ``nowrap`` line takes the container's inner cross size, so ``align-content``
cannot move it. A ``wrap`` line takes the larger of its baseline requirement
and the other items' outer hypothetical cross sizes. ``stretch`` shares a
positive leftover across those lines. The other values pack them.
``wrap-reverse`` keeps that logical result and reports it from the container's
end edge. Coordinates grow from the container's start edge toward its end.
"""

from __future__ import annotations

from dataclasses import dataclass

_EPS = 1e-9
_AUTO = "auto"
_NONE = "none"
_JUSTIFY = frozenset(
    {"flex-start", "flex-end", "center", "space-between", "space-around", "space-evenly", "normal"}
)
_ITEMS = frozenset({"flex-start", "flex-end", "center", "stretch", "baseline", "normal"})
_SELF = _ITEMS | {"auto"}
_CONTENT = frozenset(
    {"flex-start", "flex-end", "center", "space-between", "space-around", "space-evenly", "stretch", "normal"}
)
_WRAPS = frozenset({"nowrap", "wrap", "wrap-reverse"})
_PACK = frozenset({"flex-start", "flex-end", "center", "space-between", "space-around", "space-evenly"})


class _Invalid(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class _Item:
    ident: str
    main: float
    cross_auto: bool
    cross: float
    min_cross: float
    max_cross: float | None
    margin_start_auto: bool
    margin_start: float
    margin_end_auto: bool
    margin_end: float
    align: str
    baseline: float | None

    def hypothetical_inner(self) -> float:
        return _clamp(self.cross, self.min_cross, self.max_cross)

    def hypothetical_outer(self) -> float:
        return _fixed_margin(self.margin_start_auto, self.margin_start) + self.hypothetical_inner() + _fixed_margin(
            self.margin_end_auto, self.margin_end
        )

    def participates(self) -> bool:
        return (
            self.align == "baseline"
            and self.baseline is not None
            and not self.margin_start_auto
            and not self.margin_end_auto
        )

    def used_inner(self, line_size: float) -> float:
        if (
            self.align == "stretch"
            and self.cross_auto
            and not self.margin_start_auto
            and not self.margin_end_auto
        ):
            return _clamp(line_size - self.margin_start - self.margin_end, self.min_cross, self.max_cross)
        return self.hypothetical_inner()

    def placement(self) -> str:
        if self.margin_start_auto or self.margin_end_auto:
            return "flex-start"
        if self.align in {"stretch", "baseline"} and not self.participates():
            return "flex-start"
        return self.align


def place_flex_alignment(
    container_main: object,
    container_cross: object,
    lines: object,
    *,
    justify_content: object = "flex-start",
    align_items: object = "stretch",
    align_content: object = "stretch",
    wrap: object = "nowrap",
    main_gap: object = 0,
    cross_gap: object = 0,
) -> dict[str, object]:
    """Return the margin-box position of each item.

    ``container_main`` and ``container_cross`` are definite inner sizes.
    ``lines`` runs from the first flex line toward the cross end before
    ``wrap-reverse`` is applied. Each item has ``id``, outer ``main``, and
    ``cross`` (a length or ``auto``). An automatic cross size reads
    ``content``. ``min_cross`` defaults to 0 and a negative value becomes 0.
    ``max_cross`` defaults to ``none`` and a negative value becomes 0. The
    minimum wins when they disagree. Cross margins default to 0 and may be
    ``auto`` or negative. ``align_self`` defaults to ``auto``. ``baseline`` is
    the distance from the cross-start margin edge to the alignment baseline.
    """

    try:
        main_size = _length(container_main, allow_negative=False, name="container main")
        cross_size = _length(container_cross, allow_negative=False, name="container cross")
        main_gutter = _length(main_gap, allow_negative=False, name="main gap")
        cross_gutter = _length(cross_gap, allow_negative=False, name="cross gap")
        packing = _resolve_justify(_keyword(justify_content, _JUSTIFY, "justify-content"))
        items_align = _resolve_items(_keyword(align_items, _ITEMS, "align-items"))
        content_align = _resolve_content(_keyword(align_content, _CONTENT, "align-content"))
        mode = _keyword(wrap, _WRAPS, "wrap")
        parsed = _lines(lines, items_align)
        if mode == "nowrap" and len(parsed) > 1:
            raise _Invalid("nowrap cannot contain more than one line")
        placed = _place(main_size, cross_size, parsed, packing, content_align, mode, main_gutter, cross_gutter)
    except _Invalid as exc:
        return _invalid(exc.reason)
    return {
        "outcome": "placed",
        "container_main": _number(main_size),
        "container_cross": _number(cross_size),
        "justify_content": packing,
        "align_items": items_align,
        "align_content": content_align,
        "wrap": mode,
        "main_gap": _number(main_gutter),
        "cross_gap": _number(cross_gutter),
        "lines": placed,
    }


def _place(
    main_size: float,
    cross_size: float,
    lines: list[list[_Item]],
    justify: str,
    align_content: str,
    wrap: str,
    main_gap: float,
    cross_gap: float,
) -> list[dict[str, object]]:
    single = wrap == "nowrap"
    reverse = wrap == "wrap-reverse"
    sizes = [cross_size if single else _line_size(line) for line in lines]
    if not single and align_content == "stretch" and sizes:
        free = _leftover(cross_size, sizes, cross_gap)
        if free > 0:
            share = free / len(sizes)
            sizes = [size + share for size in sizes]
    if single:
        logical = [0.0 for _ in sizes]
    else:
        mode = "flex-start" if align_content == "stretch" else align_content
        logical = _pack(cross_size, sizes, cross_gap, mode)
    placed: list[dict[str, object]] = []
    for line, line_size, line_at in zip(lines, sizes, logical, strict=True):
        placed.append(_place_line(line, line_size, line_at, main_size, cross_size, justify, main_gap, reverse))
    return placed


def _place_line(
    items: list[_Item],
    line_size: float,
    line_at: float,
    main_size: float,
    container_cross: float,
    justify: str,
    main_gap: float,
    reverse: bool,
) -> dict[str, object]:
    mains = _pack(main_size, [item.main for item in items], main_gap, justify)
    participants = [item.baseline for item in items if item.participates()]
    baseline_at = max(participants) if participants else 0.0
    rendered: list[dict[str, object]] = []
    for item, main_at in zip(items, mains, strict=True):
        inner = item.used_inner(line_size)
        start, end = _used_margins(item, line_size, inner)
        outer = start + inner + end
        offset = _item_offset(item, outer, line_size, baseline_at)
        rendered.append(
            {
                "id": item.ident,
                "main": _number(main_at),
                "cross": _number(_physical(line_at + offset, outer, container_cross, reverse)),
                "main_size": _number(item.main),
                "cross_size": _number(inner),
                "margin_cross_start": _number(start),
                "margin_cross_end": _number(end),
            }
        )
    return {
        "cross": _number(_physical(line_at, line_size, container_cross, reverse)),
        "cross_size": _number(line_size),
        "items": rendered,
    }


def _line_size(items: list[_Item]) -> float:
    starts: list[float] = []
    ends: list[float] = []
    others: list[float] = []
    for item in items:
        outer = item.hypothetical_outer()
        if item.participates():
            assert item.baseline is not None
            starts.append(item.baseline)
            ends.append(outer - item.baseline)
        else:
            others.append(outer)
    requirement = 0.0
    if starts:
        requirement = max(starts) + max(ends)
    if others:
        requirement = max(requirement, max(others))
    return 0.0 if requirement < 0 else requirement


def _item_offset(item: _Item, outer: float, line_size: float, baseline_at: float) -> float:
    mode = item.placement()
    if mode == "flex-end":
        return line_size - outer
    if mode == "center":
        return (line_size - outer) / 2
    if mode == "baseline":
        assert item.baseline is not None
        return baseline_at - item.baseline
    return 0.0


def _used_margins(item: _Item, line_size: float, inner: float) -> tuple[float, float]:
    start = _fixed_margin(item.margin_start_auto, item.margin_start)
    end = _fixed_margin(item.margin_end_auto, item.margin_end)
    autos = int(item.margin_start_auto) + int(item.margin_end_auto)
    if not autos:
        return start, end
    leftover = line_size - start - inner - end
    if leftover <= _EPS:
        return start, end
    share = leftover / autos
    if item.margin_start_auto:
        start = share
    if item.margin_end_auto:
        end = share
    return start, end


def _pack(container: float, sizes: list[float], gap: float, mode: str) -> list[float]:
    count = len(sizes)
    if count == 0:
        return []
    if mode not in _PACK:
        raise _Invalid(f"alignment {mode} is invalid")
    free = _leftover(container, sizes, gap)
    used = _fallback(mode, free, count)
    if used == "flex-end":
        leading, extra = free, 0.0
    elif used == "center":
        leading, extra = free / 2, 0.0
    elif used == "space-between":
        leading, extra = 0.0, free / (count - 1)
    elif used == "space-around":
        leading, extra = free / (2 * count), free / count
    elif used == "space-evenly":
        leading = free / (count + 1)
        extra = leading
    else:
        leading, extra = 0.0, 0.0
    positions: list[float] = []
    cursor = leading
    for index, size in enumerate(sizes):
        positions.append(cursor)
        if index + 1 < count:
            cursor += size + gap + extra
    return positions


def _fallback(mode: str, free: float, count: int) -> str:
    if free < 0 or count < 2:
        if mode == "space-between":
            return "flex-start"
        if mode in {"space-around", "space-evenly"}:
            return "center"
    return mode


def _leftover(container: float, sizes: list[float], gap: float) -> float:
    count = len(sizes)
    free = container - sum(sizes) - gap * (count - 1 if count else 0)
    return 0.0 if abs(free) <= _EPS else free


def _physical(logical: float, size: float, container: float, reverse: bool) -> float:
    if not reverse:
        return logical
    return container - logical - size


def _lines(value: object, items_align: str) -> list[list[_Item]]:
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise _Invalid("lines must be a list of flex lines")
    parsed: list[list[_Item]] = []
    seen: set[str] = set()
    for index, line in enumerate(value):
        if isinstance(line, (str, bytes)) or not isinstance(line, (list, tuple)):
            raise _Invalid(f"line {index} must be a list of flex items")
        if not line:
            raise _Invalid(f"line {index} is empty")
        parsed.append([_item(entry, index, offset, items_align, seen) for offset, entry in enumerate(line)])
    return parsed


def _item(value: object, line: int, index: int, items_align: str, seen: set[str]) -> _Item:
    if not isinstance(value, dict):
        raise _Invalid(f"line {line} item {index} must be a mapping")
    ident = _ident(value.get("id", str(index)), line, index)
    if ident in seen:
        raise _Invalid(f"line {line} item {index} repeats id {ident}")
    seen.add(ident)
    cross_auto, cross = _cross(value, line, index)
    margin_start_auto, margin_start = _margin(value.get("margin_cross_start", 0), line, index, "start")
    margin_end_auto, margin_end = _margin(value.get("margin_cross_end", 0), line, index, "end")
    return _Item(
        ident=ident,
        main=_length(value.get("main"), allow_negative=True, name=f"line {line} item {index} main"),
        cross_auto=cross_auto,
        cross=cross,
        min_cross=_floor_zero(
            _length(value.get("min_cross", 0), allow_negative=True, name=f"line {line} item {index} min cross")
        ),
        max_cross=_maximum(value.get("max_cross", _NONE), f"line {line} item {index} max cross"),
        margin_start_auto=margin_start_auto,
        margin_start=margin_start,
        margin_end_auto=margin_end_auto,
        margin_end=margin_end,
        align=_resolve_self(
            _keyword(value.get("align_self", "auto"), _SELF, f"line {line} item {index} align-self"),
            items_align,
        ),
        baseline=_baseline(value, line, index),
    )


def _cross(value: dict[str, object], line: int, index: int) -> tuple[bool, float]:
    raw = value.get("cross", None)
    if isinstance(raw, str) and raw.strip().lower() == _AUTO:
        if "content" not in value:
            raise _Invalid(f"line {line} item {index} content is required")
        content = _length(value.get("content"), allow_negative=False, name=f"line {line} item {index} content")
        return True, content
    return False, _length(raw, allow_negative=False, name=f"line {line} item {index} cross")


def _margin(value: object, line: int, index: int, edge: str) -> tuple[bool, float]:
    if isinstance(value, str) and value.strip().lower() == _AUTO:
        return True, 0.0
    return False, _length(value, allow_negative=True, name=f"line {line} item {index} margin {edge}")


def _baseline(value: dict[str, object], line: int, index: int) -> float | None:
    if "baseline" not in value:
        return None
    baseline = _length(value.get("baseline"), allow_negative=False, name=f"line {line} item {index} baseline")
    return baseline


def _maximum(value: object, name: str) -> float | None:
    if _is_none(value):
        return None
    return _floor_zero(_length(value, allow_negative=True, name=name))


def _is_none(value: object) -> bool:
    if value is None:
        return True
    return isinstance(value, str) and value.strip().lower() == _NONE


def _resolve_justify(value: str) -> str:
    return "flex-start" if value == "normal" else value


def _resolve_items(value: str) -> str:
    return "stretch" if value == "normal" else value


def _resolve_content(value: str) -> str:
    return "stretch" if value == "normal" else value


def _resolve_self(value: str, items_align: str) -> str:
    if value == "auto":
        return items_align
    if value == "normal":
        return "stretch"
    return value


def _fixed_margin(automatic: bool, value: float) -> float:
    return 0.0 if automatic else value


def _clamp(value: float, low: float, high: float | None) -> float:
    if high is not None and value > high:
        value = high
    if value < low:
        value = low
    return value


def _floor_zero(value: float) -> float:
    return 0.0 if value < 0 else value


def _ident(value: object, line: int, index: int) -> str:
    if not isinstance(value, str) or value == "":
        raise _Invalid(f"line {line} item {index} id is invalid")
    return value


def _keyword(value: object, allowed: frozenset[str], name: str) -> str:
    if not isinstance(value, str):
        raise _Invalid(f"{name} is invalid")
    token = " ".join(value.strip().lower().split())
    if token not in allowed:
        raise _Invalid(f"{name} is invalid")
    return token


def _length(value: object, *, allow_negative: bool, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _Invalid(f"{name} is invalid")
    number = float(value)
    if number != number or number in {float("inf"), float("-inf")}:
        raise _Invalid(f"{name} is invalid")
    if number < 0 and not allow_negative:
        raise _Invalid(f"{name} cannot be negative")
    return number


def _number(value: float) -> int | float:
    nearest = round(value)
    if abs(value - nearest) <= _EPS:
        return int(nearest)
    return value


def _invalid(reason: str) -> dict[str, object]:
    return {
        "outcome": "invalid",
        "reason": reason,
        "container_main": None,
        "container_cross": None,
        "justify_content": None,
        "align_items": None,
        "align_content": None,
        "wrap": None,
        "main_gap": None,
        "cross_gap": None,
        "lines": None,
    }
