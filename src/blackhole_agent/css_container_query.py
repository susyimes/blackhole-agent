"""Match a CSS container query against ancestor query containers.

CSS Conditional Rules Level 5 selects, for each element, the nearest ancestor
that can answer every size feature in one condition. The element itself is
not a candidate. ``inline-size`` answers only the container's inline axis, so
a horizontal container answers ``width`` and a vertical one answers
``height``. A condition that fails on that container does not fall through.
A name does not select a container of a different name. Each comma-separated
condition chooses its own container, and ``em`` or ``var()`` uses the
selected container. Style and scroll-state features are unsupported, so a
condition that contains one selects no container. This does not lay out;
callers pass content-box sizes.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

_HORIZONTAL = frozenset({"horizontal-tb"})
_VERTICAL = frozenset({"vertical-rl", "vertical-lr", "sideways-rl", "sideways-lr"})
_TYPES = frozenset({"normal", "size", "inline-size"})
_RESERVED_NAMES = frozenset({"and", "not", "or", "none"})
_AXES = frozenset({"width", "height", "inline-size", "block-size"})
_PLAIN = {
    "width": ("width", "eq"),
    "min-width": ("width", "ge"),
    "max-width": ("width", "le"),
    "height": ("height", "eq"),
    "min-height": ("height", "ge"),
    "max-height": ("height", "le"),
    "inline-size": ("inline-size", "eq"),
    "min-inline-size": ("inline-size", "ge"),
    "max-inline-size": ("inline-size", "le"),
    "block-size": ("block-size", "eq"),
    "min-block-size": ("block-size", "ge"),
    "max-block-size": ("block-size", "le"),
}
_CMP = {">": "gt", ">=": "ge", "<": "lt", "<=": "le", "=": "eq"}
_LT = frozenset({"lt", "le"})
_GT = frozenset({"gt", "ge"})
_TOKEN = re.compile(
    r"\s+"
    r"|(?P<op>>=|<=|[><=])"
    r"|(?P<punct>[(),:])"
    r"|(?P<num>-?(?:\d+\.\d+|\d+\.|\.\d+|\d+))(?P<unit>[A-Za-z%]+)?"
    r"|(?P<ident>(?:--|-)?[A-Za-z_][A-Za-z0-9_-]*)"
    r"|(?P<bad>.)"
)
_LENGTH = re.compile(r"^(-?(?:\d+\.\d+|\d+\.|\.\d+|\d+))([A-Za-z%]+)$")
_IDENT = re.compile(r"^(?:--|-)?[A-Za-z_][A-Za-z0-9_-]*$")


class _Invalid(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class _BadFeature(Exception):
    pass


@dataclass(frozen=True)
class _Tok:
    kind: str
    value: str
    number: float = 0.0


@dataclass(frozen=True)
class _Length:
    amount: float
    unit: str
    var: str | None = None


@dataclass(frozen=True)
class _Feature:
    axis: str
    kind: str
    bound: _Length | None = None
    high: _Length | None = None
    low_op: str = ""
    high_op: str = ""


@dataclass(frozen=True)
class _Unsupported:
    pass


@dataclass(frozen=True)
class _Not:
    inner: object


@dataclass(frozen=True)
class _Bool:
    op: str
    parts: tuple[object, ...]


@dataclass(frozen=True)
class _Condition:
    name: str | None
    query: object


@dataclass
class _Box:
    id: str
    parent: _Box | None
    container_type: str
    names: frozenset[str]
    width: float
    height: float
    vertical: bool
    font_size: float
    custom: dict[str, str]


def match_container_query(elements: object, query: object) -> dict[str, object]:
    """Return which elements match ``query``.

    ``elements`` are tree nodes with ``id``, ``parent``, content-box
    ``width`` and ``height``, and optional ``container_type``,
    ``container_name``, ``writing_mode``, ``font_size``, and ``custom``.
    ``query`` is an ``@container`` prelude. ``matches`` lists the ids whose
    query list is true. ``conditions`` gives each condition's three-valued
    result and the ancestor it selected.
    """

    try:
        boxes = _boxes(elements)
        conditions = _parse(query)
    except _Invalid as exc:
        return _invalid(exc.reason)
    conditions_out: dict[str, list[dict[str, object]]] = {}
    matches: list[str] = []
    for box in boxes:
        rows = [_evaluate(box, condition) for condition in conditions]
        conditions_out[box.id] = rows
        if _combine(row["value"] for row in rows) == "true":
            matches.append(box.id)
    return {"outcome": "matched", "matches": matches, "conditions": conditions_out}


def _invalid(reason: str) -> dict[str, object]:
    return {"outcome": "invalid", "reason": reason, "matches": None, "conditions": None}


def _boxes(value: object) -> list[_Box]:
    if not isinstance(value, list) or not value:
        raise _Invalid("elements")
    pending: list[tuple[str, str | None, str, frozenset[str], float, float, bool, float, dict[str, str]]] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            raise _Invalid("elements")
        identity = item.get("id")
        if not isinstance(identity, str) or not identity or identity in seen:
            raise _Invalid("duplicate id" if isinstance(identity, str) and identity in seen else "element id")
        seen.add(identity)
        parent = item.get("parent")
        if parent is not None and not isinstance(parent, str):
            raise _Invalid("parent")
        container_type = str(item.get("container_type", "normal")).lower()
        if container_type not in _TYPES:
            raise _Invalid("container-type")
        names = _names(item.get("container_name", "none"))
        writing = str(item.get("writing_mode", "horizontal-tb")).lower()
        if writing in _HORIZONTAL:
            vertical = False
        elif writing in _VERTICAL:
            vertical = True
        else:
            raise _Invalid("writing-mode")
        pending.append(
            (
                identity,
                parent,
                container_type,
                names,
                _px(item.get("width"), "width"),
                _px(item.get("height"), "height"),
                vertical,
                _font(item.get("font_size", 16)),
                _custom(item.get("custom", {})),
            )
        )
    boxes = {
        identity: _Box(identity, None, container_type, names, width, height, vertical, font_size, custom)
        for identity, _, container_type, names, width, height, vertical, font_size, custom in pending
    }
    for identity, parent, *_rest in pending:
        if parent is None:
            continue
        if parent not in boxes:
            raise _Invalid("parent")
        boxes[identity].parent = boxes[parent]
    for box in boxes.values():
        seen_ids: set[str] = set()
        current: _Box | None = box
        while current is not None:
            if current.id in seen_ids:
                raise _Invalid("cycle")
            seen_ids.add(current.id)
            current = current.parent
    return [boxes[identity] for identity, *_rest in pending]


def _names(value: object) -> frozenset[str]:
    if value is None or value == "none":
        return frozenset()
    if isinstance(value, str):
        parts = value.split()
    elif isinstance(value, list) and all(isinstance(item, str) for item in value):
        parts = value
    else:
        raise _Invalid("container-name")
    if not parts or any(not _IDENT.fullmatch(part) or part.lower() in _RESERVED_NAMES for part in parts):
        if len(parts) == 1 and parts[0].lower() == "none":
            return frozenset()
        raise _Invalid("container-name")
    return frozenset(parts)


def _px(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise _Invalid(name)
    return float(value)


def _font(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise _Invalid("font-size")
    return float(value)


def _custom(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        raise _Invalid("custom")
    custom: dict[str, str] = {}
    for key, raw in value.items():
        if not isinstance(key, str) or not key.startswith("--") or not isinstance(raw, str):
            raise _Invalid("custom")
        custom[key] = raw
    return custom


def _parse(query: object) -> list[_Condition]:
    if not isinstance(query, str):
        raise _Invalid("query")
    text = _comments(query).strip()
    lowered = text.lower()
    if lowered.startswith("@container"):
        rest = text[len("@container") :]
        if rest[:1] not in {"", " ", "\t", "\n", "\r", "\f"}:
            raise _Invalid("query syntax")
        text = rest.strip()
    elif text.startswith("@"):
        raise _Invalid("query syntax")
    if not text:
        raise _Invalid("empty condition")
    return [_parse_condition(_tokenize(part)) for part in _split_commas(text)]


def _comments(text: str) -> str:
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


def _split_commas(text: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    start = 0
    for index, char in enumerate(text):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth < 0:
                raise _Invalid("query syntax")
        elif char == "," and depth == 0:
            parts.append(text[start:index])
            start = index + 1
    if depth != 0:
        raise _Invalid("query syntax")
    parts.append(text[start:])
    if any(not part.strip() for part in parts):
        raise _Invalid("empty condition")
    return parts


def _tokenize(text: str) -> list[_Tok]:
    tokens: list[_Tok] = []
    source = text.strip()
    for match in _TOKEN.finditer(source):
        if match.group(0).isspace():
            continue
        if match.group("bad"):
            raise _Invalid("query syntax")
        if match.group("op"):
            tokens.append(_Tok("op", match.group("op")))
            continue
        if match.group("punct"):
            tokens.append(_Tok(match.group("punct"), match.group("punct")))
            continue
        if match.group("num") is not None:
            number = float(match.group("num"))
            unit = match.group("unit")
            if unit:
                tokens.append(_Tok("dim", unit, number))
            else:
                tokens.append(_Tok("number", match.group("num"), number))
            continue
        # A function token has no whitespace before "(". A container name does.
        kind = "function" if match.end() < len(source) and source[match.end()] == "(" else "ident"
        tokens.append(_Tok(kind, match.group("ident")))
    if not tokens:
        raise _Invalid("empty condition")
    return tokens


def _parse_condition(tokens: list[_Tok]) -> _Condition:
    name = None
    body = tokens
    first = tokens[0]
    if first.kind == "ident" and first.value.lower() != "not":
        if first.value.lower() in _RESERVED_NAMES:
            raise _Invalid("container name is reserved")
        name = first.value
        body = tokens[1:]
    if not body:
        if name is None:
            raise _Invalid("empty condition")
        return _Condition(name, None)
    return _Condition(name, _parse_query(body))


def _parse_query(tokens: list[_Tok]) -> object:
    parser = _Parser(tokens)
    node = parser.query()
    if parser.peek() is not None:
        raise _Invalid("query syntax")
    return node


class _Parser:
    def __init__(self, tokens: list[_Tok]) -> None:
        self.tokens = tokens
        self.index = 0

    def peek(self) -> _Tok | None:
        if self.index >= len(self.tokens):
            return None
        return self.tokens[self.index]

    def take(self) -> _Tok:
        token = self.peek()
        if token is None:
            raise _Invalid("query syntax")
        self.index += 1
        return token

    def query(self) -> object:
        token = self.peek()
        if token is not None and token.kind == "ident" and token.value.lower() == "not":
            self.take()
            node = _Not(self.query_in_parens())
            if self.peek() is not None:
                raise _Invalid("query syntax")
            return node
        first = self.query_in_parens()
        token = self.peek()
        if token is None:
            return first
        if token.kind != "ident" or token.value.lower() not in {"and", "or"}:
            raise _Invalid("query syntax")
        op = token.value.lower()
        parts = [first]
        while self.peek() is not None and self.peek().kind == "ident" and self.peek().value.lower() == op:
            self.take()
            parts.append(self.query_in_parens())
        nxt = self.peek()
        if nxt is not None and nxt.kind == "ident" and nxt.value.lower() in {"and", "or"}:
            raise _Invalid("mixed and or")
        if self.peek() is not None:
            raise _Invalid("query syntax")
        return _Bool(op, tuple(parts))

    def query_in_parens(self) -> object:
        token = self.peek()
        if token is not None and token.kind == "function":
            self.take()
            if self.peek() is None or self.peek().kind != "(":
                raise _Invalid("query syntax")
            self.take()
            self._skip_group()
            return _Unsupported()
        if token is None or token.kind != "(":
            raise _Invalid("query syntax")
        self.take()
        inner = self._inner_tokens()
        if not inner:
            return _Unsupported()
        if inner[0].kind == "(" or (inner[0].kind == "ident" and inner[0].value.lower() == "not"):
            return _parse_query(inner)
        if inner[0].kind == "ident" and inner[0].value.lower() in {"style", "scroll-state"}:
            return _Unsupported()
        try:
            return _parse_feature(inner)
        except _BadFeature:
            return _Unsupported()

    def _inner_tokens(self) -> list[_Tok]:
        depth = 1
        inner: list[_Tok] = []
        while self.peek() is not None:
            token = self.take()
            if token.kind == "(":
                depth += 1
                inner.append(token)
                continue
            if token.kind == ")":
                depth -= 1
                if depth == 0:
                    return inner
            inner.append(token)
        raise _Invalid("query syntax")

    def _skip_group(self) -> None:
        depth = 1
        while self.peek() is not None:
            token = self.take()
            if token.kind == "(":
                depth += 1
            elif token.kind == ")":
                depth -= 1
                if depth == 0:
                    return
        raise _Invalid("query syntax")


def _parse_feature(tokens: list[_Tok]) -> _Feature:
    atoms = _atoms(tokens)
    if len(atoms) == 1 and atoms[0][0] == "ident" and atoms[0][1].value.lower() in _AXES:
        return _Feature(atoms[0][1].value.lower(), "boolean")
    if len(atoms) == 3 and atoms[0][0] == "ident" and atoms[1][0] == ":":
        mapped = _PLAIN.get(atoms[0][1].value.lower())
        if mapped is None or atoms[2][0] != "value":
            raise _BadFeature()
        return _Feature(mapped[0], mapped[1], atoms[2][1])
    if len(atoms) == 3 and atoms[0][0] == "ident" and atoms[1][0] == "op" and atoms[0][1].value.lower() in _AXES:
        if atoms[2][0] != "value":
            raise _BadFeature()
        return _Feature(atoms[0][1].value.lower(), _CMP[atoms[1][1].value], atoms[2][1])
    if len(atoms) == 3 and atoms[2][0] == "ident" and atoms[1][0] == "op" and atoms[2][1].value.lower() in _AXES:
        if atoms[0][0] != "value":
            raise _BadFeature()
        return _Feature(atoms[2][1].value.lower(), _flip(_CMP[atoms[1][1].value]), atoms[0][1])
    if (
        len(atoms) == 5
        and atoms[1][0] == "op"
        and atoms[3][0] == "op"
        and atoms[2][0] == "ident"
        and atoms[2][1].value.lower() in _AXES
        and atoms[0][0] == "value"
        and atoms[4][0] == "value"
    ):
        left = _CMP[atoms[1][1].value]
        right = _CMP[atoms[3][1].value]
        axis = atoms[2][1].value.lower()
        if left in _LT and right in _LT:
            return _Feature(axis, "between", atoms[0][1], atoms[4][1], left, right)
        if left in _GT and right in _GT:
            return _Feature(axis, "between", atoms[4][1], atoms[0][1], _flip(right), _flip(left))
    raise _BadFeature()


def _atoms(tokens: list[_Tok]) -> list[tuple[str, object]]:
    atoms: list[tuple[str, object]] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.kind in {"ident", "function"} and token.value.lower() == "var":
            if (
                index + 3 >= len(tokens)
                or tokens[index + 1].kind != "("
                or tokens[index + 2].kind != "ident"
                or not tokens[index + 2].value.startswith("--")
                or tokens[index + 3].kind != ")"
            ):
                raise _BadFeature()
            atoms.append(("value", _Length(0, "var", tokens[index + 2].value)))
            index += 4
            continue
        if token.kind == "dim":
            atoms.append(("value", _Length(token.number, token.value.lower())))
            index += 1
            continue
        atoms.append((token.kind, token))
        index += 1
    return atoms


def _flip(kind: str) -> str:
    return {"gt": "lt", "ge": "le", "lt": "gt", "le": "ge", "eq": "eq"}[kind]


def _evaluate(box: _Box, condition: _Condition) -> dict[str, object]:
    if condition.query is None:
        selected = _named_ancestor(box, condition.name)
        if selected is None:
            return {"value": "unknown", "container": None}
        return {"value": "true", "container": selected.id}
    if _unsupported(condition.query):
        return {"value": "unknown", "container": None}
    selected = _size_ancestor(box, condition.name, _features(condition.query))
    if selected is None:
        return {"value": "unknown", "container": None}
    return {"value": _eval(condition.query, selected), "container": selected.id}


def _named_ancestor(box: _Box, name: str | None) -> _Box | None:
    current = box.parent
    while current is not None:
        if name is not None and name in current.names:
            return current
        current = current.parent
    return None


def _size_ancestor(box: _Box, name: str | None, features: list[_Feature]) -> _Box | None:
    current = box.parent
    while current is not None:
        if (name is None or name in current.names) and _supports(current, features):
            return current
        current = current.parent
    return None


def _supports(box: _Box, features: list[_Feature]) -> bool:
    provided = {"horizontal", "vertical"} if box.container_type == "size" else set()
    if box.container_type == "inline-size":
        provided = {"vertical"} if box.vertical else {"horizontal"}
    for feature in features:
        if not _needed(feature.axis, box.vertical) <= provided:
            return False
    return True


def _needed(axis: str, vertical: bool) -> set[str]:
    if axis == "width":
        return {"horizontal"}
    if axis == "height":
        return {"vertical"}
    if axis == "inline-size":
        return {"vertical"} if vertical else {"horizontal"}
    return {"horizontal"} if vertical else {"vertical"}


def _unsupported(node: object) -> bool:
    if isinstance(node, _Unsupported):
        return True
    if isinstance(node, _Not):
        return _unsupported(node.inner)
    if isinstance(node, _Bool):
        return any(_unsupported(part) for part in node.parts)
    return False


def _features(node: object) -> list[_Feature]:
    if isinstance(node, _Feature):
        return [node]
    if isinstance(node, _Not):
        return _features(node.inner)
    if isinstance(node, _Bool):
        found: list[_Feature] = []
        for part in node.parts:
            found.extend(_features(part))
        return found
    return []


def _eval(node: object, box: _Box) -> str:
    if isinstance(node, _Not):
        value = _eval(node.inner, box)
        if value == "unknown":
            return "unknown"
        return "false" if value == "true" else "true"
    if isinstance(node, _Bool):
        values = [_eval(part, box) for part in node.parts]
        if node.op == "and":
            if any(value == "false" for value in values):
                return "false"
            return "unknown" if any(value == "unknown" for value in values) else "true"
        if any(value == "true" for value in values):
            return "true"
        return "unknown" if any(value == "unknown" for value in values) else "false"
    if isinstance(node, _Feature):
        return _eval_feature(node, box)
    return "unknown"


def _eval_feature(feature: _Feature, box: _Box) -> str:
    size = _read(box, feature.axis)
    if feature.kind == "boolean":
        return "true" if size != 0 else "false"
    if feature.kind == "between":
        low = _resolve(feature.bound, box)
        high = _resolve(feature.high, box)
        if low is None or high is None:
            return "unknown"
        if not _compare(low, feature.low_op, size) or not _compare(size, feature.high_op, high):
            return "false"
        return "true"
    bound = _resolve(feature.bound, box)
    if bound is None:
        return "unknown"
    return "true" if _compare(size, feature.kind, bound) else "false"


def _read(box: _Box, axis: str) -> float:
    if axis == "width":
        return box.width
    if axis == "height":
        return box.height
    if axis == "inline-size":
        return box.height if box.vertical else box.width
    return box.width if box.vertical else box.height


def _resolve(length: _Length | None, box: _Box) -> float | None:
    if length is None:
        return None
    if length.unit == "var" and length.var is not None:
        raw = box.custom.get(length.var)
        if raw is None:
            return None
        match = _LENGTH.fullmatch(raw.strip())
        if match is None:
            return None
        length = _Length(float(match.group(1)), match.group(2).lower())
    if length.unit == "px":
        return length.amount
    if length.unit == "em":
        return length.amount * box.font_size
    return None


def _compare(left: float, op: str, right: float) -> bool:
    if op == "gt":
        return left > right
    if op == "ge":
        return left >= right
    if op == "lt":
        return left < right
    if op == "le":
        return left <= right
    return left == right


def _combine(values: object) -> str:
    rows = list(values)
    if any(value == "true" for value in rows):
        return "true"
    if rows and all(value == "false" for value in rows):
        return "false"
    return "unknown"
