"""Resolve CSS list counters and format their values.

CSS Lists and Counters Level 3. Each element has an ordered set of counters.
A counter records its name, the element that created it, whether it is
reversed, and an integer. ``counter()`` reads the innermost counter of that
name. ``counters()`` reads every counter of that name from outer to inner.

Tree order visits an element, then its ``before`` pseudo-element, then its
children, then its ``after`` pseudo-element. An element inherits the counters
its preceding sibling still has, or its parent when it has no preceding
sibling. The integers come from the element that immediately precedes it in
tree order, so a descendant's increment is visible to the next sibling. A
``counter-reset`` on a child nests inside an ancestor counter of the same
name. A reset whose innermost counter was created by the element or by one
of its preceding siblings replaces that counter instead of nesting.

On one element the order is reset, then increment, then set, then a read.
The last reset of a name is the only one created. Every increment of a name
adds. The last set of a name is the value that remains. A missing counter is
created at zero before an increment, a set, or a read. ``display: none``
generates no box: that element and its descendants do not touch counters.
``visibility`` is not consulted. On a pseudo-element, ``content: none`` does
the same.

A ``list-item`` box increments ``list-item`` by 1, or by -1 when the current
``list-item`` counter is reversed, unless ``counter-increment`` already names
``list-item``. ``counter-increment: none`` still receives that automatic
increment. A reversed counter with no integer takes the automatic start from
the later increments and sets in its scope, then those operations are applied.
"""

from __future__ import annotations

from dataclasses import dataclass

_FORBIDDEN = frozenset(
    {"none", "inherit", "initial", "unset", "revert", "revert-layer", "default"}
)
_FIELDS = frozenset(
    {
        "id",
        "display",
        "content",
        "counter_reset",
        "counter_increment",
        "counter_set",
        "read",
        "children",
        "before",
        "after",
    }
)
_STYLES = frozenset(
    {
        "decimal",
        "lower-alpha",
        "upper-alpha",
        "lower-latin",
        "upper-latin",
        "lower-roman",
        "upper-roman",
        "none",
    }
)
_ROMAN = (
    (1000, "m"),
    (900, "cm"),
    (500, "d"),
    (400, "cd"),
    (100, "c"),
    (90, "xc"),
    (50, "l"),
    (40, "xl"),
    (10, "x"),
    (9, "ix"),
    (5, "v"),
    (4, "iv"),
    (1, "i"),
)


class _Invalid(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class _Reset:
    name: str
    reversed: bool
    value: int | None


@dataclass(frozen=True)
class _Counter:
    name: str
    origin: str
    reversed: bool
    initial: int | None

    @property
    def key(self) -> str:
        return f"{self.origin}\x1f{self.name}"


@dataclass
class _Node:
    id: str
    resets: list[_Reset]
    increments: list[tuple[str, int]]
    sets: list[tuple[str, int]]
    reads: list[str]
    generates: bool
    list_item: bool
    before: _Node | None
    after: _Node | None
    children: list[_Node]
    own_stack: list[_Counter] | None = None


@dataclass
class _Visit:
    id: str
    ops: list[tuple[object, ...]]
    stack: list[_Counter]


class _Scan:
    def __init__(self, text: str) -> None:
        self.text = text
        self.i = 0
        self.n = len(text)

    def skip(self) -> None:
        while self.i < self.n:
            if self.text[self.i].isspace():
                self.i += 1
                continue
            if self.text.startswith("/*", self.i):
                end = self.text.find("*/", self.i + 2)
                if end < 0:
                    raise _Invalid("unclosed comment")
                self.i = end + 2
                continue
            break

    def peek(self) -> str:
        self.skip()
        if self.i >= self.n:
            return ""
        return self.text[self.i]

    def _ident_at(self, index: int) -> bool:
        if index >= self.n:
            return False
        char = self.text[index]
        return char == "_" or char.isalpha() or ord(char) > 127

    def ident(self) -> str | None:
        self.skip()
        if self.i >= self.n:
            return None
        start = self.i
        if self.text[self.i] == "-":
            if self.i + 1 < self.n and self.text[self.i + 1] == "-":
                self.i += 2
            elif self._ident_at(self.i + 1):
                self.i += 2
            else:
                return None
        elif self._ident_at(self.i):
            self.i += 1
        else:
            return None
        while self.i < self.n:
            char = self.text[self.i]
            if char == "_" or char.isalpha() or char.isdigit() or char == "-" or ord(char) > 127:
                self.i += 1
                continue
            break
        token = self.text[start : self.i]
        if token in {"", "-"}:
            return None
        return token

    def number(self) -> int | None:
        self.skip()
        if self.i >= self.n:
            return None
        start = self.i
        if self.text[self.i] in "+-":
            if self.i + 1 >= self.n or not self.text[self.i + 1].isdigit():
                return None
            self.i += 1
        if self.i >= self.n or not self.text[self.i].isdigit():
            self.i = start
            return None
        while self.i < self.n and self.text[self.i].isdigit():
            self.i += 1
        if self.i < self.n and self.text[self.i] in ".eE":
            raise _Invalid("counter values must be integers")
        return int(self.text[start : self.i])


def _name(token: str) -> str:
    if token.lower() in _FORBIDDEN:
        raise _Invalid(f"counter name {token} is reserved")
    return token


def _alone_none(scan: _Scan) -> bool:
    saved = scan.i
    token = scan.ident()
    if token is not None and token.lower() == "none":
        scan.skip()
        if scan.i != scan.n:
            raise _Invalid("none must be the whole counter value")
        return True
    scan.i = saved
    return False


def _finish(scan: _Scan, what: str) -> None:
    scan.skip()
    if scan.i != scan.n:
        raise _Invalid(f"{what} has trailing text")


def _last_resets(items: list[_Reset]) -> list[_Reset]:
    last: dict[str, int] = {}
    for index, item in enumerate(items):
        last[item.name] = index
    return [item for index, item in enumerate(items) if last[item.name] == index]


def _parse_reset(text: str) -> list[_Reset]:
    scan = _Scan(text)
    scan.skip()
    if scan.i >= scan.n or _alone_none(scan):
        return []
    items: list[_Reset] = []
    while scan.peek():
        token = scan.ident()
        if token is None:
            raise _Invalid("counter-reset is invalid")
        if token.lower() == "reversed" and scan.peek() == "(":
            scan.i += 1
            inner = scan.ident()
            if inner is None or scan.peek() != ")":
                raise _Invalid("reversed() needs a counter name")
            scan.i += 1
            items.append(_Reset(_name(inner), True, scan.number()))
            continue
        items.append(_Reset(_name(token), False, 0 if (number := scan.number()) is None else number))
    if not items:
        raise _Invalid("counter-reset is invalid")
    return _last_resets(items)


def _parse_pairs(text: str, what: str, default: int) -> list[tuple[str, int]]:
    scan = _Scan(text)
    scan.skip()
    if scan.i >= scan.n or _alone_none(scan):
        return []
    items: list[tuple[str, int]] = []
    while scan.peek():
        token = scan.ident()
        if token is None or scan.peek() == "(":
            raise _Invalid(f"{what} is invalid")
        number = scan.number()
        items.append((_name(token), default if number is None else number))
    if not items:
        raise _Invalid(f"{what} is invalid")
    return items


def _parse_reads(value: object) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise _Invalid("read must be a list of counter names")
    names: list[str] = []
    for item in value:
        scan = _Scan(item)
        token = scan.ident()
        if token is None:
            raise _Invalid("read counter name is invalid")
        _finish(scan, "read counter name")
        names.append(_name(token))
    return names


def _property(node: dict[str, object], key: str) -> str:
    if key not in node or node[key] is None:
        return ""
    value = node[key]
    if not isinstance(value, str):
        raise _Invalid(f"{key} must be a string")
    return value


def _parse_node(value: object, seen: set[str], *, pseudo: bool) -> _Node:
    if not isinstance(value, dict):
        raise _Invalid("element must be an object")
    unknown = set(value) - _FIELDS
    if unknown:
        name = sorted(unknown)[0]
        raise _Invalid(f"unknown element field {name}")
    ident = value.get("id")
    if not isinstance(ident, str) or not ident:
        raise _Invalid("element id must be a non-empty string")
    if ident in seen:
        raise _Invalid(f"duplicate element id {ident}")
    seen.add(ident)
    if "display" in value and value["display"] is not None:
        display = value["display"]
        if not isinstance(display, str) or not display.strip():
            raise _Invalid("display must be a keyword")
        keyword = display.strip().lower()
        if any(char.isspace() for char in keyword) or not all(
            char.isalnum() or char == "-" for char in keyword
        ):
            raise _Invalid("display must be a single keyword")
    else:
        keyword = "block"
    generates = keyword != "none"
    list_item = keyword == "list-item"
    if pseudo and "content" in value and value["content"] is not None:
        content = value["content"]
        if not isinstance(content, str):
            raise _Invalid("content must be a string")
        if content.strip().lower() == "none":
            generates = False
            list_item = False
    elif "content" in value and value["content"] is not None and not isinstance(value["content"], str):
        raise _Invalid("content must be a string")
    children_value = value.get("children", [])
    if children_value is None:
        children_value = []
    if not isinstance(children_value, list):
        raise _Invalid("children must be a list")
    before_value = value.get("before")
    after_value = value.get("after")
    if before_value is not None and not isinstance(before_value, dict):
        raise _Invalid("before must be an element")
    if after_value is not None and not isinstance(after_value, dict):
        raise _Invalid("after must be an element")
    return _Node(
        id=ident,
        resets=_parse_reset(_property(value, "counter_reset")),
        increments=_parse_pairs(_property(value, "counter_increment"), "counter-increment", 1),
        sets=_parse_pairs(_property(value, "counter_set"), "counter-set", 0),
        reads=_parse_reads(value.get("read")),
        generates=generates,
        list_item=list_item and generates,
        before=_parse_node(before_value, seen, pseudo=True) if isinstance(before_value, dict) else None,
        after=_parse_node(after_value, seen, pseudo=True) if isinstance(after_value, dict) else None,
        children=[_parse_node(child, seen, pseudo=False) for child in children_value],
    )


def _inherit(counter_source: list[_Counter], value_source: list[_Counter]) -> list[_Counter]:
    present = {(counter.name, counter.origin) for counter in counter_source}
    return [
        counter
        for counter in value_source
        if (counter.name, counter.origin) in present
    ]


def _innermost(stack: list[_Counter], name: str) -> int | None:
    for index in range(len(stack) - 1, -1, -1):
        if stack[index].name == name:
            return index
    return None


def _replace_sibling(stack: list[_Counter], name: str, element_id: str, previous: set[str]) -> None:
    index = _innermost(stack, name)
    if index is None:
        return
    origin = stack[index].origin
    if origin == element_id or origin in previous:
        del stack[index]


def _create(
    stack: list[_Counter],
    ops: list[tuple[object, ...]],
    *,
    name: str,
    element_id: str,
    previous: set[str],
    reversed_counter: bool,
    initial: int | None,
) -> _Counter:
    _replace_sibling(stack, name, element_id, previous)
    counter = _Counter(name, element_id, reversed_counter, initial)
    stack.append(counter)
    ops.append(("init", counter.key, initial))
    return counter


def _apply(
    node: _Node,
    stack: list[_Counter],
    ops: list[tuple[object, ...]],
    previous: set[str],
) -> None:
    for item in node.resets:
        _create(
            stack,
            ops,
            name=item.name,
            element_id=node.id,
            previous=previous,
            reversed_counter=item.reversed,
            initial=item.value,
        )
    increments = list(node.increments)
    if node.list_item and all(name != "list-item" for name, _amount in increments):
        current = _innermost(stack, "list-item")
        amount = -1 if current is not None and stack[current].reversed else 1
        increments.append(("list-item", amount))
    for name, amount in increments:
        index = _innermost(stack, name)
        if index is None:
            counter = _create(
                stack,
                ops,
                name=name,
                element_id=node.id,
                previous=previous,
                reversed_counter=False,
                initial=0,
            )
        else:
            counter = stack[index]
        ops.append(("inc", counter.key, amount))
    for name, amount in node.sets:
        index = _innermost(stack, name)
        if index is None:
            counter = _create(
                stack,
                ops,
                name=name,
                element_id=node.id,
                previous=previous,
                reversed_counter=False,
                initial=0,
            )
        else:
            counter = stack[index]
        ops.append(("set", counter.key, amount))
    for name in node.reads:
        if _innermost(stack, name) is None:
            _create(
                stack,
                ops,
                name=name,
                element_id=node.id,
                previous=previous,
                reversed_counter=False,
                initial=0,
            )


def _walk(root: _Node) -> list[_Visit]:
    visits: list[_Visit] = []

    def visit_recording(
        node: _Node,
        parent_stack: list[_Counter] | None,
        prev_tree: list[_Counter] | None,
        prev_sibling: list[_Counter] | None,
        previous_ids: set[str],
        *,
        root_element: bool,
    ) -> list[_Counter] | None:
        if not node.generates:
            return prev_tree
        if root_element:
            stack = []
        else:
            source = prev_sibling if prev_sibling is not None else (parent_stack or [])
            stack = _inherit(source, prev_tree or [])
        ops: list[tuple[object, ...]] = []
        _apply(node, stack, ops, previous_ids)
        own = list(stack)
        node.own_stack = own
        visits.append(_Visit(node.id, ops, own))
        sequence: list[_Node] = []
        if node.before is not None:
            sequence.append(node.before)
        sequence.extend(node.children)
        if node.after is not None:
            sequence.append(node.after)
        last: list[_Counter] | None = own
        sibling_stack: list[_Counter] | None = None
        sibling_ids: set[str] = set()
        for child in sequence:
            if not child.generates:
                continue
            last = visit_recording(
                child,
                own,
                last,
                sibling_stack,
                set(sibling_ids),
                root_element=False,
            )
            sibling_stack = child.own_stack
            sibling_ids.add(child.id)
        return last

    visit_recording(root, None, None, None, set(), root_element=True)
    return visits


def _automatic(visits: list[_Visit], key: str) -> int:
    total = 0
    last_nonzero = 0
    for visit in visits:
        increment = 0
        saw_increment = False
        saw_set = False
        set_value = 0
        for op in visit.ops:
            if op[0] == "inc" and op[1] == key:
                saw_increment = True
                increment += int(op[2])
            elif op[0] == "set" and op[1] == key:
                saw_set = True
                set_value = int(op[2])
        if not saw_increment and not saw_set:
            continue
        negated = -increment
        if negated != 0:
            last_nonzero = negated
        if saw_set:
            total += set_value
            break
        total += negated
    return total + last_nonzero


def _replay(visits: list[_Visit]) -> dict[str, dict[str, object]]:
    values: dict[str, int] = {}
    elements: dict[str, dict[str, object]] = {}
    for visit in visits:
        for op in visit.ops:
            kind = op[0]
            key = str(op[1])
            if kind == "init":
                if key in values:
                    continue
                initial = op[2]
                values[key] = _automatic(visits, key) if initial is None else int(initial)
            elif kind == "inc":
                values[key] = values[key] + int(op[2])
            elif kind == "set":
                values[key] = int(op[2])
        innermost: dict[str, int] = {}
        stacks: dict[str, list[int]] = {}
        reversed_flags: dict[str, bool] = {}
        for counter in visit.stack:
            stacks.setdefault(counter.name, []).append(values[counter.key])
            innermost[counter.name] = values[counter.key]
            reversed_flags[counter.name] = counter.reversed
        elements[visit.id] = {
            "values": innermost,
            "stacks": stacks,
            "reversed": reversed_flags,
        }
    return elements


def resolve_counters(tree: object) -> dict[str, object]:
    """Return each generating element's counters after CSS Lists processing.

    ``counter_reset``, ``counter_increment``, and ``counter_set`` are the CSS
    values. ``read`` names counters used by ``counter()`` or ``counters()``.
    ``before`` and ``after`` are optional pseudo-elements. The result's
    ``values`` map is the innermost integer, and ``stacks`` lists every scope
    from outer to inner.
    """

    try:
        root = _parse_node(tree, set(), pseudo=False)
        elements = _replay(_walk(root))
    except _Invalid as exc:
        return {"outcome": "invalid", "reason": exc.reason}
    return {"outcome": "ok", "elements": elements}


def _alpha(value: int, first: str) -> str:
    if value <= 0:
        return str(value)
    letters: list[str] = []
    base = ord(first)
    remaining = value
    while remaining:
        remaining -= 1
        letters.append(chr(base + remaining % 26))
        remaining //= 26
    return "".join(reversed(letters))


def _roman(value: int, upper: bool) -> str:
    if value <= 0:
        return str(value)
    glyphs: list[str] = []
    remaining = value
    for amount, glyph in _ROMAN:
        while remaining >= amount:
            glyphs.append(glyph)
            remaining -= amount
    text = "".join(glyphs)
    return text.upper() if upper else text


def format_counter(value: object, style: object = "decimal") -> dict[str, object]:
    """Format one counter integer in a predefined counter style."""

    if isinstance(value, bool) or not isinstance(value, int):
        return {"outcome": "invalid", "reason": "counter value must be an integer"}
    if not isinstance(style, str):
        return {"outcome": "invalid", "reason": "counter style is invalid"}
    chosen = style.strip().lower()
    if chosen not in _STYLES:
        return {"outcome": "invalid", "reason": f"counter style {style} is invalid"}
    if chosen == "none":
        text = ""
    elif chosen == "decimal":
        text = str(value)
    elif chosen in {"lower-alpha", "lower-latin"}:
        text = _alpha(value, "a")
    elif chosen in {"upper-alpha", "upper-latin"}:
        text = _alpha(value, "A")
    elif chosen == "lower-roman":
        text = _roman(value, False)
    else:
        text = _roman(value, True)
    return {"outcome": "ok", "text": text}


def format_counters(values: object, separator: object, style: object = "decimal") -> dict[str, object]:
    """Join counter scopes from outer to inner, as ``counters()`` does."""

    if not isinstance(values, list) or isinstance(separator, bool) or not isinstance(separator, str):
        return {"outcome": "invalid", "reason": "counters() arguments are invalid"}
    parts: list[str] = []
    for value in values:
        rendered = format_counter(value, style)
        if rendered["outcome"] != "ok":
            return rendered
        parts.append(str(rendered["text"]))
    return {"outcome": "ok", "text": separator.join(parts)}
