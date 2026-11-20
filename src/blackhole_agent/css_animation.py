"""Sample one CSS animation at a local time.

CSS Animations Level 1 eases each keyframe interval. The timing function on a
keyframe covers the span to the next keyframe; the function on the 100%
keyframe is ignored. Iterations count from 1, so ``alternate`` plays odd
iterations forwards and even iterations in reverse. A positive delay keeps
the underlying value unless fill is ``backwards`` or ``both``, and that hold
is the keyframe that starts the first iteration. The timing function is not
applied during the delay. After the active duration, ``forwards`` holds the
end of the last iteration, including a fractional iteration and an even
``alternate`` iteration that finishes on the start value. An exact multiple
of the duration that is still inside the active duration is the end of the
iteration that just finished, not the start of the next one.

Easing output follows CSS Easing Functions Level 2: ``linear()`` control
points, cubic Bézier curves, and ``steps()``.
"""

from __future__ import annotations

import math
import re

_IDENT = re.compile(r"-?[A-Za-z_][A-Za-z0-9_-]*")
_NUMBER = re.compile(r"^[+-]?(?:\d+\.?\d*|\.\d+)$")
_INTEGER = re.compile(r"^[+-]?\d+$")
_RESERVED_NAMES = frozenset({"none", "initial", "inherit", "unset", "revert", "revert-layer", "default"})
_DIRECTIONS = frozenset({"normal", "reverse", "alternate", "alternate-reverse"})
_FILLS = frozenset({"none", "forwards", "backwards", "both"})
_CUBICS = {
    "ease": (0.25, 0.1, 0.25, 1.0),
    "ease-in": (0.42, 0.0, 1.0, 1.0),
    "ease-out": (0.0, 0.0, 0.58, 1.0),
    "ease-in-out": (0.42, 0.0, 0.58, 1.0),
}
_JUMP = {
    "end": "jump-end",
    "jump-end": "jump-end",
    "start": "jump-start",
    "jump-start": "jump-start",
    "jump-none": "jump-none",
    "jump-both": "jump-both",
}


class _Invalid(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class _Ease:
    def __init__(self, kind: str, data: object = None) -> None:
        self.kind = kind
        self.data = data


class _Frame:
    def __init__(self, offset: float, value: float, easing: _Ease) -> None:
        self.offset = offset
        self.value = value
        self.easing = easing


class _Animation:
    def __init__(
        self,
        frames: list[_Frame],
        duration: float,
        delay: float,
        iterations: float,
        direction: str,
        fill: str,
        underlying: float,
        unit: str,
    ) -> None:
        self.frames = frames
        self.duration = duration
        self.delay = delay
        self.iterations = iterations
        self.direction = direction
        self.fill = fill
        self.underlying = underlying
        self.unit = unit


def sample_css_animation(
    stylesheet: object,
    local_time_ms: object,
    *,
    property: object = "",
) -> dict[str, object]:
    """Return the used length of one animation at ``local_time_ms``.

    ``stylesheet`` holds ``@keyframes`` plus one style rule of animation
    longhands and the underlying property. ``property`` selects the length
    when more than one property is animated. Time is milliseconds from the
    moment the animation is applied. A positive delay has not started yet.
    A negative delay has already consumed that much of the active duration.
    """

    try:
        if isinstance(stylesheet, bool) or not isinstance(stylesheet, str):
            return _invalid("stylesheet")
        if isinstance(property, bool) or not isinstance(property, str):
            return _invalid("property")
        if (
            isinstance(local_time_ms, bool)
            or not isinstance(local_time_ms, (int, float))
            or not math.isfinite(float(local_time_ms))
        ):
            return _invalid("time")
        animation, idle_reason = _parse(stylesheet, property.strip().lower())
        if animation is None:
            return _idle(0.0, "", idle_reason)
        return _sample(animation, float(local_time_ms), idle_reason)
    except _Invalid as exc:
        return _invalid(exc.reason)


def _sample(animation: _Animation, time: float, idle_reason: str) -> dict[str, object]:
    if idle_reason:
        return _idle(animation.underlying, animation.unit, idle_reason)
    phase, active_time = _phase(animation, time)
    if phase == "before":
        if animation.fill in {"backwards", "both"}:
            return _held(animation, 0, 0.0, eased=False)
        return _idle(animation.underlying, animation.unit, "")
    if phase == "after":
        if animation.fill in {"forwards", "both"}:
            index, progress = _finished_iteration(animation)
            return _held(animation, index, progress, eased=animation.iterations != 0)
        return _idle(animation.underlying, animation.unit, "")
    index, progress = _running_iteration(active_time, animation.duration)
    return _held(animation, index, progress, eased=True)


def _phase(animation: _Animation, time: float) -> tuple[str, float]:
    if time < animation.delay:
        return "before", 0.0
    if animation.duration == 0 or animation.iterations == 0:
        active = 0.0
    elif math.isinf(animation.iterations):
        active = math.inf
    else:
        active = animation.duration * animation.iterations
    if time >= animation.delay + active:
        return "after", 0.0
    return "active", time - animation.delay


def _running_iteration(active_time: float, duration: float) -> tuple[int, float]:
    if duration == 0 or active_time == 0:
        return 0, 0.0
    ratio = active_time / duration
    nearest = round(ratio)
    if nearest >= 1 and abs(ratio - nearest) <= 1e-9:
        return nearest - 1, 1.0
    index = math.floor(ratio)
    return index, ratio - index


def _finished_iteration(animation: _Animation) -> tuple[int, float]:
    count = animation.iterations
    if count == 0 or math.isinf(count):
        return 0, 0.0
    if abs(count - round(count)) <= 1e-9:
        return max(0, int(round(count)) - 1), 1.0
    index = math.floor(count)
    return index, count - index


def _held(animation: _Animation, index: int, progress: float, *, eased: bool) -> dict[str, object]:
    reverse = _plays_reverse(animation.direction, index)
    directed = (1.0 - progress) if reverse else progress
    if not eased:
        value = _endpoint(animation, directed)
    else:
        value = _interpolate(animation, directed)
    return _sampled(value, animation.unit)


def _plays_reverse(direction: str, index: int) -> bool:
    if direction == "reverse":
        return True
    if direction == "alternate":
        return index % 2 == 1
    if direction == "alternate-reverse":
        return index % 2 == 0
    return False


def _endpoint(animation: _Animation, directed: float) -> float:
    if directed >= 1:
        return animation.frames[-1].value
    return animation.frames[0].value


def _interpolate(animation: _Animation, directed: float) -> float:
    frames = animation.frames
    if len(frames) == 1:
        return frames[0].value
    if directed >= frames[-1].offset:
        start, stop = frames[-2], frames[-1]
        local = 1.0
    else:
        start = frames[0]
        stop = frames[1]
        for index, frame in enumerate(frames):
            if frame.offset <= directed:
                start = frame
                stop = frames[min(index + 1, len(frames) - 1)]
            else:
                break
        span = stop.offset - start.offset
        local = 0.0 if span == 0 else (directed - start.offset) / span
    eased = _easing_output(start.easing, local)
    return start.value + (stop.value - start.value) * eased


def _easing_output(easing: _Ease, progress: float) -> float:
    if easing.kind == "identity":
        return progress
    if easing.kind == "cubic":
        x1, y1, x2, y2 = easing.data  # type: ignore[misc]
        return _cubic(progress, x1, y1, x2, y2)
    if easing.kind == "steps":
        count, position = easing.data  # type: ignore[misc]
        return _steps(progress, count, position)
    points = easing.data
    return _linear_points(progress, points)  # type: ignore[arg-type]


def _cubic(x: float, x1: float, y1: float, x2: float, y2: float) -> float:
    if x1 == y1 and x2 == y2:
        return x
    if 0 <= x <= 1:
        return _bezier(_solve_bezier(x, x1, x2), y1, y2)
    if x < 0:
        if x1 > 0:
            return x * y1 / x1
        if x2 > 0:
            return x * y2 / x2
        return 0.0
    if x2 < 1:
        return _line_past(x, x2, y2)
    if x1 < 1:
        return _line_past(x, x1, y1)
    return 1.0


def _line_past(x: float, x1: float, y1: float) -> float:
    span = 1.0 - x1
    if span == 0:
        return 1.0
    return y1 + (x - x1) * (1.0 - y1) / span


def _solve_bezier(x: float, x1: float, x2: float) -> float:
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    lo = 0.0
    hi = 1.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if _bezier(mid, x1, x2) < x:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def _bezier(t: float, c1: float, c2: float) -> float:
    complement = 1.0 - t
    return (3 * complement * complement * t * c1) + (3 * complement * t * t * c2) + (t * t * t)


def _steps(progress: float, count: int, position: str) -> float:
    if progress < 0:
        return 0.0
    if progress >= 1:
        return 1.0
    interval = min(count - 1, math.floor(progress * count))
    if position == "jump-start":
        return (interval + 1) / count
    if position == "jump-none":
        return interval / (count - 1)
    if position == "jump-both":
        return (interval + 1) / (count + 1)
    return interval / count


def _linear_points(progress: float, points: list[tuple[float, float]]) -> float:
    if len(points) == 1:
        return points[0][1]
    matched = [point for point in points if point[0] == progress]
    if matched:
        return matched[-1][1]
    if progress < points[0][0]:
        return _linear_span(progress, points[0], points[1], prefer_end=False)
    if progress > points[-1][0]:
        return _linear_span(progress, points[-2], points[-1], prefer_end=True)
    start = points[0]
    stop = points[-1]
    for point in points:
        if point[0] < progress:
            start = point
        elif point[0] > progress:
            stop = point
            break
    return _linear_span(progress, start, stop, prefer_end=False)


def _linear_span(
    progress: float,
    start: tuple[float, float],
    stop: tuple[float, float],
    *,
    prefer_end: bool,
) -> float:
    if start[0] == stop[0]:
        return stop[1] if prefer_end else start[1]
    return start[1] + (stop[1] - start[1]) * (progress - start[0]) / (stop[0] - start[0])


def _parse(stylesheet: str, property_name: str) -> tuple[_Animation | None, str]:
    text = _strip_comments(stylesheet)
    keyframes, rest = _extract_keyframes(text)
    rules = _style_bodies(rest)
    chosen = None
    for body in rules:
        declarations = _declaration_map(body)
        if "animation-name" in declarations:
            chosen = declarations
    if chosen is None:
        raise _Invalid("animation-name")
    name = _animation_name(chosen["animation-name"])
    if name is None:
        underlying, unit = _resolve_underlying(chosen, property_name, keyframes)
        return _bare(underlying, unit), "keyframes"
    frames = keyframes.get(name)
    if frames is None:
        underlying, unit = _resolve_underlying(chosen, property_name, keyframes)
        return _bare(underlying, unit), "keyframes"
    prop = _choose_property(property_name, frames, chosen)
    if prop not in _animated_properties(frames):
        underlying, unit = _resolve_underlying(chosen, prop, keyframes)
        return _bare(underlying, unit), "property"
    easing = _parse_easing(chosen.get("animation-timing-function", "linear"))
    duration = _time_value(chosen.get("animation-duration", "0s"), "duration")
    delay = _time_value(chosen.get("animation-delay", "0s"), "delay")
    iterations = _iterations(chosen.get("animation-iteration-count", "1"))
    direction = chosen.get("animation-direction", "normal").strip().lower()
    fill = chosen.get("animation-fill-mode", "none").strip().lower()
    if direction not in _DIRECTIONS:
        raise _Invalid("direction")
    if fill not in _FILLS:
        raise _Invalid("fill-mode")
    if duration < 0:
        raise _Invalid("duration")
    built, unit = _frames_for(frames, prop, chosen, easing)
    underlying_value, underlying_unit = _length(chosen[prop])
    unit = _unify(unit, underlying_unit, underlying_value)
    return (
        _Animation(built, duration, delay, iterations, direction, fill, underlying_value, unit),
        "",
    )


def _bare(underlying: float, unit: str) -> _Animation:
    identity = _Ease("identity")
    frame = _Frame(0.0, underlying, identity)
    return _Animation([frame], 0.0, 0.0, 0.0, "normal", "none", underlying, unit)


def _resolve_underlying(
    chosen: dict[str, str],
    property_name: str,
    keyframes: dict[str, list[tuple[float, dict[str, str]]]],
) -> tuple[float, str]:
    prop = property_name
    if not prop:
        names = [name for name in chosen if not name.startswith("animation-")]
        if len(names) == 1:
            prop = names[0]
        else:
            animated: list[str] = []
            for rules in keyframes.values():
                animated.extend(_animated_properties(rules))
            unique = list(dict.fromkeys(animated))
            if len(unique) == 1:
                prop = unique[0]
    if not prop or prop not in chosen:
        raise _Invalid("underlying")
    return _length(chosen[prop])


def _choose_property(
    property_name: str,
    frames: list[tuple[float, dict[str, str]]],
    chosen: dict[str, str],
) -> str:
    if property_name:
        return property_name
    animated = _animated_properties(frames)
    if len(animated) == 1:
        return animated[0]
    declared = [name for name in chosen if not name.startswith("animation-") and name in animated]
    if len(declared) == 1:
        return declared[0]
    raise _Invalid("property")


def _animated_properties(frames: list[tuple[float, dict[str, str]]]) -> list[str]:
    names: list[str] = []
    for _offset, declarations in frames:
        for name in declarations:
            if name != "animation-timing-function" and name not in names:
                names.append(name)
    return names


def _frames_for(
    frames: list[tuple[float, dict[str, str]]],
    prop: str,
    chosen: dict[str, str],
    default_easing: _Ease,
) -> tuple[list[_Frame], str]:
    grouped: dict[float, dict[str, str]] = {}
    for offset, declarations in frames:
        grouped.setdefault(offset, {}).update(declarations)
    if prop not in chosen:
        raise _Invalid("underlying")
    underlying, unit = _length(chosen[prop])
    resolved: list[tuple[float, float, _Ease]] = []
    for offset, declarations in grouped.items():
        if prop not in declarations:
            continue
        value, value_unit = _length(declarations[prop])
        unit = _unify(unit, value_unit, value)
        if "animation-timing-function" in declarations:
            easing = _parse_easing(declarations["animation-timing-function"])
        else:
            easing = default_easing
        resolved.append((offset, value, easing))
    if not any(offset == 0 for offset, _value, _easing in resolved):
        resolved.append((0.0, underlying, default_easing))
    if not any(offset == 1 for offset, _value, _easing in resolved):
        resolved.append((1.0, underlying, default_easing))
    resolved.sort(key=lambda item: item[0])
    return [_Frame(offset, value, easing) for offset, value, easing in resolved], unit


def _unify(current: str, new: str, value: float) -> str:
    if new == "" and value == 0:
        return current
    if current == "" and value == 0 and new:
        return new
    if current == "":
        return new
    if new in {"", current}:
        return current
    raise _Invalid("unit")


def _animation_name(raw: str) -> str | None:
    text = raw.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        name = text[1:-1]
        if not name:
            raise _Invalid("animation-name")
        return name
    if not _IDENT.fullmatch(text):
        raise _Invalid("animation-name")
    if text.lower() == "none":
        return None
    return text


def _iterations(raw: str) -> float:
    text = raw.strip().lower()
    if text == "infinite":
        return math.inf
    if not _NUMBER.fullmatch(text):
        raise _Invalid("iteration-count")
    value = float(text)
    if value < 0 or not math.isfinite(value):
        raise _Invalid("iteration-count")
    return value


def _time_value(raw: str, reason: str) -> float:
    text = raw.strip().lower()
    try:
        if text == "0":
            return 0.0
        if text.endswith("ms"):
            return _number(text[:-2], reason)
        if text.endswith("s"):
            return _number(text[:-1], reason) * 1000.0
    except _Invalid:
        raise _Invalid(reason) from None
    raise _Invalid(reason)


def _length(raw: str) -> tuple[float, str]:
    text = "".join(raw.split()).lower()
    if "!" in text:
        raise _Invalid("value")
    unit = ""
    if text.endswith("px"):
        unit = "px"
        text = text[:-2]
    elif text.endswith("%"):
        unit = "%"
        text = text[:-1]
    return _number(text, "value"), unit


def _number(raw: str, reason: str) -> float:
    text = raw.strip()
    if not _NUMBER.fullmatch(text):
        raise _Invalid(reason)
    value = float(text)
    if not math.isfinite(value):
        raise _Invalid(reason)
    return value


def _parse_easing(raw: str) -> _Ease:
    text = raw.strip().lower()
    if text == "linear":
        return _Ease("identity")
    if text == "step-start":
        return _Ease("steps", (1, "jump-start"))
    if text == "step-end":
        return _Ease("steps", (1, "jump-end"))
    if text in _CUBICS:
        return _Ease("cubic", _CUBICS[text])
    name, args = _function_call(text)
    if name == "cubic-bezier":
        return _parse_cubic(args)
    if name == "steps":
        return _parse_steps(args)
    if name == "linear":
        return _parse_linear(args)
    raise _Invalid("timing-function")


def _function_call(text: str) -> tuple[str, str]:
    if "(" not in text:
        raise _Invalid("timing-function")
    name, rest = text.split("(", 1)
    if not rest.endswith(")"):
        raise _Invalid("timing-function")
    return name.strip(), rest[:-1]


def _parse_cubic(args: str) -> _Ease:
    parts = [part.strip() for part in args.split(",")]
    if len(parts) != 4:
        raise _Invalid("cubic-bezier")
    values = tuple(_number(part, "cubic-bezier") for part in parts)
    if not 0 <= values[0] <= 1 or not 0 <= values[2] <= 1:
        raise _Invalid("cubic-bezier")
    return _Ease("cubic", values)


def _parse_steps(args: str) -> _Ease:
    parts = [part.strip() for part in args.split(",") if part.strip()]
    if len(parts) not in {1, 2}:
        raise _Invalid("steps")
    if not _INTEGER.fullmatch(parts[0]):
        raise _Invalid("steps")
    count = int(parts[0])
    position = "jump-end" if len(parts) == 1 else _JUMP.get(parts[1].lower(), "")
    if not position:
        raise _Invalid("steps")
    minimum = 2 if position == "jump-none" else 1
    if count < minimum:
        raise _Invalid("steps")
    return _Ease("steps", (count, position))


def _parse_linear(args: str) -> _Ease:
    if not args.strip():
        raise _Invalid("linear")
    points: list[tuple[float | None, float]] = []
    for arg in args.split(","):
        pieces = arg.split()
        if not pieces:
            raise _Invalid("linear")
        output = _number(pieces[0], "linear")
        if len(pieces) > 3:
            raise _Invalid("linear")
        if len(pieces) == 1:
            points.append((None, output))
            continue
        for percent in pieces[1:]:
            if not percent.endswith("%"):
                raise _Invalid("linear")
            points.append((_number(percent[:-1], "linear") / 100.0, output))
    return _Ease("linear", _canonicalize_linear(points))


def _canonicalize_linear(points: list[tuple[float | None, float]]) -> list[tuple[float, float]]:
    if points[0][0] is None:
        points[0] = (0.0, points[0][1])
    if points[-1][0] is None:
        points[-1] = (1.0, points[-1][1])
    ceiling: float | None = None
    for index, (progress, output) in enumerate(points):
        if progress is None:
            continue
        if ceiling is not None and progress < ceiling:
            progress = ceiling
        ceiling = progress
        points[index] = (progress, output)
    index = 0
    while index < len(points):
        if points[index][0] is not None:
            index += 1
            continue
        end = index
        while end < len(points) and points[end][0] is None:
            end += 1
        left = points[index - 1][0]
        right = points[end][0]
        assert left is not None and right is not None
        missing = end - index
        for step in range(missing):
            progress = left + (step + 1) / (missing + 1) * (right - left)
            points[index + step] = (progress, points[index + step][1])
        index = end
    return [(float(progress), output) for progress, output in points]


def _extract_keyframes(text: str) -> tuple[dict[str, list[tuple[float, dict[str, str]]]], str]:
    found: dict[str, list[tuple[float, dict[str, str]]]] = {}
    pieces: list[str] = []
    cursor = 0
    lowered = text.lower()
    while True:
        start = lowered.find("@keyframes", cursor)
        if start < 0:
            pieces.append(text[cursor:])
            break
        pieces.append(text[cursor:start])
        name, name_end = _read_keyframes_name(text, start + len("@keyframes"))
        brace = text.find("{", name_end)
        if brace < 0:
            raise _Invalid("brace")
        if text[name_end:brace].strip():
            raise _Invalid("keyframes")
        body, cursor = _brace_block(text, brace)
        found[name] = _keyframe_rules(body)
    return found, "".join(pieces)


def _read_keyframes_name(text: str, index: int) -> tuple[str, int]:
    while index < len(text) and text[index].isspace():
        index += 1
    if index >= len(text):
        raise _Invalid("keyframes")
    if text[index] in {"'", '"'}:
        quote = text[index]
        end = text.find(quote, index + 1)
        if end < 0 or not text[index + 1 : end]:
            raise _Invalid("keyframes")
        return text[index + 1 : end], end + 1
    match = _IDENT.match(text, index)
    if match is None:
        raise _Invalid("keyframes")
    name = match.group(0)
    if name.lower() in _RESERVED_NAMES:
        raise _Invalid("keyframes")
    return name, match.end()


def _keyframe_rules(body: str) -> list[tuple[float, dict[str, str]]]:
    rules: list[tuple[float, dict[str, str]]] = []
    for selector, declarations in _rule_list(body):
        offsets = _offsets(selector)
        mapped = _declaration_map(declarations)
        for offset in offsets:
            rules.append((offset, mapped))
    return rules


def _offsets(selector: str) -> list[float]:
    offsets: list[float] = []
    for piece in selector.split(","):
        token = piece.strip().lower()
        if token in {"from", "to"}:
            offsets.append(0.0 if token == "from" else 1.0)
            continue
        if not token.endswith("%"):
            raise _Invalid("offset")
        number = _number(token[:-1], "offset")
        if number < 0 or number > 100:
            raise _Invalid("offset")
        offsets.append(number / 100.0)
    if not offsets:
        raise _Invalid("offset")
    return offsets


def _style_bodies(text: str) -> list[str]:
    bodies: list[str] = []
    for selector, body in _rule_list(text):
        if selector.strip().startswith("@"):
            raise _Invalid("at-rule")
        bodies.append(body)
    return bodies


def _rule_list(text: str) -> list[tuple[str, str]]:
    rules: list[tuple[str, str]] = []
    index = 0
    length = len(text)
    while index < length:
        while index < length and text[index].isspace():
            index += 1
        if index >= length:
            break
        brace = text.find("{", index)
        if brace < 0:
            if text[index:].strip():
                raise _Invalid("brace")
            break
        body, end = _brace_block(text, brace)
        rules.append((text[index:brace], body))
        index = end
    return rules


def _brace_block(text: str, open_index: int) -> tuple[str, int]:
    depth = 0
    for index in range(open_index, len(text)):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[open_index + 1 : index], index + 1
    raise _Invalid("brace")


def _declaration_map(body: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for part in body.split(";"):
        if not part.strip():
            continue
        if ":" not in part:
            raise _Invalid("declaration")
        name, value = part.split(":", 1)
        key = name.strip().lower()
        if not key or not value.strip():
            raise _Invalid("declaration")
        found[key] = value.strip()
    return found


def _strip_comments(text: str) -> str:
    return re.sub(r"/\*.*?\*/", "", text, flags=re.S)


def _invalid(reason: str) -> dict[str, object]:
    return {
        "outcome": "invalid",
        "applying": False,
        "value": None,
        "unit": "",
        "text": "",
        "reason": reason,
    }


def _idle(value: float, unit: str, reason: str) -> dict[str, object]:
    return {
        "outcome": "idle",
        "applying": False,
        "value": value,
        "unit": unit,
        "text": _format_value(value, unit),
        "reason": reason,
    }


def _sampled(value: float, unit: str) -> dict[str, object]:
    return {
        "outcome": "sampled",
        "applying": True,
        "value": value,
        "unit": unit,
        "text": _format_value(value, unit),
        "reason": "",
    }


def _format_value(value: float, unit: str) -> str:
    if math.isfinite(value) and value == math.trunc(value):
        rendered = str(int(value))
    else:
        rendered = f"{value:.6f}".rstrip("0").rstrip(".")
    return f"{rendered}{unit}"
