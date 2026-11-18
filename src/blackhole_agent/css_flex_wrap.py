"""Collect definite flex items into flex lines, then resolve each line.

CSS Flexbox breaks lines on the hypothetical outer main size before free
space is distributed. The one-line resolver still sizes whatever list it is
given, so an item that should wrap was shrinking beside its neighbors.

``nowrap`` keeps one line. ``wrap`` starts a new line when the next outer
size, including one gap, does not fit. The first item on a line stays even
when it is wider than the container; later flexing does not pull the
following item back onto that line. ``wrap-reverse`` stacks the collected
lines from the cross-end and leaves each line's order alone.

Items are sorted by the integer ``order`` value, then by input order, before
any break. ``row-reverse`` and ``column-reverse`` move main-start to the
container's end edge. Each line is still listed from that main-start, and
the groups stay the same.

The caller supplies a definite inner main size and a definite flex base.
Automatic minimum content, an indefinite container, cross size, and
align-content are not computed. A negative minimum or maximum becomes zero,
and a minimum above its maximum wins, matching the one-line resolver.
"""

from __future__ import annotations

from blackhole_agent.css_flex_line import resolve_flex_line

_NONE = "none"
_WRAPS = frozenset({"nowrap", "wrap", "wrap-reverse"})
_DIRECTIONS = frozenset({"row", "row-reverse", "column", "column-reverse"})
_EPS = 1e-9


class _Invalid(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def wrap_flex_lines(
    container: object,
    items: object,
    *,
    gap: object = 0,
    wrap: object = "nowrap",
    direction: object = "row",
) -> dict[str, object]:
    """Return the used main size of each item after line breaking.

    ``container`` is the definite inner main size. Each item may carry
    ``id``, ``order``, ``base``, ``grow``, ``shrink``, ``minimum``,
    ``maximum``, and ``margin``, with the same size rules as one flex line.
    ``gap`` is the fixed main-axis gap. ``wrap`` is ``nowrap``, ``wrap``, or
    ``wrap-reverse``. ``direction`` is ``row``, ``row-reverse``, ``column``,
    or ``column-reverse``.
    """

    try:
        inner = _length(container, allow_negative=False, name="container")
        gutter = _length(gap, allow_negative=False, name="gap")
        mode = _keyword(wrap, _WRAPS, "wrap")
        axis = _keyword(direction, _DIRECTIONS, "direction")
        parsed = _items(items)
        lines = [_resolve_line(inner, gutter, line) for line in _collect(parsed, inner, gutter, mode)]
    except _Invalid as exc:
        return _invalid(exc.reason)
    return {
        "outcome": "wrapped",
        "container": _number(inner),
        "gap": _number(gutter),
        "wrap": mode,
        "direction": axis,
        "main_start": "end" if axis.endswith("-reverse") else "start",
        "lines": lines,
    }


def _invalid(reason: str) -> dict[str, object]:
    return {
        "outcome": "invalid",
        "reason": reason,
        "container": None,
        "gap": None,
        "wrap": None,
        "direction": None,
        "main_start": None,
        "lines": None,
    }


def _items(value: object) -> list[dict[str, object]]:
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise _Invalid("items must be a list of flex items")
    parsed: list[dict[str, object]] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise _Invalid(f"item {index} must be a mapping")
        ident = _ident(item.get("id", str(index)), index)
        if ident in seen:
            raise _Invalid(f"item {index} repeats id {ident}")
        seen.add(ident)
        order = item.get("order", 0)
        if isinstance(order, bool) or not isinstance(order, int):
            raise _Invalid(f"item {index} order is invalid")
        base = _length(item.get("base"), allow_negative=True, name=f"item {index} base")
        minimum = _floor_zero(_length(item.get("minimum", 0), allow_negative=True, name=f"item {index} minimum"))
        maximum = _maximum(item.get("maximum", _NONE), f"item {index} maximum")
        margin = _length(item.get("margin", 0), allow_negative=True, name=f"item {index} margin")
        hypothetical = _hypothetical(base, minimum, maximum)
        payload: dict[str, object] = {
            "base": base,
            "grow": _factor(item.get("grow", 0), f"item {index} grow"),
            "shrink": _factor(item.get("shrink", 1), f"item {index} shrink"),
            "minimum": minimum,
            "maximum": _NONE if maximum is None else maximum,
            "margin": margin,
        }
        parsed.append(
            {
                "id": ident,
                "order": order,
                "index": index,
                "outer": hypothetical + margin,
                "payload": payload,
            }
        )
    parsed.sort(key=lambda row: (int(row["order"]), int(row["index"])))
    return parsed


def _ident(value: object, index: int) -> str:
    if not isinstance(value, str) or value == "":
        raise _Invalid(f"item {index} id is invalid")
    return value


def _collect(
    items: list[dict[str, object]],
    container: float,
    gap: float,
    mode: str,
) -> list[list[dict[str, object]]]:
    if not items:
        return []
    if mode == "nowrap":
        return [items]
    lines: list[list[dict[str, object]]] = []
    current: list[dict[str, object]] = []
    outer_sum = 0.0
    for item in items:
        outer = item["outer"]
        assert isinstance(outer, float)
        if current:
            projected = outer_sum + outer + gap * len(current)
            if projected > container + _EPS:
                lines.append(current)
                current = []
                outer_sum = 0.0
        current.append(item)
        outer_sum += outer
    if current:
        lines.append(current)
    if mode == "wrap-reverse":
        lines.reverse()
    return lines


def _resolve_line(container: float, gap: float, line: list[dict[str, object]]) -> dict[str, object]:
    resolved = resolve_flex_line(container, [item["payload"] for item in line], gap=gap)
    sizes = resolved.get("main_sizes")
    if resolved.get("outcome") != "resolved" or not isinstance(sizes, list) or len(sizes) != len(line):
        reason = resolved.get("reason")
        raise _Invalid(str(reason or "flex line failed"))
    return {"ids": [item["id"] for item in line], "main_sizes": sizes}


def _hypothetical(base: float, minimum: float, maximum: float | None) -> float:
    size = base
    if maximum is not None and size > maximum:
        size = maximum
    if size < minimum:
        size = minimum
    if size < 0:
        size = 0.0
    return size


def _maximum(value: object, name: str) -> float | None:
    if _is_none(value):
        return None
    return _floor_zero(_length(value, allow_negative=True, name=name))


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
    return _length(value, allow_negative=False, name=name)


def _floor_zero(value: float) -> float:
    return 0.0 if value < 0 else value


def _keyword(value: object, allowed: frozenset[str], name: str) -> str:
    if not isinstance(value, str):
        raise _Invalid(f"{name} is invalid")
    token = " ".join(value.strip().lower().split())
    if token not in allowed:
        raise _Invalid(f"{name} is invalid")
    return token


def _number(value: float) -> int | float:
    nearest = round(value)
    if abs(value - nearest) <= _EPS:
        return int(nearest)
    return value
