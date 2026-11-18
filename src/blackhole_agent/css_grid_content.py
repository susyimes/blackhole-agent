"""Used sizes of CSS grid tracks from item content contributions.

CSS Grid §11.4–§11.8 sizes each track from a min and a max sizing function.
A fixed length is that length on both sides. ``1fr`` is ``minmax(auto, 1fr)``.
``fit-content()`` is an auto minimum with a max-content maximum clamped by
its argument. ``auto`` and ``fit-content()`` maxima follow max-content except
where stretch and the fit-content clamp say otherwise.

A non-spanning item sets the base and growth limit of its own track. A
spanning item then adds only the extra that the tracks it crosses cannot
already hold. That extra prefers the intrinsic tracks in the span. The CSS
grid example of two ``minmax(min-content, max-content)`` tracks, a 10px item
in the first and a spanning item of min-content 30 and max-content 100, ends
at growth limits 10 and 90: the first track stays on its item, and the second
absorbs the rest because the growth limit just assigned from min-content does
not cap the following max-content pass.

An indefinite min-content container does not distribute free space, so the
bases stand. An indefinite max-content container, and the keyword ``auto``,
grows every base to its growth limit. A definite container does that up to
the growth limits, flexible tracks then take a fr share of the available
size, and stretch gives whatever is still free only to automatic maxima.
Baseline shims are already included in the contributions the caller passes.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

_EPS = 1e-9
_INF = float("inf")
_KEYWORDS = frozenset({"min-content", "max-content", "auto"})
_INTRINSIC_MAX = frozenset({"min-content", "max-content", "auto", "fit-content"})
_MAX_CONTENT_MAX = frozenset({"max-content", "auto", "fit-content"})


class _Invalid(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass
class _Track:
    min_kind: str
    min_fixed: float
    max_kind: str
    max_fixed: float
    base: float = 0.0
    growth: float = 0.0
    infinitely_growable: bool = False


@dataclass(frozen=True)
class _Item:
    start: int
    span: int
    min_content: float
    max_content: float
    minimum: float


def size_content_grid_tracks(
    available: object,
    tracks: object,
    items: object,
    *,
    gap: object = 0,
    stretch: object = True,
) -> dict[str, object]:
    """Return the used size of each track on one axis.

    ``available`` is a length, ``min-content``, ``max-content``, or ``auto``.
    ``auto`` is the max-content constraint. Each track is ``{"fixed": length}``,
    ``{"breadth": keyword}``, ``{"minimum": breadth, "maximum": breadth}``,
    ``{"flex": factor}`` with an optional ``minimum``, or
    ``{"fit_content": length}``. A breadth is a length or ``min-content``,
    ``max-content``, or ``auto``. Each item maps ``start``, ``span``,
    ``min_content``, ``max_content``, and an optional ``minimum`` contribution.
    ``gap`` is the fixed gutter. ``stretch`` is true when the axis distributes
    like ``normal`` or ``stretch``.
    """

    try:
        constraint, space = _available(available)
        gutter = _length(gap, allow_negative=False, name="gap")
        parsed = _tracks(tracks)
        spanned = _items(items, len(parsed))
        if not isinstance(stretch, bool):
            raise _Invalid("stretch is invalid")
    except _Invalid as exc:
        return _invalid(exc.reason)

    _init(parsed)
    _non_spanning(parsed, spanned, constraint)
    _spanning(parsed, spanned, constraint, gutter, flex_only=False)
    _spanning(parsed, spanned, constraint, gutter, flex_only=True)
    for track in parsed:
        if math.isinf(track.growth):
            track.growth = track.base
        if track.growth < track.base:
            track.growth = track.base
    _maximize(parsed, space, constraint, gutter)
    _expand_flex(parsed, spanned, space, constraint, gutter)
    if stretch and constraint == "definite" and space is not None:
        _stretch(parsed, space, gutter)
    sizes = [_number(track.base) for track in parsed]
    container = _number(sum(float(size) for size in sizes) + _gap_span(len(parsed), gutter))
    return {
        "outcome": "resolved",
        "track_sizes": sizes,
        "container": container,
        "available": _number(space) if space is not None else constraint,
        "gap": _number(gutter),
    }


def _invalid(reason: str) -> dict[str, object]:
    return {
        "outcome": "invalid",
        "reason": reason,
        "track_sizes": None,
        "container": None,
        "available": None,
        "gap": None,
    }


def _available(value: object) -> tuple[str, float | None]:
    if isinstance(value, str):
        token = value.strip().lower()
        if token == "auto":
            token = "max-content"
        if token not in {"min-content", "max-content"}:
            raise _Invalid("available is invalid")
        return token, None
    return "definite", _length(value, allow_negative=False, name="available")


def _tracks(value: object) -> list[_Track]:
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise _Invalid("tracks must be a list")
    if not value:
        raise _Invalid("tracks must not be empty")
    return [_track(raw, index) for index, raw in enumerate(value)]


def _track(raw: object, index: int) -> _Track:
    if not isinstance(raw, dict):
        raise _Invalid(f"track {index} must be a mapping")
    keys = set(raw)
    name = f"track {index}"
    if keys == {"fixed"}:
        size = _length(raw["fixed"], allow_negative=False, name=f"{name} fixed")
        return _Track("fixed", size, "fixed", size)
    if keys == {"breadth"}:
        kind, size = _breadth(raw["breadth"], f"{name} breadth")
        if kind == "fixed":
            return _Track("fixed", size, "fixed", size)
        return _Track(kind, 0.0, kind, 0.0)
    if keys == {"fit_content"}:
        limit = _length(raw["fit_content"], allow_negative=False, name=f"{name} fit_content")
        return _Track("auto", 0.0, "fit-content", limit)
    if "flex" in keys:
        unknown = keys - {"flex", "minimum"}
        if unknown or "maximum" in keys:
            raise _Invalid(f"{name} mixes a flex factor with another sizing field")
        factor = _length(raw["flex"], allow_negative=False, name=f"{name} flex")
        if "minimum" in keys:
            kind, size = _breadth(raw["minimum"], f"{name} minimum")
        else:
            kind, size = "auto", 0.0
        return _Track(kind, size, "flex", factor)
    if keys == {"minimum", "maximum"}:
        min_kind, min_size = _breadth(raw["minimum"], f"{name} minimum")
        max_kind, max_size = _breadth(raw["maximum"], f"{name} maximum")
        if min_kind == "fixed" and max_kind == "fixed" and max_size < min_size:
            max_size = min_size
        return _Track(min_kind, min_size, max_kind, max_size)
    raise _Invalid(f"{name} has an unknown sizing function")


def _items(value: object, count: int) -> list[_Item]:
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise _Invalid("items must be a list")
    parsed: list[_Item] = []
    for index, raw in enumerate(value):
        if not isinstance(raw, dict):
            raise _Invalid(f"item {index} must be a mapping")
        if set(raw) - {"start", "span", "min_content", "max_content", "minimum"}:
            raise _Invalid(f"item {index} has an unknown field")
        if "min_content" not in raw or "max_content" not in raw:
            raise _Invalid(f"item {index} needs min_content and max_content")
        start = _count(raw.get("start", 0), f"item {index} start")
        span = _count(raw.get("span", 1), f"item {index} span")
        if span < 1:
            raise _Invalid(f"item {index} span must be positive")
        if start < 0 or start + span > count:
            raise _Invalid(f"item {index} span is outside the tracks")
        min_content = _length(raw["min_content"], allow_negative=False, name=f"item {index} min_content")
        max_content = _length(raw["max_content"], allow_negative=False, name=f"item {index} max_content")
        if max_content + _EPS < min_content:
            raise _Invalid(f"item {index} max_content is below min_content")
        if "minimum" in raw:
            minimum = _length(raw["minimum"], allow_negative=False, name=f"item {index} minimum")
        else:
            minimum = min_content
        if min_content + _EPS < minimum:
            raise _Invalid(f"item {index} minimum exceeds min_content")
        parsed.append(_Item(start, span, min_content, max_content, minimum))
    return parsed


def _init(tracks: list[_Track]) -> None:
    for track in tracks:
        track.base = track.min_fixed if track.min_kind == "fixed" else 0.0
        track.growth = track.max_fixed if track.max_kind == "fixed" else _INF
        if track.growth < track.base:
            track.growth = track.base
        track.infinitely_growable = False


def _non_spanning(tracks: list[_Track], items: list[_Item], constraint: str) -> None:
    for index, track in enumerate(tracks):
        if track.max_kind == "flex":
            continue
        if track.min_kind == "fixed" and track.max_kind not in _INTRINSIC_MAX:
            continue
        local = [item for item in items if item.span == 1 and item.start == index]
        if not local:
            continue
        if track.min_kind == "min-content":
            track.base = max(track.base, max(item.min_content for item in local))
        elif track.min_kind == "max-content":
            track.base = max(track.base, max(item.max_content for item in local))
        elif track.min_kind == "auto":
            if constraint in {"min-content", "max-content"}:
                track.base = max(track.base, max(_limited(item, tracks, item.min_content) for item in local))
            else:
                track.base = max(track.base, max(item.minimum for item in local))
        if track.max_kind == "min-content":
            track.growth = max(item.min_content for item in local)
        elif track.max_kind in _MAX_CONTENT_MAX:
            growth = max(item.max_content for item in local)
            if track.max_kind == "fit-content":
                growth = min(growth, track.max_fixed)
            track.growth = growth
        if track.growth < track.base:
            track.growth = track.base


def _spanning(
    tracks: list[_Track],
    items: list[_Item],
    constraint: str,
    gap: float,
    *,
    flex_only: bool,
) -> None:
    if flex_only:
        batches = [[item for item in items if _spans_flex(tracks, item)]]
    else:
        batches = []
        if items:
            for span in range(2, max(item.span for item in items) + 1):
                batch = [
                    item
                    for item in items
                    if item.span == span and not _spans_flex(tracks, item)
                ]
                if batch:
                    batches.append(batch)
    for batch in batches:
        if not batch:
            continue
        for track in tracks:
            track.infinitely_growable = False
        _distribute(
            tracks,
            batch,
            gap,
            affect_base=True,
            predicate=lambda track: _intrinsic_min(track) and _flex_gate(track, flex_only),
            contribution=lambda item: _minimum_for(item, tracks, constraint),
            beyond="minimum",
            by_flex=flex_only,
        )
        _distribute(
            tracks,
            batch,
            gap,
            affect_base=True,
            predicate=lambda track: track.min_kind in {"min-content", "max-content"} and _flex_gate(track, flex_only),
            contribution=lambda item: item.min_content,
            beyond="min-content",
            by_flex=flex_only,
        )
        if constraint == "max-content":
            _distribute(
                tracks,
                batch,
                gap,
                affect_base=True,
                predicate=lambda track: track.min_kind in {"auto", "max-content"} and _flex_gate(track, flex_only),
                contribution=lambda item: _limited(item, tracks, item.max_content),
                beyond="max-content",
                by_flex=flex_only,
            )
        _distribute(
            tracks,
            batch,
            gap,
            affect_base=True,
            predicate=lambda track: track.min_kind == "max-content" and _flex_gate(track, flex_only),
            contribution=lambda item: item.max_content,
            beyond="max-content",
            by_flex=flex_only,
        )
        for track in tracks:
            if track.growth < track.base:
                track.growth = track.base
        _distribute(
            tracks,
            batch,
            gap,
            affect_base=False,
            predicate=lambda track: track.max_kind in _INTRINSIC_MAX and _flex_gate(track, flex_only),
            contribution=lambda item: item.min_content,
            beyond="min-content",
            by_flex=flex_only,
            mark_infinite=True,
        )
        _distribute(
            tracks,
            batch,
            gap,
            affect_base=False,
            predicate=lambda track: track.max_kind in _MAX_CONTENT_MAX and _flex_gate(track, flex_only),
            contribution=lambda item: item.max_content,
            beyond="max-content",
            by_flex=flex_only,
        )
        for track in tracks:
            track.infinitely_growable = False


def _distribute(
    tracks: list[_Track],
    items: list[_Item],
    gap: float,
    *,
    affect_base: bool,
    predicate,
    contribution,
    beyond: str,
    by_flex: bool,
    mark_infinite: bool = False,
) -> None:
    planned = [0.0] * len(tracks)
    affected_set: set[int] = set()
    touched: set[int] = set()
    for item in items:
        spanned = list(range(item.start, item.start + item.span))
        affected = [index for index in spanned if predicate(tracks[index])]
        affected_set.update(affected)
        if not spanned:
            continue
        occupied = sum(_size_for(tracks[index], affect_base) for index in spanned)
        space = item_contribution = contribution(item)
        space = max(0.0, item_contribution - occupied - _gap_span(item.span, gap))
        incurred = {index: 0.0 for index in spanned}
        space = _give(tracks, affected, space, incurred, affect_base, by_flex, beyond_limits=False)
        others = [index for index in spanned if index not in affected]
        if space > _EPS and others and affected:
            space = _give(tracks, others, space, incurred, affect_base, False, beyond_limits=False)
        if space > _EPS and affected:
            extra = _beyond_targets(tracks, affected, affect_base, beyond)
            if extra:
                space = _give(tracks, extra, space, incurred, affect_base, by_flex, beyond_limits=True)
        for index, amount in incurred.items():
            if amount > planned[index]:
                planned[index] = amount
            if amount > _EPS:
                touched.add(index)
    for index in affected_set | touched:
        track = tracks[index]
        if affect_base:
            track.base += planned[index]
            continue
        if math.isinf(track.growth):
            track.growth = track.base + planned[index]
            if mark_infinite and index in affected_set:
                track.infinitely_growable = True
        else:
            track.growth += planned[index]


def _give(
    tracks: list[_Track],
    indexes: list[int],
    space: float,
    incurred: dict[int, float],
    affect_base: bool,
    by_flex: bool,
    *,
    beyond_limits: bool,
) -> float:
    active = list(indexes)
    guard = len(indexes) + 2
    while space > _EPS and active and guard:
        guard -= 1
        if by_flex:
            factors = [tracks[index].max_fixed for index in active]
            shares = _flexible_shares(space, factors)
        else:
            share = space / len(active)
            shares = [share] * len(active)
        consumed = 0.0
        nxt: list[int] = []
        for index, share in zip(active, shares):
            room = _room(tracks[index], incurred[index], affect_base, beyond_limits)
            give = min(room, max(0.0, share))
            if math.isinf(give):
                give = max(0.0, share)
            incurred[index] += give
            consumed += give
            if room > share + _EPS:
                nxt.append(index)
        if consumed <= _EPS:
            return space
        space -= consumed
        active = nxt
    return max(0.0, space)


def _room(track: _Track, already: float, affect_base: bool, beyond_limits: bool) -> float:
    current = _size_for(track, affect_base) + already
    if beyond_limits:
        limit = track.max_fixed if track.max_kind == "fit-content" else _INF
    elif affect_base:
        limit = track.growth
        if track.max_kind == "fit-content":
            limit = track.max_fixed if math.isinf(limit) else min(limit, track.max_fixed)
    elif math.isinf(track.growth) or track.infinitely_growable:
        limit = track.max_fixed if track.max_kind == "fit-content" else _INF
    else:
        limit = track.growth
    if math.isinf(limit):
        return _INF
    return max(0.0, limit - current)


def _beyond_targets(
    tracks: list[_Track],
    affected: list[int],
    affect_base: bool,
    kind: str,
) -> list[int]:
    if not affect_base:
        return [index for index in affected if tracks[index].max_kind in _INTRINSIC_MAX]
    if kind == "max-content":
        chosen = [index for index in affected if tracks[index].max_kind in _MAX_CONTENT_MAX]
    else:
        chosen = [index for index in affected if tracks[index].max_kind in _INTRINSIC_MAX]
    return chosen or list(affected)


def _maximize(tracks: list[_Track], space: float | None, constraint: str, gap: float) -> None:
    if constraint == "min-content":
        return
    if constraint == "max-content":
        for track in tracks:
            if track.growth > track.base:
                track.base = track.growth
        return
    assert space is not None
    free = space - sum(track.base for track in tracks) - _gap_span(len(tracks), gap)
    guard = len(tracks) + 1
    while free > _EPS and guard:
        guard -= 1
        growable = [track for track in tracks if track.growth > track.base + _EPS]
        if not growable:
            return
        share = free / len(growable)
        consumed = 0.0
        for track in growable:
            added = min(track.growth - track.base, share)
            track.base += added
            consumed += added
        free -= consumed
        if consumed <= _EPS:
            return


def _expand_flex(
    tracks: list[_Track],
    items: list[_Item],
    space: float | None,
    constraint: str,
    gap: float,
) -> None:
    flexible = [index for index, track in enumerate(tracks) if track.max_kind == "flex"]
    if not flexible:
        return
    if constraint == "min-content":
        fraction = 0.0
    elif constraint == "definite":
        assert space is not None
        free = space - sum(track.base for track in tracks) - _gap_span(len(tracks), gap)
        fraction = 0.0 if free <= _EPS else _fr_size(tracks, space, gap, None)
    else:
        fraction = 0.0
        for index in flexible:
            factor = tracks[index].max_fixed
            base = tracks[index].base
            portion = base / factor if factor > 1 else base
            if portion > fraction:
                fraction = portion
        for item in items:
            spanned = list(range(item.start, item.start + item.span))
            if any(tracks[index].max_kind == "flex" for index in spanned):
                portion = _fr_size(tracks, item.max_content, gap, spanned)
                if portion > fraction:
                    fraction = portion
    for index in flexible:
        product = fraction * tracks[index].max_fixed
        if product > tracks[index].base + _EPS:
            tracks[index].base = product


def _fr_size(tracks: list[_Track], space: float, gap: float, indexes: list[int] | None) -> float:
    chosen = list(range(len(tracks)) if indexes is None else indexes)
    frozen: set[int] = set()
    guard = len(chosen) + 1
    while guard:
        guard -= 1
        flexible = [index for index in chosen if tracks[index].max_kind == "flex" and index not in frozen]
        if not flexible:
            return 0.0
        occupied = _gap_span(len(chosen), gap)
        occupied += sum(tracks[index].base for index in chosen if index not in flexible)
        flex_sum = sum(tracks[index].max_fixed for index in flexible)
        if flex_sum < 1:
            flex_sum = 1.0
        hypothetical = (space - occupied) / flex_sum
        newly = [
            index
            for index in flexible
            if hypothetical * tracks[index].max_fixed < tracks[index].base - _EPS
        ]
        if not newly:
            return max(0.0, hypothetical)
        frozen.update(newly)
    return 0.0


def _stretch(tracks: list[_Track], space: float, gap: float) -> None:
    autos = [track for track in tracks if track.max_kind == "auto"]
    if not autos:
        return
    free = space - sum(track.base for track in tracks) - _gap_span(len(tracks), gap)
    if free <= _EPS:
        return
    share = free / len(autos)
    for track in autos:
        track.base += share


def _limited(item: _Item, tracks: list[_Track], value: float) -> float:
    spanned = tracks[item.start : item.start + item.span]
    cap = _cap(spanned)
    capped = value if cap is None else min(value, cap)
    return max(capped, item.minimum)


def _cap(spanned: list[_Track]) -> float | None:
    if not spanned:
        return None
    total = 0.0
    for track in spanned:
        if track.max_kind == "fixed" or track.max_kind == "fit-content":
            total += track.max_fixed
        else:
            return None
    return total


def _minimum_for(item: _Item, tracks: list[_Track], constraint: str) -> float:
    if constraint in {"min-content", "max-content"}:
        return _limited(item, tracks, item.min_content)
    return item.minimum


def _spans_flex(tracks: list[_Track], item: _Item) -> bool:
    return any(tracks[index].max_kind == "flex" for index in range(item.start, item.start + item.span))


def _intrinsic_min(track: _Track) -> bool:
    return track.min_kind != "fixed"


def _flex_gate(track: _Track, flex_only: bool) -> bool:
    return (track.max_kind == "flex") is flex_only


def _size_for(track: _Track, affect_base: bool) -> float:
    if affect_base or math.isinf(track.growth):
        return track.base
    return track.growth


def _flexible_shares(space: float, factors: list[float]) -> list[float]:
    count = len(factors)
    if count == 0 or space <= 0:
        return [0.0] * count
    flex_sum = sum(factors)
    if flex_sum >= 1:
        return [space * (factor / flex_sum) for factor in factors]
    proportional = space * flex_sum
    if flex_sum == 0:
        by_ratio = [0.0] * count
    else:
        by_ratio = [proportional * (factor / flex_sum) for factor in factors]
    equal = (space - proportional) / count
    return [part + equal for part in by_ratio]


def _breadth(value: object, name: str) -> tuple[str, float]:
    if isinstance(value, str):
        if value not in _KEYWORDS:
            raise _Invalid(f"{name} is invalid")
        return value, 0.0
    return "fixed", _length(value, allow_negative=False, name=name)


def _gap_span(count: int, gap: float) -> float:
    if count <= 1:
        return 0.0
    return gap * (count - 1)


def _count(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise _Invalid(f"{name} is invalid")
    return value


def _length(value: object, *, allow_negative: bool, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _Invalid(f"{name} is invalid")
    number = float(value)
    if number != number or number in {_INF, float("-inf")}:
        raise _Invalid(f"{name} is invalid")
    if number < 0 and not allow_negative:
        raise _Invalid(f"{name} cannot be negative")
    return number


def _number(value: float) -> int | float:
    nearest = round(value)
    if abs(value - nearest) <= _EPS:
        return int(nearest)
    return value
