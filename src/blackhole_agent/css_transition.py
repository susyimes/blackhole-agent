"""Interrupt one CSS length transition.

CSS Transitions Level 1 keeps a running transition on its original duration
and easing when the target length does not change. When the target does
change, a combined duration that is not positive cancels it. Retargeting to
the length already showing also cancels it. Retargeting to the
reversing-adjusted start shortens the return: the new shortening factor is
the absolute value, clamped to [0, 1], of the old easing output times the old
shortening factor, plus one minus that old factor. Any other target starts a
full-duration transition at the current length.

A positive delay holds the start length. A negative delay begins part-way
through the active interval. During a reverse, that negative delay is scaled
by the new shortening factor, and the active interval is the duration times
that same factor. Before the start time the used length is the start length,
not the easing output at input zero. At the end time the transition is
finished and the used length is the target.
"""

from __future__ import annotations

import math

from blackhole_agent.css_animation import _Invalid as _EaseInvalid
from blackhole_agent.css_animation import _easing_output, _length, _parse_easing, _time_value

_EPS = 1e-9


class _Invalid(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class _Change:
    def __init__(self, time_ms: float, value: float, duration: float, delay: float, easing: object, matched: bool) -> None:
        self.time_ms = time_ms
        self.value = value
        self.duration = duration
        self.delay = delay
        self.easing = easing
        self.matched = matched


class _Live:
    def __init__(
        self,
        start_time: float,
        end_time: float,
        start_value: float,
        end_value: float,
        reversing_start: float,
        shortening: float,
        easing: object,
    ) -> None:
        self.start_time = start_time
        self.end_time = end_time
        self.start_value = start_value
        self.end_value = end_value
        self.reversing_start = reversing_start
        self.shortening = shortening
        self.easing = easing


class _Run:
    def __init__(self, value: float, unit: str) -> None:
        self.value = value
        self.unit = unit
        self.live: _Live | None = None
        self.reason = "before"


def interrupt_css_transition(before: object, changes: object, sample_ms: object) -> dict[str, object]:
    """Return the used length of one transition at ``sample_ms``.

    ``before`` is the length before any change. ``changes`` is a list, in
    nondecreasing ``time_ms`` order, of style changes. Each change names the
    new ``value`` plus the ``duration``, ``delay``, and ``easing`` that apply
    to a transition started by that change. ``transition`` false means the
    property is no longer listed. Time is milliseconds.
    """

    try:
        value, unit = _parse_length(before, "before")
        events = _parse_changes(changes, unit)
        sample = _finite(sample_ms, "sample")
        return _report(_simulate(value, unit, events, sample), sample)
    except (_Invalid, _EaseInvalid) as exc:
        return _invalid(getattr(exc, "reason", "easing"))


def _simulate(value: float, unit: str, events: list[_Change], sample: float) -> _Run:
    run = _Run(value, unit)
    for event in events:
        if event.time_ms > sample:
            break
        _finish_if_due(run, event.time_ms)
        _apply(run, event)
    _finish_if_due(run, sample)
    return run


def _apply(run: _Run, event: _Change) -> None:
    if not event.matched:
        run.live = None
        run.value = event.value
        run.reason = "removed"
        return
    live = run.live
    if live is None:
        _start_or_jump(run, event, run.value)
        return
    if _same(live.end_value, event.value):
        return
    current = _value_at(live, event.time_ms)
    combined = event.duration + event.delay
    if _same(current, event.value) or combined <= 0:
        run.live = None
        run.value = event.value
        run.reason = "cancelled" if _same(current, event.value) else "immediate"
        return
    if _same(live.reversing_start, event.value):
        _start_reverse(run, live, event, current)
        return
    _start_fresh(run, event, current, shortening=1.0, reversing_start=current, shortened_delay=False)


def _start_or_jump(run: _Run, event: _Change, before: float) -> None:
    combined = event.duration + event.delay
    if _same(before, event.value) or combined <= 0:
        run.value = event.value
        run.reason = "unchanged" if _same(before, event.value) else "immediate"
        return
    _start_fresh(run, event, before, shortening=1.0, reversing_start=before, shortened_delay=False)


def _start_reverse(run: _Run, live: _Live, event: _Change, current: float) -> None:
    output = _easing_at(live, event.time_ms)
    shortening = min(1.0, abs(output * live.shortening + (1.0 - live.shortening)))
    _start_fresh(
        run,
        event,
        current,
        shortening=shortening,
        reversing_start=live.end_value,
        shortened_delay=True,
    )


def _start_fresh(
    run: _Run,
    event: _Change,
    start_value: float,
    *,
    shortening: float,
    reversing_start: float,
    shortened_delay: bool,
) -> None:
    delay = event.delay
    if shortened_delay and delay < 0:
        delay *= shortening
    start_time = event.time_ms + delay
    run.live = _Live(
        start_time,
        start_time + event.duration * shortening,
        start_value,
        event.value,
        reversing_start,
        shortening,
        event.easing,
    )
    run.reason = "started"


def _finish_if_due(run: _Run, time_ms: float) -> None:
    live = run.live
    if live is not None and time_ms >= live.end_time:
        run.value = live.end_value
        run.live = None
        run.reason = "completed"


def _value_at(live: _Live, time_ms: float) -> float:
    if time_ms >= live.end_time:
        return live.end_value
    if time_ms <= live.start_time:
        return live.start_value
    elapsed = time_ms - live.start_time
    span = live.end_time - live.start_time
    eased = _easing_output(live.easing, elapsed / span)
    return live.start_value + (live.end_value - live.start_value) * eased


def _easing_at(live: _Live, time_ms: float) -> float:
    if time_ms >= live.end_time:
        return float(_easing_output(live.easing, 1.0))
    if time_ms <= live.start_time or live.end_time <= live.start_time:
        return 0.0
    elapsed = time_ms - live.start_time
    span = live.end_time - live.start_time
    return float(_easing_output(live.easing, elapsed / span))


def _report(run: _Run, sample: float) -> dict[str, object]:
    live = run.live
    if live is None:
        return {
            "outcome": "settled",
            "applying": False,
            "value": _num(run.value),
            "unit": run.unit,
            "shortening": None,
            "reversing": False,
            "reason": run.reason,
        }
    return {
        "outcome": "transitioning",
        "applying": True,
        "value": _num(_value_at(live, sample)),
        "unit": run.unit,
        "shortening": _num(live.shortening),
        "reversing": live.shortening < 1.0 - _EPS,
        "reason": "",
    }


def _parse_changes(changes: object, unit: str) -> list[_Change]:
    if isinstance(changes, (str, bytes)) or not isinstance(changes, (list, tuple)):
        raise _Invalid("changes")
    parsed: list[_Change] = []
    previous: float | None = None
    for item in changes:
        if not isinstance(item, dict):
            raise _Invalid("change")
        time_ms = _finite(item.get("time_ms"), "time")
        if previous is not None and time_ms < previous:
            raise _Invalid("order")
        previous = time_ms
        value, value_unit = _parse_length(item.get("value"), "value")
        if value_unit != unit:
            raise _Invalid("unit")
        duration = _duration(item.get("duration", "0s"))
        delay = _delay(item.get("delay", "0s"))
        easing = _easing(item.get("easing", "linear"))
        matched = _matched(item.get("transition", True))
        parsed.append(_Change(time_ms, value, duration, delay, easing, matched))
    return parsed


def _parse_length(value: object, reason: str) -> tuple[float, str]:
    if isinstance(value, bool) or not isinstance(value, str):
        raise _Invalid(reason)
    try:
        number, unit = _length(value)
    except _EaseInvalid as exc:
        raise _Invalid(reason) from exc
    return number, unit


def _duration(value: object) -> float:
    number = _clock(value, "duration")
    if number < 0:
        raise _Invalid("duration")
    return number


def _delay(value: object) -> float:
    return _clock(value, "delay")


def _clock(value: object, reason: str) -> float:
    if isinstance(value, bool) or not isinstance(value, str):
        raise _Invalid(reason)
    try:
        return _time_value(value, reason)
    except _EaseInvalid as exc:
        raise _Invalid(reason) from exc


def _easing(value: object) -> object:
    if isinstance(value, bool) or not isinstance(value, str):
        raise _Invalid("easing")
    try:
        return _parse_easing(value)
    except _EaseInvalid as exc:
        raise _Invalid(getattr(exc, "reason", "easing")) from exc


def _matched(value: object) -> bool:
    if not isinstance(value, bool):
        raise _Invalid("transition")
    return value


def _finite(value: object, reason: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _Invalid(reason)
    number = float(value)
    if not math.isfinite(number):
        raise _Invalid(reason)
    return number


def _same(left: float, right: float) -> bool:
    return abs(left - right) <= _EPS


def _num(value: float) -> int | float:
    nearest = round(value)
    if abs(value - nearest) <= _EPS:
        return int(nearest)
    return value


def _invalid(reason: str) -> dict[str, object]:
    return {
        "outcome": "invalid",
        "applying": False,
        "value": None,
        "unit": "",
        "shortening": None,
        "reversing": False,
        "reason": reason,
    }
