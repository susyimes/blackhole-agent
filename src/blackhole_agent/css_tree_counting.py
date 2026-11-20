"""Resolve CSS sibling-index() and sibling-count() on the DOM tree.

CSS Values and Units Level 5 tree-counting functions are integers. sibling-index()
is the 1-based position of an element among its parent's element children, the
same counting :nth-child() uses. sibling-count() is how many element children
that parent has. Text nodes and comments are not children for this count.
A parentless element is the document element: index 1 of 1.

::before, ::after, and ::marker are not elements. They, including a chain such
as ::before::marker, use the ultimate originating element. :host counts the
host in the outer tree when the stylesheet lives in that host's shadow tree.
::slotted() counts the light-DOM element among its DOM siblings when the
stylesheet lives in its parent's shadow tree. ::part() is that real element.

The functions are tree-scoped references. An element in another tree, including
a descendant shadow tree of the stylesheet, resolves both functions to 0.
Shadow children are not siblings of the host's light children.

calc(), min(), max(), and clamp() then see those integers. A bare call stays
an integer. A call with an argument is invalid. sibling-index() with no unit
inside calc() is not a length.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from blackhole_agent.css_length_math import resolve_length_math

_FUNCTIONS = {"sibling-index", "sibling-count"}
_MATH = re.compile(r"(?is)^(calc|min|max|clamp)\s*\(")
_INTEGER = re.compile(r"[+-]?\d+\Z")
_ORIGIN = frozenset(
    {
        "after",
        "backdrop",
        "before",
        "cue",
        "file-selector-button",
        "marker",
        "picker",
        "picker-icon",
        "placeholder",
        "selection",
    }
)
_MAX_DEPTH = 64


class _Invalid(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass
class _El:
    kind: str
    tag: str = ""
    id: str = ""
    tree_id: str = "document"
    parent: _El | None = None
    children: list[_El] = field(default_factory=list)
    shadow_root: _El | None = None


def resolve_tree_counting(
    expression: object,
    tree: object,
    element_id: object,
    *,
    pseudo: object = "",
    style_scope: object = "document",
    percentage_basis: object = 0,
) -> dict[str, object]:
    """Resolve one value that may call sibling-index() or sibling-count().

    ``tree`` is a document element: ``tag``, ``id``, ``children``, and optional
    ``shadow`` (the shadow root's children). A ``text`` or ``comment`` node is
    not an element. ``style_scope`` is ``document`` or the id of a shadow host.
    ``pseudo`` is empty for the element itself, or a chain such as
    ``::before::marker``, ``:host``, ``::slotted``, or ``::part(name)``.
    """

    try:
        return _resolve(expression, tree, element_id, pseudo, style_scope, percentage_basis)
    except _Invalid as exc:
        return _payload(reason=exc.reason)


def _resolve(
    expression: object,
    tree: object,
    element_id: object,
    pseudo: object,
    style_scope: object,
    percentage_basis: object,
) -> dict[str, object]:
    if not isinstance(expression, str) or not expression.strip():
        raise _Invalid("expression")
    if not isinstance(element_id, str) or not element_id:
        raise _Invalid("element")
    if not isinstance(style_scope, str) or not style_scope:
        raise _Invalid("scope")
    basis = _basis(percentage_basis)
    mode = _mode(pseudo)
    calls = _calls(expression)
    elements: dict[str, _El] = {}
    root = _build(tree, None, "document", elements, 0)
    if root.kind != "element":
        raise _Invalid("tree")
    target = elements.get(element_id)
    if target is None:
        raise _Invalid("missing")
    if style_scope != "document":
        host = elements.get(style_scope)
        if host is None or host.shadow_root is None:
            raise _Invalid("scope")
    if not calls:
        raise _Invalid("function")
    index, count, scoped = _numbers(target, style_scope, mode)
    if any(not valid for _, _, _, valid in calls):
        return _payload(
            reason="argument",
            index=index,
            count=count,
            scoped=scoped,
        )
    substituted = _substitute(expression, calls, index, count).strip()
    if _INTEGER.fullmatch(substituted):
        return _payload(
            outcome="resolved",
            index=index,
            count=count,
            scoped=scoped,
            value=substituted,
            reason="",
        )
    if _MATH.match(substituted) is None:
        return _payload(
            reason="value",
            index=index,
            count=count,
            scoped=scoped,
            value=substituted,
        )
    math_result = resolve_length_math(substituted, percentage_basis=basis)
    if math_result["outcome"] != "resolved":
        return _payload(
            reason=str(math_result["reason"] or "math"),
            index=index,
            count=count,
            scoped=scoped,
            value=substituted,
        )
    return _payload(
        outcome="resolved",
        index=index,
        count=count,
        scoped=scoped,
        value=substituted,
        px=math_result["px"],
        reason="",
    )


def _basis(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _Invalid("basis")
    basis = float(value)
    if basis < 0 or not math.isfinite(basis):
        raise _Invalid("basis")
    return basis


def _mode(pseudo: object) -> str:
    if not isinstance(pseudo, str):
        raise _Invalid("pseudo")
    parts = [part for part in pseudo.strip().lower().replace("::", ":").split(":") if part]
    while parts and parts[-1].split("(", 1)[0].strip() in _ORIGIN:
        parts.pop()
    if not parts:
        return "element"
    name = parts[0].split("(", 1)[0].strip()
    if len(parts) == 1 and name == "host":
        return "host"
    if len(parts) == 1 and name == "slotted":
        return "slotted"
    if len(parts) == 1 and name == "part":
        return "element"
    raise _Invalid("pseudo")


def _numbers(target: _El, style_scope: str, mode: str) -> tuple[int, int, bool]:
    if mode == "host":
        if style_scope != target.id or target.shadow_root is None:
            return 0, 0, False
        index, count = _count(target)
        return index, count, True
    if mode == "slotted":
        parent = target.parent
        if (
            parent is None
            or parent.kind != "element"
            or parent.shadow_root is None
            or style_scope != parent.id
        ):
            return 0, 0, False
        index, count = _count(target)
        return index, count, True
    if target.tree_id == style_scope:
        index, count = _count(target)
        return index, count, True
    return 0, 0, False


def _count(node: _El) -> tuple[int, int]:
    parent = node.parent
    siblings = [node] if parent is None else [child for child in parent.children if child.kind == "element"]
    return siblings.index(node) + 1, len(siblings)


def _build(node: object, parent: _El | None, tree_id: str, elements: dict[str, _El], depth: int) -> _El:
    if depth > _MAX_DEPTH or not isinstance(node, dict):
        raise _Invalid("tree")
    if "text" in node:
        if any(key in node for key in ("tag", "comment", "children", "shadow")):
            raise _Invalid("tree")
        element = _El(kind="text", parent=parent, tree_id=tree_id)
        if parent is not None:
            parent.children.append(element)
        return element
    if "comment" in node:
        if any(key in node for key in ("tag", "children", "shadow")):
            raise _Invalid("tree")
        element = _El(kind="comment", parent=parent, tree_id=tree_id)
        if parent is not None:
            parent.children.append(element)
        return element
    tag = node.get("tag")
    if not isinstance(tag, str) or not tag:
        raise _Invalid("tree")
    identity = node.get("id", "")
    if not isinstance(identity, str):
        raise _Invalid("tree")
    element = _El(kind="element", tag=tag, id=identity, parent=parent, tree_id=tree_id)
    if parent is not None:
        parent.children.append(element)
    if identity:
        if identity in elements:
            raise _Invalid("duplicate")
        elements[identity] = element
    children = node.get("children", [])
    if not isinstance(children, list):
        raise _Invalid("tree")
    for child in children:
        _build(child, element, tree_id, elements, depth + 1)
    if "shadow" in node:
        shadow = node["shadow"]
        if not isinstance(shadow, list) or not identity:
            raise _Invalid("tree")
        root = _El(kind="shadow", parent=None, tree_id=identity)
        element.shadow_root = root
        for child in shadow:
            _build(child, root, identity, elements, depth + 1)
    return element


def _calls(expression: str) -> list[tuple[int, int, str, bool]]:
    found: list[tuple[int, int, str, bool]] = []
    index = 0
    size = len(expression)
    while index < size:
        if expression.startswith("/*", index):
            index = _comment_end(expression, index)
            continue
        if expression[index] in "\"'":
            index = _string_end(expression, index)
            continue
        if expression[index].isalpha() or expression[index] == "_":
            start = index
            index += 1
            while index < size and (expression[index].isalnum() or expression[index] in "_-"):
                index += 1
            name = expression[start:index].lower()
            if name in _FUNCTIONS:
                cursor = _skip_ignorable(expression, index)
                if cursor < size and expression[cursor] == "(":
                    end, valid = _consume_call(expression, cursor)
                    found.append((start, end, name, valid))
                    index = end
            continue
        index += 1
    return found


def _substitute(expression: str, calls: list[tuple[int, int, str, bool]], index: int, count: int) -> str:
    pieces: list[str] = []
    cursor = 0
    for start, end, name, _valid in calls:
        pieces.append(expression[cursor:start])
        pieces.append(str(index if name == "sibling-index" else count))
        cursor = end
    pieces.append(expression[cursor:])
    return "".join(pieces)


def _consume_call(text: str, open_paren: int) -> tuple[int, bool]:
    cursor = _skip_ignorable(text, open_paren + 1)
    if cursor < len(text) and text[cursor] == ")":
        return cursor + 1, True
    depth = 1
    cursor = open_paren + 1
    size = len(text)
    while cursor < size:
        if text.startswith("/*", cursor):
            cursor = _comment_end(text, cursor)
            continue
        if text[cursor] in "\"'":
            cursor = _string_end(text, cursor)
            continue
        if text[cursor] == "(":
            depth += 1
        elif text[cursor] == ")":
            depth -= 1
            if depth == 0:
                return cursor + 1, False
        cursor += 1
    raise _Invalid("syntax")


def _skip_ignorable(text: str, index: int) -> int:
    size = len(text)
    while index < size:
        if text[index].isspace():
            index += 1
            continue
        if text.startswith("/*", index):
            index = _comment_end(text, index)
            continue
        break
    return index


def _comment_end(text: str, index: int) -> int:
    end = text.find("*/", index + 2)
    if end < 0:
        raise _Invalid("syntax")
    return end + 2


def _string_end(text: str, index: int) -> int:
    quote = text[index]
    cursor = index + 1
    size = len(text)
    while cursor < size:
        if text[cursor] == "\\":
            cursor += 2
            continue
        if text[cursor] == quote:
            return cursor + 1
        cursor += 1
    raise _Invalid("syntax")


def _payload(**kwargs: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "outcome": "invalid",
        "index": None,
        "count": None,
        "scoped": False,
        "value": "",
        "px": None,
        "reason": "",
    }
    payload.update(kwargs)
    return payload
