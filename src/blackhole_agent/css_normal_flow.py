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
through to the viewport. ``display: none`` leaves the flow. A relative
box keeps the space it occupied, then its border box and in-flow descendants
move by the used left and top; later siblings stay where the static layout
put them. An absolute box is placed on the padding edge of the nearest
positioned ancestor, or on the viewport when no ancestor is positioned. A
fixed box is placed on the viewport. Neither changes the height of the flow.
An absolute or fixed box that needs the static position, shrink-to-fit, or an
indefinite height is rejected, and so is any content inside it. A float inside
a block whose only in-flow content is text
is placed in that content box, and the line boxes beside its margin box
shrink. A float beside a following block sibling is placed in that same
content box: the sibling keeps its width, its line boxes shorten where the
float margin box overlaps them, and clear moves the sibling's border edge
down to those floats. That path keeps each vertical margin instead of
collapsing adjoining ones. An automatic height is the block children, or
the stacked line boxes when
that block's own in-flow content is text, and it also grows to the bottom
margin edge of a float that block itself placed. Each character, including
the space, advances by the font size. ``line-height: normal`` uses the font
size as the strut. ``text-align`` shifts each line inside its line box. A
block that also has block children keeps those children and does not build
line boxes. An inline child may not set its own font size, line height,
text alignment, or white space.
``writing-mode``, ``direction``, and ``text-orientation`` inherit. Other
wide keywords on box properties use the initial value.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from blackhole_agent.css_absolute import place_absolute
from blackhole_agent.css_float_placement import place_floats
from blackhole_agent.css_inline_line import layout_inline_line
from blackhole_agent.css_length_math import is_length_math
from blackhole_agent.css_line_break import _default_advance, wrap_lines
from blackhole_agent.css_relative import place_relative
from blackhole_agent.css_text_align import align_inline_line
from blackhole_agent.css_logical_box import (
    _LOGICAL,
    _LOGICAL_SHORTHAND,
    _PHYSICAL_SHORTHAND,
    _SIZES,
    _Invalid as _LogicalInvalid,
    _cascade,
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
_CLEARS = frozenset({"none", "left", "right", "both"})
_OVERFLOWS = frozenset({"visible", "hidden", "auto", "scroll", "clip"})
_INHERITED = {
    "writing-mode": "horizontal-tb",
    "direction": "ltr",
    "text-orientation": "mixed",
}
_FONT = {
    "font-size": "16px",
    "line-height": "normal",
    "text-align": "start",
    "white-space": "normal",
}
_ALIGNS = frozenset(
    {"start", "end", "left", "right", "center", "justify", "justify-all", "match-parent"}
)
_WHITES = frozenset({"normal", "nowrap", "pre", "pre-wrap", "break-spaces", "pre-line"})
_COLLAPSED_EMPTY = frozenset({"normal", "nowrap"})
_INLINE_TYPE = ("font-size", "line-height", "text-align", "white-space")


class _Invalid(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class _Edge:
    x: int
    y: int
    width: int
    height: int | None


@dataclass
class _Line:
    text: str
    x: int
    y: int
    height: int
    content_width: int


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
    clear: str = "none"
    children: list[_Box] = field(default_factory=list)
    floats: list[_Box] = field(default_factory=list)
    flow: list[_Box] = field(default_factory=list)
    positioned: list[_Box] = field(default_factory=list)
    anchor_y: int | None = None
    anchor_laid: bool = False
    float_placed: bool = False
    local_y: int = 0
    float_band: tuple[int, int, int, int, str] | None = None
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
    font_size: int = 16
    line_height: str = "normal"
    text_align: str = "start"
    white_space: str = "normal"
    parent_direction: str | None = None
    inline_text: str | None = None
    lines: list[_Line] = field(default_factory=list)


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
    from the stylesheet; a style attribute is not read. Relative offsets are
    applied after the static positions. Absolute and fixed boxes are included
    in the returned boxes.
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
        root = _make_box(
            tree,
            order[0],
            _INHERITED.copy(),
            _FONT.copy(),
            None,
            styles,
            declarations,
            ids,
            counter,
            root=True,
        )
        if root.display == "none":
            raise _Invalid("root is not displayed")
        if root.position in {"absolute", "fixed"} or root.float_side != "none":
            raise _Invalid("root is outside normal flow")
        root.children, root.floats, root.flow, root.positioned = _walk(
            tree,
            order[0],
            _modes(root),
            _fonts(root),
            root.direction,
            styles,
            declarations,
            ids,
            counter,
        )
        root.inline_text = None if root.children else _inline_text(tree, order[0], styles, declarations)
        _solve(root, viewport_width, viewport_height, True, 0)
        placed = place_collapsed_margins(_collapse_spec(root))
        if placed.get("outcome") != "placed" or not isinstance(placed.get("boxes"), list):
            raise _Invalid(str(placed.get("reason") or "margin collapse failed"))
        by_id = {str(item["id"]): item for item in placed["boxes"] if isinstance(item, dict)}
        margin_top = _px(root.solved.get("margin_top"), "margin-top")
        _assign_y(root, by_id, margin_top)
        _shift_relatives(root, viewport_width, viewport_height)
        _place_positioned(root, _Edge(0, 0, viewport_width, viewport_height), [])
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


def _walk(
    tree,
    element,
    inherited: dict[str, str],
    fonts: dict[str, str],
    parent_direction: str | None,
    styles,
    declarations,
    ids: set[str],
    counter: list[int],
) -> tuple[list[_Box], list[_Box], list[_Box], list[_Box]]:
    found: list[_Box] = []
    floats: list[_Box] = []
    flow: list[_Box] = []
    positioned: list[_Box] = []
    for child in tree.children.get(element, []):
        if _local_name(child) in _SKIP_TAGS:
            continue
        box = _make_box(
            tree,
            child,
            inherited,
            fonts,
            parent_direction,
            styles,
            declarations,
            ids,
            counter,
            root=False,
        )
        if box.display == "none":
            continue
        if box.position in {"absolute", "fixed"}:
            _reject_positioned_content(tree, child)
            positioned.append(box)
            continue
        if box.float_side != "none":
            _reject_float_content(tree, child)
            floats.append(box)
            flow.append(box)
            continue
        if box.display == "inline":
            if box.position == "relative":
                raise _Invalid("relative inline is unsupported")
            nested, nested_floats, nested_flow, nested_positioned = _walk(
                tree,
                child,
                _modes(box),
                _fonts(box),
                box.direction,
                styles,
                declarations,
                ids,
                counter,
            )
            found.extend(nested)
            floats.extend(nested_floats)
            flow.extend(nested_flow)
            positioned.extend(nested_positioned)
            continue
        box.children, box.floats, box.flow, box.positioned = _walk(
            tree,
            child,
            _modes(box),
            _fonts(box),
            box.direction,
            styles,
            declarations,
            ids,
            counter,
        )
        box.inline_text = None if box.children else _inline_text(tree, child, styles, declarations)
        found.append(box)
        flow.append(box)
    return found, floats, flow, positioned


def _make_box(
    tree,
    element,
    inherited,
    fonts,
    parent_direction,
    styles,
    declarations,
    ids: set[str],
    counter: list[int],
    *,
    root: bool,
) -> _Box:
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
    clear = _keyword(_declared(winners, "clear", custom), _CLEARS, "none", "clear")
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
    font_size = _font_size(_declared(winners, "font-size", custom), fonts["font-size"])
    return _Box(
        id=box_id,
        writing_mode=mode,
        direction=direction,
        text_orientation=orientation,
        display=display,
        position=position,
        float_side=float_side,
        clear=clear,
        overflow=overflow,
        declarations=box_declarations,
        root=root,
        font_size=font_size,
        line_height=_line_height(_declared(winners, "line-height", custom), fonts["line-height"]),
        text_align=_inherited_keyword(
            _declared(winners, "text-align", custom),
            _ALIGNS,
            fonts["text-align"],
            _FONT["text-align"],
            "text-align",
        ),
        white_space=_inherited_keyword(
            _declared(winners, "white-space", custom),
            _WHITES,
            fonts["white-space"],
            _FONT["white-space"],
            "white-space",
        ),
        parent_direction=parent_direction,
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
    if box.floats and not box.children:
        _place_floats(box, content_x)
    if not box.children and (box.inline_text or box.floats):
        _fill_lines(box)
    elif box.floats:
        for child in box.children:
            _solve(child, box.content_width, box.definite_height, horizontal, content_x)
        _lay_sibling_floats(box, content_x)
    else:
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
        "children": [] if box.anchor_laid else [_collapse_spec(child) for child in box.children],
    }


def _assign_y(
    box: _Box,
    by_id: dict[str, dict[str, object]],
    origin: int,
    border_at: int | None = None,
) -> None:
    if box.anchor_y is None:
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
    else:
        if border_at is None:
            raise _Invalid("placed box is missing")
        box.y = border_at + box.anchor_y
    horizontal = (
        _px(box.solved.get("padding_left"), "padding-left")
        + _px(box.solved.get("padding_right"), "padding-right")
        + _px(box.solved.get("border_left"), "border-left")
        + _px(box.solved.get("border_right"), "border-right")
    )
    box.border_width = box.content_width + horizontal
    if box.content_height < 0:
        raise _Invalid("content height is invalid")
    content_y = box.y + _px(box.solved.get("border_top"), "border-top") + _px(box.solved.get("padding_top"), "padding-top")
    origin_x = box.x + _px(box.solved.get("border_left"), "border-left") + _px(box.solved.get("padding_left"), "padding-left")
    for line in box.lines:
        line.x += origin_x
        line.y += content_y
    for fl in box.floats:
        if not fl.float_placed:
            continue
        fl.y = content_y + fl.local_y
    for child in box.children:
        _assign_y(child, by_id, origin, box.y)


def _each(box: _Box):
    yield box
    for fl in box.floats:
        if fl.float_placed:
            yield fl
    for child in box.children:
        yield from _each(child)
    for abs_box in box.positioned:
        yield from _each(abs_box)


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
        "lines": [
            {
                "text": line.text,
                "x": line.x,
                "y": line.y,
                "height": line.height,
                "content_width": line.content_width,
            }
            for line in box.lines
        ],
    }


def _fonts(box: _Box) -> dict[str, str]:
    return {
        "font-size": f"{box.font_size}px",
        "line-height": box.line_height,
        "text-align": box.text_align,
        "white-space": box.white_space,
    }


def _inline_text(tree, element, styles, declarations) -> str | None:
    parts = [element.text or ""]
    for child in list(element):
        if not _local_name(child):
            continue
        kind = _flow_kind(tree, child, styles, declarations)
        if kind in {"skip", "out"}:
            parts.append(child.tail or "")
            continue
        if kind == "block":
            return None
        _reject_inline_type(tree, child, styles, declarations)
        inner = _inline_text(tree, child, styles, declarations)
        if inner is None:
            return None
        parts.append(inner)
        parts.append(child.tail or "")
    return "".join(parts)


def _flow_kind(tree, element, styles, declarations) -> str:
    if _local_name(element) in _SKIP_TAGS:
        return "skip"
    custom = styles.get(element, ({}, ""))[0]
    winners = _winners(tree, element, declarations)
    display = _keyword(
        _declared(winners, "display", custom),
        _DISPLAYS,
        "block" if _local_name(element) in _BLOCK_TAGS else "inline",
        "display",
    )
    position = _keyword(_declared(winners, "position", custom), _POSITIONS, "static", "position")
    float_side = _keyword(_declared(winners, "float", custom), _FLOATS, "none", "float")
    if display == "none" or position in {"absolute", "fixed"} or float_side != "none":
        return "out"
    if display == "inline":
        return "inline"
    return "block"


def _reject_inline_type(tree, element, styles, declarations) -> None:
    custom = styles.get(element, ({}, ""))[0]
    winners = _winners(tree, element, declarations)
    for name in _INLINE_TYPE:
        if _declared(winners, name, custom) is not None:
            raise _Invalid(f"inline {name} is unsupported")


def _font_size(value: str | None, parent: str) -> int:
    if value is None or value in {"inherit", "unset", "revert"}:
        return _positive_px(parent, "font-size")
    if value == "initial":
        return _positive_px(_FONT["font-size"], "font-size")
    return _positive_px(value, "font-size")


def _line_height(value: str | None, parent: str) -> str:
    if value is None or value in {"inherit", "unset", "revert"}:
        return parent
    if value in {"initial", "normal"}:
        return "normal"
    text = value.strip().lower()
    if text.endswith("px"):
        number = _px(float(text[:-2]), "line-height")
        if number < 0:
            raise _Invalid("line-height is invalid")
        return f"{number}px"
    try:
        number = float(text)
    except ValueError as exc:
        raise _Invalid("line-height is invalid") from exc
    if number < 0 or number != number or number in {float("inf"), float("-inf")}:
        raise _Invalid("line-height is invalid")
    return _unitless(number)


def _unitless(number: float) -> str:
    nearest = round(number)
    if abs(number - nearest) <= 1e-9:
        return str(int(nearest))
    return format(number, "g")


def _inherited_keyword(
    value: str | None,
    allowed: frozenset[str],
    parent: str,
    initial: str,
    name: str,
) -> str:
    if value is None or value in {"inherit", "unset", "revert"}:
        return parent
    if value == "initial":
        return initial
    token = value.strip().lower()
    if token not in allowed:
        raise _Invalid(f"{name} is invalid")
    return token


def _positive_px(value: str, name: str) -> int:
    text = value.strip().lower()
    if not text.endswith("px"):
        raise _Invalid(f"{name} is invalid")
    try:
        number = _px(float(text[:-2]), name)
    except (TypeError, ValueError) as exc:
        raise _Invalid(f"{name} is invalid") from exc
    if number <= 0:
        raise _Invalid(f"{name} is invalid")
    return number


def _float_margin(box: _Box, name: str, containing: int) -> int:
    """Use the declared margin. A float does not absorb leftover inline space."""

    declared = {prop: value for prop, value in box.declarations}
    raw = declared.get(name)
    if raw is None:
        return 0
    text = raw.strip().lower()
    if text in {"auto", "initial", "unset", "revert"}:
        return 0
    try:
        if text.endswith("px"):
            return _px(float(text[:-2]), name)
        if text.endswith("%"):
            return _px(containing * float(text[:-1]) / 100, name)
    except ValueError as exc:
        raise _Invalid(f"{name} is invalid") from exc
    raise _Invalid(f"{name} is invalid")


def _reject_float_content(tree, element) -> None:
    if (element.text or "").strip() or tree.children.get(element):
        raise _Invalid("float content is unsupported")


def _reject_positioned_content(tree, element) -> None:
    if (element.text or "").strip() or tree.children.get(element):
        raise _Invalid("positioned content is unsupported")


_AUTO_WORDS = frozenset({"auto", "initial", "unset", "revert"})


def _is_auto(value: str | None) -> bool:
    if value is None:
        return True
    return value.strip().lower() in _AUTO_WORDS


def _physical_slots(box: _Box) -> dict[str, str]:
    flow = resolve_writing_mode(box.writing_mode, box.direction, text_orientation=box.text_orientation)
    if flow.get("outcome") != "resolved":
        raise _Invalid(str(flow.get("reason") or "writing-mode is invalid"))
    try:
        return _cascade(box.declarations, flow)
    except _LogicalInvalid as exc:
        raise _Invalid(str(exc)) from exc


def _inset(slots: dict[str, str], side: str) -> str:
    return slots.get(f"inset-{side}", "auto")


def _border_arg(slots: dict[str, str], side: str) -> object:
    style = slots.get(f"border-{side}-style", "none").strip().lower()
    if style in {"none", "hidden"}:
        return 0
    width = slots.get(f"border-{side}-width")
    if width is None:
        return 3
    token = width.strip().lower()
    if token == "thin":
        return 1
    if token == "medium":
        return 3
    if token == "thick":
        return 5
    return width


def _shift_relatives(box: _Box, cb_width: int, cb_height: int | None) -> None:
    if box.position == "relative":
        dx, dy = _relative_delta(box, cb_width, cb_height)
        _translate(box, dx, dy)
    for child in box.children:
        _shift_relatives(child, box.content_width, box.definite_height)
    for fl in box.floats:
        if fl.position == "relative" and fl.float_placed:
            dx, dy = _relative_delta(fl, box.content_width, box.definite_height)
            _translate(fl, dx, dy)


def _relative_delta(box: _Box, cb_width: int, cb_height: int | None) -> tuple[int, int]:
    slots = _physical_slots(box)
    direction = box.direction if box.direction in {"ltr", "rtl"} else "ltr"
    placed = place_relative(
        [
            {
                "id": box.id,
                "position": "relative",
                "direction": direction,
                "x": box.x,
                "y": box.y,
                "width": box.border_width,
                "height": box.border_height,
                "left": _inset(slots, "left"),
                "right": _inset(slots, "right"),
                "top": _inset(slots, "top"),
                "bottom": _inset(slots, "bottom"),
            }
        ],
        containing_width=cb_width,
        containing_height="auto" if cb_height is None else cb_height,
    )
    rows = placed.get("boxes")
    if placed.get("outcome") != "placed" or not isinstance(rows, list) or not rows:
        raise _Invalid(str(placed.get("reason") or "relative position failed"))
    row = rows[0]
    if not isinstance(row, dict):
        raise _Invalid("relative position failed")
    return _px(row.get("x"), "x") - box.x, _px(row.get("y"), "y") - box.y


def _translate(box: _Box, dx: int, dy: int) -> None:
    if dx == 0 and dy == 0:
        return
    box.x += dx
    box.y += dy
    for line in box.lines:
        line.x += dx
        line.y += dy
    for fl in box.floats:
        if fl.float_placed:
            _translate(fl, dx, dy)
    for child in box.children:
        _translate(child, dx, dy)


def _padding_edge(box: _Box) -> _Edge:
    border_left = _px(box.solved.get("border_left"), "border-left")
    border_top = _px(box.solved.get("border_top"), "border-top")
    pad_left = _px(box.solved.get("padding_left"), "padding-left")
    pad_right = _px(box.solved.get("padding_right"), "padding-right")
    pad_top = _px(box.solved.get("padding_top"), "padding-top")
    pad_bottom = _px(box.solved.get("padding_bottom"), "padding-bottom")
    height = None if box.definite_height is None else box.definite_height + pad_top + pad_bottom
    return _Edge(box.x + border_left, box.y + border_top, pad_left + box.content_width + pad_right, height)


def _place_positioned(box: _Box, viewport: _Edge, stack: list[_Edge]) -> None:
    frame = stack
    if box.position in {"relative", "absolute", "fixed"}:
        frame = [*stack, _padding_edge(box)]
    for abs_box in box.positioned:
        cb = viewport if abs_box.position == "fixed" or not frame else frame[-1]
        _place_one_absolute(abs_box, cb)
    for child in box.children:
        _place_positioned(child, viewport, frame)


def _place_one_absolute(box: _Box, cb: _Edge) -> None:
    slots = _physical_slots(box)
    left, right = _inset(slots, "left"), _inset(slots, "right")
    top, bottom = _inset(slots, "top"), _inset(slots, "bottom")
    if _is_auto(left) and _is_auto(right):
        raise _Invalid("static position is unsupported")
    if _is_auto(top) and _is_auto(bottom):
        raise _Invalid("static position is unsupported")
    if _is_auto(slots.get("width")) and (_is_auto(left) or _is_auto(right)):
        raise _Invalid("absolute shrink-to-fit is unsupported")
    if _is_auto(slots.get("height")) and (_is_auto(top) or _is_auto(bottom) or cb.height is None):
        raise _Invalid("absolute height is indefinite")
    direction = box.direction if box.direction in {"ltr", "rtl"} else "ltr"
    placed = place_absolute(
        cb.width,
        containing_height="auto" if cb.height is None else cb.height,
        left=left,
        right=right,
        width=slots.get("width", "auto"),
        top=top,
        bottom=bottom,
        height=slots.get("height", "auto"),
        margin_left=slots.get("margin-left", 0),
        margin_right=slots.get("margin-right", 0),
        margin_top=slots.get("margin-top", 0),
        margin_bottom=slots.get("margin-bottom", 0),
        padding_left=slots.get("padding-left", 0),
        padding_right=slots.get("padding-right", 0),
        padding_top=slots.get("padding-top", 0),
        padding_bottom=slots.get("padding-bottom", 0),
        border_left=_border_arg(slots, "left"),
        border_right=_border_arg(slots, "right"),
        border_top=_border_arg(slots, "top"),
        border_bottom=_border_arg(slots, "bottom"),
        min_width=slots.get("min-width", "auto"),
        max_width=slots.get("max-width", "none"),
        min_height=slots.get("min-height", "auto"),
        max_height=slots.get("max-height", "none"),
        box_sizing=slots.get("box-sizing", "content-box"),
        direction=direction,
        static_left=0,
        static_right=0,
        static_top=0,
        min_content=0,
        max_content=0,
        content_height=0,
    )
    if placed.get("outcome") != "placed":
        raise _Invalid(str(placed.get("reason") or "absolute position failed"))
    box.x = cb.x + _px(placed.get("x"), "x")
    box.y = cb.y + _px(placed.get("y"), "y")
    box.content_width = _px(placed.get("width"), "content width")
    box.content_height = _px(placed.get("height"), "content height")
    box.border_width = _px(placed.get("border_box_width"), "border width")
    box.border_height = _px(placed.get("border_box_height"), "border height")
    box.margin_left = _px(placed.get("margin_left"), "margin-left")
    box.margin_right = _px(placed.get("margin_right"), "margin-right")
    box.solved = placed


def _measure_float(box: _Box, fl: _Box) -> dict[str, int]:
    solved = resolve_logical_box(
        fl.declarations,
        writing_mode=fl.writing_mode,
        direction=fl.direction,
        text_orientation=fl.text_orientation,
        containing_inline=box.content_width,
        percentage_basis=box.content_width,
        containing_block=box.definite_height,
    )
    if solved.get("outcome") != "resolved":
        raise _Invalid(str(solved.get("reason") or "float is invalid"))
    if solved.get("specified_width") in {None, "auto"} or solved.get("content_width") in {None, "auto"}:
        raise _Invalid("float width is indefinite")
    if solved.get("specified_height") in {None, "auto"} or solved.get("content_height") in {None, "auto"}:
        raise _Invalid("float height is indefinite")
    content_width = _px(solved.get("content_width"), "float width")
    content_height = _px(solved.get("content_height"), "float height")
    margin_left = _float_margin(fl, "margin-left", box.content_width)
    margin_right = _float_margin(fl, "margin-right", box.content_width)
    margin_top = _float_margin(fl, "margin-top", box.content_width)
    margin_bottom = _float_margin(fl, "margin-bottom", box.content_width)
    border_left = _px(solved.get("border_left"), "border-left")
    border_right = _px(solved.get("border_right"), "border-right")
    border_top = _px(solved.get("border_top"), "border-top")
    border_bottom = _px(solved.get("border_bottom"), "border-bottom")
    padding_left = _px(solved.get("padding_left"), "padding-left")
    padding_right = _px(solved.get("padding_right"), "padding-right")
    padding_top = _px(solved.get("padding_top"), "padding-top")
    padding_bottom = _px(solved.get("padding_bottom"), "padding-bottom")
    fl.solved = solved
    fl.content_width = content_width
    fl.content_height = content_height
    fl.margin_left = margin_left
    fl.margin_right = margin_right
    fl.border_width = content_width + padding_left + padding_right + border_left + border_right
    fl.border_height = content_height + padding_top + padding_bottom + border_top + border_bottom
    fl.local_y = margin_top
    return {
        "outer_width": margin_left + border_left + padding_left + content_width + padding_right + border_right + margin_right,
        "outer_height": margin_top + border_top + padding_top + content_height + padding_bottom + border_bottom + margin_bottom,
        "margin_left": margin_left,
        "margin_top": margin_top,
    }


def _place_floats(box: _Box, content_x: int) -> None:
    if box.writing_mode != "horizontal-tb" or box.direction != "ltr":
        raise _Invalid("float writing mode is unsupported")
    items: list[dict[str, object]] = []
    solved_rows: list[tuple[_Box, dict[str, int]]] = []
    for fl in box.floats:
        measured = _measure_float(box, fl)
        items.append(
            {
                "id": fl.id,
                "float": fl.float_side,
                "width": measured["outer_width"],
                "height": measured["outer_height"],
                "clear": fl.clear,
            }
        )
        solved_rows.append((fl, measured))
    placed = place_floats(box.content_width, items)
    if placed.get("outcome") != "placed" or not isinstance(placed.get("boxes"), list):
        raise _Invalid(str(placed.get("reason") or "float placement failed"))
    by_id = {str(item.get("id")): item for item in placed["boxes"] if isinstance(item, dict)}
    for fl, edges in solved_rows:
        row = by_id.get(fl.id)
        if row is None:
            raise _Invalid("float placement failed")
        _commit_float(fl, content_x, row, edges)


def _commit_float(fl: _Box, content_x: int, row: dict[str, object], edges: dict[str, int]) -> None:
    margin_x = _px(row.get("x"), "float x")
    margin_y = _px(row.get("y"), "float y")
    margin_width = _px(row.get("width"), "float width")
    margin_height = _px(row.get("height"), "float height")
    fl.x = content_x + margin_x + edges["margin_left"]
    fl.local_y = margin_y + edges["margin_top"]
    fl.float_band = (margin_x, margin_y, margin_width, margin_height, fl.float_side)
    fl.float_placed = True


def _lay_sibling_floats(box: _Box, content_x: int) -> None:
    """Place floats in source order and shorten each following block's lines."""

    if box.writing_mode != "horizontal-tb" or box.direction != "ltr":
        raise _Invalid("float writing mode is unsupported")
    measured = {fl.id: _measure_float(box, fl) for fl in box.floats}
    for child in box.children:
        if child.display != "block" or child.children or child.floats:
            raise _Invalid("float beside nested blocks is unsupported")
        if child.writing_mode != "horizontal-tb" or child.direction != "ltr":
            raise _Invalid("float writing mode is unsupported")
    bands: list[tuple[int, int, int, int, str]] = []
    cursor = 0
    origin = _px(box.solved.get("border_top"), "border-top") + _px(box.solved.get("padding_top"), "padding-top")
    for item in box.flow:
        if item.float_side != "none":
            spec = measured[item.id]
            floor = max(cursor, _clear_floor(item.clear, bands))
            x, y = _fit_float(item.float_side, spec["outer_width"], spec["outer_height"], floor, bands, box.content_width)
            _commit_float(
                item,
                content_x,
                {"x": x, "y": y, "width": spec["outer_width"], "height": spec["outer_height"]},
                spec,
            )
            if item.float_band is not None:
                bands.append(item.float_band)
            continue
        margin_top = _px(item.solved.get("margin_top"), "margin-top")
        margin_bottom = _px(item.solved.get("margin_bottom"), "margin-bottom")
        border_y = max(cursor + margin_top, _clear_floor(item.clear, bands))
        inset_x = (
            _px(item.solved.get("margin_left"), "margin-left")
            + _px(item.solved.get("border_left"), "border-left")
            + _px(item.solved.get("padding_left"), "padding-left")
        )
        content_top = border_y + _px(item.solved.get("border_top"), "border-top") + _px(item.solved.get("padding_top"), "padding-top")
        local = [(bx - inset_x, by - content_top, bw, bh, side) for bx, by, bw, bh, side in bands]
        _reflow_beside(item, local)
        item.anchor_y = origin + border_y
        cursor = border_y + item.border_height + margin_bottom
    box.anchor_laid = True
    if box.definite_height is None:
        box.definite_height = max([cursor, *(band[1] + band[3] for band in bands)], default=0)


def _reflow_beside(box: _Box, bands: list[tuple[int, int, int, int, str]]) -> None:
    auto = box.solved.get("content_height") == "auto"
    saved = box.definite_height
    if auto:
        box.definite_height = None
    _fill_lines_beside_floats(box, bands, contain=False)
    if not auto:
        box.definite_height = saved
    if box.definite_height is None:
        box.definite_height = 0
    chrome = (
        _px(box.solved.get("padding_top"), "padding-top")
        + _px(box.solved.get("padding_bottom"), "padding-bottom")
        + _px(box.solved.get("border_top"), "border-top")
        + _px(box.solved.get("border_bottom"), "border-bottom")
    )
    box.content_height = box.definite_height
    box.border_height = box.definite_height + chrome


def _clear_floor(clear: str, bands: list[tuple[int, int, int, int, str]]) -> int:
    if clear == "none":
        return 0
    floor = 0
    for _x, y, _w, height, side in bands:
        if clear == "both" or clear == side:
            floor = max(floor, y + height)
    return floor


def _fit_float(
    side: str,
    width: int,
    height: int,
    floor: int,
    bands: list[tuple[int, int, int, int, str]],
    containing: int,
) -> tuple[int, int]:
    events = {floor}
    for _x, y, _w, band_height, _side in bands:
        bottom = y + band_height
        if bottom > floor:
            events.add(bottom)
    for y in sorted(events):
        left = 0
        right = containing
        for bx, by, bw, bh, band_side in bands:
            if y < by + bh and y + height > by:
                if band_side == "left":
                    left = max(left, bx + bw)
                elif bx < right:
                    right = bx
        if width > containing and left == 0 and right == containing:
            return (0, y) if side == "left" else (containing - width, y)
        if side == "left" and left + width <= right:
            return left, y
        if side == "right" and right - width >= left:
            return right - width, y
    raise _Invalid("float placement failed")


def _fill_lines_beside_floats(
    box: _Box,
    bands: list[tuple[int, int, int, int, str]] | None = None,
    *,
    contain: bool = True,
) -> None:
    text = box.inline_text or ""
    if bands is None:
        bands = [fl.float_band for fl in box.floats if fl.float_placed and fl.float_band is not None]
    used = _used_line_height(box.line_height, box.font_size)
    height = _strut_height(box.font_size, used)
    if not text or (box.white_space in _COLLAPSED_EMPTY and not text.strip()):
        if box.definite_height is None:
            box.definite_height = _band_bottom(bands) if contain else 0
        return
    advances = {ch: box.font_size * _default_advance(ch) for ch in set(text)}
    remaining = text
    records: list[_Line] = []
    cursor = 0
    for _ in range(10000):
        if not remaining or (box.white_space in _COLLAPSED_EMPTY and not remaining.strip()):
            break
        left, right, bottoms = _exclusion(cursor, height, bands, box.content_width)
        available = right - left
        wrapped = wrap_lines(remaining, max(available, 0), white_space=box.white_space, advances=advances)
        lines = wrapped.get("lines") if wrapped.get("outcome") == "wrapped" else None
        if not isinstance(lines, list) or not lines or not isinstance(lines[0], dict):
            raise _Invalid(str(wrapped.get("reason") or "line break failed"))
        content = _px(lines[0].get("content_width"), "line width")
        obstructed = not (left == 0 and right == box.content_width)
        if available <= 0 or (content > available and obstructed):
            if not bottoms:
                raise _Invalid("line break failed")
            nxt = min(bottoms)
            if nxt <= cursor:
                raise _Invalid("line break failed")
            cursor = _px(nxt, "float clearance")
            continue
        rendered = str(lines[0].get("text") or "")
        if not rendered and content == 0:
            raise _Invalid("line break failed")
        rest = _drop_prefix(remaining, rendered, box.white_space)
        aligned = align_inline_line(
            available,
            [{"id": "text", "width": content, "space_after": 0}],
            text_align=box.text_align,
            direction=box.direction,
            parent_direction=box.parent_direction,
            white_space=box.white_space,
            last_line=rest == "" or (box.white_space in _COLLAPSED_EMPTY and not rest.strip()),
        )
        items = aligned.get("items") if aligned.get("outcome") == "aligned" else None
        if not isinstance(items, list) or len(items) != 1 or not isinstance(items[0], dict):
            raise _Invalid(str(aligned.get("reason") or "text alignment failed"))
        records.append(
            _Line(
                text=rendered,
                x=_px(left, "line x") + _px(items[0].get("x"), "line x"),
                y=cursor,
                height=height,
                content_width=content,
            )
        )
        remaining = rest
        cursor += height
    else:
        raise _Invalid("line break failed")
    box.lines = records
    if box.definite_height is None:
        box.definite_height = max(cursor, _band_bottom(bands)) if contain else cursor


def _exclusion(
    y: int,
    line_height: int,
    bands: list[tuple[int, int, int, int, str] | None],
    containing: int,
) -> tuple[int, int, list[int]]:
    left = 0
    right = containing
    bottoms: list[int] = []
    for band in bands:
        if band is None:
            continue
        edge_x, edge_y, width, band_height, side = band
        bottom = edge_y + band_height
        if band_height <= 0 or not (y < bottom and y + line_height > edge_y):
            continue
        bottoms.append(bottom)
        if side == "left":
            edge = edge_x + width
            if edge > left:
                left = edge
        elif edge_x < right:
            right = edge_x
    return left, right, bottoms


def _band_bottom(bands: list[tuple[int, int, int, int, str] | None]) -> int:
    bottoms = [band[1] + band[3] for band in bands if band is not None]
    return max(bottoms) if bottoms else 0


def _drop_prefix(source: str, rendered: str, white_space: str) -> str:
    if white_space in {"pre", "pre-wrap", "break-spaces"}:
        if rendered and not source.startswith(rendered):
            raise _Invalid("line break failed")
        return source[len(rendered) :]
    collapsed = " ".join(source.split())
    if rendered:
        if not collapsed.startswith(rendered):
            raise _Invalid("line break failed")
        collapsed = collapsed[len(rendered) :]
        if collapsed.startswith(" "):
            collapsed = collapsed[1:]
    elif source.strip():
        raise _Invalid("line break failed")
    return collapsed


def _fill_lines(box: _Box) -> None:
    if box.floats and not box.children:
        _fill_lines_beside_floats(box)
        return
    text = box.inline_text or ""
    if not text:
        return
    used = _used_line_height(box.line_height, box.font_size)
    height = _strut_height(box.font_size, used)
    advances = {ch: box.font_size * _default_advance(ch) for ch in set(text)}
    wrapped = wrap_lines(text, box.content_width, white_space=box.white_space, advances=advances)
    lines = wrapped.get("lines") if wrapped.get("outcome") == "wrapped" else None
    if not isinstance(lines, list):
        raise _Invalid(str(wrapped.get("reason") or "line break failed"))
    if box.white_space in _COLLAPSED_EMPTY:
        lines = [line for line in lines if isinstance(line, dict) and (line.get("text") or line.get("content_width"))]
    if not lines:
        return
    records: list[_Line] = []
    cursor = 0
    last = len(lines) - 1
    for index, line in enumerate(lines):
        if not isinstance(line, dict):
            raise _Invalid("line is invalid")
        content = _px(line.get("content_width"), "line width")
        aligned = align_inline_line(
            box.content_width,
            [{"id": "text", "width": content, "space_after": 0}],
            text_align=box.text_align,
            direction=box.direction,
            parent_direction=box.parent_direction,
            white_space=box.white_space,
            last_line=index == last,
        )
        items = aligned.get("items") if aligned.get("outcome") == "aligned" else None
        if not isinstance(items, list) or len(items) != 1 or not isinstance(items[0], dict):
            raise _Invalid(str(aligned.get("reason") or "text alignment failed"))
        records.append(
            _Line(
                text=str(line.get("text") or ""),
                x=_px(items[0].get("x"), "line x"),
                y=cursor,
                height=height,
                content_width=content,
            )
        )
        cursor += height
    box.lines = records
    if box.definite_height is None:
        box.definite_height = cursor


def _used_line_height(computed: str, font_size: int) -> int:
    if computed == "normal":
        return font_size
    if computed.endswith("px"):
        return _px(float(computed[:-2]), "line-height")
    return _px(float(computed) * font_size, "line-height")


def _strut_height(font_size: int, line_height: int) -> int:
    laid = layout_inline_line(
        {"ascent": font_size, "descent": 0, "line_height": line_height, "x_height": 0},
        [
            {
                "id": "text",
                "kind": "text",
                "vertical_align": "baseline",
                "ascent": font_size,
                "descent": 0,
                "line_height": line_height,
            }
        ],
    )
    if laid.get("outcome") != "resolved":
        raise _Invalid(str(laid.get("reason") or "line box failed"))
    return _px(laid.get("line_height"), "line height")


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
