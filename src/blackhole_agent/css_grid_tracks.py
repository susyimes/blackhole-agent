"""Used sizes of one definite CSS grid axis.

CSS Grid §12 sizes fixed tracks, minmax tracks, and fr tracks after gutters
are reserved. A minmax track grows to its maximum before flexible tracks take
leftover space. An fr sum below one leaves the rest empty. A base that already
exceeds its fr share is held and the leftover is solved again. An item that
crosses a flexible track raises those bases first: by fr ratios when the
crossed factors sum to at least one, and with the remainder shared equally
when they sum to less. The fixed gap inside a span counts toward that item.

This does not measure content, stretch auto tracks, or size an indefinite
container. Minimums are definite lengths supplied by the caller.
``size_content_grid_tracks`` is the pass that starts from content.
"""

from __future__ import annotations

_INF = float("inf")


class _Invalid(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def size_grid_tracks(
    available: object,
    tracks: object,
    items: object,
    *,
    gap: object = 0,
) -> dict[str, object]:
    """Return the used size of each track on one definite axis.

    ``available`` is the inner size. Each track is a fixed length
    (``fixed``), a fixed range (``minimum`` and ``maximum``), or a flexible
    track (``flex``, with ``minimum`` defaulting to 0). A negative minimum
    or maximum computes to 0, and a maximum below its minimum is raised to
    that minimum. ``items`` are mappings with ``start``, ``span``, and
    ``minimum``. ``gap`` is the fixed gutter between adjacent tracks.
    """

    try:
        space = _length(available, allow_negative=False, name="available")
        gutter = _length(gap, allow_negative=False, name="gap")
        parsed = _tracks(tracks)
        spanned = _items(items, len(parsed))
    except _Invalid as exc:
        return _invalid(exc.reason)

    _accommodate(parsed, spanned, gutter)
    for track in parsed:
        if track["flex"] is not None:
            track["growth"] = track["base"]
    _maximize(parsed, _free(space, parsed, gutter))
    _expand(parsed, space, gutter)
    return {
        "outcome": "resolved",
        "track_sizes": [_number(track["base"]) for track in parsed],
        "available": _number(space),
        "gap": _number(gutter),
    }


def _invalid(reason: str) -> dict[str, object]:
    return {"outcome": "invalid", "reason": reason, "track_sizes": None, "available": None, "gap": None}


def _tracks(value: object) -> list[dict[str, float | None]]:
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise _Invalid("tracks must be a list")
    return [_track(raw, index) for index, raw in enumerate(value)]


def _track(raw: object, index: int) -> dict[str, float | None]:
    if not isinstance(raw, dict):
        raise _Invalid(f"track {index} must be a mapping")
    unknown = set(raw) - {"fixed", "flex", "minimum", "maximum"}
    if unknown:
        raise _Invalid(f"track {index} has an unknown field")
    has_fixed = "fixed" in raw
    has_flex = "flex" in raw
    has_min = "minimum" in raw
    has_max = "maximum" in raw
    if has_fixed and (has_flex or has_min or has_max):
        raise _Invalid(f"track {index} mixes a fixed size with another sizing field")
    if has_flex and has_max:
        raise _Invalid(f"track {index} mixes a flex factor with a fixed maximum")
    if has_fixed:
        size = _length(raw["fixed"], allow_negative=False, name=f"track {index} fixed")
        return {"base": size, "growth": size, "flex": None}
    if has_flex:
        factor = _length(raw["flex"], allow_negative=False, name=f"track {index} flex")
        minimum = _minimum(raw["minimum"], f"track {index} minimum") if has_min else 0.0
        return {"base": minimum, "growth": _INF, "flex": factor}
    if has_min and has_max:
        minimum = _minimum(raw["minimum"], f"track {index} minimum")
        maximum = _minimum(raw["maximum"], f"track {index} maximum")
        if maximum < minimum:
            maximum = minimum
        return {"base": minimum, "growth": maximum, "flex": None}
    raise _Invalid(f"track {index} needs a fixed size, a flex factor, or a minimum and maximum")


def _items(value: object, count: int) -> list[dict[str, float]]:
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise _Invalid("items must be a list")
    parsed: list[dict[str, float]] = []
    for index, raw in enumerate(value):
        if not isinstance(raw, dict):
            raise _Invalid(f"item {index} must be a mapping")
        if set(raw) - {"start", "span", "minimum"}:
            raise _Invalid(f"item {index} has an unknown field")
        start = _count(raw.get("start", 0), f"item {index} start")
        span = _count(raw.get("span", 1), f"item {index} span")
        if span < 1:
            raise _Invalid(f"item {index} span must be positive")
        if start < 0 or start + span > count:
            raise _Invalid(f"item {index} span is outside the tracks")
        minimum = _minimum(raw.get("minimum", 0), f"item {index} minimum")
        parsed.append({"start": float(start), "span": float(span), "minimum": minimum})
    return parsed


def _accommodate(tracks: list[dict[str, float | None]], items: list[dict[str, float]], gap: float) -> None:
    planned = [0.0] * len(tracks)
    for item in items:
        start = int(item["start"])
        span = int(item["span"])
        covered = range(start, start + span)
        flexible = [index for index in covered if tracks[index]["flex"] is not None]
        if not flexible:
            continue
        occupied = sum(_base(tracks[index]) for index in covered) + _gap_span(span, gap)
        space = item["minimum"] - occupied
        if space <= 0:
            continue
        factors = [_factor(tracks[index]) for index in flexible]
        for index, share in zip(flexible, _flexible_shares(space, factors)):
            if share > planned[index]:
                planned[index] = share
    for index, extra in enumerate(planned):
        tracks[index]["base"] = _base(tracks[index]) + extra


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


def _maximize(tracks: list[dict[str, float | None]], free: float) -> None:
    guard = len(tracks) + 1
    while free > 1e-9 and guard:
        guard -= 1
        growable = [track for track in tracks if _growth(track) > _base(track) + 1e-9]
        if not growable:
            return
        share = free / len(growable)
        consumed = 0.0
        for track in growable:
            added = min(_growth(track) - _base(track), share)
            track["base"] = _base(track) + added
            consumed += added
        free -= consumed
        if consumed <= 1e-9:
            return


def _expand(tracks: list[dict[str, float | None]], available: float, gap: float) -> None:
    if _free(available, tracks, gap) <= 1e-9:
        return
    fraction = _fr_size(tracks, gap, available)
    for track in tracks:
        flex = track["flex"]
        if not isinstance(flex, float):
            continue
        product = fraction * flex
        if product > _base(track) + 1e-9:
            track["base"] = product


def _fr_size(tracks: list[dict[str, float | None]], gap: float, space: float) -> float:
    frozen: set[int] = set()
    while True:
        flexible = [index for index, track in enumerate(tracks) if track["flex"] is not None and index not in frozen]
        occupied = _gap_span(len(tracks), gap)
        for index, track in enumerate(tracks):
            if index not in flexible:
                occupied += _base(track)
        flex_sum = sum(_factor(tracks[index]) for index in flexible)
        if flex_sum < 1:
            flex_sum = 1.0
        hypothetical = (space - occupied) / flex_sum
        newly = [
            index
            for index in flexible
            if hypothetical * _factor(tracks[index]) < _base(tracks[index]) - 1e-9
        ]
        if not newly:
            return hypothetical
        frozen.update(newly)


def _free(available: float, tracks: list[dict[str, float | None]], gap: float) -> float:
    total = _gap_span(len(tracks), gap) + sum(_base(track) for track in tracks)
    remaining = available - total
    return 0.0 if remaining < 0 else remaining


def _gap_span(count: int, gap: float) -> float:
    if count <= 1:
        return 0.0
    return gap * (count - 1)


def _base(track: dict[str, float | None]) -> float:
    base = track["base"]
    assert isinstance(base, float)
    return base


def _growth(track: dict[str, float | None]) -> float:
    growth = track["growth"]
    assert isinstance(growth, float)
    return growth


def _factor(track: dict[str, float | None]) -> float:
    flex = track["flex"]
    assert isinstance(flex, float)
    return flex


def _minimum(value: object, name: str) -> float:
    return _floor_zero(_length(value, allow_negative=True, name=name))


def _count(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise _Invalid(f"{name} is invalid")
    return value


def _length(value: object, *, allow_negative: bool, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _Invalid(f"{name} is invalid")
    number = float(value)
    if number != number or number in {float("inf"), float("-inf")}:
        raise _Invalid(f"{name} is invalid")
    if number < 0 and not allow_negative:
        raise _Invalid(f"{name} cannot be negative")
    return number


def _floor_zero(value: float) -> float:
    return 0.0 if value < 0 else value


def _number(value: float) -> int | float:
    nearest = round(value)
    if abs(value - nearest) <= 1e-9:
        return int(nearest)
    return value
