"""Rewrite one CSS color with relative color syntax.

CSS Color 5 converts the origin into the relative color's space, then each
channel is a literal, ``none``, a channel keyword, or a math function over
those keywords. A bare keyword keeps a missing component. Math treats a
missing keyword as zero. The keyword's number is the resolved channel, so
``rgb()`` keywords run from 0 to 255 while ``color(srgb)`` keywords run from
0 to 1, and a hue keyword is degrees in ``[0, 360)``. ``calc()`` does not
wrap a hue back into that range. Alpha is clamped to ``[0, 1]``. Color
channels are not clamped, so an out-of-gamut result stays out of gamut.

``alpha()`` changes only the origin's alpha and keeps its color space. A
relative ``color()`` is limited to the spaces the mixer can convert:
``srgb``, ``srgb-linear``, ``xyz``, ``xyz-d65``, and ``xyz-d50``. ``var()``,
``currentcolor``, legacy commas, and an absolute color are rejected.
``color-mix()`` can be an origin. It still does not accept a relative color
as one of its inputs.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from blackhole_agent.css_color_mix import _Color, _Invalid, _convert, _parse_color

_EXTRA_NAMED = {
    "darkblue": (0, 0, 139),
    "indianred": (205, 92, 92),
    "lightseagreen": (32, 178, 170),
}
_SPACE_ALIAS = {"xyz": "xyz-d65"}
_EXPLICIT_CHANNELS = {
    "srgb": ("r", "g", "b"),
    "srgb-linear": ("r", "g", "b"),
    "xyz": ("x", "y", "z"),
    "xyz-d65": ("x", "y", "z"),
    "xyz-d50": ("x", "y", "z"),
}
_WS = frozenset(" \t\n\r\f")
_ANGLE = {"deg": 1.0, "turn": 360.0, "rad": 180.0 / math.pi, "grad": 0.9}
_CONSTANTS = {"e": math.e, "pi": math.pi, "infinity": math.inf, "nan": math.nan}
_MATH = frozenset({"calc", "min", "max", "clamp"})
_MAX_DEPTH = 16


class _Bad(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class _Slot:
    percent_of: float | None
    number_scale: float
    hue: bool = False
    clamp: bool = False

    def finish(self, declared: float) -> float:
        if not math.isfinite(declared):
            raise _Bad("math")
        value = declared / self.number_scale
        if not self.clamp:
            return value
        if value < 0:
            return 0.0
        if value > 1:
            return 1.0
        return value


_RGB = _Slot(255.0, 255.0)
_HUE = _Slot(None, 1.0, hue=True)
_ALPHA = _Slot(1.0, 1.0, clamp=True)
_UNIT = _Slot(1.0, 1.0)
_HUNDRED = _Slot(100.0, 1.0)
_LAB_AB = _Slot(125.0, 1.0)
_LCH_C = _Slot(150.0, 1.0)
_OK_AB = _Slot(0.4, 1.0)


@dataclass(frozen=True)
class _Form:
    space: str
    names: tuple[str, str, str]
    slots: tuple[_Slot, _Slot, _Slot]
    rgb_bytes: bool


def _form(
    space: str,
    names: tuple[str, str, str],
    slots: tuple[_Slot, _Slot, _Slot],
    *,
    rgb_bytes: bool = False,
) -> _Form:
    return _Form(space, names, slots, rgb_bytes)


_FORMS = {
    "rgb": _form("srgb", ("r", "g", "b"), (_RGB, _RGB, _RGB), rgb_bytes=True),
    "rgba": _form("srgb", ("r", "g", "b"), (_RGB, _RGB, _RGB), rgb_bytes=True),
    "hsl": _form("hsl", ("h", "s", "l"), (_HUE, _HUNDRED, _HUNDRED)),
    "hsla": _form("hsl", ("h", "s", "l"), (_HUE, _HUNDRED, _HUNDRED)),
    "hwb": _form("hwb", ("h", "w", "b"), (_HUE, _HUNDRED, _HUNDRED)),
    "lab": _form("lab", ("l", "a", "b"), (_HUNDRED, _LAB_AB, _LAB_AB)),
    "lch": _form("lch", ("l", "c", "h"), (_HUNDRED, _LCH_C, _HUE)),
    "oklab": _form("oklab", ("l", "a", "b"), (_UNIT, _OK_AB, _OK_AB)),
    "oklch": _form("oklch", ("l", "c", "h"), (_UNIT, _OK_AB, _HUE)),
}


def resolve_relative_color(expression: str) -> dict[str, object]:
    """Return the color produced by one relative color expression.

    ``outcome`` is ``resolved`` or ``invalid``. ``components`` use the same
    channel scale as ``mix_color``: ``rgb()`` numbers are divided by 255,
    and a missing component is ``None``.
    """

    if not isinstance(expression, str):
        raise TypeError("relative color expression must be a string")
    try:
        return _resolve(expression, 0)
    except _Bad as exc:
        return _invalid(exc.reason)


def _resolve(expression: str, depth: int) -> dict[str, object]:
    if depth > _MAX_DEPTH:
        raise _Bad("syntax")
    text = _strip_comments(expression).strip()
    name, body = _split_call(text)
    if not _starts_keyword(body, "from"):
        raise _Bad("syntax")
    rest = body[_skip(body, 0) + len("from") :]
    if name == "alpha":
        return _resolve_alpha(rest, depth)
    if name == "color":
        return _resolve_explicit(rest, depth)
    form = _FORMS.get(name)
    if form is None:
        raise _Bad("syntax")
    origin_text, index = _read_color(rest, 0)
    channels, alpha_text, end = _read_channels(rest, index)
    if end != len(rest):
        raise _Bad("syntax")
    if len(channels) != 3:
        raise _Bad("syntax")
    origin = _convert(_origin_color(origin_text, depth), form.space)
    keywords = _keywords(origin, form.names, form.slots, rgb_bytes=form.rgb_bytes)
    produced = [_eval_slot(channels[index], form.slots[index], keywords) for index in range(3)]
    alpha = origin.alpha if alpha_text is None else _eval_slot(alpha_text, _ALPHA, keywords)
    return _resolved(form.space, produced, _clamp_alpha(alpha))


def _resolve_alpha(rest: str, depth: int) -> dict[str, object]:
    origin_text, index = _read_color(rest, 0)
    index = _skip(rest, index)
    if index >= len(rest) or rest[index] != "/":
        raise _Bad("syntax")
    alpha_text = rest[index + 1 :].strip()
    if not alpha_text:
        raise _Bad("syntax")
    origin = _origin_color(origin_text, depth)
    keywords = _keywords(origin, ("", "", ""), (_UNIT, _UNIT, _UNIT), rgb_bytes=False)
    keywords = {"alpha": keywords["alpha"]}
    alpha = _eval_slot(alpha_text, _ALPHA, keywords)
    return _resolved(origin.space, list(origin.channels), alpha)


def _resolve_explicit(rest: str, depth: int) -> dict[str, object]:
    origin_text, index = _read_color(rest, 0)
    index = _skip(rest, index)
    if index >= len(rest) or not _ident_at(rest, index):
        raise _Bad("syntax")
    space_token, index = _read_ident(rest, index)
    space_name = space_token.lower()
    names = _EXPLICIT_CHANNELS.get(space_name)
    if names is None:
        raise _Bad("space")
    channels, alpha_text, end = _read_channels(rest, index)
    if end != len(rest) or len(channels) != 3:
        raise _Bad("syntax")
    space = _SPACE_ALIAS.get(space_name, space_name)
    origin = _convert(_origin_color(origin_text, depth), space)
    keywords = _keywords(origin, names, (_UNIT, _UNIT, _UNIT), rgb_bytes=False)
    produced = [_eval_slot(channels[index], _UNIT, keywords) for index in range(3)]
    alpha = origin.alpha if alpha_text is None else _eval_slot(alpha_text, _ALPHA, keywords)
    return _resolved(space, produced, _clamp_alpha(alpha))


def _origin_color(text: str, depth: int) -> _Color:
    raw = text.strip()
    if _looks_relative(raw):
        resolved = _resolve(raw, depth + 1)
        components = resolved["components"]
        if not isinstance(components, list):
            raise _Bad("color")
        alpha = resolved["alpha"]
        stored = alpha if alpha is None or isinstance(alpha, (int, float)) else None
        return _Color(str(resolved["space"]), list(components), stored)
    lowered = raw.lower()
    if lowered in _EXTRA_NAMED:
        red, green, blue = _EXTRA_NAMED[lowered]
        return _Color("srgb", [red / 255, green / 255, blue / 255], 1.0)
    try:
        return _parse_color(raw)
    except (_Invalid, ValueError, TypeError) as exc:
        raise _Bad("color") from exc


def _looks_relative(text: str) -> bool:
    try:
        _name, body = _split_call(text.strip())
    except _Bad:
        return False
    return _starts_keyword(body, "from")


def _keywords(
    color: _Color,
    names: tuple[str, str, str],
    slots: tuple[_Slot, _Slot, _Slot],
    *,
    rgb_bytes: bool,
) -> dict[str, float | None]:
    values: dict[str, float | None] = {}
    for index, name in enumerate(names):
        if not name:
            continue
        raw = color.channels[index]
        if raw is None:
            values[name] = None
        elif slots[index].hue:
            values[name] = raw % 360.0
        elif rgb_bytes:
            values[name] = raw * 255.0
        else:
            values[name] = float(raw)
    values["alpha"] = None if color.alpha is None else float(color.alpha)
    return values


def _eval_slot(text: str, slot: _Slot, keywords: dict[str, float | None]) -> float | None:
    raw = text.strip()
    if not raw:
        raise _Bad("syntax")
    lowered = raw.lower()
    if lowered == "none":
        return None
    ident = _single_ident(raw)
    if ident is not None and ident.lower() in keywords:
        value = keywords[ident.lower()]
        if value is None:
            return None
        return slot.finish(value)
    if _math_call(raw):
        return slot.finish(_Math(raw, keywords, slot).value())
    return slot.finish(_literal(raw, slot))


def _literal(text: str, slot: _Slot) -> float:
    lowered = text.lower()
    if lowered.endswith("%"):
        if slot.percent_of is None:
            raise _Bad("syntax")
        try:
            number = float(lowered[:-1])
        except ValueError as exc:
            raise _Bad("syntax") from exc
        if not math.isfinite(number):
            raise _Bad("math")
        return number / 100.0 * slot.percent_of
    for suffix, scale in _ANGLE.items():
        if lowered.endswith(suffix) and len(lowered) > len(suffix):
            if not slot.hue:
                raise _Bad("syntax")
            try:
                number = float(lowered[: -len(suffix)])
            except ValueError as exc:
                raise _Bad("syntax") from exc
            if not math.isfinite(number):
                raise _Bad("math")
            return number * scale
    try:
        number = float(lowered)
    except ValueError as exc:
        raise _Bad("syntax") from exc
    if not math.isfinite(number):
        raise _Bad("math")
    return number


def _clamp_alpha(alpha: float | None) -> float | None:
    if alpha is None:
        return None
    if alpha < 0:
        return 0.0
    if alpha > 1:
        return 1.0
    return float(alpha)


class _Math:
    def __init__(self, text: str, keywords: dict[str, float | None], slot: _Slot) -> None:
        self.text = text
        self.n = len(text)
        self.i = 0
        self.keywords = keywords
        self.slot = slot

    def value(self) -> float:
        parsed = self._expression()
        self._skip()
        if self.i != self.n or not math.isfinite(parsed):
            raise _Bad("math" if self.i == self.n else "syntax")
        return parsed

    def _expression(self) -> float:
        left = self._term()
        while True:
            op = self._spaced_add()
            if op is None:
                return left
            right = self._term()
            left = left + right if op == "+" else left - right
            if not math.isfinite(left):
                raise _Bad("math")

    def _term(self) -> float:
        left = self._unary()
        while True:
            mark = self.i
            self._skip()
            if self.i < self.n and self.text[self.i] in "*/":
                op = self.text[self.i]
                self.i += 1
                right = self._unary()
                if op == "*":
                    left *= right
                elif right == 0:
                    raise _Bad("math")
                else:
                    left /= right
                if not math.isfinite(left):
                    raise _Bad("math")
            else:
                self.i = mark
                return left

    def _unary(self) -> float:
        self._skip()
        if self.i < self.n and self.text[self.i] in "+-":
            op = self.text[self.i]
            self.i += 1
            value = self._unary()
            return value if op == "+" else -value
        return self._primary()

    def _primary(self) -> float:
        self._skip()
        if self.i >= self.n:
            raise _Bad("syntax")
        if self.text[self.i] == "(":
            self.i += 1
            value = self._expression()
            self._skip()
            if self.i >= self.n or self.text[self.i] != ")":
                raise _Bad("syntax")
            self.i += 1
            return value
        if _ident_at(self.text, self.i):
            name = self._ident()
            if self.i < self.n and self.text[self.i] == "(":
                self.i += 1
                return self._call(name)
            return self._name(name)
        return self._number()

    def _call(self, name: str) -> float:
        lowered = name.lower()
        if lowered == "calc":
            value = self._expression()
            self._close()
            return value
        if lowered in {"min", "max"}:
            args = self._arguments()
            if not args:
                raise _Bad("syntax")
            return min(args) if lowered == "min" else max(args)
        if lowered == "clamp":
            args = self._arguments()
            if len(args) != 3:
                raise _Bad("syntax")
            return max(args[0], min(args[1], args[2]))
        raise _Bad("syntax")

    def _arguments(self) -> list[float]:
        values = [self._expression()]
        while True:
            self._skip()
            if self.i < self.n and self.text[self.i] == ",":
                self.i += 1
                values.append(self._expression())
                continue
            self._close()
            return values

    def _close(self) -> None:
        self._skip()
        if self.i >= self.n or self.text[self.i] != ")":
            raise _Bad("syntax")
        self.i += 1

    def _name(self, name: str) -> float:
        lowered = name.lower()
        if lowered in _CONSTANTS:
            return _CONSTANTS[lowered]
        if lowered not in self.keywords:
            raise _Bad("syntax")
        value = self.keywords[lowered]
        return 0.0 if value is None else float(value)

    def _number(self) -> float:
        start = self.i
        if self.text[self.i] == ".":
            self.i += 1
            if self.i >= self.n or not self.text[self.i].isdigit():
                raise _Bad("syntax")
        elif not self.text[self.i].isdigit():
            raise _Bad("syntax")
        while self.i < self.n and self.text[self.i].isdigit():
            self.i += 1
        if start < self.n and self.text[start] != "." and self.i < self.n and self.text[self.i] == ".":
            self.i += 1
            while self.i < self.n and self.text[self.i].isdigit():
                self.i += 1
        try:
            value = float(self.text[start : self.i])
        except ValueError as exc:
            raise _Bad("syntax") from exc
        if self.i < self.n and self.text[self.i] == "%":
            self.i += 1
            if self.slot.percent_of is None:
                raise _Bad("syntax")
            return value / 100.0 * self.slot.percent_of
        if self.i < self.n and (self.text[self.i].isalpha() or self.text[self.i] == "_"):
            unit = self._ident().lower()
            scale = _ANGLE.get(unit)
            if scale is None or not self.slot.hue:
                raise _Bad("syntax")
            return value * scale
        return value

    def _ident(self) -> str:
        name, self.i = _read_ident(self.text, self.i)
        return name

    def _spaced_add(self) -> str | None:
        mark = self.i
        if not self._has_space():
            return None
        self._skip()
        if self.i >= self.n or self.text[self.i] not in "+-":
            self.i = mark
            return None
        op = self.text[self.i]
        after = self.i + 1
        if after >= self.n or self.text[after] not in _WS:
            self.i = mark
            return None
        self.i = after
        return op

    def _has_space(self) -> bool:
        return self.i < self.n and self.text[self.i] in _WS

    def _skip(self) -> None:
        while self.i < self.n and self.text[self.i] in _WS:
            self.i += 1


def _read_channels(text: str, index: int) -> tuple[list[str], str | None, int]:
    channels: list[str] = []
    while len(channels) < 3:
        index = _skip(text, index)
        if index >= len(text) or text[index] == "/":
            break
        if text[index] == ",":
            raise _Bad("syntax")
        channel, index = _read_component(text, index)
        channels.append(channel)
    index = _skip(text, index)
    if index < len(text) and text[index] == ",":
        raise _Bad("syntax")
    alpha = None
    if index < len(text) and text[index] == "/":
        alpha = text[index + 1 :].strip()
        if not alpha:
            raise _Bad("syntax")
        index = len(text)
    return channels, alpha, index


def _read_component(text: str, index: int) -> tuple[str, int]:
    if _ident_at(text, index):
        _name, after = _read_ident(text, index)
        if after < len(text) and text[after] == "(":
            end = _matching_paren(text, after)
            return text[index:end], end
        return text[index:after], after
    start = index
    if text[index] in "+-":
        index += 1
        if index >= len(text) or not (text[index].isdigit() or text[index] == "."):
            raise _Bad("syntax")
    if index >= len(text) or not (text[index].isdigit() or text[index] == "."):
        raise _Bad("syntax")
    if text[index] == ".":
        index += 1
        if index >= len(text) or not text[index].isdigit():
            raise _Bad("syntax")
    while index < len(text) and text[index].isdigit():
        index += 1
    if index < len(text) and text[index] == "." and text[start : index].count(".") == 0:
        index += 1
        while index < len(text) and text[index].isdigit():
            index += 1
    if index < len(text) and text[index] == "%":
        return text[start : index + 1], index + 1
    if index < len(text) and (text[index].isalpha() or text[index] == "_"):
        _unit, index = _read_ident(text, index)
    return text[start:index], index


def _read_color(text: str, index: int) -> tuple[str, int]:
    index = _skip(text, index)
    if index >= len(text):
        raise _Bad("syntax")
    if text[index] == "#":
        end = index + 1
        while end < len(text) and text[end] in "0123456789abcdefABCDEF":
            end += 1
        if end == index + 1:
            raise _Bad("color")
        return text[index:end], end
    if not _ident_at(text, index):
        raise _Bad("color")
    _name, end = _read_ident(text, index)
    if end < len(text) and text[end] == "(":
        end = _matching_paren(text, end)
    return text[index:end], end


def _split_call(text: str) -> tuple[str, str]:
    index = _skip(text, 0)
    if not _ident_at(text, index):
        raise _Bad("syntax")
    name, index = _read_ident(text, index)
    if index >= len(text) or text[index] != "(":
        raise _Bad("syntax")
    end = _matching_paren(text, index)
    if _skip(text, end) != len(text):
        raise _Bad("syntax")
    return name.lower(), text[index + 1 : end - 1]


def _starts_keyword(text: str, word: str) -> bool:
    index = _skip(text, 0)
    if not text.lower().startswith(word, index):
        return False
    after = index + len(word)
    return after >= len(text) or not (text[after].isalnum() or text[after] in "-_")


def _math_call(text: str) -> bool:
    ident = _single_ident_prefix(text)
    return ident is not None and ident.lower() in _MATH and text[len(ident) :].startswith("(")


def _single_ident(text: str) -> str | None:
    if not text or not _ident_at(text, 0):
        return None
    name, index = _read_ident(text, 0)
    if index != len(text):
        return None
    return name


def _single_ident_prefix(text: str) -> str | None:
    if not _ident_at(text, 0):
        return None
    name, index = _read_ident(text, 0)
    return name if index > 0 else None


def _strip_comments(text: str) -> str:
    pieces: list[str] = []
    index = 0
    while index < len(text):
        if text.startswith("/*", index):
            end = text.find("*/", index + 2)
            if end < 0:
                raise _Bad("syntax")
            pieces.append(" ")
            index = end + 2
        else:
            pieces.append(text[index])
            index += 1
    return "".join(pieces)


def _matching_paren(text: str, open_index: int) -> int:
    depth = 0
    index = open_index
    while index < len(text):
        char = text[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    raise _Bad("syntax")


def _read_ident(text: str, index: int) -> tuple[str, int]:
    start = index
    if text[index] == "-":
        index += 1
    if index >= len(text) or not (text[index].isalpha() or text[index] == "_"):
        raise _Bad("syntax")
    index += 1
    while index < len(text) and (text[index].isalnum() or text[index] in "-_"):
        index += 1
    return text[start:index], index


def _ident_at(text: str, index: int) -> bool:
    if index >= len(text):
        return False
    char = text[index]
    if char.isalpha() or char == "_":
        return True
    return char == "-" and index + 1 < len(text) and (text[index + 1].isalpha() or text[index + 1] == "_")


def _skip(text: str, index: int) -> int:
    while index < len(text) and text[index] in _WS:
        index += 1
    return index


def _resolved(space: str, channels: list[float | None], alpha: float | None) -> dict[str, object]:
    return {
        "outcome": "resolved",
        "space": space,
        "components": [_public(channel) for channel in channels],
        "alpha": _public(alpha),
        "reason": "",
    }


def _invalid(reason: str) -> dict[str, object]:
    return {
        "outcome": "invalid",
        "space": "",
        "components": [],
        "alpha": None,
        "reason": reason,
    }


def _public(value: float | None) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        return None
    number = float(value)
    if number == 0:
        return 0
    nearest = round(number)
    if abs(number - nearest) <= 1e-10:
        return int(nearest)
    return number
