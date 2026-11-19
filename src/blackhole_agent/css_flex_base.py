"""Unclamped flex base and hypothetical main size of one flex item.

CSS Flexbox §9.2.3. The flex base ignores minimums, maximums, and the
content-box floor. A specified size of zero that already includes its
padding and border therefore has a negative inner base. The hypothetical
main size clamps that base and floors the content box at zero. When the
minimum and the maximum disagree, the minimum wins.

A definite basis, including a percentage of a definite container, is that
used size. ``auto`` retrieves the main size, and an automatic main size
becomes ``content``. A percentage of an indefinite container is not definite.
``content`` with a preferred aspect ratio and a definite cross size is the
transferred size, before a min-content or max-content constraint. Otherwise
a constraint sizes ``content`` and ``fit-content``. ``min-content`` and
``max-content`` stay those contributions. An automatic minimum uses the
existing content-based floor and does not change the flex base.

Orthogonal writing modes are not laid out. The caller supplies the
min-content and max-content contributions. Free-space distribution stays
with ``resolve_flex_line``.
"""

from __future__ import annotations

from blackhole_agent.css_flex_minimum import automatic_flex_minimum
from blackhole_agent.css_length_math import is_length_math, resolve_length_math

_AUTO = "auto"
_NONE = "none"
_CONTENT = "content"
_MIN_CONTENT = "min-content"
_MAX_CONTENT = "max-content"
_FIT_CONTENT = "fit-content"
_INDEFINITE = "indefinite"
_CONTENT_BOX = "content-box"
_BORDER_BOX = "border-box"
_BASIS_WORDS = frozenset({_AUTO, _CONTENT, _MIN_CONTENT, _MAX_CONTENT, _FIT_CONTENT})
_CONSTRAINTS = frozenset({_MIN_CONTENT, _MAX_CONTENT})
_AVAILABLE = frozenset({_CONTENT, _FIT_CONTENT})


class _Invalid(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def resolve_flex_base(
    container: object = _INDEFINITE,
    *,
    flex_basis: object = _AUTO,
    main_size: object = _AUTO,
    minimum: object = _AUTO,
    maximum: object = _NONE,
    padding: object = 0,
    border: object = 0,
    box_sizing: object = _CONTENT_BOX,
    cross: object = _AUTO,
    ratio: object = _NONE,
    min_content: object = None,
    max_content: object = None,
    constraint: object = None,
    replaced: object = False,
    scrollable: object = False,
) -> dict[str, object]:
    """Return the inner flex base and the hypothetical main size.

    ``container`` is the inner main size, or ``indefinite``. ``flex_basis``
    and ``main_size`` accept a length, a percentage, ``calc()``, ``min()``,
    ``max()``, ``clamp()``, ``auto``, ``content``, ``min-content``,
    ``max-content``, or ``fit-content``. ``padding`` and ``border`` are the
    sums of the main-axis edges. ``box_sizing`` is ``content-box`` or
    ``border-box``. ``cross`` is a definite content-box cross size or
    ``auto``. ``ratio`` is ``none`` or the main size divided by the cross
    size. ``constraint`` is ``min-content``, ``max-content``, or omitted.
    ``minimum`` accepts ``auto``. ``maximum`` accepts ``none``.
    """

    try:
        available = _container(container)
        sizing = _keyword(box_sizing, {_CONTENT_BOX, _BORDER_BOX}, "box-sizing")
        chrome = _edge(padding, "padding") + _edge(border, "border")
        limit = _keyword(constraint, _CONSTRAINTS, "constraint") if constraint is not None else None
        kind, specified = _used_basis(flex_basis, main_size, available)
        inner, basis = _base_inner(
            kind,
            specified,
            chrome,
            sizing,
            available,
            limit,
            _cross(cross),
            _ratio(ratio),
            min_content,
            max_content,
        )
        hypothetical = _hypothetical(
            inner,
            chrome,
            sizing,
            available,
            minimum,
            maximum,
            main_size,
            _cross(cross),
            _ratio(ratio),
            min_content,
            replaced,
            scrollable,
        )
    except _Invalid as exc:
        return _invalid(exc.reason)
    return {
        "outcome": "resolved",
        "reason": None,
        "inner_base": _number(inner),
        "outer_base": _number(inner + chrome),
        "hypothetical_inner": _number(hypothetical),
        "hypothetical_outer": _number(hypothetical + chrome),
        "basis": basis,
    }


def _invalid(reason: str) -> dict[str, object]:
    return {
        "outcome": "invalid",
        "reason": reason,
        "inner_base": None,
        "outer_base": None,
        "hypothetical_inner": None,
        "hypothetical_outer": None,
        "basis": None,
    }


def _base_inner(
    kind: str,
    specified: float | None,
    chrome: float,
    sizing: str,
    available: float | None,
    constraint: str | None,
    cross: float | None,
    ratio: float | None,
    min_content: object,
    max_content: object,
) -> tuple[float, str]:
    if kind == "definite":
        if specified is None:
            raise _Invalid("flex-basis is invalid")
        return _to_inner(specified, chrome, sizing), "definite"
    if kind == _CONTENT and ratio is not None and cross is not None:
        return cross * ratio, "transferred"
    if kind in _AVAILABLE and constraint == _MIN_CONTENT:
        return _contribution(min_content, "min-content"), _MIN_CONTENT
    if kind in _AVAILABLE and constraint == _MAX_CONTENT:
        return _contribution(max_content, "max-content"), _MAX_CONTENT
    if kind == _MIN_CONTENT:
        return _contribution(min_content, "min-content"), _MIN_CONTENT
    if kind == _MAX_CONTENT:
        return _contribution(max_content, "max-content"), _MAX_CONTENT
    if kind == _CONTENT:
        return _contribution(max_content, "max-content"), _MAX_CONTENT
    low = _contribution(min_content, "min-content")
    high = _contribution(max_content, "max-content")
    if available is None:
        return high, _FIT_CONTENT
    return min(high, max(low, available)), _FIT_CONTENT


def _hypothetical(
    inner: float,
    chrome: float,
    sizing: str,
    available: float | None,
    minimum: object,
    maximum: object,
    main_size: object,
    cross: float | None,
    ratio: float | None,
    min_content: object,
    replaced: object,
    scrollable: object,
) -> float:
    floor = _used_minimum(
        minimum,
        maximum,
        main_size,
        chrome,
        sizing,
        available,
        cross,
        ratio,
        min_content,
        replaced,
        scrollable,
    )
    ceiling = _used_maximum(maximum, chrome, sizing, available)
    if ceiling is not None and floor > ceiling:
        ceiling = floor
    size = inner
    if ceiling is not None and size > ceiling:
        size = ceiling
    if size < floor:
        size = floor
    if size < 0:
        size = 0.0
    return size


def _used_minimum(
    minimum: object,
    maximum: object,
    main_size: object,
    chrome: float,
    sizing: str,
    available: float | None,
    cross: float | None,
    ratio: float | None,
    min_content: object,
    replaced: object,
    scrollable: object,
) -> float:
    token = _size_token(minimum, available, "minimum")
    if token[0] == "pct" and available is None:
        token = (_AUTO, 0.0)
    if token[0] != _AUTO:
        return _to_inner(max(0.0, _definite_px(token, available, "minimum")), chrome, sizing)
    content = 0.0 if min_content is None else _contribution(min_content, "min-content")
    specified = _definite_property(main_size, chrome, sizing, available)
    cap = _used_maximum(maximum, chrome, sizing, available)
    result = automatic_flex_minimum(
        content,
        specified=_AUTO if specified is None else max(0.0, specified),
        maximum=_NONE if cap is None else max(0.0, cap),
        ratio=_NONE if ratio is None else ratio,
        cross=_AUTO if cross is None else cross,
        replaced=replaced,
        scrollable=scrollable,
    )
    floor = result.get("minimum")
    if result.get("outcome") != "definite" or isinstance(floor, bool) or not isinstance(floor, (int, float)):
        raise _Invalid(str(result.get("reason") or "minimum is invalid"))
    return float(floor)


def _used_maximum(
    maximum: object,
    chrome: float,
    sizing: str,
    available: float | None,
) -> float | None:
    token = _size_token(maximum, available, "maximum")
    if token[0] in {_NONE, _AUTO} or (token[0] == "pct" and available is None):
        return None
    return _to_inner(max(0.0, _definite_px(token, available, "maximum")), chrome, sizing)


def _definite_property(
    main_size: object,
    chrome: float,
    sizing: str,
    available: float | None,
) -> float | None:
    token = _size_token(main_size, available, "main size")
    if token[0] in _BASIS_WORDS or token[0] == "pct" and available is None:
        return None
    if token[0] == _AUTO:
        return None
    return _to_inner(max(0.0, _definite_px(token, available, "main size")), chrome, sizing)


def _used_basis(
    flex_basis: object,
    main_size: object,
    available: float | None,
) -> tuple[str, float | None]:
    kind, value = _basis_token(flex_basis, available, "flex-basis")
    if kind == _AUTO:
        kind, value = _basis_token(main_size, available, "main size")
        if kind == _AUTO:
            return _CONTENT, None
    if kind == "px":
        return "definite", max(0.0, value)
    if kind == "pct":
        if available is None:
            return _CONTENT, None
        return "definite", max(0.0, available * value / 100.0)
    return kind, None


def _basis_token(value: object, available: float | None, name: str) -> tuple[str, float]:
    token = _size_token(value, available, name)
    if token[0] == _NONE:
        raise _Invalid(f"{name} is invalid")
    return token


def _size_token(value: object, available: float | None, name: str) -> tuple[str, float]:
    if is_length_math(value):
        return _math(value, available, name)
    if isinstance(value, bool):
        raise _Invalid(f"{name} is invalid")
    if isinstance(value, (int, float)):
        return _finite(float(value), name)
    if not isinstance(value, str):
        raise _Invalid(f"{name} is invalid")
    text = " ".join(value.strip().lower().split())
    if text in _BASIS_WORDS or text == _NONE:
        return text, 0.0
    if text.endswith("%"):
        return "pct", _number_text(text[:-1], name)
    if text.endswith("px"):
        return _finite(_number_text(text[:-2], name), name)
    raise _Invalid(f"{name} is invalid")


def _math(value: object, available: float | None, name: str) -> tuple[str, float]:
    basis = 0.0 if available is None else available
    resolved = resolve_length_math(
        value,
        percentage_basis=basis,
        allow_percentage=available is not None,
    )
    if resolved.get("outcome") != "resolved":
        if available is None and resolved.get("reason") == "percentage":
            return _CONTENT, 0.0
        raise _Invalid(f"{name} is invalid")
    number = resolved.get("px")
    if isinstance(number, bool) or not isinstance(number, (int, float)):
        raise _Invalid(f"{name} is invalid")
    return _finite(float(number), name)


def _definite_px(token: tuple[str, float], available: float | None, name: str) -> float:
    kind, value = token
    if kind == "px":
        return value
    if kind == "pct":
        if available is None:
            raise _Invalid(f"{name} is invalid")
        return available * value / 100.0
    raise _Invalid(f"{name} is invalid")


def _to_inner(specified: float, chrome: float, sizing: str) -> float:
    size = specified if specified > 0 else 0.0
    if sizing == _BORDER_BOX:
        return size - chrome
    return size


def _contribution(value: object, name: str) -> float:
    if value is None:
        raise _Invalid(f"{name} is required")
    return _nonneg(value, name)


def _container(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, str) and value.strip().lower() == _INDEFINITE:
        return None
    return _nonneg(value, "container")


def _cross(value: object) -> float | None:
    if isinstance(value, str) and value.strip().lower() == _AUTO:
        return None
    return _nonneg(value, "cross size")


def _ratio(value: object) -> float | None:
    if isinstance(value, str) and " ".join(value.strip().lower().split()) == _NONE:
        return None
    number = _nonneg(value, "ratio")
    if number <= 0:
        raise _Invalid("ratio must be positive")
    return number


def _edge(value: object, name: str) -> float:
    if isinstance(value, str):
        text = value.strip().lower()
        if text.endswith("px"):
            return _nonneg(text[:-2], name)
    return _nonneg(value, name)


def _keyword(value: object, allowed: set[str] | frozenset[str], name: str) -> str:
    if not isinstance(value, str):
        raise _Invalid(f"{name} is invalid")
    token = value.strip().lower()
    if token not in allowed:
        raise _Invalid(f"{name} is invalid")
    return token


def _finite(value: float, name: str) -> tuple[str, float]:
    if value != value or value in {float("inf"), float("-inf")}:
        raise _Invalid(f"{name} is invalid")
    return "px", value


def _number_text(text: str, name: str) -> float:
    try:
        return float(text)
    except ValueError as exc:
        raise _Invalid(f"{name} is invalid") from exc


def _nonneg(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise _Invalid(f"{name} is invalid")
    if isinstance(value, str):
        text = value.strip().lower()
        if text.endswith("px"):
            text = text[:-2]
        try:
            number = float(text)
        except ValueError as exc:
            raise _Invalid(f"{name} is invalid") from exc
    else:
        number = float(value)
    if number != number or number in {float("inf"), float("-inf")} or number < 0:
        raise _Invalid(f"{name} is invalid")
    return number


def _number(value: float) -> int | float:
    nearest = round(value)
    if abs(value - nearest) <= 1e-9:
        return int(nearest)
    return value
