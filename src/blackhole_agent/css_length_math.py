"""Resolve CSS math functions to a used length.

CSS Values and Units Level 4. ``calc()``, ``min()``, ``max()``, and
``clamp()`` are a length-percentage. Percentages stay symbolic until a
definite basis resolves them. ``clamp(MIN, VAL, MAX)`` is
``max(MIN, min(VAL, MAX))``, so a lower bound above the upper bound wins.

``round()``, ``mod()``, ``rem()``, ``abs()``, ``sign()``, ``hypot()``,
``pow()``, ``sqrt()``, ``log()``, ``exp()``, and the trigonometric functions
resolve in the same expression. ``round(nearest, ...)`` breaks an exact tie
toward +infinity, so ``round(nearest, -10.5px, 1px)`` is -10px. ``mod()``
keeps the sign of the step and ``rem()`` keeps the sign of the dividend.
``sin()``, ``cos()``, and ``tan()`` take radians or an angle; an exactly
represented ``tan(90deg)`` is +infinity and ``tan(-90deg)`` is -infinity.
``pow()`` of a negative base requires an integer exponent. ``line-width``
and dividing one length by another stay invalid.

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
_FUNCTIONS = frozenset(
    {
        "calc",
        "min",
        "max",
        "clamp",
        "round",
        "mod",
        "rem",
        "sin",
        "cos",
        "tan",
        "asin",
        "acos",
        "atan",
        "atan2",
        "pow",
        "sqrt",
        "hypot",
        "log",
        "exp",
        "abs",
        "sign",
    }
)
_UNARY = frozenset({"sin", "cos", "tan", "asin", "acos", "atan", "sqrt", "exp", "abs", "sign"})
_BINARY = frozenset({"pow", "atan2", "mod", "rem"})
_STRATEGIES = frozenset({"nearest", "up", "down", "to-zero"})
_ANGLE_SCALE = {"deg": 1.0, "rad": 180.0 / math.pi, "turn": 360.0}
_MATH_START = re.compile(
    r"(?i)\s*(atan2|acos|asin|atan|hypot|sqrt|round|clamp|sign|abs|calc|min|max|mod|rem|sin|cos|tan|pow|log|exp)\("
)


class _Invalid(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class _Num:
    value: float
    tainted: bool = False


@dataclass(frozen=True)
class _Angle:
    deg: float
    tainted: bool = False


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
                if unit == "px":
                    tokens.append(("len", number))
                elif unit == "grad":
                    tokens.append(("ang", number * 9.0 / 10.0))
                elif unit in _ANGLE_SCALE:
                    tokens.append(("ang", number * _ANGLE_SCALE[unit]))
                else:
                    raise _Invalid("unit")
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
            if name in _CONSTANTS:
                tokens.append(("num", _CONSTANTS[name]))
            else:
                tokens.append(("ident", name))
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
        if name == "round":
            return self.parse_round(depth + 1)
        if name in _UNARY:
            return _unary(str(name), self.parse_args(depth + 1, 1, 1)[0], self.basis)
        if name in _BINARY:
            left, right = self.parse_args(depth + 1, 2, 2)
            return _binary(str(name), left, right, self.basis)
        if name == "log":
            args = self.parse_args(depth + 1, 1, 2)
            base = args[1] if len(args) == 2 else None
            return _log_node(args[0], base)
        if name == "hypot":
            return _hypot_node(self.parse_args(depth + 1, 1, None), self.basis)
        raise _Invalid("math is invalid")

    def parse_round(self, depth: int) -> _Node:
        strategy = "nearest"
        if self.peek() is not None and self.peek()[0] == "ident":
            strategy = str(self.take("ident")[1])
            if strategy not in _STRATEGIES:
                raise _Invalid("math is invalid")
            self.take("comma")
        value = self.parse_sum(depth)
        step = None
        if self.peek() == ("comma", ","):
            self.take("comma")
            step = self.parse_sum(depth)
        if self.peek() == ("comma", ","):
            raise _Invalid("math is invalid")
        self.take("rp")
        return _round_node(strategy, value, step, self.basis)

    def parse_args(self, depth: int, minimum: int, maximum: int | None) -> list[_Node]:
        args = [self.parse_sum(depth)]
        while self.peek() == ("comma", ","):
            if maximum is not None and len(args) >= maximum:
                raise _Invalid("math is invalid")
            self.take("comma")
            args.append(self.parse_sum(depth))
        if len(args) < minimum:
            raise _Invalid("math is invalid")
        self.take("rp")
        return args

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
        if token[0] == "ang":
            self.take("ang")
            return _Angle(_token_float(token[1]))
        raise _Invalid("math is invalid")


def _token_float(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _Invalid("math is invalid")
    return float(value)


def _add(left: _Node, right: _Node, sign: float) -> _Node:
    if isinstance(left, _Num) and isinstance(right, _Num):
        return _Num(left.value + sign * right.value, left.tainted or right.tainted)
    if isinstance(left, _Len) and isinstance(right, _Len):
        return _Len(
            left.px + sign * right.px,
            left.pct + sign * right.pct,
            left.px_set or right.px_set,
            left.pct_set or right.pct_set,
        )
    if isinstance(left, _Angle) and isinstance(right, _Angle):
        return _Angle(left.deg + sign * right.deg, left.tainted or right.tainted)
    raise _Invalid("type")


def _multiply(left: _Node, right: _Node) -> _Node:
    if isinstance(left, _Num) and isinstance(right, _Num):
        return _Num(left.value * right.value, left.tainted or right.tainted)
    if isinstance(left, _Num) and isinstance(right, _Len):
        return _scale(right, left.value, left.tainted)
    if isinstance(left, _Len) and isinstance(right, _Num):
        return _scale(left, right.value, right.tainted)
    if isinstance(left, _Num) and isinstance(right, _Angle):
        return _Angle(right.deg * left.value, left.tainted or right.tainted)
    if isinstance(left, _Angle) and isinstance(right, _Num):
        return _Angle(left.deg * right.value, left.tainted or right.tainted)
    raise _Invalid("type")


def _divide(left: _Node, right: _Node) -> _Node:
    if isinstance(left, _Angle) and isinstance(right, _Angle):
        return _Num(_divide_number(left.deg, right.deg), left.tainted or right.tainted)
    if not isinstance(right, _Num):
        raise _Invalid("type")
    if isinstance(left, _Num):
        return _Num(_divide_number(left.value, right.value), left.tainted or right.tainted)
    if isinstance(left, _Len):
        return _Len(
            _divide_component(left.px, left.px_set, right.value),
            _divide_component(left.pct, left.pct_set, right.value),
            left.px_set,
            left.pct_set or right.tainted,
        )
    if isinstance(left, _Angle):
        return _Angle(_divide_number(left.deg, right.value), left.tainted or right.tainted)
    raise _Invalid("type")


def _scale(length: _Len, factor: float, tainted: bool = False) -> _Len:
    return _Len(length.px * factor, length.pct * factor, length.px_set, length.pct_set or tainted)


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
        tainted = any(arg.tainted for arg in args if isinstance(arg, _Num))
        return _Num(_pick(numbers, name), tainted)
    if not all(isinstance(arg, _Len) for arg in args):
        raise _Invalid("type")
    lengths = [arg for arg in args if isinstance(arg, _Len)]
    picked = _pick([arg.px + arg.pct * basis / 100.0 for arg in lengths], name)
    return _Len(picked, 0.0, True, any(arg.pct_set for arg in lengths))


def _pick(values: list[float], name: str) -> float:
    if any(math.isnan(value) for value in values):
        return math.nan
    return min(values) if name == "min" else max(values)


def _kind_value(node: _Node, basis: float) -> tuple[str, float, bool]:
    if isinstance(node, _Num):
        return "num", node.value, node.tainted
    if isinstance(node, _Angle):
        return "ang", node.deg, node.tainted
    if isinstance(node, _Len):
        return "len", node.px + node.pct * basis / 100.0, node.pct_set
    raise _Invalid("type")


def _restore(kind: str, value: float, tainted: bool) -> _Node:
    if kind == "num":
        return _Num(value, tainted)
    if kind == "ang":
        return _Angle(value, tainted)
    if kind == "len":
        return _Len(value, 0.0, True, tainted)
    raise _Invalid("type")


def _require_num(node: _Node) -> tuple[float, bool]:
    if not isinstance(node, _Num):
        raise _Invalid("type")
    return node.value, node.tainted


def _is_integer(value: float) -> bool:
    return math.isfinite(value) and abs(value - round(value)) <= 1e-9


def _is_odd_integer(value: float) -> bool:
    return _is_integer(value) and int(round(value)) % 2 != 0


def _unary(name: str, node: _Node, basis: float) -> _Node:
    if name == "abs":
        return _abs_node(node, basis)
    if name == "sign":
        return _sign_node(node, basis)
    if name in {"sin", "cos", "tan"}:
        return _trig_node(name, node)
    if name in {"asin", "acos", "atan"}:
        value, tainted = _require_num(node)
        degrees = {"asin": _asin_deg, "acos": _acos_deg, "atan": _atan_deg}[name](value)
        return _Angle(degrees, tainted)
    value, tainted = _require_num(node)
    if name == "sqrt":
        return _Num(_sqrt_value(value), tainted)
    if name == "exp":
        return _Num(_exp_value(value), tainted)
    raise _Invalid("math is invalid")


def _binary(name: str, left: _Node, right: _Node, basis: float) -> _Node:
    if name == "pow":
        base, base_taint = _require_num(left)
        exponent, exponent_taint = _require_num(right)
        return _Num(_pow(base, exponent), base_taint or exponent_taint)
    if name == "atan2":
        return _atan2_node(left, right, basis)
    if name in {"mod", "rem"}:
        return _mod_node(name, left, right, basis)
    raise _Invalid("math is invalid")


def _abs_node(node: _Node, basis: float) -> _Node:
    kind, value, tainted = _kind_value(node, basis)
    if math.isnan(value) or value > 0 or (value == 0 and math.copysign(1.0, value) > 0):
        result = value
    else:
        result = -value
    return _restore(kind, result, tainted)


def _sign_node(node: _Node, basis: float) -> _Num:
    _, value, tainted = _kind_value(node, basis)
    if math.isnan(value):
        result = math.nan
    elif value == 0:
        result = math.copysign(0.0, value)
    else:
        result = 1.0 if value > 0 else -1.0
    return _Num(result, tainted)


def _trig_node(name: str, node: _Node) -> _Num:
    if isinstance(node, _Angle):
        result = {"sin": _sin_deg, "cos": _cos_deg, "tan": _tan_deg}[name](node.deg)
        return _Num(result, node.tainted)
    if isinstance(node, _Num):
        if not math.isfinite(node.value):
            return _Num(math.nan, node.tainted)
        result = {"sin": math.sin, "cos": math.cos, "tan": math.tan}[name](node.value)
        if name in {"sin", "tan"} and node.value == 0:
            result = math.copysign(0.0, node.value)
        return _Num(result, node.tainted)
    raise _Invalid("type")


def _reduced_deg(deg: float) -> float:
    reduced = deg % 360.0
    if reduced < 0:
        reduced += 360.0
    if abs(reduced - 360.0) <= 1e-8:
        return 0.0
    return reduced


def _near_deg(value: float, target: float) -> bool:
    return abs(value - target) <= 1e-8


def _sin_deg(deg: float) -> float:
    if not math.isfinite(deg):
        return math.nan
    reduced = _reduced_deg(deg)
    if _near_deg(reduced, 0.0) or _near_deg(reduced, 180.0):
        return 0.0
    if _near_deg(reduced, 90.0):
        return 1.0
    if _near_deg(reduced, 270.0):
        return -1.0
    return math.sin(math.radians(deg))


def _cos_deg(deg: float) -> float:
    if not math.isfinite(deg):
        return math.nan
    reduced = _reduced_deg(deg)
    if _near_deg(reduced, 0.0):
        return 1.0
    if _near_deg(reduced, 180.0):
        return -1.0
    if _near_deg(reduced, 90.0) or _near_deg(reduced, 270.0):
        return 0.0
    return math.cos(math.radians(deg))


def _tan_deg(deg: float) -> float:
    if not math.isfinite(deg):
        return math.nan
    reduced = _reduced_deg(deg)
    if _near_deg(reduced, 90.0):
        return math.inf
    if _near_deg(reduced, 270.0):
        return -math.inf
    return math.tan(math.radians(deg))


def _asin_deg(value: float) -> float:
    if math.isnan(value) or value < -1 or value > 1:
        return math.nan
    if value == 0:
        return math.copysign(0.0, value)
    return math.degrees(math.asin(value))


def _acos_deg(value: float) -> float:
    if math.isnan(value) or value < -1 or value > 1:
        return math.nan
    if value == 1:
        return 0.0
    return math.degrees(math.acos(value))


def _atan_deg(value: float) -> float:
    if math.isnan(value):
        return math.nan
    if value == math.inf:
        return 90.0
    if value == -math.inf:
        return -90.0
    if value == 0:
        return math.copysign(0.0, value)
    return math.degrees(math.atan(value))


def _atan2_node(y_node: _Node, x_node: _Node, basis: float) -> _Angle:
    y_kind, y_value, y_taint = _kind_value(y_node, basis)
    x_kind, x_value, x_taint = _kind_value(x_node, basis)
    if y_kind != x_kind:
        raise _Invalid("type")
    if math.isnan(y_value) or math.isnan(x_value):
        return _Angle(math.nan, y_taint or x_taint)
    return _Angle(math.degrees(math.atan2(y_value, x_value)), y_taint or x_taint)


def _round_node(strategy: str, value: _Node, step: _Node | None, basis: float) -> _Node:
    kind, number, tainted = _kind_value(value, basis)
    if step is None:
        if kind != "num":
            raise _Invalid("math is invalid")
        step_value = 1.0
    else:
        step_kind, step_value, step_taint = _kind_value(step, basis)
        if step_kind != kind:
            raise _Invalid("type")
        tainted = tainted or step_taint
    return _restore(kind, _round_value(strategy, number, step_value), tainted)


def _round_value(strategy: str, number: float, step: float) -> float:
    if math.isnan(number) or math.isnan(step) or step == 0 or (math.isinf(number) and math.isinf(step)):
        return math.nan
    if math.isinf(number):
        return number
    if math.isinf(step):
        return _round_infinite_step(strategy, number)
    quotient = number / step
    if _is_integer(quotient):
        return number
    floor_multiple = math.floor(quotient) * step
    ceil_multiple = math.ceil(quotient) * step
    lower = floor_multiple if floor_multiple <= ceil_multiple else ceil_multiple
    upper = ceil_multiple if ceil_multiple >= floor_multiple else floor_multiple
    if strategy == "up":
        return upper
    if strategy == "down":
        return lower
    if strategy == "to-zero":
        if abs(lower) == abs(upper):
            return upper
        return lower if abs(lower) < abs(upper) else upper
    if abs(number - lower) == abs(number - upper):
        return upper
    return lower if abs(number - lower) < abs(number - upper) else upper


def _round_infinite_step(strategy: str, number: float) -> float:
    positive = math.copysign(1.0, number) > 0
    if strategy in {"nearest", "to-zero"}:
        return 0.0 if number > 0 or (number == 0 and positive) else -0.0
    if strategy == "up":
        if number > 0:
            return math.inf
        return 0.0 if number == 0 and positive else -0.0
    if number < 0:
        return -math.inf
    return -0.0 if number == 0 and not positive else 0.0


def _mod_node(name: str, left: _Node, right: _Node, basis: float) -> _Node:
    kind, number, tainted = _kind_value(left, basis)
    step_kind, step, step_taint = _kind_value(right, basis)
    if kind != step_kind:
        raise _Invalid("type")
    result = _mod_value(number, step) if name == "mod" else _rem_value(number, step)
    return _restore(kind, result, tainted or step_taint)


def _mod_value(number: float, step: float) -> float:
    if math.isnan(number) or math.isnan(step) or step == 0 or math.isinf(number):
        return math.nan
    if math.isinf(step):
        if math.copysign(1.0, number) != math.copysign(1.0, step):
            return math.nan
        return number
    sign = math.copysign(1.0, step)
    return number - sign * _round_value("down", number * sign, step)


def _rem_value(number: float, step: float) -> float:
    if math.isnan(number) or math.isnan(step) or step == 0 or math.isinf(number):
        return math.nan
    if math.isinf(step):
        return number
    return number - _round_value("to-zero", number, step)


def _hypot_node(args: list[_Node], basis: float) -> _Node:
    kinds: list[str] = []
    values: list[float] = []
    tainted = False
    for arg in args:
        kind, value, bit = _kind_value(arg, basis)
        kinds.append(kind)
        values.append(value)
        tainted = tainted or bit
    if any(kind != kinds[0] for kind in kinds):
        raise _Invalid("type")
    if any(math.isnan(value) for value in values):
        result = math.nan
    elif any(math.isinf(value) for value in values):
        result = math.inf
    else:
        result = math.hypot(*values)
    return _restore(kinds[0], result, tainted)


def _log_node(value: _Node, base: _Node | None) -> _Num:
    number, tainted = _require_num(value)
    if base is None:
        base_value, base_taint = math.e, False
    else:
        base_value, base_taint = _require_num(base)
    return _Num(_log_value(number, base_value), tainted or base_taint)


def _log_value(number: float, base: float) -> float:
    if math.isnan(number) or math.isnan(base) or number < 0 or base <= 0 or base == 1 or math.isinf(base):
        return math.nan
    if number == 0:
        return -math.inf
    if number == 1:
        return 0.0
    if math.isinf(number):
        return math.inf
    return math.log(number) / math.log(base)


def _sqrt_value(number: float) -> float:
    if math.isnan(number) or number < 0:
        return math.nan
    if number == 0:
        return math.copysign(0.0, number)
    if math.isinf(number):
        return math.inf
    return math.sqrt(number)


def _exp_value(number: float) -> float:
    if math.isnan(number):
        return math.nan
    if number == math.inf:
        return math.inf
    if number == -math.inf:
        return 0.0
    try:
        return math.exp(number)
    except OverflowError:
        return math.inf


def _pow(base: float, exponent: float) -> float:
    if math.isnan(base) or math.isnan(exponent):
        return math.nan
    if exponent == 0:
        return 1.0
    if math.isinf(base) and math.isinf(exponent):
        return 0.0 if exponent < 0 else math.inf
    if math.isinf(exponent):
        magnitude = abs(base)
        if magnitude == 1:
            return math.nan
        if magnitude > 1:
            return math.inf if exponent > 0 else 0.0
        return 0.0 if exponent > 0 else math.inf
    if math.isinf(base):
        odd = _is_odd_integer(exponent)
        if base > 0:
            return 0.0 if exponent < 0 else math.inf
        if exponent < 0:
            return -0.0 if odd else 0.0
        return -math.inf if odd else math.inf
    if base == 0:
        odd = _is_odd_integer(exponent)
        negative_zero = math.copysign(1.0, base) < 0
        if exponent < 0:
            return -math.inf if negative_zero and odd else math.inf
        return -0.0 if negative_zero and odd else 0.0
    if base < 0:
        if not _is_integer(exponent):
            return math.nan
        power = int(round(exponent))
        try:
            return float(base ** power)
        except OverflowError:
            return math.copysign(math.inf, -1.0 if power % 2 else 1.0)
    try:
        return float(base ** exponent)
    except OverflowError:
        return math.inf


def _number(value: float) -> int | float:
    nearest = round(value)
    if abs(value - nearest) <= 1e-9:
        return int(nearest)
    return value
