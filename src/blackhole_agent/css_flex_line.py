"""Used main sizes on one definite flex line.

CSS Flexbox §9.7 resolves flexible lengths after the flex base and the
maximum are known. A numeric minimum is that floor. ``auto`` asks §4.5 for
the content-based automatic minimum and then uses that floor. An omitted
minimum stays 0, so an explicit zero still shrinks below the content size.
This does not compute a content-based flex base or wrapping. Cross-axis
placement is ``place_flex_alignment``.

A main-axis gap is included in the hypothetical sum and in free space, as a
fixed length between items. Main-axis margins are included in the outer size
and do not flex. Shrink weights use the inner base. Flex factors that sum to
less than one absorb only that fraction of the original free space. When a
minimum and a maximum disagree, the minimum wins, matching the CSS used-value
rule that a size raised to the minimum may exceed the maximum.
"""

from __future__ import annotations

from blackhole_agent.css_flex_minimum import automatic_flex_minimum

_NONE = "none"
_AUTO = "auto"


class _Invalid(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def resolve_flex_line(
    container: object,
    items: object,
    *,
    gap: object = 0,
) -> dict[str, object]:
    """Resolve the inner used main size of each item on one flex line.

    ``container`` is the inner main size. Each item is a mapping with
    ``base`` (inner flex base, which may be negative), ``grow`` (default 0),
    ``shrink`` (default 1), ``minimum`` (default 0; a negative value computes
    to 0; ``auto`` uses the content-based floor), ``maximum`` (default
    ``none``; a negative value computes to 0), and ``margin`` (default 0,
    the sum of the two main-axis margins, which may be negative). An ``auto``
    minimum also reads ``content``, ``specified``, ``ratio``, ``cross``,
    ``cross_minimum``, ``cross_maximum``, ``replaced``, and ``scrollable``.
    ``gap`` is the fixed main-axis gap between items.
    """

    try:
        inner = _length(container, allow_negative=False, name="container")
        gutter = _length(gap, allow_negative=False, name="gap")
        parsed = _items(items)
    except _Invalid as exc:
        return _invalid(exc.reason)

    sizes = _resolve(inner, parsed, gutter)
    return {
        "outcome": "resolved",
        "main_sizes": [_number(size) for size in sizes],
        "container": _number(inner),
        "gap": _number(gutter),
    }


def _invalid(reason: str) -> dict[str, object]:
    return {"outcome": "invalid", "reason": reason, "main_sizes": None, "container": None, "gap": None}


def _items(value: object) -> list[dict[str, float | None]]:
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise _Invalid("items must be a list of flex items")
    parsed: list[dict[str, float | None]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise _Invalid(f"item {index} must be a mapping")
        maximum = item.get("maximum", _NONE)
        maximum_floor = (
            None
            if _is_none(maximum)
            else _floor_zero(_length(maximum, allow_negative=True, name=f"item {index} maximum"))
        )
        parsed.append(
            {
                "base": _length(item.get("base"), allow_negative=True, name=f"item {index} base"),
                "grow": _factor(item.get("grow", 0), f"item {index} grow"),
                "shrink": _factor(item.get("shrink", 1), f"item {index} shrink"),
                "minimum": _minimum(item, index, maximum_floor),
                "maximum": maximum_floor,
                "margin": _length(item.get("margin", 0), allow_negative=True, name=f"item {index} margin"),
            }
        )
    return parsed


def _is_none(value: object) -> bool:
    if value is None:
        return True
    if not isinstance(value, str):
        return False
    return value.strip().lower() == _NONE


def _length(value: object, *, allow_negative: bool, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _Invalid(f"{name} is invalid")
    number = float(value)
    if number != number or number in {float("inf"), float("-inf")}:
        raise _Invalid(f"{name} is invalid")
    if number < 0 and not allow_negative:
        raise _Invalid(f"{name} cannot be negative")
    return number


def _factor(value: object, name: str) -> float:
    number = _length(value, allow_negative=False, name=name)
    return number


def _floor_zero(value: float) -> float:
    return 0.0 if value < 0 else value


def _is_auto(value: object) -> bool:
    return isinstance(value, str) and " ".join(value.strip().lower().split()) == _AUTO


def _minimum(item: dict[str, object], index: int, maximum: float | None) -> float:
    raw = item.get("minimum", 0)
    if not _is_auto(raw):
        return _floor_zero(_length(raw, allow_negative=True, name=f"item {index} minimum"))
    result = automatic_flex_minimum(
        item.get("content"),
        specified=item.get("specified", _AUTO),
        maximum=_NONE if maximum is None else maximum,
        ratio=item.get("ratio", _NONE),
        cross=item.get("cross", _AUTO),
        cross_minimum=item.get("cross_minimum", _AUTO),
        cross_maximum=item.get("cross_maximum", _NONE),
        replaced=item.get("replaced", False),
        scrollable=item.get("scrollable", False),
    )
    floor = result.get("minimum")
    if result.get("outcome") != "definite" or isinstance(floor, bool) or not isinstance(floor, (int, float)):
        reason = result.get("reason")
        raise _Invalid(str(reason or f"item {index} minimum is invalid"))
    return float(floor)


def _clamp(size: float, item: dict[str, float | None]) -> float:
    maximum = item["maximum"]
    if isinstance(maximum, float) and size > maximum:
        size = maximum
    minimum = item["minimum"]
    if isinstance(minimum, float) and size < minimum:
        size = minimum
    if size < 0:
        size = 0.0
    return size


def _hypothetical(item: dict[str, float | None]) -> float:
    base = item["base"]
    assert isinstance(base, float)
    return _clamp(base, item)


def _outer(inner: float, item: dict[str, float | None]) -> float:
    margin = item["margin"]
    assert isinstance(margin, float)
    return inner + margin


def _gap_span(count: int, gap: float) -> float:
    if count <= 1:
        return 0.0
    return gap * (count - 1)


def _resolve(container: float, items: list[dict[str, float | None]], gap: float) -> list[float]:
    for item in items:
        item["hypothetical"] = _hypothetical(item)
        item["target"] = item["base"]
        item["frozen"] = False

    hypothetical_sum = _gap_span(len(items), gap)
    for item in items:
        hypothetical = item["hypothetical"]
        assert isinstance(hypothetical, float)
        hypothetical_sum += _outer(hypothetical, item)
    use_grow = hypothetical_sum < container

    for item in items:
        base = item["base"]
        hypothetical = item["hypothetical"]
        assert isinstance(base, float) and isinstance(hypothetical, float)
        factor = item["grow"] if use_grow else item["shrink"]
        assert isinstance(factor, float)
        inflexible = factor == 0 or (use_grow and base > hypothetical) or (not use_grow and base < hypothetical)
        if inflexible:
            item["frozen"] = True
            item["target"] = hypothetical

    initial_free = container - _occupied(items, gap)
    guard = len(items) + 1
    while guard:
        guard -= 1
        pending = [item for item in items if not item["frozen"]]
        if not pending:
            break
        remaining = container - _occupied(items, gap)
        factor_sum = 0.0
        for item in pending:
            factor = item["grow"] if use_grow else item["shrink"]
            assert isinstance(factor, float)
            factor_sum += factor
        if factor_sum < 1:
            scaled_initial = initial_free * factor_sum
            if abs(scaled_initial) < abs(remaining):
                remaining = scaled_initial
        if use_grow:
            _distribute_grow(pending, remaining, factor_sum)
        else:
            _distribute_shrink(pending, remaining)
        violation = _clamp_pending(pending)
        if abs(violation) <= 1e-9:
            for item in pending:
                item["frozen"] = True
        elif violation > 0:
            _freeze_marked(pending, "min")
        else:
            _freeze_marked(pending, "max")
    return [float(item["target"]) for item in items]


def _occupied(items: list[dict[str, float | None]], gap: float) -> float:
    total = _gap_span(len(items), gap)
    for item in items:
        if item["frozen"]:
            inner = item["target"]
        else:
            inner = item["base"]
        assert isinstance(inner, float)
        total += _outer(inner, item)
    return total


def _distribute_grow(pending: list[dict[str, float | None]], remaining: float, factor_sum: float) -> None:
    for item in pending:
        base = item["base"]
        grow = item["grow"]
        assert isinstance(base, float) and isinstance(grow, float)
        share = 0.0 if factor_sum == 0 else remaining * (grow / factor_sum)
        item["target"] = base + share


def _distribute_shrink(pending: list[dict[str, float | None]], remaining: float) -> None:
    weights: list[float] = []
    for item in pending:
        base = item["base"]
        shrink = item["shrink"]
        assert isinstance(base, float) and isinstance(shrink, float)
        weights.append(shrink * base)
    weight_sum = sum(weights)
    for item, weight in zip(pending, weights):
        base = item["base"]
        assert isinstance(base, float)
        share = 0.0 if weight_sum == 0 else abs(remaining) * (weight / weight_sum)
        item["target"] = base - share


def _clamp_pending(pending: list[dict[str, float | None]]) -> float:
    total = 0.0
    for item in pending:
        unclamped = item["target"]
        assert isinstance(unclamped, float)
        clamped = _clamp(unclamped, item)
        item["target"] = clamped
        delta = clamped - unclamped
        total += delta
        if delta < -1e-9:
            item["violation"] = "max"
        elif delta > 1e-9:
            item["violation"] = "min"
        else:
            item["violation"] = ""
    return total


def _freeze_marked(pending: list[dict[str, float | None]], kind: str) -> None:
    marked = [item for item in pending if item.get("violation") == kind]
    if not marked:
        for item in pending:
            item["frozen"] = True
        return
    for item in marked:
        item["frozen"] = True


def _number(value: float) -> int | float:
    nearest = round(value)
    if abs(value - nearest) <= 1e-9:
        return int(nearest)
    return value
