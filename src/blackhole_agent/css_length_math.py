"""Resolve CSS math functions to a used length.

CSS Values and Units Level 4. ``calc()``, ``min()``, ``max()``, and
``clamp()`` are a length-percentage. Percentages stay symbolic until a
definite basis resolves them. ``clamp(MIN, VAL, MAX)`` is
``max(MIN, min(VAL, MAX))``, so a lower bound above the upper bound wins.

``+`` and ``-`` are operators only when whitespace surrounds them. ``*`` and
``/`` bind tighter and do not need whitespace. A bare number is not a length,
including a unitless zero. Two lengths cannot be multiplied. A top-level
non-finite result is invalid. ``min()`` still absorbs ``+infinity``, so
``min(10px, 10px / 0)`` is 10px.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

_MAX_DEPTH = 64
_CONSTANTS = {
    "e": math.e,
    "pi": math.pi,
    "infinity": math.inf,
    "-infinity": -math.inf,
    "nan": math.nan,
}
_FUNCTIONS = frozenset({"calc", "min", "max", "clamp"})
_MATH_START = re.compile(r"(?i)\s*(calc|min|max|clamp)\(")


class _Invalid(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class _Num:
    value: float


@dataclass(frozen=True)
class _Len:
    px: float
    pct: float
    px_set: bool
    pct_set: bool


_Node = _Num | _Len


def is_length_math(expression: object) -> bool:
    """True when the whole token starts with a CSS math function."""

    return isinstance(expression, str) and _MATH_START.match(expression) is not None


def resolve_length_math(
    expression: object,
    *,
    percentage_basis: object,
    allow_percentage: bool = True,
) -> dict[str, object]:
    """Resolve one math function to pixels.

    ``percentage_basis`` is the definite length a percentage refers to.
    ``allow_percentage`` is false for properties that reject percentages,
    even when a percentage loses a ``min()`` or ``max()``.
    """

    try:
        px = _resolve(expression, percentage_basis, allow_percentage=allow_percentage)
    except _Invalid as exc:
        return {"outcome": "invalid", "px": None, "reason": exc.reason}
    return {"outcome": "resolved", "px": _number(px), "reason": None}


def _resolve(expression: object, percentage_basis: object, *, allow_percentage: bool) -> float:
    if not isinstance(expression, str) or isinstance(percentage_basis, bool):
        raise _Invalid("math is invalid")
    if not isinstance(percentage_basis, (int, float)):
        raise _Invalid("basis")
    basis = float(percentage_basis)
    if basis < 0 or not math.isfinite(basis):
        raise _Invalid("basis")
    node = _parse(expression, basis)
    if not isinstance(node, _Len):
        raise _Invalid("type")
    if node.pct_set and not allow_percentage:
        raise _Invalid("percentage")
    px = node.px + node.pct * basis / 100.0
    if not math.isfinite(px):
        raise _Invalid("non-finite")
    return px


def _parse(expression: str, basis: float) -> _Node:
    tokens = _tokenize(_comments_to_space(expression))
    parser = _Parser(tokens, basis)
    if parser.peek() is None or parser.peek()[0] != "fn":
        raise _Invalid("math is invalid")
    node = parser.parse_fn(0)
    if parser.peek() is not None:
        raise _Invalid("math is invalid")
    return node


def _comments_to_space(text: str) -> str:
    pieces: list[str] = []
    index = 0
    while index < len(text):
        if text.startswith("/*", index):
            end = text.find("*/", index + 2)
            if end < 0:
                raise _Invalid("unclosed comment")
            pieces.append(" ")
            index = end + 2
            continue
        pieces.append(text[index])
        index += 1
    return "".join(pieces)


def _tokenize(text: str) -> list[tuple[str, object]]:
    tokens: list[tuple[str, object]] = []
    index = 0
    size = len(text)
    while index < size:
        char = text[index]
        if char.isspace():
            index += 1
            continue
        if char in "*/":
            tokens.append(("op", char))
            index += 1
            continue
        if char in "+-" and _binary_sign(text, index):
            tokens.append(("op", char))
            index += 1
            continue
        number_end = _number_end(text, index)
        if number_end is not None:
            number = float(text[index:number_end])
            if number_end < size and text[number_end] == "%":
                tokens.append(("pct", number))
                index = number_end + 1
                continue
            if number_end < size and (text[number_end].isalpha() or text[number_end] == "_"):
                unit_end, unit = _ident_at(text, number_end)
                if unit != "px":
                    raise _Invalid("unit")
                tokens.append(("len", number))
                index = unit_end
                continue
            tokens.append(("num", number))
            index = number_end
            continue
        ident = _ident_at(text, index)
        if ident is not None:
            end, name = ident
            if end < size and text[end] == "(":
                if name not in _FUNCTIONS:
                    raise _Invalid("math is invalid")
                tokens.append(("fn", name))
                index = end
                continue
            if name not in _CONSTANTS:
                raise _Invalid("math is invalid")
            tokens.append(("num", _CONSTANTS[name]))
            index = end
            continue
        if char == "(":
            tokens.append(("lp", "("))
            index += 1
            continue
        if char == ")":
            tokens.append(("rp", ")"))
            index += 1
            continue
        if char == ",":
            tokens.append(("comma", ","))
            index += 1
            continue
        raise _Invalid("math is invalid")
    return tokens


def _binary_sign(text: str, index: int) -> bool:
    return index > 0 and text[index - 1].isspace() and index + 1 < len(text) and text[index + 1].isspace()


def _number_end(text: str, index: int) -> int | None:
    size = len(text)
    cursor = index
    if text[cursor] in "+-":
        cursor += 1
        if cursor >= size:
            return None
    saw_digit = False
    while cursor < size and text[cursor].isdigit():
        saw_digit = True
        cursor += 1
    if cursor < size and text[cursor] == ".":
        cursor += 1
        while cursor < size and text[cursor].isdigit():
            saw_digit = True
            cursor += 1
    if not saw_digit:
        return None
    if cursor < size and text[cursor] in "eE":
        exponent = cursor + 1
        if exponent < size and text[exponent] in "+-":
            exponent += 1
        digit_end = exponent
        while digit_end < size and text[digit_end].isdigit():
            digit_end += 1
        if digit_end > exponent:
            cursor = digit_end
    return cursor


def _ident_at(text: str, index: int) -> tuple[int, str] | None:
    size = len(text)
    cursor = index
    if text[cursor] == "-":
        cursor += 1
        if cursor >= size or not (text[cursor].isalpha() or text[cursor] == "_"):
            return None
    elif not (text[cursor].isalpha() or text[cursor] == "_"):
        return None
    cursor += 1
    while cursor < size and (text[cursor].isalnum() or text[cursor] in "_-"):
        cursor += 1
    return cursor, text[index:cursor].lower()


class _Parser:
    def __init__(self, tokens: list[tuple[str, object]], basis: float) -> None:
        self.tokens = tokens
        self.basis = basis
        self.index = 0

    def peek(self) -> tuple[str, object] | None:
        if self.index >= len(self.tokens):
            return None
        return self.tokens[self.index]

    def take(self, kind: str | None = None, value: object | None = None) -> tuple[str, object]:
        token = self.peek()
        if token is None or (kind is not None and token[0] != kind) or (value is not None and token[1] != value):
            raise _Invalid("math is invalid")
        self.index += 1
        return token

    def parse_fn(self, depth: int) -> _Node:
        name = self.take("fn")[1]
        self.take("lp")
        if name == "calc":
            node = self.parse_sum(depth + 1)
            self.take("rp")
            return node
        if name in {"min", "max"}:
            args = [self.parse_sum(depth + 1)]
            while self.peek() == ("comma", ","):
                self.take("comma")
                args.append(self.parse_sum(depth + 1))
            self.take("rp")
            return _extremum(str(name), args, self.basis)
        if name == "clamp":
            low = self.parse_sum(depth + 1)
            self.take("comma")
            value = self.parse_sum(depth + 1)
            self.take("comma")
            high = self.parse_sum(depth + 1)
            if self.peek() == ("comma", ","):
                raise _Invalid("math is invalid")
            self.take("rp")
            return _extremum("max", [low, _extremum("min", [value, high], self.basis)], self.basis)
        raise _Invalid("math is invalid")

    def parse_sum(self, depth: int) -> _Node:
        if depth > _MAX_DEPTH:
            raise _Invalid("depth")
        left = self.parse_product(depth)
        while self.peek() is not None and self.peek()[0] == "op" and self.peek()[1] in {"+", "-"}:
            sign = -1.0 if self.take("op")[1] == "-" else 1.0
            right = self.parse_product(depth)
            left = _add(left, right, sign)
        return left

    def parse_product(self, depth: int) -> _Node:
        left = self.parse_value(depth)
        while self.peek() is not None and self.peek()[0] == "op" and self.peek()[1] in {"*", "/"}:
            operator = self.take("op")[1]
            right = self.parse_value(depth)
            left = _multiply(left, right) if operator == "*" else _divide(left, right)
        return left

    def parse_value(self, depth: int) -> _Node:
        if depth > _MAX_DEPTH:
            raise _Invalid("depth")
        token = self.peek()
        if token is None:
            raise _Invalid("math is invalid")
        if token[0] == "fn":
            return self.parse_fn(depth + 1)
        if token[0] == "lp":
            self.take("lp")
            node = self.parse_sum(depth + 1)
            self.take("rp")
            return node
        if token[0] == "num":
            self.take("num")
            return _Num(_token_float(token[1]))
        if token[0] == "len":
            self.take("len")
            return _Len(_token_float(token[1]), 0.0, True, False)
        if token[0] == "pct":
            self.take("pct")
            return _Len(0.0, _token_float(token[1]), False, True)
        raise _Invalid("math is invalid")


def _token_float(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _Invalid("math is invalid")
    return float(value)


def _add(left: _Node, right: _Node, sign: float) -> _Node:
    if isinstance(left, _Num) and isinstance(right, _Num):
        return _Num(left.value + sign * right.value)
    if isinstance(left, _Len) and isinstance(right, _Len):
        return _Len(
            left.px + sign * right.px,
            left.pct + sign * right.pct,
            left.px_set or right.px_set,
            left.pct_set or right.pct_set,
        )
    raise _Invalid("type")


def _multiply(left: _Node, right: _Node) -> _Node:
    if isinstance(left, _Num) and isinstance(right, _Num):
        return _Num(left.value * right.value)
    if isinstance(left, _Num) and isinstance(right, _Len):
        return _scale(right, left.value)
    if isinstance(left, _Len) and isinstance(right, _Num):
        return _scale(left, right.value)
    raise _Invalid("type")


def _divide(left: _Node, right: _Node) -> _Node:
    if not isinstance(right, _Num):
        raise _Invalid("type")
    if isinstance(left, _Num):
        return _Num(_divide_number(left.value, right.value))
    if isinstance(left, _Len):
        return _Len(
            _divide_component(left.px, left.px_set, right.value),
            _divide_component(left.pct, left.pct_set, right.value),
            left.px_set,
            left.pct_set,
        )
    raise _Invalid("type")


def _scale(length: _Len, factor: float) -> _Len:
    return _Len(length.px * factor, length.pct * factor, length.px_set, length.pct_set)


def _divide_number(numer: float, denom: float) -> float:
    if math.isnan(numer) or math.isnan(denom):
        return math.nan
    if denom == 0:
        if numer == 0:
            return math.nan
        return math.copysign(math.inf, numer * math.copysign(1.0, denom))
    return numer / denom


def _divide_component(value: float, present: bool, denom: float) -> float:
    if not present:
        return 0.0
    return _divide_number(value, denom)


def _extremum(name: str, args: list[_Node], basis: float) -> _Node:
    if all(isinstance(arg, _Num) for arg in args):
        numbers = [arg.value for arg in args if isinstance(arg, _Num)]
        return _Num(_pick(numbers, name))
    if not all(isinstance(arg, _Len) for arg in args):
        raise _Invalid("type")
    lengths = [arg for arg in args if isinstance(arg, _Len)]
    picked = _pick([arg.px + arg.pct * basis / 100.0 for arg in lengths], name)
    return _Len(picked, 0.0, True, any(arg.pct_set for arg in lengths))


def _pick(values: list[float], name: str) -> float:
    if any(math.isnan(value) for value in values):
        return math.nan
    return min(values) if name == "min" else max(values)


def _number(value: float) -> int | float:
    nearest = round(value)
    if abs(value - nearest) <= 1e-9:
        return int(nearest)
    return value
