"""Padding-edge origin of an absolute or fixed box.

CSS 2.1 §10.1 gives an absolute box the padding edge of the nearest ancestor
whose position is not static. A fixed box ignores those merely positioned
ancestors and uses the viewport. CSS Transforms, Filters, and Containment
change that: a transform, filter, perspective, or backdrop-filter other than
none, and paint containment, establish a containing block for both absolute
and fixed descendants. ``translate(0)`` and ``blur(0)`` still count.

The rectangle is the ancestor's border box inset by its own borders. That
width and height are the percentage basis. A chosen ancestor whose display
is inline can split across line fragments, so this resolver refuses it
instead of returning one rectangle. It does not lay out the tree, and it
does not read will-change or container-type.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

_AUTO_NONE = "none"
_POSITIONS = frozenset({"static", "relative", "absolute", "fixed", "sticky"})
_SCHEMES = frozenset({"absolute", "fixed"})
_DISPLAYS = frozenset(
    {
        "block",
        "inline",
        "inline-block",
        "flex",
        "inline-flex",
        "grid",
        "inline-grid",
        "list-item",
        "flow-root",
    }
)
_CONTAIN = frozenset({"none", "paint", "layout", "size", "style", "strict", "content"})
_PAINT = frozenset({"paint", "strict", "content"})
_FIELDS = frozenset(
    {
        "id",
        "position",
        "display",
        "transform",
        "filter",
        "perspective",
        "backdrop_filter",
        "contain",
        "x",
        "y",
        "width",
        "height",
        "border_top",
        "border_right",
        "border_bottom",
        "border_left",
        "children",
    }
)
_VIEWPORT = frozenset({"x", "y", "width", "height"})


class _Invalid(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass
class _Node:
    id: str
    position: str
    display: str
    effects: bool
    x: float
    y: float
    width: float
    height: float
    border_top: float
    border_right: float
    border_bottom: float
    border_left: float
    children: list[_Node]


def resolve_containing_block(tree: object, target: object, *, viewport: object) -> dict[str, object]:
    """Return the padding edge that contains ``target``, or the viewport.

    ``target`` is the id of an absolute or fixed box. ``viewport`` is the
    initial containing block, with ``x``, ``y``, ``width``, and ``height``.
    Ancestors are walked from the parent upward. The first one that captures
    the target's scheme wins. A fixed box is captured only by an effect, not
    by position alone.
    """

    try:
        if not isinstance(target, str) or target == "":
            raise _Invalid("target")
        port = _viewport(viewport)
        root = _node(tree, set())
        path = _find(root, target)
        if path is None:
            raise _Invalid("missing")
        return _resolve(path, port)
    except _Invalid as exc:
        return _invalid(exc.reason)


def _resolve(path: list[_Node], port: dict[str, float]) -> dict[str, object]:
    target = path[-1]
    if target.position not in _SCHEMES:
        raise _Invalid("position")
    for ancestor in reversed(path[:-1]):
        if not _captures(ancestor, target.position):
            continue
        if ancestor.display == "inline":
            raise _Invalid("inline fragment")
        return _rectangle(target.position, "ancestor", ancestor.id, _padding(ancestor))
    return _rectangle(target.position, "viewport", None, port)


def _captures(ancestor: _Node, scheme: str) -> bool:
    if scheme == "fixed":
        return ancestor.effects
    return ancestor.position != "static" or ancestor.effects


def _padding(node: _Node) -> dict[str, float]:
    width = node.width - node.border_left - node.border_right
    height = node.height - node.border_top - node.border_bottom
    if width < 0.0 or height < 0.0:
        raise _Invalid("border")
    return {
        "x": node.x + node.border_left,
        "y": node.y + node.border_top,
        "width": width,
        "height": height,
    }


def _rectangle(
    scheme: str,
    source: str,
    ancestor: str | None,
    edges: dict[str, float],
) -> dict[str, object]:
    return {
        "outcome": "resolved",
        "scheme": scheme,
        "source": source,
        "ancestor": ancestor,
        "x": _number(edges["x"]),
        "y": _number(edges["y"]),
        "width": _number(edges["width"]),
        "height": _number(edges["height"]),
    }


def _viewport(value: object) -> dict[str, float]:
    if not isinstance(value, dict) or set(value) != _VIEWPORT:
        raise _Invalid("viewport")
    return {
        "x": _length(value["x"], "viewport x", minimum=None),
        "y": _length(value["y"], "viewport y", minimum=None),
        "width": _length(value["width"], "viewport width", minimum=0.0),
        "height": _length(value["height"], "viewport height", minimum=0.0),
    }


def _node(value: object, seen: set[str]) -> _Node:
    if not isinstance(value, dict) or set(value) - _FIELDS:
        raise _Invalid("box" if not isinstance(value, dict) else "field")
    raw_id = value.get("id")
    if not isinstance(raw_id, str) or raw_id == "":
        raise _Invalid("id")
    if raw_id in seen:
        raise _Invalid("duplicate")
    seen.add(raw_id)
    if "width" not in value or "height" not in value:
        raise _Invalid("width")
    position = _choice(value.get("position", "static"), _POSITIONS, "position")
    display = _choice(value.get("display", "block"), _DISPLAYS, "display")
    effects = any(
        (
            _effect(value.get("transform", _AUTO_NONE), "transform"),
            _effect(value.get("filter", _AUTO_NONE), "filter"),
            _effect(value.get("perspective", _AUTO_NONE), "perspective"),
            _effect(value.get("backdrop_filter", _AUTO_NONE), "backdrop_filter"),
            _paint(value.get("contain", _AUTO_NONE)),
        )
    )
    node = _Node(
        id=raw_id,
        position=position,
        display=display,
        effects=effects,
        x=_length(value.get("x", 0), "x", minimum=None),
        y=_length(value.get("y", 0), "y", minimum=None),
        width=_length(value["width"], "width", minimum=0.0),
        height=_length(value["height"], "height", minimum=0.0),
        border_top=_length(value.get("border_top", 0), "border_top", minimum=0.0),
        border_right=_length(value.get("border_right", 0), "border_right", minimum=0.0),
        border_bottom=_length(value.get("border_bottom", 0), "border_bottom", minimum=0.0),
        border_left=_length(value.get("border_left", 0), "border_left", minimum=0.0),
        children=[],
    )
    _padding(node)
    node.children = _children(value.get("children", []), seen)
    return node


def _children(value: object, seen: set[str]) -> list[_Node]:
    if not isinstance(value, list):
        raise _Invalid("children")
    return [_node(child, seen) for child in value]


def _find(node: _Node, target: str) -> list[_Node] | None:
    if node.id == target:
        return [node]
    for child in node.children:
        found = _find(child, target)
        if found is not None:
            return [node, *found]
    return None


def _effect(value: object, name: str) -> bool:
    return _token(value, name) != _AUTO_NONE


def _paint(value: object) -> bool:
    if not isinstance(value, str):
        raise _Invalid("contain")
    parts = value.strip().lower().split()
    if not parts or any(part not in _CONTAIN for part in parts):
        raise _Invalid("contain")
    if _AUTO_NONE in parts and parts != [_AUTO_NONE]:
        raise _Invalid("contain")
    return any(part in _PAINT for part in parts)


def _choice(value: object, allowed: frozenset[str], name: str) -> str:
    text = _token(value, name)
    if text not in allowed:
        raise _Invalid(name)
    return text


def _token(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise _Invalid(name)
    text = value.strip().lower()
    if text == "":
        raise _Invalid(name)
    return text


def _length(value: object, name: str, *, minimum: float | None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _Invalid(name)
    number = float(value)
    if not math.isfinite(number):
        raise _Invalid(name)
    if minimum is not None and number < minimum:
        raise _Invalid(name)
    return number


def _number(value: float) -> int | float:
    if value.is_integer():
        return int(value)
    return value


def _invalid(reason: str) -> dict[str, object]:
    return {
        "outcome": "invalid",
        "reason": reason,
        "scheme": None,
        "source": None,
        "ancestor": None,
        "x": None,
        "y": None,
        "width": None,
        "height": None,
    }
