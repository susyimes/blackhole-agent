"""Match a CSS container query against ancestor query containers.

CSS Conditional Rules Level 5 selects, for each element, the nearest ancestor
that can answer every feature in one condition. The element itself is not a
candidate. ``inline-size`` answers only the container's inline axis, so a
horizontal container answers ``width`` and a vertical one answers ``height``.
A condition that fails on that container does not fall through. A name does
not select a container of a different name. Each comma-separated condition
chooses its own container, and ``em`` or ``var()`` uses the selected container.

Every element can answer ``style()``. A custom property is compared as the
computed token stream the caller stored: whitespace collapses, case stays, and
a missing property is not equal. ``style(--name)`` is true when that stream is
non-empty. A numeric range needs ``registered`` syntax ``<number>``,
``<integer>``, ``<length>``, or ``<percentage>``; an unregistered name or a
bound of the wrong type is false. ``style()`` of a non-custom property stays
unsupported, so that condition selects no container.

``scroll-state()`` needs ``container-type`` to include ``scroll-state``, which
may sit beside ``size`` or ``inline-size``. Stuck and scrollable states are
physical edges. Snapped states are the ``x`` and ``y`` axes. Logical keywords
follow the container's writing mode. ``none`` is true only when that set is
empty, and ``snapped: both`` needs both axes. This does not lay out; callers
pass content-box sizes and those states.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

_HORIZONTAL = frozenset({"horizontal-tb"})
_VERTICAL = frozenset({"vertical-rl", "vertical-lr", "sideways-rl", "sideways-lr"})
_TYPE_WORDS = frozenset({"size", "inline-size", "scroll-state"})
_SYNTAXES = frozenset({"<number>", "<integer>", "<length>", "<percentage>"})
_EDGES = frozenset({"top", "right", "bottom", "left"})
_AXES_SCROLL = frozenset({"x", "y"})
_STUCK_STATES = _EDGES | frozenset(
    {"none", "block-start", "inline-start", "block-end", "inline-end", "x", "y", "block", "inline"}
)
_SNAPPED_STATES = frozenset({"none", "x", "y", "block", "inline", "both"})
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
_NUMBER_TEXT = re.compile(r"^[+-]?(?:\d+\.\d+|\d+\.|\.\d+|\d+)$")
_INTEGER_TEXT = re.compile(r"^[+-]?\d+$")
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
    raw: str = ""


@dataclass(frozen=True)
class _Length:
    amount: float
    unit: str
    var: str | None = None
    raw: str = ""


@dataclass(frozen=True)
class _Feature:
    axis: str
    kind: str
    bound: _Length | None = None
    high: _Length | None = None
    low_op: str = ""
    high_op: str = ""


@dataclass(frozen=True)
class _Style:
    mode: str
    name: str
    value: str = ""
    op: str = ""
    bound: _Length | None = None
    high: _Length | None = None
    low_op: str = ""
    high_op: str = ""


@dataclass(frozen=True)
class _Scroll:
    kind: str
    state: str


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
    container_types: frozenset[str]
    names: frozenset[str]
    width: float
    height: float
    vertical: bool
    writing_mode: str
    font_size: float
    custom: dict[str, str]
    registered: dict[str, str]
    stuck: frozenset[str]
    snapped: frozenset[str]
    scrollable: frozenset[str]


def match_container_query(elements: object, query: object) -> dict[str, object]:
    """Return which elements match ``query``.

    ``elements`` are tree nodes with ``id``, ``parent``, content-box
    ``width`` and ``height``, and optional ``container_type``,
    ``container_name``, ``writing_mode``, ``font_size``, ``custom``,
    ``registered``, ``stuck``, ``snapped``, and ``scrollable``. ``query`` is
    an ``@container`` prelude. ``matches`` lists the ids whose query list is
    true. ``conditions`` gives each condition's three-valued result and the
    ancestor it selected.
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
    pending: list[tuple[str, str | None, _Box]] = []
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
        writing = str(item.get("writing_mode", "horizontal-tb")).lower()
        if writing in _HORIZONTAL:
            vertical = False
        elif writing in _VERTICAL:
            vertical = True
        else:
            raise _Invalid("writing-mode")
        box = _Box(
            identity,
            None,
            _container_types(item.get("container_type", "normal")),
            _names(item.get("container_name", "none")),
            _px(item.get("width"), "width"),
            _px(item.get("height"), "height"),
            vertical,
            writing,
            _font(item.get("font_size", 16)),
            _custom(item.get("custom", {})),
            _registered(item.get("registered", {})),
            _flag_set(item.get("stuck"), _EDGES, "stuck"),
            _flag_set(item.get("snapped"), _AXES_SCROLL, "snapped"),
            _flag_set(item.get("scrollable"), _EDGES, "scrollable"),
        )
        pending.append((identity, parent, box))
    boxes = {identity: box for identity, _, box in pending}
    for identity, parent, _box in pending:
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
    return [box for _identity, _parent, box in pending]


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


def _container_types(value: object) -> frozenset[str]:
    text = str(value if value is not None else "normal").strip().lower()
    if text == "normal":
        return frozenset()
    parts = text.split()
    if not parts or any(part not in _TYPE_WORDS for part in parts) or len(parts) != len(set(parts)):
        raise _Invalid("container-type")
    if "size" in parts and "inline-size" in parts:
        raise _Invalid("container-type")
    return frozenset(parts)


def _registered(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        raise _Invalid("registered")
    registered: dict[str, str] = {}
    for key, raw in value.items():
        if not isinstance(key, str) or not key.startswith("--") or not isinstance(raw, str):
            raise _Invalid("registered")
        syntax = "".join(raw.split()).lower()
        if syntax not in _SYNTAXES:
            raise _Invalid("registered")
        registered[key] = syntax
    return registered


def _flag_set(value: object, allowed: frozenset[str], name: str) -> frozenset[str]:
    if value is None:
        return frozenset()
    if isinstance(value, str):
        parts = value.split()
    elif isinstance(value, list) and all(isinstance(item, str) for item in value):
        parts = [item for item in value if item]
    else:
        raise _Invalid(name)
    lowered = [part.lower() for part in parts]
    if not lowered or lowered == ["none"]:
        return frozenset()
    if "none" in lowered or any(part not in allowed for part in lowered):
        raise _Invalid(name)
    return frozenset(lowered)


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
                tokens.append(_Tok("dim", unit, number, match.group("num")))
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
            return self._function_query()
        if token is None or token.kind != "(":
            raise _Invalid("query syntax")
        self.take()
        inner = self._inner_tokens()
        if not inner:
            return _Unsupported()
        if inner[0].kind in {"(", "function"} or (inner[0].kind == "ident" and inner[0].value.lower() == "not"):
            return _parse_query(inner)
        if inner[0].kind == "ident" and inner[0].value.lower() in {"style", "scroll-state"}:
            return _Unsupported()
        try:
            return _parse_feature(inner)
        except _BadFeature:
            return _Unsupported()

    def _function_query(self) -> object:
        name = self.take().value.lower()
        if self.peek() is None or self.peek().kind != "(":
            raise _Invalid("query syntax")
        self.take()
        return _style_or_scroll(name, self._inner_tokens())

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


def _style_or_scroll(name: str, inner: list[_Tok]) -> object:
    try:
        if name == "style":
            return _parse_style(inner)
        if name == "scroll-state":
            return _parse_scroll(inner)
    except _BadFeature:
        return _Unsupported()
    return _Unsupported()


def _parse_style(tokens: list[_Tok]) -> _Style:
    if len(tokens) == 1 and tokens[0].kind == "ident" and tokens[0].value.startswith("--"):
        return _Style("boolean", tokens[0].value)
    if (
        len(tokens) >= 3
        and tokens[0].kind == "ident"
        and tokens[0].value.startswith("--")
        and tokens[1].kind == ":"
    ):
        return _Style("eq", tokens[0].value, _serialize_value(tokens[2:]))
    return _parse_style_range(tokens)


def _parse_style_range(tokens: list[_Tok]) -> _Style:
    atoms = _style_atoms(tokens)
    if len(atoms) == 3 and atoms[0][0] == "name" and atoms[1][0] == "op" and atoms[2][0] == "value":
        return _Style("cmp", _text(atoms[0][1]), op=_CMP[_text(atoms[1][1])], bound=_span(atoms[2][1]))
    if len(atoms) == 3 and atoms[2][0] == "name" and atoms[1][0] == "op" and atoms[0][0] == "value":
        return _Style("cmp", _text(atoms[2][1]), op=_flip(_CMP[_text(atoms[1][1])]), bound=_span(atoms[0][1]))
    if (
        len(atoms) == 5
        and atoms[0][0] == "value"
        and atoms[1][0] == "op"
        and atoms[2][0] == "name"
        and atoms[3][0] == "op"
        and atoms[4][0] == "value"
    ):
        left = _CMP[_text(atoms[1][1])]
        right = _CMP[_text(atoms[3][1])]
        name = _text(atoms[2][1])
        if left in _LT and right in _LT:
            return _Style("between", name, bound=_span(atoms[0][1]), high=_span(atoms[4][1]), low_op=left, high_op=right)
        if left in _GT and right in _GT:
            return _Style(
                "between",
                name,
                bound=_span(atoms[4][1]),
                high=_span(atoms[0][1]),
                low_op=_flip(right),
                high_op=_flip(left),
            )
    raise _BadFeature()


def _text(value: object) -> str:
    if not isinstance(value, str):
        raise _BadFeature()
    return value


def _span(value: object) -> _Length:
    if not isinstance(value, _Length):
        raise _BadFeature()
    return value


def _style_atoms(tokens: list[_Tok]) -> list[tuple[str, object]]:
    atoms: list[tuple[str, object]] = []
    for token in tokens:
        if token.kind == "ident" and token.value.startswith("--"):
            atoms.append(("name", token.value))
            continue
        if token.kind == "op":
            if token.value not in _CMP:
                raise _BadFeature()
            atoms.append(("op", token.value))
            continue
        if token.kind in {"number", "dim"}:
            atoms.append(("value", _length_token(token)))
            continue
        raise _BadFeature()
    return atoms


def _length_token(token: _Tok) -> _Length:
    if token.kind == "number":
        return _Length(token.number, "", raw=token.value)
    if token.kind == "dim":
        return _Length(token.number, token.value.lower(), raw=token.raw or _format_number(token.number))
    raise _BadFeature()


def _serialize_value(tokens: list[_Tok]) -> str:
    pieces: list[str] = []
    for token in tokens:
        if token.kind in {":", "op"}:
            raise _BadFeature()
        if token.kind == ",":
            pieces.append(",")
            continue
        if token.kind == "(":
            pieces.append("(")
            continue
        if token.kind == ")":
            pieces.append(")")
            continue
        lexeme = _lexeme(token)
        if pieces and pieces[-1] != "(":
            pieces.append(" ")
        pieces.append(lexeme)
    text = "".join(pieces).strip()
    if not text:
        raise _BadFeature()
    return " ".join(text.split())


def _lexeme(token: _Tok) -> str:
    if token.kind == "dim":
        return f"{token.raw or _format_number(token.number)}{token.value.lower()}"
    if token.kind == "number":
        return token.value
    return token.value


def _format_number(number: float) -> str:
    if number.is_integer():
        return str(int(number))
    return str(number)


def _parse_scroll(tokens: list[_Tok]) -> _Scroll:
    if len(tokens) != 3 or tokens[0].kind != "ident" or tokens[1].kind != ":" or tokens[2].kind != "ident":
        raise _BadFeature()
    kind = tokens[0].value.lower()
    state = tokens[2].value.lower()
    allowed = {"stuck": _STUCK_STATES, "snapped": _SNAPPED_STATES, "scrollable": _STUCK_STATES}.get(kind)
    if allowed is None or state not in allowed:
        raise _BadFeature()
    return _Scroll(kind, state)


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


def _size_ancestor(box: _Box, name: str | None, features: list[object]) -> _Box | None:
    current = box.parent
    while current is not None:
        if (name is None or name in current.names) and _supports(current, features):
            return current
        current = current.parent
    return None


def _supports(box: _Box, features: list[object]) -> bool:
    needs_scroll = any(isinstance(feature, _Scroll) for feature in features)
    size_features = [feature for feature in features if isinstance(feature, _Feature)]
    if needs_scroll and "scroll-state" not in box.container_types:
        return False
    if not size_features:
        return True
    if "size" in box.container_types:
        provided = {"horizontal", "vertical"}
    elif "inline-size" in box.container_types:
        provided = {"vertical"} if box.vertical else {"horizontal"}
    else:
        provided = set()
    for feature in size_features:
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


def _features(node: object) -> list[object]:
    if isinstance(node, (_Feature, _Style, _Scroll)):
        return [node]
    if isinstance(node, _Not):
        return _features(node.inner)
    if isinstance(node, _Bool):
        found: list[object] = []
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
    if isinstance(node, _Style):
        return _eval_style(node, box)
    if isinstance(node, _Scroll):
        return _eval_scroll(node, box)
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


def _eval_style(feature: _Style, box: _Box) -> str:
    raw = box.custom.get(feature.name)
    if feature.mode == "boolean":
        return "true" if raw is not None and _collapse(raw) != "" else "false"
    if feature.mode == "eq":
        if raw is None:
            return "false"
        return "true" if _collapse(raw) == feature.value else "false"
    syntax = box.registered.get(feature.name)
    if syntax is None or raw is None:
        return "false"
    actual = _typed_number(_collapse(raw), syntax, box.font_size)
    if actual is None:
        return "false"
    if feature.mode == "cmp":
        bound = _bound_number(feature.bound, syntax, box.font_size)
        if bound is None:
            return "false"
        return "true" if _compare(actual, feature.op, bound) else "false"
    low = _bound_number(feature.bound, syntax, box.font_size)
    high = _bound_number(feature.high, syntax, box.font_size)
    if low is None or high is None:
        return "false"
    if not _compare(low, feature.low_op, actual) or not _compare(actual, feature.high_op, high):
        return "false"
    return "true"


def _eval_scroll(feature: _Scroll, box: _Box) -> str:
    if feature.kind == "snapped":
        return "true" if _snapped(feature.state, box) else "false"
    edges = box.stuck if feature.kind == "stuck" else box.scrollable
    return "true" if _edge_state(feature.state, edges, box.writing_mode) else "false"


def _collapse(text: str) -> str:
    return " ".join(text.split())


def _typed_number(text: str, syntax: str, font_size: float) -> float | None:
    if syntax == "<number>":
        if not _NUMBER_TEXT.fullmatch(text):
            return None
        return float(text)
    if syntax == "<integer>":
        if not _INTEGER_TEXT.fullmatch(text):
            return None
        return float(text)
    if syntax == "<percentage>":
        if not text.endswith("%"):
            return None
        number = text[:-1]
        if not _NUMBER_TEXT.fullmatch(number):
            return None
        return float(number)
    if syntax == "<length>":
        match = _LENGTH.fullmatch(text)
        if match is None:
            return None
        amount = float(match.group(1))
        unit = match.group(2).lower()
        if unit == "px":
            return amount
        if unit == "em":
            return amount * font_size
        return None
    return None


def _bound_number(length: _Length | None, syntax: str, font_size: float) -> float | None:
    if length is None or length.var is not None:
        return None
    if syntax in {"<number>", "<integer>"}:
        if length.unit != "":
            return None
        raw = length.raw
        if syntax == "<integer>" and not _INTEGER_TEXT.fullmatch(raw):
            return None
        if syntax == "<number>" and raw and not _NUMBER_TEXT.fullmatch(raw):
            return None
        return length.amount
    if syntax == "<percentage>":
        if length.unit != "%":
            return None
        return length.amount
    if syntax == "<length>":
        if length.unit == "px":
            return length.amount
        if length.unit == "em":
            return length.amount * font_size
        return None
    return None


def _logical_edges(mode: str) -> dict[str, str]:
    if mode == "horizontal-tb":
        return {"block-start": "top", "block-end": "bottom", "inline-start": "left", "inline-end": "right"}
    if mode in {"vertical-rl", "sideways-rl"}:
        return {"block-start": "right", "block-end": "left", "inline-start": "top", "inline-end": "bottom"}
    return {"block-start": "left", "block-end": "right", "inline-start": "top", "inline-end": "bottom"}


def _edge_state(state: str, edges: frozenset[str], mode: str) -> bool:
    if state == "none":
        return not edges
    if state in _EDGES:
        return state in edges
    if state == "x":
        return bool(edges & {"left", "right"})
    if state == "y":
        return bool(edges & {"top", "bottom"})
    mapping = _logical_edges(mode)
    if state in mapping:
        return mapping[state] in edges
    if state == "block":
        return mapping["block-start"] in edges or mapping["block-end"] in edges
    if state == "inline":
        return mapping["inline-start"] in edges or mapping["inline-end"] in edges
    return False


def _snapped(state: str, box: _Box) -> bool:
    axes = box.snapped
    inline_axis = "x" if box.writing_mode == "horizontal-tb" else "y"
    block_axis = "y" if box.writing_mode == "horizontal-tb" else "x"
    if state == "none":
        return not axes
    if state == "both":
        return "x" in axes and "y" in axes
    if state in {"x", "y"}:
        return state in axes
    if state == "inline":
        return inline_axis in axes
    if state == "block":
        return block_axis in axes
    return False


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
