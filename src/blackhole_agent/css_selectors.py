"""Match CSS selectors and resolve author declarations.

Selectors Level 4 counts ``:nth-child(An+B of S)`` only among siblings that
match S. ``:is()`` and ``:not()`` take the specificity of their most specific
argument even when a less specific argument matched. ``:where()`` adds none.
``:has()`` matches when a relative selector reaches another element: a missing
combinator means a descendant, and ``>``, ``+``, and ``~`` keep their usual
direction. Its specificity is the most specific argument. An author
``!important`` declaration beats a normal declaration of higher specificity.
The reader covers type, class, id, the universal selector, and the descendant,
child, next-sibling, and subsequent-sibling combinators.

``computed_value`` substitutes ``var()`` after the cascade. A custom property
inherits the value its parent already computed, so a child that overrides a
dependency does not retarget that inherited value. A cycle is
guaranteed-invalid even when the cyclic declaration carries a fallback. A
fallback on a property outside the cycle still applies, and a fallback that
is never used does not create a cycle. Registered ``@property`` rules,
``revert-layer``, and animation tainting are outside this reader.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from blackhole_agent.html5_document import parse_tree


_HTML_SPACE = re.compile(r"[ \t\n\f\r]+")
_ANB = re.compile(r"([+-]?(?:\d+)?)n([+-]\d+)?\Z")
_NUMBER = re.compile(r"[+-]?\d+\Z")


class CssSelectorError(ValueError):
    """A selector or stylesheet is outside the supported grammar."""


@dataclass(frozen=True)
class _Simple:
    kind: str
    name: str = ""
    selectors: tuple[Complex, ...] = ()
    a: int = 0
    b: int = 0


@dataclass(frozen=True)
class Complex:
    compounds: tuple[tuple[_Simple, ...], ...]
    combinators: tuple[str, ...]
    anchor: str = ""


@dataclass(frozen=True)
class _Decl:
    selectors: tuple[Complex, ...]
    prop: str
    value: str
    important: bool
    order: int


@dataclass
class _Tree:
    parent: dict
    children: dict
    order: list


def matched_ids(markup: str, selector: str) -> list[str]:
    """Return the id of each matching element, in tree order.

    An element with no id is skipped. The match itself still uses that element
    when a combinator or an ``of`` clause walks through it.
    """

    tree, order = _document(markup)
    compiled = _selector_list(selector)
    found: list[str] = []
    for element in order:
        if not _list_matches(tree, element, compiled):
            continue
        identity = _attr(element, "id")
        if identity:
            found.append(identity)
    return found


def selector_specificity(selector: str) -> list[list[int]]:
    """Specificity of each complex selector, as ``[ids, classes, types]``."""

    return [[*triple] for triple in (_specificity(item) for item in _selector_list(selector))]


def cascaded_value(markup: str, stylesheet: str, element_id: str, property_name: str) -> str:
    """Winning author value for ``element_id``, or empty when none applies."""

    if not isinstance(element_id, str) or not element_id:
        raise CssSelectorError("element id must be a non-empty string")
    prop = _property_key(property_name)
    if not prop:
        raise CssSelectorError("property name is empty")
    tree, order = _document(markup)
    target = next((element for element in order if _attr(element, "id") == element_id), None)
    if target is None:
        return ""
    return _cascaded_map(tree, target, _stylesheet(stylesheet)).get(prop, "")


def _document(markup: str) -> tuple[_Tree, list]:
    if not isinstance(markup, str):
        raise CssSelectorError("markup must be a string")
    root = parse_tree(markup)
    parent: dict = {}
    children: dict = {}
    order: list = []

    def walk(element, owner) -> None:
        parent[element] = owner
        order.append(element)
        kids = [child for child in list(element) if _local_name(child)]
        children[element] = kids
        for child in kids:
            walk(child, element)

    walk(root, None)
    return _Tree(parent, children, order), order


def _local_name(element) -> str:
    tag = element.tag
    if not isinstance(tag, str):
        return ""
    if tag.startswith("{"):
        tag = tag.split("}", 1)[1]
    return tag.lower()


def _attr(element, name: str) -> str | None:
    wanted = name.lower()
    for key, value in element.attrib.items():
        if isinstance(key, str) and key.split("}", 1)[-1].lower() == wanted:
            return value
    return None


def _classes(element) -> frozenset[str]:
    raw = _attr(element, "class")
    if not raw:
        return frozenset()
    return frozenset(part for part in _HTML_SPACE.split(raw) if part)


class _Parser:
    def __init__(self, text: str) -> None:
        self.text = text
        self.length = len(text)
        self.index = 0

    def peek(self) -> str:
        return self.text[self.index] if self.index < self.length else ""

    def skip_space(self) -> None:
        while self.peek() and self.peek().isspace():
            self.index += 1

    def selector_list(self) -> tuple[Complex, ...]:
        self.skip_space()
        if not self.peek():
            raise CssSelectorError("selector is empty")
        items = [self.complex_selector()]
        while True:
            self.skip_space()
            if self.peek() != ",":
                break
            self.index += 1
            self.skip_space()
            items.append(self.complex_selector())
        return tuple(items)

    def complex_selector(self) -> Complex:
        self.skip_space()
        compounds = [self.compound()]
        combinators: list[str] = []
        while True:
            saved = self.index
            self.skip_space()
            if self.peek() in {",", ")", ""}:
                break
            combinator = " "
            if self.peek() in {">", "+", "~"}:
                combinator = self.peek()
                self.index += 1
                self.skip_space()
            elif saved == self.index:
                break
            if not self._simple_start():
                if combinator != " ":
                    raise CssSelectorError("combinator is missing its right selector")
                break
            combinators.append(combinator)
            compounds.append(self.compound())
        return Complex(tuple(tuple(item) for item in compounds), tuple(combinators))

    def relative_selector_list(self) -> tuple[Complex, ...]:
        self.skip_space()
        if not self.peek():
            raise CssSelectorError("selector is empty")
        items = [self.relative_selector()]
        while True:
            self.skip_space()
            if self.peek() != ",":
                break
            self.index += 1
            self.skip_space()
            if not self.peek():
                raise CssSelectorError("selector is empty")
            items.append(self.relative_selector())
        return tuple(items)

    def relative_selector(self) -> Complex:
        self.skip_space()
        anchor = " "
        if self.peek() in {">", "+", "~"}:
            anchor = self.peek()
            self.index += 1
        parsed = self.complex_selector()
        return Complex(parsed.compounds, parsed.combinators, anchor)

    def compound(self) -> list[_Simple]:
        if not self._simple_start():
            raise CssSelectorError("expected a selector")
        items: list[_Simple] = []
        while self._simple_start():
            items.append(self.simple())
        return items

    def simple(self) -> _Simple:
        char = self.peek()
        if char == "*":
            self.index += 1
            return _Simple("universal")
        if char == ".":
            self.index += 1
            return _Simple("class", self.ident())
        if char == "#":
            self.index += 1
            return _Simple("id", self.ident())
        if char == ":":
            return self.pseudo()
        return _Simple("type", self.ident().lower())

    def pseudo(self) -> _Simple:
        self.index += 1
        if self.peek() == ":":
            raise CssSelectorError("pseudo-elements are outside this reader")
        name = self.ident().lower()
        if self.peek() != "(":
            raise CssSelectorError(f":{name} is outside this reader")
        self.index += 1
        argument = self.balanced("(", ")")
        if name in {"is", "not", "where"}:
            selectors = _Parser(argument).selector_list()
            return _Simple("pseudo", name, selectors)
        if name == "has":
            selectors = _Parser(argument).relative_selector_list()
            return _Simple("pseudo", name, selectors)
        if name in {"nth-child", "nth-last-child"}:
            nth, of_selector = _split_of(argument)
            step, offset = _anb(nth)
            selectors = _Parser(of_selector).selector_list() if of_selector else ()
            return _Simple("pseudo", name, selectors, step, offset)
        raise CssSelectorError(f":{name} is outside this reader")

    def balanced(self, open_char: str, close_char: str) -> str:
        depth = 1
        start = self.index
        while self.index < self.length:
            char = self.text[self.index]
            if char == open_char:
                depth += 1
            elif char == close_char:
                depth -= 1
                if depth == 0:
                    argument = self.text[start:self.index]
                    self.index += 1
                    return argument
            self.index += 1
        raise CssSelectorError(f"unclosed {open_char}")

    def ident(self) -> str:
        start = self.index
        if self.peek() == "-":
            self.index += 1
        if not self._ident_char(self.peek(), start=True):
            raise CssSelectorError("expected an identifier")
        self.index += 1
        while self._ident_char(self.peek(), start=False):
            self.index += 1
        return self.text[start:self.index]

    def _simple_start(self) -> bool:
        char = self.peek()
        return char in {"*", ".", "#", ":"} or self._ident_start()

    def _ident_start(self) -> bool:
        char = self.peek()
        if self._ident_char(char, start=True):
            return True
        if char != "-" or self.index + 1 >= self.length:
            return False
        nxt = self.text[self.index + 1]
        return nxt == "-" or self._ident_char(nxt, start=True)

    @staticmethod
    def _ident_char(char: str, *, start: bool) -> bool:
        if not char:
            return False
        if char.isalpha() or char == "_" or ord(char) > 127:
            return True
        if char.isdigit():
            return not start
        return not start and char == "-"


def _split_of(argument: str) -> tuple[str, str]:
    depth = 0
    index = 0
    length = len(argument)
    while index < length:
        char = argument[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif depth == 0 and char.isspace():
            cursor = index
            while cursor < length and argument[cursor].isspace():
                cursor += 1
            if argument[cursor:cursor + 2].lower() == "of":
                after = cursor + 2
                if after >= length or not (argument[after].isalnum() or argument[after] in "_-"):
                    if after < length and argument[after].isspace():
                        while after < length and argument[after].isspace():
                            after += 1
                        return argument[:index].strip(), argument[after:].strip()
        index += 1
    return argument.strip(), ""


def _anb(text: str) -> tuple[int, int]:
    compact = re.sub(r"\s+", "", text.lower())
    if compact in {"odd", "even"}:
        return (2, 1) if compact == "odd" else (2, 0)
    if not compact:
        raise CssSelectorError("nth expression is empty")
    number = _NUMBER.fullmatch(compact)
    if number:
        return 0, int(compact)
    match = _ANB.fullmatch(compact)
    if match is None:
        raise CssSelectorError(f"nth expression {text!r} is invalid")
    raw_step = match.group(1)
    if raw_step in {"", "+"}:
        step = 1
    elif raw_step == "-":
        step = -1
    else:
        step = int(raw_step)
    return step, int(match.group(2) or 0)


def _nth_holds(index: int, step: int, offset: int) -> bool:
    if index <= 0:
        return False
    if step == 0:
        return index == offset
    moved = index - offset
    if moved % step != 0:
        return False
    return moved // step >= 0


def _selector_list(selector: str) -> tuple[Complex, ...]:
    if not isinstance(selector, str):
        raise CssSelectorError("selector must be a string")
    parser = _Parser(_strip_comments(selector))
    compiled = parser.selector_list()
    parser.skip_space()
    if parser.peek():
        raise CssSelectorError("trailing text after selector")
    return compiled


def _strip_comments(text: str) -> str:
    pieces: list[str] = []
    index = 0
    while index < len(text):
        if text.startswith("/*", index):
            end = text.find("*/", index + 2)
            if end < 0:
                raise CssSelectorError("unclosed comment")
            index = end + 2
            continue
        pieces.append(text[index])
        index += 1
    return "".join(pieces)


def _specificity(selector: Complex) -> tuple[int, int, int]:
    ids = classes = types = 0
    for compound in selector.compounds:
        for simple in compound:
            if simple.kind == "id":
                ids += 1
            elif simple.kind == "class":
                classes += 1
            elif simple.kind == "type":
                types += 1
            elif simple.kind == "pseudo":
                gained = _pseudo_specificity(simple)
                ids += gained[0]
                classes += gained[1]
                types += gained[2]
    return ids, classes, types


def _pseudo_specificity(simple: _Simple) -> tuple[int, int, int]:
    if simple.name == "where":
        return 0, 0, 0
    if simple.name in {"is", "not", "has"}:
        return max((_specificity(item) for item in simple.selectors), default=(0, 0, 0))
    if simple.name in {"nth-child", "nth-last-child"}:
        extra = max((_specificity(item) for item in simple.selectors), default=(0, 0, 0))
        return extra[0], extra[1] + 1, extra[2]
    raise CssSelectorError(f":{simple.name} has no specificity")


def _list_matches(tree: _Tree, element, selectors: tuple[Complex, ...]) -> bool:
    return any(_complex_matches(tree, element, selector) for selector in selectors)


def _matching_specificity(tree: _Tree, element, selectors: tuple[Complex, ...]) -> tuple[int, int, int] | None:
    matched = [_specificity(selector) for selector in selectors if _complex_matches(tree, element, selector)]
    if not matched:
        return None
    return max(matched)


def _complex_matches(tree: _Tree, element, selector: Complex) -> bool:
    return _chain(tree, element, selector, len(selector.compounds) - 1)


def _chain(tree: _Tree, element, selector: Complex, index: int) -> bool:
    if not _compound_matches(tree, element, selector.compounds[index]):
        return False
    if index == 0:
        return True
    combinator = selector.combinators[index - 1]
    if combinator == ">":
        parent = tree.parent.get(element)
        return parent is not None and _chain(tree, parent, selector, index - 1)
    if combinator == "+":
        previous = _neighbor(tree, element, -1)
        return previous is not None and _chain(tree, previous, selector, index - 1)
    if combinator == " ":
        parent = tree.parent.get(element)
        while parent is not None:
            if _chain(tree, parent, selector, index - 1):
                return True
            parent = tree.parent.get(parent)
        return False
    if combinator == "~":
        previous = _neighbor(tree, element, -1)
        while previous is not None:
            if _chain(tree, previous, selector, index - 1):
                return True
            previous = _neighbor(tree, previous, -1)
        return False
    return False


def _identity_index(elements: list, element) -> int:
    for index, item in enumerate(elements):
        if item is element:
            return index
    raise ValueError(element)


def _anchored_matches(tree: _Tree, scope, selector: Complex) -> bool:
    return any(
        _match_forward(tree, start, selector, 0) for start in _related(tree, scope, selector.anchor)
    )


def _match_forward(tree: _Tree, element, selector: Complex, index: int) -> bool:
    if not _compound_matches(tree, element, selector.compounds[index]):
        return False
    if index + 1 == len(selector.compounds):
        return True
    combinator = selector.combinators[index]
    return any(
        _match_forward(tree, nxt, selector, index + 1) for nxt in _related(tree, element, combinator)
    )


def _related(tree: _Tree, element, combinator: str):
    if combinator == ">":
        return list(tree.children.get(element, ()))
    if combinator == "+":
        nxt = _neighbor(tree, element, 1)
        return [] if nxt is None else [nxt]
    if combinator == "~":
        found = []
        nxt = _neighbor(tree, element, 1)
        while nxt is not None:
            found.append(nxt)
            nxt = _neighbor(tree, nxt, 1)
        return found
    if combinator == " ":
        found = []
        pending = list(tree.children.get(element, ()))
        while pending:
            current = pending.pop()
            found.append(current)
            pending.extend(tree.children.get(current, ()))
        return found
    return []


def _neighbor(tree: _Tree, element, direction: int):
    parent = tree.parent.get(element)
    if parent is None:
        return None
    siblings = tree.children[parent]
    position = _identity_index(siblings, element) + direction
    if position < 0 or position >= len(siblings):
        return None
    return siblings[position]


def _compound_matches(tree: _Tree, element, compound: tuple[_Simple, ...]) -> bool:
    return all(_simple_matches(tree, element, simple) for simple in compound)


def _simple_matches(tree: _Tree, element, simple: _Simple) -> bool:
    if simple.kind == "universal":
        return True
    if simple.kind == "type":
        return _local_name(element) == simple.name
    if simple.kind == "class":
        return simple.name in _classes(element)
    if simple.kind == "id":
        return _attr(element, "id") == simple.name
    if simple.name in {"is", "where"}:
        return _list_matches(tree, element, simple.selectors)
    if simple.name == "has":
        return any(_anchored_matches(tree, element, selector) for selector in simple.selectors)
    if simple.name == "not":
        return not _list_matches(tree, element, simple.selectors)
    if simple.name in {"nth-child", "nth-last-child"}:
        return _nth_matches(tree, element, simple)
    return False


def _nth_matches(tree: _Tree, element, simple: _Simple) -> bool:
    parent = tree.parent.get(element)
    siblings = [element] if parent is None else list(tree.children[parent])
    if simple.selectors:
        siblings = [item for item in siblings if _list_matches(tree, item, simple.selectors)]
    try:
        position = _identity_index(siblings, element) + 1
    except ValueError:
        return False
    if simple.name == "nth-last-child":
        position = len(siblings) - position + 1
    return _nth_holds(position, simple.a, simple.b)


def _stylesheet(stylesheet: str) -> list[_Decl]:
    if not isinstance(stylesheet, str):
        raise CssSelectorError("stylesheet must be a string")
    parser = _Parser(_strip_comments(stylesheet))
    declarations: list[_Decl] = []
    order = 0
    while True:
        parser.skip_space()
        if not parser.peek():
            return declarations
        if parser.peek() == "@":
            raise CssSelectorError("at-rules are outside this reader")
        selectors = parser.selector_list()
        parser.skip_space()
        if parser.peek() != "{":
            raise CssSelectorError("expected a declaration block")
        parser.index += 1
        body = parser.balanced("{", "}")
        for chunk in body.split(";"):
            if not chunk.strip():
                continue
            if ":" not in chunk:
                raise CssSelectorError("declaration is missing a colon")
            name, raw_value = chunk.split(":", 1)
            prop = _property_key(name)
            value, important = _important(raw_value.strip())
            if not prop or not value:
                raise CssSelectorError("declaration is empty")
            declarations.append(_Decl(selectors, prop, value, important, order))
            order += 1


def _important(value: str) -> tuple[str, bool]:
    match = re.search(r"^(.*?)!important\s*\Z", value, re.IGNORECASE | re.DOTALL)
    if match is None:
        return value.strip(), False
    return match.group(1).strip(), True


def _property_key(name: str) -> str:
    """Custom properties keep author case. Every other property is ASCII-lower."""

    text = name.strip()
    if text.startswith("--"):
        return text
    return text.lower()


def _cascaded_map(tree: _Tree, element, declarations: list[_Decl]) -> dict[str, str]:
    winners: dict[str, tuple[tuple[bool, tuple[int, int, int], int], str]] = {}
    for decl in declarations:
        specificity = _matching_specificity(tree, element, decl.selectors)
        if specificity is None:
            continue
        key = (decl.important, specificity, decl.order)
        current = winners.get(decl.prop)
        if current is None or key > current[0]:
            winners[decl.prop] = (key, decl.value)
    return {prop: value for prop, (_rank, value) in winners.items()}


class _GuaranteedInvalid:
    """Initial value of a custom property, and the result of a failed substitution."""


_INVALID = _GuaranteedInvalid()
_WIDE_KEYWORDS = frozenset({"inherit", "initial", "unset", "revert"})


def computed_value(markup: str, stylesheet: str, element_id: str, property_name: str) -> str:
    """Computed value of one property on ``element_id``.

    Custom properties and ``color`` inherit. A guaranteed-invalid custom
    property serializes as the empty string. A valid empty custom property
    serializes as one space. Any other property is substituted from its own
    cascaded declaration and does not inherit.
    """

    if not isinstance(element_id, str) or not element_id:
        raise CssSelectorError("element id must be a non-empty string")
    prop = _property_key(property_name)
    if not prop:
        raise CssSelectorError("property name is empty")
    tree, order = _document(markup)
    declarations = _stylesheet(stylesheet)
    styles: dict = {}
    for element in order:
        parent = tree.parent.get(element)
        parent_custom, parent_color = styles.get(parent, ({}, ""))
        styles[element] = _computed_style(tree, element, declarations, parent_custom, parent_color)
    target = next((element for element in order if _attr(element, "id") == element_id), None)
    if target is None:
        return ""
    custom, color = styles[target]
    if prop.startswith("--"):
        return custom.get(prop, "")
    if prop == "color":
        return color
    raw = _cascaded_map(tree, target, declarations).get(prop)
    if raw is None or _wide_keyword(raw) is not None:
        return ""
    substituted = _substitute(raw, lambda name: custom.get(name, _INVALID))
    if substituted is _INVALID:
        return ""
    return substituted


def _computed_style(
    tree: _Tree,
    element,
    declarations: list[_Decl],
    parent_custom: dict[str, str],
    parent_color: str,
) -> tuple[dict[str, str], str]:
    winners = _cascaded_map(tree, element, declarations)
    specified: dict[str, str] = {}
    forced_invalid: set[str] = set()
    for name, value in winners.items():
        if not name.startswith("--"):
            continue
        keyword = _wide_keyword(value)
        if keyword in {"inherit", "unset"}:
            continue
        if keyword in {"initial", "revert"}:
            forced_invalid.add(name)
            continue
        specified[name] = value
    dependencies = {name: _active_dependencies(value) for name, value in specified.items()}
    cyclic = _cyclic_properties(dependencies)
    memo: dict[str, str | _GuaranteedInvalid] = {}
    resolving: set[str] = set()

    def lookup(name: str) -> str | _GuaranteedInvalid:
        if name in resolving:
            return _INVALID
        if name in memo:
            return memo[name]
        if name in cyclic or name in forced_invalid:
            memo[name] = _INVALID
            return _INVALID
        if name in specified:
            return resolve(name)
        return parent_custom.get(name, _INVALID)

    def resolve(name: str) -> str | _GuaranteedInvalid:
        if name in memo:
            return memo[name]
        if name in cyclic or name in forced_invalid:
            memo[name] = _INVALID
            return _INVALID
        resolving.add(name)
        try:
            value = _substitute(specified[name], lookup)
        finally:
            resolving.discard(name)
        memo[name] = value
        return value

    custom = dict(parent_custom)
    for name in forced_invalid:
        custom.pop(name, None)
    for name in specified:
        value = resolve(name)
        if value is _INVALID:
            custom.pop(name, None)
            continue
        custom[name] = " " if value == "" else value
    color = _computed_color(winners.get("color"), parent_color, lambda name: custom.get(name, _INVALID))
    return custom, color


def _computed_color(raw: str | None, parent_color: str, lookup) -> str:
    if raw is None:
        return parent_color
    keyword = _wide_keyword(raw)
    if keyword in {"inherit", "unset"}:
        return parent_color
    if keyword in {"initial", "revert"}:
        return ""
    substituted = _substitute(raw, lookup)
    if substituted is _INVALID or not substituted.strip():
        return parent_color
    return substituted


def _wide_keyword(value: str) -> str | None:
    token = value.strip().lower()
    if token in _WIDE_KEYWORDS:
        return token
    return None


def _cyclic_properties(dependencies: dict[str, tuple[str, ...]]) -> set[str]:
    """Names that sit on a cycle of used ``var()`` first arguments.

    A fallback is not an edge. Issue 11500 made ``var()`` short-circuit, so a
    cycle that exists only inside an unused fallback is not a cycle. A property
    that does sit on a cycle is wholly guaranteed-invalid; its own fallback is
    not applied.
    """

    cyclic: set[str] = set()
    color: dict[str, int] = {}
    stack: list[str] = []

    def visit(name: str) -> None:
        color[name] = 1
        stack.append(name)
        for nxt in dependencies.get(name, ()):
            if nxt not in dependencies:
                continue
            state = color.get(nxt, 0)
            if state == 1:
                cyclic.update(stack[stack.index(nxt) :])
            elif state == 0:
                visit(nxt)
        stack.pop()
        color[name] = 2

    for name in dependencies:
        if color.get(name, 0) == 0:
            visit(name)
    return cyclic


def _active_dependencies(value: str) -> tuple[str, ...]:
    found: list[str] = []
    _scan_dependencies(value, found)
    return tuple(found)


def _scan_dependencies(text: str, found: list[str]) -> None:
    index = 0
    while index < len(text):
        if text[index] in "\"'":
            index = _skip_string(text, index)
            continue
        if _var_at(text, index):
            argument, __, end = _split_var(text, index)
            _scan_dependencies(argument, found)
            literal = _literal_custom_name(argument)
            if literal is not None:
                found.append(literal)
            index = end
            continue
        index += 1


def _substitute(text: str, lookup) -> str | _GuaranteedInvalid:
    parts: list[str] = []
    index = 0
    while index < len(text):
        if text[index] in "\"'":
            end = _skip_string(text, index)
            parts.append(text[index:end])
            index = end
            continue
        if _var_at(text, index):
            argument, fallback, end = _split_var(text, index)
            name = _resolve_custom_name(argument, lookup)
            result: str | _GuaranteedInvalid = _INVALID if name is None else lookup(name)
            if result is _INVALID:
                if fallback is None:
                    return _INVALID
                result = _substitute(fallback.strip(), lookup)
                if result is _INVALID:
                    return _INVALID
            parts.append(result)
            index = end
            continue
        parts.append(text[index])
        index += 1
    return "".join(parts)


def _resolve_custom_name(argument: str, lookup) -> str | None:
    substituted = _substitute(argument, lookup)
    if substituted is _INVALID:
        return None
    return _literal_custom_name(substituted)


def _literal_custom_name(text: str) -> str | None:
    token = text.strip()
    if len(token) < 3 or not token.startswith("--"):
        return None
    if any(char.isspace() or char in "(),{}:;\"'\\/" for char in token):
        return None
    return token


def _var_at(text: str, index: int) -> bool:
    if not text.startswith("var", index):
        return False
    if index > 0 and _ident_char(text[index - 1]):
        return False
    cursor = index + 3
    if cursor < len(text) and _ident_char(text[cursor]):
        return False
    while cursor < len(text) and text[cursor] in " \t\n\f\r":
        cursor += 1
    return cursor < len(text) and text[cursor] == "("


def _ident_char(char: str) -> bool:
    return char.isalnum() or char in "_-" or ord(char) > 127


def _split_var(text: str, index: int) -> tuple[str, str | None, int]:
    open_paren = text.find("(", index)
    if open_paren < 0:
        raise CssSelectorError("var( is missing its opening parenthesis")
    depth = 1
    cursor = open_paren + 1
    comma: int | None = None
    while cursor < len(text) and depth:
        if text[cursor] in "\"'":
            cursor = _skip_string(text, cursor)
            continue
        char = text[cursor]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                break
        elif char == "," and depth == 1 and comma is None:
            comma = cursor
        cursor += 1
    if depth != 0:
        raise CssSelectorError("unclosed var(")
    if comma is None:
        return text[open_paren + 1 : cursor], None, cursor + 1
    return text[open_paren + 1 : comma], text[comma + 1 : cursor], cursor + 1


def _skip_string(text: str, index: int) -> int:
    quote = text[index]
    index += 1
    while index < len(text):
        if text[index] == "\\":
            index += 2
            continue
        if text[index] == quote:
            return index + 1
        index += 1
    raise CssSelectorError("unclosed string")
