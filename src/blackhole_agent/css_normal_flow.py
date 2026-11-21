"""Place normal-flow block boxes from a document and a stylesheet.

Each isolated solver already knows one equation: the inline size, the
collapsed vertical margins, or the winning declaration. None of them can
answer where a block paints. Percentage widths were resolved against a
measure the caller invented, and adjoining margins were somebody else's
addition.

This walk kills that split. A stylesheet is cascaded onto the parsed
document, custom properties are substituted, and each block is sized
against its parent's used content box. Adjoining vertical margins then
collapse, and the root box keeps its own margin instead of collapsing
through to the viewport. ``display: none``, floats, and absolute or fixed
boxes leave the flow. An automatic height is the block children only;
there are no line boxes. ``writing-mode``, ``direction``, and
``text-orientation`` inherit. Other wide keywords on box properties use
the initial value.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from blackhole_agent.css_length_math import is_length_math
from blackhole_agent.css_logical_box import (
    _LOGICAL,
    _LOGICAL_SHORTHAND,
    _PHYSICAL_SHORTHAND,
    _SIZES,
    resolve_logical_box,
)
from blackhole_agent.css_margin_collapse import place_collapsed_margins
from blackhole_agent.css_selectors import (
    CssSelectorError,
    _INVALID,
    _attr,
    _computed_style,
    _declaration_precedence,
    _document,
    _local_name,
    _stylesheet,
    _substitute,
    _wide_keyword,
)
from blackhole_agent.css_writing_mode import resolve_writing_mode

_BOX_PROPS = (
    set(_LOGICAL)
    | set(_SIZES)
    | set(_PHYSICAL_SHORTHAND)
    | set(_LOGICAL_SHORTHAND)
    | {
        "width",
        "height",
        "min-width",
        "max-width",
        "min-height",
        "max-height",
        "box-sizing",
        "margin-top",
        "margin-right",
        "margin-bottom",
        "margin-left",
        "padding-top",
        "padding-right",
        "padding-bottom",
        "padding-left",
        "border-top-width",
        "border-right-width",
        "border-bottom-width",
        "border-left-width",
        "border-top-style",
        "border-right-style",
        "border-bottom-style",
        "border-left-style",
        "top",
        "right",
        "bottom",
        "left",
    }
)
_BLOCK_TAGS = frozenset(
    {
        "address",
        "article",
        "aside",
        "blockquote",
        "body",
        "dd",
        "details",
        "dialog",
        "div",
        "dl",
        "dt",
        "fieldset",
        "figcaption",
        "figure",
        "footer",
        "form",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hgroup",
        "hr",
        "html",
        "li",
        "main",
        "nav",
        "ol",
        "p",
        "pre",
        "section",
        "ul",
    }
)
_SKIP_TAGS = frozenset({"base", "head", "link", "meta", "script", "style", "template", "title"})
_DISPLAYS = frozenset({"block", "inline", "inline-block", "none"})
_POSITIONS = frozenset({"static", "relative", "absolute", "fixed"})
_FLOATS = frozenset({"none", "left", "right"})
_OVERFLOWS = frozenset({"visible", "hidden", "auto", "scroll", "clip"})
_INHERITED = {
    "writing-mode": "horizontal-tb",
    "direction": "ltr",
    "text-orientation": "mixed",
}


class _Invalid(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass
class _Box:
    id: str
    writing_mode: str
    direction: str
    text_orientation: str
    display: str
    position: str
    float_side: str
    overflow: str
    declarations: list[tuple[str, str]]
    root: bool = False
    children: list[_Box] = field(default_factory=list)
    solved: dict[str, object] = field(default_factory=dict)
    definite_height: int | None = None
    x: int = 0
    y: int = 0
    content_width: int = 0
    content_height: int = 0
    border_width: int = 0
    border_height: int = 0
    margin_left: int = 0
    margin_right: int = 0


def layout_normal_flow(
    markup: str,
    stylesheet: str,
    *,
    viewport_width: int,
    viewport_height: int | None = None,
) -> dict[str, object]:
    """Return viewport border boxes for the document's normal-flow blocks.

    ``viewport_width`` is the initial containing block's width in CSS pixels.
    ``viewport_height`` is that block's height, or indefinite when omitted.
    ``x`` and ``y`` are the border edges measured from the viewport origin.
    Lengths are ``px`` or percentages. A unitless zero is rejected. Rules come
    from the stylesheet; a style attribute is not read.
    """

    if not isinstance(markup, str) or not isinstance(stylesheet, str):
        return _invalid("markup is invalid")
    if type(viewport_width) is not int or viewport_width < 0:
        return _invalid("viewport width is invalid")
    if viewport_height is not None and (type(viewport_height) is not int or viewport_height < 0):
        return _invalid("viewport height is invalid")
    try:
        tree, order = _document(markup)
        if not order:
            raise _Invalid("document is empty")
        declarations, registrations = _stylesheet(stylesheet)
        styles: dict[object, tuple[dict, str]] = {}
        for element in order:
            parent = tree.parent.get(element)
            parent_custom, parent_color = styles.get(parent, ({}, ""))
            styles[element] = _computed_style(
                tree,
                element,
                declarations,
                parent_custom,
                parent_color,
                registrations,
            )
        ids: set[str] = set()
        counter = [0]
        root = _make_box(tree, order[0], _INHERITED.copy(), styles, declarations, ids, counter, root=True)
        if root.display == "none":
            raise _Invalid("root is not displayed")
        if root.position in {"absolute", "fixed"} or root.float_side != "none":
            raise _Invalid("root is outside normal flow")
        root.children = _walk(tree, order[0], _modes(root), styles, declarations, ids, counter)
        _solve(root, viewport_width, viewport_height, True, 0)
        placed = place_collapsed_margins(_collapse_spec(root))
        if placed.get("outcome") != "placed" or not isinstance(placed.get("boxes"), list):
            raise _Invalid(str(placed.get("reason") or "margin collapse failed"))
        by_id = {str(item["id"]): item for item in placed["boxes"] if isinstance(item, dict)}
        margin_top = _px(root.solved.get("margin_top"), "margin-top")
        _assign_y(root, by_id, margin_top)
        boxes = [_record(box) for box in _each(root)]
    except (CssSelectorError, _Invalid) as exc:
        return _invalid(str(exc))
    return {"outcome": "placed", "reason": None, "boxes": boxes}


def _invalid(reason: str) -> dict[str, object]:
    return {"outcome": "invalid", "reason": reason, "boxes": None}


def _modes(box: _Box) -> dict[str, str]:
    return {
        "writing-mode": box.writing_mode,
        "direction": box.direction,
        "text-orientation": box.text_orientation,
    }


def _walk(tree, element, inherited: dict[str, str], styles, declarations, ids: set[str], counter: list[int]) -> list[_Box]:
    found: list[_Box] = []
    for child in tree.children.get(element, []):
        if _local_name(child) in _SKIP_TAGS:
            continue
        box = _make_box(tree, child, inherited, styles, declarations, ids, counter, root=False)
        if box.display == "none" or box.position in {"absolute", "fixed"} or box.float_side != "none":
            continue
        if box.display == "inline":
            found.extend(_walk(tree, child, _modes(box), styles, declarations, ids, counter))
            continue
        box.children = _walk(tree, child, _modes(box), styles, declarations, ids, counter)
        found.append(box)
    return found


def _make_box(tree, element, inherited, styles, declarations, ids: set[str], counter: list[int], *, root: bool) -> _Box:
    custom = styles.get(element, ({}, ""))[0]
    winners = _winners(tree, element, declarations)
    mode = _inherited("writing-mode", winners, custom, inherited)
    direction = _inherited("direction", winners, custom, inherited)
    orientation = _inherited("text-orientation", winners, custom, inherited)
    display = _keyword(
        _declared(winners, "display", custom),
        _DISPLAYS,
        "block" if _local_name(element) in _BLOCK_TAGS else "inline",
        "display",
    )
    position = _keyword(_declared(winners, "position", custom), _POSITIONS, "static", "position")
    float_side = _keyword(_declared(winners, "float", custom), _FLOATS, "none", "float")
    overflow = _keyword(_declared(winners, "overflow", custom), _OVERFLOWS, "visible", "overflow")
    box_declarations = [
        (prop, value)
        for prop, value in ((_prop, _declared(winners, _prop, custom)) for _prop in _winner_names(winners))
        if prop in _BOX_PROPS and value is not None and _wide_keyword(value) is None
    ]
    author = (_attr(element, "id") or "").strip()
    if author:
        if author in ids:
            raise _Invalid("duplicate id")
        box_id = author
    else:
        counter[0] += 1
        box_id = _local_name(element) or "anon"
        if box_id in ids:
            box_id = f"anon-{counter[0]}"
        while box_id in ids:
            counter[0] += 1
            box_id = f"anon-{counter[0]}"
    ids.add(box_id)
    return _Box(
        id=box_id,
        writing_mode=mode,
        direction=direction,
        text_orientation=orientation,
        display=display,
        position=position,
        float_side=float_side,
        overflow=overflow,
        declarations=box_declarations,
        root=root,
    )


def _winners(tree, element, declarations) -> list[tuple[int, str, str]]:
    grouped: dict[str, list[tuple[tuple, object]]] = {}
    for decl in declarations:
        if str(decl.prop).startswith("--"):
            continue
        parts = _declaration_precedence(tree, element, decl)
        if parts is None:
            continue
        specificity, proximity = parts
        layer_priority = -decl.layer if decl.important else decl.layer
        rank = (decl.important, layer_priority, specificity, -proximity, decl.order)
        grouped.setdefault(decl.prop, []).append((rank, decl))
    chosen: list[tuple[int, str, str]] = []
    for prop, items in grouped.items():
        items.sort(key=lambda item: item[0], reverse=True)
        rejected: set[int] = set()
        for _rank, decl in items:
            if decl.layer in rejected:
                continue
            if str(decl.value).strip().lower() == "revert-layer":
                rejected.add(decl.layer)
                continue
            chosen.append((int(decl.order), prop, str(decl.value)))
            break
    chosen.sort(key=lambda item: item[0])
    return chosen


def _winner_names(winners: list[tuple[int, str, str]]) -> list[str]:
    return [prop for _order, prop, _value in winners]


def _declared(winners: list[tuple[int, str, str]], name: str, custom: dict) -> str | None:
    found = None
    for _order, prop, value in winners:
        if prop == name:
            found = value
    if found is None:
        return None
    if _wide_keyword(found) is not None:
        return found.strip().lower()
    substituted = _substitute(found, lambda key: custom.get(key, _INVALID))
    if substituted is _INVALID or not isinstance(substituted, str) or not substituted.strip():
        return None
    return substituted


def _inherited(name: str, winners, custom: dict, inherited: dict[str, str]) -> str:
    raw = _declared(winners, name, custom)
    if raw is None or raw in {"inherit", "unset", "revert"}:
        return inherited[name]
    if raw == "initial":
        return _INHERITED[name]
    return raw.strip().lower()


def _keyword(value: str | None, allowed: frozenset[str], default: str, name: str) -> str:
    if value is None or value in {"initial", "unset", "revert"}:
        return default
    if value == "inherit":
        raise _Invalid(f"{name} inherit is unsupported")
    token = value.strip().lower()
    if token not in allowed:
        raise _Invalid(f"{name} is invalid")
    return token


def _solve(box: _Box, parent_width: int, parent_height: int | None, parent_horizontal: bool, parent_content_x: int) -> None:
    flow = resolve_writing_mode(box.writing_mode, box.direction, text_orientation=box.text_orientation)
    if flow.get("outcome") != "resolved":
        raise _Invalid(str(flow.get("reason") or "writing-mode is invalid"))
    horizontal = flow.get("horizontal") is True
    available_inline, available_block = _available(parent_horizontal, parent_width, parent_height, horizontal)
    if available_inline is None:
        raise _Invalid("indefinite inline containing size")
    declarations = list(box.declarations)
    if available_block is None:
        blocked = _block_properties(horizontal)
        declarations = [item for item in declarations if not (item[0] in blocked and _needs_basis(item[1]))]
    solved = resolve_logical_box(
        declarations,
        writing_mode=box.writing_mode,
        direction=box.direction,
        text_orientation=box.text_orientation,
        containing_inline=available_inline,
        percentage_basis=parent_width,
        containing_block=available_block,
    )
    if solved.get("outcome") != "resolved":
        raise _Invalid(str(solved.get("reason") or "box is invalid"))
    content_width = solved.get("content_width")
    if content_width == "auto":
        raise _Invalid("content width is indefinite")
    box.solved = solved
    box.content_width = _px(content_width, "content width")
    content_height = solved.get("content_height")
    box.definite_height = None if content_height == "auto" else _px(content_height, "content height")
    box.margin_left = _px(solved.get("margin_left"), "margin-left")
    box.margin_right = _px(solved.get("margin_right"), "margin-right")
    box.x = parent_content_x + box.margin_left
    content_x = box.x + _px(solved.get("border_left"), "border-left") + _px(solved.get("padding_left"), "padding-left")
    for child in box.children:
        _solve(child, box.content_width, box.definite_height, horizontal, content_x)


def _available(
    parent_horizontal: bool,
    parent_width: int,
    parent_height: int | None,
    child_horizontal: bool,
) -> tuple[int | None, int | None]:
    if parent_horizontal == child_horizontal:
        if child_horizontal:
            return parent_width, parent_height
        return parent_height, parent_width
    if parent_horizontal:
        return parent_height, parent_width
    return parent_width, parent_height


def _block_properties(horizontal: bool) -> set[str]:
    logical = {"block-size", "min-block-size", "max-block-size"}
    if horizontal:
        return logical | {"height", "min-height", "max-height"}
    return logical | {"width", "min-width", "max-width"}


def _needs_basis(value: str) -> bool:
    text = " ".join(value.lower().split())
    return "%" in text or is_length_math(text)


def _collapse_spec(box: _Box) -> dict[str, object]:
    solved = box.solved
    return {
        "id": box.id,
        "margin_top": _px(solved.get("margin_top"), "margin-top"),
        "margin_bottom": _px(solved.get("margin_bottom"), "margin-bottom"),
        "padding_top": _px(solved.get("padding_top"), "padding-top"),
        "padding_bottom": _px(solved.get("padding_bottom"), "padding-bottom"),
        "border_top": _px(solved.get("border_top"), "border-top"),
        "border_bottom": _px(solved.get("border_bottom"), "border-bottom"),
        "height": "auto" if box.definite_height is None else box.definite_height,
        "min_height": 0,
        "overflow": "hidden" if box.root else box.overflow,
        "float": "none",
        "position": "relative" if box.position == "relative" else "static",
        "display": "inline-block" if box.display == "inline-block" else "block",
        "clearance": False,
        "children": [_collapse_spec(child) for child in box.children],
    }


def _assign_y(box: _Box, by_id: dict[str, dict[str, object]], origin: int) -> None:
    placed = by_id.get(box.id)
    if placed is None:
        raise _Invalid("placed box is missing")
    box.y = origin + _px(placed.get("y"), "y")
    box.border_height = _px(placed.get("border_height"), "border height")
    chrome = (
        _px(box.solved.get("padding_top"), "padding-top")
        + _px(box.solved.get("padding_bottom"), "padding-bottom")
        + _px(box.solved.get("border_top"), "border-top")
        + _px(box.solved.get("border_bottom"), "border-bottom")
    )
    if box.definite_height is None:
        box.content_height = box.border_height - chrome
    else:
        box.content_height = box.definite_height
    horizontal = (
        _px(box.solved.get("padding_left"), "padding-left")
        + _px(box.solved.get("padding_right"), "padding-right")
        + _px(box.solved.get("border_left"), "border-left")
        + _px(box.solved.get("border_right"), "border-right")
    )
    box.border_width = box.content_width + horizontal
    if box.content_height < 0:
        raise _Invalid("content height is invalid")
    for child in box.children:
        _assign_y(child, by_id, origin)


def _each(box: _Box):
    yield box
    for child in box.children:
        yield from _each(child)


def _record(box: _Box) -> dict[str, object]:
    return {
        "id": box.id,
        "x": box.x,
        "y": box.y,
        "content_width": box.content_width,
        "content_height": box.content_height,
        "border_width": box.border_width,
        "border_height": box.border_height,
        "margin_left": box.margin_left,
        "margin_right": box.margin_right,
    }


def _px(value: object, name: str) -> int:
    if type(value) is bool or not isinstance(value, (int, float)):
        raise _Invalid(f"{name} is invalid")
    number = float(value)
    if number != number or number in {float("inf"), float("-inf")}:
        raise _Invalid(f"{name} is invalid")
    nearest = round(number)
    if abs(number - nearest) > 1e-6:
        raise _Invalid(f"{name} is not integral")
    return int(nearest)
