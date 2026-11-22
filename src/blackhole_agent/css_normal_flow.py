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
Horizontal text inside that box supplies shrink-to-fit width and the stacked
line-box height. Automatic insets on an axis use the static position between
block siblings. Element children are rejected, a static position inside a
line is rejected, and a vertical writing mode still rejects those automatic
sizes. A float inside
a block whose only in-flow content is text
is placed in that content box, and the line boxes beside its margin box
shrink. A float beside a following block sibling is placed in that same
content box: the sibling keeps its width, its line boxes shorten where the
float margin box overlaps them, and clear moves the sibling's border edge
down to those floats. Text in the float is wrapped in its content box.
Automatic width is the shrink-to-fit size, and automatic height is the
stacked line boxes; a specified size stays specified. Element children
inside a float are rejected. That sibling path keeps each vertical margin
instead of collapsing adjoining ones. An automatic height is the block children, or
the stacked line boxes when
that block's own in-flow content is text, and it also grows to the bottom
margin edge of a float that block itself placed. Each character, including
the space, advances by the font size. When that whole paragraph fits on one
horizontal plain line and its Unicode bidi visual order differs from the
source, each character is also a glyph from the line's left edge. A wrapped
fragment and a line that is already visual omit glyphs. ``line-height: normal`` uses the font
size as the strut. ``text-align`` shifts each line inside its line box. A
block that also has block children keeps those children and does not build
line boxes. An inline child may set font-size and line-height. Each run advances
by its own font size, and the line grows to the tallest run without
shrinking the parent's strut. text-align and white-space on an inline
stay rejected. A float beside those mixed runs is rejected too. An
inline-block is an atomic inline: automatic width is the shrink-to-fit of
its text, the words before and after stay on the line, and the atomic box
moves intact to the next line when it does not fit. Its bottom margin edge
rests on the parent baseline when overflow is not visible or it has no line
box; otherwise the baseline is its last line. A block sibling, a float, a
nested inline-block, and positioned content inside it are rejected.
A ``display: flex`` row lays its element children out on one nowrap line.
``flex`` and the flex longhands set each item's used content width from the
row's content box; an automatic row height is the tallest item, and a
following block starts under that border box. ``flex-wrap: wrap`` breaks
before free space is distributed, using each item's hypothetical main size:
an item that does not fit starts the next line, and that line flexes alone.
Automatic height is the sum of the line cross sizes, so the following block
starts under the last line. ``wrap-reverse`` mirrors those lines from the
cross end. ``flex-direction: column`` uses the block size as the main size.
A definite height is shared by the flex factors, and an automatic height is
the sum of the hypothetical main sizes, so inline free space does not grow
the items. ``column-reverse`` packs that line from the bottom edge.
``flex-wrap`` on a column breaks before that free space is distributed:
an item whose hypothetical block size does not fit starts the next column,
and ``wrap-reverse`` places the first column at the inline end.
``column-reverse`` still packs each of those columns from the bottom.
An automatic column height has no definite block size, so it stays one
column. A definite ``gap`` is removed from free space before items grow or
shrink, and the same gutter separates wrapped lines. An automatic cross size
includes those gutters, so the following block starts after the last gapped
line. ``justify-content`` then packs any main-axis leftover, on a row or a
column and on each wrapped line. ``align-items`` and ``align-self`` place a
shorter item inside that line. ``align-content`` packs wrapped lines inside
a definite cross size and does not move a single line. A definite main-axis
margin sits outside the flexible length. An auto main margin absorbs positive
free space before that packing. ``align-items: baseline`` lines the first
text baselines up, and an automatic row grows to that line. A column treats
baseline as ``flex-start``. ``flex-direction: row-reverse`` packs each line
from the inline end: the first item's margin box ends on the right content
edge, a definite margin-left stays on the left of that item, and
``justify-content: flex-end`` leaves the free space on the right. An auto
margin-right is the main-start margin and absorbs positive free space before
that packing. A wrapped row-reverse line uses the same end edge. ``order``
sorts items before that packing and before a wrap break; equal values keep
source order. Text in a
row item wraps at its hypothetical main size; an automatic cross size is
those line boxes, painted in the used content width. Loose container text
stays rejected.
A ``display: grid`` container places its element children on explicit column
tracks. Fixed ``px`` tracks keep that size, and ``fr`` tracks share the
content box after column gaps are removed. Auto-placement fills rows in
order, so a later item starts a new row when the columns are full even if
inline space remains. A ``span`` covers the tracks it crosses, including
the gutters between them. An automatic item stretches to that area; a
specified length stays at the track start. Implicit rows use a definite
``grid-auto-rows`` length, and explicit rows keep their size when empty.
Automatic height is those rows plus the row gaps, so a following block
starts under the last row. ``grid-auto-flow: column`` fills each column
before the next one, and ``dense`` puts a later item in a hole the sparse
cursor left behind. ``order`` sorts that automatic sequence first; equal
values keep source order. A text-only item contributes its min-content and
max-content to the columns, plus any definite horizontal margin, padding,
and used border.
``max-content`` keeps the unwrapped line, ``auto`` then absorbs leftover
space in a definite grid, and a fixed column keeps its length and wraps the
text inside the content box. Definite margins shrink a stretched automatic
size. An auto margin absorbs positive free space in the area and does not
grow the track. An automatic row grows to the line boxes plus definite
vertical margins, padding, and used border. A block child is placed in that content box: the item is
an independent formatting context, so the child's margin stays inside the
item and adjoining child margins collapse. The child's text contributes its
min-content and max-content, and a narrow column wraps those line boxes.
The row grows to that content, so the following block starts under it.
``grid-template-areas`` places an item on the rectangle of its name, even when
that rectangle is not the item's source position. A bracketed line name on
``grid-template-columns`` or ``grid-template-rows`` is selected by
``grid-column`` or ``grid-row``. A name that is not one rectangle is rejected.
Padding and a used border inset the content box. An absent or hidden border
style contributes nothing. A definite grid height is the used content height:
fixed rows keep their size, ``fr`` rows share the free space after row gaps,
and a following block starts at that border edge even when the tracks overflow
it. An ``fr`` row without a definite height stays rejected.
``minmax()`` clamps a track between a length floor and a length ceiling.
That ceiling is filled before a flexible sibling takes leftover space, and
a flexible ceiling keeps a floor that already exceeds its share. A ceiling
below its floor is ignored. A flexible row still needs a definite height.
A flexible floor is rejected.
``justify-items`` and ``align-items`` pack each item margin box inside its
area. ``normal`` and ``stretch`` fill an automatic size. ``start``,
``center``, and ``end`` keep a definite size, or the max-content size when
the size is automatic, and sit on that edge. ``justify-self`` and
``align-self`` override the container for one item; ``auto`` uses the
container keyword. ``left`` and ``right`` apply only on the inline axis.
A distribution keyword such as ``space-between`` stays invalid on an item
axis. ``justify-content`` still only decides whether content-sized columns
grow into leftover inline space.
A ``display: table`` sizes columns from the text inside its cells. An
automatic width replaces the stretched block size with the max-content of
that text, and never grows past the containing block. ``table-layout: fixed``
keeps a definite width, takes column widths from the first row, and wraps
each cell into that column. The row grows to the stacked line boxes.
``vertical-align: bottom`` sits a shorter cell's lines on the row's bottom
edge. Automatic height is those rows, so a following block starts under the
table. ``border-collapse: collapse`` on an automatic table shares each grid
line between the table, the rows, and the cells. A wider border wins before
style, ``hidden`` removes the line, and the extra pixel of an odd internal
line stays on its start side. Cell text starts after the half assigned to
that cell. The following block starts under the table border box. A fixed
table, a definite table width, captions, spans, border spacing, and element
children inside a cell stay rejected.
An ``inline-size`` or ``size`` container answers ``@container`` for descendants
after its content-box size is known. The container is not a candidate for its
own query. A named query selects the nearest ancestor with that name which can
answer the features, and a failed condition does not fall through to an outer
container. Matching declarations join the cascade at their source order, so a
later unconditional declaration of the same specificity still wins. A box
without ``container-type`` does not answer a size query.
Writing mode, direction and text orientation inherit. Other CSS-wide keywords
on box properties use their initial values.
A text-only orthogonal block wraps down its used content height and stacks
its lines from block-start. Once the columns determine its width, the
horizontal parent resolves auto margins and stacks the physical border box.
Widths and heights in line records are physical. Text uses the engine's
uniform glyph advances. Nested formatting contexts, mixed fonts and
justification inside this orthogonal block are unsupported.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from blackhole_agent.css_absolute import place_absolute
from blackhole_agent.css_container_query import match_container_query
from blackhole_agent.css_bidi import reorder_css_bidi
from blackhole_agent.css_auto_table import layout_auto_columns
from blackhole_agent.css_collapsed_border import resolve_collapsed_grid
from blackhole_agent.css_fixed_table import layout_fixed_columns
from blackhole_agent.css_flex_align import flex_line_cross_size, place_flex_alignment
from blackhole_agent.css_flex_base import resolve_flex_base
from blackhole_agent.css_flex_line import resolve_flex_line
from blackhole_agent.css_flex_wrap import wrap_flex_lines
from blackhole_agent.css_float_placement import place_floats
from blackhole_agent.css_grid_align import align_grid_item
from blackhole_agent.css_grid_areas import place_named_grid
from blackhole_agent.css_grid_content import size_content_grid_tracks
from blackhole_agent.css_grid_placement import place_grid_items
from blackhole_agent.css_grid_tracks import size_grid_tracks
from blackhole_agent.css_inline_line import layout_inline_line
from blackhole_agent.css_length_math import is_length_math
from blackhole_agent.css_line_break import _default_advance, wrap_lines
from blackhole_agent.css_relative import place_relative
from blackhole_agent.css_table_rows import layout_table_rows
from blackhole_agent.css_text_align import align_inline_line
from blackhole_agent.css_logical_box import (
    _LOGICAL,
    _LOGICAL_SHORTHAND,
    _PHYSICAL_SHORTHAND,
    _SIZES,
    _Invalid as _LogicalInvalid,
    _cascade,
    _solve as _solve_box_slots,
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
_DISPLAYS = frozenset(
    {"block", "inline", "inline-block", "flex", "grid", "table", "table-row", "table-cell", "none"}
)
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
_INLINE_REJECTED = ("text-align", "white-space")


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
class _Piece:
    text: str
    font_size: int
    line_height: str
    atom: _Box | None = None


@dataclass
class _Line:
    text: str
    x: int
    y: int
    height: int
    content_width: int
    runs: list[dict[str, object]] = field(default_factory=list)
    baseline: int = 0
    atoms: list[dict[str, object]] = field(default_factory=list)
    glyphs: list[dict[str, object]] = field(default_factory=list)


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
    static_index: int = 0
    flow_y: int = 0
    lines: list[_Line] = field(default_factory=list)
    atoms: list[_Box] = field(default_factory=list)
    pieces: list[_Piece] = field(default_factory=list)
    local_x: int = 0
    flex: dict[str, object] | None = None
    grid: dict[str, object] | None = None
    table: dict[str, object] | None = None
    parent_box: _Box | None = None
    container_type: str = "normal"
    container_name: str = "none"
    query_rules: list[tuple[str, object]] = field(default_factory=list)
    sheet: list = field(default_factory=list)
    custom: dict = field(default_factory=dict)
    element: object = None
    tree: object = None


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
        container_rules: list[tuple[str, object]] = []
        declarations, registrations = _stylesheet(stylesheet, container_rules=container_rules)
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
            container_rules=container_rules,
        )
        if root.display == "none":
            raise _Invalid("root is not displayed")
        if root.display in {"table-row", "table-cell"}:
            raise _Invalid("table box is outside the table")
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
            root,
            container_rules,
        )
        _set_inline(root, tree, order[0], styles, declarations)
        _solve(root, viewport_width, viewport_height, viewport_height, 0)
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
    host: _Box,
    container_rules: list | None = None,
) -> tuple[list[_Box], list[_Box], list[_Box], list[_Box]]:
    formatting_context = {"grid": _walk_grid, "flex": _walk_flex, "table": _walk_table}.get(host.display)
    if formatting_context is not None:
        return formatting_context(tree, element, inherited, fonts, styles, declarations, ids, counter, host)
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
            container_rules=container_rules,
        )
        box.parent_box = host
        if box.display == "none":
            continue
        if box.position in {"absolute", "fixed"}:
            if tree.children.get(child):
                raise _Invalid("positioned content is unsupported")
            box.inline_text = child.text or ""
            box.static_index = len(found)
            positioned.append(box)
            continue
        if box.float_side != "none":
            _reject_float_content(tree, child)
            box.inline_text = child.text or ""
            floats.append(box)
            flow.append(box)
            continue
        if box.display in {"table-row", "table-cell"}:
            raise _Invalid("table box is outside the table")
        inline = box.display == "inline"
        if inline and box.position == "relative":
            raise _Invalid("relative inline is unsupported")
        if box.display == "inline-block" and box.position != "static":
            raise _Invalid("positioned inline-block is unsupported")
        nested = _walk(
            tree, child, _modes(box), _fonts(box), box.direction, styles, declarations,
            ids, counter, host if inline else box, container_rules,
        )
        if inline:
            children, child_floats, child_flow, child_positioned = nested
            found.extend(children)
            floats.extend(child_floats)
            flow.extend(child_flow)
            positioned.extend(child_positioned)
            continue
        box.children, box.floats, box.flow, box.positioned = nested
        _set_inline(box, tree, child, styles, declarations)
        if box.display == "inline-block":
            if box.children or box.floats or box.positioned or box.atoms:
                raise _Invalid("inline-block content is unsupported")
            host.atoms.append(box)
            continue
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
    container_rules: list | None = None,
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
    box_declarations = _boxed_declarations(winners, custom)
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
        container_type=_container_kind(_declared(winners, "container-type", custom)),
        container_name=_container_label(_declared(winners, "container-name", custom)),
        query_rules=_matching_queries(tree, element, container_rules),
        sheet=declarations,
        custom=custom,
        element=element,
        tree=tree,
    )


def _container_kind(value: str | None) -> str:
    if value is None or value in {"initial", "unset", "revert"}:
        return "normal"
    if value == "inherit":
        raise _Invalid("container-type inherit is unsupported")
    token = " ".join(value.lower().split())
    if token not in {"normal", "size", "inline-size"}:
        raise _Invalid("container-type is invalid")
    return token


def _container_label(value: str | None) -> str:
    if value is None or value in {"initial", "unset", "revert", "none"}:
        return "none"
    if value == "inherit":
        raise _Invalid("container-name inherit is unsupported")
    return " ".join(value.split())


def _matching_queries(tree, element, rules: list | None) -> list[tuple[str, object]]:
    matched: list[tuple[str, object]] = []
    for query, decl in rules or []:
        if _declaration_precedence(tree, element, decl) is not None:
            matched.append((str(query), decl))
    return matched


def _boxed_declarations(winners, custom: dict) -> list[tuple[str, str]]:
    return [
        (prop, value)
        for prop, value in ((name, _declared(winners, name, custom)) for name in _winner_names(winners))
        if prop in _BOX_PROPS and value is not None and _wide_keyword(value) is None
    ]


def _retarget_query_descendants(box: _Box) -> None:
    if box.container_type not in {"inline-size", "size"}:
        return
    for target in _query_targets(box):
        _retarget_query_target(target)


def _query_targets(box: _Box) -> list[_Box]:
    found: list[_Box] = []

    def walk(node: _Box) -> None:
        for child in (*node.children, *node.floats, *node.positioned, *node.atoms):
            found.append(child)
            if child.container_type in {"inline-size", "size"}:
                continue
            walk(child)

    walk(box)
    return found


def _retarget_query_target(target: _Box) -> None:
    if not target.query_rules or target.tree is None or target.element is None:
        return
    chosen = [decl for query, decl in target.query_rules if _query_matches(target, str(query))]
    if not chosen:
        return
    winners = _winners(target.tree, target.element, [*target.sheet, *chosen])
    target.declarations = _boxed_declarations(winners, target.custom)


def _query_matches(target: _Box, query: str) -> bool:
    result = match_container_query(_query_chain(target), query)
    if result.get("outcome") != "matched":
        raise _Invalid(str(result.get("reason") or "container query is invalid"))
    matches = result.get("matches")
    return isinstance(matches, list) and target.id in matches


def _query_chain(target: _Box) -> list[dict[str, object]]:
    chain: list[_Box] = []
    current: _Box | None = target
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        chain.append(current)
        current = current.parent_box
    chain.reverse()
    nodes: list[dict[str, object]] = []
    for box in chain:
        nodes.append(
            {
                "id": box.id,
                "parent": None if box.parent_box is None else box.parent_box.id,
                "width": box.content_width,
                "height": 0 if box.definite_height is None else box.definite_height,
                "container_type": box.container_type,
                "container_name": box.container_name,
                "writing_mode": box.writing_mode,
                "font_size": box.font_size,
            }
        )
    return nodes


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


def _edge_extent(solved: dict[str, object], *sides: str) -> int:
    return sum(_px(solved.get(f"{kind}_{side}"), f"{kind}-{side}") for side in sides for kind in ("border", "padding"))


def _vertical_geometry(
    box: _Box, flow: dict[str, object], width: int, height: int | None, height_limit: int | None,
) -> dict[str, object]:
    if box.children or box.floats or box.atoms or box.positioned or _mixed_runs(box):
        raise _Invalid("vertical block requires uniform inline text")
    if box.text_align in {"justify", "justify-all"}:
        raise _Invalid("vertical justification is unsupported")

    # Resolve logical declarations in the child's axes once. Physical margins
    # and percentage bases belong to its horizontal containing block.
    slots = _physical_slots(box, flow)
    height_basis = height if height is not None else height_limit
    if height_basis is None:
        for name in ("height", "min-height", "max-height"):
            if "%" in slots.get(name, ""):
                slots.pop(name)
    parent_flow = resolve_writing_mode("horizontal-tb", box.parent_direction or "ltr")
    sizing = slots.get("box-sizing", "content-box")

    def geometry() -> dict[str, object]:
        try:
            # Indefinite-height percentages were removed above. Absolute calc()
            # lengths are still resolvable with zero as their percentage basis.
            return _solve_box_slots(parent_flow, slots, width, width, height_basis or 0, sizing)
        except _LogicalInvalid as exc:
            raise _Invalid(str(exc)) from exc

    solved = geometry()
    if solved["content_height"] == "auto":
        minimum, maximum = _intrinsic_text_sizes(box)
        edges = _edge_extent(solved, "top", "bottom")
        measure = maximum
        if height_limit is not None:
            margins = _px(solved["margin_top"], "margin-top") + _px(solved["margin_bottom"], "margin-bottom")
            measure = min(maximum, max(minimum, height_limit - margins - edges))
        slots["height"] = f"{measure + (edges if sizing == 'border-box' else 0)}px"
        solved = geometry()

    measure = _px(solved["content_height"], "content height")
    lines = _plain_lines(box, measure, str(flow["direction"]))
    if slots.get("width", "auto") == "auto":
        extent = sum(line.height for line in lines)
        if sizing == "border-box":
            extent += _edge_extent(solved, "left", "right")
        slots["width"] = f"{extent}px"
        solved = geometry()

    block_size = _px(solved["content_width"], "content width")
    for line in lines:
        # The line builder measures x from line-left and y from block-start.
        x = block_size - line.y - line.height if flow["block_start"] == "right" else line.y
        y = measure - line.x - line.content_width if flow["line_left"] == "bottom" else line.x
        line.x, line.y = x, y
        line.content_width, line.height = line.height, line.content_width
    box.lines = lines
    return solved


def _solve(
    box: _Box, parent_width: int, parent_height: int | None, viewport_height: int | None,
    parent_content_x: int, scrollport_height: int | None = None,
) -> None:
    flow = _writing_flow(box)
    horizontal = flow["horizontal"] is True
    vertical_text = not horizontal and box.display == "block"
    if vertical_text:
        limits = [limit for limit in (parent_height, viewport_height, scrollport_height) if limit is not None]
        solved = _vertical_geometry(box, flow, parent_width, parent_height, min(limits, default=None))
    else:
        available_inline, available_block = (parent_width, parent_height) if horizontal else (parent_height, parent_width)
        if available_inline is None:
            raise _Invalid("indefinite inline containing size")
        declarations = box.declarations
        if available_block is None:
            blocked = _block_properties(horizontal)
            declarations = [item for item in declarations if not (item[0] in blocked and _needs_basis(item[1]))]
        solved = resolve_logical_box(
            declarations,
            writing_mode=box.writing_mode, direction=box.direction, text_orientation=box.text_orientation,
            containing_inline=available_inline, percentage_basis=parent_width, containing_block=available_block,
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
    if vertical_text:
        return
    _retarget_query_descendants(box)
    content_x = box.x + _edge_extent(solved, "left")
    if box.display == "grid":
        _place_grid(box, content_x, viewport_height)
        return
    if box.display == "flex":
        _place_flex_row(box, content_x)
        return
    if box.display == "table":
        _place_table(box, content_x)
        return
    if box.floats and not box.children:
        _place_floats(box, content_x)
    if not box.children and (box.inline_text or box.floats or box.atoms):
        _fill_lines(box)
    # Only a definite containing block, scrollport or the viewport constrains
    # an orthogonal descendant. Ordinary fixed-height ancestors do not.
    if box.overflow in {"hidden", "scroll", "auto"}:
        scrollport_height = box.definite_height
    for child in box.children:
        _solve(child, box.content_width, box.definite_height, viewport_height, content_x, scrollport_height)
    if box.floats and box.children:
        _lay_sibling_floats(box, content_x)


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
        box.flow_y = box.y
        box.border_height = _px(placed.get("border_height"), "border height")
        if box.definite_height is None:
            box.content_height = box.border_height - _edge_extent(box.solved, "top", "bottom")
        else:
            box.content_height = box.definite_height
    else:
        if border_at is None:
            raise _Invalid("placed box is missing")
        box.y = border_at + box.anchor_y
        box.flow_y = box.y
    box.border_width = box.content_width + _edge_extent(box.solved, "left", "right")
    if box.content_height < 0:
        raise _Invalid("content height is invalid")
    content_x, content_y = _position_lines(box)
    for atom in box.atoms:
        atom.x, atom.y = content_x + atom.local_x, content_y + atom.local_y
        _position_lines(atom)
    for fl in box.floats:
        if not fl.float_placed:
            continue
        fl.y = content_y + fl.local_y
        _position_lines(fl)
    for child in box.children:
        _assign_y(child, by_id, origin, box.y)


def _position_lines(box: _Box) -> tuple[int, int]:
    x = box.x + _edge_extent(box.solved, "left")
    y = box.y + _edge_extent(box.solved, "top")
    for line in box.lines:
        line.x += x
        line.y += y
    return x, y


def _each(box: _Box):
    yield box
    for fl in box.floats:
        if fl.float_placed:
            yield fl
    for atom in box.atoms:
        yield from _each(atom)
    for child in box.children:
        yield from _each(child)
    for abs_box in box.positioned:
        yield from _each(abs_box)


def _record(box: _Box) -> dict[str, object]:
    item = {
        "id": box.id,
        "x": box.x,
        "y": box.y,
        "content_width": box.content_width,
        "content_height": box.content_height,
        "border_width": box.border_width,
        "border_height": box.border_height,
        "margin_left": box.margin_left,
        "margin_right": box.margin_right,
        "lines": [_record_line(line) for line in box.lines],
    }
    used = (box.table or {}).get("used_edges")
    if isinstance(used, dict):
        item["collapsed_borders"] = used
    return item


def _record_line(line: _Line) -> dict[str, object]:
    item: dict[str, object] = {
        "text": line.text,
        "x": line.x,
        "y": line.y,
        "height": line.height,
        "content_width": line.content_width,
    }
    if line.runs:
        item["runs"] = [
            {
                "text": run["text"],
                "x": line.x + int(run["x"]),
                "font_size": run["font_size"],
                "width": run["width"],
            }
            for run in line.runs
        ]
    if line.atoms:
        item["atoms"] = [
            {
                "id": str(entry["id"]),
                "x": line.x + int(entry["x"]),
                "width": int(entry["width"]),
            }
            for entry in line.atoms
        ]
    if line.glyphs:
        item["glyphs"] = [
            {
                "ch": str(glyph["ch"]),
                "x": line.x + int(glyph["x"]),
                "width": int(glyph["width"]),
            }
            for glyph in line.glyphs
        ]
    return item


def _fonts(box: _Box) -> dict[str, str]:
    return {
        "font-size": f"{box.font_size}px",
        "line-height": box.line_height,
        "text-align": box.text_align,
        "white-space": box.white_space,
    }


def _set_inline(box: _Box, tree, element, styles, declarations) -> None:
    if box.children:
        if box.atoms:
            raise _Invalid("inline-block beside blocks is unsupported")
        return
    pieces = _inline_pieces(tree, element, styles, declarations, _fonts(box), box.atoms)
    if pieces is None and box.atoms:
        raise _Invalid("inline-block beside blocks is unsupported")
    box.pieces = pieces or []
    box.inline_text = None if pieces is None else "".join(piece.text for piece in pieces)


def _inline_pieces(tree, element, styles, declarations, fonts: dict[str, str], atoms: list[_Box]) -> list[_Piece] | None:
    stream = iter(atoms)
    pieces: list[_Piece] = []

    def add(text: str, size: int, leading: str) -> None:
        if not text:
            return
        if pieces and pieces[-1].atom is None and pieces[-1].font_size == size and pieces[-1].line_height == leading:
            pieces[-1].text += text
            return
        pieces.append(_Piece(text, size, leading))

    def walk(node, parent_fonts: dict[str, str]) -> bool:
        size = _positive_px(parent_fonts["font-size"], "font-size")
        leading = parent_fonts["line-height"]
        add(node.text or "", size, leading)
        for child in list(node):
            if not _local_name(child):
                continue
            kind = _flow_kind(tree, child, styles, declarations)
            if kind in {"skip", "out"}:
                add(child.tail or "", size, leading)
                continue
            if kind == "inline-block":
                try:
                    atom = next(stream)
                except StopIteration as exc:
                    raise _Invalid("inline-block is unsupported") from exc
                pieces.append(_Piece("", size, leading, atom))
                add(child.tail or "", size, leading)
                continue
            if kind == "block":
                return False
            _reject_inline_type(tree, child, styles, declarations)
            if not walk(child, _inline_fonts(tree, child, styles, declarations, parent_fonts)):
                return False
            add(child.tail or "", size, leading)
        return True

    if not walk(element, fonts):
        return None
    if next(stream, None) is not None:
        raise _Invalid("inline-block is unsupported")
    return pieces


def _inline_fonts(tree, element, styles, declarations, parent: dict[str, str]) -> dict[str, str]:
    custom = styles.get(element, ({}, ""))[0]
    winners = _winners(tree, element, declarations)
    size = _font_size(_declared(winners, "font-size", custom), parent["font-size"])
    return {
        "font-size": f"{size}px",
        "line-height": _line_height(_declared(winners, "line-height", custom), parent["line-height"]),
        "text-align": parent["text-align"],
        "white-space": parent["white-space"],
    }


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
    if display == "inline-block":
        return "inline-block"
    return "block"


def _reject_inline_type(tree, element, styles, declarations) -> None:
    custom = styles.get(element, ({}, ""))[0]
    winners = _winners(tree, element, declarations)
    for name in _INLINE_REJECTED:
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
    if tree.children.get(element):
        raise _Invalid("float content is unsupported")


_AUTO_WORDS = frozenset({"auto", "initial", "unset", "revert"})


def _is_auto(value: str | None) -> bool:
    if value is None:
        return True
    return value.strip().lower() in _AUTO_WORDS


def _writing_flow(box: _Box) -> dict[str, object]:
    flow = resolve_writing_mode(box.writing_mode, box.direction, text_orientation=box.text_orientation)
    if flow.get("outcome") != "resolved":
        raise _Invalid(str(flow.get("reason") or "writing-mode is invalid"))
    return flow


def _physical_slots(box: _Box, flow: dict[str, object] | None = None) -> dict[str, str]:
    try:
        return _cascade(box.declarations, flow or _writing_flow(box))
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
        _place_one_absolute(abs_box, cb, box)
    for child in box.children:
        _place_positioned(child, viewport, frame)


def _hypothetical_edges(parent: _Box, index: int) -> tuple[int, int, int]:
    """Margin-edge x, y, and right of a static block in this parent's flow."""

    border_left = _px(parent.solved.get("border_left"), "border-left")
    border_right = _px(parent.solved.get("border_right"), "border-right")
    pad_left = _px(parent.solved.get("padding_left"), "padding-left")
    pad_right = _px(parent.solved.get("padding_right"), "padding-right")
    content_left = parent.x + border_left + pad_left
    content_right = parent.x + parent.border_width - border_right - pad_right
    if index < len(parent.children):
        sibling = parent.children[index]
        margin_top = _px(sibling.solved.get("margin_top"), "margin-top")
        return content_left, sibling.flow_y - margin_top, content_right
    if parent.children:
        last = parent.children[-1]
        margin_bottom = _px(last.solved.get("margin_bottom"), "margin-bottom")
        return content_left, last.flow_y + last.border_height + margin_bottom, content_right
    return content_left, parent.y + _edge_extent(parent.solved, "top"), content_right


def _place_one_absolute(box: _Box, cb: _Edge, parent: _Box) -> None:
    slots = _physical_slots(box)
    left, right = _inset(slots, "left"), _inset(slots, "right")
    top, bottom = _inset(slots, "top"), _inset(slots, "bottom")
    needs_static = (_is_auto(left) and _is_auto(right)) or (_is_auto(top) and _is_auto(bottom))
    needs_shrink = _is_auto(slots.get("width")) and (_is_auto(left) or _is_auto(right))
    needs_height = _is_auto(slots.get("height")) and (
        _is_auto(top) or _is_auto(bottom) or cb.height is None
    )
    if box.writing_mode != "horizontal-tb" and (needs_static or needs_shrink or needs_height):
        if _is_auto(left) and _is_auto(right):
            raise _Invalid("static position is unsupported")
        if _is_auto(top) and _is_auto(bottom):
            raise _Invalid("static position is unsupported")
        if needs_shrink:
            raise _Invalid("absolute shrink-to-fit is unsupported")
        raise _Invalid("absolute height is indefinite")
    if needs_static and (parent.inline_text or parent.pieces):
        raise _Invalid("static position inside a line is unsupported")
    if needs_static:
        hyp_x, hyp_y, hyp_right = _hypothetical_edges(parent, box.static_index)
        static_left = hyp_x - cb.x
        static_right = (cb.x + cb.width) - hyp_right
        static_top = hyp_y - cb.y
    else:
        static_left = static_right = static_top = 0
    minimum, maximum = _intrinsic_text_sizes(box) if box.inline_text else (0, 0)
    direction = box.direction if box.direction in {"ltr", "rtl"} else "ltr"

    def solve(content_height: int) -> dict[str, object]:
        return place_absolute(
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
            static_left=static_left,
            static_right=static_right,
            static_top=static_top,
            min_content=minimum,
            max_content=maximum,
            content_height=content_height,
        )

    placed = solve(0)
    if placed.get("outcome") == "placed" and box.inline_text:
        width = _px(placed.get("width"), "content width")
        measured = sum(line.height for line in _plain_lines(box, width, direction))
        if measured != 0:
            placed = solve(measured)
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
    box.lines = _plain_lines(
        box,
        box.content_width,
        direction,
        place_glyphs=box.writing_mode == "horizontal-tb",
    )
    _position_lines(box)


_WIDTH_LIMITS = ("min-width", "max-width", "min-inline-size", "max-inline-size")
_HEIGHT_LIMITS = ("min-height", "max-height", "min-block-size", "max-block-size")
_LIMIT_INITIAL = {
    "min-width": "auto",
    "max-width": "none",
    "min-inline-size": "auto",
    "max-inline-size": "none",
    "min-height": "auto",
    "max-height": "none",
    "min-block-size": "auto",
    "max-block-size": "none",
}


def _specified_auto(value: object) -> bool:
    if value is None:
        return True
    return _is_auto(str(value))


def _has_explicit_limit(box: _Box, names: tuple[str, ...]) -> bool:
    declared = {prop: value.strip().lower() for prop, value in box.declarations}
    for name in names:
        raw = declared.get(name)
        if raw is None or raw in {_LIMIT_INITIAL[name], "initial", "unset", "revert"}:
            continue
        return True
    return False


def _shrink_advances(box: _Box) -> dict[str, int] | list[int]:
    text = box.inline_text or ""
    if _mixed_runs(box):
        styles = _style_stream(box.pieces)
        if len(styles) != len(text):
            raise _Invalid("inline run is invalid")
        return [_advance_of(ch, styles[index][0]) for index, ch in enumerate(text)]
    return {ch: box.font_size * _default_advance(ch) for ch in set(text) | {" "}}


def _intrinsic_text_sizes(box: _Box) -> tuple[int, int]:
    text = box.inline_text or ""
    measured = wrap_lines(text, 0, white_space=box.white_space, advances=_shrink_advances(box))
    if measured["outcome"] != "wrapped":
        raise _Invalid(str(measured.get("reason") or "text measurement failed"))
    return _px(measured["min_content"], "min-content"), _px(measured["max_content"], "max-content")


def _shrink_float_width(box: _Box, available: int) -> int:
    minimum, maximum = _intrinsic_text_sizes(box)
    return min(max(minimum, available), maximum)


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
    width_auto = _specified_auto(solved.get("specified_width"))
    height_auto = _specified_auto(solved.get("specified_height")) or solved.get("content_height") in {None, "auto"}
    if width_auto:
        if _has_explicit_limit(fl, _WIDTH_LIMITS):
            raise _Invalid("float intrinsic limit is unsupported")
        if any(prop == "box-sizing" and value.strip().lower() == "border-box" for prop, value in fl.declarations):
            raise _Invalid("float shrink-to-fit box is unsupported")
        content_width = _shrink_float_width(
            fl,
            box.content_width - margin_left - margin_right - border_left - border_right - padding_left - padding_right,
        )
    else:
        if solved.get("content_width") in {None, "auto"}:
            raise _Invalid("float width is indefinite")
        content_width = _px(solved.get("content_width"), "float width")
    if height_auto and _has_explicit_limit(fl, _HEIGHT_LIMITS):
        raise _Invalid("float intrinsic limit is unsupported")
    fl.solved = solved
    fl.content_width = content_width
    fl.definite_height = None if height_auto else _px(solved.get("content_height"), "float height")
    if fl.inline_text:
        _fill_lines(fl)
    if fl.definite_height is None:
        fl.definite_height = 0
    content_height = fl.definite_height
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


def _text_offset(box: _Box, measure: int, content: int, last: bool, *, direction: str | None = None) -> int:
    aligned = align_inline_line(
        measure, [{"id": "text", "width": content}],
        text_align=box.text_align, direction=direction or box.direction,
        parent_direction=box.parent_direction, white_space=box.white_space, last_line=last,
    )
    items = aligned.get("items") if aligned["outcome"] == "aligned" else None
    if not isinstance(items, list) or len(items) != 1 or not isinstance(items[0], dict):
        raise _Invalid(str(aligned.get("reason") or "text alignment failed"))
    return _px(items[0].get("x"), "line offset")


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
        last = rest == "" or (box.white_space in _COLLAPSED_EMPTY and not rest.strip())
        offset = _text_offset(box, available, content, last)
        records.append(
            _Line(
                text=rendered,
                x=_px(left, "line x") + offset,
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


def _mixed_runs(box: _Box) -> bool:
    return any(
        run.font_size != box.font_size or run.line_height != box.line_height for run in box.pieces if run.text
    )


def _style_stream(runs: list[_Piece]) -> list[tuple[int, str]]:
    styles: list[tuple[int, str]] = []
    for run in runs:
        styles.extend((run.font_size, run.line_height) for _ in run.text)
    return styles


def _advance_of(ch: str, size: int) -> int:
    return _px(size * _default_advance(ch), "advance")


def _collapse_styled(text: str, styles: list[tuple[int, str]]) -> tuple[str, list[tuple[int, str]]]:
    pieces: list[str] = []
    chosen: list[tuple[int, str]] = []
    index = 0
    count = len(text)
    gap: tuple[int, str] | None = None
    while index < count:
        if text[index].isspace():
            if gap is None:
                gap = styles[index]
            index += 1
            continue
        if pieces:
            if gap is None:
                raise _Invalid("inline font break is unsupported")
            pieces.append(" ")
            chosen.append(gap)
        gap = None
        while index < count and not text[index].isspace():
            pieces.append(text[index])
            chosen.append(styles[index])
            index += 1
    collapsed = "".join(pieces)
    if collapsed != " ".join(text.split()):
        raise _Invalid("inline font break is unsupported")
    return collapsed, chosen


def _split_styled(
    source: str,
    styles: list[tuple[int, str]],
    rendered: str,
    white_space: str,
) -> tuple[list[tuple[int, str]], str, list[tuple[int, str]]]:
    if len(styles) != len(source):
        raise _Invalid("inline run is invalid")
    if white_space in {"pre", "pre-wrap", "break-spaces"}:
        if rendered and not source.startswith(rendered):
            raise _Invalid("inline font break is unsupported")
        used = len(rendered)
        return styles[:used], source[used:], styles[used:]
    collapsed, collapsed_styles = _collapse_styled(source, styles)
    if not rendered:
        if source.strip():
            raise _Invalid("inline font break is unsupported")
        return [], "", []
    if not collapsed.startswith(rendered):
        raise _Invalid("inline font break is unsupported")
    used = len(rendered)
    rest = collapsed[used:]
    rest_styles = collapsed_styles[used:]
    if rest.startswith(" "):
        rest = rest[1:]
        rest_styles = rest_styles[1:]
    return collapsed_styles[:used], rest, rest_styles


def _group_runs(rendered: str, styles: list[tuple[int, str]]) -> list[tuple[str, int, str, int]]:
    if len(rendered) != len(styles):
        raise _Invalid("inline font break is unsupported")
    groups: list[tuple[str, int, str, int]] = []
    for ch, (size, leading) in zip(rendered, styles, strict=True):
        width = _advance_of(ch, size)
        if groups and groups[-1][1] == size and groups[-1][2] == leading:
            text, _, _, previous = groups[-1]
            groups[-1] = (text + ch, size, leading, previous + width)
            continue
        groups.append((ch, size, leading, width))
    return groups


def _runs_line_height(box: _Box, groups: list[tuple[str, int, str, int]]) -> tuple[int, int]:
    boxes = []
    for index, (_text, size, leading, _width) in enumerate(groups):
        boxes.append(
            {
                "id": f"r{index}",
                "kind": "text",
                "vertical_align": "baseline",
                "ascent": size,
                "descent": 0,
                "line_height": _used_line_height(leading, size),
            }
        )
    laid = layout_inline_line(
        {
            "ascent": box.font_size,
            "descent": 0,
            "line_height": _used_line_height(box.line_height, box.font_size),
            "x_height": 0,
        },
        boxes,
    )
    if laid.get("outcome") != "resolved":
        raise _Invalid(str(laid.get("reason") or "line box failed"))
    return _px(laid.get("line_height"), "line height"), _px(laid.get("baseline"), "baseline")


def _fill_mixed(box: _Box) -> None:
    text = box.inline_text or ""
    if not text:
        return
    if "\t" in text:
        raise _Invalid("inline font tab is unsupported")
    styles = _style_stream(box.pieces)
    if len(styles) != len(text):
        raise _Invalid("inline run is invalid")
    records: list[_Line] = []
    cursor = 0
    remaining = text
    remaining_styles = styles
    for _ in range(10000):
        if not remaining or (box.white_space in _COLLAPSED_EMPTY and not remaining.strip()):
            break
        advances = [_advance_of(ch, remaining_styles[index][0]) for index, ch in enumerate(remaining)]
        wrapped = wrap_lines(remaining, box.content_width, white_space=box.white_space, advances=advances)
        lines = wrapped.get("lines") if wrapped.get("outcome") == "wrapped" else None
        if not isinstance(lines, list) or not lines or not isinstance(lines[0], dict):
            raise _Invalid(str(wrapped.get("reason") or "line break failed"))
        rendered = str(lines[0].get("text") or "")
        content = _px(lines[0].get("content_width"), "line width")
        if not rendered and content == 0:
            raise _Invalid("line break failed")
        line_styles, rest, rest_styles = _split_styled(remaining, remaining_styles, rendered, box.white_space)
        if rest == remaining:
            raise _Invalid("line break failed")
        groups = _group_runs(rendered, line_styles)
        height, baseline = _runs_line_height(box, groups)
        last = rest == "" or (box.white_space in _COLLAPSED_EMPTY and not rest.strip())
        offset = _text_offset(box, box.content_width, content, last)
        local = 0
        runs: list[dict[str, object]] = []
        for piece, size, _leading, width in groups:
            runs.append({"text": piece, "x": local, "font_size": size, "width": width})
            local += width
        records.append(
            _Line(
                text=rendered,
                x=offset,
                y=cursor,
                height=height,
                content_width=content,
                runs=runs,
                baseline=baseline,
            )
        )
        remaining = rest
        remaining_styles = rest_styles
        cursor += height
    else:
        raise _Invalid("line break failed")
    box.lines = records
    if box.definite_height is None:
        box.definite_height = cursor


_ZWSP = "\u200b"
_MARK = 0xE000


def _atom_edges(parent: _Box, atom: _Box, row: dict[str, int]) -> tuple[int, int]:
    solved = atom.solved
    margin_top = row["margin_top"]
    margin_bottom = _float_margin(atom, "margin-bottom", parent.content_width)
    border_top = _px(solved.get("border_top"), "border-top")
    border_bottom = _px(solved.get("border_bottom"), "border-bottom")
    padding_top = _px(solved.get("padding_top"), "padding-top")
    padding_bottom = _px(solved.get("padding_bottom"), "padding-bottom")
    if atom.overflow != "visible" or not atom.lines:
        return row["outer_height"], 0
    last = atom.lines[-1]
    content_base = last.y + last.baseline
    above = margin_top + border_top + padding_top + content_base
    below = atom.content_height - content_base + padding_bottom + border_bottom + margin_bottom
    if below < 0:
        raise _Invalid("inline-block baseline is invalid")
    return above, below


def _line_extent(
    box: _Box,
    groups: list[tuple[str, int, str, int]],
    edges: list[tuple[int, int]],
) -> tuple[int, int, list[int]]:
    payload = []
    for index, (_text, size, leading, _width) in enumerate(groups):
        payload.append(
            {
                "id": f"t{index}",
                "kind": "text",
                "vertical_align": "baseline",
                "ascent": size,
                "descent": 0,
                "line_height": _used_line_height(leading, size),
            }
        )
    if not payload:
        payload.append(
            {
                "id": "strut",
                "kind": "text",
                "vertical_align": "baseline",
                "ascent": box.font_size,
                "descent": 0,
                "line_height": _used_line_height(box.line_height, box.font_size),
            }
        )
    laid = layout_inline_line(
        {
            "ascent": box.font_size,
            "descent": 0,
            "line_height": _used_line_height(box.line_height, box.font_size),
            "x_height": 0,
        },
        payload,
    )
    if laid.get("outcome") != "resolved":
        raise _Invalid(str(laid.get("reason") or "line box failed"))
    above = _px(laid.get("baseline"), "baseline")
    below = _px(laid.get("line_height"), "line height") - above
    for edge_above, edge_below in edges:
        above = max(above, edge_above)
        below = max(below, edge_below)
    return above + below, above, [above - edge_above for edge_above, _edge_below in edges]


def _fill_inline_blocks(box: _Box) -> None:
    """Place inline-blocks as atomic line items around the parent's text."""

    if box.writing_mode != "horizontal-tb" or box.direction != "ltr":
        raise _Invalid("inline-block writing mode is unsupported")
    if len(box.atoms) > 32:
        raise _Invalid("inline-block is unsupported")
    for atom in box.atoms:
        if atom.writing_mode != "horizontal-tb" or atom.direction != "ltr":
            raise _Invalid("inline-block writing mode is unsupported")
    measured = {atom.id: _measure_float(box, atom) for atom in box.atoms}
    entries: list[tuple[str, int, str, _Box | None]] = []
    serial = 0
    for piece in box.pieces:
        if piece.atom is None:
            for ch in piece.text:
                if ch in "\t\r\n" or ch == _ZWSP or _MARK <= ord(ch) <= _MARK + 31:
                    raise _Invalid("inline-block break is unsupported")
                entries.append((ch, piece.font_size, piece.line_height, None))
            continue
        mark = chr(_MARK + serial)
        serial += 1
        entries.append((_ZWSP, piece.font_size, piece.line_height, None))
        entries.append((mark, piece.font_size, piece.line_height, piece.atom))
        entries.append((_ZWSP, piece.font_size, piece.line_height, None))
    if serial != len(box.atoms):
        raise _Invalid("inline-block is unsupported")
    source = "".join(item[0] for item in entries)
    advances = []
    for ch, size, _leading, atom in entries:
        if ch == _ZWSP:
            advances.append(0)
        elif atom is not None:
            advances.append(measured[atom.id]["outer_width"])
        else:
            advances.append(_advance_of(ch, size))
    wrapped = wrap_lines(source, max(box.content_width, 0), white_space=box.white_space, advances=advances)
    raw_lines = wrapped.get("lines") if wrapped.get("outcome") == "wrapped" else None
    if not isinstance(raw_lines, list):
        raise _Invalid(str(wrapped.get("reason") or "line break failed"))
    records: list[_Line] = []
    cursor_y = 0
    index = 0
    placed: set[str] = set()
    visible_lines = [line for line in raw_lines if isinstance(line, dict)]
    last = len(visible_lines) - 1
    for line_index, line in enumerate(visible_lines):
        rendered = str(line.get("text") or "")
        content = _px(line.get("content_width"), "line width")
        if not rendered and content == 0:
            continue
        chosen: list[tuple[str, int, str, _Box | None]] = []
        for ch in rendered:
            while index < len(entries) and entries[index][0] != ch:
                if not entries[index][0].isspace():
                    raise _Invalid("inline-block line is invalid")
                index += 1
            if index >= len(entries):
                raise _Invalid("inline-block line is invalid")
            chosen.append(entries[index])
            index += 1
        groups: list[tuple[str, int, str, int]] = []
        runs: list[dict[str, object]] = []
        atom_records: list[dict[str, object]] = []
        atoms_here: list[tuple[_Box, int]] = []
        cursor = 0
        buf = ""
        buf_size = 0
        buf_leading = ""
        buf_width = 0
        buf_x = 0

        def flush() -> None:
            nonlocal buf, buf_width
            if not buf:
                return
            groups.append((buf, buf_size, buf_leading, buf_width))
            runs.append({"text": buf, "x": buf_x, "font_size": buf_size, "width": buf_width})
            buf = ""
            buf_width = 0

        for ch, size, leading, atom in chosen:
            if ch == _ZWSP:
                continue
            if atom is not None:
                flush()
                row = measured[atom.id]
                border_x = cursor + row["margin_left"]
                atoms_here.append((atom, border_x))
                atom_records.append({"id": atom.id, "x": border_x, "width": row["outer_width"]})
                cursor += row["outer_width"]
                placed.add(atom.id)
                continue
            advance = _advance_of(ch, size)
            if buf and (size != buf_size or leading != buf_leading):
                flush()
            if not buf:
                buf_x = cursor
                buf_size = size
                buf_leading = leading
            buf += ch
            buf_width += advance
            cursor += advance
        flush()
        if cursor != content:
            raise _Invalid("inline-block line is invalid")
        edges = [_atom_edges(box, atom, measured[atom.id]) for atom, _border_x in atoms_here]
        height, above, tops = _line_extent(box, groups, edges)
        offset = _text_offset(box, box.content_width, content, line_index == last)
        for (atom, border_x), top in zip(atoms_here, tops, strict=True):
            atom.local_x = offset + border_x
            atom.local_y = cursor_y + top + measured[atom.id]["margin_top"]
        visible = "".join(ch for ch, _size, _leading, atom in chosen if atom is None and ch != _ZWSP)
        records.append(
            _Line(
                text=visible,
                x=offset,
                y=cursor_y,
                height=height,
                content_width=content,
                runs=runs,
                baseline=above,
                atoms=atom_records,
            )
        )
        cursor_y += height
    while index < len(entries) and entries[index][0].isspace():
        index += 1
    if index != len(entries) or placed != {atom.id for atom in box.atoms}:
        raise _Invalid("inline-block line is invalid")
    box.lines = records
    if box.definite_height is None:
        box.definite_height = cursor_y


def _fill_lines(box: _Box) -> None:
    if box.atoms:
        if box.floats:
            raise _Invalid("inline-block beside a float is unsupported")
        _fill_inline_blocks(box)
        return
    if _mixed_runs(box) and box.floats and not box.children:
        raise _Invalid("inline font beside a float is unsupported")
    if box.floats and not box.children:
        _fill_lines_beside_floats(box)
        return
    if _mixed_runs(box):
        _fill_mixed(box)
        return
    box.lines = _plain_lines(box, box.content_width, box.direction, place_glyphs=True)
    if box.lines and box.definite_height is None:
        box.definite_height = sum(line.height for line in box.lines)


def _bidi_glyphs(text: str, direction: str, font_size: int) -> list[dict[str, object]]:
    """Visual x of one line when UAX #9 order differs from the source text.

    ``x`` is the distance from the line's left edge. Characters removed by
    bidi controls are omitted. A line whose visual string matches its source
    returns nothing, so an already-left-to-right line stays a plain line.
    """

    if direction not in {"ltr", "rtl"} or not text:
        return []
    ordered = reorder_css_bidi(text, direction=direction)
    visual = ordered.get("visual")
    if ordered.get("outcome") != "reordered" or not isinstance(visual, str) or visual == text:
        return []
    glyphs: list[dict[str, object]] = []
    cursor = 0
    for ch in visual:
        width = _advance_of(ch, font_size)
        glyphs.append({"ch": ch, "x": cursor, "width": width})
        cursor += width
    return glyphs


def _plain_lines(box: _Box, measure: int, direction: str, *, place_glyphs: bool = False) -> list[_Line]:
    text = box.inline_text or ""
    if not text:
        return []
    used = _used_line_height(box.line_height, box.font_size)
    height, baseline = _strut_metrics(box.font_size, used)
    wrapped = wrap_lines(text, measure, white_space=box.white_space, advances=_shrink_advances(box))
    lines = wrapped.get("lines") if wrapped.get("outcome") == "wrapped" else None
    if not isinstance(lines, list):
        raise _Invalid(str(wrapped.get("reason") or "line break failed"))
    if box.white_space in _COLLAPSED_EMPTY:
        lines = [line for line in lines if isinstance(line, dict) and (line.get("text") or line.get("content_width"))]
    if not lines:
        return []
    records: list[_Line] = []
    cursor = 0
    last = len(lines) - 1
    # A wrapped fragment is not its own paragraph. Glyphs stay off until the
    # whole paragraph fits on the line that is being painted.
    whole_paragraph = place_glyphs and len(lines) == 1
    for index, line in enumerate(lines):
        if not isinstance(line, dict):
            raise _Invalid("line is invalid")
        rendered = str(line.get("text") or "")
        content = _px(line.get("content_width"), "line width")
        offset = _text_offset(box, measure, content, index == last, direction=direction)
        glyphs = _bidi_glyphs(rendered, direction, box.font_size) if whole_paragraph else []
        if glyphs and sum(int(glyph["width"]) for glyph in glyphs) != content:
            glyphs = []
        records.append(
            _Line(
                text=rendered,
                x=offset,
                y=cursor,
                height=height,
                content_width=content,
                baseline=baseline,
                glyphs=glyphs,
            )
        )
        cursor += height
    return records


def _used_line_height(computed: str, font_size: int) -> int:
    if computed == "normal":
        return font_size
    if computed.endswith("px"):
        return _px(float(computed[:-2]), "line-height")
    return _px(float(computed) * font_size, "line-height")


def _strut_metrics(font_size: int, line_height: int) -> tuple[int, int]:
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
    return _px(laid.get("line_height"), "line height"), _px(laid.get("baseline"), "baseline")


def _strut_height(font_size: int, line_height: int) -> int:
    return _strut_metrics(font_size, line_height)[0]


_FLEX_DIRECTIONS = frozenset({"row", "row-reverse", "column", "column-reverse"})
_FLEX_WRAPS = frozenset({"nowrap", "wrap", "wrap-reverse"})
_FLEX_JUSTIFY = frozenset(
    {"normal", "flex-start", "flex-end", "center", "space-between", "space-around", "space-evenly"}
)
_FLEX_ITEMS = frozenset({"normal", "stretch", "flex-start", "flex-end", "center", "baseline"})
_FLEX_SELF = _FLEX_ITEMS | {"auto"}
_FLEX_CONTENT = _FLEX_JUSTIFY | {"stretch"}
_FLEX_EDGES = (
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
)
_ZERO_EDGE = frozenset({"0", "0px", "initial", "unset", "revert"})


def _walk_flex(
    tree,
    element,
    inherited: dict[str, str],
    fonts: dict[str, str],
    styles,
    declarations,
    ids: set[str],
    counter: list[int],
    host: _Box,
) -> tuple[list[_Box], list[_Box], list[_Box], list[_Box]]:
    host.flex = _flex_container(tree, element, styles, declarations)
    if host.writing_mode != "horizontal-tb" or host.direction != "ltr":
        raise _Invalid("flex writing mode is unsupported")
    _reject_loose_text(getattr(element, "text", None))
    items: list[_Box] = []
    for child in tree.children.get(element, []):
        _reject_loose_text(getattr(child, "tail", None))
        if _local_name(child) in _SKIP_TAGS:
            continue
        item = _make_box(
            tree,
            child,
            inherited,
            fonts,
            host.direction,
            styles,
            declarations,
            ids,
            counter,
            root=False,
        )
        if item.display == "none":
            continue
        if item.display in {"table", "table-row", "table-cell"}:
            raise _Invalid("table formatting in flex is unsupported")
        if item.position != "static" or item.float_side != "none":
            raise _Invalid("flex item is outside the line")
        if item.writing_mode != "horizontal-tb" or item.direction != "ltr":
            raise _Invalid("flex writing mode is unsupported")
        if _flex_item_elements(tree, child):
            raise _Invalid("flex item content is unsupported")
        column = str((host.flex or {}).get("direction") or "row") in {"column", "column-reverse"}
        _reject_item_edges(item, column=column)
        item.inline_text = child.text or ""
        item.flex = _flex_item(tree, child, styles, declarations)
        items.append(item)
    return items, [], items, []


def _flex_item_elements(tree, element) -> bool:
    return any(_local_name(child) not in _SKIP_TAGS for child in tree.children.get(element, []))


def _reject_loose_text(text: object) -> None:
    if isinstance(text, str) and text.strip():
        raise _Invalid("flex text is unsupported")


def _reject_item_edges(box: _Box, *, column: bool) -> None:
    sizing = _box_decl(box, "box-sizing")
    if sizing not in {None, "content-box", "initial", "unset", "revert"}:
        raise _Invalid("flex box-sizing is unsupported")
    for name in _FLEX_EDGES:
        if name.startswith("margin-"):
            continue
        raw = _box_decl(box, name)
        if raw is None or raw.strip().lower() in _ZERO_EDGE:
            continue
        raise _Invalid("flex item edge is unsupported")
    if column:
        limits = {
            "min-width": {"auto", "0", "0px", "initial", "unset", "revert"},
            "max-width": {"none", "initial", "unset", "revert"},
        }
    else:
        limits = {
            "min-height": {"auto", "0", "0px", "initial", "unset", "revert"},
            "max-height": {"none", "initial", "unset", "revert"},
        }
    for name, allowed in limits.items():
        raw = _box_decl(box, name)
        if raw is None or raw.strip().lower() in allowed:
            continue
        raise _Invalid("flex item cross limit is unsupported")


def _box_decl(box: _Box, name: str) -> str | None:
    found = None
    for prop, value in box.declarations:
        if prop == name:
            found = value
    return found


def _flex_container(tree, element, styles, declarations) -> dict[str, object]:
    custom = styles.get(element, ({}, ""))[0]
    direction = "row"
    wrap = "nowrap"
    justify = "normal"
    align = "normal"
    content_align = "normal"
    row_gap = 0
    column_gap = 0
    tracked = {
        "flex-direction",
        "flex-wrap",
        "flex-flow",
        "justify-content",
        "align-items",
        "align-content",
        "gap",
        "column-gap",
        "row-gap",
    }
    for _order, prop, raw in _winners(tree, element, declarations):
        if prop not in tracked:
            continue
        value = _author_value(raw, custom)
        if prop == "flex-direction":
            direction = _choice(value, "row", _FLEX_DIRECTIONS, "flex-direction")
        elif prop == "flex-wrap":
            wrap = _choice(value, "nowrap", _FLEX_WRAPS, "flex-wrap")
        elif prop == "flex-flow":
            direction, wrap = _flex_flow(value)
        elif prop == "justify-content":
            justify = _choice(value, "normal", _FLEX_JUSTIFY, "justify-content")
        elif prop == "align-items":
            align = _choice(value, "normal", _FLEX_ITEMS, "align-items")
        elif prop == "align-content":
            content_align = _choice(value, "normal", _FLEX_CONTENT, "align-content")
        elif prop == "gap":
            row_gap, column_gap = _gap_pair(value)
        elif prop == "row-gap":
            row_gap = _gap_length(value)
        elif prop == "column-gap":
            column_gap = _gap_length(value)
    return {
        "justify": justify,
        "align": align,
        "align_content": content_align,
        "wrap": wrap,
        "direction": direction,
        "row_gap": row_gap,
        "column_gap": column_gap,
    }


def _gap_pair(value: str) -> tuple[int, int]:
    if value in {"initial", "unset", "revert"}:
        return 0, 0
    if value == "inherit":
        raise _Invalid("flex gap inherit is unsupported")
    parts = value.split(" ")
    if len(parts) == 1:
        length = _gap_length(parts[0])
        return length, length
    if len(parts) == 2:
        return _gap_length(parts[0]), _gap_length(parts[1])
    raise _Invalid("flex gap is unsupported")


def _gap_length(value: str) -> int:
    if value in {"0", "0px", "normal", "initial", "unset", "revert"}:
        return 0
    if value == "inherit":
        raise _Invalid("flex gap inherit is unsupported")
    if value.endswith("px"):
        length = _px(float(value[:-2]), "flex gap")
        if length < 0:
            raise _Invalid("flex gap is unsupported")
        return length
    raise _Invalid("flex gap is unsupported")


def _axis_gaps(spec: dict[str, object], *, column: bool) -> tuple[int, int]:
    row_gap = _px(spec.get("row_gap", 0), "flex gap")
    column_gap = _px(spec.get("column_gap", 0), "flex gap")
    if column:
        return row_gap, column_gap
    return column_gap, row_gap


def _gapped_span(sizes: list[int], gap: int) -> int:
    if not sizes:
        return 0
    return sum(sizes) + gap * (len(sizes) - 1)


def _flex_item(tree, element, styles, declarations) -> dict[str, object]:
    custom = styles.get(element, ({}, ""))[0]
    grow = 0.0
    shrink = 1.0
    basis: object = "auto"
    align = "auto"
    order = 0
    for _order, prop, raw in _winners(tree, element, declarations):
        if prop not in {"flex", "flex-grow", "flex-shrink", "flex-basis", "align-self", "order"}:
            continue
        value = _author_value(raw, custom)
        if prop == "flex":
            grow, shrink, basis = _parse_flex(value)
        elif prop == "flex-grow":
            grow = _flex_factor(value, 0.0)
        elif prop == "flex-shrink":
            shrink = _flex_factor(value, 1.0)
        elif prop == "flex-basis":
            basis = _flex_basis(value)
        elif prop == "align-self":
            align = _choice(value, "auto", _FLEX_SELF, "align-self")
        else:
            order = _css_order(value)
    return {"grow": grow, "shrink": shrink, "basis": basis, "align": align, "order": order}


def _css_order(value: str) -> int:
    if value in {"0", "initial", "unset", "revert"}:
        return 0
    if value == "inherit":
        raise _Invalid("order inherit is unsupported")
    sign = -1 if value.startswith("-") else 1
    digits = value[1:] if sign < 0 else value
    if not digits.isdigit() or (len(digits) > 1 and digits.startswith("0")):
        raise _Invalid("order is unsupported")
    return 0 if digits == "0" else sign * int(digits)


def _stored_order(spec: object) -> int:
    raw = spec.get("order", 0) if isinstance(spec, dict) else 0
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise _Invalid("order is unsupported")
    return raw


def _author_value(value: str, custom: dict) -> str:
    if _wide_keyword(value) is not None:
        return value.strip().lower()
    substituted = _substitute(value, lambda key: custom.get(key, _INVALID))
    if substituted is _INVALID or not isinstance(substituted, str) or not substituted.strip():
        raise _Invalid("flex value is invalid")
    return " ".join(substituted.strip().lower().split())


def _choice(value: str, default: str, allowed: frozenset[str], name: str) -> str:
    if value == "inherit":
        raise _Invalid(f"{name} inherit is unsupported")
    if value in {"initial", "unset", "revert"}:
        return default
    if value not in allowed:
        raise _Invalid(f"{name} is invalid")
    return value


def _flex_flow(value: str) -> tuple[str, str]:
    if value in {"initial", "unset", "revert"}:
        return "row", "nowrap"
    if value == "inherit":
        raise _Invalid("flex-flow inherit is unsupported")
    direction = "row"
    wrap = "nowrap"
    parts = value.split(" ")
    if not parts or len(parts) > 2:
        raise _Invalid("flex-flow is invalid")
    for part in parts:
        if part in _FLEX_DIRECTIONS:
            direction = part
        elif part in _FLEX_WRAPS:
            wrap = part
        else:
            raise _Invalid("flex-flow is invalid")
    return direction, wrap


def _parse_flex(value: str) -> tuple[float, float, object]:
    if value in {"initial", "unset", "revert"}:
        return 0.0, 1.0, "auto"
    if value == "inherit":
        raise _Invalid("flex inherit is unsupported")
    if value == "none":
        return 0.0, 0.0, "auto"
    if value == "auto":
        return 1.0, 1.0, "auto"
    parts = value.split(" ")
    if not parts or len(parts) > 3:
        raise _Invalid("flex is invalid")
    grow = None
    shrink = None
    basis = None
    for part in parts:
        if _basis_token(part):
            if basis is not None:
                raise _Invalid("flex is invalid")
            basis = _flex_basis(part)
            continue
        number = _flex_factor(part, 0.0)
        if grow is None:
            grow = number
        elif shrink is None:
            shrink = number
        else:
            raise _Invalid("flex is invalid")
    return (1.0 if grow is None else grow, 1.0 if shrink is None else shrink, 0 if basis is None else basis)


def _basis_token(part: str) -> bool:
    if part in {"auto", "content", "min-content", "max-content", "fit-content"}:
        return True
    if part.endswith(("px", "%")):
        return True
    return part.startswith(("calc(", "min(", "max(", "clamp("))


def _flex_basis(value: str) -> object:
    if value in {"initial", "unset", "revert", "auto"}:
        return "auto"
    if value == "inherit":
        raise _Invalid("flex inherit is unsupported")
    if value == "0":
        return 0
    if value.endswith("px"):
        return _px(float(value[:-2]), "flex-basis")
    if value.endswith("%") or value in {"content", "min-content", "max-content", "fit-content"}:
        return value
    if value.startswith(("calc(", "min(", "max(", "clamp(")):
        return value
    raise _Invalid("flex-basis is unsupported")


def _flex_factor(value: str, default: float) -> float:
    if value in {"initial", "unset", "revert"}:
        return default
    if value == "inherit":
        raise _Invalid("flex inherit is unsupported")
    try:
        number = float(value)
    except ValueError as exc:
        raise _Invalid("flex factor is invalid") from exc
    if number < 0 or number != number or number in {float("inf"), float("-inf")}:
        raise _Invalid("flex factor is invalid")
    return number


def _main_size(raw: str | None, default: str) -> object:
    if raw is None:
        return default
    text = " ".join(raw.strip().lower().split())
    if text in {"initial", "unset", "revert"}:
        return default
    if text == "inherit":
        raise _Invalid("flex inherit is unsupported")
    if text in {"auto", "none", "min-content", "max-content", "content", "fit-content"}:
        return text
    if text == "0":
        return 0
    if text.endswith("px"):
        return _px(float(text[:-2]), "flex length")
    if text.endswith("%") or text.startswith(("calc(", "min(", "max(", "clamp(")):
        return text
    raise _Invalid("flex length is unsupported")


def _line_limit(value: object) -> object:
    if isinstance(value, bool):
        raise _Invalid("flex length is unsupported")
    if isinstance(value, (int, float)) or value in {"auto", "none"}:
        return value
    raise _Invalid("flex length is unsupported")


def _text_main(text: str, font_size: int) -> int:
    return sum(_advance_of(ch, font_size) for ch in text)


def _used_cross(raw: str | None, content: int, name: str) -> tuple[object, int]:
    if raw is None:
        return "auto", content
    text = " ".join(raw.strip().lower().split())
    if text in {"auto", "initial", "unset", "revert"}:
        return "auto", content
    if text == "inherit":
        raise _Invalid("flex inherit is unsupported")
    if text == "0":
        return 0, 0
    if text.endswith("px"):
        used = _px(float(text[:-2]), name)
        return used, used
    raise _Invalid(f"flex item {name} is unsupported")


def _flex_number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _Invalid(f"{name} is invalid")
    return float(value)


def _wrap_minimum(value: object, content: int) -> float:
    if value == "auto":
        return float(content)
    return _flex_number(value, "flex minimum")


def _wrap_maximum(value: object) -> object:
    if value == "none":
        return "none"
    return _flex_number(value, "flex maximum")


def _margin_token(
    value: str,
    name: str,
    *,
    unsupported: str = "flex item margin is unsupported",
) -> tuple[bool, int]:
    token = " ".join(value.strip().lower().split())
    if token in _ZERO_EDGE or token in {"0", "0px"}:
        return False, 0
    if token == "auto":
        return True, 0
    if len(token) > 2 and token.endswith("px"):
        return False, _px(float(token[:-2]), name)
    raise _Invalid(unsupported)


def _margin_shorthand(
    value: str,
    *,
    unsupported: str = "flex item margin is unsupported",
) -> dict[str, tuple[bool, int]]:
    token = " ".join(value.strip().lower().split())
    if token in {"initial", "unset", "revert"}:
        return {side: (False, 0) for side in ("top", "right", "bottom", "left")}
    parts = token.split(" ")

    def one(part: str) -> tuple[bool, int]:
        return _margin_token(part, "margin", unsupported=unsupported)

    if len(parts) == 1:
        side = one(parts[0])
        return {name: side for name in ("top", "right", "bottom", "left")}
    if len(parts) == 2:
        block = one(parts[0])
        inline = one(parts[1])
        return {"top": block, "right": inline, "bottom": block, "left": inline}
    if len(parts) == 3:
        return {
            "top": one(parts[0]),
            "right": one(parts[1]),
            "bottom": one(parts[2]),
            "left": one(parts[1]),
        }
    if len(parts) == 4:
        return {
            "top": one(parts[0]),
            "right": one(parts[1]),
            "bottom": one(parts[2]),
            "left": one(parts[3]),
        }
    raise _Invalid(unsupported)


def _flex_margins(box: _Box) -> dict[str, tuple[bool, int]]:
    sides = {side: (False, 0) for side in ("top", "right", "bottom", "left")}
    for prop, value in box.declarations:
        if prop == "margin":
            sides.update(_margin_shorthand(value))
        elif prop in {"margin-top", "margin-right", "margin-bottom", "margin-left"}:
            sides[prop.split("-", 1)[1]] = _margin_token(value, prop)
    return sides


def _main_margin_sum(margins: dict[str, tuple[bool, int]], *, column: bool) -> int:
    pair = ("top", "bottom") if column else ("left", "right")
    total = 0
    for side in pair:
        automatic, length = margins[side]
        if not automatic:
            total += length
    return total


def _container_align(spec: dict[str, object], *, column: bool) -> str:
    align = str(spec.get("align", "normal"))
    if column and align == "baseline":
        return "flex-start"
    return align


def _used_item_align(item_align: str, container_align: str, *, column: bool) -> str:
    align = container_align if item_align == "auto" else item_align
    if align == "normal":
        align = "stretch"
    if column and align == "baseline":
        align = "flex-start"
    return align


def _item_baseline(row: dict[str, object], *, column: bool, align: str) -> int | None:
    if align != "baseline":
        return None
    margins = row["margins"]
    if not isinstance(margins, dict):
        raise _Invalid("flex item margin is unsupported")
    top_auto, top = margins["top"]
    bottom_auto, bottom = margins["bottom"]
    if top_auto or bottom_auto:
        return None
    item = row["item"]
    if not isinstance(item, _Box):
        raise _Invalid("flex item is missing")
    text = item.inline_text or ""
    if text.strip() or item.white_space not in _COLLAPSED_EMPTY:
        used = _used_line_height(item.line_height, item.font_size)
        return top + _strut_metrics(item.font_size, used)[1]
    content = _px(row["hypothetical"], "flex cross") if row["cross"] == "auto" else _px(row["cross"], "flex cross")
    return top + content + bottom


def _margin_side(pair: tuple[bool, int]) -> object:
    automatic, length = pair
    return "auto" if automatic else length


def _flex_entry(
    row: dict[str, object],
    inner: object,
    *,
    column: bool,
    container_align: str,
    reverse: bool = False,
) -> dict[str, object]:
    margins = row["margins"]
    if not isinstance(margins, dict):
        raise _Invalid("flex item margin is unsupported")
    item = row["item"]
    if not isinstance(item, _Box):
        raise _Invalid("flex item is missing")
    if column:
        main_pair = (margins["top"], margins["bottom"])
        cross_pair = (margins["left"], margins["right"])
    else:
        main_pair = (margins["left"], margins["right"])
        cross_pair = (margins["top"], margins["bottom"])
    if reverse:
        main_pair = (main_pair[1], main_pair[0])
    align = _used_item_align(str(row["align"]), container_align, column=column)
    entry: dict[str, object] = {
        "id": item.id,
        "main": inner,
        "cross": row["cross"],
        "align_self": align,
        "margin_main_start": _margin_side(main_pair[0]),
        "margin_main_end": _margin_side(main_pair[1]),
        "margin_cross_start": _margin_side(cross_pair[0]),
        "margin_cross_end": _margin_side(cross_pair[1]),
    }
    if row["cross"] == "auto":
        entry["content"] = row["hypothetical"]
    baseline = _item_baseline(row, column=column, align=align)
    if baseline is not None:
        entry["baseline"] = baseline
    return entry


def _line_cross_size(entries: list[dict[str, object]], align: str) -> int:
    sized = flex_line_cross_size(entries, align_items=align)
    if sized.get("outcome") != "resolved":
        raise _Invalid(str(sized.get("reason") or "flex cross failed"))
    return _px(sized.get("cross_size"), "flex cross")


def _commit_flex_item(
    item: _Box,
    entry: dict[str, object],
    *,
    column: bool,
    content_x: int,
    origin: int,
    container_main: int,
    reverse: bool,
) -> None:
    inner = _px(entry.get("main_size"), "flex main")
    margin_box = _px(entry.get("main"), "flex main")
    main_start = _px(entry.get("margin_main_start", 0), "flex margin")
    main_end = _px(entry.get("margin_main_end", 0), "flex margin")
    if reverse:
        outer = main_start + inner + main_end
        margin_box = container_main - margin_box - outer
        border_main = margin_box + main_end
        used_main_start, used_main_end = main_end, main_start
    else:
        border_main = margin_box + main_start
        used_main_start, used_main_end = main_start, main_end
    cross_size = _px(entry.get("cross_size"), "flex cross")
    cross_start = _px(entry.get("margin_cross_start", 0), "flex margin")
    cross_end = _px(entry.get("margin_cross_end", 0), "flex margin")
    border_cross = _px(entry.get("cross"), "flex cross") + cross_start
    if column:
        item.content_width = cross_size
        item.content_height = inner
        item.x = content_x + border_cross
        item.anchor_y = origin + border_main
        item.margin_left = cross_start
        item.margin_right = cross_end
        solved_margins = {
            "margin_top": used_main_start,
            "margin_bottom": used_main_end,
            "margin_left": cross_start,
            "margin_right": cross_end,
        }
    else:
        item.content_width = inner
        item.content_height = cross_size
        item.x = content_x + border_main
        item.anchor_y = origin + border_cross
        item.margin_left = used_main_start
        item.margin_right = used_main_end
        solved_margins = {
            "margin_left": used_main_start,
            "margin_right": used_main_end,
            "margin_top": cross_start,
            "margin_bottom": cross_end,
        }
    item.border_width = item.content_width
    item.border_height = item.content_height
    item.solved = dict(_ZERO_FLEX_EDGES)
    if isinstance(item.solved, dict):
        item.solved.update(solved_margins)
    if not column and item.inline_text:
        item.lines = _plain_lines(item, item.content_width, item.direction)


def _line_cross(row: dict[str, object]) -> int:
    if row["cross"] == "auto":
        return _px(row["hypothetical"], "flex height")
    return _px(row["cross"], "flex height")


def _place_wrapped_flex_lines(
    box: _Box,
    content_x: int,
    spec: dict[str, object],
    rows: list[dict[str, object]],
    *,
    column: bool = False,
) -> None:
    by_row = {row["item"].id: row for row in rows}
    reverse = str(spec.get("direction") or "") in {"row-reverse", "column-reverse"}
    main_size = box.definite_height if column else box.content_width
    if main_size is None:
        raise _Invalid("flex column wrap is unsupported")
    main_gap, cross_gap = _axis_gaps(spec, column=column)
    broken = wrap_flex_lines(
        main_size,
        [
            {
                "id": row["item"].id,
                "order": _stored_order(row["item"].flex),
                "base": row["base"],
                "grow": row["grow"],
                "shrink": row["shrink"],
                "minimum": _wrap_minimum(row["minimum"], _px(row["content"], "flex content")),
                "maximum": _wrap_maximum(row["maximum"]),
                "margin": _main_margin_sum(row["margins"], column=column),
            }
            for row in rows
        ],
        gap=main_gap,
        wrap="wrap",
        direction="column" if column else "row",
    )
    lines = broken.get("lines")
    if broken.get("outcome") != "wrapped" or not isinstance(lines, list):
        raise _Invalid(str(broken.get("reason") or "flex wrap failed"))
    grouped: list[list[dict[str, object]]] = []
    crosses: list[int] = []
    for line in lines:
        if not isinstance(line, dict):
            raise _Invalid("flex wrap failed")
        ids = line.get("ids")
        mains = line.get("main_sizes")
        if not isinstance(ids, list) or not isinstance(mains, list) or len(ids) != len(mains) or not ids:
            raise _Invalid("flex wrap failed")
        entries: list[dict[str, object]] = []
        height = 0
        container_align = str(spec.get("align", "normal"))
        for ident, inner in zip(ids, mains, strict=True):
            row = by_row.get(str(ident))
            if row is None:
                raise _Invalid("flex wrap failed")
            entries.append(
                _flex_entry(row, inner, column=column, container_align=container_align, reverse=reverse)
            )
            height = max(height, _line_cross(row))
        grouped.append(entries)
        if column:
            crosses.append(height)
        else:
            crosses.append(_line_cross_size(entries, _container_align(spec, column=False)))
    if not column and box.definite_height is None:
        box.definite_height = _gapped_span(crosses, cross_gap)
    cross_size = box.content_width if column else box.definite_height
    placed = place_flex_alignment(
        main_size,
        cross_size,
        grouped,
        justify_content=spec.get("justify", "normal"),
        align_items=_container_align(spec, column=column),
        align_content=spec.get("align_content", "normal"),
        wrap=str(spec.get("wrap") or "wrap"),
        main_gap=main_gap,
        cross_gap=cross_gap,
    )
    placed_lines = placed.get("lines")
    if placed.get("outcome") != "placed" or not isinstance(placed_lines, list):
        raise _Invalid(str(placed.get("reason") or "flex alignment failed"))
    located: dict[str, dict[str, object]] = {}
    for line in placed_lines:
        if not isinstance(line, dict) or not isinstance(line.get("items"), list):
            raise _Invalid("flex alignment failed")
        for entry in line["items"]:
            if isinstance(entry, dict) and entry.get("id") is not None:
                located[str(entry["id"])] = entry
    origin = _px(box.solved.get("border_top"), "border-top") + _px(box.solved.get("padding_top"), "padding-top")
    for row in rows:
        item = row["item"]
        entry = located.get(item.id)
        if entry is None:
            raise _Invalid("flex alignment failed")
        _commit_flex_item(
            item,
            entry,
            column=column,
            content_x=content_x,
            origin=origin,
            container_main=main_size,
            reverse=reverse,
        )
    box.anchor_laid = True


_ZERO_FLEX_EDGES = {
    "margin_top": 0,
    "margin_right": 0,
    "margin_bottom": 0,
    "margin_left": 0,
    "padding_top": 0,
    "padding_right": 0,
    "padding_bottom": 0,
    "padding_left": 0,
    "border_top": 0,
    "border_right": 0,
    "border_bottom": 0,
    "border_left": 0,
}


def _place_flex_row(box: _Box, content_x: int) -> None:
    if box.writing_mode != "horizontal-tb" or box.direction != "ltr":
        raise _Invalid("flex writing mode is unsupported")
    spec = box.flex or {"justify": "normal", "align": "normal", "wrap": "nowrap", "direction": "row"}
    direction = str(spec.get("direction") or "row")
    column = direction in {"column", "column-reverse"}
    rows: list[dict[str, object]] = []
    for item in box.children:
        flex = item.flex or {"grow": 0.0, "shrink": 1.0, "basis": "auto", "align": "auto"}
        text = item.inline_text or ""
        text_width = _text_main(text, item.font_size)
        text_height = (
            _strut_height(item.font_size, _used_line_height(item.line_height, item.font_size)) if text else 0
        )
        if column:
            content_main = text_height
            specified = _main_size(_box_decl(item, "height"), "auto")
            cross, hypothetical = _used_cross(_box_decl(item, "width"), text_width, "width")
            minimum = _line_limit(_main_size(_box_decl(item, "min-height"), "auto"))
            maximum = _line_limit(_main_size(_box_decl(item, "max-height"), "none"))
            available: object = box.definite_height if box.definite_height is not None else "indefinite"
        else:
            content_main = text_width
            specified = _main_size(_box_decl(item, "width"), "auto")
            cross, hypothetical = _used_cross(_box_decl(item, "height"), text_height, "height")
            minimum = _line_limit(_main_size(_box_decl(item, "min-width"), "auto"))
            maximum = _line_limit(_main_size(_box_decl(item, "max-width"), "none"))
            available = box.content_width
        basis = resolve_flex_base(
            available,
            flex_basis=flex["basis"],
            main_size=specified,
            minimum="auto",
            maximum="none",
            min_content=content_main,
            max_content=content_main,
        )
        if basis.get("outcome") != "resolved":
            raise _Invalid(str(basis.get("reason") or "flex base failed"))
        if not column and text and cross == "auto":
            preview = _plain_lines(
                item,
                _px(basis["hypothetical_inner"], "flex width"),
                item.direction,
            )
            if preview:
                hypothetical = sum(line.height for line in preview)
        rows.append(
            {
                "item": item,
                "base": basis["inner_base"],
                "hypothetical_main": basis["hypothetical_inner"],
                "grow": flex["grow"],
                "shrink": flex["shrink"],
                "minimum": minimum,
                "maximum": maximum,
                "content": content_main,
                "specified": specified if isinstance(specified, (int, float)) and not isinstance(specified, bool) else "auto",
                "cross": cross,
                "hypothetical": hypothetical,
                "align": flex["align"],
                "margins": _flex_margins(item),
            }
        )
    rows.sort(key=lambda row: _stored_order(row["item"].flex))
    if not rows:
        if box.definite_height is None:
            box.definite_height = 0
        box.anchor_laid = True
        return
    if str(spec.get("wrap") or "nowrap") != "nowrap" and (not column or box.definite_height is not None):
        _place_wrapped_flex_lines(box, content_x, spec, rows, column=column)
        return
    main_gap, cross_gap = _axis_gaps(spec, column=column)
    container_align = str(spec.get("align", "normal"))
    if column:
        container_main = box.definite_height
        if container_main is None:
            container_main = _gapped_span(
                [
                    _px(row["hypothetical_main"], "flex height")
                    + _main_margin_sum(row["margins"], column=True)
                    for row in rows
                ],
                main_gap,
            )
            box.definite_height = container_main
        container_cross = box.content_width
    else:
        container_main = box.content_width
        container_cross = box.definite_height
    line = resolve_flex_line(
        container_main,
        [
            {
                "base": row["base"],
                "grow": row["grow"],
                "shrink": row["shrink"],
                "minimum": row["minimum"],
                "maximum": row["maximum"],
                "margin": _main_margin_sum(row["margins"], column=column),
                "content": row["content"],
                "specified": row["specified"],
            }
            for row in rows
        ],
        gap=main_gap,
    )
    if line.get("outcome") != "resolved" or not isinstance(line.get("main_sizes"), list):
        raise _Invalid(str(line.get("reason") or "flex line failed"))
    sizes = line["main_sizes"]
    if len(sizes) != len(rows):
        raise _Invalid("flex line failed")
    reverse = direction in {"row-reverse", "column-reverse"}
    entries = [
        _flex_entry(row, inner, column=column, container_align=container_align, reverse=reverse)
        for row, inner in zip(rows, sizes, strict=True)
    ]
    if not column and container_cross is None:
        container_cross = _line_cross_size(entries, _container_align(spec, column=False))
        box.definite_height = container_cross
    placed = place_flex_alignment(
        container_main,
        container_cross,
        [entries],
        justify_content=spec.get("justify", "normal"),
        align_items=_container_align(spec, column=column),
        align_content=spec.get("align_content", "normal"),
        wrap="nowrap",
        main_gap=main_gap,
        cross_gap=cross_gap,
    )
    if placed.get("outcome") != "placed" or not isinstance(placed.get("lines"), list):
        raise _Invalid(str(placed.get("reason") or "flex alignment failed"))
    lines = placed["lines"]
    if len(lines) != 1 or not isinstance(lines[0], dict) or not isinstance(lines[0].get("items"), list):
        raise _Invalid("flex alignment failed")
    by_id = {str(entry.get("id")): entry for entry in lines[0]["items"] if isinstance(entry, dict)}
    origin = _px(box.solved.get("border_top"), "border-top") + _px(box.solved.get("padding_top"), "padding-top")
    for row in rows:
        item = row["item"]
        entry = by_id.get(item.id)
        if entry is None:
            raise _Invalid("flex alignment failed")
        _commit_flex_item(
            item,
            entry,
            column=column,
            content_x=content_x,
            origin=origin,
            container_main=container_main,
            reverse=reverse,
        )
    box.anchor_laid = True


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


_GRID_FLOWS = frozenset({"row", "column", "dense", "row dense", "column dense"})
_GRID_ALIGN = frozenset({"normal", "stretch", "start"})
_GRID_ITEM_ALIGN = frozenset(
    {
        "normal",
        "stretch",
        "start",
        "end",
        "center",
        "self-start",
        "self-end",
        "flex-start",
        "flex-end",
    }
)
_GRID_JUSTIFY_ITEMS = _GRID_ITEM_ALIGN | {"left", "right"}
_GRID_JUSTIFY_SELF = _GRID_JUSTIFY_ITEMS | {"auto"}
_GRID_ALIGN_SELF = _GRID_ITEM_ALIGN | {"auto"}
_GRID_ITEM_PROPS = frozenset(
    {
        "grid-column",
        "grid-row",
        "grid-column-start",
        "grid-column-end",
        "grid-row-start",
        "grid-row-end",
        "grid-area",
        "order",
        "justify-self",
        "align-self",
    }
)
_GRID_LONGHANDS = frozenset(
    {
        "grid-column-start",
        "grid-column-end",
        "grid-row-start",
        "grid-row-end",
        "grid-area",
    }
)


def _walk_grid(
    tree,
    element,
    inherited: dict[str, str],
    fonts: dict[str, str],
    styles,
    declarations,
    ids: set[str],
    counter: list[int],
    host: _Box,
) -> tuple[list[_Box], list[_Box], list[_Box], list[_Box]]:
    host.grid = _grid_container(tree, element, styles, declarations)
    if host.writing_mode != "horizontal-tb" or host.direction != "ltr":
        raise _Invalid("grid writing mode is unsupported")
    _reject_grid_text(getattr(element, "text", None))
    items: list[_Box] = []
    for child in tree.children.get(element, []):
        _reject_grid_text(getattr(child, "tail", None))
        if not _local_name(child) or _local_name(child) in _SKIP_TAGS:
            continue
        item = _make_box(
            tree,
            child,
            inherited,
            fonts,
            host.direction,
            styles,
            declarations,
            ids,
            counter,
            root=False,
        )
        if item.display == "none":
            continue
        if item.display in {"table", "table-row", "table-cell"}:
            raise _Invalid("table formatting in grid is unsupported")
        if item.position != "static" or item.float_side != "none":
            raise _Invalid("grid item is outside the grid")
        if item.writing_mode != "horizontal-tb" or item.direction != "ltr":
            raise _Invalid("grid writing mode is unsupported")
        if _flex_item_elements(tree, child):
            _adopt_grid_item_blocks(tree, child, item, styles, declarations, ids, counter)
        else:
            item.inline_text = child.text or ""
        _reject_grid_edges(item)
        item.grid = _grid_item(tree, child, styles, declarations, item)
        items.append(item)
    return items, [], items, []


def _grid_text(text: object) -> bool:
    return isinstance(text, str) and bool(text.strip())


def _reject_grid_text(text: object) -> None:
    if _grid_text(text):
        raise _Invalid("grid text is unsupported")


_GRID_EDGE = "grid item edge is unsupported"
_GRID_SIDES = ("top", "right", "bottom", "left")
_GRID_BORDER_STYLES = frozenset(
    {"none", "hidden", "dotted", "dashed", "solid", "double", "groove", "ridge", "inset", "outset"}
)
_GRID_LOGICAL_CHROME = frozenset(
    {
        "padding-inline",
        "padding-inline-start",
        "padding-inline-end",
        "padding-block",
        "padding-block-start",
        "padding-block-end",
        "border-inline-width",
        "border-inline-start-width",
        "border-inline-end-width",
        "border-block-width",
        "border-block-start-width",
        "border-block-end-width",
        "border-inline-style",
        "border-inline-start-style",
        "border-inline-end-style",
        "border-block-style",
        "border-block-start-style",
        "border-block-end-style",
    }
)


def _grid_quad(value: str, parse) -> dict[str, object] | None:
    token = " ".join(value.strip().lower().split())
    if token in {"initial", "unset", "revert"}:
        return None
    parts = token.split(" ")
    if len(parts) == 1:
        chosen = (parts[0], parts[0], parts[0], parts[0])
    elif len(parts) == 2:
        chosen = (parts[0], parts[1], parts[0], parts[1])
    elif len(parts) == 3:
        chosen = (parts[0], parts[1], parts[2], parts[1])
    elif len(parts) == 4:
        chosen = (parts[0], parts[1], parts[2], parts[3])
    else:
        raise _Invalid(_GRID_EDGE)
    return {side: parse(part) for side, part in zip(_GRID_SIDES, chosen, strict=True)}


def _grid_padding_length(value: str) -> int:
    token = " ".join(value.strip().lower().split())
    if token in _ZERO_EDGE:
        return 0
    if len(token) > 2 and token.endswith("px"):
        length = _px(float(token[:-2]), "padding")
        if length < 0:
            raise _Invalid(_GRID_EDGE)
        return length
    raise _Invalid(_GRID_EDGE)


def _grid_border_width_token(value: str) -> object:
    token = " ".join(value.strip().lower().split())
    if token in {"initial", "unset", "revert", "medium"}:
        return "medium"
    if token in {"thin", "thick"}:
        return token
    if token in _ZERO_EDGE:
        return 0
    if len(token) > 2 and token.endswith("px"):
        length = _px(float(token[:-2]), "border-width")
        if length < 0:
            raise _Invalid(_GRID_EDGE)
        return length
    raise _Invalid(_GRID_EDGE)


def _grid_border_style_token(value: str) -> str:
    token = " ".join(value.strip().lower().split())
    if token in {"initial", "unset", "revert"}:
        return "none"
    if token not in _GRID_BORDER_STYLES:
        raise _Invalid(_GRID_EDGE)
    return token


def _grid_chrome(box: _Box) -> dict[str, int]:
    """Used content-box padding and border. A hidden style has no used width."""

    padding = {side: 0 for side in _GRID_SIDES}
    widths: dict[str, object] = {side: "medium" for side in _GRID_SIDES}
    styles = {side: "none" for side in _GRID_SIDES}
    for prop, raw in box.declarations:
        if prop == "padding":
            chosen = _grid_quad(raw, _grid_padding_length)
            padding = {side: 0 for side in _GRID_SIDES} if chosen is None else {**padding, **chosen}
        elif prop in {"padding-top", "padding-right", "padding-bottom", "padding-left"}:
            padding[prop.split("-", 1)[1]] = _grid_padding_length(raw)
        elif prop == "border-width":
            chosen = _grid_quad(raw, _grid_border_width_token)
            widths = {side: "medium" for side in _GRID_SIDES} if chosen is None else {**widths, **chosen}
        elif prop in {"border-top-width", "border-right-width", "border-bottom-width", "border-left-width"}:
            widths[prop.split("-")[1]] = _grid_border_width_token(raw)
        elif prop == "border-style":
            chosen = _grid_quad(raw, _grid_border_style_token)
            styles = {side: "none" for side in _GRID_SIDES} if chosen is None else {**styles, **chosen}
        elif prop in {"border-top-style", "border-right-style", "border-bottom-style", "border-left-style"}:
            styles[prop.split("-")[1]] = _grid_border_style_token(raw)
    used = {f"padding_{side}": padding[side] for side in _GRID_SIDES}
    for side in _GRID_SIDES:
        width = widths[side]
        if styles[side] in {"none", "hidden"}:
            used[f"border_{side}"] = 0
        elif width in {None, "medium"}:
            used[f"border_{side}"] = 3
        elif width == "thin":
            used[f"border_{side}"] = 1
        elif width == "thick":
            used[f"border_{side}"] = 5
        else:
            used[f"border_{side}"] = _px(width, "border-width")
    return used


def _install_grid_chrome(item: _Box) -> None:
    solved = dict(_ZERO_FLEX_EDGES)
    solved.update(_grid_chrome(item))
    item.solved = solved


def _grid_border_content(border: int, chrome: int) -> int:
    content = border - chrome
    if content < 0:
        raise _Invalid(_GRID_EDGE)
    return content


def _reject_grid_edges(box: _Box) -> None:
    sizing = _box_decl(box, "box-sizing")
    if sizing not in {None, "content-box", "initial", "unset", "revert"}:
        raise _Invalid("grid box-sizing is unsupported")
    for prop, raw in box.declarations:
        if prop in _GRID_LOGICAL_CHROME and raw.strip().lower() not in _ZERO_EDGE | {"none"}:
            raise _Invalid(_GRID_EDGE)
    _grid_chrome(box)
    limits = {
        "min-width": {"auto", "0", "0px", "initial", "unset", "revert"},
        "min-height": {"auto", "0", "0px", "initial", "unset", "revert"},
        "max-width": {"none", "initial", "unset", "revert"},
        "max-height": {"none", "initial", "unset", "revert"},
    }
    for name, allowed in limits.items():
        raw = _box_decl(box, name)
        if raw is None or raw.strip().lower() in allowed:
            continue
        raise _Invalid("grid item limit is unsupported")


def _grid_container(tree, element, styles, declarations) -> dict[str, object]:
    custom = styles.get(element, ({}, ""))[0]
    columns: list[dict[str, object]] = []
    rows: list[dict[str, object]] = []
    areas: list[str] | None = None
    column_lines: list[list[str]] | None = None
    row_lines: list[list[str]] | None = None
    auto_rows: int | None = None
    auto_columns: int | None = None
    row_gap = 0
    column_gap = 0
    flow = "row"
    justify = "normal"
    justify_items = "normal"
    align_items = "normal"
    tracked = {
        "grid-template-columns",
        "grid-template-rows",
        "grid-template",
        "grid-template-areas",
        "grid",
        "grid-auto-rows",
        "grid-auto-columns",
        "grid-auto-flow",
        "justify-items",
        "align-items",
        "justify-content",
        "align-content",
        "gap",
        "column-gap",
        "row-gap",
    }
    for _order, prop, raw in _winners(tree, element, declarations):
        if prop not in tracked:
            continue
        value = _grid_author(raw, custom)
        if prop == "grid-template-columns":
            columns, column_lines = _grid_named_column_tracks(value)
        elif prop == "grid-template-rows":
            rows, row_lines = _grid_named_row_tracks(value)
        elif prop == "grid-template-areas":
            areas = _grid_area_rows(value)
        elif prop in {"grid-template", "grid"}:
            if value not in {"none", "initial", "unset", "revert"}:
                raise _Invalid("grid template is unsupported")
        elif prop == "grid-auto-rows":
            auto_rows = _grid_auto_track(value)
        elif prop == "grid-auto-columns":
            auto_columns = _grid_auto_track(value)
        elif prop == "grid-auto-flow":
            flow = _choice(value, "row", _GRID_FLOWS, "grid-auto-flow")
        elif prop == "justify-items":
            justify_items = _choice(value, "normal", _GRID_JUSTIFY_ITEMS, prop)
        elif prop == "align-items":
            align_items = _choice(value, "normal", _GRID_ITEM_ALIGN, prop)
        elif prop == "justify-content":
            justify = _choice(value, "normal", _GRID_ALIGN, prop)
        elif prop == "align-content":
            _choice(value, "normal", _GRID_ALIGN, prop)
        elif prop == "gap":
            row_gap, column_gap = _grid_gap_pair(value)
        elif prop == "row-gap":
            row_gap = _grid_gap_length(value)
        elif prop == "column-gap":
            column_gap = _grid_gap_length(value)
    if not columns:
        raise _Invalid("grid template is unsupported")
    return {
        "columns": columns,
        "rows": rows,
        "auto_rows": auto_rows,
        "auto_columns": auto_columns,
        "row_gap": row_gap,
        "column_gap": column_gap,
        "flow": flow,
        "justify": justify,
        "justify_items": justify_items,
        "align_items": align_items,
        "areas": areas,
        "column_lines": column_lines,
        "row_lines": row_lines,
    }


def _grid_item(tree, element, styles, declarations, box: _Box) -> dict[str, object]:
    custom = styles.get(element, ({}, ""))[0]
    column = ("auto", "auto")
    row = ("auto", "auto")
    area = ""
    column_set = False
    row_set = False
    item_order = 0
    justify_self = "auto"
    align_self = "auto"
    for _order, prop, raw in _winners(tree, element, declarations):
        if prop not in _GRID_ITEM_PROPS:
            continue
        value = _grid_author(raw, custom)
        if prop == "grid-area":
            area = _grid_area_name(value)
            continue
        if prop in _GRID_LONGHANDS:
            if value not in {"auto", "initial", "unset", "revert"}:
                raise _Invalid("grid line is unsupported")
            continue
        if prop == "order":
            item_order = _css_order(value)
            continue
        if prop == "justify-self":
            justify_self = _choice(value, "auto", _GRID_JUSTIFY_SELF, prop)
            continue
        if prop == "align-self":
            align_self = _choice(value, "auto", _GRID_ALIGN_SELF, prop)
            continue
        if prop == "grid-column":
            column = _grid_placement(value)
            column_set = True
        elif prop == "grid-row":
            row = _grid_placement(value)
            row_set = True
    return {
        "column_start": column[0],
        "column_end": column[1],
        "row_start": row[0],
        "row_end": row[1],
        "area": area,
        "column_set": column_set,
        "row_set": row_set,
        "width": _grid_length(_box_decl(box, "width")),
        "height": _grid_length(_box_decl(box, "height")),
        "order": item_order,
        "justify_self": justify_self,
        "align_self": align_self,
        "margins": _grid_margin_sides(tree, element, styles, declarations),
    }


def _grid_author(value: str, custom: dict) -> str:
    if _wide_keyword(value) is not None:
        return value.strip().lower()
    substituted = _substitute(value, lambda key: custom.get(key, _INVALID))
    if substituted is _INVALID or not isinstance(substituted, str) or not substituted.strip():
        raise _Invalid("grid value is invalid")
    return " ".join(substituted.strip().lower().split())


def _grid_placement(value: str) -> tuple[object, object]:
    if value in {"auto", "initial", "unset", "revert"}:
        return "auto", "auto"
    if value == "inherit":
        raise _Invalid("grid line inherit is unsupported")
    if value.count("/") > 1:
        raise _Invalid("grid line is unsupported")
    if "/" not in value:
        side = _grid_side(value)
        if isinstance(side, str) and side.startswith("span "):
            return "auto", side
        return side, "auto"
    left, right = (part.strip() for part in value.split("/", 1))
    return _grid_side(left), _grid_side(right)


def _grid_side(token: str) -> object:
    if token == "auto":
        return "auto"
    if token.startswith("span "):
        count = token[5:]
        if not count.isdigit() or count.startswith("0"):
            raise _Invalid("grid line is unsupported")
        return f"span {int(count)}"
    sign = -1 if token.startswith("-") else 1
    digits = token[1:] if sign < 0 else token
    if digits.isdigit() and not digits.startswith("0"):
        return sign * int(digits)
    if sign > 0 and _grid_ident(token):
        return token
    raise _Invalid("grid line is unsupported")


def _grid_track_defs(value: str) -> list[dict[str, object]]:
    if value in {"initial", "unset", "revert", "none"}:
        return []
    if value == "inherit":
        raise _Invalid("grid template inherit is unsupported")
    tracks: list[dict[str, object]] = []
    for kind, token in _grid_track_atoms(value):
        if kind != "track":
            raise _Invalid("grid track is unsupported")
        tracks.append(_parse_track_token(token))
    return tracks


def _grid_track_atoms(value: str) -> list[tuple[str, str]]:
    """Split a track list without cutting a ``minmax()`` on its spaces."""

    atoms: list[tuple[str, str]] = []
    index = 0
    length = len(value)
    while index < length:
        while index < length and value[index].isspace():
            index += 1
        if index >= length:
            break
        if value[index] == "[":
            end = value.find("]", index + 1)
            if end < 0:
                raise _Invalid("grid line is unsupported")
            atoms.append(("names", value[index + 1 : end]))
            index = end + 1
            continue
        if value[index] == "]":
            raise _Invalid("grid line is unsupported")
        if value.startswith("minmax(", index):
            end = _matching_paren(value, index + 6)
            atoms.append(("track", value[index : end + 1]))
            index = end + 1
            continue
        start = index
        while index < length and not value[index].isspace() and value[index] not in "[]":
            index += 1
        atoms.append(("track", value[start:index]))
    return atoms


def _matching_paren(value: str, open_index: int) -> int:
    if open_index >= len(value) or value[open_index] != "(":
        raise _Invalid("grid track is unsupported")
    depth = 0
    for index in range(open_index, len(value)):
        char = value[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index
    raise _Invalid("grid track is unsupported")


def _parse_track_token(token: str) -> dict[str, object]:
    if token.startswith("minmax("):
        return _minmax_track(token)
    return _plain_track(token)


def _minmax_track(token: str) -> dict[str, object]:
    if not token.endswith(")") or token.count("(") != 1 or token.count(")") != 1:
        raise _Invalid("grid track is unsupported")
    inner = token[len("minmax(") : -1].strip()
    if "(" in inner or ")" in inner:
        raise _Invalid("grid track is unsupported")
    parts = [part.strip() for part in inner.split(",")]
    if len(parts) != 2 or any(not part for part in parts):
        raise _Invalid("grid track is unsupported")
    floor_kind, floor = _minmax_bound(parts[0])
    ceiling_kind, ceiling = _minmax_bound(parts[1])
    if floor_kind == "flex":
        raise _Invalid("grid track is unsupported")
    if ceiling_kind == "flex":
        return {"flex": ceiling, "minimum": floor}
    return {"minimum": floor, "maximum": ceiling}


def _minmax_bound(token: str) -> tuple[str, float]:
    if token.endswith("fr"):
        try:
            factor = float(token[:-2])
        except ValueError as exc:
            raise _Invalid("grid track is unsupported") from exc
        if factor <= 0 or factor != factor or factor in {float("inf"), float("-inf")}:
            raise _Invalid("grid track is unsupported")
        return "flex", factor
    if token == "0" or token.endswith("px"):
        raw = "0" if token == "0" else token[:-2]
        try:
            number = float(raw)
        except ValueError as exc:
            raise _Invalid("grid track is unsupported") from exc
        length = float(_px(number, "grid track"))
        if length < 0:
            raise _Invalid("grid track is unsupported")
        return "length", length
    raise _Invalid("grid track is unsupported")


def _plain_track(part: str) -> dict[str, object]:
    if part.endswith("px") or part == "0":
        raw = "0" if part == "0" else part[:-2]
        try:
            number = float(raw)
        except ValueError as exc:
            raise _Invalid("grid track is unsupported") from exc
        return {"fixed": float(_px(number, "grid track"))}
    if part.endswith("fr"):
        try:
            factor = float(part[:-2])
        except ValueError as exc:
            raise _Invalid("grid track is unsupported") from exc
        if factor <= 0 or factor != factor or factor in {float("inf"), float("-inf")}:
            raise _Invalid("grid track is unsupported")
        return {"flex": factor, "minimum": 0}
    if part in {"auto", "min-content", "max-content"}:
        return {"breadth": part}
    raise _Invalid("grid track is unsupported")


def _grid_auto_track(value: str) -> int | None:
    if value in {"auto", "initial", "unset", "revert"}:
        return None
    if value == "inherit":
        raise _Invalid("grid auto track inherit is unsupported")
    tracks = _grid_track_defs(value)
    if len(tracks) != 1 or "fixed" not in tracks[0] or "flex" in tracks[0]:
        raise _Invalid("grid auto track is unsupported")
    return _px(tracks[0]["fixed"], "grid auto track")


def _grid_gap_pair(value: str) -> tuple[int, int]:
    if value in {"initial", "unset", "revert"}:
        return 0, 0
    if value == "inherit":
        raise _Invalid("grid gap inherit is unsupported")
    parts = value.split(" ")
    if len(parts) == 1:
        length = _grid_gap_length(parts[0])
        return length, length
    if len(parts) == 2:
        return _grid_gap_length(parts[0]), _grid_gap_length(parts[1])
    raise _Invalid("grid gap is unsupported")


def _grid_gap_length(value: str) -> int:
    if value in {"0", "0px", "normal", "initial", "unset", "revert"}:
        return 0
    if value == "inherit":
        raise _Invalid("grid gap inherit is unsupported")
    if value.endswith("px"):
        length = _px(float(value[:-2]), "grid gap")
        if length < 0:
            raise _Invalid("grid gap is unsupported")
        return length
    raise _Invalid("grid gap is unsupported")


def _grid_length(value: str | None) -> object:
    if value is None:
        return "auto"
    text = " ".join(value.strip().lower().split())
    if text in {"auto", "initial", "unset", "revert"}:
        return "auto"
    if text == "inherit":
        raise _Invalid("grid length inherit is unsupported")
    if text == "0":
        return 0
    if text.endswith("px"):
        return _px(float(text[:-2]), "grid length")
    raise _Invalid("grid length is unsupported")


def _grid_offset(sizes: list[int], index: int, gap: int) -> int:
    if index < 0 or index > len(sizes):
        raise _Invalid("grid item is outside the tracks")
    return sum(sizes[:index]) + gap * index


def _grid_span(sizes: list[int], index: int, span: int, gap: int) -> int:
    if span < 1 or index < 0 or index + span > len(sizes):
        raise _Invalid("grid item is outside the tracks")
    return sum(sizes[index : index + span]) + gap * (span - 1)


def _grid_ident(token: str) -> bool:
    if not token or token in {"auto", "span"} or token.startswith("--"):
        return False
    first = token[0]
    if first == "-":
        if len(token) < 2:
            return False
        first = token[1]
    if not (first.isalpha() or first == "_"):
        return False
    return all(char.isalnum() or char in {"_", "-"} for char in token)


def _grid_area_name(value: str) -> str:
    if value in {"auto", "initial", "unset", "revert"}:
        return ""
    if value == "inherit" or any(char.isspace() or char == "/" for char in value) or not _grid_ident(value):
        raise _Invalid("grid area is unsupported")
    return value


def _grid_area_rows(value: str) -> list[str] | None:
    if value in {"none", "initial", "unset", "revert"}:
        return None
    if value == "inherit":
        raise _Invalid("grid template inherit is unsupported")
    rows: list[str] = []
    index = 0
    length = len(value)
    while index < length:
        while index < length and value[index].isspace():
            index += 1
        if index >= length:
            break
        quote = value[index]
        if quote not in {"'", '"'}:
            raise _Invalid("grid template is unsupported")
        index += 1
        start = index
        while index < length and value[index] != quote:
            if value[index] == "\\":
                raise _Invalid("grid template is unsupported")
            index += 1
        if index >= length:
            raise _Invalid("grid template is unsupported")
        cells = " ".join(value[start:index].split())
        if not cells:
            raise _Invalid("grid template is unsupported")
        rows.append(cells)
        index += 1
    if not rows:
        raise _Invalid("grid template is unsupported")
    return rows


def _grid_named_column_tracks(value: str) -> tuple[list[dict[str, object]], list[list[str]] | None]:
    if "[" not in value and "]" not in value:
        return _grid_track_defs(value), None
    return _read_named_tracks(value)


def _grid_named_row_tracks(value: str) -> tuple[list[dict[str, object]], list[list[str]] | None]:
    if "[" not in value and "]" not in value:
        return _grid_track_defs(value), None
    return _read_named_tracks(value)


def _read_named_tracks(value: str) -> tuple[list[dict[str, object]], list[list[str]] | None]:
    lines: list[list[str]] = [[]]
    tracks: list[dict[str, object]] = []
    for kind, token in _grid_track_atoms(value):
        if kind == "names":
            for name in token.split():
                if not _grid_ident(name):
                    raise _Invalid("grid line is unsupported")
                lines[-1].append(name)
            continue
        tracks.append(_parse_track_token(token))
        lines.append([])
    if not tracks:
        raise _Invalid("grid template is unsupported")
    if not any(lines):
        return tracks, None
    return tracks, lines


def _named_grid_side(value: object) -> bool:
    return isinstance(value, str) and value != "auto" and not value.startswith("span ")


def _pad_named_lines(lines: object, tracks: int) -> list[list[str]] | None:
    if not isinstance(lines, list):
        return None
    copied: list[list[str]] = []
    for item in lines:
        if not isinstance(item, list) or any(not isinstance(name, str) for name in item):
            raise _Invalid("grid line is unsupported")
        copied.append(list(item))
    need = tracks + 1
    if len(copied) > need:
        raise _Invalid("grid line is unsupported")
    copied.extend([] for _ in range(need - len(copied)))
    return copied


def _place_grid_items(
    box: _Box,
    spec: dict[str, object],
    columns: list,
    explicit_rows: list,
) -> dict[str, object]:
    ordered = sorted(box.children, key=lambda child: _stored_order(child.grid))
    areas = spec.get("areas")
    column_lines = spec.get("column_lines")
    row_lines = spec.get("row_lines")
    named = bool(areas) or column_lines is not None or row_lines is not None
    plain: list[dict[str, object]] = []
    resolved: list[dict[str, object]] = []
    for item in ordered:
        grid = item.grid if isinstance(item.grid, dict) else {}
        start_c = grid.get("column_start", "auto")
        end_c = grid.get("column_end", "auto")
        start_r = grid.get("row_start", "auto")
        end_r = grid.get("row_end", "auto")
        area = str(grid.get("area") or "")
        if area or any(_named_grid_side(side) for side in (start_c, end_c, start_r, end_r)):
            named = True
        plain.append(
            {
                "id": item.id,
                "column_start": start_c,
                "column_end": end_c,
                "row_start": start_r,
                "row_end": end_r,
            }
        )
        entry: dict[str, object] = {"id": item.id}
        if area:
            entry["area"] = area
        if grid.get("column_set") or not area:
            entry["column_start"] = start_c
            entry["column_end"] = end_c
        if grid.get("row_set") or not area:
            entry["row_start"] = start_r
            entry["row_end"] = end_r
        resolved.append(entry)
    flow = spec.get("flow", "row")
    if not named:
        placed = place_grid_items(len(columns), len(explicit_rows), plain, flow=flow)
        return placed if isinstance(placed, dict) else {"outcome": "invalid", "reason": "grid placement failed"}
    area_columns = len(str(areas[0]).split()) if isinstance(areas, list) and areas else 0
    area_rows = len(areas) if isinstance(areas, list) else 0
    placed = place_named_grid(
        len(columns),
        len(explicit_rows),
        resolved,
        areas=areas if isinstance(areas, list) and areas else None,
        column_lines=_pad_named_lines(column_lines, max(len(columns), area_columns)),
        row_lines=_pad_named_lines(row_lines, max(len(explicit_rows), area_rows)),
        flow=flow,
    )
    return placed if isinstance(placed, dict) else {"outcome": "invalid", "reason": "grid placement failed"}


def _fixed_row_breadth(track: object) -> int:
    """Used size of one explicit row when the grid block size is indefinite."""

    if isinstance(track, dict) and "flex" in track:
        raise _Invalid("grid row flex is unsupported")
    if isinstance(track, dict) and "minimum" in track and "maximum" in track and "breadth" not in track:
        floor = _px(track["minimum"], "grid track")
        ceiling = _px(track["maximum"], "grid track")
        return ceiling if ceiling >= floor else floor
    if isinstance(track, dict) and "fixed" in track and "breadth" not in track:
        return _px(track["fixed"], "grid track")
    raise _Invalid("grid row track is unsupported")


def _definite_row_track(track: object) -> dict[str, object]:
    """One explicit row inside a definite grid content box."""

    if isinstance(track, dict) and "flex" in track and "breadth" not in track:
        factor = track["flex"]
        if isinstance(factor, bool) or not isinstance(factor, (int, float)):
            raise _Invalid("grid row flex is unsupported")
        minimum = track.get("minimum", 0)
        return {"flex": factor, "minimum": _px(minimum, "grid track")}
    if isinstance(track, dict) and "minimum" in track and "maximum" in track and "breadth" not in track:
        return {
            "minimum": _px(track["minimum"], "grid track"),
            "maximum": _px(track["maximum"], "grid track"),
        }
    if isinstance(track, dict) and "fixed" in track and "breadth" not in track:
        return {"fixed": _px(track["fixed"], "grid track")}
    raise _Invalid("grid row track is unsupported")


def _grid_row_minimum(item: _Box, text_heights: dict[str, int]) -> int:
    specified = (item.grid or {}).get("height", "auto")
    contribution = specified if type(specified) is int else text_heights.get(item.id, 0)
    return (
        contribution
        + _grid_definite_margins(item, "top", "bottom")
        + _edge_extent(item.solved, "top", "bottom")
    )


def _automatic_row_sizes(
    box: _Box,
    explicit_rows: list,
    row_count: int,
    auto_rows: object,
    located: dict[str, dict[str, object]],
    text_heights: dict[str, int],
) -> list[int]:
    sizes: list[int] = []
    for index in range(row_count):
        if index < len(explicit_rows):
            sizes.append(_fixed_row_breadth(explicit_rows[index]))
            continue
        if isinstance(auto_rows, int):
            sizes.append(auto_rows)
            continue
        sizes.append(_content_row_height(index, box, located, text_heights))
    return sizes


def _definite_row_sizes(
    box: _Box,
    explicit_rows: list,
    row_count: int,
    auto_rows: object,
    row_gap: int,
    located: dict[str, dict[str, object]],
    text_heights: dict[str, int],
    specified_height: int,
) -> list[int]:
    """Size rows in a definite content box. Flexible rows take the leftover."""

    tracks: list[dict[str, object]] = []
    for index in range(row_count):
        if index < len(explicit_rows):
            tracks.append(_definite_row_track(explicit_rows[index]))
            continue
        if isinstance(auto_rows, int):
            tracks.append({"fixed": auto_rows})
            continue
        tracks.append({"fixed": _content_row_height(index, box, located, text_heights)})
    if not tracks:
        return []
    contributions: list[dict[str, object]] = []
    for item in box.children:
        entry = located.get(item.id)
        if entry is None:
            raise _Invalid("grid placement failed")
        contributions.append(
            {
                "start": int(entry.get("row") or 0) - 1,
                "span": int(entry.get("row_span") or 0),
                "minimum": _grid_row_minimum(item, text_heights),
            }
        )
    sized = size_grid_tracks(specified_height, tracks, contributions, gap=row_gap)
    raw_sizes = sized.get("track_sizes")
    if sized.get("outcome") != "resolved" or not isinstance(raw_sizes, list):
        raise _Invalid(str(sized.get("reason") or "grid tracks failed"))
    return [_px(size, "grid row") for size in raw_sizes]


def _place_grid(box: _Box, content_x: int, viewport_height: int | None) -> None:
    if box.writing_mode != "horizontal-tb" or box.direction != "ltr":
        raise _Invalid("grid writing mode is unsupported")
    specified_height = box.definite_height
    spec = box.grid or {}
    columns = spec.get("columns")
    explicit_rows = spec.get("rows")
    if not isinstance(columns, list) or not columns or not isinstance(explicit_rows, list):
        raise _Invalid("grid template is unsupported")
    column_gap = _px(spec.get("column_gap", 0), "grid gap")
    row_gap = _px(spec.get("row_gap", 0), "grid gap")
    placed = _place_grid_items(box, spec, columns, explicit_rows)
    placements = placed.get("placements")
    if placed.get("outcome") != "placed" or not isinstance(placements, list):
        raise _Invalid(str(placed.get("reason") or "grid placement failed"))
    if int(placed.get("column_start_line") or 0) != 1 or int(placed.get("row_start_line") or 0) != 1:
        raise _Invalid("grid implicit line is unsupported")
    column_count = int(placed.get("column_count") or 0)
    extra = column_count - len(columns)
    if extra < 0:
        raise _Invalid("grid column is invalid")
    track_defs = list(columns)
    if extra:
        auto_columns = spec.get("auto_columns")
        if not isinstance(auto_columns, int):
            raise _Invalid("grid auto column is unsupported")
        track_defs.extend({"fixed": auto_columns} for _ in range(extra))
    located = {
        str(entry.get("id")): entry
        for entry in placements
        if isinstance(entry, dict) and entry.get("id") is not None
    }
    for item in box.children:
        _install_grid_chrome(item)
    column_sizes = _size_grid_columns(box, track_defs, located, column_gap, spec)
    text_heights = _measure_grid_items(
        box, located, column_sizes, column_gap, content_x, viewport_height
    )
    row_count = int(placed.get("row_count") or 0)
    auto_rows = spec.get("auto_rows")
    if specified_height is None:
        row_sizes = _automatic_row_sizes(
            box, explicit_rows, row_count, auto_rows, located, text_heights
        )
    else:
        row_sizes = _definite_row_sizes(
            box,
            explicit_rows,
            row_count,
            auto_rows,
            row_gap,
            located,
            text_heights,
            specified_height,
        )
    origin = _px(box.solved.get("border_top"), "border-top") + _px(box.solved.get("padding_top"), "padding-top")
    for item in box.children:
        entry = located.get(item.id)
        if entry is None:
            raise _Invalid("grid placement failed")
        row = int(entry.get("row") or 0) - 1
        row_span = int(entry.get("row_span") or 0)
        specified = (item.grid or {}).get("height", "auto")
        area = _grid_span(row_sizes, row, row_span, row_gap)
        chrome_y = _edge_extent(item.solved, "top", "bottom")
        align, items_keyword = _grid_axis_keywords(box, item, "block")
        if type(specified) is int:
            aligned = _align_grid_axis(
                item,
                area,
                axis="block",
                size=specified + chrome_y,
                automatic=0,
                align=align,
                items=items_keyword,
            )
            item.content_height = specified
            item.border_height = specified + chrome_y
        else:
            aligned = _align_grid_axis(
                item,
                area,
                axis="block",
                size="auto",
                automatic=text_heights.get(item.id, 0) + chrome_y,
                align=align,
                items=items_keyword,
            )
            item.border_height = _px(aligned.get("size"), "grid item")
            item.content_height = _grid_border_content(item.border_height, chrome_y)
        item.anchor_y = (
            origin
            + _grid_offset(row_sizes, row, row_gap)
            + _px(aligned.get("start"), "grid item")
        )
        item.border_width = item.content_width + _edge_extent(item.solved, "left", "right")
        item.solved.update(
            margin_top=_px(aligned.get("margin_start"), "grid margin"),
            margin_bottom=_px(aligned.get("margin_end"), "grid margin"),
            margin_left=item.margin_left,
            margin_right=item.margin_right,
        )
    if specified_height is None:
        box.definite_height = _gapped_span(row_sizes, row_gap)
    else:
        box.definite_height = specified_height
    box.anchor_laid = True


def _size_grid_columns(
    box: _Box,
    track_defs: list[dict[str, object]],
    located: dict[str, dict[str, object]],
    column_gap: int,
    spec: dict[str, object],
) -> list[int]:
    if any("breadth" in track for track in track_defs):
        payload: list[dict[str, object]] = []
        for item in box.children:
            entry = located.get(item.id)
            if entry is None:
                raise _Invalid("grid placement failed")
            minimum, maximum = _grid_content_contribution(item)
            payload.append(
                {
                    "start": int(entry.get("column") or 0) - 1,
                    "span": int(entry.get("column_span") or 0),
                    "min_content": minimum,
                    "max_content": maximum,
                }
            )
        sized = size_content_grid_tracks(
            box.content_width,
            track_defs,
            payload,
            gap=column_gap,
            stretch=str(spec.get("justify") or "normal") != "start",
        )
    else:
        sized = size_grid_tracks(box.content_width, track_defs, [], gap=column_gap)
    raw_sizes = sized.get("track_sizes")
    if sized.get("outcome") != "resolved" or not isinstance(raw_sizes, list):
        raise _Invalid(str(sized.get("reason") or "grid tracks failed"))
    return [_px(size, "grid column") for size in raw_sizes]


_GRID_MARGIN_UNSUPPORTED = "grid item margin is unsupported"


def _grid_margin_sides(tree, element, styles, declarations) -> dict[str, tuple[bool, int]]:
    """Resolve the item's physical margins. A negative length stays rejected."""

    custom = styles.get(element, ({}, ""))[0]
    sides = {side: (False, 0) for side in ("top", "right", "bottom", "left")}
    for _order, prop, raw in _winners(tree, element, declarations):
        if prop == "margin":
            sides.update(
                _margin_shorthand(_grid_author(raw, custom), unsupported=_GRID_MARGIN_UNSUPPORTED)
            )
            continue
        if prop in {"margin-top", "margin-right", "margin-bottom", "margin-left"}:
            sides[prop.split("-", 1)[1]] = _margin_token(
                _grid_author(raw, custom),
                prop,
                unsupported=_GRID_MARGIN_UNSUPPORTED,
            )
    for automatic, length in sides.values():
        if not automatic and length < 0:
            raise _Invalid(_GRID_MARGIN_UNSUPPORTED)
    return sides


def _grid_definite_margins(item: _Box, *names: str) -> int:
    """Definite margins join the track contribution. Auto margins contribute nothing."""

    margins = (item.grid or {}).get("margins")
    if not isinstance(margins, dict):
        return 0
    total = 0
    for name in names:
        pair = margins.get(name)
        if not isinstance(pair, tuple) or len(pair) != 2:
            raise _Invalid(_GRID_MARGIN_UNSUPPORTED)
        automatic, length = pair
        if not automatic:
            total += _px(length, "grid item margin")
    return total


def _grid_axis_keywords(box: _Box, item: _Box, axis: str) -> tuple[str, str]:
    """Self alignment, then the container's items keyword, for one axis."""

    container = box.grid or {}
    spec = item.grid or {}
    if axis == "inline":
        return (
            str(spec.get("justify_self") or "auto"),
            str(container.get("justify_items") or "normal"),
        )
    return (
        str(spec.get("align_self") or "auto"),
        str(container.get("align_items") or "normal"),
    )


def _align_grid_axis(
    item: _Box,
    area: int,
    *,
    axis: str,
    size: object,
    automatic: int,
    align: str = "auto",
    items: str = "normal",
) -> dict[str, object]:
    margins = (item.grid or {}).get("margins")
    if not isinstance(margins, dict):
        margins = {side: (False, 0) for side in ("top", "right", "bottom", "left")}
    start_name, end_name = ("left", "right") if axis == "inline" else ("top", "bottom")

    def edge(name: str) -> object:
        pair = margins.get(name)
        if not isinstance(pair, tuple) or len(pair) != 2:
            raise _Invalid(_GRID_MARGIN_UNSUPPORTED)
        automatic_margin, length = pair
        if not automatic_margin and length < 0:
            raise _Invalid(_GRID_MARGIN_UNSUPPORTED)
        return "auto" if automatic_margin else length

    aligned = align_grid_item(
        area,
        size="auto" if size == "auto" else size,
        automatic=automatic,
        margin_start=edge(start_name),
        margin_end=edge(end_name),
        align=align,
        items=items,
        axis=axis,
    )
    if aligned.get("outcome") != "aligned":
        raise _Invalid(str(aligned.get("reason") or _GRID_MARGIN_UNSUPPORTED))
    return aligned


def _grid_content_contribution(item: _Box) -> tuple[int, int]:
    extra = _grid_definite_margins(item, "left", "right") + _edge_extent(item.solved, "left", "right")
    width = (item.grid or {}).get("width", "auto")
    if isinstance(width, int):
        return width + extra, width + extra
    if item.children:
        bounds = [_nested_block_intrinsic(child) for child in item.children]
        return max(bound[0] for bound in bounds) + extra, max(bound[1] for bound in bounds) + extra
    if item.inline_text:
        minimum, maximum = _intrinsic_text_sizes(item)
        return minimum + extra, maximum + extra
    return extra, extra


def _nested_block_intrinsic(box: _Box) -> tuple[int, int]:
    """Min and max content of a block inside a grid item, before the item margin."""

    specified = _specified_px_width(box)
    if specified is not None:
        return specified, specified
    if box.children:
        bounds = [_nested_block_intrinsic(child) for child in box.children]
        return max(bound[0] for bound in bounds), max(bound[1] for bound in bounds)
    if box.inline_text:
        return _intrinsic_text_sizes(box)
    return 0, 0


def _specified_px_width(box: _Box) -> int | None:
    raw = _box_decl(box, "width")
    if raw is None:
        return None
    text = " ".join(raw.strip().lower().split())
    if text in {"auto", "initial", "unset", "revert"}:
        return None
    if text == "0":
        return 0
    if text.endswith("px"):
        return _px(float(text[:-2]), "grid item")
    return None


def _adopt_grid_item_blocks(
    tree,
    element,
    item: _Box,
    styles,
    declarations,
    ids: set[str],
    counter: list[int],
) -> None:
    """Take a grid item's block children. Mixed text and other displays stay rejected."""

    if _grid_text(getattr(element, "text", None)):
        raise _Invalid("grid item content is unsupported")
    for node in tree.children.get(element, []):
        if _grid_text(getattr(node, "tail", None)):
            raise _Invalid("grid item content is unsupported")
    found, floats, _flow, positioned = _walk(
        tree,
        element,
        _modes(item),
        _fonts(item),
        item.direction,
        styles,
        declarations,
        ids,
        counter,
        item,
    )
    if floats or positioned or item.atoms or not found:
        raise _Invalid("grid item content is unsupported")
    for child in found:
        _reject_grid_item_block(child)
    item.children = found
    item.flow = list(found)


def _reject_grid_item_block(box: _Box) -> None:
    if box.display != "block" or box.position != "static" or box.float_side != "none":
        raise _Invalid("grid item content is unsupported")
    if box.writing_mode != "horizontal-tb" or box.direction != "ltr":
        raise _Invalid("grid item content is unsupported")
    sizing = _box_decl(box, "box-sizing")
    if sizing not in {None, "content-box", "initial", "unset", "revert"}:
        raise _Invalid("grid item content is unsupported")
    for child in box.children:
        _reject_grid_item_block(child)


def _lay_grid_item_blocks(item: _Box, viewport_height: int | None) -> int:
    """Place block children inside the item and return the content height they use.

    The item is an independent formatting context: child margins do not escape,
    and adjoining vertical margins of those children collapse with each other.
    """

    inset_x = _edge_extent(item.solved, "left")
    inset_y = _edge_extent(item.solved, "top")
    for child in item.children:
        _solve(child, item.content_width, None, viewport_height, item.x + inset_x)
    placed = place_collapsed_margins(
        {
            "id": item.id,
            "margin_top": 0,
            "margin_bottom": 0,
            "padding_top": 0,
            "padding_bottom": 0,
            "border_top": 0,
            "border_bottom": 0,
            "height": "auto",
            "min_height": 0,
            "overflow": "clip",
            "float": "none",
            "position": "static",
            "display": "block",
            "clearance": False,
            "children": [_collapse_spec(child) for child in item.children],
        }
    )
    boxes = placed.get("boxes")
    if placed.get("outcome") != "placed" or not isinstance(boxes, list):
        raise _Invalid(str(placed.get("reason") or "grid item content is unsupported"))
    by_id = {str(entry.get("id")): entry for entry in boxes if isinstance(entry, dict)}
    parent = by_id.get(item.id)
    if parent is None:
        raise _Invalid("grid item content is unsupported")
    for child in item.children:
        _stamp_grid_child(child, by_id, -inset_y)
    return _px(parent.get("border_height"), "grid item")


def _stamp_grid_child(box: _Box, by_id: dict[str, dict[str, object]], parent_y: int) -> None:
    record = by_id.get(box.id)
    if record is None:
        raise _Invalid("grid item content is unsupported")
    border_y = _px(record.get("y"), "y")
    box.anchor_y = border_y - parent_y
    box.border_height = _px(record.get("border_height"), "border height")
    box.content_height = box.border_height - _edge_extent(box.solved, "top", "bottom")
    if box.content_height < 0:
        raise _Invalid("content height is invalid")
    for child in box.children:
        _stamp_grid_child(child, by_id, border_y)


def _measure_grid_items(
    box: _Box,
    located: dict[str, dict[str, object]],
    column_sizes: list[int],
    column_gap: int,
    content_x: int,
    viewport_height: int | None,
) -> dict[str, int]:
    heights: dict[str, int] = {}
    for item in box.children:
        entry = located.get(item.id)
        if entry is None:
            raise _Invalid("grid placement failed")
        column = int(entry.get("column") or 0) - 1
        column_span = int(entry.get("column_span") or 0)
        area = _grid_span(column_sizes, column, column_span, column_gap)
        width = (item.grid or {}).get("width", "auto")
        chrome_x = _edge_extent(item.solved, "left", "right")
        align, items_keyword = _grid_axis_keywords(box, item, "inline")
        if type(width) is int:
            aligned = _align_grid_axis(
                item,
                area,
                axis="inline",
                size=width + chrome_x,
                automatic=0,
                align=align,
                items=items_keyword,
            )
            item.content_width = width
        else:
            content_auto = _intrinsic_text_sizes(item)[1] if item.inline_text else 0
            aligned = _align_grid_axis(
                item,
                area,
                axis="inline",
                size="auto",
                automatic=content_auto + chrome_x,
                align=align,
                items=items_keyword,
            )
            item.content_width = _grid_border_content(_px(aligned.get("size"), "grid item"), chrome_x)
        item.margin_left = _px(aligned.get("margin_start"), "grid margin")
        item.margin_right = _px(aligned.get("margin_end"), "grid margin")
        item.x = content_x + _grid_offset(column_sizes, column, column_gap) + _px(
            aligned.get("start"), "grid item"
        )
        item.border_width = item.content_width + chrome_x
        if item.children:
            heights[item.id] = _lay_grid_item_blocks(item, viewport_height)
        elif item.inline_text:
            item.lines = _plain_lines(item, item.content_width, item.direction)
            heights[item.id] = sum(line.height for line in item.lines)
        else:
            heights[item.id] = 0
    return heights


def _content_row_height(
    index: int,
    box: _Box,
    located: dict[str, dict[str, object]],
    text_heights: dict[str, int],
) -> int:
    height = 0
    for item in box.children:
        entry = located.get(item.id)
        if entry is None:
            raise _Invalid("grid placement failed")
        row = int(entry.get("row") or 0) - 1
        span = int(entry.get("row_span") or 0)
        if row > index or row + span <= index:
            continue
        if span != 1:
            raise _Invalid("grid row span content is unsupported")
        specified = (item.grid or {}).get("height", "auto")
        if isinstance(specified, int):
            contribution = specified
        else:
            contribution = text_heights.get(item.id, 0)
        height = max(
            height,
            contribution
            + _grid_definite_margins(item, "top", "bottom")
            + _edge_extent(item.solved, "top", "bottom"),
        )
    return height


_TABLE_LAYOUTS = frozenset({"auto", "fixed"})
_TABLE_ALIGNS = frozenset({"baseline", "top", "middle", "bottom"})
_TABLE_CHROME = (
    "border-spacing",
    "border-collapse",
    "caption-side",
    "empty-cells",
)


def _walk_table(
    tree,
    element,
    inherited: dict[str, str],
    fonts: dict[str, str],
    styles,
    declarations,
    ids: set[str],
    counter: list[int],
    host: _Box,
) -> tuple[list[_Box], list[_Box], list[_Box], list[_Box]]:
    host.table = _table_container(tree, element, styles, declarations)
    if host.table.get("collapse") is True:
        host.table["borders"] = _specified_borders(host)
        host.declarations = [
            (prop, value) for prop, value in host.declarations if not _border_declaration(prop)
        ]
    if host.writing_mode != "horizontal-tb" or host.direction != "ltr":
        raise _Invalid("table writing mode is unsupported")
    _reject_table_text(getattr(element, "text", None))
    rows: list[_Box] = []
    for child in tree.children.get(element, []):
        _reject_table_text(getattr(child, "tail", None))
        if not _local_name(child) or _local_name(child) in _SKIP_TAGS:
            continue
        row = _make_box(
            tree,
            child,
            inherited,
            fonts,
            host.direction,
            styles,
            declarations,
            ids,
            counter,
            root=False,
        )
        if row.display == "none":
            continue
        if row.display != "table-row":
            raise _Invalid("table row is unsupported")
        if row.position != "static" or row.float_side != "none":
            raise _Invalid("table row is outside the table")
        if row.writing_mode != "horizontal-tb" or row.direction != "ltr":
            raise _Invalid("table writing mode is unsupported")
        if host.table.get("collapse") is True:
            row.table = {"borders": _specified_borders(row)}
        _reject_table_text(getattr(child, "text", None))
        cells = _table_cells(
            tree,
            child,
            inherited,
            fonts,
            styles,
            declarations,
            ids,
            counter,
            host,
        )
        if not cells:
            raise _Invalid("table row is empty")
        row.children = cells
        rows.append(row)
    if not rows:
        raise _Invalid("table is empty")
    count = len(rows[0].children)
    if any(len(row.children) != count for row in rows):
        raise _Invalid("table columns do not match")
    return rows, [], rows, []


def _table_cells(
    tree,
    row_element,
    inherited: dict[str, str],
    fonts: dict[str, str],
    styles,
    declarations,
    ids: set[str],
    counter: list[int],
    host: _Box,
) -> list[_Box]:
    cells: list[_Box] = []
    for child in tree.children.get(row_element, []):
        _reject_table_text(getattr(child, "tail", None))
        if not _local_name(child) or _local_name(child) in _SKIP_TAGS:
            continue
        cell = _make_box(
            tree,
            child,
            inherited,
            fonts,
            host.direction,
            styles,
            declarations,
            ids,
            counter,
            root=False,
        )
        if cell.display == "none":
            continue
        if cell.display != "table-cell":
            raise _Invalid("table cell is unsupported")
        if cell.position != "static" or cell.float_side != "none":
            raise _Invalid("table cell is outside the table")
        if cell.writing_mode != "horizontal-tb" or cell.direction != "ltr":
            raise _Invalid("table writing mode is unsupported")
        if any(
            _local_name(grand) and _local_name(grand) not in _SKIP_TAGS
            for grand in tree.children.get(child, [])
        ):
            raise _Invalid("table cell content is unsupported")
        for grand in tree.children.get(child, []):
            _reject_table_text(getattr(grand, "tail", None))
        collapse = host.table.get("collapse") is True
        _reject_table_edges(cell, collapse=collapse)
        cell.inline_text = child.text or ""
        cell.table = _table_cell(tree, child, styles, declarations)
        if collapse:
            cell.table["borders"] = _specified_borders(cell)
        cells.append(cell)
    return cells


def _reject_table_text(text: object) -> None:
    if isinstance(text, str) and text.strip():
        raise _Invalid("table text is unsupported")


def _reject_table_edges(box: _Box, *, collapse: bool = False) -> None:
    sizing = _box_decl(box, "box-sizing")
    if sizing not in {None, "content-box", "initial", "unset", "revert"}:
        raise _Invalid("table box-sizing is unsupported")
    allowed_border = collapse
    for name in (*_FLEX_EDGES, "margin", "padding", "border-width"):
        if allowed_border and _border_declaration(name):
            continue
        raw = _box_decl(box, name)
        if raw is None or raw.strip().lower() in _ZERO_EDGE | {"none"}:
            continue
        raise _Invalid("table cell edge is unsupported")
    limits = {
        "min-width": {"auto", "0", "0px", "initial", "unset", "revert"},
        "min-height": {"auto", "0", "0px", "initial", "unset", "revert"},
        "max-width": {"none", "initial", "unset", "revert"},
        "max-height": {"none", "initial", "unset", "revert"},
    }
    for name, allowed in limits.items():
        raw = _box_decl(box, name)
        if raw is None or raw.strip().lower() in allowed:
            continue
        raise _Invalid("table cell limit is unsupported")


def _table_container(tree, element, styles, declarations) -> dict[str, object]:
    custom = styles.get(element, ({}, ""))[0]
    layout = "auto"
    collapse = False
    spacing = "0"
    for _order, prop, raw in _winners(tree, element, declarations):
        if prop == "table-layout":
            layout = _choice(_grid_author(raw, custom), "auto", _TABLE_LAYOUTS, "table-layout")
            continue
        if prop not in _TABLE_CHROME:
            continue
        value = _grid_author(raw, custom)
        if prop == "border-spacing":
            spacing = value
            continue
        if prop == "border-collapse":
            if value == "collapse":
                collapse = True
            elif value not in {"separate", "initial", "unset", "revert"}:
                raise _Invalid("table border collapse is unsupported")
            continue
        if prop == "caption-side" and value not in {"top", "initial", "unset", "revert"}:
            raise _Invalid("table caption is unsupported")
        if prop == "empty-cells" and value not in {"show", "initial", "unset", "revert"}:
            raise _Invalid("table empty cells are unsupported")
    if not collapse and spacing not in {"0", "0px", "initial", "unset", "revert"}:
        raise _Invalid("table spacing is unsupported")
    return {"layout": layout, "collapse": collapse}


def _table_cell(tree, element, styles, declarations) -> dict[str, object]:
    custom = styles.get(element, ({}, ""))[0]
    width: object = "auto"
    align = "baseline"
    for _order, prop, raw in _winners(tree, element, declarations):
        if prop not in {"width", "vertical-align"}:
            continue
        value = _grid_author(raw, custom)
        if prop == "width":
            width = _table_length(value)
        else:
            align = _choice(value, "baseline", _TABLE_ALIGNS, "vertical-align")
    return {"width": width, "vertical_align": align}


def _table_length(value: str) -> object:
    if value in {"auto", "initial", "unset", "revert"}:
        return "auto"
    if value == "inherit":
        raise _Invalid("table length inherit is unsupported")
    if value == "0":
        return 0
    if value.endswith("px"):
        return _px(float(value[:-2]), "table length")
    raise _Invalid("table length is unsupported")


_BORDER_STYLES = frozenset(
    {"none", "hidden", "dotted", "dashed", "solid", "double", "groove", "ridge", "inset", "outset"}
)
_BORDER_LINE = {"thin": 1, "medium": 3, "thick": 5}


def _border_declaration(prop: str) -> bool:
    name = prop.strip().lower()
    if name in {"border-width", "border-style"}:
        return True
    return name.startswith("border-") and (name.endswith("-width") or name.endswith("-style"))


def _specified_borders(box: _Box) -> dict[str, dict[str, object]]:
    slots = _physical_slots(box)
    sides: dict[str, dict[str, object]] = {}
    for side in ("top", "right", "bottom", "left"):
        style = slots.get(f"border-{side}-style", "none")
        if style not in _BORDER_STYLES:
            raise _Invalid("table border style is unsupported")
        sides[side] = {"style": style, "width": _specified_border_width(style, slots.get(f"border-{side}-width"))}
    return sides


def _specified_border_width(style: str, raw: str | None) -> int:
    if style == "none":
        return 0
    token = "medium" if raw is None else raw.strip().lower()
    if token in {"initial", "unset", "revert"}:
        token = "medium"
    if token in _BORDER_LINE:
        return _BORDER_LINE[token]
    if token == "0":
        return 0
    if token.endswith("px"):
        return _px(float(token[:-2]), "table border")
    raise _Invalid("table border width is unsupported")


def _split_internal(width: int) -> tuple[int, int]:
    """Share one internal edge. The extra pixel stays on the start side."""

    start = (width + 1) // 2
    return start, width - start


def _collapsed_lines(box: _Box, rows: list[_Box], columns: int) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    cells = [
        {
            "row": row_index,
            "column": column,
            "span": 1,
            "rowspan": 1,
            "borders": (cell.table or {}).get("borders") or {},
        }
        for row_index, row in enumerate(rows)
        for column, cell in enumerate(row.children)
    ]
    resolved = resolve_collapsed_grid(
        columns,
        len(rows),
        table=(box.table or {}).get("borders") or {},
        rows=[(row.table or {}).get("borders") or {} for row in rows],
        cells=cells,
        direction="ltr",
    )
    vertical = resolved.get("vertical")
    horizontal = resolved.get("horizontal")
    if resolved.get("outcome") != "resolved" or not isinstance(vertical, list) or not isinstance(horizontal, list):
        raise _Invalid(str(resolved.get("reason") or "collapsed border failed"))
    return vertical, horizontal


def _collapsed_axis(
    sizes: list[int], edges: list[dict[str, object]]
) -> tuple[list[int], list[int], list[int], int, int, int]:
    count = len(sizes)
    if len(edges) != count + 1:
        raise _Invalid("collapsed border failed")
    widths = [_px(edge.get("width"), "collapsed border") for edge in edges]
    positions: list[int] = []
    starts: list[int] = []
    ends: list[int] = []
    cursor = 0
    for index, size in enumerate(sizes):
        start = widths[0] if index == 0 else _split_internal(widths[index])[1]
        end = widths[count] if index == count - 1 else _split_internal(widths[index + 1])[0]
        positions.append(cursor)
        starts.append(start)
        ends.append(end)
        cursor += start + size + end
    outer_start = widths[0]
    outer_end = widths[count]
    return positions, starts, ends, outer_start, outer_end, cursor - outer_start - outer_end


def _used_edge(edge: dict[str, object], inset: int) -> dict[str, object]:
    return {
        "width": _px(edge.get("width"), "collapsed border"),
        "inset": inset,
        "style": edge.get("style"),
        "source": edge.get("source"),
    }


def _place_collapsed_table(
    box: _Box,
    rows: list[_Box],
    column_sizes: list[int],
    heights: list[object],
    by_id: dict[str, dict[str, object]],
    content_x: int,
) -> None:
    vertical, horizontal = _collapsed_lines(box, rows, len(column_sizes))
    row_heights = [_px(heights[index], "table row") for index in range(len(rows))]
    xs, lefts, rights, table_left, table_right, content_width = _collapsed_axis(column_sizes, vertical)
    ys, tops, bottoms, table_top, table_bottom, content_height = _collapsed_axis(row_heights, horizontal)
    box.content_width = content_width
    box.definite_height = content_height
    solved = dict(box.solved)
    solved["border_left"] = table_left
    solved["border_right"] = table_right
    solved["border_top"] = table_top
    solved["border_bottom"] = table_bottom
    box.solved = solved
    if box.table is None:
        box.table = {}
    box.table["used_edges"] = {
        "left": _used_edge(vertical[0], table_left),
        "right": _used_edge(vertical[-1], table_right),
        "top": _used_edge(horizontal[0], table_top),
        "bottom": _used_edge(horizontal[-1], table_bottom),
    }
    full_width = table_left + content_width + table_right
    for row_index, row in enumerate(rows):
        row_height = row_heights[row_index]
        top = tops[row_index]
        bottom = bottoms[row_index]
        row.x = content_x
        row.anchor_y = ys[row_index]
        row.content_width = full_width
        row.content_height = top + row_height + bottom
        row.border_width = full_width
        row.border_height = top + row_height + bottom
        row.margin_left = 0
        row.margin_right = 0
        row.solved = dict(_ZERO_FLEX_EDGES)
        for column, cell in enumerate(row.children):
            entry = by_id.get(cell.id)
            if entry is None:
                raise _Invalid("table placement failed")
            left = lefts[column]
            right = rights[column]
            shift = _px(entry.get("content_top"), "table cell")
            cell_solved = dict(_ZERO_FLEX_EDGES)
            cell_solved["border_left"] = left
            cell_solved["border_right"] = right
            cell_solved["border_top"] = top
            cell_solved["border_bottom"] = bottom
            cell.solved = cell_solved
            cell.x = content_x + xs[column]
            # The row already carries this grid position. Cells are offset from the row.
            cell.anchor_y = 0
            cell.content_width = column_sizes[column]
            cell.content_height = row_height
            cell.border_width = left + column_sizes[column] + right
            cell.border_height = top + row_height + bottom
            cell.margin_left = 0
            cell.margin_right = 0
            if cell.table is None:
                cell.table = {}
            cell.table["used_edges"] = {
                "left": _used_edge(vertical[column], left),
                "right": _used_edge(vertical[column + 1], right),
                "top": _used_edge(horizontal[row_index], top),
                "bottom": _used_edge(horizontal[row_index + 1], bottom),
            }
            for line in cell.lines:
                line.y += shift
    box.anchor_laid = True


def _place_table(box: _Box, content_x: int) -> None:
    if box.writing_mode != "horizontal-tb" or box.direction != "ltr":
        raise _Invalid("table writing mode is unsupported")
    rows = box.children
    if not rows or any(not row.children for row in rows):
        raise _Invalid("table is empty")
    count = len(rows[0].children)
    if any(len(row.children) != count for row in rows):
        raise _Invalid("table columns do not match")
    available = box.content_width
    width_auto = box.solved.get("specified_width") in {None, "auto"}
    layout = str((box.table or {}).get("layout") or "auto")
    collapse = (box.table or {}).get("collapse") is True
    if collapse and (layout == "fixed" or not width_auto):
        raise _Invalid("collapsed table width is unsupported")
    if layout == "fixed" and not width_auto:
        sized = layout_fixed_columns(
            available,
            ["auto"] * count,
            cells=[_fixed_cell(cell) for cell in rows[0].children],
            spacing=0,
        )
    else:
        payload: list[dict[str, object]] = []
        for row in rows:
            for column, cell in enumerate(row.children):
                minimum, maximum = _intrinsic_text_sizes(cell)
                item: dict[str, object] = {
                    "column": column,
                    "span": 1,
                    "min_content": minimum,
                    "max_content": maximum,
                }
                width = (cell.table or {}).get("width", "auto")
                if width != "auto":
                    item["width"] = width
                payload.append(item)
        sized = layout_auto_columns(
            "auto" if width_auto else available,
            ["auto"] * count,
            payload,
            containing=available if width_auto else None,
            spacing=0,
        )
    raw_sizes = sized.get("column_widths")
    if sized.get("outcome") != "resolved" or not isinstance(raw_sizes, list) or len(raw_sizes) != count:
        raise _Invalid(str(sized.get("reason") or "table columns failed"))
    column_sizes = [_px(size, "table column") for size in raw_sizes]
    used_width = _px(sized.get("used_table_width"), "table width")
    box.content_width = used_width
    row_cells: list[dict[str, object]] = []
    for row_index, row in enumerate(rows):
        for column, cell in enumerate(row.children):
            cell.content_width = column_sizes[column]
            if (cell.inline_text or "").strip() or cell.white_space not in _COLLAPSED_EMPTY:
                _fill_lines(cell)
            row_cells.append(
                {
                    "id": cell.id,
                    "row": row_index,
                    "content_height": cell.definite_height or 0,
                    "baseline": cell.lines[0].baseline if cell.lines else 0,
                    "vertical_align": str((cell.table or {}).get("vertical_align") or "baseline"),
                }
            )
    laid = layout_table_rows(
        ["auto"] * len(rows),
        row_cells,
        table_height="auto" if box.definite_height is None else box.definite_height,
        border_spacing=0,
    )
    placed = laid.get("cells")
    heights = laid.get("row_heights")
    if laid.get("outcome") != "resolved" or not isinstance(placed, list) or not isinstance(heights, list):
        raise _Invalid(str(laid.get("reason") or "table rows failed"))
    by_id = {
        str(entry.get("id")): entry
        for entry in placed
        if isinstance(entry, dict) and entry.get("id") is not None
    }
    if collapse:
        _place_collapsed_table(box, rows, column_sizes, list(heights), by_id, content_x)
        return
    origin = _px(box.solved.get("border_top"), "border-top") + _px(box.solved.get("padding_top"), "padding-top")
    offsets: list[int] = []
    cursor = 0
    for size in column_sizes:
        offsets.append(cursor)
        cursor += size
    for row_index, row in enumerate(rows):
        row_height = _px(heights[row_index], "table row")
        lead = by_id.get(row.children[0].id)
        if lead is None:
            raise _Invalid("table placement failed")
        row_top = _px(lead.get("border_top"), "table row")
        row.x = content_x
        row.anchor_y = origin + row_top
        row.content_width = used_width
        row.content_height = row_height
        row.border_width = used_width
        row.border_height = row_height
        row.margin_left = 0
        row.margin_right = 0
        row.solved = dict(_ZERO_FLEX_EDGES)
        for column, cell in enumerate(row.children):
            entry = by_id.get(cell.id)
            if entry is None:
                raise _Invalid("table placement failed")
            slot = _px(entry.get("border_height"), "table cell")
            shift = _px(entry.get("content_top"), "table cell")
            cell.x = content_x + offsets[column]
            cell.anchor_y = origin + _px(entry.get("border_top"), "table cell")
            cell.content_width = column_sizes[column]
            cell.content_height = slot
            cell.border_width = column_sizes[column]
            cell.border_height = slot
            cell.margin_left = 0
            cell.margin_right = 0
            cell.solved = dict(_ZERO_FLEX_EDGES)
            for line in cell.lines:
                line.y += shift
    box.definite_height = _px(laid.get("used_table_height"), "table height")
    box.anchor_laid = True


def _fixed_cell(cell: _Box) -> dict[str, object]:
    width = (cell.table or {}).get("width", "auto")
    return {"span": 1, "width": "auto" if width == "auto" else width}
