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
put them. A relative inline keeps that same static slot in the line: its
glyphs paint at the static position plus the used left and top, a nested
relative inline adds its own offset, and later glyphs, the line break, and
the following block stay put. A vertical writing mode, a non-ltr paragraph,
white-space other than normal, a different font, a float beside the inline,
and an inline-block inside it stay rejected. An absolute or fixed box uses the padding edge of the nearest ancestor that captures it. A position other than static captures an absolute box only. A transform, filter, perspective, backdrop-filter, paint or layout containment, hidden content-visibility, or capturing will-change captures both, including translate(0) on a static box. Otherwise an absolute box uses the viewport when no ancestor is positioned, and a fixed box uses the viewport. An inline capturer is rejected. Neither out-of-flow box changes the height of the flow.
A sticky block keeps the place it occupied in the flow. Its used border box
then shifts against the nearest non-visible overflow scrollport, or against
the viewport when every ancestor is visible. ``scroll_x`` and ``scroll_y``
move only that viewport; a nearer scrollport stays at scroll zero. The parent
padding edge stops the shift, and the following sibling stays at its static
position. Nested sticky, a sticky float, a sticky inline, a sticky root, and
a sticky box that is not horizontal and left-to-right are rejected.
Horizontal text inside that box supplies shrink-to-fit width and the stacked
line-box height. A static block child is laid out in that content box: its
text wraps to the definite width, adjoining child margins collapse inside
the absolute formatting context, and an automatic height grows to the last
child's margin edge. An automatic width with an automatic horizontal inset
shrinks to those children: the used content width is the minimum of their
max-content and the maximum of their min-content and the available space.
A child margin stays inside that box. A percentage width, an intrinsic
limit, a float, and a nested positioned box stay rejected. Automatic insets
on an axis use the static position between
block siblings. An inline absolute in a horizontal left-to-right line uses the
static position of the first inline box it would have generated: preceding text
keeps it on that line when the hypothetical word fits, and the next line
receives it when the word does not. The parent's in-flow lines omit that
absolute. A block-level absolute in that line, a float, an inline-block, a
relative inline, justification, white-space other than normal, and a vertical
writing mode stay rejected. A vertical
writing mode still rejects those automatic sizes. An absolute or fixed box
with ``position-anchor`` and ``position-area`` then moves onto that named
in-flow anchor. The margin box meets the anchor's block-start border edge
for ``block-start`` and its inline-end border edge for ``inline-end``, and
it stays centered on the other axis. A specified ``left`` or ``top`` does
not keep the box away from that edge. The following in-flow block stays
where it was without the anchored box. A missing name, a duplicated
``anchor-name``, a float or other out-of-flow anchor, an anchor inside the
positioned box, a non-horizontal box, an indefinite containing block
height, and ``position-area`` on a static box are rejected. A float inside
a block whose only in-flow content is text
is placed in that content box, and the line boxes beside its margin box
shrink. An inline-block in that text is an unbreakable item: its margin box
sits in the gap when the line fits, and the item moves intact below the float
when it does not. A shaped float, a taller atomic box, and a mixed font stay
rejected for that item. ``shape-outside`` replaces that rectangle with the shape clipped to
the margin box: a circle leaves its corner open, an inset releases the next
line where the shape ends, and ``shape-margin`` expands the shape before
clipping. A shape that cannot be parsed is rejected. A float beside a
following block sibling is placed in that same
content box: the sibling keeps its width, its line boxes shorten where the
float area overlaps them, and clear moves the sibling's border edge
down to those floats. Text in the float is wrapped in its content box.
Automatic width is the shrink-to-fit size, and automatic height is the
stacked line boxes; a specified size stays specified. In-flow block
children lay out in the float: their margins stay inside, automatic
widths stretch, and an automatic float shrinks to the widest child.
Inline children, nested floats, and loose text beside those blocks stay
rejected. That sibling path keeps each vertical margin
instead of collapsing adjoining ones. An automatic height is the block children, or
the stacked line boxes when
that block's own in-flow content is text, and it also grows to the bottom
margin edge of a float that block itself placed. Each character, including
the space, advances by the font size. On every horizontal plain line, including
one that wrapped, a Unicode bidi visual order that differs from the source is
a glyph from that line's left edge. A line that is already visual omits
glyphs. Justification, a float, and a relative inline still omit them. ``line-height: normal`` uses the font
size as the strut. ``text-align`` shifts each line inside its line box.
``justify`` and ``justify-all`` give the aligner one item per word, so leftover
inline space is added to the interior gaps instead of sitting after the line.
The last line of ``justify`` stays packed unless ``text-align-last: justify``
or ``justify-all`` stretches it. ``text-justify: none`` leaves the gaps alone,
and ``inter-character`` also opens the gaps inside a word. A line with no
interior gap does not move, and leftover space is never compressed. Preserved
white space, a vertical writing mode, a non-ltr direction, a mixed font, an
inline-block, and a relative inline stay rejected. ``text-indent`` moves only
the first line of a horizontal left-to-right block and shortens that line's
wrap measure by the same amount. A length may be negative and can start the
line outside the content edge. A percentage is resolved against the containing
block's inline size and is inherited as that percentage, so a child can clear
it with zero. ``hanging`` and ``each-line`` are rejected. A float intrusion,
an inline-block, a mixed font, an inside marker, and a vertical writing mode
stay rejected. A

block that also has block children keeps those children and does not build
line boxes. Inline content beside those children becomes an anonymous block
box with no margin, border, or padding, stretched to the parent's content
width and using the parent's font, alignment, and white space. Collapsible
whitespace between blocks does not generate one. A float is a split in
that same stream: the text before it, and the text after it, each become an
anonymous block, and those blocks shorten their lines beside the float. An
inline-block in that loose text is an unbreakable item of the anonymous
block: its margin box shares the shortened line when it fits, and the item
moves intact below the float when it does not. The following block sibling
keeps its own lines, shortened where the float still overlaps them. Clear
on a later sibling starts that sibling below the float. A relative inline,
a mixed font, a shaped float, and an atomic box taller than the strut stay
rejected in that mix. An
absolute or fixed box still leaves the loose text out. An inline child may set font-size and line-height. Each run advances
by its own font size, and the line grows to the tallest run without
shrinking the parent's strut. text-align and white-space on an inline
stay rejected. A float beside those mixed runs is rejected too. An
inline-block is an atomic inline: automatic width is the shrink-to-fit of
its text, the words before and after stay on the line, and the atomic box
moves intact to the next line when it does not fit. Its bottom margin edge
rests on the parent baseline when overflow is not visible or it has no line
box; otherwise the baseline is its last line. ``vertical-align`` moves that
margin box: ``top`` and ``bottom`` meet the line edges, ``middle`` centers it
on the baseline, ``text-top`` and ``text-bottom`` meet the parent content
edges, and a length or percentage raises the baseline alignment. ``sub`` and
``super`` are rejected. A block sibling, a float, a nested inline-block, and
positioned content inside it are rejected.
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
those line boxes, painted in the used content width. A contiguous text run
in the container is an anonymous item with the initial flex factors: its
max-content slot is the collapsed or preserved text, a whitespace-only run
is omitted, and ``display: contents`` does not split the run. ``order: 0``
places that run before a later item. A different font on the run, or a
preserved break inside it, is rejected.
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
A grid item whose own ``grid-template-columns`` is ``subgrid`` does not size
those columns. Its children use the parent tracks it spans, parent gutter
included. An omitted column gap keeps each child on its parent track. A zero
column gap pulls the children across that gutter. A line past the spanned
columns clamps onto the last spanned track, and the subgrid grows no column.
``grid-template-rows: subgrid`` and a subgrid that is not itself a grid item
are rejected. A specified width on a subgrid child is rejected; its height is
a definite length.
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
that cell. The following block starts under the table border box.
``colspan`` and ``rowspan`` assign slots. The cell covers those tracks, a
later cell starts at the next free slot, and the span's max-content is spread
across its columns. A span that lands on an occupied slot is rejected, and a
span of zero is rejected. A span past the rows that exist covers only those
rows. A static block child inside a cell is an independent formatting
context: its margin stays inside the cell, adjoining child margins collapse,
and the row grows to that content. A narrow column wraps the child's text,
and an automatic column takes the child's max-content. Floats, positioned
boxes, and loose text beside those children stay rejected. ``border-spacing``
separates those cells. A horizontal length opens a gap between adjoining
columns, and a vertical length opens a gap between rows. An automatic table
width also keeps that horizontal gap outside both edges. A fixed table width
keeps it only between columns. ``border-collapse: collapse`` ignores the
spacing. A negative length is rejected. A static text caption stacks in
that content box: ``caption-side: top`` sits above the grid and
``caption-side: bottom`` sits under it. The caption wraps to the table's
used width and does not change the columns, so the following block starts
under the caption plus the grid. The caption's own ``caption-side`` wins
over the table's. A collapsed table, a table border or padding, a second
caption, caption children, and any other caption side stay rejected.
A block with ``column-count`` or ``column-width`` is a multicol container.
Each text-only child is an unbreakable border box: it wraps at the used
column width, and ``column-span: all`` takes the whole content box and ends
that column line. The shortest balanced line sets an automatic height, so
the following block starts under the multicol box. ``column-fill: auto``
with an automatic height still balances, because a continuous container has
no constrained column block size. A definite height fills in source order up
to that content height: a child that does not fit starts the next column,
``column`` or ``always`` breaks do the same unless the break would leave a
column empty, ``avoid-column`` keeps a fitting suffix with the next child,
and content past the last column overflows it. ``page`` does not start a
column. The following block stays under that specified border box.
``column-span: all`` inside that fixed fill balances and shortens the line
above the spanner, lays the spanner across the content box, and fills the
leftover block size in source order. The multicol keeps its specified
height. A nested formatting context, a non-zero margin, and a
non-horizontal writing mode stay rejected. An omitted ``column-gap`` is
``1em``.
An ``inline-size`` or ``size`` container answers ``@container`` for descendants
after its content-box size is known. The container is not a candidate for its
own query. A named query selects the nearest ancestor with that name which can
answer the features, and a failed condition does not fall through to an outer
container. Matching declarations join the cascade at their source order, so a
later unconditional declaration of the same specificity still wins. A box
without ``container-type`` does not answer a size query.
A horizontal in-flow block measures its automatic height from the content
stack, then ``max-height`` clamps that content and ``min-height`` raises it.
The minimum wins when both are set. The following block starts at the used
border edge. A percentage uses the parent's definite content height. An
automatic parent turns a percentage ``min-height`` into zero and a percentage
``max-height`` into none. ``box-sizing: border-box`` subtracts vertical
padding and border, and the content box does not go below zero. A non-zero
``min-height`` stops the bottom margin from collapsing through the block.
Flex, grid, table, multicol, float, and vertical boxes keep the heights
their own formatting contexts already chose.
A preferred ``aspect-ratio`` on one of those horizontal blocks maps the
definite content width into an automatic height. The used height is at least
that mapped size, and a taller content stack still grows it. A scrollport,
or an explicit ``min-height`` including zero, keeps the mapped size and lets
the extra content overflow. ``max-height`` clamps the mapped size. A
specified height stays specified. A plain ratio uses the ``box-sizing`` box;
``auto`` together with a ratio always uses the content box. A zero component
behaves as ``auto``.
An ``img``, ``video``, or ``canvas`` is replaced. Its width and height
attributes are the intrinsic size. Automatic axes use that size, or 300 by
150 when neither attribute is present. One specified axis wins, and the
automatic axis keeps the intrinsic ratio. A block's automatic horizontal
margins then center that used width. An inline replaced element is an atomic
line item whose bottom margin edge rests on the strut baseline. ``object-fit``
places the concrete object inside the content box. An absolute or fixed image
uses that intrinsic size and then the absolute inset equation, so definite
insets do not stretch it. Automatic insets use its static position, including
the line slot of an inline image. A maximum width shrinks that size and keeps
the ratio. An inline relative or sticky image, a vertical writing mode,
``border-box``, a CSS ``aspect-ratio``, and a child stay rejected.
An ``li`` and any other ``display: list-item`` principal box lays out as a
block and paints a marker from the ``list-item`` counter. ``ol`` and ``ul``
reset that counter. The initial marker is a disc; an ``ol`` uses decimal
unless the author sets another type. ``list-style-position: outside`` ends
the marker on the content start and does not move the principal line.
``inside`` places the marker on the first line and wraps the remaining text
at the full content width. ``none`` paints nothing. A float, a non-horizontal
writing mode, and an inside marker beside a block child stay rejected.
Writing mode, direction and text orientation inherit. Other CSS-wide keywords
on box properties use their initial values.
A text-only orthogonal block wraps down its used content height and stacks
its lines from block-start. Once the columns determine its width, the
horizontal parent resolves auto margins and stacks the physical border box.
Widths and heights in line records are physical. Text uses the engine's
uniform glyph advances. Nested formatting contexts, mixed fonts and
justification inside this orthogonal block are unsupported.
``display: contents`` generates no box. The element is replaced by its
children and text in the parent's formatting context, so its own width,
padding, border, and margin do not move them. A percentage on a child uses
that parent. ``font-size`` and ``line-height`` still inherit through the
element, including onto an inline run that stays on the parent's line.
Nested contents unwraps. A flex or grid parent takes the children as items,
and a table parent takes them as rows or cells. Float, absolute, and
relative on the contents element do not generate a box: the child stays in
flow. The root element's contents computes to block.
``sibling-index()`` and ``sibling-count()`` resolve in a used box length.
The number is that element's place among its DOM element siblings, so a
``display: none`` sibling still counts and a ``display: contents`` parent
does not reparent the child. A percentage stays a percentage of the
containing block. A call with an argument is invalid. A comment that only
mentions the function does not call it.
``::before`` and ``::after`` insert their string content into that element's
inline stream and inherit its font. A flex container keeps each generated
string as its own anonymous item. ``counter()`` and ``counters()`` in that
content become the same text: ``::before`` reads the counter after the
element's own reset and increment, and ``::after`` reads it after the
element's children. A counter style formats the integer. ``counters()``
joins every scope of that name, outer scope first, with its separator.
A flex, grid, or table box, a flex or grid item, an unknown function, and
any other property on a pseudo that generates a box stay rejected.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from blackhole_agent.css_absolute import place_absolute
from blackhole_agent.css_anchor_position import place_anchored
from blackhole_agent.css_aspect_ratio import block_ratio_limits, parse_aspect_ratio
from blackhole_agent.css_container_query import match_container_query
from blackhole_agent.css_counters import format_counter, format_counters, resolve_counters
from blackhole_agent.css_bidi import reorder_css_bidi
from blackhole_agent.css_auto_table import layout_auto_columns
from blackhole_agent.css_collapsed_border import resolve_collapsed_grid
from blackhole_agent.css_fixed_table import layout_fixed_columns
from blackhole_agent.css_flex_align import flex_line_cross_size, place_flex_alignment
from blackhole_agent.css_flex_base import resolve_flex_base
from blackhole_agent.css_flex_line import resolve_flex_line
from blackhole_agent.css_flex_wrap import wrap_flex_lines
from blackhole_agent.css_float_lines import seek_shaped_gap, shaped_gap_at
from blackhole_agent.css_float_placement import place_floats
from blackhole_agent.css_shape_outside import ShapeError, prepare_shape
from blackhole_agent.css_sticky import sticky_offset
from blackhole_agent.css_subgrid import place_subgrid_items
from blackhole_agent.css_grid_align import align_grid_item
from blackhole_agent.css_grid_areas import place_named_grid
from blackhole_agent.css_grid_content import size_content_grid_tracks
from blackhole_agent.css_grid_placement import place_grid_items
from blackhole_agent.css_grid_tracks import size_grid_tracks
from blackhole_agent.css_hit_test import element_from_point
from blackhole_agent.css_object_fit import fit_object
from blackhole_agent.css_replaced import used_replaced_size
from blackhole_agent.css_inline_line import layout_inline_line
from blackhole_agent.css_length_math import is_length_math
from blackhole_agent.css_line_break import _default_advance, wrap_lines
from blackhole_agent.css_relative import place_relative
from blackhole_agent.css_table_rows import layout_table_rows
from blackhole_agent.css_text_align import align_inline_line
from blackhole_agent.css_tree_counting import resolve_tree_counting
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
from blackhole_agent.css_column_break import fragment_columns
from blackhole_agent.css_containing_block import resolve_containing_block
from blackhole_agent.css_multicol import layout_multicol
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
    resolve_generated_plans,
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
_REPLACED_TAGS = frozenset({"img", "video", "canvas"})
_REPLACED_SKIP = _SKIP_TAGS | {"source", "track"}
_OBJECT_FITS = frozenset({"fill", "contain", "cover", "none", "scale-down"})
_DISPLAYS = frozenset(
    {
        "block",
        "inline",
        "inline-block",
        "flex",
        "grid",
        "table",
        "table-row",
        "table-cell",
        "table-caption",
        "none",
        "contents",
    }
)
_FLOW_DISPLAYS = _DISPLAYS | {"list-item"}
_LIST_TYPES = frozenset(
    {
        "none",
        "disc",
        "circle",
        "square",
        "decimal",
        "lower-alpha",
        "upper-alpha",
        "lower-latin",
        "upper-latin",
        "lower-roman",
        "upper-roman",
    }
)
_LIST_POSITIONS = frozenset({"inside", "outside"})
_MARKER_SYMBOLS = {"disc": "\u2022", "circle": "\u25e6", "square": "\u25aa"}
_MARKER_SENTINEL = "\ufffc"
_MARKER_BREAK = "\u200b"
_STATIC_MARK = "\ufffc"
_LIST_RESET_TAGS = frozenset({"ol", "ul"})
_TABLE_OUTSIDE = frozenset({"table-row", "table-cell", "table-caption"})
_POSITIONS = frozenset({"static", "relative", "absolute", "fixed", "sticky"})
_FLOATS = frozenset({"none", "left", "right"})
_CLEARS = frozenset({"none", "left", "right", "both"})
_OVERFLOWS = frozenset({"visible", "hidden", "auto", "scroll", "clip"})
_SCROLLPORTS = frozenset({"hidden", "auto", "scroll", "clip"})
_INHERITED = {
    "writing-mode": "horizontal-tb",
    "direction": "ltr",
    "text-orientation": "mixed",
}
_FONT = {
    "font-size": "16px",
    "line-height": "normal",
    "text-align": "start",
    "text-align-last": "auto",
    "text-justify": "auto",
    "text-indent": "0px",
    "white-space": "normal",
    "list-style-type": "disc",
    "list-style-position": "outside",
}
_ALIGNS = frozenset(
    {"start", "end", "left", "right", "center", "justify", "justify-all", "match-parent"}
)
_LAST_ALIGNS = frozenset({"auto", "start", "end", "left", "right", "center", "justify"})
_JUSTIFY_MODES = frozenset({"auto", "none", "inter-word", "inter-character"})
_WHITES = frozenset({"normal", "nowrap", "pre", "pre-wrap", "break-spaces", "pre-line"})
_FRAGMENT_BREAKS = frozenset(
    {
        "auto",
        "avoid",
        "always",
        "all",
        "avoid-page",
        "page",
        "left",
        "right",
        "recto",
        "verso",
        "avoid-column",
        "column",
        "avoid-region",
        "region",
    }
)
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


@dataclass(frozen=True)
class _Shift:
    direction: str
    left: str
    right: str
    top: str
    bottom: str


@dataclass
class _Piece:
    text: str
    font_size: int
    line_height: str
    atom: _Box | None = None
    shifts: tuple[_Shift, ...] = ()


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
    float_band: tuple[int, int, int, int, str, str, float] | None = None
    shape_outside: str = ""
    shape_margin: float = 0.0
    solved: dict[str, object] = field(default_factory=dict)
    definite_height: int | None = None
    min_content_height: int = 0
    max_content_height: int | None = None
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
    text_align_last: str = "auto"
    text_justify: str = "auto"
    text_indent: str = "0px"
    containing_inline: int | None = None
    white_space: str = "normal"
    parent_direction: str | None = None
    inline_text: str | None = None
    static_index: int = 0
    line_static: tuple[str, tuple[int, ...]] | None = None
    flow_y: int = 0
    lines: list[_Line] = field(default_factory=list)
    atoms: list[_Box] = field(default_factory=list)
    pieces: list[_Piece] = field(default_factory=list)
    relative_layers: dict[int, _Shift] = field(default_factory=dict)
    local_x: int = 0
    flex: dict[str, object] | None = None
    grid: dict[str, object] | None = None
    table: dict[str, object] | None = None
    multicol: dict[str, object] | None = None
    column_span: str = "none"
    break_before: str = "auto"
    break_after: str = "auto"
    parent_box: _Box | None = None
    anonymous: bool = False
    container_type: str = "normal"
    container_name: str = "none"
    query_rules: list[tuple[str, object]] = field(default_factory=list)
    sheet: list = field(default_factory=list)
    custom: dict = field(default_factory=dict)
    element: object = None
    tree: object = None
    aspect_ratio: tuple[float, float, bool] | None = None
    vertical_align: str | float = "baseline"
    stack_z: str | None = None
    stack_opacity: str | None = None
    stack_pointer: str | None = None
    stack_visibility: str | None = None
    anchor_name: str = ""
    position_anchor: str = ""
    position_area: str = ""
    replaced: bool = False
    intrinsic_width: int | None = None
    intrinsic_height: int | None = None
    object_fit: str = "fill"
    object_position: str = "50% 50%"
    object_box: dict[str, int] | None = None
    list_item: bool = False
    list_style_type: str = "disc"
    list_style_position: str = "outside"
    counter_reset: str = ""
    counter_increment: str = ""
    counter_children: list[_Box] = field(default_factory=list)
    counters_closed: bool = False
    marker_text: str | None = None
    marker_width: int = 0
    marker: dict[str, object] | None = None
    capture: dict[str, str] = field(default_factory=dict)


def layout_normal_flow(
    markup: str,
    stylesheet: str,
    *,
    viewport_width: int,
    viewport_height: int | None = None,
    scroll_x: int = 0,
    scroll_y: int = 0,
) -> dict[str, object]:
    """Return viewport border boxes for the document's normal-flow blocks.

    ``viewport_width`` is the initial containing block's width in CSS pixels.
    ``viewport_height`` is that block's height, or indefinite when omitted.
    ``scroll_x`` and ``scroll_y`` are that viewport's scroll offsets. They
    move a sticky box whose scrollport is the viewport and leave every other
    box at its static position. ``x`` and ``y`` are the border edges measured
    from the unscrolled viewport origin. Lengths are ``px`` or percentages. A
    unitless zero is rejected. ``sibling-index()`` and ``sibling-count()``
    inside a box length use the element's DOM siblings before that length is
    solved. Rules come from the stylesheet; a style
    attribute is not read. Relative offsets are applied after the static
    positions, then sticky offsets. Absolute and fixed boxes are included
    in the returned boxes.
    """

    try:
        root = _placed_root(
            markup,
            stylesheet,
            viewport_width=viewport_width,
            viewport_height=viewport_height,
            scroll_x=scroll_x,
            scroll_y=scroll_y,
        )
    except (CssSelectorError, _Invalid) as exc:
        return _invalid(str(exc))
    return {"outcome": "placed", "reason": None, "boxes": [_record(box) for box in _each(root)]}


def element_from_document(
    markup: str,
    stylesheet: str,
    x: object,
    y: object,
    *,
    viewport_width: int,
    viewport_height: int | None = None,
    scroll_x: int = 0,
    scroll_y: int = 0,
) -> dict[str, object]:
    """Return the frontmost element whose border box contains ``(x, y)``.

    The document is laid out by ``layout_normal_flow``. Paint order is CSS 2.2
    Appendix E, so a float is in front of an overlapping in-flow block, a
    positive z-index is in front of a later auto-positioned sibling, and a
    negative z-index that escapes its parent is behind that parent.
    ``pointer-events: none`` and ``visibility: hidden`` are not targets.
    ``outcome`` is ``hit``, ``miss``, or ``invalid``.
    """

    try:
        _finite_point(x, "x")
        _finite_point(y, "y")
        root = _placed_root(
            markup,
            stylesheet,
            viewport_width=viewport_width,
            viewport_height=viewport_height,
            scroll_x=scroll_x,
            scroll_y=scroll_y,
        )
        tree = _document_hit_tree(root)
    except (CssSelectorError, _Invalid) as exc:
        return {"outcome": "invalid", "id": None, "reason": str(exc)}
    found = element_from_point(tree, x, y)
    if not isinstance(found, dict):
        return {"outcome": "invalid", "id": None, "reason": "hit failed"}
    if "reason" not in found:
        return {**found, "reason": None}
    return found


def _placed_root(
    markup: str,
    stylesheet: str,
    *,
    viewport_width: int,
    viewport_height: int | None,
    scroll_x: int,
    scroll_y: int,
) -> _Box:
    if not isinstance(markup, str) or not isinstance(stylesheet, str):
        raise _Invalid("markup is invalid")
    if type(viewport_width) is not int or viewport_width < 0:
        raise _Invalid("viewport width is invalid")
    if viewport_height is not None and (type(viewport_height) is not int or viewport_height < 0):
        raise _Invalid("viewport height is invalid")
    if type(scroll_x) is not int:
        raise _Invalid("scroll x is invalid")
    if type(scroll_y) is not int:
        raise _Invalid("scroll y is invalid")
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
    generated: dict[int, tuple[str, str]] = {}
    plans: dict[int, tuple[list, list]] = {}
    for element in order:
        try:
            before, after = resolve_generated_plans(tree, element, declarations, styles[element][0])
        except CssSelectorError as exc:
            raise _Invalid(str(exc)) from exc
        if _plan_has_counter(before) or _plan_has_counter(after):
            if _flow_kind(tree, element, styles, declarations) == "contents":
                raise _Invalid("generated counter is unsupported")
            plans[id(element)] = (before, after)
            continue
        pair = (_plan_text(before), _plan_text(after))
        if pair == ("", ""):
            continue
        if _flow_kind(tree, element, styles, declarations) == "contents":
            continue
        generated[id(element)] = pair
    tree.generated = generated
    tree.generated_plans = plans
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
    if root.display in _TABLE_OUTSIDE:
        raise _Invalid("table box is outside the table")
    if root.position in {"absolute", "fixed"} or root.float_side != "none":
        raise _Invalid("root is outside normal flow")
    if root.position == "sticky":
        raise _Invalid("sticky root is unsupported")
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
    _set_inline(root, tree, order[0], styles, declarations, ids, counter)
    _bind_list_markers(root)
    _solve(root, viewport_width, viewport_height, viewport_height, 0)
    placed = place_collapsed_margins(_collapse_spec(root))
    if placed.get("outcome") != "placed" or not isinstance(placed.get("boxes"), list):
        raise _Invalid(str(placed.get("reason") or "margin collapse failed"))
    by_id = {str(item["id"]): item for item in placed["boxes"] if isinstance(item, dict)}
    margin_top = _px(root.solved.get("margin_top"), "margin-top")
    _assign_y(root, by_id, margin_top)
    _shift_relatives(root, viewport_width, viewport_height)
    _shift_stickies(root, viewport_width, viewport_height, scroll_x, scroll_y)
    _place_positioned(root, _Edge(0, 0, viewport_width, viewport_height))
    return root


def _invalid(reason: str) -> dict[str, object]:
    return {"outcome": "invalid", "reason": reason, "boxes": None}


_HIT_DISPLAYS = frozenset({"block", "inline", "inline-block"})


def _finite_point(value: object, name: str) -> None:
    if isinstance(value, bool) or type(value) not in (int, float):
        raise _Invalid(f"{name} is invalid")
    if value != value or value in (float("inf"), float("-inf")):
        raise _Invalid(f"{name} is invalid")


def _stack_text(raw: str | None) -> str | None:
    if raw is None:
        return None
    token = " ".join(raw.split()).lower()
    return token or None


def _used_z(raw: str | None, inherited: int | None) -> int | None:
    token = _stack_text(raw)
    if token is None or token in {"initial", "unset", "revert", "auto"}:
        return None
    if token == "inherit":
        return inherited
    sign = 1
    digits = token
    if digits[0] in "+-":
        sign = -1 if digits[0] == "-" else 1
        digits = digits[1:]
    if not digits or not digits.isdigit():
        raise _Invalid("z-index is invalid")
    return sign * int(digits)


def _used_opacity(raw: str | None, inherited: float) -> float:
    token = _stack_text(raw)
    if token is None or token in {"initial", "unset", "revert"}:
        return 1.0
    if token == "inherit":
        return inherited
    percent = token.endswith("%")
    body = token[:-1] if percent else token
    try:
        number = float(body)
    except ValueError as exc:
        raise _Invalid("opacity is invalid") from exc
    if number != number or number in (float("inf"), float("-inf")):
        raise _Invalid("opacity is invalid")
    if percent:
        number /= 100.0
    if number < 0.0 or number > 1.0:
        raise _Invalid("opacity is invalid")
    return number


def _used_keyword(
    raw: str | None,
    inherited: str,
    allowed: frozenset[str],
    initial: str,
    name: str,
) -> str:
    token = _stack_text(raw)
    if token is None or token in {"unset", "revert"}:
        return inherited
    if token == "initial":
        return initial
    if token == "inherit":
        return inherited
    if token not in allowed:
        raise _Invalid(f"{name} is invalid")
    return token


def _document_hit_tree(root: _Box) -> dict[str, object]:
    boxes: list[_Box] = []
    seen: set[int] = set()
    stack = [root]
    while stack:
        box = stack.pop()
        marker = id(box)
        if marker in seen:
            continue
        seen.add(marker)
        boxes.append(box)
        stack.extend(box.positioned)
        stack.extend(box.floats)
        stack.extend(box.children)
        stack.extend(box.atoms)
    by_parent: dict[int, list[_Box]] = {}
    for box in boxes:
        if box is root or box.anonymous:
            continue
        parent = box.parent_box
        while parent is not None and parent.anonymous:
            parent = parent.parent_box
        if parent is None:
            continue
        by_parent.setdefault(id(parent), []).append(box)
    return _hit_node(root, by_parent, "auto", "visible", None, 1.0)


def _hit_node(
    box: _Box,
    by_parent: dict[int, list[_Box]],
    pointer: str,
    visibility: str,
    inherited_z: int | None,
    inherited_opacity: float,
) -> dict[str, object]:
    if box.display not in _HIT_DISPLAYS:
        raise _Invalid("display is unsupported")
    if box.position not in _POSITIONS:
        raise _Invalid("position is invalid")
    if box.float_side not in _FLOATS:
        raise _Invalid("float is invalid")
    used_pointer = _used_keyword(
        box.stack_pointer, pointer, frozenset({"auto", "none"}), "auto", "pointer-events"
    )
    used_visibility = _used_keyword(
        box.stack_visibility, visibility, frozenset({"visible", "hidden"}), "visible", "visibility"
    )
    used_z = _used_z(box.stack_z, inherited_z)
    used_opacity = _used_opacity(box.stack_opacity, inherited_opacity)
    children = sorted(by_parent.get(id(box), ()), key=lambda child: _hit_sibling_key(box, child))
    return {
        "id": box.id,
        "position": box.position,
        "z_index": "auto" if used_z is None else used_z,
        "opacity": used_opacity,
        "float": box.float_side,
        "display": box.display,
        "x": box.x,
        "y": box.y,
        "width": box.border_width,
        "height": box.border_height,
        "pointer_events": used_pointer,
        "visibility": used_visibility,
        "children": [
            _hit_node(child, by_parent, used_pointer, used_visibility, used_z, used_opacity)
            for child in children
        ],
    }


def _hit_sibling_key(parent: _Box, child: _Box) -> tuple[int, str]:
    tree = parent.tree
    element = parent.element
    child_element = child.element
    if tree is None or element is None or child_element is None:
        return (10**9, child.id)
    try:
        index = list(tree.children.get(element, [])).index(child_element)
    except ValueError:
        index = 10**9
    return (index, child.id)


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
        if box.replaced and _replaced_has_content(tree, child):
            raise _Invalid("replaced content is unsupported")
        if box.display == "contents":
            if host.float_side != "none" and _float_loose_text(tree, child, host.white_space):
                raise _Invalid("float content is unsupported")
            children, child_floats, child_flow, child_positioned = _walk(
                tree,
                child,
                _modes(box),
                _fonts(box),
                box.direction,
                styles,
                declarations,
                ids,
                counter,
                host,
                container_rules,
            )
            found.extend(children)
            floats.extend(child_floats)
            flow.extend(child_flow)
            positioned.extend(child_positioned)
            if child_positioned and _capture_effect(box):
                raise _Invalid("contents capture is unsupported")
            continue
        host.counter_children.append(box)
        if box.position in {"absolute", "fixed"}:
            nested = _walk(
                tree, child, _modes(box), _fonts(box), box.direction, styles, declarations,
                ids, counter, box, container_rules,
            )
            box.children, box.floats, box.flow, box.positioned = nested
            _set_inline(box, tree, child, styles, declarations, ids, counter)
            if box.children or box.floats or box.positioned or box.atoms:
                if (
                    box.display != "block"
                    or box.floats
                    or box.positioned
                    or box.atoms
                    or box.inline_text
                ):
                    raise _Invalid("positioned content is unsupported")
                for nested_box in box.children:
                    _reject_abs_block(nested_box)
            box.static_index = len(found)
            positioned.append(box)
            continue
        if box.float_side != "none":
            if box.position == "sticky":
                raise _Invalid("sticky float is unsupported")
            element_children = [
                node for node in tree.children.get(child, []) if _local_name(node) not in _SKIP_TAGS
            ]
            if element_children:
                if box.writing_mode != "horizontal-tb" or box.direction != "ltr":
                    raise _Invalid("float content is unsupported")
                nested = _walk(
                    tree,
                    child,
                    _modes(box),
                    _fonts(box),
                    box.direction,
                    styles,
                    declarations,
                    ids,
                    counter,
                    box,
                    container_rules,
                )
                box.children, box.floats, box.flow, box.positioned = nested
                box.counters_closed = True
                if (
                    not box.children
                    or box.floats
                    or box.positioned
                    or box.atoms
                    or _float_loose_text(tree, child, box.white_space)
                    or any(not _float_block_child(item) for item in box.children)
                ):
                    raise _Invalid("float content is unsupported")
            else:
                box.counters_closed = True
                if _element_has_counter_plan(tree, child):
                    raise _Invalid("generated counter is unsupported")
                box.inline_text = child.text or ""
            floats.append(box)
            flow.append(box)
            continue
        if box.replaced and box.display == "inline" and box.float_side == "none":
            if box.position != "static":
                raise _Invalid("positioned replaced element is unsupported")
            host.atoms.append(box)
            continue
        if box.display in _TABLE_OUTSIDE:
            raise _Invalid("table box is outside the table")
        inline = box.display == "inline"
        if inline and box.position == "sticky":
            raise _Invalid("sticky inline is unsupported")
        if inline and box.position == "relative":
            if box.writing_mode != "horizontal-tb" or box.direction not in {"ltr", "rtl"}:
                raise _Invalid("relative inline is unsupported")
            atoms_before = len(host.atoms)
            children, child_floats, _child_flow, child_positioned = _walk(
                tree,
                child,
                _modes(box),
                _fonts(box),
                box.direction,
                styles,
                declarations,
                ids,
                counter,
                host,
                container_rules,
            )
            if children or child_floats or child_positioned or len(host.atoms) != atoms_before:
                raise _Invalid("relative inline content is unsupported")
            host.relative_layers[id(child)] = _inline_shift(box)
            box.counters_closed = True
            continue
        if box.display == "inline-block" and box.position != "static":
            raise _Invalid("positioned inline-block is unsupported")
        nested = _walk(
            tree, child, _modes(box), _fonts(box), box.direction, styles, declarations,
            ids, counter, host if inline else box, container_rules,
        )
        if inline:
            children, child_floats, child_flow, child_positioned = nested
            if child_positioned and _capture_effect(box):
                raise _Invalid("inline fragment")
            found.extend(children)
            floats.extend(child_floats)
            flow.extend(child_flow)
            positioned.extend(child_positioned)
            box.counters_closed = True
            continue
        box.children, box.floats, box.flow, box.positioned = nested
        _set_inline(box, tree, child, styles, declarations, ids, counter)
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
    tag = _local_name(element)
    if _declared(winners, "list-style", custom) is not None:
        raise _Invalid("list-style shorthand is unsupported")
    display = _keyword(
        _declared(winners, "display", custom),
        _FLOW_DISPLAYS,
        "list-item" if tag == "li" else ("block" if tag in _BLOCK_TAGS else "inline"),
        "display",
    )
    list_item = display == "list-item"
    if list_item:
        display = "block"
    if root and display == "contents":
        display = "block"
        list_item = False
    position = _keyword(_declared(winners, "position", custom), _POSITIONS, "static", "position")
    float_side = _keyword(_declared(winners, "float", custom), _FLOATS, "none", "float")
    clear = _keyword(_declared(winners, "clear", custom), _CLEARS, "none", "clear")
    overflow = _keyword(_declared(winners, "overflow", custom), _OVERFLOWS, "visible", "overflow")
    box_declarations = _counted_declarations(tree, element, _boxed_declarations(winners, custom))
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
    replaced = _local_name(element) in _REPLACED_TAGS
    intrinsic_width = _intrinsic_attribute(element, "width") if replaced else None
    intrinsic_height = _intrinsic_attribute(element, "height") if replaced else None
    object_fit = _read_object_fit(winners, custom) if replaced else "fill"
    object_position = _read_object_position(winners, custom) if replaced else "50% 50%"
    font_size = _font_size(_declared(winners, "font-size", custom), fonts["font-size"])
    line_height = _line_height(_declared(winners, "line-height", custom), fonts["line-height"])
    columns = _read_columns(winners, custom, font_size)
    shape_outside, shape_margin = _read_float_shape(winners, custom) if float_side != "none" else ("", 0.0)
    position_anchor, position_area = _read_position_anchor(winners, custom, position, mode, direction)
    box = _Box(
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
        line_height=line_height,
        vertical_align=(
            _read_inline_align(_declared(winners, "vertical-align", custom), font_size, line_height)
            if display == "inline-block"
            else "baseline"
        ),
        text_align=_inherited_keyword(
            _declared(winners, "text-align", custom),
            _ALIGNS,
            fonts["text-align"],
            _FONT["text-align"],
            "text-align",
        ),
        text_align_last=_inherited_keyword(
            _declared(winners, "text-align-last", custom),
            _LAST_ALIGNS,
            fonts["text-align-last"],
            _FONT["text-align-last"],
            "text-align-last",
        ),
        text_justify=_inherited_keyword(
            _declared(winners, "text-justify", custom),
            _JUSTIFY_MODES,
            fonts["text-justify"],
            _FONT["text-justify"],
            "text-justify",
        ),
        text_indent=_read_text_indent(_declared(winners, "text-indent", custom), fonts["text-indent"]),
        white_space=_inherited_keyword(
            _declared(winners, "white-space", custom),
            _WHITES,
            fonts["white-space"],
            _FONT["white-space"],
            "white-space",
        ),
        parent_direction=parent_direction,
        multicol=columns,
        column_span=_read_column_span(winners, custom),
        break_before=_read_fragment_break(winners, custom, "break-before"),
        break_after=_read_fragment_break(winners, custom, "break-after"),
        shape_outside=shape_outside,
        shape_margin=shape_margin,
        container_type=_container_kind(_declared(winners, "container-type", custom)),
        container_name=_container_label(_declared(winners, "container-name", custom)),
        query_rules=_matching_queries(tree, element, container_rules),
        sheet=declarations,
        custom=custom,
        element=element,
        tree=tree,
        aspect_ratio=_read_aspect_ratio(winners, custom),
        stack_z=_declared(winners, "z-index", custom),
        stack_opacity=_declared(winners, "opacity", custom),
        stack_pointer=_declared(winners, "pointer-events", custom),
        stack_visibility=_declared(winners, "visibility", custom),
        replaced=replaced,
        intrinsic_width=intrinsic_width,
        intrinsic_height=intrinsic_height,
        object_fit=object_fit,
        object_position=object_position,
        list_item=list_item,
        list_style_type=_list_style_type(winners, custom, fonts, tag),
        list_style_position=_inherited_keyword(
            _declared(winners, "list-style-position", custom),
            _LIST_POSITIONS,
            fonts["list-style-position"],
            "outside",
            "list-style-position",
        ),
        counter_reset=_counter_declaration(winners, custom, "counter-reset", tag),
        counter_increment=_counter_declaration(winners, custom, "counter-increment", ""),
        anchor_name=_read_anchor_name(winners, custom),
        position_anchor=position_anchor,
        position_area=position_area,
        capture=_read_capture(winners, custom),
    )
    boxes = getattr(tree, "box_of", None)
    if not isinstance(boxes, dict):
        boxes = {}
        tree.box_of = boxes
    boxes[id(element)] = box
    return box


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


def _counted_declarations(tree, element, declarations: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Replace tree-counting calls with the integers the length solver can see.

    The substituted expression keeps percentages symbolic. A call that takes
    an argument cannot be a length. A mention that is only a comment stays
    untouched, because the counter finds no call.
    """

    if not any(_mentions_tree_count(value) for _prop, value in declarations):
        return declarations
    counting, labels = _counting_context(tree)
    label = labels.get(element)
    if label is None:
        raise _Invalid("sibling function is invalid")
    rewritten: list[tuple[str, str]] = []
    for prop, value in declarations:
        if not _mentions_tree_count(value):
            rewritten.append((prop, value))
            continue
        result = resolve_tree_counting(value, counting, label, percentage_basis=0)
        reason = str(result.get("reason") or "")
        if reason == "argument":
            raise _Invalid("sibling function argument is invalid")
        if reason == "function":
            rewritten.append((prop, value))
            continue
        substituted = result.get("value")
        if not isinstance(substituted, str) or not substituted.strip():
            raise _Invalid(reason or "sibling function is invalid")
        rewritten.append((prop, substituted))
    return rewritten


def _mentions_tree_count(value: str) -> bool:
    lowered = value.lower()
    return "sibling-index" in lowered or "sibling-count" in lowered


def _counting_context(tree) -> tuple[dict[str, object], dict[object, str]]:
    cached = getattr(tree, "_sibling_counts", None)
    if cached is not None:
        return cached
    labels: dict[object, str] = {}

    def build(node) -> dict[str, object]:
        label = f"e{id(node)}"
        labels[node] = label
        return {
            "tag": _local_name(node) or "element",
            "id": label,
            "children": [build(child) for child in tree.children.get(node, ())],
        }

    root = next((node for node, parent in tree.parent.items() if parent is None), None)
    if root is None:
        raise _Invalid("sibling function is invalid")
    cached = (build(root), labels)
    tree._sibling_counts = cached
    return cached


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
    target.declarations = _counted_declarations(
        target.tree, target.element, _boxed_declarations(winners, target.custom)
    )


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
    if box.text_align in {"justify", "justify-all"} or box.text_align_last == "justify":
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


def _column_text(value: str | None) -> str | None:
    if value is None:
        return None
    return " ".join(value.strip().lower().split())


def _read_aspect_ratio(winners, custom: dict) -> tuple[float, float, bool] | None:
    raw = _declared(winners, "aspect-ratio", custom)
    if raw is None or raw in {"auto", "initial", "unset", "revert"}:
        return None
    if raw == "inherit":
        raise _Invalid("aspect-ratio inherit is unsupported")
    try:
        return parse_aspect_ratio(raw)
    except ValueError as exc:
        raise _Invalid("aspect-ratio is invalid") from exc


def _read_column_span(winners, custom: dict) -> str:
    value = _column_text(_declared(winners, "column-span", custom))
    if value is None or value in {"none", "initial", "unset", "revert"}:
        return "none"
    if value == "inherit":
        raise _Invalid("column-span inherit is unsupported")
    if value == "all":
        return "all"
    raise _Invalid("column-span is invalid")


def _read_columns(winners, custom: dict, font_size: int) -> dict[str, object] | None:
    count = _column_count(_column_text(_declared(winners, "column-count", custom)))
    width = _column_width(_column_text(_declared(winners, "column-width", custom)))
    if count is None and width is None:
        return None
    return {
        "count": "auto" if count is None else count,
        "width": "auto" if width is None else width,
        "gap": _column_gap(_column_text(_declared(winners, "column-gap", custom)), font_size),
        "fill": _column_fill(_column_text(_declared(winners, "column-fill", custom))),
    }


def _column_count(value: str | None) -> int | None:
    if value is None or value in {"auto", "initial", "unset", "revert"}:
        return None
    if value == "inherit":
        raise _Invalid("column-count inherit is unsupported")
    if value.isdigit() and value[0] != "0":
        return int(value)
    raise _Invalid("column-count is invalid")


def _column_width(value: str | None) -> int | None:
    if value is None or value in {"auto", "initial", "unset", "revert"}:
        return None
    if value == "inherit":
        raise _Invalid("column-width inherit is unsupported")
    if not value.endswith("px"):
        raise _Invalid("column-width is invalid")
    number = _px(float(value[:-2]), "column-width")
    if number < 1:
        raise _Invalid("column-width is invalid")
    return number


def _column_gap(value: str | None, font_size: int) -> int:
    if value is None or value in {"normal", "initial", "unset", "revert"}:
        return font_size
    if value == "inherit":
        raise _Invalid("column-gap inherit is unsupported")
    if value in {"0", "0px"}:
        return 0
    if not value.endswith("px"):
        raise _Invalid("column-gap is invalid")
    number = _px(float(value[:-2]), "column-gap")
    if number < 0:
        raise _Invalid("column-gap is invalid")
    return number


def _column_fill(value: str | None) -> str:
    if value is None or value in {"balance", "initial", "unset", "revert"}:
        return "balance"
    if value == "balance-all":
        return "balance-all"
    if value == "inherit":
        raise _Invalid("column-fill inherit is unsupported")
    if value == "auto":
        return "auto"
    raise _Invalid("column-fill is invalid")


def _read_fragment_break(winners, custom: dict, name: str) -> str:
    value = _column_text(_declared(winners, name, custom))
    if value is None or value in {"auto", "initial", "unset", "revert"}:
        return "auto"
    if value == "inherit":
        raise _Invalid(f"{name} inherit is unsupported")
    if value in _FRAGMENT_BREAKS:
        return value
    raise _Invalid(f"{name} is invalid")


def _column_inline_offset(index: int, available: int, gap: int, count: int) -> int:
    """Used inline start of one column, matching the multicol column formula."""

    if count < 1:
        raise _Invalid("column count is invalid")
    product = index * (available + gap)
    if product % count != 0:
        raise _Invalid("column inline is not integral")
    return product // count


def _place_multicol(box: _Box, content_x: int, viewport_height: int | None) -> None:
    """Lay text-only children into columns and anchor them there.

    ``column-fill: auto`` with a definite height fills that content height in
    source order. A spanner balances the line above it and the next row fills
    the block size that remains. An automatic height still balances.
    """

    spec = box.multicol or {}
    if box.floats or box.positioned or box.atoms or box.inline_text:
        raise _Invalid("column content is unsupported")
    fill = str(spec.get("fill", "balance"))
    # A continuous auto fill has no column block size, so it balances.
    sizing_fill = "balance" if fill == "auto" else fill
    available = box.content_width
    preview = layout_multicol(
        available,
        [],
        column_width=spec.get("width", "auto"),
        column_count=spec.get("count", "auto"),
        column_gap=spec.get("gap", 0),
        column_fill=sizing_fill,
    )
    if preview.get("outcome") != "flowed":
        raise _Invalid(str(preview.get("reason") or "columns failed"))
    column_width = _px(preview.get("column_width"), "column width")
    if column_width < 1:
        raise _Invalid("column width is invalid")
    fragments: list[dict[str, object]] = []
    for child in box.children:
        _reject_column_child(child)
        measure = available if child.column_span == "all" else column_width
        _solve(child, measure, None, viewport_height, content_x)
        _reject_column_margin(child)
        chrome = _edge_extent(child.solved, "top", "bottom")
        content_height = 0 if child.definite_height is None else child.definite_height
        child.content_height = content_height
        child.border_height = content_height + chrome
        fragments.append({"id": child.id, "height": child.border_height, "span": child.column_span})
    if fill == "auto" and box.definite_height is not None:
        _anchor_fixed_columns(box, content_x, available, preview)
        return
    flowed = layout_multicol(
        available,
        fragments,
        column_width=spec.get("width", "auto"),
        column_count=spec.get("count", "auto"),
        column_gap=spec.get("gap", 0),
        column_fill=sizing_fill,
    )
    placed = flowed.get("boxes")
    if flowed.get("outcome") != "flowed" or not isinstance(placed, list):
        raise _Invalid(str(flowed.get("reason") or "columns failed"))
    _anchor_column_rows(box, content_x, placed, "inline", "block")
    if box.definite_height is None:
        box.definite_height = _px(flowed.get("block_size"), "column block size")
    box.anchor_laid = True


def _anchor_fixed_columns(
    box: _Box,
    content_x: int,
    available: int,
    preview: dict[str, object],
) -> None:
    """Fill a definite column block size and keep that multicol height.

    A ``column-span: all`` child balances and shortens the line above it,
    then the next row fills whatever block size remains. A row with no
    spanner still fills the whole specified size in source order.
    """

    count = _px(preview.get("column_count"), "column count")
    gap = _px((box.multicol or {}).get("gap", 0), "column gap")
    limit = box.definite_height
    if limit is None:
        raise _Invalid("column block size is indefinite")
    spec = box.multicol or {}
    cursor = 0
    rows: list[dict[str, object]] = []
    run: list[_Box] = []

    def take_row(item: dict[str, object], inline: object, block: object) -> None:
        rows.append({"id": item.get("id"), "inline": inline, "block": block})

    def flush(balance: bool) -> None:
        nonlocal cursor
        if not run:
            return
        if balance:
            flowed = layout_multicol(
                available,
                [{"id": child.id, "height": child.border_height, "span": "none"} for child in run],
                column_width=spec.get("width", "auto"),
                column_count=spec.get("count", "auto"),
                column_gap=spec.get("gap", 0),
                column_fill="balance",
            )
            placed = flowed.get("boxes")
            if flowed.get("outcome") != "flowed" or not isinstance(placed, list):
                raise _Invalid(str(flowed.get("reason") or "columns failed"))
            for item in placed:
                if not isinstance(item, dict):
                    raise _Invalid("column placement failed")
                take_row(item, item.get("inline"), cursor + _px(item.get("block"), "column block"))
            cursor += _px(flowed.get("block_size"), "column block size")
        else:
            remaining = limit - cursor if cursor < limit else 0
            fragmented = fragment_columns(
                count,
                remaining,
                [
                    {
                        "id": child.id,
                        "height": child.border_height,
                        "break_before": child.break_before,
                        "break_after": child.break_after,
                    }
                    for child in run
                ],
            )
            placed = fragmented.get("boxes")
            if fragmented.get("outcome") != "fragmented" or not isinstance(placed, list):
                raise _Invalid(str(fragmented.get("reason") or "columns failed"))
            for item in placed:
                if not isinstance(item, dict):
                    raise _Invalid("column placement failed")
                column = _px(item.get("column"), "column")
                take_row(
                    item,
                    _column_inline_offset(column, available, gap, count),
                    cursor + _px(item.get("block"), "column block"),
                )
        run.clear()

    for child in box.children:
        if child.column_span == "all":
            flush(True)
            rows.append({"id": child.id, "inline": 0, "block": cursor})
            cursor += child.border_height
            continue
        run.append(child)
    flush(False)
    _anchor_column_rows(box, content_x, rows, "inline", "block")
    box.anchor_laid = True


def _anchor_column_rows(
    box: _Box,
    content_x: int,
    placed: list[dict[str, object]],
    inline_key: str,
    block_key: str,
) -> None:
    by_id = {str(item.get("id")): item for item in placed if isinstance(item, dict)}
    origin = _px(box.solved.get("border_top"), "border-top") + _px(box.solved.get("padding_top"), "padding-top")
    for child in box.children:
        row = by_id.get(child.id)
        if row is None:
            raise _Invalid("column placement failed")
        child.x = content_x + _px(row.get(inline_key), "column inline") + child.margin_left
        child.anchor_y = origin + _px(row.get(block_key), "column block")
        child.border_width = child.content_width + _edge_extent(child.solved, "left", "right")


def _reject_column_child(child: _Box) -> None:
    if child.display != "block" or child.position != "static" or child.float_side != "none":
        raise _Invalid("column content is unsupported")
    if child.children or child.floats or child.positioned or child.atoms or child.multicol is not None:
        raise _Invalid("column content is unsupported")
    if child.writing_mode != "horizontal-tb" or child.direction != "ltr" or _mixed_runs(child):
        raise _Invalid("column content is unsupported")


def _reject_column_margin(child: _Box) -> None:
    for name in ("margin_top", "margin_right", "margin_bottom", "margin_left"):
        if _px(child.solved.get(name), name.replace("_", "-")) != 0:
            raise _Invalid("column margin is unsupported")


def _solve(
    box: _Box, parent_width: int, parent_height: int | None, viewport_height: int | None,
    parent_content_x: int, scrollport_height: int | None = None,
) -> None:
    box.containing_inline = parent_width
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
    box.min_content_height = _stored_min(solved.get("content_min_height"))
    box.max_content_height = _stored_max(solved.get("content_max_height"))
    _apply_block_aspect(box)
    box.margin_left = _px(solved.get("margin_left"), "margin-left")
    box.margin_right = _px(solved.get("margin_right"), "margin-right")
    box.x = parent_content_x + box.margin_left
    if (
        box.replaced
        and box.display == "block"
        and box.float_side == "none"
        and box.position not in {"absolute", "fixed"}
    ):
        if vertical_text or box.direction != "ltr":
            raise _Invalid("replaced writing mode is unsupported")
        _apply_replaced_block(box, parent_width, parent_height, parent_content_x)
    if vertical_text:
        if box.multicol is not None:
            raise _Invalid("column writing mode is unsupported")
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
    if box.multicol is not None and box.display == "block":
        if box.direction != "ltr":
            raise _Invalid("column writing mode is unsupported")
        _place_multicol(box, content_x, viewport_height)
        return
    if box.floats and not box.children:
        _place_floats(box, content_x)
    if not box.children and (box.inline_text or box.floats or box.atoms):
        _fill_lines(box)
    elif (
        box.list_item
        and box.marker_text
        and not box.children
        and not box.inline_text
        and not box.floats
        and not box.atoms
        and box.definite_height is None
    ):
        box.definite_height = _used_line_height(box.line_height, box.font_size)
    # Only a definite containing block, scrollport or the viewport constrains
    # an orthogonal descendant. Ordinary fixed-height ancestors do not.
    if box.overflow in {"hidden", "scroll", "auto"}:
        scrollport_height = box.definite_height
    for child in box.children:
        _solve(child, box.content_width, box.definite_height, viewport_height, content_x, scrollport_height)
    if box.floats and box.children:
        _lay_sibling_floats(box, content_x)
    _attach_list_marker(box)


def _block_properties(horizontal: bool) -> set[str]:
    logical = {"block-size", "min-block-size", "max-block-size"}
    if horizontal:
        return logical | {"height", "min-height", "max-height"}
    return logical | {"width", "min-width", "max-width"}


def _needs_basis(value: str) -> bool:
    text = " ".join(value.lower().split())
    return "%" in text or is_length_math(text)


def _stored_min(value: object) -> int:
    if value is None:
        return 0
    return _px(value, "min-height")


def _stored_max(value: object) -> int | None:
    if value is None:
        return None
    return _px(value, "max-height")


def _box_sizing(box: _Box) -> str:
    sizing = "content-box"
    for name, value in box.declarations:
        if name != "box-sizing":
            continue
        token = " ".join(value.lower().split())
        if token in {"content-box", "border-box"}:
            sizing = token
    return sizing


def _aspect_block(box: _Box) -> bool:
    return (
        box.display == "block"
        and box.float_side == "none"
        and box.position not in {"absolute", "fixed"}
        and box.writing_mode == "horizontal-tb"
        and box.multicol is None
        and box.flex is None
        and box.grid is None
        and box.table is None
    )


def _apply_block_aspect(box: _Box) -> None:
    parsed = box.aspect_ratio
    if parsed is None or box.definite_height is not None or not _aspect_block(box):
        return
    width_part, height_part, content_box = parsed
    solved = box.solved
    locked, floor = block_ratio_limits(
        content_width=box.content_width,
        horizontal_chrome=_edge_extent(solved, "left", "right"),
        vertical_chrome=_edge_extent(solved, "top", "bottom"),
        ratio=(width_part, height_part),
        content_box=content_box,
        box_sizing=_box_sizing(box),
        min_is_auto=solved.get("content_min_height") is None,
        clips=box.overflow in _SCROLLPORTS,
        min_content_height=box.min_content_height,
        max_content_height=box.max_content_height,
    )
    if locked is not None:
        box.definite_height = locked
        return
    box.min_content_height = floor


def _used_block_limits(box: _Box) -> tuple[int, int | None]:
    """Content-box floor and cap for one horizontal in-flow block.

    Flex, grid, table, multicol, float, absolute, and vertical boxes already
    publish a used height. Clamping them again would move siblings those
    formatting contexts have placed.
    """

    if (
        box.display != "block"
        or box.float_side != "none"
        or box.position in {"absolute", "fixed"}
        or box.writing_mode != "horizontal-tb"
        or box.multicol is not None
        or box.flex is not None
        or box.grid is not None
        or box.table is not None
    ):
        return 0, None
    return box.min_content_height, box.max_content_height


def _max_limit_token(value: int | None) -> int | str:
    return "none" if value is None else value


def _collapse_spec(box: _Box) -> dict[str, object]:
    solved = box.solved
    minimum, maximum = _used_block_limits(box)
    return {
        "id": box.id,
        "margin_top": _px(solved.get("margin_top"), "margin-top"),
        "margin_bottom": _px(solved.get("margin_bottom"), "margin-bottom"),
        "padding_top": _px(solved.get("padding_top"), "padding-top"),
        "padding_bottom": _px(solved.get("padding_bottom"), "padding-bottom"),
        "border_top": _px(solved.get("border_top"), "border-top"),
        "border_bottom": _px(solved.get("border_bottom"), "border-bottom"),
        "height": "auto" if box.definite_height is None else box.definite_height,
        "min_height": minimum,
        "max_height": _max_limit_token(maximum),
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
        box.content_height = box.border_height - _edge_extent(box.solved, "top", "bottom")
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
        if fl.children:
            _position_float_children(fl)
    for child in box.children:
        _assign_y(child, by_id, origin, box.y)


def _position_lines(box: _Box) -> tuple[int, int]:
    x = box.x + _edge_extent(box.solved, "left")
    y = box.y + _edge_extent(box.solved, "top")
    for line in box.lines:
        line.x += x
        line.y += y
    if box.marker is not None:
        box.marker["x"] = int(box.marker["x"]) + x
        box.marker["y"] = int(box.marker["y"]) + y
    return x, y


def _each(box: _Box):
    yield box
    for fl in box.floats:
        if fl.float_placed:
            yield from _each(fl)
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
    if box.object_box is not None:
        item["object"] = box.object_box
    if box.marker is not None:
        item["marker"] = {
            "text": box.marker["text"],
            "x": box.marker["x"],
            "y": box.marker["y"],
            "width": box.marker["width"],
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
        recorded_runs = []
        for run in line.runs:
            recorded = {
                "text": run["text"],
                "x": line.x + int(run["x"]),
                "font_size": run["font_size"],
                "width": run["width"],
            }
            if "y" in run:
                recorded["y"] = line.y + int(run["y"])
            recorded_runs.append(recorded)
        item["runs"] = recorded_runs
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
        "text-align-last": box.text_align_last,
        "text-justify": box.text_justify,
        "text-indent": box.text_indent,
        "white-space": box.white_space,
        "list-style-type": box.list_style_type,
        "list-style-position": box.list_style_position,
    }


def _set_inline(
    box: _Box, tree, element, styles, declarations, ids: set[str], counter: list[int]
) -> None:
    box.counters_closed = True
    if box.flex is not None and box.display == "flex":
        return
    if box.children and not _anonymous_split_allowed(box):
        if box.atoms:
            raise _Invalid("inline-block beside blocks is unsupported")
        return
    if box.children:
        _wrap_anonymous_blocks(box, tree, element, styles, declarations, ids, counter)
        return
    pieces = _inline_pieces(
        tree, element, styles, declarations, _fonts(box), box.atoms, box.relative_layers
    )
    if pieces is None and box.atoms:
        raise _Invalid("inline-block beside blocks is unsupported")
    box.pieces = pieces or []
    box.inline_text = None if pieces is None else "".join(piece.text for piece in pieces)
    if box.inline_text and box.positioned:
        _remember_line_static(box, tree, element, styles, declarations)


def _anonymous_split_allowed(box: _Box) -> bool:
    """In-flow blocks can wrap inline runs. A float splits those runs.

    An inline-block in the loose text rides the anonymous block. An absolute
    or fixed box still drops the loose text.
    """

    return (
        box.position in {"static", "relative"}
        and box.float_side == "none"
        and not box.positioned
        and box.display == "block"
        and box.multicol is None
        and box.flex is None
        and box.grid is None
        and box.table is None
        and box.writing_mode == "horizontal-tb"
        and box.direction == "ltr"
    )


def _wrap_anonymous_blocks(
    box: _Box, tree, element, styles, declarations, ids: set[str], counter: list[int]
) -> None:
    float_ids = {id(item.element) for item in box.floats if item.element is not None}
    segments = _inline_segments(
        tree,
        element,
        styles,
        declarations,
        _fonts(box),
        box.atoms,
        box.relative_layers,
        float_ids,
    )
    visible: list[tuple[str, list[_Piece], list[_Box]]] = []
    for kind, pieces, atoms in segments:
        if kind == "inline" and not _inline_segment_visible(pieces, atoms, box.white_space):
            continue
        visible.append((kind, pieces, atoms))
    if not any(kind == "inline" for kind, _pieces, _atoms in visible):
        if box.atoms:
            raise _Invalid("inline-block beside blocks is unsupported")
        return
    rebuilt: list[_Box] = []
    flow: list[_Box] = []
    index = 0
    floats = iter(box.floats)
    for kind, pieces, atoms in visible:
        if kind == "float":
            floated = next(floats, None)
            if floated is None:
                raise _Invalid("anonymous float split failed")
            flow.append(floated)
            continue
        if kind == "block":
            if index >= len(box.children):
                raise _Invalid("anonymous block split failed")
            child = box.children[index]
            index += 1
            rebuilt.append(child)
            flow.append(child)
            continue
        anon = _make_anonymous_block(box, pieces, atoms, ids, counter)
        if box.floats and _mixed_runs(anon):
            raise _Invalid("inline font beside a float is unsupported")
        if box.floats and _relative_pieces(anon):
            raise _Invalid("relative inline beside a float is unsupported")
        rebuilt.append(anon)
        flow.append(anon)
    if index != len(box.children) or next(floats, None) is not None:
        raise _Invalid("anonymous float split failed")
    box.children = rebuilt
    box.flow = flow
    box.atoms = []
    box.pieces = []
    box.inline_text = None


def _inline_segment_visible(pieces: list[_Piece], atoms: list[_Box], white_space: str) -> bool:
    if atoms:
        return True
    text = "".join(piece.text for piece in pieces)
    if white_space in {"pre", "pre-wrap", "break-spaces"}:
        return bool(text)
    return bool(text.strip())


def _make_anonymous_block(
    parent: _Box,
    pieces: list[_Piece],
    atoms: list[_Box],
    ids: set[str],
    counter: list[int],
) -> _Box:
    anon = _Box(
        id=_anonymous_id(ids, counter),
        writing_mode=parent.writing_mode,
        direction=parent.direction,
        text_orientation=parent.text_orientation,
        display="block",
        position="static",
        float_side="none",
        overflow="visible",
        declarations=[],
        font_size=parent.font_size,
        line_height=parent.line_height,
        text_align=parent.text_align,
        text_align_last=parent.text_align_last,
        text_justify=parent.text_justify,
        text_indent=parent.text_indent,
        white_space=parent.white_space,
        parent_direction=parent.direction,
        anonymous=True,
        parent_box=parent,
        pieces=pieces,
        atoms=atoms,
        inline_text="".join(piece.text for piece in pieces),
    )
    return anon


def _anonymous_id(ids: set[str], counter: list[int]) -> str:
    while True:
        counter[0] += 1
        box_id = f"anon-{counter[0]}"
        if box_id not in ids:
            ids.add(box_id)
            return box_id


def _inline_segments(
    tree,
    element,
    styles,
    declarations,
    fonts: dict[str, str],
    atoms: list[_Box],
    layers_of: dict[int, _Shift],
    float_ids: set[int] | None = None,
) -> list[tuple[str, list[_Piece], list[_Box]]]:
    """Split one element's inline stream on its in-flow block children.

    A float in ``float_ids`` is its own marker, so the text before that float
    and the text after it become different anonymous blocks.
    """

    floats = float_ids or set()
    stream = iter(atoms)
    segments: list[tuple[str, list[_Piece], list[_Box]]] = []
    pieces: list[_Piece] = []
    used: list[_Box] = []
    block_size = _positive_px(fonts["font-size"], "font-size")
    block_leading = fonts["line-height"]

    def flush() -> None:
        nonlocal pieces, used
        if pieces or used:
            segments.append(("inline", pieces, used))
            pieces = []
            used = []

    def add(text: str, size: int, leading: str, layers: tuple[_Shift, ...]) -> None:
        nonlocal pieces
        if not text:
            return
        if layers and (size != block_size or leading != block_leading):
            raise _Invalid("relative inline font is unsupported")
        if (
            pieces
            and pieces[-1].atom is None
            and pieces[-1].font_size == size
            and pieces[-1].line_height == leading
            and pieces[-1].shifts == layers
        ):
            pieces[-1].text += text
            return
        pieces.append(_Piece(text, size, leading, shifts=layers))

    def walk(node, parent_fonts: dict[str, str], inherited: tuple[_Shift, ...]) -> None:
        own = layers_of.get(id(node))
        layers = inherited + ((own,) if own is not None else ())
        size = _positive_px(parent_fonts["font-size"], "font-size")
        leading = parent_fonts["line-height"]
        before, after = _generated(tree, node)
        add(before + (node.text or ""), size, leading, layers)
        for child in list(node):
            if not _local_name(child):
                continue
            kind = _flow_kind(tree, child, styles, declarations)
            if id(child) in floats:
                flush()
                segments.append(("float", [], []))
                add(child.tail or "", size, leading, layers)
                continue
            if kind in {"skip", "out"}:
                add(child.tail or "", size, leading, layers)
                continue
            if kind == "contents":
                walk(child, _inline_fonts(tree, child, styles, declarations, parent_fonts), layers)
                add(child.tail or "", size, leading, layers)
                continue
            if kind == "inline-block":
                if layers:
                    raise _Invalid("relative inline content is unsupported")
                try:
                    atom = next(stream)
                except StopIteration as exc:
                    raise _Invalid("inline-block is unsupported") from exc
                pieces.append(_Piece("", size, leading, atom))
                used.append(atom)
                add(child.tail or "", size, leading, layers)
                continue
            if kind == "block":
                flush()
                segments.append(("block", [], []))
                add(child.tail or "", size, leading, layers)
                continue
            _reject_inline_type(tree, child, styles, declarations)
            walk(child, _inline_fonts(tree, child, styles, declarations, parent_fonts), layers)
            add(child.tail or "", size, leading, layers)
        add(after, size, leading, layers)

    walk(element, fonts, ())
    flush()
    if next(stream, None) is not None:
        raise _Invalid("inline-block is unsupported")
    return segments


def _inline_pieces(
    tree,
    element,
    styles,
    declarations,
    fonts: dict[str, str],
    atoms: list[_Box],
    layers_of: dict[int, _Shift],
) -> list[_Piece] | None:
    stream = iter(atoms)
    pieces: list[_Piece] = []
    block_size = _positive_px(fonts["font-size"], "font-size")
    block_leading = fonts["line-height"]

    def add(text: str, size: int, leading: str, layers: tuple[_Shift, ...]) -> None:
        if not text:
            return
        if layers and (size != block_size or leading != block_leading):
            raise _Invalid("relative inline font is unsupported")
        if (
            pieces
            and pieces[-1].atom is None
            and pieces[-1].font_size == size
            and pieces[-1].line_height == leading
            and pieces[-1].shifts == layers
        ):
            pieces[-1].text += text
            return
        pieces.append(_Piece(text, size, leading, shifts=layers))

    def walk(node, parent_fonts: dict[str, str], inherited: tuple[_Shift, ...]) -> bool:
        own = layers_of.get(id(node))
        layers = inherited + ((own,) if own is not None else ())
        size = _positive_px(parent_fonts["font-size"], "font-size")
        leading = parent_fonts["line-height"]
        before, after = _generated(tree, node)
        add(before + (node.text or ""), size, leading, layers)
        for child in list(node):
            if not _local_name(child):
                continue
            kind = _flow_kind(tree, child, styles, declarations)
            if kind in {"skip", "out"}:
                add(child.tail or "", size, leading, layers)
                continue
            if kind == "contents":
                if not walk(child, _inline_fonts(tree, child, styles, declarations, parent_fonts), layers):
                    return False
                add(child.tail or "", size, leading, layers)
                continue
            if kind == "inline-block":
                if layers:
                    raise _Invalid("relative inline content is unsupported")
                try:
                    atom = next(stream)
                except StopIteration as exc:
                    raise _Invalid("inline-block is unsupported") from exc
                pieces.append(_Piece("", size, leading, atom))
                add(child.tail or "", size, leading, layers)
                continue
            if kind == "block":
                return False
            _reject_inline_type(tree, child, styles, declarations)
            if not walk(child, _inline_fonts(tree, child, styles, declarations, parent_fonts), layers):
                return False
            add(child.tail or "", size, leading, layers)
        add(after, size, leading, layers)
        return True

    if not walk(element, fonts, ()):
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
        "text-align-last": parent["text-align-last"],
        "text-justify": parent["text-justify"],
        "white-space": parent["white-space"],
    }


def _flow_kind(tree, element, styles, declarations) -> str:
    if _local_name(element) in _SKIP_TAGS:
        return "skip"
    custom = styles.get(element, ({}, ""))[0]
    winners = _winners(tree, element, declarations)
    display = _keyword(
        _declared(winners, "display", custom),
        _FLOW_DISPLAYS,
        "block" if _local_name(element) in _BLOCK_TAGS else "inline",
        "display",
    )
    if display == "list-item":
        display = "block"
    position = _keyword(_declared(winners, "position", custom), _POSITIONS, "static", "position")
    float_side = _keyword(_declared(winners, "float", custom), _FLOATS, "none", "float")
    if display == "none":
        return "out"
    if display == "contents":
        return "contents"
    if position in {"absolute", "fixed"} or float_side != "none":
        return "out"
    if display == "inline" and position == "static" and _local_name(element) in _REPLACED_TAGS:
        return "inline-block"
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


def _read_text_indent(value: str | None, parent: str) -> str:
    """Specified indent. A percentage is kept so a child resolves its own block."""

    if value is None or value.strip().lower() in {"inherit", "unset", "revert"}:
        return parent
    if value.strip().lower() == "initial":
        return "0px"
    text = " ".join(value.strip().lower().split())
    if "hanging" in text or "each-line" in text or " " in text:
        raise _Invalid("text-indent is unsupported")
    if text.endswith("px"):
        try:
            number = float(text[:-2])
        except ValueError as exc:
            raise _Invalid("text-indent is invalid") from exc
        return f"{_px(number, 'text-indent')}px"
    if text.endswith("%"):
        try:
            number = float(text[:-1])
        except ValueError as exc:
            raise _Invalid("text-indent is invalid") from exc
        if number != number or number in {float("inf"), float("-inf")}:
            raise _Invalid("text-indent is invalid")
        if number == 0:
            return "0px"
        return f"{_px(number, 'text-indent')}%"
    raise _Invalid("text-indent is invalid")


def _text_indent_used(box: _Box) -> int:
    raw = box.text_indent
    if raw == "0px":
        return 0
    if box.writing_mode != "horizontal-tb" or box.direction != "ltr":
        raise _Invalid("text-indent writing mode is unsupported")
    if raw.endswith("%"):
        basis = box.containing_inline
        if basis is None and box.parent_box is not None:
            basis = box.parent_box.content_width
        if basis is None:
            raise _Invalid("text-indent percentage is indefinite")
        return _px(float(raw[:-1]) * basis / 100.0, "text-indent")
    if raw.endswith("px"):
        return _px(float(raw[:-2]), "text-indent")
    raise _Invalid("text-indent is invalid")


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


def _plan_has_counter(parts: list) -> bool:
    return any(isinstance(part, tuple) and part and part[0] in {"counter", "counters"} for part in parts)


def _plan_text(parts: list) -> str:
    return "".join(part[1] for part in parts if isinstance(part, tuple) and part and part[0] == "text")


def _element_has_counter_plan(tree, element) -> bool:
    plans = getattr(tree, "generated_plans", None)
    if not isinstance(plans, dict):
        return False
    pair = plans.get(id(element))
    return isinstance(pair, tuple) and any(_plan_has_counter(side) for side in pair)


def _generated(tree, element) -> tuple[str, str]:
    plans = getattr(tree, "generated_plans", None)
    if isinstance(plans, dict) and id(element) in plans:
        planned = plans[id(element)]
        pair = _realize_counter_content(tree, element, planned)
        plans.pop(id(element), None)
        found = getattr(tree, "generated", None)
        if not isinstance(found, dict):
            found = {}
            tree.generated = found
        found[id(element)] = pair
        return pair
    found = getattr(tree, "generated", None)
    if not isinstance(found, dict):
        return "", ""
    pair = found.get(id(element))
    if not isinstance(pair, tuple) or len(pair) != 2:
        return "", ""
    return str(pair[0]), str(pair[1])


_COUNTER_CONTENT_DISPLAYS = frozenset({"flex", "grid", "table", "table-row", "table-cell", "table-caption"})


def _in_counter_tree(box: _Box) -> bool:
    if box.root:
        return True
    parent = box.parent_box
    if parent is None:
        return False
    return any(child is box for child in parent.counter_children)


def _realize_counter_content(tree, element, planned: tuple) -> tuple[str, str]:
    boxes = getattr(tree, "box_of", None)
    box = boxes.get(id(element)) if isinstance(boxes, dict) else None
    if (
        not isinstance(box, _Box)
        or not box.counters_closed
        or not _in_counter_tree(box)
        or box.display in _COUNTER_CONTENT_DISPLAYS
    ):
        raise _Invalid("generated counter is unsupported")
    if box.display == "inline" and box.element is not None:
        if any(_local_name(child) and _local_name(child) not in _SKIP_TAGS for child in list(box.element)):
            raise _Invalid("generated counter is unsupported")
    root = box
    while root.parent_box is not None:
        root = root.parent_box
    resolved = resolve_counters(_counter_payload(root))
    if resolved.get("outcome") != "ok" or not isinstance(resolved.get("elements"), dict):
        raise _Invalid(str(resolved.get("reason") or "generated counter is unsupported"))
    elements = resolved["elements"]
    before, after = planned
    return (
        _render_counter_parts(before, elements, box, "before"),
        _render_counter_parts(after, elements, box, "after"),
    )


def _render_counter_parts(parts, elements: dict, box: _Box, side: str) -> str:
    if not isinstance(parts, list) or not parts:
        return ""
    state = None
    if _plan_has_counter(parts):
        state = elements.get(f"\x1f{side}\x1f{box.id}")
        if not isinstance(state, dict):
            raise _Invalid("generated counter is unsupported")
    values = state.get("values") if isinstance(state, dict) else {}
    stacks = state.get("stacks") if isinstance(state, dict) else {}
    if not isinstance(values, dict):
        values = {}
    if not isinstance(stacks, dict):
        stacks = {}
    chunks: list[str] = []
    for part in parts:
        if not isinstance(part, tuple) or not part:
            raise _Invalid("generated counter is unsupported")
        if part[0] == "text":
            chunks.append(str(part[1]))
            continue
        if part[0] == "counter":
            rendered = format_counter(values.get(part[1]), part[2])
        elif part[0] == "counters":
            stack = stacks.get(part[1])
            rendered = format_counters(stack if isinstance(stack, list) else None, part[2], part[3])
        else:
            raise _Invalid("generated counter is unsupported")
        if rendered.get("outcome") != "ok":
            raise _Invalid(str(rendered.get("reason") or "generated counter is unsupported"))
        chunks.append(str(rendered.get("text") or ""))
    return "".join(chunks)


def _counter_pseudo(box: _Box, side: str, parts) -> dict[str, object] | None:
    if not isinstance(parts, list):
        return None
    reads = [part[1] for part in parts if isinstance(part, tuple) and part and part[0] in {"counter", "counters"}]
    if not reads:
        return None
    return {"id": f"\x1f{side}\x1f{box.id}", "display": "inline", "read": reads}


def _leaf_generated(tree, element) -> str:
    before, after = _generated(tree, element)
    return before + (getattr(element, "text", None) or "") + after


def _float_loose_text(tree, element, white_space: str) -> bool:
    before, after = _generated(tree, element)
    chunks = [before, element.text or "", after]
    for node in list(element):
        chunks.append(node.tail or "")
    raw = "".join(chunks)
    if white_space in {"pre", "pre-wrap", "break-spaces"}:
        return raw != ""
    return any(not character.isspace() for character in raw)


def _float_block_child(box: _Box) -> bool:
    if (
        box.display != "block"
        or box.float_side != "none"
        or box.position != "static"
        or box.writing_mode != "horizontal-tb"
        or box.direction != "ltr"
        or box.floats
        or box.positioned
        or box.atoms
        or box.multicol is not None
        or box.flex is not None
        or box.grid is not None
        or box.table is not None
        or box.anonymous
    ):
        return False
    return all(_float_block_child(child) for child in box.children)


def _iter_float_descendants(box: _Box):
    for child in box.children:
        yield child
        yield from _iter_float_descendants(child)


def _specified_margin_px(value: str | None, *, reason: str = "float content is unsupported") -> int:
    """Specified horizontal margin. Auto does not enlarge a shrink-to-fit box."""

    if value is None:
        return 0
    text = value.strip().lower()
    if text in {"auto", "initial", "unset", "revert"}:
        return 0
    if not text.endswith("px"):
        raise _Invalid(reason)
    return _px(float(text[:-2]), "margin")


def _resolve_float_child(
    box: _Box, containing: int, *, reason: str = "float content is unsupported"
) -> dict[str, object]:
    solved = resolve_logical_box(
        box.declarations,
        writing_mode=box.writing_mode,
        direction=box.direction,
        text_orientation=box.text_orientation,
        containing_inline=containing,
        percentage_basis=containing,
        containing_block=None,
    )
    if solved.get("outcome") != "resolved":
        raise _Invalid(str(solved.get("reason") or reason))
    return solved


def _float_child_span(box: _Box, *, reason: str = "float content is unsupported") -> tuple[int, int]:
    if any(prop == "box-sizing" and value.strip().lower() == "border-box" for prop, value in box.declarations):
        raise _Invalid(reason)
    if _has_explicit_limit(box, _WIDTH_LIMITS):
        raise _Invalid(reason)
    narrow = _resolve_float_child(box, 0, reason=reason)
    wide = _resolve_float_child(box, 10000, reason=reason)
    for key in ("padding_left", "padding_right", "border_left", "border_right"):
        if narrow.get(key) != wide.get(key):
            raise _Invalid(reason)
    slots = _cascade(box.declarations, _writing_flow(box))
    start = "left" if box.direction != "rtl" else "right"
    end = "right" if start == "left" else "left"
    margins = _specified_margin_px(slots.get(f"margin-{start}"), reason=reason) + _specified_margin_px(
        slots.get(f"margin-{end}"), reason=reason
    )
    chrome = margins + sum(
        _px(narrow.get(key), key.replace("_", "-"))
        for key in ("padding_left", "padding_right", "border_left", "border_right")
    )
    specified = narrow.get("specified_width")
    if _specified_auto(specified):
        if box.children:
            pairs = [_float_child_span(child, reason=reason) for child in box.children]
            inner_min = max(item[0] for item in pairs)
            inner_max = max(item[1] for item in pairs)
        else:
            inner_min, inner_max = _intrinsic_text_sizes(box)
    elif "%" in str(specified) or narrow.get("content_width") != wide.get("content_width"):
        raise _Invalid(reason)
    else:
        inner_min = inner_max = _px(narrow.get("content_width"), "width")
    return inner_min + chrome, inner_max + chrome


def _absolute_content_span(box: _Box) -> tuple[int, int]:
    """Min-content and max-content of an absolute box from its block children."""

    pairs = [
        _float_child_span(child, reason="absolute shrink-to-fit is unsupported") for child in box.children
    ]
    return max(item[0] for item in pairs), max(item[1] for item in pairs)


def _lay_float_blocks(fl: _Box) -> None:
    for child in fl.children:
        _solve(child, fl.content_width, fl.definite_height, None, 0)
    spec = _collapse_spec(fl)
    spec["float"] = fl.float_side
    spec["margin_top"] = 0
    spec["margin_bottom"] = 0
    spec["min_height"] = 0
    spec["max_height"] = "none"
    spec["height"] = "auto" if fl.definite_height is None else fl.definite_height
    placed = place_collapsed_margins(spec)
    rows = placed.get("boxes") if placed.get("outcome") == "placed" else None
    if not isinstance(rows, list):
        raise _Invalid(str(placed.get("reason") or "float content failed"))
    by_id = {str(item.get("id")): item for item in rows if isinstance(item, dict)}
    own = by_id.get(fl.id)
    if own is None:
        raise _Invalid("float content failed")
    fl.border_height = _px(own.get("border_height"), "border height")
    vertical = _edge_extent(fl.solved, "top", "bottom")
    fl.content_height = fl.border_height - vertical
    if fl.content_height < 0:
        raise _Invalid("content height is invalid")
    fl.definite_height = fl.content_height
    for child in _iter_float_descendants(fl):
        row = by_id.get(child.id)
        if row is None:
            raise _Invalid("float content failed")
        child.anchor_y = _px(row.get("y"), "y")
        child.border_height = _px(row.get("border_height"), "border height")
        child.border_width = child.content_width + _edge_extent(child.solved, "left", "right")
        child.content_height = child.border_height - _edge_extent(child.solved, "top", "bottom")
        if child.content_height < 0:
            raise _Invalid("content height is invalid")


def _position_float_children(fl: _Box) -> None:
    origin_x = fl.x + _edge_extent(fl.solved, "left")
    for child in _iter_float_descendants(fl):
        if child.anchor_y is None:
            raise _Invalid("float content failed")
        child.x += origin_x
        child.y = fl.y + child.anchor_y
        child.flow_y = child.y
        _position_lines(child)


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


def _inline_shift(box: _Box) -> _Shift:
    direction = box.direction if box.direction in {"ltr", "rtl"} else "ltr"
    if any(_decl_percent_inset(prop, value) for prop, value in box.declarations):
        values = _physical_percent_insets(box)
    else:
        slots = _physical_slots(box)
        values = {side: _inset(slots, side) for side in ("left", "right", "top", "bottom")}
    return _Shift(direction, values["left"], values["right"], values["top"], values["bottom"])


def _decl_percent_inset(prop: str, value: str) -> bool:
    name = prop.strip().lower()
    if name not in {"top", "right", "bottom", "left"} and not name.startswith("inset"):
        return False
    return "%" in value


def _physical_percent_insets(box: _Box) -> dict[str, str]:
    """Physical inset longhands, including percentages the box solver rejects."""

    values = {side: "auto" for side in ("top", "right", "bottom", "left")}
    for prop, raw in box.declarations:
        name = prop.strip().lower()
        if name.startswith("inset"):
            raise _Invalid("relative inline is unsupported")
        if name not in values:
            continue
        text = " ".join(raw.split()).lower()
        if text in {"auto", "initial", "unset", "revert"}:
            values[name] = "auto"
            continue
        if text.endswith("px") or text.endswith("%"):
            values[name] = text
            continue
        raise _Invalid("inset is invalid")
    return values


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
    if box.marker is not None:
        box.marker["x"] = int(box.marker["x"]) + dx
        box.marker["y"] = int(box.marker["y"]) + dy
    for fl in box.floats:
        if fl.float_placed:
            _translate(fl, dx, dy)
    for child in box.children:
        _translate(child, dx, dy)
    if box.anonymous:
        for atom in box.atoms:
            _translate(atom, dx, dy)


def _shift_stickies(
    box: _Box,
    viewport_width: int,
    viewport_height: int | None,
    scroll_x: int,
    scroll_y: int,
) -> None:
    if box.position == "sticky":
        if box.writing_mode != "horizontal-tb" or box.direction != "ltr":
            raise _Invalid("sticky writing mode is unsupported")
        if box.float_side != "none":
            raise _Invalid("sticky float is unsupported")
        if _sticky_descendant(box):
            raise _Invalid("nested sticky is unsupported")
        _translate(box, *_sticky_delta(box, viewport_width, viewport_height, scroll_x, scroll_y))
    for child in box.children:
        _shift_stickies(child, viewport_width, viewport_height, scroll_x, scroll_y)
    for fl in box.floats:
        _shift_stickies(fl, viewport_width, viewport_height, scroll_x, scroll_y)
    for atom in box.atoms:
        _shift_stickies(atom, viewport_width, viewport_height, scroll_x, scroll_y)
    for abs_box in box.positioned:
        _shift_stickies(abs_box, viewport_width, viewport_height, scroll_x, scroll_y)


def _sticky_descendant(box: _Box) -> bool:
    pending = [*box.children, *box.floats, *box.atoms, *box.positioned]
    while pending:
        current = pending.pop()
        if current.position == "sticky":
            return True
        pending.extend(current.children)
        pending.extend(current.floats)
        pending.extend(current.atoms)
        pending.extend(current.positioned)
    return False


def _sticky_delta(
    box: _Box,
    viewport_width: int,
    viewport_height: int | None,
    scroll_x: int,
    scroll_y: int,
) -> tuple[int, int]:
    parent = box.parent_box
    if parent is None:
        raise _Invalid("sticky root is unsupported")
    port_x, port_y, port_w, port_h, port_scroll_x, port_scroll_y = _sticky_port(
        box, viewport_width, viewport_height, scroll_x, scroll_y
    )
    cb_x, cb_y, cb_w, cb_h = _padding_rect(parent)
    slots = _physical_slots(box)
    return (
        _sticky_axis(
            box.x,
            box.border_width,
            port_x,
            port_w,
            port_scroll_x,
            cb_x,
            cb_x + cb_w,
            _sticky_length(_inset(slots, "left"), port_w, "left"),
            _sticky_length(_inset(slots, "right"), port_w, "right"),
        ),
        _sticky_axis(
            box.y,
            box.border_height,
            port_y,
            port_h,
            port_scroll_y,
            cb_y,
            cb_y + cb_h,
            _sticky_length(_inset(slots, "top"), port_h, "top"),
            _sticky_length(_inset(slots, "bottom"), port_h, "bottom"),
        ),
    )


def _sticky_port(
    box: _Box,
    viewport_width: int,
    viewport_height: int | None,
    scroll_x: int,
    scroll_y: int,
) -> tuple[int, int, int, int, int, int]:
    current = box.parent_box
    while current is not None:
        if current.overflow in _SCROLLPORTS:
            x, y, width, height = _padding_rect(current)
            return x, y, width, height, 0, 0
        current = current.parent_box
    if viewport_height is None:
        raise _Invalid("sticky scrollport is indefinite")
    return 0, 0, viewport_width, viewport_height, scroll_x, scroll_y


def _padding_rect(box: _Box) -> tuple[int, int, int, int]:
    top = _px(box.solved.get("border_top"), "border-top")
    right = _px(box.solved.get("border_right"), "border-right")
    bottom = _px(box.solved.get("border_bottom"), "border-bottom")
    left = _px(box.solved.get("border_left"), "border-left")
    width = box.border_width - left - right
    height = box.border_height - top - bottom
    if width < 0 or height < 0:
        raise _Invalid("sticky containing block is invalid")
    return box.x + left, box.y + top, width, height


def _sticky_length(raw: str, basis: int, name: str) -> object:
    text = " ".join(raw.strip().lower().split())
    if text in {"auto", "initial", "unset", "revert"}:
        return "auto"
    try:
        if text.endswith("px"):
            return _px(float(text[:-2]), name)
        if text.endswith("%"):
            return _px(basis * float(text[:-1]) / 100, name)
    except (TypeError, ValueError) as exc:
        raise _Invalid(f"{name} is invalid") from exc
    raise _Invalid(f"{name} is invalid")


def _sticky_axis(
    origin: int,
    size: int,
    port_origin: int,
    port_size: int,
    scroll: int,
    containing_start: int,
    containing_end: int,
    start: object,
    end: object,
) -> int:
    found = sticky_offset(
        origin,
        size,
        port_size,
        containing_start,
        containing_end,
        scroll=scroll,
        port_origin=port_origin,
        start=start,
        end=end,
    )
    if found.get("outcome") != "resolved":
        raise _Invalid(str(found.get("reason") or "sticky position failed"))
    return _px(found.get("offset"), "sticky offset")


def _padding_edge(box: _Box) -> _Edge:
    border_left = _px(box.solved.get("border_left"), "border-left")
    border_top = _px(box.solved.get("border_top"), "border-top")
    pad_left = _px(box.solved.get("padding_left"), "padding-left")
    pad_right = _px(box.solved.get("padding_right"), "padding-right")
    pad_top = _px(box.solved.get("padding_top"), "padding-top")
    pad_bottom = _px(box.solved.get("padding_bottom"), "padding-bottom")
    height = None if box.definite_height is None else box.definite_height + pad_top + pad_bottom
    return _Edge(box.x + border_left, box.y + border_top, pad_left + box.content_width + pad_right, height)


def _dashed_ident(token: str) -> bool:
    if len(token) < 3 or not token.startswith("--"):
        return False
    body = token[2:]
    first = body[0]
    if not first.isascii() or not (first.isalpha() or first == "_"):
        return False
    return all(char.isascii() and (char.isalnum() or char in "_-") for char in body)


def _read_anchor_name(winners, custom: dict) -> str:
    value = _declared(winners, "anchor-name", custom)
    if value is None:
        return ""
    token = " ".join(value.split())
    lowered = token.lower()
    if lowered in {"initial", "unset", "revert", "none"}:
        return ""
    if lowered == "inherit":
        raise _Invalid("anchor-name inherit is unsupported")
    if "," in token or " " in token:
        raise _Invalid("anchor-name is unsupported")
    if not _dashed_ident(token):
        raise _Invalid("anchor-name is invalid")
    return token


def _read_position_anchor(
    winners,
    custom: dict,
    position: str,
    writing_mode: str,
    direction: str,
) -> tuple[str, str]:
    anchor_value = _declared(winners, "position-anchor", custom)
    area_value = _declared(winners, "position-area", custom)
    anchor = "" if anchor_value is None else " ".join(anchor_value.split())
    area = "" if area_value is None else " ".join(area_value.split()).lower()
    if anchor.lower() in {"", "initial", "unset", "revert", "auto"}:
        anchor = ""
    elif anchor.lower() == "inherit":
        raise _Invalid("position-anchor inherit is unsupported")
    elif "," in anchor or " " in anchor or not _dashed_ident(anchor):
        raise _Invalid("position-anchor is invalid")
    if area in {"", "initial", "unset", "revert", "none"}:
        area = ""
    elif area == "inherit":
        raise _Invalid("position-area inherit is unsupported")
    if not anchor and not area:
        return "", ""
    if position not in {"absolute", "fixed"} or writing_mode != "horizontal-tb" or direction != "ltr":
        raise _Invalid("position-area is unsupported")
    if not anchor or not area:
        raise _Invalid("position-area is unsupported")
    return anchor, area


def _anchor_index(root: _Box) -> dict[str, _Box]:
    found: dict[str, _Box] = {}

    def walk(box: _Box) -> None:
        if box.anchor_name:
            if box.anchor_name in found:
                raise _Invalid("anchor-name is duplicated")
            found[box.anchor_name] = box
        for child in (*box.children, *box.floats, *box.atoms, *box.positioned):
            walk(child)

    walk(root)
    return found


def _box_contains(ancestor: _Box, node: _Box) -> bool:
    current: _Box | None = node
    while current is not None:
        if current is ancestor:
            return True
        current = current.parent_box
    return False


def _align_to_anchor(box: _Box, cb: _Edge, anchors: dict[str, _Box]) -> None:
    """Move an absolute or fixed border box onto its named anchor area."""

    if not box.position_area:
        return
    if box.writing_mode != "horizontal-tb" or box.direction != "ltr":
        raise _Invalid("position-area is unsupported")
    name = box.position_anchor
    anchor = anchors.get(name)
    if anchor is None:
        raise _Invalid("default anchor is missing")
    if anchor.position in {"absolute", "fixed"} or anchor.float_side != "none":
        raise _Invalid("anchor is out of flow")
    if anchor.writing_mode != "horizontal-tb" or anchor.direction != "ltr":
        raise _Invalid("position-area is unsupported")
    if _box_contains(box, anchor):
        raise _Invalid("anchor is inside the positioned box")
    if cb.height is None:
        raise _Invalid("anchor containing block is indefinite")
    placed = place_anchored(
        {
            "x": cb.x,
            "y": cb.y,
            "width": cb.width,
            "height": cb.height,
            "writing_mode": "horizontal-tb",
            "direction": "ltr",
        },
        {
            "x": anchor.x,
            "y": anchor.y,
            "width": anchor.border_width,
            "height": anchor.border_height,
            "writing_mode": "horizontal-tb",
            "direction": "ltr",
        },
        {
            "width": box.border_width,
            "height": box.border_height,
            "margin_top": _px(box.solved.get("margin_top"), "margin-top"),
            "margin_right": box.margin_right,
            "margin_bottom": _px(box.solved.get("margin_bottom"), "margin-bottom"),
            "margin_left": box.margin_left,
            "position_area": box.position_area,
            "writing_mode": "horizontal-tb",
            "direction": "ltr",
        },
    )
    if placed.get("outcome") != "placed":
        raise _Invalid(str(placed.get("reason") or "position-area failed"))
    _translate(box, _px(placed.get("x"), "x") - box.x, _px(placed.get("y"), "y") - box.y)


_CAPTURE_DISPLAYS = frozenset(
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
_CAPTURE_DEFAULTS = {
    "transform": "none",
    "filter": "none",
    "perspective": "none",
    "backdrop_filter": "none",
    "contain": "none",
    "content_visibility": "visible",
    "will_change": "auto",
}
_CAPTURE_NAMES = {
    "transform": "transform",
    "filter": "filter",
    "perspective": "perspective",
    "backdrop_filter": "backdrop-filter",
    "contain": "contain",
    "content_visibility": "content-visibility",
    "will_change": "will-change",
}


def _capture_token(value: str | None, *, default: str, name: str) -> str:
    if value is None or value in {"initial", "unset", "revert", "revert-layer"}:
        return default
    if value == "inherit":
        raise _Invalid(f"{name} inherit is unsupported")
    token = " ".join(value.strip().lower().split())
    if not token:
        raise _Invalid(f"{name} is invalid")
    return token


def _read_capture(winners, custom: dict) -> dict[str, str]:
    values = {
        key: _capture_token(_declared(winners, css_name, custom), default=default, name=css_name)
        for key, css_name, default in (
            (key, _CAPTURE_NAMES[key], _CAPTURE_DEFAULTS[key]) for key in _CAPTURE_DEFAULTS
        )
    }
    found = resolve_containing_block(
        {
            "id": "host",
            "display": "block",
            "position": "static",
            "width": 10,
            "height": 10,
            **values,
            "children": [
                {"id": "child", "position": "absolute", "display": "block", "width": 1, "height": 1}
            ],
        },
        "child",
        viewport={"x": 0, "y": 0, "width": 10, "height": 10},
    )
    if found.get("outcome") != "resolved":
        reason = str(found.get("reason") or "containing block failed")
        css_name = _CAPTURE_NAMES.get(reason, reason.replace("_", "-"))
        raise _Invalid(f"{css_name} is invalid")
    return values


def _capture_effect(box: _Box) -> bool:
    values = {**_CAPTURE_DEFAULTS, **box.capture}
    found = resolve_containing_block(
        {
            "id": "host",
            "display": "block",
            "position": "static",
            "width": 10,
            "height": 10,
            **values,
            "children": [
                {"id": "child", "position": "absolute", "display": "block", "width": 1, "height": 1}
            ],
        },
        "child",
        viewport={"x": 0, "y": 0, "width": 10, "height": 10},
    )
    return found.get("source") == "ancestor"


def _capture_display(display: str) -> str:
    if display in _CAPTURE_DISPLAYS:
        return display
    return "block"


def _capture_border(box: _Box, key: str) -> int:
    value = box.solved.get(key)
    if value is None:
        return 0
    return _px(value, key)


def _capture_tree(box: _Box) -> dict[str, object]:
    payload: dict[str, object] | None = None
    current: _Box | None = box
    seen: set[int] = set()
    while current is not None:
        marker = id(current)
        if marker in seen:
            raise _Invalid("containing block failed")
        seen.add(marker)
        values = {**_CAPTURE_DEFAULTS, **current.capture}
        node: dict[str, object] = {
            "id": current.id,
            "position": current.position,
            "display": _capture_display(current.display),
            "x": current.x,
            "y": current.y,
            "width": max(current.border_width, 0),
            "height": max(current.border_height, 0),
            **values,
        }
        for side in ("top", "right", "bottom", "left"):
            node[f"border_{side}"] = _capture_border(current, f"border_{side}")
        if payload is not None:
            node["children"] = [payload]
        payload = node
        current = current.parent_box
    if payload is None:
        raise _Invalid("containing block failed")
    return payload


def _captured_edge(box: _Box, viewport: _Edge) -> _Edge:
    found = resolve_containing_block(
        _capture_tree(box),
        box.id,
        viewport={
            "x": viewport.x,
            "y": viewport.y,
            "width": viewport.width,
            "height": 0 if viewport.height is None else viewport.height,
        },
    )
    if found.get("outcome") != "resolved":
        raise _Invalid(str(found.get("reason") or "containing block failed"))
    if found.get("source") != "ancestor":
        return viewport
    ancestor_id = found.get("ancestor")
    current = box.parent_box
    while current is not None and current.id != ancestor_id:
        current = current.parent_box
    if current is None:
        raise _Invalid("containing block failed")
    return _padding_edge(current)


def _place_positioned(
    box: _Box,
    viewport: _Edge,
    anchors: dict[str, _Box] | None = None,
) -> None:
    if anchors is None:
        anchors = _anchor_index(box)
    for abs_box in box.positioned:
        cb = _captured_edge(abs_box, viewport)
        _place_one_absolute(abs_box, cb, box)
        _align_to_anchor(abs_box, cb, anchors)
    for child in box.children:
        _place_positioned(child, viewport, anchors)


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


def _reject_abs_block(box: _Box) -> None:
    """Keep an absolute formatting context to static horizontal blocks."""

    if box.display != "block" or box.position != "static" or box.float_side != "none":
        raise _Invalid("positioned content is unsupported")
    if box.writing_mode != "horizontal-tb" or box.direction != "ltr":
        raise _Invalid("positioned content is unsupported")
    if box.floats or box.positioned or box.atoms or box.multicol is not None:
        raise _Invalid("positioned content is unsupported")
    if box.flex is not None or box.grid is not None or box.table is not None:
        raise _Invalid("positioned content is unsupported")
    if box.children and box.inline_text:
        raise _Invalid("positioned content is unsupported")
    for child in box.children:
        _reject_abs_block(child)


def _shift_x(box: _Box, delta: int) -> None:
    if delta == 0:
        return
    box.x += delta
    for child in box.children:
        _shift_x(child, delta)


def _paint_anchored(box: _Box, border_at: int) -> None:
    if box.anchor_y is None:
        raise _Invalid("placed box is missing")
    box.y = border_at + box.anchor_y
    box.flow_y = box.y
    box.border_width = box.content_width + _edge_extent(box.solved, "left", "right")
    if box.content_height < 0:
        raise _Invalid("content height is invalid")
    _position_lines(box)
    for child in box.children:
        _paint_anchored(child, box.y)


def _adopt_absolute(box: _Box, cb: _Edge, placed: dict[str, object]) -> None:
    box.x = cb.x + _px(placed.get("x"), "x")
    box.y = cb.y + _px(placed.get("y"), "y")
    box.content_width = _px(placed.get("width"), "content width")
    box.content_height = _px(placed.get("height"), "content height")
    box.border_width = _px(placed.get("border_box_width"), "border width")
    box.border_height = _px(placed.get("border_box_height"), "border height")
    box.margin_left = _px(placed.get("margin_left"), "margin-left")
    box.margin_right = _px(placed.get("margin_right"), "margin-right")
    box.solved = placed


def _remember_line_static(box: _Box, tree, element, styles, declarations) -> None:
    """Record where each inline absolute would have started in this line."""

    if not _line_static_parent(box):
        return
    anchor = {
        "font-size": f"{box.font_size}px",
        "line-height": box.line_height,
        "text-align": box.text_align,
        "text-align-last": box.text_align_last,
        "text-justify": box.text_justify,
        "white-space": box.white_space,
    }
    for abs_box in box.positioned:
        abs_box.line_static = None
        if abs_box.display != "inline" or abs_box.element is None:
            continue
        try:
            abs_box.line_static = _marked_inline(
                tree, element, abs_box.element, styles, declarations, anchor, box.font_size
            )
        except _Invalid:
            abs_box.line_static = None


def _line_static_parent(box: _Box) -> bool:
    if box.writing_mode != "horizontal-tb" or box.direction != "ltr" or box.white_space != "normal":
        return False
    if box.atoms or box.floats or box.relative_layers or box.list_item:
        return False
    return box.text_align not in {"justify", "justify-all"} and box.text_align_last != "justify"


def _marked_inline(
    tree,
    element,
    target,
    styles,
    declarations,
    anchor: dict[str, str],
    size: int,
) -> tuple[str, tuple[int, ...]]:
    parts: list[str] = []
    advances: list[int] = []
    found = _mark_inline_node(
        tree, element, target, styles, declarations, anchor, size, parts, advances
    )
    if not found or parts.count(_STATIC_MARK) != 1:
        raise _Invalid("static position inside a line is unsupported")
    return "".join(parts), tuple(advances)


def _mark_inline_node(
    tree,
    node,
    target,
    styles,
    declarations,
    anchor: dict[str, str],
    size: int,
    parts: list[str],
    advances: list[int],
) -> bool:
    found = False
    before, after = _generated(tree, node)
    _push_inline_text(before + (node.text or ""), size, parts, advances)
    for child in list(node):
        if not _local_name(child):
            continue
        if child is target:
            _push_static_target(tree, child, styles, declarations, anchor, parts, advances)
            _push_inline_text(child.tail or "", size, parts, advances)
            found = True
            continue
        kind = _flow_kind(tree, child, styles, declarations)
        if kind in {"skip", "out"}:
            _push_inline_text(child.tail or "", size, parts, advances)
            continue
        if kind != "inline" and kind != "contents":
            raise _Invalid("static position inside a line is unsupported")
        if kind == "inline" and _declared_position(tree, child, styles, declarations) == "relative":
            raise _Invalid("static position inside a line is unsupported")
        child_anchor = _inline_fonts(tree, child, styles, declarations, anchor)
        _require_static_font(child_anchor, anchor)
        child_size = _positive_px(child_anchor["font-size"], "font-size")
        if _mark_inline_node(
            tree, child, target, styles, declarations, anchor, child_size, parts, advances
        ):
            found = True
        _push_inline_text(child.tail or "", size, parts, advances)
    _push_inline_text(after, size, parts, advances)
    return found


def _push_static_target(
    tree,
    node,
    styles,
    declarations,
    anchor: dict[str, str],
    parts: list[str],
    advances: list[int],
) -> None:
    fonts = _inline_fonts(tree, node, styles, declarations, anchor)
    _require_static_font(fonts, anchor)
    parts.append(_STATIC_MARK)
    advances.append(0)
    _push_static_contents(tree, node, styles, declarations, anchor, parts, advances)


def _push_static_contents(
    tree,
    node,
    styles,
    declarations,
    anchor: dict[str, str],
    parts: list[str],
    advances: list[int],
) -> None:
    fonts = _inline_fonts(tree, node, styles, declarations, anchor)
    _require_static_font(fonts, anchor)
    size = _positive_px(fonts["font-size"], "font-size")
    before, after = _generated(tree, node)
    _push_inline_text(before + (node.text or ""), size, parts, advances)
    for child in list(node):
        if not _local_name(child):
            continue
        kind = _flow_kind(tree, child, styles, declarations)
        if kind in {"skip", "out"}:
            _push_inline_text(child.tail or "", size, parts, advances)
            continue
        if kind != "inline" and kind != "contents":
            raise _Invalid("static position inside a line is unsupported")
        if kind == "inline" and _declared_position(tree, child, styles, declarations) == "relative":
            raise _Invalid("static position inside a line is unsupported")
        _push_static_contents(tree, child, styles, declarations, anchor, parts, advances)
        _push_inline_text(child.tail or "", size, parts, advances)
    _push_inline_text(after, size, parts, advances)


def _declared_position(tree, element, styles, declarations) -> str:
    custom = styles.get(element, ({}, ""))[0]
    winners = _winners(tree, element, declarations)
    return _keyword(_declared(winners, "position", custom), _POSITIONS, "static", "position")


def _require_static_font(fonts: dict[str, str], anchor: dict[str, str]) -> None:
    if fonts["font-size"] != anchor["font-size"] or fonts["line-height"] != anchor["line-height"]:
        raise _Invalid("static position inside a line is unsupported")


def _push_inline_text(text: str, size: int, parts: list[str], advances: list[int]) -> None:
    if _STATIC_MARK in text:
        raise _Invalid("static position inside a line is unsupported")
    for character in text:
        parts.append(character)
        advances.append(_advance_of(character, size))


def _line_static_edges(parent: _Box, marked: tuple[str, tuple[int, ...]]) -> tuple[int, int, int]:
    """Viewport margin-edge of the marked inline, plus the parent's content right."""

    text, advances = marked
    measure = parent.content_width
    wrapped = wrap_lines(text, measure, white_space=parent.white_space, advances=list(advances))
    lines = wrapped.get("lines") if wrapped.get("outcome") == "wrapped" else None
    if not isinstance(lines, list):
        raise _Invalid(str(wrapped.get("reason") or "static position inside a line is unsupported"))
    if parent.white_space in _COLLAPSED_EMPTY:
        lines = [
            line
            for line in lines
            if isinstance(line, dict) and (line.get("text") or line.get("content_width"))
        ]
    used = _used_line_height(parent.line_height, parent.font_size)
    height, _baseline = _strut_metrics(parent.font_size, used)
    origin_x = parent.x + _edge_extent(parent.solved, "left")
    origin_y = parent.y + _edge_extent(parent.solved, "top")
    cursor = 0
    found: tuple[int, int] | None = None
    last = len(lines) - 1
    for index, line in enumerate(lines):
        if not isinstance(line, dict):
            raise _Invalid("line is invalid")
        rendered = str(line.get("text") or "")
        if _STATIC_MARK in rendered:
            content = _px(line.get("content_width"), "line width")
            offset = _text_offset(parent, measure, content, index == last)
            before = rendered.split(_STATIC_MARK, 1)[0]
            partial = sum(_advance_of(character, parent.font_size) for character in before)
            found = (origin_x + offset + partial, origin_y + cursor)
            break
        cursor += height
    if found is None:
        raise _Invalid("static position inside a line is unsupported")
    content_right = parent.x + parent.border_width - _edge_extent(parent.solved, "right")
    return found[0], found[1], content_right


def _place_absolute_replaced(box: _Box, cb: _Edge, parent: _Box) -> None:
    """Give an out-of-flow replaced box its used size, then solve the insets."""

    if box.writing_mode != "horizontal-tb" or box.direction != "ltr":
        raise _Invalid("replaced writing mode is unsupported")
    if _box_sizing(box) != "content-box":
        raise _Invalid("replaced box-sizing is unsupported")
    if box.aspect_ratio is not None:
        raise _Invalid("replaced aspect-ratio is unsupported")
    if box.children or box.floats or box.positioned or box.atoms:
        raise _Invalid("positioned replaced element is unsupported")
    slots = _physical_slots(box)
    left, right = _inset(slots, "left"), _inset(slots, "right")
    top, bottom = _inset(slots, "top"), _inset(slots, "bottom")
    needs_static = (_is_auto(left) and _is_auto(right)) or (_is_auto(top) and _is_auto(bottom))
    if needs_static and (parent.inline_text or parent.pieces):
        if not _line_static_parent(parent) or box.display != "inline" or box.line_static is None:
            raise _Invalid("static position inside a line is unsupported")
        hyp_x, hyp_y, hyp_right = _line_static_edges(parent, box.line_static)
    elif needs_static:
        hyp_x, hyp_y, hyp_right = _hypothetical_edges(parent, box.static_index)
    else:
        hyp_x = hyp_y = hyp_right = None
    if hyp_x is None:
        static_left = static_right = static_top = 0
    else:
        static_left = hyp_x - cb.x
        static_right = (cb.x + cb.width) - hyp_right
        static_top = hyp_y - cb.y
    sized = used_replaced_size(
        cb.width,
        containing_height="auto" if cb.height is None else cb.height,
        width=slots.get("width", "auto"),
        height=slots.get("height", "auto"),
        min_width=slots.get("min-width", "auto"),
        max_width=slots.get("max-width", "none"),
        min_height=slots.get("min-height", "auto"),
        max_height=slots.get("max-height", "none"),
        margin_left=0,
        margin_right=0,
        margin_top=0,
        margin_bottom=0,
        padding_left=slots.get("padding-left", 0),
        padding_right=slots.get("padding-right", 0),
        border_left=_border_arg(slots, "left"),
        border_right=_border_arg(slots, "right"),
        intrinsic_width=box.intrinsic_width,
        intrinsic_height=box.intrinsic_height,
        layout="inline",
        direction=box.direction,
    )
    if sized.get("outcome") != "sized":
        raise _Invalid(str(sized.get("reason") or "replaced size is invalid"))
    placed = place_absolute(
        cb.width,
        containing_height="auto" if cb.height is None else cb.height,
        left=left,
        right=right,
        width=sized.get("width"),
        top=top,
        bottom=bottom,
        height=sized.get("height"),
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
        min_width="auto",
        max_width="none",
        min_height="auto",
        max_height="none",
        box_sizing="content-box",
        direction=box.direction,
        static_left=static_left,
        static_right=static_right,
        static_top=static_top,
        min_content=sized.get("width"),
        max_content=sized.get("width"),
        content_height=sized.get("height"),
    )
    if placed.get("outcome") != "placed":
        raise _Invalid(str(placed.get("reason") or "absolute position failed"))
    _adopt_absolute(box, cb, placed)
    _fit_replaced_object(box)
    box.lines = []


def _place_one_absolute(box: _Box, cb: _Edge, parent: _Box) -> None:
    if box.replaced:
        _place_absolute_replaced(box, cb, parent)
        return
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
        if not _line_static_parent(parent) or box.display != "inline" or box.line_static is None:
            raise _Invalid("static position inside a line is unsupported")
        hyp_x, hyp_y, hyp_right = _line_static_edges(parent, box.line_static)
    elif needs_static:
        hyp_x, hyp_y, hyp_right = _hypothetical_edges(parent, box.static_index)
    else:
        hyp_x = hyp_y = hyp_right = None
    if hyp_x is None:
        static_left = static_right = static_top = 0
    else:
        static_left = hyp_x - cb.x
        static_right = (cb.x + cb.width) - hyp_right
        static_top = hyp_y - cb.y
    if box.children and needs_shrink:
        minimum, maximum = _absolute_content_span(box)
    elif box.inline_text:
        minimum, maximum = _intrinsic_text_sizes(box)
    else:
        minimum, maximum = (0, 0)
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

    if box.children and box.writing_mode != "horizontal-tb":
        raise _Invalid("positioned content is unsupported")
    placed = solve(0)
    if placed.get("outcome") == "placed" and box.inline_text and not box.children:
        width = _px(placed.get("width"), "content width")
        measured = sum(line.height for line in _plain_lines(box, width, direction))
        if measured != 0:
            placed = solve(measured)
    if placed.get("outcome") != "placed":
        raise _Invalid(str(placed.get("reason") or "absolute position failed"))
    _adopt_absolute(box, cb, placed)
    if box.children:
        measured = _lay_grid_item_blocks(box, None, reason="positioned content is unsupported")
        revised = solve(measured)
        if revised.get("outcome") != "placed":
            raise _Invalid(str(revised.get("reason") or "absolute position failed"))
        revised_x = cb.x + _px(revised.get("x"), "x")
        revised_width = _px(revised.get("width"), "content width")
        previous_x = box.x
        previous_width = box.content_width
        _adopt_absolute(box, cb, revised)
        if revised_width != previous_width:
            _lay_grid_item_blocks(box, None, reason="positioned content is unsupported")
        elif revised_x != previous_x:
            for child in box.children:
                _shift_x(child, revised_x - previous_x)
        box.lines = []
        for child in box.children:
            _paint_anchored(child, box.y)
        return
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
    minimum = _px(measured["min_content"], "min-content")
    maximum = _px(measured["max_content"], "max-content")
    indent = _text_indent_used(box)
    if indent > 0:
        return minimum + indent, maximum + indent
    if indent < 0:
        return minimum, max(0, maximum + indent)
    return minimum, maximum


def _shrink_float_width(box: _Box, available: int) -> int:
    if box.children:
        pairs = [_float_child_span(child) for child in box.children]
        minimum = max(item[0] for item in pairs)
        maximum = max(item[1] for item in pairs)
    else:
        minimum, maximum = _intrinsic_text_sizes(box)
    room = available if available > 0 else 0
    return min(max(minimum, room), maximum)


def _intrinsic_attribute(element, name: str) -> int | None:
    raw = _attr(element, name)
    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return None
    if not text.isascii() or not text.isdigit():
        raise _Invalid("replaced size is invalid")
    return int(text)


def _read_object_fit(winners, custom: dict) -> str:
    value = _declared(winners, "object-fit", custom)
    if value is None or value in {"initial", "unset", "revert"}:
        return "fill"
    if value == "inherit":
        raise _Invalid("object-fit inherit is unsupported")
    token = " ".join(value.lower().split())
    if token not in _OBJECT_FITS:
        raise _Invalid("object-fit is invalid")
    return token


def _read_object_position(winners, custom: dict) -> str:
    value = _declared(winners, "object-position", custom)
    if value is None or value in {"initial", "unset", "revert"}:
        return "50% 50%"
    if value == "inherit":
        raise _Invalid("object-position inherit is unsupported")
    return " ".join(value.split())


def _replaced_has_content(tree, element) -> bool:
    if (element.text or "").strip():
        return True
    for node in tree.children.get(element, []):
        if _local_name(node) not in _REPLACED_SKIP:
            return True
        if (node.tail or "").strip():
            return True
    return False


def _box_prop(box: _Box, name: str, default: str) -> str:
    found = default
    for prop, value in box.declarations:
        if prop == name:
            found = value
    return found


def _replaced_layout(box: _Box) -> str:
    if box.float_side != "none":
        return "float"
    if box.display == "inline-block":
        return "inline-block"
    if box.display == "inline":
        return "inline"
    if box.display == "block":
        return "block"
    raise _Invalid("replaced display is unsupported")


def _used_replaced(
    box: _Box,
    containing_width: int,
    containing_height: int | None,
    solved: dict,
) -> dict:
    if box.writing_mode != "horizontal-tb" or box.direction != "ltr":
        raise _Invalid("replaced writing mode is unsupported")
    if _box_sizing(box) != "content-box":
        raise _Invalid("replaced box-sizing is unsupported")
    if box.aspect_ratio is not None:
        raise _Invalid("replaced aspect-ratio is unsupported")
    sized = used_replaced_size(
        containing_width,
        containing_height="auto" if containing_height is None else containing_height,
        width=_box_prop(box, "width", "auto"),
        height=_box_prop(box, "height", "auto"),
        min_width=_box_prop(box, "min-width", "auto"),
        max_width=_box_prop(box, "max-width", "none"),
        min_height=_box_prop(box, "min-height", "auto"),
        max_height=_box_prop(box, "max-height", "none"),
        margin_left=_box_prop(box, "margin-left", "0px"),
        margin_right=_box_prop(box, "margin-right", "0px"),
        margin_top=_box_prop(box, "margin-top", "0px"),
        margin_bottom=_box_prop(box, "margin-bottom", "0px"),
        padding_left=_px(solved.get("padding_left"), "padding-left"),
        padding_right=_px(solved.get("padding_right"), "padding-right"),
        border_left=_px(solved.get("border_left"), "border-left"),
        border_right=_px(solved.get("border_right"), "border-right"),
        intrinsic_width=box.intrinsic_width,
        intrinsic_height=box.intrinsic_height,
        layout=_replaced_layout(box),
        direction=box.direction,
    )
    if sized.get("outcome") != "sized":
        raise _Invalid(str(sized.get("reason") or "replaced size is invalid"))
    return sized


def _store_replaced(box: _Box, sized: dict) -> None:
    box.content_width = _px(sized.get("width"), "content width")
    box.content_height = _px(sized.get("height"), "content height")
    box.definite_height = box.content_height
    box.margin_left = _px(sized.get("margin_left"), "margin-left")
    box.margin_right = _px(sized.get("margin_right"), "margin-right")
    box.solved["margin_left"] = box.margin_left
    box.solved["margin_right"] = box.margin_right
    box.solved["margin_top"] = _px(sized.get("margin_top"), "margin-top")
    box.solved["margin_bottom"] = _px(sized.get("margin_bottom"), "margin-bottom")
    _fit_replaced_object(box)


def _fit_replaced_object(box: _Box) -> None:
    fitted = fit_object(
        box.content_width,
        box.content_height,
        fit=box.object_fit,
        position=box.object_position,
        natural_width=box.intrinsic_width,
        natural_height=box.intrinsic_height,
    )
    if fitted.get("outcome") != "fitted":
        raise _Invalid(str(fitted.get("reason") or "object-fit is invalid"))
    box.object_box = {
        "x": _px(fitted.get("x"), "object x"),
        "y": _px(fitted.get("y"), "object y"),
        "width": _px(fitted.get("width"), "object width"),
        "height": _px(fitted.get("height"), "object height"),
    }


def _apply_replaced_block(
    box: _Box,
    containing_width: int,
    containing_height: int | None,
    parent_content_x: int,
) -> None:
    sized = _used_replaced(box, containing_width, containing_height, box.solved)
    _store_replaced(box, sized)
    box.x = parent_content_x + box.margin_left


def _measure_replaced(
    parent: _Box,
    fl: _Box,
    solved: dict,
    padding_left: int,
    padding_right: int,
    padding_top: int,
    padding_bottom: int,
    border_left: int,
    border_right: int,
    border_top: int,
    border_bottom: int,
) -> dict[str, int]:
    sized = _used_replaced(fl, parent.content_width, parent.definite_height, solved)
    _store_replaced(fl, sized)
    margin_top = _px(sized.get("margin_top"), "margin-top")
    margin_bottom = _px(sized.get("margin_bottom"), "margin-bottom")
    fl.border_width = fl.content_width + padding_left + padding_right + border_left + border_right
    fl.border_height = fl.content_height + padding_top + padding_bottom + border_top + border_bottom
    fl.local_y = margin_top
    return {
        "outer_width": fl.margin_left + fl.border_width + fl.margin_right,
        "outer_height": margin_top + fl.border_height + margin_bottom,
        "margin_left": fl.margin_left,
        "margin_top": margin_top,
    }


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
    if fl.replaced:
        fl.solved = solved
        return _measure_replaced(
            box,
            fl,
            solved,
            padding_left,
            padding_right,
            padding_top,
            padding_bottom,
            border_left,
            border_right,
            border_top,
            border_bottom,
        )
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
    fl.margin_left = margin_left
    fl.margin_right = margin_right
    fl.border_width = content_width + padding_left + padding_right + border_left + border_right
    fl.local_y = margin_top
    if fl.children:
        _lay_float_blocks(fl)
    else:
        if fl.inline_text:
            _fill_lines(fl)
        if fl.definite_height is None:
            fl.definite_height = 0
        fl.content_height = fl.definite_height
        fl.border_height = fl.content_height + padding_top + padding_bottom + border_top + border_bottom
    return {
        "outer_width": margin_left + fl.border_width + margin_right,
        "outer_height": margin_top + fl.border_height + margin_bottom,
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
    if fl.shape_outside:
        try:
            prepare_shape(fl.shape_outside, margin_width, margin_height, fl.shape_margin)
        except ShapeError as exc:
            raise _Invalid(exc.reason) from exc
    fl.float_band = (
        margin_x,
        margin_y,
        margin_width,
        margin_height,
        fl.float_side,
        fl.shape_outside,
        fl.shape_margin,
    )
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
    bands: list[tuple[int, int, int, int, str, str, float]] = []
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
        local = [_shift_band(band, inset_x, content_top) for band in bands]
        _reflow_beside(item, local)
        item.anchor_y = origin + border_y
        cursor = border_y + item.border_height + margin_bottom
    box.anchor_laid = True
    if box.definite_height is None:
        box.definite_height = max([cursor, *(band[1] + band[3] for band in bands)], default=0)


def _reflow_beside(box: _Box, bands: list[tuple[int, int, int, int, str, str, float]]) -> None:
    auto = box.solved.get("content_height") == "auto"
    saved = box.definite_height
    if auto:
        box.definite_height = None
    if box.atoms:
        _fill_atoms_beside_floats(box, bands, contain=False)
    else:
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


def _clear_floor(clear: str, bands: list[tuple[int, int, int, int, str, str, float]]) -> int:
    if clear == "none":
        return 0
    floor = 0
    for _x, y, _w, height, side, *_rest in bands:
        if clear == "both" or clear == side:
            floor = max(floor, y + height)
    return floor


def _fit_float(
    side: str,
    width: int,
    height: int,
    floor: int,
    bands: list[tuple[int, int, int, int, str, str, float]],
    containing: int,
) -> tuple[int, int]:
    events = {floor}
    for _x, y, _w, band_height, _side, *_rest in bands:
        bottom = y + band_height
        if bottom > floor:
            events.add(bottom)
    for y in sorted(events):
        left = 0
        right = containing
        for bx, by, bw, bh, band_side, *_rest in bands:
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


def _gap_alignment(box: _Box) -> bool:
    return box.text_align in {"justify", "justify-all"} or box.text_align_last == "justify"


def _uses_gap_items(box: _Box, last: bool) -> bool:
    if box.text_align in {"justify", "justify-all"}:
        return True
    return last and box.text_align_last == "justify"


def _snap(value: object, name: str) -> int:
    if type(value) is bool or not isinstance(value, (int, float)):
        raise _Invalid(f"{name} is invalid")
    number = float(value)
    if number != number or number in {float("inf"), float("-inf")}:
        raise _Invalid(f"{name} is invalid")
    return int(round(number))


def _word_gaps(rendered: str, font_size: int) -> list[tuple[str, int]]:
    words: list[tuple[str, int]] = []
    index = 0
    count = len(rendered)
    while index < count:
        if rendered[index] == " ":
            raise _Invalid("justified leading space is unsupported")
        end = index
        while end < count and rendered[end] != " ":
            end += 1
        space_at = end
        while space_at < count and rendered[space_at] == " ":
            space_at += 1
        space = sum(_advance_of(rendered[pos], font_size) for pos in range(end, space_at))
        words.append((rendered[index:end], space))
        index = space_at
    return words


def _gap_items(
    rendered: str, font_size: int, *, character: bool
) -> tuple[list[dict[str, object]], list[tuple[str, list[str]]]]:
    items: list[dict[str, object]] = []
    groups: list[tuple[str, list[str]]] = []
    serial = 0
    for word, space in _word_gaps(rendered, font_size):
        ids: list[str] = []
        if character:
            last = len(word) - 1
            for offset, ch in enumerate(word):
                ident = f"c{serial}"
                serial += 1
                items.append(
                    {
                        "id": ident,
                        "width": _advance_of(ch, font_size),
                        "space_after": space if offset == last else 0,
                    }
                )
                ids.append(ident)
        else:
            ident = f"w{serial}"
            serial += 1
            items.append(
                {
                    "id": ident,
                    "width": sum(_advance_of(ch, font_size) for ch in word),
                    "space_after": space,
                }
            )
            ids.append(ident)
        groups.append((word, ids))
    return items, groups


def _text_offset(box: _Box, measure: int, content: int, last: bool, *, direction: str | None = None) -> int:
    aligned = align_inline_line(
        measure,
        [{"id": "text", "width": content}],
        text_align=box.text_align,
        text_align_last=box.text_align_last,
        text_justify=box.text_justify,
        direction=direction or box.direction,
        parent_direction=box.parent_direction,
        white_space=box.white_space,
        last_line=last,
    )
    items = aligned.get("items") if aligned["outcome"] == "aligned" else None
    if not isinstance(items, list) or len(items) != 1 or not isinstance(items[0], dict):
        raise _Invalid(str(aligned.get("reason") or "text alignment failed"))
    return _px(items[0].get("x"), "line offset")


def _align_content(
    box: _Box,
    measure: int,
    rendered: str,
    packed: int,
    last: bool,
    direction: str | None,
) -> tuple[int, int, list[dict[str, object]]]:
    """Place one line. Justification returns word runs inside the line box."""

    flow = direction or box.direction
    if not rendered or not _uses_gap_items(box, last):
        return _text_offset(box, measure, packed, last, direction=flow), packed, []
    if flow != "ltr" or box.writing_mode != "horizontal-tb":
        raise _Invalid("justified writing mode is unsupported")
    if box.white_space not in {"normal", "nowrap", "pre-line"}:
        raise _Invalid("justified white-space is unsupported")
    if any(ch in rendered for ch in "\t\r\n"):
        raise _Invalid("justified break is unsupported")
    items, groups = _gap_items(rendered, box.font_size, character=box.text_justify == "inter-character")
    if not items:
        return _text_offset(box, measure, packed, last, direction=flow), packed, []
    aligned = align_inline_line(
        measure,
        items,
        text_align=box.text_align,
        text_align_last=box.text_align_last,
        text_justify=box.text_justify,
        direction=flow,
        parent_direction=box.parent_direction,
        white_space=box.white_space,
        last_line=last,
    )
    placed = aligned.get("items") if aligned.get("outcome") == "aligned" else None
    if not isinstance(placed, list) or len(placed) != len(items):
        raise _Invalid(str(aligned.get("reason") or "text alignment failed"))
    by_id = {str(row.get("id")): row for row in placed if isinstance(row, dict)}
    if any(ident not in by_id for _word, ids in groups for ident in ids):
        raise _Invalid("text alignment failed")
    origin = _snap(by_id[groups[0][1][0]].get("x"), "x")
    runs: list[dict[str, object]] = []
    for word, ids in groups:
        start = _snap(by_id[ids[0]].get("x"), "x")
        last_row = by_id[ids[-1]]
        end = _snap(last_row.get("x"), "x") + _snap(last_row.get("width"), "width")
        runs.append(
            {
                "text": word,
                "x": start - origin,
                "y": 0,
                "font_size": box.font_size,
                "width": end - start,
            }
        )
    used = int(runs[-1]["x"]) + int(runs[-1]["width"])
    return origin, used, runs


def _fill_lines_beside_floats(
    box: _Box,
    bands: list[tuple[int, int, int, int, str, str, float]] | None = None,
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
        shaped = _shaped_float_payload(bands)
        if shaped is None:
            left, right, bottoms = _exclusion(cursor, height, bands, box.content_width)
        else:
            gap = shaped_gap_at(box.content_width, shaped, height, cursor)
            if gap.get("outcome") != "placed":
                raise _Invalid(str(gap.get("reason") or "shape-outside is invalid"))
            left = _px(gap.get("left"), "line x")
            right = _px(gap.get("right"), "line x")
            bottoms = []
        available = right - left
        wrapped = wrap_lines(remaining, max(available, 0), white_space=box.white_space, advances=advances)
        lines = wrapped.get("lines") if wrapped.get("outcome") == "wrapped" else None
        if not isinstance(lines, list) or not lines or not isinstance(lines[0], dict):
            raise _Invalid(str(wrapped.get("reason") or "line break failed"))
        content = _px(lines[0].get("content_width"), "line width")
        obstructed = not (left == 0 and right == box.content_width)
        if available <= 0 or (content > available and obstructed):
            if shaped is not None:
                found = seek_shaped_gap(box.content_width, shaped, height, cursor, content)
                if found.get("outcome") != "placed":
                    raise _Invalid(str(found.get("reason") or "shape-outside is invalid"))
                nxt = _px(found.get("y"), "float clearance")
                if nxt <= cursor:
                    raise _Invalid("line break failed")
                cursor = nxt
                continue
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
        offset, used, runs = _align_content(box, available, rendered, content, last, box.direction)
        records.append(
            _Line(
                text=rendered,
                x=_px(left, "line x") + offset,
                y=cursor,
                height=height,
                content_width=used,
                runs=runs,
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
    bands: list[tuple[int, int, int, int, str, str, float] | None],
    containing: int,
) -> tuple[int, int, list[int]]:
    left = 0
    right = containing
    bottoms: list[int] = []
    for band in bands:
        if band is None:
            continue
        edge_x, edge_y, width, band_height, side, *_rest = band
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


def _band_bottom(bands: list[tuple[int, int, int, int, str, str, float] | None]) -> int:
    bottoms = [band[1] + band[3] for band in bands if band is not None]
    return max(bottoms) if bottoms else 0


def _shift_band(
    band: tuple[int, int, int, int, str, str, float],
    inset_x: int,
    content_top: int,
) -> tuple[int, int, int, int, str, str, float]:
    edge_x, edge_y, width, height, side, shape, margin = band
    return (edge_x - inset_x, edge_y - content_top, width, height, side, shape, margin)


def _shaped_float_payload(
    bands: list[tuple[int, int, int, int, str, str, float] | None],
) -> list[dict[str, object]] | None:
    payload: list[dict[str, object]] = []
    shaped = False
    for band in bands:
        if band is None:
            continue
        edge_x, edge_y, width, height, side, shape, margin = band
        item: dict[str, object] = {
            "side": side,
            "x": edge_x,
            "y": edge_y,
            "width": width,
            "height": height,
        }
        if shape:
            item["shape"] = shape
            item["shape_margin"] = margin
            shaped = True
        payload.append(item)
    if not shaped:
        return None
    return payload


def _read_float_shape(winners, custom: dict) -> tuple[str, float]:
    raw = _declared(winners, "shape-outside", custom)
    if raw is None or raw.strip().lower() in {"none", "initial", "unset", "revert"}:
        return "", 0.0
    if raw.strip().lower() == "inherit":
        raise _Invalid("shape-outside inherit is unsupported")
    shape = raw.strip().lower()
    margin_raw = _declared(winners, "shape-margin", custom)
    if margin_raw is None or margin_raw.strip().lower() in {"initial", "unset", "revert", "0px"}:
        return shape, 0.0
    if margin_raw.strip().lower() == "inherit":
        raise _Invalid("shape-margin inherit is unsupported")
    text = margin_raw.strip().lower()
    if not text.endswith("px"):
        raise _Invalid("shape-margin is invalid")
    try:
        number = float(text[:-2])
    except ValueError as exc:
        raise _Invalid("shape-margin is invalid") from exc
    if number < 0 or number != number or number in {float("inf"), float("-inf")}:
        raise _Invalid("shape-margin is invalid")
    return shape, number


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


def _read_inline_align(value: str | None, font_size: int, line_height: str) -> str | float:
    """Used vertical-align for an inline-block. The initial value is baseline."""

    if value is None or value in {"initial", "unset", "revert", "baseline"}:
        return "baseline"
    if value == "inherit":
        raise _Invalid("vertical-align inherit is unsupported")
    token = value.strip().lower()
    if token in {"top", "bottom", "middle", "text-top", "text-bottom", "baseline"}:
        return token
    if token in {"sub", "super"}:
        raise _Invalid("vertical-align is unsupported")
    if token == "0":
        return 0
    if token.endswith("%"):
        number = _align_number(token[:-1])
        resolved = number * _used_line_height(line_height, font_size) / 100.0
    elif token.endswith("px"):
        resolved = _align_number(token[:-2])
    else:
        raise _Invalid("vertical-align is unsupported")
    nearest = round(resolved)
    if abs(resolved - nearest) > 1e-6:
        raise _Invalid("vertical-align is unsupported")
    return int(nearest)


def _align_number(text: str) -> float:
    try:
        number = float(text)
    except ValueError as exc:
        raise _Invalid("vertical-align is unsupported") from exc
    if number != number or number in {float("inf"), float("-inf")}:
        raise _Invalid("vertical-align is unsupported")
    return number


def _atom_align(atom: _Box, below: int) -> str | float:
    """Shift that puts the atomic baseline on the parent baseline, or a keyword."""

    spec = atom.vertical_align
    if spec == "baseline":
        return -below
    if isinstance(spec, str):
        return spec
    return spec - below


def _line_extent(
    box: _Box,
    groups: list[tuple[str, int, str, int]],
    atoms_here: list[tuple[_Box, int]],
    measured: dict[str, dict[str, int]],
) -> tuple[int, int, list[int]]:
    payload: list[dict[str, object]] = []
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
    for index, (atom, _border_x) in enumerate(atoms_here):
        row = measured[atom.id]
        above, below = _atom_edges(box, atom, row)
        outer = row["outer_height"]
        if above + below != outer:
            raise _Invalid("inline-block baseline is invalid")
        payload.append(
            {
                "id": f"a{index}",
                "kind": "atomic",
                "vertical_align": _atom_align(atom, below),
                "height": outer,
                "margin_top": 0,
                "margin_bottom": 0,
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
    if laid.get("outcome") != "resolved" or not isinstance(laid.get("boxes"), list):
        raise _Invalid(str(laid.get("reason") or "line box failed"))
    placed = {
        str(item.get("id")): item for item in laid["boxes"] if isinstance(item, dict)
    }
    height = _px(laid.get("line_height"), "line height")
    baseline = _px(laid.get("baseline"), "baseline")
    tops: list[int] = []
    for index, _atom in enumerate(atoms_here):
        item = placed.get(f"a{index}")
        if not isinstance(item, dict):
            raise _Invalid("line box failed")
        tops.append(_px(item.get("top"), "atom top"))
    return height, baseline, tops


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
    entries = _atom_sources(box)
    source = "".join(item[0] for item in entries)
    wrapped = wrap_lines(
        source,
        max(box.content_width, 0),
        white_space=box.white_space,
        advances=_atom_advances(entries, measured),
    )
    raw_lines = wrapped.get("lines") if wrapped.get("outcome") == "wrapped" else None
    if not isinstance(raw_lines, list):
        raise _Invalid(str(wrapped.get("reason") or "line break failed"))
    records: list[_Line] = []
    cursor_y = 0
    index = 0
    placed: set[str] = set()
    visible_lines = [line for line in raw_lines if isinstance(line, dict)]
    last_index = len(visible_lines) - 1
    for line_index, line in enumerate(visible_lines):
        rendered = str(line.get("text") or "")
        content = _px(line.get("content_width"), "line width")
        if not rendered and content == 0:
            continue
        chosen, index = _match_atom_line(entries, index, rendered)
        record, height = _paint_atom_line(
            box,
            chosen,
            content,
            box.content_width,
            0,
            cursor_y,
            line_index == last_index,
            measured,
            placed,
        )
        records.append(record)
        cursor_y += height
    while index < len(entries) and entries[index][0].isspace():
        index += 1
    if index != len(entries) or placed != {atom.id for atom in box.atoms}:
        raise _Invalid("inline-block line is invalid")
    box.lines = records
    if box.definite_height is None:
        box.definite_height = cursor_y


def _atom_sources(box: _Box) -> list[tuple[str, int, str, _Box | None]]:
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
    return entries


def _atom_advances(
    entries: list[tuple[str, int, str, _Box | None]], measured: dict[str, dict[str, int]]
) -> list[int]:
    advances: list[int] = []
    for ch, size, _leading, atom in entries:
        if ch == _ZWSP:
            advances.append(0)
        elif atom is not None:
            advances.append(measured[atom.id]["outer_width"])
        else:
            advances.append(_advance_of(ch, size))
    return advances


def _match_atom_line(
    entries: list[tuple[str, int, str, _Box | None]], index: int, rendered: str
) -> tuple[list[tuple[str, int, str, _Box | None]], int]:
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
    return chosen, index


def _paint_atom_line(
    box: _Box,
    chosen: list[tuple[str, int, str, _Box | None]],
    content: int,
    measure: int,
    left: int,
    cursor_y: int,
    last: bool,
    measured: dict[str, dict[str, int]],
    placed: set[str],
) -> tuple[_Line, int]:
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
    height, above, tops = _line_extent(box, groups, atoms_here, measured)
    offset = _text_offset(box, measure, content, last)
    for (atom, border_x), top in zip(atoms_here, tops, strict=True):
        atom.local_x = left + offset + border_x
        atom.local_y = cursor_y + top + measured[atom.id]["margin_top"]
    visible = "".join(ch for ch, _size, _leading, atom in chosen if atom is None and ch != _ZWSP)
    return (
        _Line(
            text=visible,
            x=left + offset,
            y=cursor_y,
            height=height,
            content_width=content,
            runs=runs,
            baseline=above,
            atoms=atom_records,
        ),
        height,
    )


def _fill_atoms_beside_floats(
    box: _Box,
    bands: list[tuple[int, int, int, int, str, str, float]] | None = None,
    *,
    contain: bool = True,
) -> None:
    """Place inline-blocks in gaps shortened by floats.

    This box's own floats supply the bands when ``bands`` is omitted. A
    parent that already shifted its float bands passes those bands and sets
    ``contain`` false so the height stays the line stack.
    """

    if box.writing_mode != "horizontal-tb" or box.direction != "ltr":
        raise _Invalid("inline-block writing mode is unsupported")
    if len(box.atoms) > 32:
        raise _Invalid("inline-block is unsupported")
    for atom in box.atoms:
        if atom.writing_mode != "horizontal-tb" or atom.direction != "ltr":
            raise _Invalid("inline-block writing mode is unsupported")
    if _mixed_runs(box) or _relative_pieces(box):
        raise _Invalid("inline-block beside a float is unsupported")
    if bands is None:
        bands = [fl.float_band for fl in box.floats if fl.float_placed and fl.float_band is not None]
        if len(bands) != len(box.floats) or any(band[5] for band in bands):
            raise _Invalid("inline-block beside a float is unsupported")
    elif any(band[5] for band in bands):
        raise _Invalid("inline-block beside a float is unsupported")
    measured = {atom.id: _measure_float(box, atom) for atom in box.atoms}
    strut = _strut_height(box.font_size, _used_line_height(box.line_height, box.font_size))
    if any(measured[atom.id]["outer_height"] != strut for atom in box.atoms):
        raise _Invalid("inline-block beside a float is unsupported")
    entries = _atom_sources(box)
    records: list[_Line] = []
    placed: set[str] = set()
    index = 0
    cursor_y = 0
    for _ in range(10000):
        if index >= len(entries):
            break
        left, right, bottoms = _exclusion(cursor_y, strut, bands, box.content_width)
        available = right - left
        obstructed = not (left == 0 and right == box.content_width)
        if available <= 0:
            if not bottoms:
                raise _Invalid("line break failed")
            nxt = min(bottoms)
            if nxt <= cursor_y:
                raise _Invalid("line break failed")
            cursor_y = nxt
            continue
        source = "".join(item[0] for item in entries[index:])
        wrapped = wrap_lines(
            source,
            max(available, 0),
            white_space=box.white_space,
            advances=_atom_advances(entries[index:], measured),
        )
        lines = wrapped.get("lines") if wrapped.get("outcome") == "wrapped" else None
        if not isinstance(lines, list) or not lines or not isinstance(lines[0], dict):
            raise _Invalid(str(wrapped.get("reason") or "line break failed"))
        rendered = str(lines[0].get("text") or "")
        content = _px(lines[0].get("content_width"), "line width")
        if not rendered and content == 0:
            raise _Invalid("line break failed")
        if content > available and obstructed:
            if not bottoms:
                raise _Invalid("line break failed")
            nxt = min(bottoms)
            if nxt <= cursor_y:
                raise _Invalid("line break failed")
            cursor_y = nxt
            continue
        chosen, new_index = _match_atom_line(entries, index, rendered)
        if new_index <= index:
            raise _Invalid("line break failed")
        rest = entries[new_index:]
        last = not any(ch.strip() and ch != _ZWSP for ch, _size, _leading, _atom in rest)
        record, height = _paint_atom_line(
            box, chosen, content, available, left, cursor_y, last, measured, placed
        )
        if height != strut:
            raise _Invalid("inline-block beside a float is unsupported")
        records.append(record)
        index = new_index
        cursor_y += height
    else:
        raise _Invalid("line break failed")
    while index < len(entries) and entries[index][0].isspace():
        index += 1
    if index != len(entries) or placed != {atom.id for atom in box.atoms}:
        raise _Invalid("inline-block line is invalid")
    box.lines = records
    if box.definite_height is None:
        bottom = _band_bottom(bands)
        box.definite_height = max(cursor_y, bottom) if contain else cursor_y


def _fill_lines(box: _Box) -> None:
    if box.text_indent != "0px" and (box.floats or box.atoms or _mixed_runs(box)):
        raise _Invalid("text-indent is unsupported")
    if _gap_alignment(box):
        if box.writing_mode != "horizontal-tb" or box.direction != "ltr":
            raise _Invalid("justified writing mode is unsupported")
        if box.white_space not in {"normal", "nowrap", "pre-line"}:
            raise _Invalid("justified white-space is unsupported")
        if _relative_pieces(box):
            raise _Invalid("justified relative inline is unsupported")
        if box.atoms:
            raise _Invalid("justified inline-block is unsupported")
        if _mixed_runs(box):
            raise _Invalid("justified mixed font is unsupported")
    if _relative_pieces(box):
        if box.writing_mode != "horizontal-tb" or box.direction != "ltr" or box.white_space != "normal":
            raise _Invalid("relative inline is unsupported")
        if box.atoms:
            raise _Invalid("relative inline content is unsupported")
        if box.floats:
            raise _Invalid("relative inline beside a float is unsupported")
        if _mixed_runs(box):
            raise _Invalid("relative inline font is unsupported")
    if box.atoms:
        if box.floats:
            _fill_atoms_beside_floats(box)
            return
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
        tail = box.lines[-1]
        box.definite_height = tail.y + tail.height


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


def _relative_pieces(box: _Box) -> bool:
    return any(piece.shifts for piece in box.pieces)


def _source_shifts(box: _Box) -> list[tuple[_Shift, ...]]:
    shifts: list[tuple[_Shift, ...]] = []
    for piece in box.pieces:
        if piece.atom is not None:
            raise _Invalid("relative inline content is unsupported")
        shifts.extend((piece.shifts,) * len(piece.text))
    text = box.inline_text or ""
    if len(shifts) != len(text):
        raise _Invalid("relative inline is unsupported")
    return shifts


def _collapse_shift_text(
    text: str, shifts: list[tuple[_Shift, ...]]
) -> tuple[str, list[tuple[_Shift, ...]]]:
    """Collapse whitespace the same way a normal line keeps one space."""

    if len(shifts) != len(text):
        raise _Invalid("relative inline is unsupported")
    chars: list[str] = []
    chosen: list[tuple[_Shift, ...]] = []
    index = 0
    count = len(text)
    gap: tuple[_Shift, ...] | None = None
    while index < count:
        if text[index].isspace():
            if gap is None:
                gap = shifts[index]
            index += 1
            continue
        if chars:
            if gap is None:
                raise _Invalid("relative inline is unsupported")
            chars.append(" ")
            chosen.append(gap)
        gap = None
        while index < count and not text[index].isspace():
            chars.append(text[index])
            chosen.append(shifts[index])
            index += 1
    return "".join(chars), chosen


def _layers_delta(shifts: tuple[_Shift, ...], cb_width: int, cb_height: int | None) -> tuple[int, int]:
    dx = 0
    dy = 0
    height: object = "auto" if cb_height is None else cb_height
    for index, shift in enumerate(shifts):
        placed = place_relative(
            [
                {
                    "id": f"s{index}",
                    "position": "relative",
                    "direction": shift.direction,
                    "x": 0,
                    "y": 0,
                    "width": 0,
                    "height": 0,
                    "left": shift.left,
                    "right": shift.right,
                    "top": shift.top,
                    "bottom": shift.bottom,
                }
            ],
            containing_width=cb_width,
            containing_height=height,
        )
        rows = placed.get("boxes")
        if placed.get("outcome") != "placed" or not isinstance(rows, list) or not rows:
            raise _Invalid(str(placed.get("reason") or "relative position failed"))
        row = rows[0]
        if not isinstance(row, dict):
            raise _Invalid("relative position failed")
        dx += _px(row.get("x"), "x")
        dy += _px(row.get("y"), "y")
    return dx, dy


def _relative_runs(
    rendered: str,
    shifts: list[tuple[_Shift, ...]],
    font_size: int,
    cb_width: int,
    cb_height: int | None,
    content: int,
) -> list[dict[str, object]]:
    if len(rendered) != len(shifts):
        raise _Invalid("relative inline is unsupported")
    runs: list[dict[str, object]] = []
    cursor = 0
    buf = ""
    buf_shift: tuple[_Shift, ...] = ()
    buf_x = 0
    buf_width = 0

    def flush() -> None:
        nonlocal buf, buf_width
        if not buf:
            return
        dx, dy = _layers_delta(buf_shift, cb_width, cb_height)
        runs.append(
            {
                "text": buf,
                "x": buf_x + dx,
                "y": dy,
                "font_size": font_size,
                "width": buf_width,
            }
        )
        buf = ""
        buf_width = 0

    for ch, shift in zip(rendered, shifts, strict=True):
        advance = _advance_of(ch, font_size)
        if buf and shift != buf_shift:
            flush()
        if not buf:
            buf_x = cursor
            buf_shift = shift
        buf += ch
        buf_width += advance
        cursor += advance
    flush()
    if cursor != content:
        raise _Invalid("relative inline is unsupported")
    return runs


def _list_style_type(winners, custom: dict, fonts: dict[str, str], tag: str) -> str:
    raw = _declared(winners, "list-style-type", custom)
    if raw is None and tag == "ol":
        return "decimal"
    return _inherited_keyword(raw, _LIST_TYPES, fonts["list-style-type"], "disc", "list-style-type")


def _counter_declaration(winners, custom: dict, name: str, tag: str) -> str:
    raw = _declared(winners, name, custom)
    if raw == "inherit":
        raise _Invalid(f"{name} inherit is unsupported")
    if name == "counter-reset" and raw is None and tag in _LIST_RESET_TAGS:
        return "list-item"
    if raw is None or raw in {"initial", "unset", "revert", "none"}:
        return ""
    return " ".join(raw.split())


def _marker_string(value: int, style: str) -> str:
    if style == "none":
        return ""
    symbol = _MARKER_SYMBOLS.get(style)
    if symbol is not None:
        return symbol + " "
    formatted = format_counter(value, style)
    if formatted.get("outcome") != "ok":
        raise _Invalid(str(formatted.get("reason") or "list marker is invalid"))
    return str(formatted["text"]) + ". "


def _text_advance(text: str, font_size: int) -> int:
    return sum(_advance_of(character, font_size) for character in text)


def _counter_payload(box: _Box) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": box.id,
        "display": "list-item" if box.list_item else "block",
        "children": [_counter_payload(child) for child in box.counter_children],
    }
    if box.counter_reset:
        payload["counter_reset"] = box.counter_reset
    if box.counter_increment:
        payload["counter_increment"] = box.counter_increment
    plans = getattr(box.tree, "generated_plans", None) if box.tree is not None else None
    pair = plans.get(id(box.element)) if isinstance(plans, dict) and box.element is not None else None
    if isinstance(pair, tuple) and len(pair) == 2:
        before = _counter_pseudo(box, "before", pair[0])
        after = _counter_pseudo(box, "after", pair[1])
        if before is not None:
            payload["before"] = before
        if after is not None:
            payload["after"] = after
    return payload


def _reject_unsupported_marker(box: _Box) -> None:
    parent = box.parent_box
    if box.float_side != "none" or box.position not in {"static", "relative"}:
        raise _Invalid("list marker is unsupported")
    if box.writing_mode != "horizontal-tb" or box.direction != "ltr":
        raise _Invalid("list marker writing mode is unsupported")
    if parent is not None and (
        parent.display in {"flex", "grid", "table", "table-row", "table-cell", "table-caption"}
        or parent.multicol is not None
    ):
        raise _Invalid("list marker is unsupported")


def _apply_list_markers(box: _Box, elements: dict[str, object], seen: set[int]) -> None:
    if id(box) in seen:
        return
    seen.add(id(box))
    if box.list_item:
        _reject_unsupported_marker(box)
        element = elements.get(box.id)
        values = element.get("values") if isinstance(element, dict) else None
        number = values.get("list-item") if isinstance(values, dict) else None
        if isinstance(number, bool) or not isinstance(number, int):
            raise _Invalid("list marker is unsupported")
        text = _marker_string(number, box.list_style_type)
        box.marker_text = text
        box.marker_width = _text_advance(text, box.font_size)
    for child in box.counter_children:
        _apply_list_markers(child, elements, seen)


def _require_list_markers(box: _Box) -> None:
    stack = [box]
    visited: set[int] = set()
    while stack:
        current = stack.pop()
        marker = id(current)
        if marker in visited:
            continue
        visited.add(marker)
        if current.list_item and current.marker_text is None:
            raise _Invalid("list marker is unsupported")
        stack.extend(current.counter_children)
        stack.extend(current.children)
        stack.extend(current.floats)
        stack.extend(current.positioned)
        stack.extend(current.atoms)


def _bind_list_markers(root: _Box) -> None:
    resolved = resolve_counters(_counter_payload(root))
    if resolved.get("outcome") != "ok" or not isinstance(resolved.get("elements"), dict):
        raise _Invalid(str(resolved.get("reason") or "counter is invalid"))
    elements = resolved["elements"]
    _apply_list_markers(root, elements, set())
    _require_list_markers(root)


def _attach_list_marker(box: _Box) -> None:
    if not box.list_item:
        return
    if box.marker_text is None:
        raise _Invalid("list marker is unsupported")
    if not box.marker_text:
        return
    if box.list_style_position == "inside" and (box.children or box.floats or box.atoms):
        raise _Invalid("inside marker content is unsupported")
    if box.list_style_position == "inside":
        x, y = 0, 0
    else:
        x = -box.marker_width
        y = box.lines[0].y if box.lines else 0
    box.marker = {"text": box.marker_text, "x": x, "y": y, "width": box.marker_width}


def _inside_marker_indent(box: _Box) -> int:
    if not box.list_item or box.list_style_position != "inside" or not box.marker_text:
        return 0
    if box.white_space != "normal":
        raise _Invalid("inside marker white-space is unsupported")
    if box.text_align not in {"start", "left"}:
        raise _Invalid("inside marker alignment is unsupported")
    if box.atoms or box.floats or box.children or _relative_pieces(box) or _mixed_runs(box):
        raise _Invalid("inside marker content is unsupported")
    if box.writing_mode != "horizontal-tb" or box.direction != "ltr":
        raise _Invalid("list marker writing mode is unsupported")
    return box.marker_width


def _marked_line_records(
    box: _Box,
    lines: list,
    measure: int,
    direction: str,
    height: int,
    baseline: int,
    indent: int,
    place_glyphs: bool,
) -> list[_Line]:
    prepared: list[tuple[str, int, bool]] = []
    for index, line in enumerate(lines):
        if not isinstance(line, dict):
            raise _Invalid("line is invalid")
        rendered = str(line.get("text") or "")
        content = _px(line.get("content_width"), "line width")
        if index == 0:
            if not rendered.startswith(_MARKER_SENTINEL):
                raise _Invalid("list marker is invalid")
            rendered = rendered[1:]
            content -= indent
            if content < 0:
                raise _Invalid("list marker is invalid")
            on_marker = True
        else:
            if _MARKER_SENTINEL in rendered:
                raise _Invalid("list marker is invalid")
            on_marker = False
        rendered = rendered.replace(_MARKER_BREAK, "")
        prepared.append((rendered, content, on_marker))
    cursor = 0
    if prepared and prepared[0][2] and not prepared[0][0]:
        cursor = height
        prepared = prepared[1:]
    visible = [item for item in prepared if item[0] or item[1]]
    records: list[_Line] = []
    last = len(visible) - 1
    for index, (rendered, content, on_marker) in enumerate(visible):
        offset, used, runs = _align_content(box, measure, rendered, content, index == last, direction)
        if on_marker:
            offset += indent
        glyphs = _bidi_glyphs(rendered, direction, box.font_size) if place_glyphs and not runs else []
        if glyphs and sum(int(glyph["width"]) for glyph in glyphs) != content:
            glyphs = []
        records.append(
            _Line(
                text=rendered,
                x=offset,
                y=cursor,
                height=height,
                content_width=used,
                baseline=baseline,
                glyphs=glyphs,
                runs=runs,
            )
        )
        cursor += height
    return records


def _kept_lines(box: _Box, wrapped: dict[str, object]) -> list:
    lines = wrapped.get("lines") if wrapped.get("outcome") == "wrapped" else None
    if not isinstance(lines, list):
        raise _Invalid(str(wrapped.get("reason") or "line break failed"))
    if box.white_space in _COLLAPSED_EMPTY:
        return [line for line in lines if isinstance(line, dict) and (line.get("text") or line.get("content_width"))]
    return lines


def _indented_wrap(box: _Box, text: str, measure: int, indent: int) -> list:
    """Wrap the first line in the shortened measure, then the rest at full width."""

    first_measure = measure - indent
    if first_measure < 0:
        first_measure = 0
    advances = _shrink_advances(box)
    lines = _kept_lines(
        box, wrap_lines(text, first_measure, white_space=box.white_space, advances=advances)
    )
    if not lines:
        return []
    first = lines[0]
    if not isinstance(first, dict):
        raise _Invalid("line is invalid")
    rest = _drop_prefix(text, str(first.get("text") or ""), box.white_space)
    if not rest or (box.white_space in _COLLAPSED_EMPTY and not rest.strip()):
        return [first]
    tail = _kept_lines(
        box, wrap_lines(rest, max(measure, 0), white_space=box.white_space, advances=advances)
    )
    return [first, *tail]


def _plain_lines(box: _Box, measure: int, direction: str, *, place_glyphs: bool = False) -> list[_Line]:
    text = box.inline_text or ""
    if not text:
        return []
    text_indent = _text_indent_used(box)
    if text_indent and direction != "ltr":
        raise _Invalid("text-indent writing mode is unsupported")
    shifted = _relative_pieces(box)
    if shifted and box.white_space != "normal":
        raise _Invalid("relative inline is unsupported")
    used = _used_line_height(box.line_height, box.font_size)
    height, baseline = _strut_metrics(box.font_size, used)
    indent = _inside_marker_indent(box)
    if text_indent and indent:
        raise _Invalid("text-indent beside a marker is unsupported")
    if text_indent and _mixed_runs(box):
        raise _Invalid("text-indent is unsupported")
    if indent and (_MARKER_SENTINEL in text or _MARKER_BREAK in text):
        raise _Invalid("inside marker content is unsupported")
    if indent:
        lines = _kept_lines(
            box,
            wrap_lines(
                _MARKER_SENTINEL + _MARKER_BREAK + text,
                measure,
                white_space=box.white_space,
                advances=[indent, 0, *[_advance_of(character, box.font_size) for character in text]],
            ),
        )
    elif text_indent:
        lines = _indented_wrap(box, text, measure, text_indent)
    else:
        lines = _kept_lines(
            box, wrap_lines(text, measure, white_space=box.white_space, advances=_shrink_advances(box))
        )
    if not lines:
        return []
    if indent:
        return _marked_line_records(
            box, lines, measure, direction, height, baseline, indent, place_glyphs
        )
    collapsed = ""
    collapsed_shifts: list[tuple[_Shift, ...]] = []
    if shifted:
        collapsed, collapsed_shifts = _collapse_shift_text(text, _source_shifts(box))
    records: list[_Line] = []
    cursor = 0
    shift_index = 0
    last = len(lines) - 1
    # A broken line is reordered on its own. Wrapping does not drop glyphs.
    for index, line in enumerate(lines):
        if not isinstance(line, dict):
            raise _Invalid("line is invalid")
        rendered = str(line.get("text") or "")
        content = _px(line.get("content_width"), "line width")
        line_measure = measure
        origin = 0
        if text_indent and index == 0:
            line_measure = measure - text_indent
            if line_measure < 0:
                line_measure = 0
            origin = text_indent
        offset, used, runs = _align_content(box, line_measure, rendered, content, index == last, direction)
        glyphs = _bidi_glyphs(rendered, direction, box.font_size) if place_glyphs and not runs else []
        if glyphs and sum(int(glyph["width"]) for glyph in glyphs) != content:
            glyphs = []
        if shifted:
            if runs:
                raise _Invalid("justified relative inline is unsupported")
            if rendered and not collapsed.startswith(rendered):
                raise _Invalid("relative inline is unsupported")
            line_shifts = collapsed_shifts[shift_index : shift_index + len(rendered)]
            shift_index += len(rendered)
            collapsed = collapsed[len(rendered) :]
            collapsed_shifts = collapsed_shifts[shift_index:]
            shift_index = 0
            if collapsed.startswith(" "):
                collapsed = collapsed[1:]
                collapsed_shifts = collapsed_shifts[1:]
            runs = _relative_runs(
                rendered,
                line_shifts,
                box.font_size,
                box.content_width,
                box.definite_height,
                content,
            )
        records.append(
            _Line(
                text=rendered,
                x=offset + origin,
                y=cursor,
                height=height,
                content_width=used,
                baseline=baseline,
                glyphs=glyphs,
                runs=runs,
            )
        )
        cursor += height
    if shifted and collapsed.strip():
        raise _Invalid("relative inline is unsupported")
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


def _generating_children(
    tree,
    element,
    inherited: dict[str, str],
    fonts: dict[str, str],
    parent_direction: str | None,
    styles,
    declarations,
    ids: set[str],
    counter: list[int],
    *,
    reject_text,
) -> list[tuple[_Box, object]]:
    """Boxes that participate in the parent. ``display: contents`` is not one of them."""

    found: list[tuple[_Box, object]] = []

    def absorb(node, node_inherited: dict[str, str], node_fonts: dict[str, str], direction: str | None) -> None:
        for child in tree.children.get(node, []):
            reject_text(getattr(child, "tail", None))
            if not _local_name(child) or _local_name(child) in _SKIP_TAGS:
                continue
            box = _make_box(
                tree,
                child,
                node_inherited,
                node_fonts,
                direction,
                styles,
                declarations,
                ids,
                counter,
                root=False,
            )
            if box.display == "none":
                continue
            if box.display == "contents":
                reject_text(getattr(child, "text", None))
                absorb(child, _modes(box), _fonts(box), box.direction)
                continue
            found.append((box, child))

    absorb(element, inherited, fonts, parent_direction)
    return found


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
    host.counters_closed = True
    if host.writing_mode != "horizontal-tb" or host.direction != "ltr":
        raise _Invalid("flex writing mode is unsupported")
    items: list[_Box] = []
    pending: list[str] = []
    _collect_flex_items(
        tree,
        element,
        inherited,
        fonts,
        host.direction,
        styles,
        declarations,
        ids,
        counter,
        host,
        items,
        pending,
        host.font_size,
        host.line_height,
        host.white_space,
    )
    _flush_flex_text(host, pending, items, ids, counter)
    return items, [], items, []


def _collect_flex_items(
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
    items: list[_Box],
    pending: list[str],
    font: int,
    leading: str,
    white: str,
    *,
    generate: bool = True,
) -> None:
    """Flex items in source order, with text runs held until a real box."""

    before, after = _generated(tree, element) if generate else ("", "")
    if before:
        _append_flex_text(pending, before, font, leading, white, host)
        _flush_flex_text(host, pending, items, ids, counter)
    _append_flex_text(pending, getattr(element, "text", None), font, leading, white, host)
    column = str((host.flex or {}).get("direction") or "row") in {"column", "column-reverse"}
    for child in tree.children.get(element, []):
        if not _local_name(child) or _local_name(child) in _SKIP_TAGS:
            _append_flex_text(pending, getattr(child, "tail", None), font, leading, white, host)
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
            _append_flex_text(pending, getattr(child, "tail", None), font, leading, white, host)
            continue
        if box.display == "contents":
            _collect_flex_items(
                tree,
                child,
                _modes(box),
                _fonts(box),
                box.direction,
                styles,
                declarations,
                ids,
                counter,
                host,
                items,
                pending,
                box.font_size,
                box.line_height,
                box.white_space,
                generate=False,
            )
            _append_flex_text(pending, getattr(child, "tail", None), font, leading, white, host)
            continue
        _flush_flex_text(host, pending, items, ids, counter)
        if box.display in {"table", *_TABLE_OUTSIDE}:
            raise _Invalid("table formatting in flex is unsupported")
        if box.position != "static" or box.float_side != "none":
            raise _Invalid("flex item is outside the line")
        if box.writing_mode != "horizontal-tb" or box.direction != "ltr":
            raise _Invalid("flex writing mode is unsupported")
        if _flex_item_elements(tree, child):
            raise _Invalid("flex item content is unsupported")
        _reject_item_edges(box, column=column)
        box.inline_text = _leaf_generated(tree, child)
        box.flex = _flex_item(tree, child, styles, declarations)
        items.append(box)
        _append_flex_text(pending, getattr(child, "tail", None), font, leading, white, host)
    if after:
        _flush_flex_text(host, pending, items, ids, counter)
        _append_flex_text(pending, after, font, leading, white, host)
        _flush_flex_text(host, pending, items, ids, counter)


def _append_flex_text(
    pending: list[str],
    text: object,
    font: int,
    leading: str,
    white: str,
    host: _Box,
) -> None:
    if not isinstance(text, str) or text == "":
        return
    if text.strip() and (font != host.font_size or leading != host.line_height):
        raise _Invalid("flex text font is unsupported")
    if text.strip() and white != host.white_space:
        raise _Invalid("flex text white-space is unsupported")
    pending.append(text)


def _flex_anonymous_text(raw: str, white_space: str) -> str | None:
    if white_space in {"normal", "nowrap"}:
        collapsed = " ".join(raw.split())
        return collapsed or None
    if white_space == "pre-line":
        stripped = raw.strip()
        if not stripped:
            return None
        if "\n" in stripped or "\r" in stripped:
            raise _Invalid("flex preserved break is unsupported")
        return " ".join(raw.split())
    if white_space in {"pre", "pre-wrap", "break-spaces"}:
        if not raw.strip():
            return None
        if any(character in raw for character in "\n\r\t"):
            raise _Invalid("flex preserved break is unsupported")
        return raw
    raise _Invalid("flex white-space is unsupported")


def _flush_flex_text(
    host: _Box,
    pending: list[str],
    items: list[_Box],
    ids: set[str],
    counter: list[int],
) -> None:
    raw = "".join(pending)
    pending.clear()
    rendered = _flex_anonymous_text(raw, host.white_space)
    if not rendered:
        return
    items.append(
        _Box(
            id=_anonymous_id(ids, counter),
            writing_mode=host.writing_mode,
            direction=host.direction,
            text_orientation=host.text_orientation,
            display="block",
            position="static",
            float_side="none",
            overflow="visible",
            declarations=[],
            font_size=host.font_size,
            line_height=host.line_height,
            text_align=host.text_align,
            text_align_last=host.text_align_last,
            text_justify=host.text_justify,
            text_indent=host.text_indent,
            white_space=host.white_space,
            parent_direction=host.direction,
            inline_text=rendered,
            anonymous=True,
            parent_box=host,
            flex={"grow": 0.0, "shrink": 1.0, "basis": "auto", "align": "auto", "order": 0},
        )
    )


def _flex_item_elements(tree, element) -> bool:
    return any(_local_name(child) not in _SKIP_TAGS for child in tree.children.get(element, []))


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
    host.counters_closed = True
    if host.writing_mode != "horizontal-tb" or host.direction != "ltr":
        raise _Invalid("grid writing mode is unsupported")
    before, after = _generated(tree, element)
    _reject_grid_text(before)
    _reject_grid_text(after)
    _reject_grid_text(getattr(element, "text", None))
    items: list[_Box] = []
    for item, child in _generating_children(
        tree,
        element,
        inherited,
        fonts,
        host.direction,
        styles,
        declarations,
        ids,
        counter,
        reject_text=_reject_grid_text,
    ):
        if item.display in {"table", *_TABLE_OUTSIDE}:
            raise _Invalid("table formatting in grid is unsupported")
        if item.position != "static" or item.float_side != "none":
            raise _Invalid("grid item is outside the grid")
        if item.writing_mode != "horizontal-tb" or item.direction != "ltr":
            raise _Invalid("grid writing mode is unsupported")
        if _flex_item_elements(tree, child):
            _adopt_grid_item_blocks(tree, child, item, styles, declarations, ids, counter)
        else:
            item.inline_text = _leaf_generated(tree, child)
        container = item.grid if item.display == "grid" and isinstance(item.grid, dict) else None
        _reject_grid_edges(item)
        item.grid = _grid_item(tree, child, styles, declarations, item)
        if container and container.get("column_subgrid"):
            item.grid["column_subgrid"] = True
            item.grid["subgrid_gap"] = (
                "normal" if container.get("column_gap_normal", True) else container.get("column_gap", 0)
            )
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
    column_gap_normal = True
    column_subgrid = False
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
            if value == "subgrid":
                columns = []
                column_lines = None
                column_subgrid = True
            else:
                columns, column_lines = _grid_named_column_tracks(value)
                column_subgrid = False
        elif prop == "grid-template-rows":
            if value == "subgrid":
                raise _Invalid("row subgrid is unsupported")
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
            column_gap_normal = _gap_column_is_normal(value)
        elif prop == "row-gap":
            row_gap = _grid_gap_length(value)
        elif prop == "column-gap":
            column_gap_normal = value in {"normal", "initial", "unset", "revert"}
            column_gap = 0 if column_gap_normal else _grid_gap_length(value)
    if column_subgrid:
        if columns:
            raise _Invalid("subgrid track list is unsupported")
    elif not columns:
        raise _Invalid("grid template is unsupported")
    return {
        "columns": columns,
        "column_subgrid": column_subgrid,
        "column_gap_normal": column_gap_normal,
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


def _gap_column_is_normal(value: str) -> bool:
    parts = value.split(" ")
    token = parts[-1] if parts else value
    return token in {"normal", "initial", "unset", "revert"}


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
    if spec.get("column_subgrid"):
        raise _Invalid("subgrid is not a grid item")
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


def _lay_grid_item_blocks(
    item: _Box,
    viewport_height: int | None,
    *,
    reason: str = "grid item content is unsupported",
) -> int:
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
        raise _Invalid(str(placed.get("reason") or reason))
    by_id = {str(entry.get("id")): entry for entry in boxes if isinstance(entry, dict)}
    parent = by_id.get(item.id)
    if parent is None:
        raise _Invalid(reason)
    for child in item.children:
        _stamp_grid_child(child, by_id, -inset_y, reason)
    return _px(parent.get("border_height"), "grid item")


def _stamp_grid_child(
    box: _Box,
    by_id: dict[str, dict[str, object]],
    parent_y: int,
    reason: str = "grid item content is unsupported",
) -> None:
    record = by_id.get(box.id)
    if record is None:
        raise _Invalid(reason)
    border_y = _px(record.get("y"), "y")
    box.anchor_y = border_y - parent_y
    box.border_height = _px(record.get("border_height"), "border height")
    box.content_height = box.border_height - _edge_extent(box.solved, "top", "bottom")
    if box.content_height < 0:
        raise _Invalid("content height is invalid")
    for child in box.children:
        _stamp_grid_child(child, by_id, border_y, reason)


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
        if (item.grid or {}).get("column_subgrid"):
            heights[item.id] = _place_column_subgrid(item, entry, column_sizes, column_gap, content_x)
        elif item.children:
            heights[item.id] = _lay_grid_item_blocks(item, viewport_height)
        elif item.inline_text:
            item.lines = _plain_lines(item, item.content_width, item.direction)
            heights[item.id] = sum(line.height for line in item.lines)
        else:
            heights[item.id] = 0
    return heights


def _subgrid_child_line(spec: dict[str, object], cursor: int, covered: int) -> tuple[int, int, int]:
    """Map one subgrid child's column placement to a solver line and span."""

    start = spec.get("column_start", "auto")
    end = spec.get("column_end", "auto")
    if start == "auto" and end == "auto":
        if cursor > covered:
            raise _Invalid("subgrid grows no implicit track")
        return cursor, 1, cursor + 1
    if start == "auto" and isinstance(end, str) and end.startswith("span "):
        span = int(end[5:])
        if span < 1 or cursor > covered:
            raise _Invalid("subgrid grows no implicit track")
        return cursor, span, cursor + span
    if isinstance(start, int) and not isinstance(start, bool) and end == "auto":
        return start, 1, cursor
    if isinstance(start, int) and not isinstance(start, bool) and isinstance(end, str) and end.startswith("span "):
        span = int(end[5:])
        if span < 1:
            raise _Invalid("subgrid line is unsupported")
        return start, span, cursor
    if (
        isinstance(start, int)
        and not isinstance(start, bool)
        and isinstance(end, int)
        and not isinstance(end, bool)
        and start > 0
        and end > start
    ):
        return start, end - start, cursor
    raise _Invalid("subgrid line is unsupported")


def _place_column_subgrid(
    item: _Box,
    entry: dict[str, object],
    column_sizes: list[int],
    column_gap: int,
    content_x: int,
) -> int:
    """Place a column subgrid's children on the parent tracks that item spans."""

    span_start = int(entry.get("column") or 0)
    span = int(entry.get("column_span") or 0)
    if span_start < 1 or span < 1 or span_start - 1 + span > len(column_sizes):
        raise _Invalid("subgrid span is outside the parent grid")
    if (item.grid or {}).get("width", "auto") != "auto":
        raise _Invalid("subgrid item width is unsupported")
    if not item.children:
        raise _Invalid("subgrid item is missing")
    payload: list[dict[str, object]] = []
    heights: dict[str, int] = {}
    cursor = 1
    for child in item.children:
        spec = child.grid if isinstance(child.grid, dict) else {}
        if spec.get("width", "auto") != "auto":
            raise _Invalid("subgrid item width is unsupported")
        height = spec.get("height", "auto")
        if type(height) is not int:
            raise _Invalid("subgrid item height is unsupported")
        if child.children or (child.inline_text or "").strip():
            raise _Invalid("subgrid item content is unsupported")
        if child.position != "static" or child.float_side != "none":
            raise _Invalid("subgrid item is outside the grid")
        line, item_span, cursor = _subgrid_child_line(spec, cursor, span)
        payload.append({"id": child.id, "start": line, "span": item_span})
        heights[child.id] = height
    spec = item.grid if isinstance(item.grid, dict) else {}
    placed = place_subgrid_items(
        column_sizes,
        payload,
        gap=column_gap,
        span_start=span_start,
        span=span,
        subgrid_gap=spec.get("subgrid_gap", "normal"),
        edge_start=_edge_extent(item.solved, "left"),
        edge_end=_edge_extent(item.solved, "right"),
    )
    boxes = placed.get("items")
    if placed.get("outcome") != "placed" or not isinstance(boxes, list):
        raise _Invalid(str(placed.get("reason") or "subgrid placement failed"))
    by_id = {str(row.get("id")): row for row in boxes if isinstance(row, dict)}
    top = _edge_extent(item.solved, "top")
    used = 0
    for child in item.children:
        found = by_id.get(child.id)
        if found is None:
            raise _Invalid("subgrid placement failed")
        _install_grid_chrome(child)
        chrome_x = _edge_extent(child.solved, "left", "right")
        chrome_y = _edge_extent(child.solved, "top", "bottom")
        size = _px(found.get("size"), "subgrid item")
        child.content_width = size - chrome_x
        if child.content_width < 0:
            raise _Invalid("subgrid item width is invalid")
        child.border_width = child.content_width + chrome_x
        child.content_height = heights[child.id]
        child.border_height = child.content_height + chrome_y
        child.x = content_x + _px(found.get("start"), "subgrid item")
        child.anchor_y = top
        child.margin_left = 0
        child.margin_right = 0
        used = max(used, child.border_height)
    return used


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
_TABLE_SPAN_LIMIT = 1000


def _html_table_span(element, name: str) -> int:
    raw = _attr(element, name)
    if raw is None or not raw.strip():
        return 1
    token = raw.strip()
    if not token.isdigit():
        raise _Invalid("table span is unsupported")
    value = int(token)
    if value < 1:
        raise _Invalid("table span is unsupported")
    if value > _TABLE_SPAN_LIMIT:
        return _TABLE_SPAN_LIMIT
    return value


def _assign_table_slots(rows: list[_Box]) -> None:
    """Occupy grid slots the way an HTML table does.

    A cell starts at the first free column of its row. ``colspan`` and
    ``rowspan`` mark that rectangle. A later cell skips occupied slots.
    A span that would cover an occupied slot is a document error. Rows that
    were never generated are not invented; the span stops at the last row.
    """

    occupied: set[tuple[int, int]] = set()
    row_count = len(rows)
    for row_index, row in enumerate(rows):
        cursor = 0
        for cell in row.children:
            table = cell.table or {}
            span = table.get("span")
            rowspan = table.get("rowspan")
            if (
                isinstance(span, bool)
                or isinstance(rowspan, bool)
                or not isinstance(span, int)
                or not isinstance(rowspan, int)
                or span < 1
                or rowspan < 1
            ):
                raise _Invalid("table span is unsupported")
            while (row_index, cursor) in occupied:
                cursor += 1
            covered = min(rowspan, row_count - row_index)
            for dy in range(covered):
                for dx in range(span):
                    if (row_index + dy, cursor + dx) in occupied:
                        raise _Invalid("table cell overlap is unsupported")
            for dy in range(covered):
                for dx in range(span):
                    occupied.add((row_index + dy, cursor + dx))
            table["column"] = cursor
            table["span"] = span
            table["rowspan"] = covered
            cell.table = table
            cursor += span


def _cell_slot(cell: _Box) -> tuple[int, int, int]:
    table = cell.table or {}
    column = table.get("column")
    span = table.get("span")
    rowspan = table.get("rowspan")
    if (
        isinstance(column, bool)
        or isinstance(span, bool)
        or isinstance(rowspan, bool)
        or not isinstance(column, int)
        or not isinstance(span, int)
        or not isinstance(rowspan, int)
        or column < 0
        or span < 1
        or rowspan < 1
    ):
        raise _Invalid("table placement failed")
    return column, span, rowspan


def _table_column_count(rows: list[_Box]) -> int:
    count = 0
    for row in rows:
        for cell in row.children:
            column, span, _rowspan = _cell_slot(cell)
            count = max(count, column + span)
    if count < 1:
        raise _Invalid("table is empty")
    return count


def _span_metrics(
    positions: list[int],
    starts: list[int],
    ends: list[int],
    sizes: list[int],
    index: int,
    span: int,
) -> tuple[int, int, int, int]:
    if span < 1 or index < 0 or index + span > len(sizes):
        raise _Invalid("table placement failed")
    last = index + span - 1
    border = positions[last] + starts[last] + sizes[last] + ends[last] - positions[index]
    content = border - starts[index] - ends[last]
    if content < 0:
        raise _Invalid("table placement failed")
    return positions[index], content, starts[index], ends[last]
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
    host.counters_closed = True
    if host.table.get("collapse") is True:
        host.table["borders"] = _specified_borders(host)
        host.declarations = [
            (prop, value) for prop, value in host.declarations if not _border_declaration(prop)
        ]
    if host.writing_mode != "horizontal-tb" or host.direction != "ltr":
        raise _Invalid("table writing mode is unsupported")
    before, after = _generated(tree, element)
    _reject_table_text(before)
    _reject_table_text(after)
    _reject_table_text(getattr(element, "text", None))
    rows: list[_Box] = []
    captions: list[_Box] = []
    for row, child in _generating_children(
        tree,
        element,
        inherited,
        fonts,
        host.direction,
        styles,
        declarations,
        ids,
        counter,
        reject_text=_reject_table_text,
    ):
        if row.display == "table-caption":
            _take_table_caption(tree, child, row, host, styles, declarations)
            captions.append(row)
            continue
        if row.display != "table-row":
            raise _Invalid("table row is unsupported")
        if row.position != "static" or row.float_side != "none":
            raise _Invalid("table row is outside the table")
        if row.writing_mode != "horizontal-tb" or row.direction != "ltr":
            raise _Invalid("table writing mode is unsupported")
        if host.table.get("collapse") is True:
            row.table = {"borders": _specified_borders(row)}
        row_before, row_after = _generated(tree, child)
        _reject_table_text(row_before)
        _reject_table_text(row_after)
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
    if len(captions) > 1:
        raise _Invalid("table caption count is unsupported")
    if not rows:
        raise _Invalid("table is empty")
    _assign_table_slots(rows)
    if host.table is None:
        raise _Invalid("table placement failed")
    host.table["captions"] = captions
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
    for cell, child in _generating_children(
        tree,
        row_element,
        inherited,
        fonts,
        host.direction,
        styles,
        declarations,
        ids,
        counter,
        reject_text=_reject_table_text,
    ):
        if cell.display != "table-cell":
            raise _Invalid("table cell is unsupported")
        if cell.position != "static" or cell.float_side != "none":
            raise _Invalid("table cell is outside the table")
        if cell.writing_mode != "horizontal-tb" or cell.direction != "ltr":
            raise _Invalid("table writing mode is unsupported")
        collapse = host.table.get("collapse") is True
        _reject_table_edges(cell, collapse=collapse)
        if _table_cell_elements(tree, child):
            _adopt_table_cell_blocks(tree, child, cell, styles, declarations, ids, counter)
        else:
            for grand in tree.children.get(child, []):
                _reject_table_text(getattr(grand, "tail", None))
            cell.inline_text = _leaf_generated(tree, child)
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
    spacing_x = 0
    spacing_y = 0
    caption_side = "top"
    for _order, prop, raw in _winners(tree, element, declarations):
        if prop == "table-layout":
            layout = _choice(_grid_author(raw, custom), "auto", _TABLE_LAYOUTS, "table-layout")
            continue
        if prop not in _TABLE_CHROME:
            continue
        value = _grid_author(raw, custom)
        if prop == "border-spacing":
            spacing_x, spacing_y = _border_spacing(value)
            continue
        if prop == "border-collapse":
            if value == "collapse":
                collapse = True
            elif value not in {"separate", "initial", "unset", "revert"}:
                raise _Invalid("table border collapse is unsupported")
            continue
        if prop == "caption-side":
            caption_side = _caption_side_token(value)
            continue
        if prop == "empty-cells" and value not in {"show", "initial", "unset", "revert"}:
            raise _Invalid("table empty cells are unsupported")
    return {
        "layout": layout,
        "collapse": collapse,
        "spacing_x": spacing_x,
        "spacing_y": spacing_y,
        "caption_side": caption_side,
    }


def _caption_side_token(value: str) -> str:
    if value in {"top", "initial", "unset", "revert"}:
        return "top"
    if value == "bottom":
        return "bottom"
    if value == "inherit":
        raise _Invalid("table caption inherit is unsupported")
    raise _Invalid("table caption is unsupported")


def _element_caption_side(tree, element, styles, declarations) -> str | None:
    custom = styles.get(element, ({}, ""))[0]
    chosen = None
    for _order, prop, raw in _winners(tree, element, declarations):
        if prop == "caption-side":
            chosen = _grid_author(raw, custom)
    if chosen is None:
        return None
    return _caption_side_token(chosen)


def _take_table_caption(tree, element, caption: _Box, host: _Box, styles, declarations) -> None:
    if caption.position != "static" or caption.float_side != "none":
        raise _Invalid("table caption is outside the table")
    if caption.writing_mode != "horizontal-tb" or caption.direction != "ltr":
        raise _Invalid("table caption writing mode is unsupported")
    if _table_cell_elements(tree, element):
        raise _Invalid("table caption content is unsupported")
    for node in tree.children.get(element, []):
        _reject_table_text(getattr(node, "tail", None))
    text = getattr(element, "text", None) or ""
    if not str(text).strip():
        raise _Invalid("table caption is empty")
    _reject_caption_chrome(caption)
    declared = _element_caption_side(tree, element, styles, declarations)
    fallback = str((host.table or {}).get("caption_side") or "top")
    caption.inline_text = str(text)
    caption.table = {"caption_side": declared if declared is not None else fallback}


def _reject_caption_chrome(box: _Box) -> None:
    sizing = _box_decl(box, "box-sizing")
    if sizing not in {None, "content-box", "initial", "unset", "revert"}:
        raise _Invalid("table caption edge is unsupported")
    for name in (*_FLEX_EDGES, "margin", "padding", "border-width", "width", "height"):
        raw = _box_decl(box, name)
        if raw is None:
            continue
        token = raw.strip().lower()
        if name in {"width", "height"} and token in {"auto", "initial", "unset", "revert"}:
            continue
        if token in _ZERO_EDGE | {"none", "auto"}:
            continue
        raise _Invalid("table caption edge is unsupported")
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
        raise _Invalid("table caption edge is unsupported")


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
    return {
        "width": width,
        "vertical_align": align,
        "span": _html_table_span(element, "colspan"),
        "rowspan": _html_table_span(element, "rowspan"),
    }


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
    cells = []
    for row_index, row in enumerate(rows):
        for cell in row.children:
            column, span, rowspan = _cell_slot(cell)
            cells.append(
                {
                    "row": row_index,
                    "column": column,
                    "span": span,
                    "rowspan": rowspan,
                    "borders": (cell.table or {}).get("borders") or {},
                }
            )
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
        for cell in row.children:
            entry = by_id.get(cell.id)
            if entry is None:
                raise _Invalid("table placement failed")
            column, span, rowspan = _cell_slot(cell)
            _x_off, content_w, left, right = _span_metrics(xs, lefts, rights, column_sizes, column, span)
            _y_off, content_h, cell_top, cell_bottom = _span_metrics(
                ys, tops, bottoms, row_heights, row_index, rowspan
            )
            shift = _px(entry.get("content_top"), "table cell")
            cell_solved = dict(_ZERO_FLEX_EDGES)
            cell_solved["border_left"] = left
            cell_solved["border_right"] = right
            cell_solved["border_top"] = cell_top
            cell_solved["border_bottom"] = cell_bottom
            cell.solved = cell_solved
            cell.x = content_x + xs[column]
            # The row already carries this grid position. Cells are offset from the row.
            cell.anchor_y = 0
            cell.content_width = content_w
            cell.content_height = content_h
            cell.border_width = left + content_w + right
            cell.border_height = cell_top + content_h + cell_bottom
            cell.margin_left = 0
            cell.margin_right = 0
            if cell.table is None:
                cell.table = {}
            cell.table["used_edges"] = {
                "left": _used_edge(vertical[column], left),
                "right": _used_edge(vertical[column + span], right),
                "top": _used_edge(horizontal[row_index], cell_top),
                "bottom": _used_edge(horizontal[row_index + rowspan], cell_bottom),
            }
            for line in cell.lines:
                line.y += shift
            _shift_cell_children(cell, shift)
    box.anchor_laid = True


def _table_cell_elements(tree, element) -> bool:
    return any(
        _local_name(node) and _local_name(node) not in _SKIP_TAGS
        for node in tree.children.get(element, [])
    )


def _adopt_table_cell_blocks(
    tree,
    element,
    cell: _Box,
    styles,
    declarations,
    ids: set[str],
    counter: list[int],
) -> None:
    """Take a cell's static block children. Mixed text and other displays stay rejected."""

    if _grid_text(getattr(element, "text", None)):
        raise _Invalid("table cell content is unsupported")
    for node in tree.children.get(element, []):
        if _grid_text(getattr(node, "tail", None)):
            raise _Invalid("table cell content is unsupported")
    found, floats, _flow, positioned = _walk(
        tree,
        element,
        _modes(cell),
        _fonts(cell),
        cell.direction,
        styles,
        declarations,
        ids,
        counter,
        cell,
    )
    if floats or positioned or cell.atoms or not found:
        raise _Invalid("table cell content is unsupported")
    for child in found:
        _reject_table_cell_block(child)
    cell.children = found
    cell.flow = list(found)


def _reject_table_cell_block(box: _Box) -> None:
    if box.display != "block" or box.position != "static" or box.float_side != "none":
        raise _Invalid("table cell content is unsupported")
    if box.writing_mode != "horizontal-tb" or box.direction != "ltr":
        raise _Invalid("table cell content is unsupported")
    if box.floats or box.positioned or box.atoms or box.multicol is not None:
        raise _Invalid("table cell content is unsupported")
    if box.flex is not None or box.grid is not None or box.table is not None:
        raise _Invalid("table cell content is unsupported")
    if box.children and box.inline_text:
        raise _Invalid("table cell content is unsupported")
    sizing = _box_decl(box, "box-sizing")
    if sizing not in {None, "content-box", "initial", "unset", "revert"}:
        raise _Invalid("table cell content is unsupported")
    for child in box.children:
        _reject_table_cell_block(child)


def _cell_content_bounds(cell: _Box) -> tuple[int, int]:
    """Min and max content of a cell, including a block child's text."""

    if cell.children:
        bounds = [_nested_block_intrinsic(child) for child in cell.children]
        return max(bound[0] for bound in bounds), max(bound[1] for bound in bounds)
    return _intrinsic_text_sizes(cell)


def _cell_content_baseline(cell: _Box) -> int:
    """Distance from the cell content top to the first line baseline."""

    if cell.lines:
        return int(cell.lines[0].baseline)
    found = _first_block_baseline(cell, -_edge_extent(cell.solved, "top"))
    return 0 if found is None else found


def _first_block_baseline(box: _Box, border_top: int) -> int | None:
    if box.lines:
        return border_top + _edge_extent(box.solved, "top") + int(box.lines[0].y) + int(box.lines[0].baseline)
    for child in box.children:
        if child.anchor_y is None:
            continue
        found = _first_block_baseline(child, border_top + child.anchor_y)
        if found is not None:
            return found
    return None


def _shift_cell_children(cell: _Box, shift: int) -> None:
    if shift == 0:
        return
    for child in cell.children:
        if child.anchor_y is not None:
            child.anchor_y += shift


def _border_spacing(value: str) -> tuple[int, int]:
    if value in {"initial", "unset", "revert"}:
        return 0, 0
    if value == "inherit":
        raise _Invalid("table spacing inherit is unsupported")
    parts = value.split(" ")
    if len(parts) == 1:
        length = _spacing_px(parts[0])
        return length, length
    if len(parts) == 2:
        return _spacing_px(parts[0]), _spacing_px(parts[1])
    raise _Invalid("table spacing is unsupported")


def _spacing_px(value: str) -> int:
    if value == "0":
        return 0
    if not value.endswith("px"):
        raise _Invalid("table spacing is unsupported")
    try:
        number = float(value[:-2])
    except ValueError as exc:
        raise _Invalid("table spacing is unsupported") from exc
    length = _px(number, "table spacing")
    if length < 0:
        raise _Invalid("table spacing is unsupported")
    return length


def _used_table_spacing(box: _Box) -> tuple[int, int]:
    table = box.table or {}
    return (
        _px(table.get("spacing_x", 0), "table spacing"),
        _px(table.get("spacing_y", 0), "table spacing"),
    )


def _spaced_column_offsets(sizes: list[int], gap: int, lead: int) -> list[int]:
    offsets: list[int] = []
    cursor = lead
    for size in sizes:
        offsets.append(cursor)
        cursor += size + gap
    return offsets


def _place_table(box: _Box, content_x: int) -> None:
    if box.writing_mode != "horizontal-tb" or box.direction != "ltr":
        raise _Invalid("table writing mode is unsupported")
    rows = box.children
    if not rows or any(not row.children for row in rows):
        raise _Invalid("table is empty")
    count = _table_column_count(rows)
    available = box.content_width
    width_auto = box.solved.get("specified_width") in {None, "auto"}
    layout = str((box.table or {}).get("layout") or "auto")
    collapse = (box.table or {}).get("collapse") is True
    captions = list((box.table or {}).get("captions") or [])
    if captions and collapse:
        raise _Invalid("table caption collapse is unsupported")
    if collapse and (layout == "fixed" or not width_auto):
        raise _Invalid("collapsed table width is unsupported")
    spacing_x, spacing_y = (0, 0) if collapse else _used_table_spacing(box)
    fixed_width = layout == "fixed" and not width_auto
    if fixed_width:
        first = sorted(rows[0].children, key=lambda item: _cell_slot(item)[0])
        sized = layout_fixed_columns(
            available,
            ["auto"] * count,
            cells=[_fixed_cell(cell) for cell in first],
            spacing=spacing_x,
        )
    else:
        payload: list[dict[str, object]] = []
        for row in rows:
            for cell in row.children:
                column, span, _rowspan = _cell_slot(cell)
                minimum, maximum = _cell_content_bounds(cell)
                item: dict[str, object] = {
                    "column": column,
                    "span": span,
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
            spacing=spacing_x,
        )
    raw_sizes = sized.get("column_widths")
    if sized.get("outcome") != "resolved" or not isinstance(raw_sizes, list) or len(raw_sizes) != count:
        raise _Invalid(str(sized.get("reason") or "table columns failed"))
    column_sizes = [_px(size, "table column") for size in raw_sizes]
    used_width = _px(sized.get("used_table_width"), "table width")
    box.content_width = used_width
    inline_axis: tuple[list[int], list[int], list[int]] | None = None
    block_tops: list[int] | None = None
    column_offsets = _spaced_column_offsets(column_sizes, spacing_x, spacing_x if not fixed_width else 0)
    if collapse:
        vertical, horizontal = _collapsed_lines(box, rows, len(column_sizes))
        xs, lefts, rights, _outer_left, _outer_right, _inner = _collapsed_axis(column_sizes, vertical)
        inline_axis = (xs, lefts, rights)
        if any(cell.children for row in rows for cell in row.children):
            _ignored, block_tops, _bottoms, _table_top, _table_bottom, _inner_height = _collapsed_axis(
                [0] * len(rows), horizontal
            )
    row_cells: list[dict[str, object]] = []
    for row_index, row in enumerate(rows):
        for cell in row.children:
            column, span, rowspan = _cell_slot(cell)
            if inline_axis is None:
                cell.content_width = _grid_span(column_sizes, column, span, spacing_x)
            else:
                axis_x, axis_left, axis_right = inline_axis
                cell.content_width = _span_metrics(
                    axis_x, axis_left, axis_right, column_sizes, column, span
                )[1]
            if cell.children:
                if inline_axis is None:
                    cell.x = content_x + column_offsets[column]
                    cell.solved = dict(_ZERO_FLEX_EDGES)
                else:
                    axis_x, axis_left, axis_right = inline_axis
                    _x_off, _content_w, left, right = _span_metrics(
                        axis_x, axis_left, axis_right, column_sizes, column, span
                    )
                    cell.x = content_x + axis_x[column]
                    top = block_tops[row_index] if block_tops is not None else 0
                    solved = dict(_ZERO_FLEX_EDGES)
                    solved["border_left"] = left
                    solved["border_right"] = right
                    solved["border_top"] = top
                    cell.solved = solved
                cell.definite_height = _lay_grid_item_blocks(
                    cell, None, reason="table cell content is unsupported"
                )
            elif (cell.inline_text or "").strip() or cell.white_space not in _COLLAPSED_EMPTY:
                _fill_lines(cell)
            row_cells.append(
                {
                    "id": cell.id,
                    "row": row_index,
                    "rowspan": rowspan,
                    "content_height": cell.definite_height or 0,
                    "baseline": _cell_content_baseline(cell),
                    "vertical_align": str((cell.table or {}).get("vertical_align") or "baseline"),
                }
            )
    laid = layout_table_rows(
        ["auto"] * len(rows),
        row_cells,
        table_height="auto" if box.definite_height is None else box.definite_height,
        border_spacing=spacing_y,
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
        for cell in row.children:
            entry = by_id.get(cell.id)
            if entry is None:
                raise _Invalid("table placement failed")
            column, span, _rowspan = _cell_slot(cell)
            slot = _px(entry.get("border_height"), "table cell")
            shift = _px(entry.get("content_top"), "table cell")
            cell_top = _px(entry.get("border_top"), "table cell")
            content_width = _grid_span(column_sizes, column, span, spacing_x)
            cell.x = content_x + column_offsets[column]
            cell.anchor_y = cell_top - row_top
            cell.content_width = content_width
            cell.content_height = slot
            cell.border_width = content_width
            cell.border_height = slot
            cell.margin_left = 0
            cell.margin_right = 0
            cell.solved = dict(_ZERO_FLEX_EDGES)
            for line in cell.lines:
                line.y += shift
            _shift_cell_children(cell, shift)
    box.definite_height = _px(laid.get("used_table_height"), "table height")
    _lay_table_caption(box, rows, content_x)
    box.anchor_laid = True


def _lay_table_caption(box: _Box, rows: list[_Box], content_x: int) -> None:
    """Stack the one text caption above or below the grid. Columns stay put."""

    captions = list((box.table or {}).get("captions") or [])
    if not captions:
        return
    if len(captions) != 1 or not isinstance(captions[0], _Box):
        raise _Invalid("table caption count is unsupported")
    caption = captions[0]
    side = str((caption.table or {}).get("caption_side") or "top")
    if side not in {"top", "bottom"}:
        raise _Invalid("table caption is unsupported")
    for key in (
        "border_top",
        "border_right",
        "border_bottom",
        "border_left",
        "padding_top",
        "padding_right",
        "padding_bottom",
        "padding_left",
    ):
        if _px(box.solved.get(key), key) != 0:
            raise _Invalid("table caption edge is unsupported")
    if box.definite_height is None:
        raise _Invalid("table placement failed")
    caption.content_width = box.content_width
    caption.x = content_x
    caption.solved = dict(_ZERO_FLEX_EDGES)
    caption.margin_left = 0
    caption.margin_right = 0
    _fill_lines(caption)
    caption_height = 0 if caption.definite_height is None else caption.definite_height
    caption.content_height = caption_height
    caption.border_width = box.content_width
    caption.border_height = caption_height
    grid_height = box.definite_height
    if side == "top":
        for row in rows:
            if row.anchor_y is None:
                raise _Invalid("table placement failed")
            row.anchor_y += caption_height
        caption.anchor_y = 0
    else:
        caption.anchor_y = grid_height
    box.definite_height = grid_height + caption_height
    box.children.append(caption)


def _fixed_cell(cell: _Box) -> dict[str, object]:
    width = (cell.table or {}).get("width", "auto")
    _column, span, _rowspan = _cell_slot(cell)
    return {"span": span, "width": "auto" if width == "auto" else width}
