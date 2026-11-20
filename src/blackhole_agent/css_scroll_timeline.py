"""Scroll and view progress for a CSS scroll-driven animation.

CSS Scroll-driven Animations. A scroll timeline's progress is the scroll
offset divided by the scrollable overflow minus the port. A view timeline's
cover, contain, entry, exit, entry-crossing, and exit-crossing ranges are
scroll offsets where the subject's border edges meet the visibility range.
The range is inactive when those two offsets coincide. Insets move the
visibility range in from the scrollport; a percentage inset uses the port.

The active duration of a finite animation is aligned to that progress.
A positive delay occupies the start of the range. A negative delay is time
already spent inside the iteration when progress is zero. An infinite
iteration count has an empty active duration, so the effect stays idle.
``sample_css_animation`` still eases the keyframes.
"""

from __future__ import annotations

import math

from blackhole_agent.css_animation import _Invalid, _parse, sample_css_animation

_RANGES = frozenset(
    {"cover", "contain", "entry", "exit", "entry-crossing", "exit-crossing", "scroll"}
)


class _Bad(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def scroll_timeline_progress(offset: object, overflow: object, port: object) -> dict[str, object]:
    """Return progress along one scrollport axis.

    ``overflow`` is the scrollable overflow size and ``port`` is the scrollport
    size on that axis. Progress is ``offset / (overflow - port)``. The timeline
    is inactive when the denominator is zero.
    """

    try:
        position = _number(offset, "offset")
        length = _number(overflow, "overflow")
        visible = _number(port, "port")
        if length < 0:
            raise _Bad("overflow")
        if visible < 0:
            raise _Bad("port")
        if length < visible:
            raise _Bad("overflow")
        return _progress(position, 0.0, length - visible, "scroll")
    except _Bad as exc:
        return _invalid(exc.reason)


def view_timeline_progress(
    offset: object,
    subject_start: object,
    subject_size: object,
    port: object,
    *,
    inset_start: object = 0,
    inset_end: object = 0,
    range_name: object = "cover",
    overflow: object = None,
) -> dict[str, object]:
    """Return progress through one named view range.

    ``subject_start`` is the subject's start border edge in the same coordinate
    space as ``offset``. Both grow toward the end of the scroll container's
    axis. ``inset_start`` and ``inset_end`` shrink the visibility range from
    the scrollport edges. ``range_name`` ``scroll`` uses ``overflow`` the same
    way a scroll timeline does.
    """

    try:
        position = _number(offset, "offset")
        start = _number(subject_start, "subject")
        size = _number(subject_size, "subject")
        visible = _number(port, "port")
        if size < 0:
            raise _Bad("subject")
        if visible < 0:
            raise _Bad("port")
        name = _range_name(range_name)
        if name == "scroll":
            if overflow is None:
                raise _Bad("overflow")
            length = _number(overflow, "overflow")
            if length < 0 or length < visible:
                raise _Bad("overflow")
            return _progress(position, 0.0, length - visible, name)
        inset_a = _inset(inset_start, visible, "inset")
        inset_b = _inset(inset_end, visible, "inset")
        vis_start = inset_a
        vis_end = visible - inset_b
        if vis_end < vis_start:
            raise _Bad("inset")
        range_start, range_end = _named_range(name, start, size, vis_start, vis_end)
        return _progress(position, range_start, range_end, name)
    except _Bad as exc:
        return _invalid(exc.reason)


def sample_scroll_driven_animation(
    stylesheet: object,
    progress: object,
    *,
    property: object = "",
) -> dict[str, object]:
    """Sample one animation at a scroll-driven progress.

    ``progress`` ``None`` is an inactive timeline: the effect does not apply
    and the value stays the underlying length. A number is the timeline
    progress, including values outside 0 and 1. The stylesheet is the same
    text ``sample_css_animation`` reads.
    """

    if isinstance(property, bool) or not isinstance(property, str):
        return _sample_invalid("property")
    if isinstance(stylesheet, bool) or not isinstance(stylesheet, str):
        return _sample_invalid("stylesheet")
    try:
        parsed, idle_reason = _parse(stylesheet, property.strip().lower())
    except _Invalid as exc:
        return _sample_invalid(exc.reason)
    if progress is None:
        return _inactive(parsed.underlying, parsed.unit)
    try:
        fraction = _number(progress, "progress")
    except _Bad as exc:
        return _sample_invalid(exc.reason)
    if idle_reason:
        sampled = sample_css_animation(stylesheet, 0, property=property)
        sampled["progress"] = _num(fraction)
        return sampled
    if math.isinf(parsed.iterations):
        return _effect_idle(parsed.underlying, parsed.unit, "infinite", fraction)
    local = _local_time(parsed.delay, parsed.duration, parsed.iterations, fraction)
    sampled = sample_css_animation(stylesheet, local, property=property)
    sampled["progress"] = _num(fraction)
    return sampled


def _named_range(
    name: str,
    subject_start: float,
    subject_size: float,
    vis_start: float,
    vis_end: float,
) -> tuple[float, float]:
    start_at_end = subject_start - vis_end
    end_at_start = subject_start + subject_size - vis_start
    start_at_start = subject_start - vis_start
    end_at_end = subject_start + subject_size - vis_end
    cover = (start_at_end, end_at_start)
    contain = (min(start_at_start, end_at_end), max(start_at_start, end_at_end))
    ranges = {
        "cover": cover,
        "contain": contain,
        "entry": (cover[0], contain[0]),
        "exit": (contain[1], cover[1]),
        "entry-crossing": (start_at_end, end_at_end),
        "exit-crossing": (start_at_start, end_at_start),
    }
    return ranges[name]


def _progress(offset: float, start: float, end: float, name: str) -> dict[str, object]:
    if start == end:
        return {
            "outcome": "inactive",
            "progress": None,
            "start": _num(start),
            "end": _num(end),
            "range": name,
            "reason": "range",
        }
    return {
        "outcome": "active",
        "progress": _num((offset - start) / (end - start)),
        "start": _num(start),
        "end": _num(end),
        "range": name,
        "reason": "",
    }


def _local_time(delay: float, duration: float, iterations: float, progress: float) -> float:
    active = duration * iterations
    if delay >= 0:
        return progress * (delay + active)
    end_time = delay + active
    if end_time <= 0:
        return 0.0
    return progress * end_time


def _range_name(value: object) -> str:
    if isinstance(value, bool) or not isinstance(value, str):
        raise _Bad("range")
    name = value.strip().lower()
    if name not in _RANGES:
        raise _Bad("range")
    return name


def _inset(value: object, port: float, name: str) -> float:
    if isinstance(value, str):
        text = value.strip().lower()
        if text.endswith("%"):
            return _number(text[:-1], name) * port / 100.0
        if text.endswith("px"):
            return _number(text[:-2], name)
        raise _Bad(name)
    return _number(value, name)


def _number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise _Bad(name)
    if isinstance(value, str):
        text = value.strip()
        try:
            number = float(text)
        except ValueError:
            raise _Bad(name) from None
    else:
        number = float(value)
    if not math.isfinite(number):
        raise _Bad(name)
    return number


def _num(value: float) -> int | float:
    if math.isfinite(value) and value == math.trunc(value):
        return int(value)
    return value


def _invalid(reason: str) -> dict[str, object]:
    return {
        "outcome": "invalid",
        "progress": None,
        "start": None,
        "end": None,
        "range": "",
        "reason": reason,
    }


def _inactive(value: float, unit: str) -> dict[str, object]:
    return {
        "outcome": "inactive",
        "applying": False,
        "value": _num(value),
        "unit": unit,
        "text": _text(value, unit),
        "reason": "timeline",
        "progress": None,
    }


def _effect_idle(value: float, unit: str, reason: str, progress: float) -> dict[str, object]:
    return {
        "outcome": "idle",
        "applying": False,
        "value": _num(value),
        "unit": unit,
        "text": _text(value, unit),
        "reason": reason,
        "progress": _num(progress),
    }


def _sample_invalid(reason: str) -> dict[str, object]:
    return {
        "outcome": "invalid",
        "applying": False,
        "value": None,
        "unit": "",
        "text": "",
        "reason": reason,
        "progress": None,
    }


def _text(value: float, unit: str) -> str:
    rendered = str(int(value)) if value == math.trunc(value) else f"{value:.6f}".rstrip("0").rstrip(".")
    return f"{rendered}{unit}"
