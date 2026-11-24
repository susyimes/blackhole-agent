"""Match CSS selectors and resolve author declarations.

Selectors Level 4 counts ``:nth-child(An+B of S)`` only among siblings that
match S. ``:is()`` and ``:not()`` take the specificity of their most specific
argument even when a less specific argument matched. ``:where()`` adds none.
``:has()`` matches when a relative selector reaches another element: a missing
combinator means a descendant, and ``>``, ``+``, and ``~`` keep their usual
direction. Its specificity is the most specific argument. An author
``!important`` declaration beats a normal declaration of higher specificity.
The reader covers type, class, id, attribute selectors, the universal selector,
and the descendant, child, next-sibling, and subsequent-sibling combinators.
An attribute has specificity (0, 1, 0). Presence matches an empty value.
``=``, ``~=``, ``|=``, ``^=``, ``$=``, and ``*=`` compare the stored value.
In an HTML element, the HTML keyword attributes (including ``type``, ``lang``,
and ``rel``) fold ASCII case unless the ``s`` flag is set. Other values,
including ``href`` and ``data-*``, stay sensitive unless the ``i`` flag is set.
An empty ``~=``, ``|=``, ``^=``, ``$=``, or ``*=`` value, a whitespace word,
two flags, or a namespace prefix is rejected.

``computed_value`` substitutes ``var()`` after the cascade. A custom property
inherits the value its parent already computed, so a child that overrides a
dependency does not retarget that inherited value. A cycle is
guaranteed-invalid even when the cyclic declaration carries a fallback. A
fallback on a property outside the cycle still applies, and a fallback that
is never used does not create a cycle. ``@layer`` orders author rules by
first appearance: nested layers sit before the rules of their parent,
unlayered rules come last, and ``!important`` reverses that order.
``revert-layer`` drops every declaration in its current layer and continues
with the layer below. ``@scope`` keeps a style rule on the inclusive
descendants of one scope root and off the inclusive descendants of its
limits. Selectors in the block are relative to that root unless they contain
``:scope`` or ``&``; the prelude does not add specificity. ``:scope`` is
(0, 1, 0) and ``&`` is (0, 0, 0). Specificity still outranks scope proximity,
and proximity outranks source order. A rule with no scope root is infinitely
far. A valid ``@property`` rule registers a custom property; the last valid
rule for that name wins. The rule needs a syntax string and ``inherits``.
A syntax other than ``*`` also needs a computationally independent initial
value that matches it. ``inherits: false`` does not pass the parent value
down. A non-universal value that fails its syntax, including a cycle,
computes to that initial value. ``*`` still becomes guaranteed-invalid on a
cycle. An invalid rule leaves the name unregistered. This reader accepts
``<color>``, ``<length>``, ``<percentage>``, ``<length-percentage>``,
``<number>``, ``<integer>``, ``<angle>``, ``<time>``, ``<custom-ident>``,
literal idents, and the ``|``, ``+``, and ``#`` operators. It keeps a
matching token as written: no unit or color canonicalization, and
``calc()``, ``currentcolor``, and relative units cannot be an initial value.
A style rule may contain another style rule. ``&`` is that parent selector
list wrapped in ``:is()``, so the nested rule takes the most specific
parent's specificity for every parent. A nested selector with no ``&`` is
relative to the parent: a leading combinator is kept, and the default
combinator is a descendant. An invalid nested selector is dropped with its
block and leaves the parent rule in place. The same expansion works inside
``@scope``: the inner rule keeps that scope's root, limit, and proximity.
A scope-relative parent keeps its implied relationship after ``&``
substitution, and that relationship adds no specificity. An invalid inner
selector still does not discard the parent declaration or later rules.
``@media`` keeps its block only when
the query matches the media map: type, width, height, derived orientation,
``prefers-color-scheme``, and ``prefers-reduced-motion``. Lengths are px.
``not``, ``and``, ``or``, a comma, and ``only`` follow Media Queries 4. A
query nested in a style rule uses that rule's selectors. An unknown feature
or a malformed query does not match, and later rules stay. ``@supports``
keeps its block when the condition is supported: ``color`` accepts a color
or a CSS-wide keyword, a custom property accepts any non-empty value, and
``selector()`` accepts one complex selector this reader can parse.
A trailing ``::before`` or ``::after`` is one of those selectors. It does not
match the element; the layout engine reads it as generated content. Any
other pseudo-element, and a pseudo-element in an ``@scope`` boundary, is
rejected.
``font-tech()``, ``font-format()``, and any other function are unsupported.
``not``, ``and``, and ``or`` combine those answers. An empty prelude or a
mix of ``and`` and ``or`` drops that block and leaves later rules. The block
stays in its layer, scope, and nesting parent. Animation tainting stays
outside. ``@container`` stays out of the unconditional cascade when the
caller collects container rules; those declarations keep their source order
for a later query match. Without that collection the at-rule is rejected.
``@font-face`` is collected only when the caller asks for faces. The rule
needs ``font-family``. ``font-weight``, ``font-style``, ``font-stretch``,
``unicode-range``, ``src``, and ``font-display`` may follow. Without that
collection the at-rule is rejected.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from blackhole_agent.html5_document import parse_tree


_HTML_SPACE = re.compile(r"[ \t\n\f\r]+")
_ANB = re.compile(r"([+-]?(?:\d+)?)n([+-]\d+)?\Z")
_NUMBER = re.compile(r"[+-]?\d+\Z")
_HTML_NAMESPACE = "http://www.w3.org/1999/xhtml"
_ASCII_LOWER = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")
# HTML: these attribute values fold ASCII case in selectors unless `s` is set.
_HTML_CASELESS_ATTRIBUTES = frozenset(
    {
        "accept",
        "accept-charset",
        "align",
        "alink",
        "axis",
        "bgcolor",
        "charset",
        "checked",
        "clear",
        "codetype",
        "color",
        "compact",
        "declare",
        "defer",
        "dir",
        "direction",
        "disabled",
        "enctype",
        "face",
        "frame",
        "hreflang",
        "http-equiv",
        "lang",
        "language",
        "link",
        "media",
        "method",
        "multiple",
        "nohref",
        "noresize",
        "noshade",
        "nowrap",
        "readonly",
        "rel",
        "rev",
        "rules",
        "scope",
        "scrolling",
        "selected",
        "shape",
        "target",
        "text",
        "type",
        "valign",
        "valuetype",
        "vlink",
    }
)


class CssSelectorError(ValueError):
    """A selector or stylesheet is outside the supported grammar."""


class _PseudoMatch:
    """When set, a trailing ``::before`` or ``::after`` matches its element.

    Element cascade leaves this empty, so a pseudo-element selector does not
    style the element. Generated content sets the name for one lookup.
    """

    name: str | None = None


@dataclass(frozen=True)
class _Simple:
    kind: str
    name: str = ""
    selectors: tuple[Complex, ...] = ()
    a: int = 0
    b: int = 0
    operator: str = ""
    value: str = ""
    case: str = ""


@dataclass(frozen=True)
class Complex:
    compounds: tuple[tuple[_Simple, ...], ...]
    combinators: tuple[str, ...]
    anchor: str = ""


@dataclass(frozen=True)
class _ScopeFrame:
    """One ``@scope``. An inner start selector is relative to the outer root."""

    start: tuple[Complex, ...] | None
    end: tuple[Complex, ...] | None
    start_relative: bool


@dataclass(frozen=True)
class _Decl:
    selectors: tuple[Complex, ...]
    prop: str
    value: str
    important: bool
    order: int
    layer: int
    scopes: tuple[_ScopeFrame, ...] = ()


@dataclass(frozen=True)
class _SyntaxPart:
    name: str
    multiplier: str = ""


@dataclass(frozen=True)
class _Syntax:
    universal: bool
    parts: tuple[_SyntaxPart, ...] = ()


@dataclass(frozen=True)
class _Registration:
    syntax: _Syntax
    inherits: bool
    initial: str | None


@dataclass
class _Tree:
    parent: dict
    children: dict
    order: list
    scope_cache: dict = field(default_factory=dict)


# Fewer generational hops win. An unscoped rule is farther than any real scope.
_UNSCOPED = 1_000_000_000
_ROOT_RULE = (Complex(((_Simple("pseudo", "scope-amp"),),), ()),)


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


def cascaded_value(
    markup: str,
    stylesheet: str,
    element_id: str,
    property_name: str,
    *,
    media: dict | None = None,
) -> str:
    """Winning author value for ``element_id``, or empty when none applies.

    ``media`` supplies the viewport for ``@media``. Width and height are px.
    Orientation is landscape when width is greater than height. An omitted
    map is a screen of zero width and height.
    """

    if not isinstance(element_id, str) or not element_id:
        raise CssSelectorError("element id must be a non-empty string")
    prop = _property_key(property_name)
    if not prop:
        raise CssSelectorError("property name is empty")
    tree, order = _document(markup)
    target = next((element for element in order if _attr(element, "id") == element_id), None)
    if target is None:
        return ""
    declarations, _registered = _stylesheet(stylesheet, media=media)
    return _cascaded_map(tree, target, declarations).get(prop, "")


def matching_elements(root, selector: str) -> list:
    """Match an already parsed, possibly mutated tree without serializing it."""

    tree, order = _tree(root)
    compiled = _selector_list(selector)
    return [element for element in order if _list_matches(tree, element, compiled)]


def cascaded_element_value(
    root,
    element,
    stylesheet: str,
    property_name: str,
    *,
    media: dict | None = None,
) -> str:
    """Resolve one element's author value in an already parsed live tree."""

    prop = _property_key(property_name)
    if not prop:
        raise CssSelectorError("property name is empty")
    tree, order = _tree(root)
    if element not in order:
        return ""
    declarations, _registered = _stylesheet(stylesheet, media=media)
    return _cascaded_map(tree, element, declarations).get(prop, "")


def _document(markup: str) -> tuple[_Tree, list]:
    if not isinstance(markup, str):
        raise CssSelectorError("markup must be a string")
    return _tree(parse_tree(markup))


def _tree(root) -> tuple[_Tree, list]:
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


def _ascii_lower(text: str) -> str:
    return text.translate(_ASCII_LOWER)


def _html_element(element) -> bool:
    tag = element.tag
    if not isinstance(tag, str):
        return False
    if tag.startswith("{") and "}" in tag:
        return tag[1:].split("}", 1)[0] == _HTML_NAMESPACE
    return True


def _attribute_values_fold(element, simple: _Simple) -> bool:
    if simple.case == "i":
        return True
    if simple.case == "s":
        return False
    return _html_element(element) and simple.name in _HTML_CASELESS_ATTRIBUTES


def _attribute_matches(element, simple: _Simple) -> bool:
    raw = _attr(element, simple.name)
    if raw is None:
        return False
    if not simple.operator:
        return True
    actual = raw
    expected = simple.value
    if _attribute_values_fold(element, simple):
        actual = _ascii_lower(actual)
        expected = _ascii_lower(expected)
    operator = simple.operator
    if operator == "=":
        return actual == expected
    if operator == "~=":
        if not expected or any(char in " \t\n\r\f" for char in expected):
            return False
        return expected in _HTML_SPACE.split(actual)
    if operator == "|=":
        return bool(expected) and (actual == expected or actual.startswith(expected + "-"))
    if operator == "^=":
        return bool(expected) and actual.startswith(expected)
    if operator == "$=":
        return bool(expected) and actual.endswith(expected)
    if operator == "*=":
        return bool(expected) and expected in actual
    return False


class _Parser:
    def __init__(self, text: str, *, nesting: bool = False, style_nesting: bool = False) -> None:
        self.text = text
        self.length = len(text)
        self.index = 0
        self.nesting = nesting
        self.style_nesting = style_nesting

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

    def scoped_selector_list(self) -> tuple[Complex, ...]:
        """Selectors inside ``@scope``: implied ``:scope`` descendant unless anchored."""

        self.skip_space()
        if not self.peek():
            raise CssSelectorError("selector is empty")
        items = [self.scoped_complex()]
        while True:
            self.skip_space()
            if self.peek() != ",":
                break
            self.index += 1
            self.skip_space()
            if not self.peek():
                raise CssSelectorError("selector is empty")
            items.append(self.scoped_complex())
        return tuple(items)

    def scoped_complex(self) -> Complex:
        self.skip_space()
        if self.peek() in {">", "+", "~"}:
            return self.relative_selector()
        parsed = self.complex_selector()
        if _contains_scope_ref(parsed):
            return parsed
        return Complex(parsed.compounds, parsed.combinators, " ")

    def nested_selector_list(self) -> tuple[Complex, ...]:
        """Relative selectors inside a style rule. ``&`` refers to the parent."""

        self.skip_space()
        if not self.peek():
            raise CssSelectorError("selector is empty")
        items = [self.nested_complex()]
        while True:
            self.skip_space()
            if self.peek() != ",":
                break
            self.index += 1
            self.skip_space()
            if not self.peek():
                raise CssSelectorError("selector is empty")
            items.append(self.nested_complex())
        return tuple(items)

    def nested_complex(self) -> Complex:
        self.skip_space()
        if self.peek() in {">", "+", "~"}:
            return self.relative_selector()
        return self.complex_selector()

    def next_kind(self) -> str:
        kind, _end = self._classify_at(self.index)
        return kind

    def take_prelude(self) -> str:
        kind, end = self._classify_at(self.index)
        if kind != "rule":
            raise CssSelectorError("expected a declaration block")
        prelude = self.text[self.index:end]
        self.index = end + 1
        return prelude

    def take_declaration(self) -> str:
        _kind, end = self._classify_at(self.index)
        text = self.text[self.index:end]
        if end < self.length and self.text[end] == ";":
            self.index = end + 1
        else:
            self.index = end
        return text

    def _classify_at(self, index: int) -> tuple[str, int]:
        depth = 0
        while index < self.length:
            char = self.text[index]
            if char in "\"'":
                index = _skip_string(self.text, index)
                continue
            if char == "(":
                depth += 1
            elif char == ")" and depth:
                depth -= 1
            elif depth == 0 and char == "{":
                return "rule", index
            elif depth == 0 and char == ";":
                return "decl", index
            index += 1
        return "decl", self.length

    def compound(self) -> list[_Simple]:
        if not self._simple_start():
            raise CssSelectorError("expected a selector")
        items: list[_Simple] = []
        while self._simple_start():
            item = self.simple()
            if self.style_nesting and item.kind == "type" and items:
                raise CssSelectorError("a type selector must come first in a compound")
            items.append(item)
        return items

    def simple(self) -> _Simple:
        char = self.peek()
        if char == "[":
            return self.attribute()
        if char == "&":
            self.index += 1
            if self.style_nesting:
                return _Simple("pseudo", "nest")
            if not self.nesting:
                raise CssSelectorError("& is outside this reader")
            return _Simple("pseudo", "scope-amp")
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
            self.index += 1
            name = self.ident().lower()
            if name not in {"before", "after"} or self.peek() == "(":
                raise CssSelectorError("pseudo-elements are outside this reader")
            return _Simple("pseudo-element", name)
        name = self.ident().lower()
        if name in {"before", "after"} and self.peek() != "(":
            return _Simple("pseudo-element", name)
        if name == "scope":
            if self.peek() == "(":
                raise CssSelectorError(":scope does not take arguments")
            return _Simple("pseudo", "scope")
        if self.peek() != "(":
            raise CssSelectorError(f":{name} is outside this reader")
        self.index += 1
        argument = self.balanced("(", ")")
        child = {"nesting": self.nesting, "style_nesting": self.style_nesting}
        if name in {"is", "not", "where"}:
            selectors = _Parser(argument, **child).selector_list()
            return _Simple("pseudo", name, selectors)
        if name == "has":
            selectors = _Parser(argument, **child).relative_selector_list()
            return _Simple("pseudo", name, selectors)
        if name in {"nth-child", "nth-last-child"}:
            nth, of_selector = _split_of(argument)
            step, offset = _anb(nth)
            selectors = _Parser(of_selector, **child).selector_list() if of_selector else ()
            return _Simple("pseudo", name, selectors, step, offset)
        raise CssSelectorError(f":{name} is outside this reader")

    def attribute(self) -> _Simple:
        self.index += 1
        self.skip_space()
        if self.peek() in {"*", "|"}:
            raise CssSelectorError("attribute namespaces are outside this reader")
        name = self.ident().lower()
        self.skip_space()
        if self.peek() == "|":
            nxt = self.text[self.index + 1] if self.index + 1 < self.length else ""
            if nxt != "=":
                raise CssSelectorError("attribute namespaces are outside this reader")
        if self.peek() == "]":
            self.index += 1
            return _Simple("attribute", name)
        operator = ""
        if self.peek() in "~|^$*":
            operator = self.peek()
            self.index += 1
            if self.peek() != "=":
                raise CssSelectorError("attribute matcher is missing equals")
        if self.peek() != "=":
            raise CssSelectorError("expected an attribute matcher")
        self.index += 1
        operator = f"{operator}="
        self.skip_space()
        value = self.attribute_value()
        self.skip_space()
        flag = ""
        if self._ident_start():
            flag = self.ident().lower()
            if flag not in {"i", "s"}:
                raise CssSelectorError("attribute case flag is outside this reader")
            self.skip_space()
            if self._ident_start():
                raise CssSelectorError("attribute selector has two case flags")
        if self.peek() != "]":
            raise CssSelectorError("unclosed attribute selector")
        self.index += 1
        if operator == "~=" and (value == "" or any(char in " \t\n\r\f" for char in value)):
            raise CssSelectorError("attribute word contains whitespace")
        if operator != "=" and value == "":
            raise CssSelectorError("attribute matcher value is empty")
        return _Simple("attribute", name, operator=operator, value=value, case=flag)

    def attribute_value(self) -> str:
        quote = self.peek()
        if quote in {"'", '"'}:
            self.index += 1
            chars: list[str] = []
            while self.peek() and self.peek() != quote:
                if self.peek() == "\\":
                    self.index += 1
                    escaped = self.peek()
                    if not escaped:
                        raise CssSelectorError("attribute string escape is unfinished")
                    if escaped not in "\n\r\f":
                        chars.append(escaped)
                    self.index += 1
                    continue
                if self.peek() in "\n\r\f":
                    raise CssSelectorError("attribute string contains a newline")
                chars.append(self.peek())
                self.index += 1
            if self.peek() != quote:
                raise CssSelectorError("unclosed attribute string")
            self.index += 1
            return "".join(chars)
        if not self._ident_start():
            raise CssSelectorError("expected an attribute value")
        return self.ident()

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
        if char == "&":
            return self.nesting or self.style_nesting
        return char in {"*", ".", "#", ":", "["} or self._ident_start()

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
            elif simple.kind in {"class", "attribute"}:
                classes += 1
            elif simple.kind == "type":
                types += 1
            elif simple.kind == "pseudo":
                gained = _pseudo_specificity(simple)
                ids += gained[0]
                classes += gained[1]
                types += gained[2]
            elif simple.kind == "pseudo-element":
                types += 1
    return ids, classes, types


def _pseudo_specificity(simple: _Simple) -> tuple[int, int, int]:
    if simple.name in {"where", "scope-amp"}:
        return 0, 0, 0
    if simple.name == "scope":
        return 0, 1, 0
    if simple.name in {"is", "not", "has"}:
        return max((_specificity(item) for item in simple.selectors), default=(0, 0, 0))
    if simple.name in {"nth-child", "nth-last-child"}:
        extra = max((_specificity(item) for item in simple.selectors), default=(0, 0, 0))
        return extra[0], extra[1] + 1, extra[2]
    raise CssSelectorError(f":{simple.name} has no specificity")


def _contains_scope_ref(selector: Complex) -> bool:
    def simple(item: _Simple) -> bool:
        if item.kind == "pseudo" and item.name in {"scope", "scope-amp"}:
            return True
        return any(_contains_scope_ref(child) for child in item.selectors)

    return any(simple(item) for compound in selector.compounds for item in compound)


def _list_matches(tree: _Tree, element, selectors: tuple[Complex, ...], scope_el=None) -> bool:
    """Match one selector. An anchored selector stays relative to ``scope_el``.

    Nesting wraps a scope-relative parent in ``:is()``. The parent's implied
    relationship is an anchor, not a written ``:scope``, so it must still
    apply or ``> span { em }`` inside ``@scope`` would match every span.
    """

    return any(_one_matches(tree, element, selector, scope_el) for selector in selectors)


def _matching_specificity(
    tree: _Tree, element, selectors: tuple[Complex, ...], scope_el=None
) -> tuple[int, int, int] | None:
    matched = [
        _specificity(selector)
        for selector in selectors
        if _complex_matches(tree, element, selector, scope_el)
    ]
    if not matched:
        return None
    return max(matched)


def _complex_matches(tree: _Tree, element, selector: Complex, scope_el=None) -> bool:
    return _chain(tree, element, selector, len(selector.compounds) - 1, scope_el)


def _chain(tree: _Tree, element, selector: Complex, index: int, scope_el=None) -> bool:
    if not _compound_matches(tree, element, selector.compounds[index], scope_el):
        return False
    if index == 0:
        return True
    combinator = selector.combinators[index - 1]
    if combinator == ">":
        parent = tree.parent.get(element)
        return parent is not None and _chain(tree, parent, selector, index - 1, scope_el)
    if combinator == "+":
        previous = _neighbor(tree, element, -1)
        return previous is not None and _chain(tree, previous, selector, index - 1, scope_el)
    if combinator == " ":
        parent = tree.parent.get(element)
        while parent is not None:
            if _chain(tree, parent, selector, index - 1, scope_el):
                return True
            parent = tree.parent.get(parent)
        return False
    if combinator == "~":
        previous = _neighbor(tree, element, -1)
        while previous is not None:
            if _chain(tree, previous, selector, index - 1, scope_el):
                return True
            previous = _neighbor(tree, previous, -1)
        return False
    return False


def _identity_index(elements: list, element) -> int:
    for index, item in enumerate(elements):
        if item is element:
            return index
    raise ValueError(element)


def _anchored_matches(tree: _Tree, scope, selector: Complex, scope_el=None) -> bool:
    return any(
        _match_forward(tree, start, selector, 0, scope_el)
        for start in _related(tree, scope, selector.anchor)
    )


def _match_forward(tree: _Tree, element, selector: Complex, index: int, scope_el=None) -> bool:
    if not _compound_matches(tree, element, selector.compounds[index], scope_el):
        return False
    if index + 1 == len(selector.compounds):
        return True
    combinator = selector.combinators[index]
    return any(
        _match_forward(tree, nxt, selector, index + 1, scope_el)
        for nxt in _related(tree, element, combinator)
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


def _compound_matches(tree: _Tree, element, compound: tuple[_Simple, ...], scope_el=None) -> bool:
    return all(_simple_matches(tree, element, simple, scope_el) for simple in compound)


def _simple_matches(tree: _Tree, element, simple: _Simple, scope_el=None) -> bool:
    if simple.kind == "universal":
        return True
    if simple.kind == "type":
        return _local_name(element) == simple.name
    if simple.kind == "class":
        return simple.name in _classes(element)
    if simple.kind == "id":
        return _attr(element, "id") == simple.name
    if simple.kind == "attribute":
        return _attribute_matches(element, simple)
    if simple.name in {"is", "where"}:
        return _list_matches(tree, element, simple.selectors, scope_el)
    if simple.name == "has":
        return any(_anchored_matches(tree, element, selector, scope_el) for selector in simple.selectors)
    if simple.name == "not":
        return not _list_matches(tree, element, simple.selectors, scope_el)
    if simple.name in {"nth-child", "nth-last-child"}:
        return _nth_matches(tree, element, simple, scope_el)
    if simple.name in {"scope", "scope-amp"}:
        return scope_el is not None and element is scope_el
    if simple.kind == "pseudo-element":
        return _PseudoMatch.name == simple.name
    return False


def _nth_matches(tree: _Tree, element, simple: _Simple, scope_el=None) -> bool:
    parent = tree.parent.get(element)
    siblings = [element] if parent is None else list(tree.children[parent])
    if simple.selectors:
        siblings = [item for item in siblings if _list_matches(tree, item, simple.selectors, scope_el)]
    try:
        position = _identity_index(siblings, element) + 1
    except ValueError:
        return False
    if simple.name == "nth-last-child":
        position = len(siblings) - position + 1
    return _nth_holds(position, simple.a, simple.b)


class _LayerNode:
    """One cascade layer. Its children are ordered before its own rules."""

    def __init__(self) -> None:
        self.children: list[_LayerNode] = []
        self.named: dict[str, _LayerNode] = {}
        self.slot = -1


class _LayerOrder:
    """First-seen layer tree, flattened with each parent after its children."""

    def __init__(self) -> None:
        self.root = _LayerNode()
        self.unlayered = 0

    def ensure(self, parent: _LayerNode, name: str) -> _LayerNode:
        found = parent.named.get(name)
        if found is not None:
            return found
        child = _LayerNode()
        parent.children.append(child)
        parent.named[name] = child
        return child

    def anonymous(self, parent: _LayerNode) -> _LayerNode:
        child = _LayerNode()
        parent.children.append(child)
        return child

    def descend(self, parent: _LayerNode, parts: tuple[str, ...]) -> _LayerNode:
        node = parent
        for part in parts:
            node = self.ensure(node, part)
        return node

    def freeze(self) -> None:
        count = 0

        def walk(node: _LayerNode, *, root: bool) -> None:
            nonlocal count
            for child in node.children:
                walk(child, root=False)
            if not root:
                node.slot = count
                count += 1

        walk(self.root, root=True)
        self.unlayered = count

    def slot_of(self, node: _LayerNode) -> int:
        if node is self.root:
            return self.unlayered
        return node.slot


_Found = tuple[tuple[Complex, ...], str, str, bool, int, _LayerNode, tuple[_ScopeFrame, ...]]


_MEDIA_CMP = re.compile(r"(>=|<=|>|<|=)")
_MEDIA_AXES = {
    "width": "width",
    "height": "height",
    "min-width": "width",
    "max-width": "width",
    "min-height": "height",
    "max-height": "height",
}
_MEDIA_DISCRETE = ("orientation", "prefers-color-scheme", "prefers-reduced-motion")


class _Mq:
    """Cursor over one media query. Keywords and feature names are lowercased."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.length = len(text)
        self.index = 0

    def peek(self) -> str:
        return self.text[self.index] if self.index < self.length else ""

    def skip(self) -> None:
        while self.peek() and self.peek().isspace():
            self.index += 1

    def ident(self) -> str | None:
        self.skip()
        char = self.peek()
        if not (char.isalpha() or char == "_"):
            return None
        start = self.index
        # An empty peek is a substring of every string, so test the character first.
        while self.index < self.length:
            char = self.peek()
            if not (char.isalnum() or char in "-_"):
                break
            self.index += 1
        return self.text[start : self.index].lower()

    def take(self, word: str) -> bool:
        saved = self.index
        if self.ident() == word:
            return True
        self.index = saved
        return False

    def paren(self) -> str:
        self.skip()
        if self.peek() != "(":
            raise CssSelectorError("expected a parenthesized media condition")
        self.index += 1
        start = self.index
        depth = 1
        while self.index < self.length:
            char = self.peek()
            if char in "\"'":
                self.index = _skip_string(self.text, self.index)
                continue
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    body = self.text[start : self.index]
                    self.index += 1
                    return body
            self.index += 1
        raise CssSelectorError("unclosed media condition")


def _media_context(media: dict | None) -> dict[str, object]:
    if media is None:
        media = {}
    if not isinstance(media, dict):
        raise CssSelectorError("media context must be a mapping")
    width = _context_px(media.get("width", 0), "width")
    height = _context_px(media.get("height", 0), "height")
    medium = str(media.get("type", "screen")).strip().lower() or "screen"
    scheme = str(media.get("prefers-color-scheme", "light")).strip().lower()
    motion = str(media.get("prefers-reduced-motion", "no-preference")).strip().lower()
    return {
        "type": medium,
        "width": width,
        "height": height,
        "orientation": "landscape" if width > height else "portrait",
        "prefers-color-scheme": scheme,
        "prefers-reduced-motion": motion,
    }


def _context_px(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise CssSelectorError(f"media {name} must be a px length")
    if isinstance(value, str):
        text = value.strip().lower()
        parsed = _css_px(text)
        if parsed is None:
            try:
                number = float(text)
            except ValueError as exc:
                raise CssSelectorError(f"media {name} must be a px length") from exc
        else:
            number = parsed
    else:
        number = float(value)
    if number < 0:
        raise CssSelectorError(f"media {name} cannot be negative")
    return number


def _css_px(value: str) -> float | None:
    text = value.strip().lower()
    if text == "0":
        return 0.0
    if re.fullmatch(r"\+?(?:\d+\.\d+|\d+|\.\d+)px", text) is None:
        return None
    return float(text[:-2])


def _media_queries(text: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    start = 0
    index = 0
    while index < len(text):
        char = text[index]
        if char in "\"'":
            index = _skip_string(text, index)
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            if depth == 0:
                raise CssSelectorError("unbalanced media query")
            depth -= 1
        elif char == "," and depth == 0:
            parts.append(text[start:index])
            start = index + 1
        index += 1
    if depth:
        raise CssSelectorError("unbalanced media query")
    parts.append(text[start:])
    return parts


def _not_then_paren(parser: _Mq) -> bool:
    saved = parser.index
    matched = parser.take("not")
    if matched:
        parser.skip()
        matched = parser.peek() == "("
    parser.index = saved
    return matched


def _media_matches(prelude: str, ctx: dict[str, object]) -> bool:
    text = prelude.strip()
    if not text:
        return True
    try:
        parts = _media_queries(text)
    except CssSelectorError:
        return False
    matched = False
    for part in parts:
        try:
            matched = _eval_media_query(part, ctx) or matched
        except CssSelectorError:
            continue
    return matched


def _eval_media_query(text: str, ctx: dict[str, object]) -> bool:
    parser = _Mq(text)
    parser.skip()
    if not parser.peek():
        return False
    if parser.peek() == "(" or _not_then_paren(parser):
        value = _eval_condition(parser, ctx)
        parser.skip()
        if parser.peek():
            raise CssSelectorError("trailing text in media query")
        return value
    negated = parser.take("not")
    if not negated:
        parser.take("only")
    medium = parser.ident()
    if medium is None:
        raise CssSelectorError("media query is missing a type")
    checks: list[bool] = []
    while parser.take("and"):
        checks.append(_eval_parens(parser, ctx))
    parser.skip()
    if parser.peek():
        raise CssSelectorError("trailing text in media query")
    matched = (medium == "all" or medium == ctx["type"]) and all(checks)
    return (not matched) if negated else matched


def _eval_condition(parser: _Mq, ctx: dict[str, object]) -> bool:
    parser.skip()
    if parser.take("not"):
        return not _eval_parens(parser, ctx)
    first = _eval_parens(parser, ctx)
    parser.skip()
    if parser.take("and"):
        values = [first]
        while True:
            values.append(_eval_parens(parser, ctx))
            parser.skip()
            if not parser.take("and"):
                break
        if parser.take("or"):
            raise CssSelectorError("media query mixes and and or")
        return all(values)
    if parser.take("or"):
        values = [first]
        while True:
            values.append(_eval_parens(parser, ctx))
            parser.skip()
            if not parser.take("or"):
                break
        if parser.take("and"):
            raise CssSelectorError("media query mixes and and or")
        return any(values)
    return first


def _eval_parens(parser: _Mq, ctx: dict[str, object]) -> bool:
    return _eval_piece(parser.paren(), ctx)


def _eval_piece(body: str, ctx: dict[str, object]) -> bool:
    parser = _Mq(body)
    parser.skip()
    if not parser.peek():
        return False
    if parser.peek() == "(" or _not_then_paren(parser):
        value = _eval_condition(parser, ctx)
        parser.skip()
        if parser.peek():
            raise CssSelectorError("trailing text in media condition")
        return value
    return _media_feature(" ".join(body.split()), ctx)


def _media_feature(text: str, ctx: dict[str, object]) -> bool:
    raw = text.strip()
    if not raw:
        return False
    lowered = raw.lower()
    if ":" not in lowered and any(op in lowered for op in (">=", "<=", ">", "<", "=")):
        return _feature_range(lowered, ctx)
    if ":" in raw:
        name, value = lowered.split(":", 1)
        return _plain_feature(name.strip(), value.strip(), ctx)
    return False


def _plain_feature(name: str, value: str, ctx: dict[str, object]) -> bool:
    axis = _MEDIA_AXES.get(name)
    if axis is not None:
        px = _css_px(value)
        if px is None:
            return False
        current = float(ctx[axis])
        if name.startswith("min-"):
            return current >= px
        if name.startswith("max-"):
            return current <= px
        return current == px
    if name in _MEDIA_DISCRETE:
        return ctx[name] == value
    return False


def _feature_range(text: str, ctx: dict[str, object]) -> bool:
    parts = [part.strip() for part in _MEDIA_CMP.split(text)]
    if len(parts) == 3:
        return _compare_ends(parts[0], parts[1], parts[2], ctx)
    if len(parts) == 5:
        return _compare_ends(parts[0], parts[1], parts[2], ctx) and _compare_ends(
            parts[2], parts[3], parts[4], ctx
        )
    return False


def _compare_ends(left: str, op: str, right: str, ctx: dict[str, object]) -> bool:
    if left in {"width", "height"}:
        px = _css_px(right)
        return px is not None and _apply_op(float(ctx[left]), op, px)
    if right in {"width", "height"}:
        px = _css_px(left)
        return px is not None and _apply_op(px, op, float(ctx[right]))
    return False


def _apply_op(left: float, op: str, right: float) -> bool:
    if op == ">=":
        return left >= right
    if op == "<=":
        return left <= right
    if op == ">":
        return left > right
    if op == "<":
        return left < right
    if op == "=":
        return left == right
    return False


def _take_at_block(parser: _Parser) -> tuple[str, str]:
    start = parser.index
    depth = 0
    while parser.index < parser.length:
        char = parser.peek()
        if char in "\"'":
            parser.index = _skip_string(parser.text, parser.index)
            continue
        if char == "(":
            depth += 1
        elif char == ")" and depth:
            depth -= 1
        elif char == "{" and depth == 0:
            prelude = parser.text[start : parser.index]
            parser.index += 1
            return prelude, parser.balanced("{", "}")
        parser.index += 1
    raise CssSelectorError("expected an @media block")


class _Supports:
    """Cursor over one ``@supports`` condition."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.length = len(text)
        self.index = 0

    def peek(self) -> str:
        return self.text[self.index] if self.index < self.length else ""

    def skip(self) -> None:
        while self.peek() and self.peek().isspace():
            self.index += 1

    def ident(self) -> str | None:
        self.skip()
        start = self.index
        if self.peek() == "-":
            self.index += 1
            if self.peek() == "-":
                self.index += 1
        char = self.peek()
        if not char or not (char.isalpha() or char == "_" or ord(char) > 127):
            self.index = start
            return None
        self.index += 1
        while self.index < self.length:
            char = self.peek()
            if not (char.isalnum() or char in "-_" or ord(char) > 127):
                break
            self.index += 1
        return self.text[start : self.index]

    def take(self, word: str) -> bool:
        saved = self.index
        found = self.ident()
        if found is not None and found.lower() == word:
            return True
        self.index = saved
        return False

    def paren(self) -> str:
        self.skip()
        if self.peek() != "(":
            raise CssSelectorError("expected a supports condition")
        self.index += 1
        start = self.index
        depth = 1
        while self.index < self.length:
            char = self.peek()
            if char in "\"'":
                self.index = _skip_string(self.text, self.index)
                continue
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    body = self.text[start : self.index]
                    self.index += 1
                    return body
            self.index += 1
        raise CssSelectorError("unclosed supports condition")


def _supports_matches(prelude: str) -> bool:
    text = prelude.strip()
    if not text:
        return False
    try:
        parser = _Supports(text)
        value = _supports_condition(parser)
        parser.skip()
        if parser.peek():
            return False
        return value
    except CssSelectorError:
        return False


def _supports_condition(parser: _Supports) -> bool:
    parser.skip()
    if parser.take("not"):
        return not _supports_in_parens(parser)
    first = _supports_in_parens(parser)
    parser.skip()
    if parser.take("and"):
        values = [first]
        while True:
            values.append(_supports_in_parens(parser))
            parser.skip()
            if not parser.take("and"):
                break
        if parser.take("or"):
            raise CssSelectorError("supports condition mixes and and or")
        return all(values)
    if parser.take("or"):
        values = [first]
        while True:
            values.append(_supports_in_parens(parser))
            parser.skip()
            if not parser.take("or"):
                break
        if parser.take("and"):
            raise CssSelectorError("supports condition mixes and and or")
        return any(values)
    return first


def _supports_in_parens(parser: _Supports) -> bool:
    parser.skip()
    if parser.peek() == "(":
        return _supports_paren_body(parser.paren())
    return _supports_function(parser)


def _supports_function(parser: _Supports) -> bool:
    name = parser.ident()
    if name is None or parser.peek() != "(":
        raise CssSelectorError("expected a supports feature")
    return _named_supports_feature(name, parser.paren())


def _supports_paren_body(body: str) -> bool:
    parser = _Supports(body)
    parser.skip()
    if not parser.peek():
        return False
    if parser.peek() == "(" or _supports_looks_like_not(parser):
        value = _supports_condition(parser)
        parser.skip()
        if parser.peek():
            raise CssSelectorError("trailing text in supports condition")
        return value
    saved = parser.index
    name = parser.ident()
    if name is None:
        return False
    if parser.peek() == "(":
        argument = parser.paren()
        parser.skip()
        if not parser.peek():
            return _named_supports_feature(name, argument)
        value_parser = _Supports(body)
        value = _supports_condition(value_parser)
        value_parser.skip()
        if value_parser.peek():
            raise CssSelectorError("trailing text in supports condition")
        return value
    if parser.peek().isspace():
        parser.skip()
    if parser.peek() == ":":
        return _declaration_supported(body)
    parser.index = saved
    return False


def _supports_looks_like_not(parser: _Supports) -> bool:
    saved = parser.index
    matched = parser.take("not")
    follows = False
    if matched:
        parser.skip()
        if parser.peek() == "(":
            follows = True
        else:
            name = parser.ident()
            follows = name is not None and parser.peek() == "("
    parser.index = saved
    return matched and follows


def _named_supports_feature(name: str, argument: str) -> bool:
    lowered = name.lower()
    if lowered == "selector":
        return _selector_feature(argument)
    return False


def _selector_feature(argument: str) -> bool:
    text = argument.strip()
    if not text:
        return False
    try:
        parser = _Parser(text)
        parser.complex_selector()
        parser.skip_space()
        return not parser.peek()
    except CssSelectorError:
        return False


def _declaration_supported(body: str) -> bool:
    parser = _Supports(body)
    parser.skip()
    name = parser.ident()
    if name is None:
        return False
    parser.skip()
    if parser.peek() != ":":
        return False
    parser.index += 1
    raw = parser.text[parser.index :].strip()
    if not raw or ";" in raw:
        return False
    value, _important_flag = _important(raw)
    if not value:
        return False
    if name.startswith("--"):
        return len(name) > 2
    if name.lower() == "color":
        return value.lower() in _CSS_WIDE_IDENTS or _is_color(value)
    return False


def _stylesheet(
    stylesheet: str,
    *,
    media: dict | None = None,
    container_rules: list | None = None,
    font_faces: list | None = None,
) -> tuple[list[_Decl], dict[str, _Registration]]:
    if not isinstance(stylesheet, str):
        raise CssSelectorError("stylesheet must be a string")
    context = _media_context(media)
    layers = _LayerOrder()
    found: list[_Found] = []
    held: list[tuple[str, _Found]] | None = [] if container_rules is not None else None
    counter = [0]
    registered: dict[str, _Registration] = {}
    _fill_sheet(
        _Parser(_strip_comments(stylesheet)),
        layers,
        layers.root,
        (),
        found,
        counter,
        registered,
        context,
        held,
        "",
        font_faces,
    )
    layers.freeze()
    declarations = [
        _Decl(selectors, prop, value, important, seq, layers.slot_of(node), scopes)
        for selectors, prop, value, important, seq, node, scopes in found
    ]
    if container_rules is not None and held is not None:
        for query, (selectors, prop, value, important, seq, node, scopes) in held:
            container_rules.append(
                (
                    query,
                    _Decl(selectors, prop, value, important, seq, layers.slot_of(node), scopes),
                )
            )
    return declarations, registered


def _fill_sheet(
    parser: _Parser,
    layers: _LayerOrder,
    current: _LayerNode,
    scopes: tuple[_ScopeFrame, ...],
    found: list[_Found],
    counter: list[int],
    registered: dict[str, _Registration],
    media: dict[str, object],
    held: list[tuple[str, _Found]] | None = None,
    query: str = "",
    font_faces: list | None = None,
) -> None:
    while True:
        parser.skip_space()
        if not parser.peek():
            return
        if parser.peek() == "@":
            _at_rule(
                parser, layers, current, scopes, found, counter, registered, media, held, query, font_faces
            )
            continue
        if parser.next_kind() == "decl":
            text = parser.take_declaration()
            if not text.strip():
                continue
            if not scopes:
                raise CssSelectorError("declaration is outside a style rule")
            _store_declaration(text, _ROOT_RULE, current, scopes, found, counter, held, query)
            continue
        prelude = parser.take_prelude()
        selectors = _parse_rule_selectors(prelude, scoped=bool(scopes))
        _store_block(parser.balanced("{", "}"), selectors, current, scopes, found, counter, media, held, query)


def _at_rule(
    parser: _Parser,
    layers: _LayerOrder,
    current: _LayerNode,
    scopes: tuple[_ScopeFrame, ...],
    found: list[_Found],
    counter: list[int],
    registered: dict[str, _Registration],
    media: dict[str, object],
    held: list[tuple[str, _Found]] | None = None,
    query: str = "",
    font_faces: list | None = None,
) -> None:
    parser.index += 1
    keyword = parser.ident().lower()
    if keyword == "font-face":
        if font_faces is None:
            raise CssSelectorError("at-rules are outside this reader")
        _read_font_face(parser, font_faces)
        return
    if keyword == "property":
        _read_property_rule(parser, registered)
        return
    if keyword == "container":
        prelude, body = _take_at_block(parser)
        if held is None:
            raise CssSelectorError("at-rules are outside this reader")
        text = " ".join(prelude.split())
        if not text:
            raise CssSelectorError("container query is empty")
        _fill_sheet(
            _Parser(body), layers, current, scopes, found, counter, registered, media, held, text, font_faces
        )
        return
    if keyword == "scope":
        frame = _read_scope_frame(parser, nested=bool(scopes))
        parser.index += 1
        body = parser.balanced("{", "}")
        _fill_sheet(
            _Parser(body), layers, current, scopes + (frame,), found, counter, registered, media, held, query, font_faces
        )
        return
    if keyword == "media":
        prelude, body = _take_at_block(parser)
        if _media_matches(prelude, media):
            _fill_sheet(
                _Parser(body), layers, current, scopes, found, counter, registered, media, held, query, font_faces
            )
        return
    if keyword == "supports":
        prelude, body = _take_at_block(parser)
        if _supports_matches(prelude):
            _fill_sheet(
                _Parser(body), layers, current, scopes, found, counter, registered, media, held, query, font_faces
            )
        return
    if keyword != "layer":
        raise CssSelectorError("at-rules are outside this reader")
    parser.skip_space()
    if parser.peek() == "{":
        parser.index += 1
        body = parser.balanced("{", "}")
        _fill_sheet(
            _Parser(body), layers, layers.anonymous(current), scopes, found, counter, registered, media, held, query, font_faces
        )
        return
    names = [_layer_name(parser)]
    while True:
        parser.skip_space()
        if parser.peek() != ",":
            break
        parser.index += 1
        parser.skip_space()
        names.append(_layer_name(parser))
    parser.skip_space()
    if parser.peek() == "{":
        if len(names) != 1:
            raise CssSelectorError("@layer block takes one layer name")
        parser.index += 1
        body = parser.balanced("{", "}")
        _fill_sheet(
            _Parser(body),
            layers,
            layers.descend(current, names[0]),
            scopes,
            found,
            counter,
            registered,
            media,
            held,
            query,
            font_faces,
        )
        return
    if parser.peek() == ";":
        parser.index += 1
        for name in names:
            layers.descend(current, name)
        return
    raise CssSelectorError("expected an @layer block or statement")


_FONT_FACE_DESCRIPTORS = frozenset(
    {
        "font-family",
        "font-weight",
        "font-style",
        "font-stretch",
        "unicode-range",
        "src",
        "font-display",
    }
)


def _read_font_face(parser: _Parser, faces: list) -> None:
    """Read one ``@font-face`` into the caller's face list.

    The face id is ``family/weight/style`` in source order. A repeated id
    gains a numeric suffix. ``src`` and ``font-display`` are accepted and do
    not change the face the layout matcher sees.
    """

    parser.skip_space()
    if parser.peek() != "{":
        raise CssSelectorError("@font-face is missing a block")
    parser.index += 1
    inner = _Parser(parser.balanced("{", "}"))
    props: dict[str, str] = {}
    while True:
        inner.skip_space()
        if not inner.peek():
            break
        if inner.peek() == "@" or inner.next_kind() != "decl":
            raise CssSelectorError("@font-face block is invalid")
        chunk = inner.take_declaration()
        if not chunk.strip():
            continue
        if ":" not in chunk:
            raise CssSelectorError("@font-face declaration is missing a colon")
        name, raw_value = chunk.split(":", 1)
        prop = _property_key(name)
        value, important = _important(raw_value.strip())
        if important or prop not in _FONT_FACE_DESCRIPTORS or not value:
            raise CssSelectorError("@font-face descriptor is invalid")
        props[prop] = value
    family_raw = props.get("font-family")
    if family_raw is None:
        raise CssSelectorError("@font-face is missing font-family")
    family = _font_face_family(family_raw)
    weight = _font_face_weight(props.get("font-weight", "400"))
    style = " ".join(props.get("font-style", "normal").lower().split())
    face: dict[str, object] = {
        "family": family,
        "weight": weight,
        "style": style,
        "source": "font-face",
    }
    if "font-stretch" in props:
        face["width"] = " ".join(props["font-stretch"].lower().split())
    if "unicode-range" in props:
        face["unicode-range"] = props["unicode-range"]
    ident = f"{family}/{weight}/{style}"
    used = {str(item.get("id")) for item in faces}
    suffix = 2
    while ident in used:
        ident = f"{family}/{weight}/{style}#{suffix}"
        suffix += 1
    face["id"] = ident
    faces.append(face)


def _font_face_family(value: str) -> str:
    text = " ".join(value.split())
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        text = " ".join(text[1:-1].split())
    if not text or any(mark in text for mark in ",{};"):
        raise CssSelectorError("@font-face font-family is invalid")
    return text


def _font_face_weight(value: str) -> str:
    parts = " ".join(value.lower().split()).replace(",", " ").split()
    if not parts or len(parts) > 2:
        raise CssSelectorError("@font-face font-weight is invalid")
    numbers: list[str] = []
    for part in parts:
        if part == "normal":
            numbers.append("400")
            continue
        if part == "bold":
            numbers.append("700")
            continue
        try:
            number = float(part)
        except ValueError as exc:
            raise CssSelectorError("@font-face font-weight is invalid") from exc
        if number < 1 or number > 1000 or number != number:
            raise CssSelectorError("@font-face font-weight is invalid")
        if abs(number - round(number)) <= 1e-9:
            numbers.append(str(int(round(number))))
        else:
            numbers.append(format(number, ".12g"))
    return " ".join(numbers)


def _layer_name(parser: _Parser) -> tuple[str, ...]:
    parts = [parser.ident()]
    while parser.peek() == ".":
        parser.index += 1
        parts.append(parser.ident())
    return tuple(parts)


def _read_scope_frame(parser: _Parser, *, nested: bool) -> _ScopeFrame:
    parser.skip_space()
    start_text: str | None = None
    end_text: str | None = None
    if parser.peek() == "(":
        parser.index += 1
        start_text = parser.balanced("(", ")")
        parser.skip_space()
    if _at_keyword(parser, "to"):
        parser.skip_space()
        if parser.peek() != "(":
            raise CssSelectorError("@scope limit is missing parentheses")
        parser.index += 1
        end_text = parser.balanced("(", ")")
        parser.skip_space()
    elif start_text is None and parser.peek() != "{":
        raise CssSelectorError("expected an @scope block")
    if parser.peek() != "{":
        raise CssSelectorError("expected an @scope block")
    start = None if start_text is None else _boundary_selectors(start_text, relative=nested)
    end = None if end_text is None else _boundary_selectors(end_text, relative=True)
    return _ScopeFrame(start, end, nested)


def _selector_mentions_pseudo(selector: Complex) -> bool:
    def walk(item: _Simple) -> bool:
        if item.kind == "pseudo-element":
            return True
        return any(walk(child) for selector in item.selectors for child in _selector_simples(selector))

    return any(walk(item) for compound in selector.compounds for item in compound)


def _selector_simples(selector: Complex):
    for compound in selector.compounds:
        yield from compound


def _reject_boundary_pseudos(selectors: tuple[Complex, ...]) -> None:
    if any(_selector_mentions_pseudo(selector) for selector in selectors):
        raise CssSelectorError("pseudo-elements are outside this reader")


def _require_trailing_pseudos(selectors: tuple[Complex, ...]) -> None:
    """A pseudo-element is only the last simple of the last compound."""

    for selector in selectors:
        sites: list[tuple[int, int]] = []
        for compound_index, compound in enumerate(selector.compounds):
            for simple_index, simple in enumerate(compound):
                if simple.selectors and any(_selector_mentions_pseudo(child) for child in simple.selectors):
                    raise CssSelectorError("pseudo-elements are outside this reader")
                if simple.kind == "pseudo-element":
                    sites.append((compound_index, simple_index))
        if not sites:
            continue
        last_compound = len(selector.compounds) - 1
        last_simple = len(selector.compounds[-1]) - 1
        if sites != [(last_compound, last_simple)]:
            raise CssSelectorError("pseudo-elements are outside this reader")
        if selector.compounds[-1][-1].name not in {"before", "after"}:
            raise CssSelectorError("pseudo-elements are outside this reader")


def _at_keyword(parser: _Parser, word: str) -> bool:
    parser.skip_space()
    saved = parser.index
    if not parser._ident_start():
        return False
    found = parser.ident()
    if found.lower() != word:
        parser.index = saved
        return False
    return True


def _boundary_selectors(text: str, *, relative: bool) -> tuple[Complex, ...]:
    parser = _Parser(text, nesting=relative)
    parsed = parser.scoped_selector_list() if relative else parser.selector_list()
    parser.skip_space()
    if parser.peek():
        raise CssSelectorError("trailing text after selector")
    _reject_boundary_pseudos(parsed)
    return parsed


def _parse_rule_selectors(text: str, *, scoped: bool) -> tuple[Complex, ...]:
    parser = _Parser(text, nesting=scoped)
    parsed = parser.scoped_selector_list() if scoped else parser.selector_list()
    parser.skip_space()
    if parser.peek():
        raise CssSelectorError("trailing text after selector")
    _require_trailing_pseudos(parsed)
    return parsed


def _store_block(
    body: str,
    selectors: tuple[Complex, ...],
    node: _LayerNode,
    scopes: tuple[_ScopeFrame, ...],
    found: list[_Found],
    counter: list[int],
    media: dict[str, object],
    held: list[tuple[str, _Found]] | None = None,
    query: str = "",
) -> None:
    _fill_style_body(body, selectors, node, scopes, found, counter, media, held, query)


def _fill_style_body(
    body: str,
    selectors: tuple[Complex, ...],
    node: _LayerNode,
    scopes: tuple[_ScopeFrame, ...],
    found: list[_Found],
    counter: list[int],
    media: dict[str, object],
    held: list[tuple[str, _Found]] | None = None,
    query: str = "",
) -> None:
    """Declarations keep ``selectors``. Inner style rules expand against them."""

    parser = _Parser(body)
    while True:
        parser.skip_space()
        if not parser.peek():
            return
        if parser.peek() == "@":
            _nested_media(parser, selectors, node, scopes, found, counter, media, held, query)
            continue
        if parser.next_kind() == "decl":
            text = parser.take_declaration()
            if text.strip():
                _store_declaration(text, selectors, node, scopes, found, counter, held, query)
            continue
        prelude = parser.take_prelude()
        try:
            nested = _parse_nested_selectors(prelude)
        except CssSelectorError:
            parser.balanced("{", "}")
            continue
        expanded = tuple(_desugar_nested(selectors, item) for item in nested)
        _require_trailing_pseudos(expanded)
        _fill_style_body(parser.balanced("{", "}"), expanded, node, scopes, found, counter, media, held, query)


def _nested_media(
    parser: _Parser,
    selectors: tuple[Complex, ...],
    node: _LayerNode,
    scopes: tuple[_ScopeFrame, ...],
    found: list[_Found],
    counter: list[int],
    media: dict[str, object],
    held: list[tuple[str, _Found]] | None = None,
    query: str = "",
) -> None:
    parser.index += 1
    keyword = parser.ident().lower()
    if keyword == "supports":
        prelude, body = _take_at_block(parser)
        if _supports_matches(prelude):
            _fill_style_body(body, selectors, node, scopes, found, counter, media, held, query)
        return
    if keyword != "media":
        raise CssSelectorError("at-rules are outside this reader")
    prelude, body = _take_at_block(parser)
    if _media_matches(prelude, media):
        _fill_style_body(body, selectors, node, scopes, found, counter, media, held, query)


def _parse_nested_selectors(text: str) -> tuple[Complex, ...]:
    parser = _Parser(text, style_nesting=True)
    parsed = parser.nested_selector_list()
    parser.skip_space()
    if parser.peek():
        raise CssSelectorError("trailing text after selector")
    return parsed


def _contains_nesting_selector(selector: Complex) -> bool:
    def walk(item: _Simple) -> bool:
        if item.kind == "pseudo" and item.name == "nest":
            return True
        return any(_contains_nesting_selector(child) for child in item.selectors)

    return any(walk(item) for compound in selector.compounds for item in compound)


def _replace_nesting_selector(selector: Complex, parents: tuple[Complex, ...]) -> Complex:
    def walk(item: _Simple) -> _Simple:
        if item.kind == "pseudo" and item.name == "nest":
            return _Simple("pseudo", "is", parents)
        if not item.selectors:
            return item
        return _Simple(
            item.kind,
            item.name,
            tuple(_replace_nesting_selector(child, parents) for child in item.selectors),
            item.a,
            item.b,
        )

    compounds = tuple(tuple(walk(item) for item in compound) for compound in selector.compounds)
    return Complex(compounds, selector.combinators)


def _desugar_nested(parents: tuple[Complex, ...], selector: Complex) -> Complex:
    """Replace ``&`` with ``:is(parents)``. A relative selector gets that parent too."""

    if _contains_nesting_selector(selector):
        replaced = _replace_nesting_selector(selector, parents)
        if not selector.anchor:
            return replaced
        return Complex(
            ((_Simple("pseudo", "is", parents),), *replaced.compounds),
            (selector.anchor, *replaced.combinators),
        )
    combinator = selector.anchor or " "
    return Complex(
        ((_Simple("pseudo", "is", parents),), *selector.compounds),
        (combinator, *selector.combinators),
    )


def _store_declaration(
    chunk: str,
    selectors: tuple[Complex, ...],
    node: _LayerNode,
    scopes: tuple[_ScopeFrame, ...],
    found: list[_Found],
    counter: list[int],
    held: list[tuple[str, _Found]] | None = None,
    query: str = "",
) -> None:
    if ":" not in chunk:
        raise CssSelectorError("declaration is missing a colon")
    name, raw_value = chunk.split(":", 1)
    prop = _property_key(name)
    value, important = _important(raw_value.strip())
    if not prop or not value:
        raise CssSelectorError("declaration is empty")
    item = (selectors, prop, value, important, counter[0], node, scopes)
    if query:
        if held is None:
            raise CssSelectorError("at-rules are outside this reader")
        held.append((query, item))
    else:
        found.append(item)
    counter[0] += 1


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


def _document_element(tree: _Tree):
    for element in tree.order:
        if not _local_name(element):
            continue
        parent = tree.parent.get(element)
        if parent is None or not _local_name(parent):
            return element
    return None


def _hops(tree: _Tree, element, root) -> int | None:
    hops = 0
    current = element
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        if current is root:
            return hops
        seen.add(id(current))
        current = tree.parent.get(current)
        hops += 1
    return None


def _in_instance(tree: _Tree, element, instance: tuple) -> bool:
    if _hops(tree, element, instance[0]) is None:
        return False
    return all(_hops(tree, element, limit) is None for limit in instance[1])


def _one_matches(tree: _Tree, element, selector: Complex, scope_el) -> bool:
    if not selector.anchor:
        return _complex_matches(tree, element, selector, scope_el)
    prefixed = Complex(
        ((_Simple("pseudo", "scope"),), *selector.compounds),
        (selector.anchor, *selector.combinators),
    )
    return _complex_matches(tree, element, prefixed, scope_el)


def _selectors_match(tree: _Tree, element, selectors: tuple[Complex, ...], scope_el, *, relative: bool) -> bool:
    if relative:
        return any(_one_matches(tree, element, selector, scope_el) for selector in selectors)
    return _list_matches(tree, element, selectors, scope_el)


def _frame_roots(tree: _Tree, frame: _ScopeFrame, outer: tuple | None) -> list:
    if frame.start is None:
        root = _document_element(tree)
        return [] if root is None else [root]
    if not frame.start_relative:
        anchor = _document_element(tree)
        return [
            element
            for element in tree.order
            if _local_name(element) and _selectors_match(tree, element, frame.start, anchor, relative=False)
        ]
    if outer is None:
        return []
    return [
        element
        for element in tree.order
        if _local_name(element)
        and _in_instance(tree, element, outer)
        and _selectors_match(tree, element, frame.start, outer[0], relative=True)
    ]


def _limit_elements(tree: _Tree, root, end: tuple[Complex, ...] | None) -> tuple:
    if not end:
        return ()
    return tuple(
        element
        for element in _related(tree, root, " ")
        if _selectors_match(tree, element, end, root, relative=True)
    )


def _scope_chains(tree: _Tree, frames: tuple[_ScopeFrame, ...]) -> tuple:
    cached = tree.scope_cache.get(frames)
    if cached is not None:
        return cached
    found: list[tuple] = []

    def walk(index: int, chain: tuple) -> None:
        outer = chain[-1] if chain else None
        for root in _frame_roots(tree, frames[index], outer):
            nxt = chain + ((root, _limit_elements(tree, root, frames[index].end)),)
            if index + 1 == len(frames):
                found.append(nxt)
            else:
                walk(index + 1, nxt)

    if frames:
        walk(0, ())
    result = tuple(found)
    tree.scope_cache[frames] = result
    return result


def _declaration_precedence(tree: _Tree, element, decl: _Decl) -> tuple[tuple[int, int, int], int] | None:
    if not decl.scopes:
        specificity = _matching_specificity(tree, element, decl.selectors, _document_element(tree))
        if specificity is None:
            return None
        return specificity, _UNSCOPED
    best: tuple[tuple, tuple[int, int, int], int] | None = None
    for chain in _scope_chains(tree, decl.scopes):
        if not all(_in_instance(tree, element, instance) for instance in chain):
            continue
        root = chain[-1][0]
        hops = _hops(tree, element, root)
        if hops is None:
            continue
        for selector in decl.selectors:
            if not _one_matches(tree, element, selector, root):
                continue
            specificity = _specificity(selector)
            key = (specificity, -hops)
            if best is None or key > best[0]:
                best = (key, specificity, hops)
    if best is None:
        return None
    return best[1], best[2]


def _cascaded_map(tree: _Tree, element, declarations: list[_Decl]) -> dict[str, str]:
    grouped: dict[str, list[tuple[tuple, _Decl]]] = {}
    for decl in declarations:
        parts = _declaration_precedence(tree, element, decl)
        if parts is None:
            continue
        specificity, proximity = parts
        # Important order is the reverse of normal layer order. A higher tuple wins.
        # Scope proximity sits after specificity and before source order.
        layer_priority = -decl.layer if decl.important else decl.layer
        rank = (decl.important, layer_priority, specificity, -proximity, decl.order)
        grouped.setdefault(decl.prop, []).append((rank, decl))
    winners: dict[str, str] = {}
    for prop, items in grouped.items():
        items.sort(key=lambda item: item[0], reverse=True)
        rejected: set[int] = set()
        for _rank, decl in items:
            if decl.layer in rejected:
                continue
            if decl.value.strip().lower() == "revert-layer":
                rejected.add(decl.layer)
                continue
            winners[prop] = decl.value
            break
    return winners


def _trailing_pseudo(selector: Complex) -> str | None:
    if not selector.compounds:
        return None
    last = selector.compounds[-1]
    if not last or last[-1].kind != "pseudo-element":
        return None
    return last[-1].name


def resolve_generated_strings(
    tree: _Tree,
    element,
    declarations: list[_Decl],
    custom: dict,
) -> tuple[str, str]:
    """String content of ``::before`` and ``::after``, or empty when no box is generated.

    ``attr()`` is replaced by that element's attribute before the string is
    returned. A missing attribute is empty. A fallback, a type, or any other
    function raises ``generated content is unsupported``. Any other property
    on a pseudo that does generate a box raises ``generated box is
    unsupported``. Element rules are not read as the pseudo's own declarations.
    """

    before = _one_generated(tree, element, declarations, custom, "before", plans=False)
    after = _one_generated(tree, element, declarations, custom, "after", plans=False)
    return (before if isinstance(before, str) else "", after if isinstance(after, str) else "")


def resolve_generated_plans(
    tree: _Tree,
    element,
    declarations: list[_Decl],
    custom: dict,
) -> tuple[list, list]:
    """``::before`` and ``::after`` content as text and counter parts.

    ``counter()`` and ``counters()`` stay in the plan. ``attr()`` is already
    the element's attribute text. A fallback, a type, or any other function
    raises ``generated content is unsupported``. A property besides ``content``
    on a pseudo that generates a box raises ``generated box is unsupported``.
    """

    before = _one_generated(tree, element, declarations, custom, "before", plans=True)
    after = _one_generated(tree, element, declarations, custom, "after", plans=True)
    return (before if isinstance(before, list) else [], after if isinstance(after, list) else [])


def _one_generated(
    tree: _Tree,
    element,
    declarations: list[_Decl],
    custom: dict,
    pseudo: str,
    *,
    plans: bool,
) -> str | list:
    chosen = [decl for decl in declarations if any(_trailing_pseudo(selector) == pseudo for selector in decl.selectors)]
    if not chosen:
        return [] if plans else ""
    previous = _PseudoMatch.name
    _PseudoMatch.name = pseudo
    try:
        winners = _cascaded_map(tree, element, chosen)
    finally:
        _PseudoMatch.name = previous
    raw = winners.get("content")
    if raw is None:
        return [] if plans else ""
    substituted = _substitute(raw, lambda name: custom.get(name, _INVALID))
    if substituted is _INVALID or not isinstance(substituted, str):
        raise CssSelectorError("generated content is unsupported")
    if plans:
        parsed = _generated_content_parts(substituted)
        if parsed is None:
            return []
        parsed = _expand_attr_parts(element, parsed)
        if any(name != "content" for name in winners):
            raise CssSelectorError("generated box is unsupported")
        return parsed
    text = _generated_content_text(substituted, element)
    if text is None:
        return ""
    if any(name != "content" for name in winners):
        raise CssSelectorError("generated box is unsupported")
    return text


def _generated_content_parts(value: str) -> list[tuple] | None:
    text = value.strip()
    if text.lower() in {"normal", "none", "initial", "unset", "revert"}:
        return None
    if text.lower() == "inherit":
        raise CssSelectorError("generated content is unsupported")
    parts: list[tuple] = []
    index = 0
    length = len(text)
    while index < length:
        index = _skip_css_space(text, index)
        if index >= length:
            break
        if text[index] in "\"'":
            end = _end_of_string(text, index)
            if end is None:
                raise CssSelectorError("generated content is unsupported")
            unquoted = _unquote(text[index:end])
            if unquoted is None:
                raise CssSelectorError("generated content is unsupported")
            parts.append(("text", unquoted))
            index = end
            continue
        name, next_index = _read_css_ident(text, index)
        if name is None or next_index >= length or text[next_index] != "(":
            raise CssSelectorError("generated content is unsupported")
        call, index = _generated_call(text, next_index, name)
        parts.append(call)
    if not parts:
        raise CssSelectorError("generated content is unsupported")
    return parts


def _generated_call(text: str, index: int, name: str) -> tuple[tuple, int]:
    if index >= len(text) or text[index] != "(":
        raise CssSelectorError("generated content is unsupported")
    index += 1
    kind = name.lower()
    if kind == "counter":
        index = _skip_css_space(text, index)
        counter_name, index = _read_css_ident(text, index)
        if counter_name is None:
            raise CssSelectorError("generated content is unsupported")
        style = "decimal"
        index = _skip_css_space(text, index)
        if index < len(text) and text[index] == ",":
            index = _skip_css_space(text, index + 1)
            style_name, index = _read_css_ident(text, index)
            if style_name is None:
                raise CssSelectorError("generated content is unsupported")
            style = style_name.lower()
        index = _skip_css_space(text, index)
        if index >= len(text) or text[index] != ")":
            raise CssSelectorError("generated content is unsupported")
        return ("counter", counter_name, style), index + 1
    if kind == "counters":
        index = _skip_css_space(text, index)
        counter_name, index = _read_css_ident(text, index)
        if counter_name is None:
            raise CssSelectorError("generated content is unsupported")
        index = _skip_css_space(text, index)
        if index >= len(text) or text[index] != ",":
            raise CssSelectorError("generated content is unsupported")
        index = _skip_css_space(text, index + 1)
        if index >= len(text) or text[index] not in "\"'":
            raise CssSelectorError("generated content is unsupported")
        end = _end_of_string(text, index)
        if end is None:
            raise CssSelectorError("generated content is unsupported")
        separator = _unquote(text[index:end])
        if separator is None:
            raise CssSelectorError("generated content is unsupported")
        index = _skip_css_space(text, end)
        style = "decimal"
        if index < len(text) and text[index] == ",":
            index = _skip_css_space(text, index + 1)
            style_name, index = _read_css_ident(text, index)
            if style_name is None:
                raise CssSelectorError("generated content is unsupported")
            style = style_name.lower()
            index = _skip_css_space(text, index)
        if index >= len(text) or text[index] != ")":
            raise CssSelectorError("generated content is unsupported")
        return ("counters", counter_name, separator, style), index + 1
    if kind == "attr":
        index = _skip_css_space(text, index)
        attr_name, index = _read_css_ident(text, index)
        if attr_name is None:
            raise CssSelectorError("generated content is unsupported")
        index = _skip_css_space(text, index)
        if index >= len(text) or text[index] != ")":
            raise CssSelectorError("generated content is unsupported")
        return ("attr", attr_name), index + 1
    raise CssSelectorError("generated content is unsupported")


def _expand_attr_parts(element, parts: list[tuple]) -> list[tuple]:
    """Replace ``attr()`` with that element's attribute. A missing one is empty."""

    expanded: list[tuple] = []
    for part in parts:
        if part[0] == "attr":
            raw = _attr(element, part[1])
            piece = "" if raw is None else raw
            if expanded and expanded[-1][0] == "text":
                expanded[-1] = ("text", expanded[-1][1] + piece)
            else:
                expanded.append(("text", piece))
            continue
        if expanded and part[0] == "text" and expanded[-1][0] == "text":
            expanded[-1] = ("text", expanded[-1][1] + part[1])
        else:
            expanded.append(part)
    return expanded


def _skip_css_space(text: str, index: int) -> int:
    while index < len(text) and text[index].isspace():
        index += 1
    return index


def _read_css_ident(text: str, index: int) -> tuple[str | None, int]:
    length = len(text)
    if index >= length:
        return None, index
    start = index
    char = text[index]
    if char == "-":
        if index + 1 < length and text[index + 1] == "-":
            index += 2
        elif index + 1 < length and _css_ident_start(text[index + 1]):
            index += 2
        else:
            return None, start
    elif _css_ident_start(char):
        index += 1
    else:
        return None, start
    while index < length and _css_ident_continue(text[index]):
        index += 1
    token = text[start:index]
    if token in {"", "-"}:
        return None, start
    return token, index


def _css_ident_start(char: str) -> bool:
    return char == "_" or char.isalpha() or ord(char) > 127


def _css_ident_continue(char: str) -> bool:
    return char == "_" or char.isalpha() or char.isdigit() or char == "-" or ord(char) > 127


def _generated_content_text(value: str, element=None) -> str | None:
    parts = _generated_content_parts(value)
    if parts is None:
        return None
    if element is not None:
        parts = _expand_attr_parts(element, parts)
    if any(part[0] != "text" for part in parts):
        raise CssSelectorError("generated content is unsupported")
    return "".join(part[1] for part in parts if part[0] == "text")


def _end_of_string(text: str, start: int) -> int | None:
    quote = text[start]
    index = start + 1
    while index < len(text):
        char = text[index]
        if char == "\\":
            index += 2
            continue
        if char == quote:
            return index + 1
        if char in "\n\r\f":
            return None
        index += 1
    return None


class _GuaranteedInvalid:
    """Initial value of a custom property, and the result of a failed substitution."""


_INVALID = _GuaranteedInvalid()
_WIDE_KEYWORDS = frozenset({"inherit", "initial", "unset", "revert"})


def computed_value(
    markup: str,
    stylesheet: str,
    element_id: str,
    property_name: str,
    *,
    media: dict | None = None,
) -> str:
    """Computed value of one property on ``element_id``.

    Custom properties and ``color`` inherit. A guaranteed-invalid custom
    property serializes as the empty string. A valid empty custom property
    serializes as one space. Any other property is substituted from its own
    cascaded declaration and does not inherit. A valid ``@property`` rule
    changes that for the names it registers.
    """

    if not isinstance(element_id, str) or not element_id:
        raise CssSelectorError("element id must be a non-empty string")
    prop = _property_key(property_name)
    if not prop:
        raise CssSelectorError("property name is empty")
    tree, order = _document(markup)
    declarations, registrations = _stylesheet(stylesheet, media=media)
    styles: dict = {}
    for element in order:
        parent = tree.parent.get(element)
        parent_custom, parent_color = styles.get(parent, ({}, ""))
        styles[element] = _computed_style(
            tree, element, declarations, parent_custom, parent_color, registrations
        )
    target = next((element for element in order if _attr(element, "id") == element_id), None)
    if target is None:
        return ""
    custom, color = styles[target]
    if prop.startswith("--"):
        found = custom.get(prop, "")
        return found if isinstance(found, str) else ""
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
    parent_custom: dict[str, str | _GuaranteedInvalid],
    parent_color: str,
    registrations: dict[str, _Registration],
) -> tuple[dict[str, str | _GuaranteedInvalid], str]:
    winners = _cascaded_map(tree, element, declarations)
    specified: dict[str, str] = {}
    forced_invalid: set[str] = set()
    explicit_inherit: set[str] = set()
    use_initial: set[str] = set()
    for name, value in winners.items():
        if not name.startswith("--"):
            continue
        keyword = _wide_keyword(value)
        registered = registrations.get(name)
        if keyword == "inherit":
            if registered is None:
                continue
            explicit_inherit.add(name)
            continue
        if keyword == "unset":
            if registered is None or registered.inherits:
                continue
            use_initial.add(name)
            continue
        if keyword in {"initial", "revert"}:
            if registered is None:
                forced_invalid.add(name)
            else:
                use_initial.add(name)
            continue
        specified[name] = value
    dependencies = {name: _active_dependencies(value) for name, value in specified.items()}
    cyclic = _cyclic_properties(dependencies)
    memo: dict[str, str | _GuaranteedInvalid] = {}
    resolving: set[str] = set()

    def failed(name: str) -> str | _GuaranteedInvalid:
        registered = registrations.get(name)
        if registered is not None and not registered.syntax.universal:
            return _registered_initial(registered)
        return _INVALID

    def lookup(name: str) -> str | _GuaranteedInvalid:
        if name in resolving:
            return _INVALID
        if name in memo:
            return memo[name]
        if name in explicit_inherit:
            if name in parent_custom:
                return parent_custom[name]
            registered = registrations.get(name)
            return _INVALID if registered is None else _registered_initial(registered)
        if name in use_initial:
            return _registered_initial(registrations[name])
        if name in cyclic or name in forced_invalid:
            return failed(name)
        if name in specified:
            return resolve(name)
        registered = registrations.get(name)
        if registered is None:
            return parent_custom.get(name, _INVALID)
        if registered.inherits and name in parent_custom:
            return parent_custom[name]
        return _registered_initial(registered)

    def resolve(name: str) -> str | _GuaranteedInvalid:
        if name in memo:
            return memo[name]
        if name in cyclic or name in forced_invalid:
            memo[name] = failed(name)
            return memo[name]
        resolving.add(name)
        try:
            value = _substitute(specified[name], lookup)
        finally:
            resolving.discard(name)
        registered = registrations.get(name)
        if (
            value is not _INVALID
            and registered is not None
            and not registered.syntax.universal
            and not _value_matches(registered.syntax, value)
        ):
            value = _registered_initial(registered)
        memo[name] = value
        return value

    custom: dict[str, str | _GuaranteedInvalid] = {}
    for name, value in parent_custom.items():
        registered = registrations.get(name)
        if registered is not None and not registered.inherits:
            continue
        custom[name] = value
    for name in forced_invalid:
        custom.pop(name, None)
    for name in explicit_inherit:
        _store_custom(custom, name, lookup(name), registered=True)
    for name in use_initial:
        _store_custom(custom, name, lookup(name), registered=True)
    for name in specified:
        _store_custom(custom, name, resolve(name), registered=name in registrations)
    for name, registered in registrations.items():
        if name in custom:
            continue
        _store_custom(custom, name, _registered_initial(registered), registered=True)
    color = _computed_color(winners.get("color"), parent_color, lambda name: custom.get(name, _INVALID))
    return custom, color


def _store_custom(
    custom: dict[str, str | _GuaranteedInvalid],
    name: str,
    value: str | _GuaranteedInvalid,
    *,
    registered: bool,
) -> None:
    if value is _INVALID:
        if registered:
            custom[name] = _INVALID
        else:
            custom.pop(name, None)
        return
    custom[name] = " " if value == "" else value


def _registered_initial(registered: _Registration) -> str | _GuaranteedInvalid:
    if registered.initial is None:
        return _INVALID
    return registered.initial


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


def _read_property_rule(parser: _Parser, registered: dict[str, _Registration]) -> None:
    """Consume one ``@property`` rule. An invalid rule registers nothing."""

    names, valid_names = _property_prelude(parser)
    parser.skip_space()
    if parser.peek() != "{":
        raise CssSelectorError("expected an @property block")
    parser.index += 1
    body = parser.balanced("{", "}")
    if not valid_names:
        return
    registration = _parse_registration(body)
    if registration is None:
        return
    for name in names:
        registered[name] = registration


def _property_prelude(parser: _Parser) -> tuple[list[str], bool]:
    names: list[str] = []
    while True:
        name = _read_custom_name(parser)
        if name is None:
            return names, False
        names.append(name)
        parser.skip_space()
        if parser.peek() != ",":
            return names, True
        parser.index += 1


def _read_custom_name(parser: _Parser) -> str | None:
    parser.skip_space()
    start = parser.index
    if not parser.text.startswith("--", parser.index):
        return None
    parser.index += 2
    if not parser._ident_char(parser.peek(), start=True):
        parser.index = start
        return None
    parser.index += 1
    while parser._ident_char(parser.peek(), start=False):
        parser.index += 1
    return parser.text[start : parser.index]


def _parse_registration(body: str) -> _Registration | None:
    parser = _Parser(body)
    syntax: _Syntax | None = None
    inherits: bool | None = None
    initials: list[str] = []
    while True:
        parser.skip_space()
        if not parser.peek():
            break
        chunk = parser.take_declaration().strip()
        if not chunk:
            continue
        parsed = _descriptor(chunk)
        if parsed is None:
            continue
        key, raw = parsed
        if key == "syntax":
            text = _unquote(raw)
            if text is None:
                continue
            consumed = _consume_syntax(text)
            if consumed is None:
                continue
            syntax = consumed
        elif key == "inherits":
            token = raw.strip().lower()
            if token == "true":
                inherits = True
            elif token == "false":
                inherits = False
        elif key == "initial-value":
            candidate = raw.strip()
            if candidate and _computationally_independent(candidate):
                initials.append(candidate)
    if syntax is None or inherits is None:
        return None
    chosen: str | None = None
    for candidate in initials:
        if _initial_ok(syntax, candidate):
            chosen = candidate
    if not syntax.universal and chosen is None:
        return None
    return _Registration(syntax, inherits, chosen)


def _descriptor(chunk: str) -> tuple[str, str] | None:
    if ":" not in chunk:
        return None
    name, raw = chunk.split(":", 1)
    key = name.strip().lower()
    value, important = _important(raw.strip())
    if important or not key or not value.strip():
        return None
    return key, value.strip()


def _unquote(value: str) -> str | None:
    text = value.strip()
    if len(text) < 2 or text[0] not in "\"'" or text[-1] != text[0]:
        return None
    quote = text[0]
    body = text[1:-1]
    out: list[str] = []
    index = 0
    while index < len(body):
        char = body[index]
        if char == "\\":
            if index + 1 >= len(body):
                return None
            out.append(body[index + 1])
            index += 2
            continue
        if char == quote or char in "\n\r\f":
            return None
        out.append(char)
        index += 1
    return "".join(out)


_SYNTAX_TYPES = frozenset(
    {
        "<number>",
        "<integer>",
        "<length>",
        "<percentage>",
        "<length-percentage>",
        "<angle>",
        "<time>",
        "<color>",
        "<custom-ident>",
    }
)
_ABSOLUTE_LENGTH_UNITS = frozenset({"px", "in", "cm", "mm", "q", "pt", "pc"})
_RELATIVE_UNITS = frozenset(
    {
        "em",
        "ex",
        "cap",
        "ch",
        "ic",
        "lh",
        "rlh",
        "rem",
        "vw",
        "vh",
        "vi",
        "vb",
        "vmin",
        "vmax",
        "svw",
        "svh",
        "svmin",
        "svmax",
        "lvw",
        "lvh",
        "lvmin",
        "lvmax",
        "dvw",
        "dvh",
        "dvmin",
        "dvmax",
        "cqw",
        "cqh",
        "cqi",
        "cqb",
        "cqmin",
        "cqmax",
    }
)
_LENGTH_UNITS = _ABSOLUTE_LENGTH_UNITS | _RELATIVE_UNITS
_ANGLE_UNITS = frozenset({"deg", "rad", "grad", "turn"})
_TIME_UNITS = frozenset({"s", "ms"})
_CSS_WIDE_IDENTS = frozenset({"inherit", "initial", "unset", "revert", "revert-layer"})
_NUMBER_TEXT = r"[+-]?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][+-]?\d+)?"
_DIMENSION = re.compile(rf"({_NUMBER_TEXT})([A-Za-z%]+)?\Z")
_UNIT_AFTER_NUMBER = re.compile(rf"{_NUMBER_TEXT}([A-Za-z%]+)")
_IDENT_TEXT = re.compile(r"(?:--|-)?[A-Za-z_\u0080-\U0010FFFF][A-Za-z0-9_\-\u0080-\U0010FFFF]*\Z")
_NAMED_COLORS = frozenset(
    """
    aliceblue antiquewhite aqua aquamarine azure beige bisque black blanchedalmond blue blueviolet brown
    burlywood cadetblue chartreuse chocolate coral cornflowerblue cornsilk crimson cyan darkblue darkcyan
    darkgoldenrod darkgray darkgreen darkgrey darkkhaki darkmagenta darkolivegreen darkorange darkorchid
    darkred darksalmon darkseagreen darkslateblue darkslategray darkslategrey darkturquoise darkviolet
    deeppink deepskyblue dimgray dimgrey dodgerblue firebrick floralwhite forestgreen fuchsia gainsboro
    ghostwhite gold goldenrod gray green greenyellow grey honeydew hotpink indianred indigo ivory khaki
    lavender lavenderblush lawngreen lemonchiffon lightblue lightcoral lightcyan lightgoldenrodyellow
    lightgray lightgreen lightgrey lightpink lightsalmon lightseagreen lightskyblue lightslategray
    lightslategrey lightsteelblue lightyellow lime limegreen linen magenta maroon mediumaquamarine
    mediumblue mediumorchid mediumpurple mediumseagreen mediumslateblue mediumspringgreen mediumturquoise
    mediumvioletred midnightblue mintcream mistyrose moccasin navajowhite navy oldlace olive olivedrab
    orange orangered orchid palegoldenrod palegreen paleturquoise palevioletred papayawhip peachpuff peru
    pink plum powderblue purple rebeccapurple red rosybrown royalblue saddlebrown salmon sandybrown
    seagreen seashell sienna silver skyblue slateblue slategray slategrey snow springgreen steelblue tan
    teal thistle tomato turquoise violet wheat white whitesmoke yellow yellowgreen transparent
    """.split()
)


def _consume_syntax(text: str) -> _Syntax | None:
    raw = text.strip()
    if raw == "*":
        return _Syntax(True, ())
    if not raw:
        return None
    parts: list[_SyntaxPart] = []
    index = 0
    length = len(raw)
    ident = re.compile(r"(?:--|-)?[A-Za-z_\u0080-\U0010FFFF][A-Za-z0-9_\-\u0080-\U0010FFFF]*")
    while index < length:
        while index < length and raw[index].isspace():
            index += 1
        if index >= length:
            return None
        if raw[index] == "<":
            end = raw.find(">", index)
            if end < 0:
                return None
            name = raw[index : end + 1].lower()
            if name not in _SYNTAX_TYPES:
                return None
            index = end + 1
        else:
            matched = ident.match(raw, index)
            if matched is None:
                return None
            name = matched.group(0)
            index = matched.end()
        multiplier = ""
        if index < length and raw[index] in "+#":
            multiplier = raw[index]
            index += 1
        parts.append(_SyntaxPart(name, multiplier))
        while index < length and raw[index].isspace():
            index += 1
        if index >= length:
            break
        if raw[index] != "|":
            return None
        index += 1
    if not parts:
        return None
    return _Syntax(False, tuple(parts))


def _initial_ok(syntax: _Syntax, value: str) -> bool:
    if not value.strip():
        return False
    if syntax.universal:
        return True
    return _value_matches(syntax, value)


def _computationally_independent(value: str) -> bool:
    if re.search(r"(?:var|attr|env|calc)\s*\(", value, re.IGNORECASE):
        return False
    if re.search(r"currentcolor", value, re.IGNORECASE):
        return False
    for match in _UNIT_AFTER_NUMBER.finditer(value):
        if match.group(1).lower() in _RELATIVE_UNITS:
            return False
    return True


def _value_matches(syntax: _Syntax, value: str) -> bool:
    text = value.strip()
    if syntax.universal:
        return True
    if not text:
        return False
    return any(_part_matches(part, text) for part in syntax.parts)


def _part_matches(part: _SyntaxPart, text: str) -> bool:
    if part.multiplier == "+":
        items = _split_top_level(text, comma=False)
        return bool(items) and all(_base_matches(part.name, item) for item in items)
    if part.multiplier == "#":
        items = _split_top_level(text, comma=True)
        return bool(items) and all(_base_matches(part.name, item) for item in items)
    return _base_matches(part.name, text.strip())


def _split_top_level(text: str, *, comma: bool) -> list[str] | None:
    items: list[str] = []
    buf: list[str] = []
    depth = 0
    quote = ""
    index = 0

    def flush() -> bool:
        item = "".join(buf).strip()
        buf.clear()
        if not item:
            return False
        items.append(item)
        return True

    while index < len(text):
        char = text[index]
        if quote:
            buf.append(char)
            if char == "\\" and index + 1 < len(text):
                buf.append(text[index + 1])
                index += 2
                continue
            if char == quote:
                quote = ""
            index += 1
            continue
        if char in "\"'":
            quote = char
            buf.append(char)
            index += 1
            continue
        if char == "(":
            depth += 1
            buf.append(char)
            index += 1
            continue
        if char == ")" and depth:
            depth -= 1
            buf.append(char)
            index += 1
            continue
        if depth == 0 and comma and char == ",":
            if not flush():
                return None
            index += 1
            continue
        if depth == 0 and not comma and char.isspace():
            if "".join(buf).strip() and not flush():
                return None
            buf.clear()
            index += 1
            continue
        buf.append(char)
        index += 1
    if quote or depth:
        return None
    if "".join(buf).strip() and not flush():
        return None
    return items


def _base_matches(name: str, text: str) -> bool:
    token = text.strip()
    if name == "<number>":
        return _number_unit(token) == (token, None) and _DIMENSION.fullmatch(token) is not None and token[-1:] != "%"
    if name == "<integer>":
        return re.fullmatch(r"[+-]?\d+", token) is not None
    if name == "<length>":
        return _is_length(token)
    if name == "<percentage>":
        return _is_percentage(token)
    if name == "<length-percentage>":
        return _is_length(token) or _is_percentage(token)
    if name == "<angle>":
        return _is_dimension(token, _ANGLE_UNITS)
    if name == "<time>":
        return _is_dimension(token, _TIME_UNITS)
    if name == "<color>":
        return _is_color(token)
    if name == "<custom-ident>":
        return _IDENT_TEXT.fullmatch(token) is not None and token.lower() not in _CSS_WIDE_IDENTS
    return _IDENT_TEXT.fullmatch(token) is not None and token == name


def _number_unit(text: str) -> tuple[str, str | None] | tuple[None, None]:
    matched = _DIMENSION.fullmatch(text)
    if matched is None:
        return None, None
    return matched.group(1), matched.group(2)


def _is_length(text: str) -> bool:
    number, unit = _number_unit(text)
    if number is None:
        return False
    if unit is None:
        return _number_is_zero(number)
    return unit.lower() in _LENGTH_UNITS


def _is_percentage(text: str) -> bool:
    number, unit = _number_unit(text)
    return number is not None and unit == "%"


def _is_dimension(text: str, units: frozenset[str]) -> bool:
    number, unit = _number_unit(text)
    return number is not None and unit is not None and unit.lower() in units


def _number_is_zero(number: str) -> bool:
    try:
        return float(number) == 0.0
    except ValueError:
        return False


def _is_color(text: str) -> bool:
    if text.lower() in _NAMED_COLORS or text.lower() == "currentcolor":
        return True
    if re.fullmatch(r"#[0-9a-fA-F]{3,4}|#[0-9a-fA-F]{6}|#[0-9a-fA-F]{8}", text):
        return True
    matched = re.fullmatch(r"(rgba?|hsla?|hwb)\((.*)\)", text, re.IGNORECASE | re.DOTALL)
    if matched is None:
        return False
    return _color_inner_ok(matched.group(2))


def _color_inner_ok(inner: str) -> bool:
    body = inner.strip()
    if not body:
        return False
    cursor = 0
    while cursor < len(body):
        char = body[cursor]
        if char.isspace() or char in ",/%.+-":
            cursor += 1
            continue
        if char.isdigit():
            cursor += 1
            while cursor < len(body) and body[cursor] in "0123456789.eE+-":
                cursor += 1
            continue
        if body.startswith("none", cursor) and (cursor + 4 == len(body) or not body[cursor + 4].isalnum()):
            cursor += 4
            continue
        return False
    return True
