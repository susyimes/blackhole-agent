"""Pack already-sized grid tracks inside a definite content box.

CSS Box Alignment distributes free space after track sizing. The fixed gap
stays between tracks. ``end`` and ``center`` shift the whole list, including
when the tracks overflow the container. ``space-between``, ``space-around``,
and ``space-evenly`` add to every gutter. ``space-between`` falls back to
``start`` for one track or a negative leftover. ``space-around`` and
``space-evenly`` fall back to ``center`` in those same cases.

``normal`` and ``stretch`` map to ``start`` here. Automatic columns and
flexible rows already absorbed their growth during track sizing, and a
remainder stays at the start. ``flex-start`` is ``start`` and ``flex-end``
is ``end``. A share that is not an integer pixel is rejected.
"""

from __future__ import annotations

_START = frozenset({"normal", "stretch", "start", "flex-start"})
_END = frozenset({"end", "flex-end"})
_EXACT = frozenset({"center", "space-between", "space-around", "space-evenly"})
CONTENT_KEYWORDS = _START | _END | _EXACT
_PACK = frozenset({"start", "end", "center", "space-between", "space-around", "space-evenly"})


class _Invalid(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def grid_content_stretches(keyword: object) -> bool:
    """True when automatic columns should absorb leftover inline space."""

    return keyword in {"normal", "stretch"}


def pack_grid_content(
    container: object,
    sizes: object,
    gap: object,
    keyword: object,
) -> dict[str, object]:
    """Return the leading offset and the extra length added to each gutter."""

    try:
        space = _length(container, "container")
        gutter = _length(gap, "gap")
        tracks = _sizes(sizes)
        mode = _mode(keyword)
        if not tracks:
            return _packed(0, 0)
        free = space - sum(tracks) - gutter * (len(tracks) - 1)
        used = _fallback(mode, free, len(tracks))
        leading, extra = _shares(used, free, len(tracks))
    except _Invalid as exc:
        return {"outcome": "invalid", "reason": exc.reason, "leading": None, "extra": None}
    return _packed(leading, extra)


def _packed(leading: int, extra: int) -> dict[str, object]:
    return {"outcome": "packed", "reason": None, "leading": leading, "extra": extra}


def _mode(keyword: object) -> str:
    if keyword in _START:
        return "start"
    if keyword in _END:
        return "end"
    if keyword in _EXACT:
        return str(keyword)
    raise _Invalid("grid content alignment is invalid")


def _fallback(mode: str, free: int, count: int) -> str:
    if mode not in _PACK:
        raise _Invalid("grid content alignment is invalid")
    if free < 0 or count < 2:
        if mode == "space-between":
            return "start"
        if mode in {"space-around", "space-evenly"}:
            return "center"
    return mode


def _shares(mode: str, free: int, count: int) -> tuple[int, int]:
    if mode == "end":
        return free, 0
    if mode == "center":
        return _div(free, 2), 0
    if mode == "space-between":
        return 0, _div(free, count - 1)
    if mode == "space-around":
        return _div(free, 2 * count), _div(free, count)
    if mode == "space-evenly":
        share = _div(free, count + 1)
        return share, share
    return 0, 0


def _div(free: int, denom: int) -> int:
    if denom <= 0 or free % denom != 0:
        raise _Invalid("grid content alignment is not integral")
    return free // denom


def _length(value: object, name: str) -> int:
    if type(value) is not int or value < 0:
        raise _Invalid(f"{name} is invalid")
    return value


def _sizes(value: object) -> list[int]:
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise _Invalid("tracks are invalid")
    sizes: list[int] = []
    for index, raw in enumerate(value):
        if type(raw) is not int or raw < 0:
            raise _Invalid(f"track {index} is invalid")
        sizes.append(raw)
    return sizes
