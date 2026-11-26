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
the following block stay put. Beside a float, that same offset paints on the
shortened line: a percentage left uses the paragraph content width, and the
float and the following block stay at their static positions. A vertical
writing mode, a non-ltr paragraph, white-space other than normal, a different
font, and an inline-block inside it stay rejected. An absolute or fixed box uses the padding edge of the nearest ancestor that captures it. A position other than static captures an absolute box only. A transform, filter, perspective, backdrop-filter, paint or layout containment, hidden content-visibility, or capturing will-change captures both, including translate(0) on a static box. Otherwise an absolute box uses the viewport when no ancestor is positioned, and a fixed box uses the viewport. An inline capturer is rejected. Neither out-of-flow box changes the height of the flow.
A sticky block keeps the place it occupied in the flow. Its used border box
then shifts against the nearest non-visible overflow scrollport, or against
the viewport when every ancestor is visible. ``scroll_x`` and ``scroll_y``
move only that viewport. A nearer scrollport uses ``port_scroll`` when that
port scrolls on its own, and otherwise stays at scroll zero. The parent
padding edge stops the shift, and the following sibling stays at its static
position. A sticky descendant is shifted after that ancestor, so it keeps
the ancestor's shift until the ancestor's containing block stops the ancestor,
and it can then still meet the viewport inset inside the ancestor padding edge.
A sticky float, a sticky inline, a sticky root, and a non-horizontal or
non-ltr sticky box are rejected.
Horizontal text inside that box supplies shrink-to-fit width and the stacked
line-box height. A static block child is laid out in that content box: its
text wraps to the definite width, adjoining child margins collapse inside
the absolute formatting context, and an automatic height grows to the last
child's margin edge. An automatic width with an automatic horizontal inset
shrinks to those children: the used content width is the minimum of their
max-content and the maximum of their min-content and the available space.
A child margin stays inside that box. A plain percentage width on that
child is cyclic: shrink-to-fit uses the child's min-content and max-content
as if the percentage were auto, then the used width is that percentage of
the definite shrink width. An intrinsic limit, a float, and a nested
positioned box stay rejected. Automatic insets
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
height, and ``position-area`` on a static box are rejected. ``anchor-size()``
on that absolute or fixed box copies one border-box edge of its anchor into
``width``, ``height``, or their minimum and maximum. An omitted keyword uses
the property's axis, ``width`` and ``height`` are physical, and ``block``
follows a horizontal containing block. The function may name the anchor, or
it uses ``position-anchor`` when the name is omitted. A length or percentage
fallback is used when that anchor is missing; the percentage uses the
containing block's size on that axis. A missing fallback, a static box, a
float or other out-of-flow anchor, an anchor inside the positioned box, and
a vertical or non-ltr box are rejected. ``anchor()`` on ``left``, ``right``,
``top``, or ``bottom`` of that same absolute or fixed box is resolved before
the inset equation. The margin edge lines up with the requested edge of the
named in-flow anchor. An omitted name uses ``position-anchor``. ``center``
and a percentage select a point on the property's axis. A missing anchor, or
a side on the wrong axis, uses a ``px`` or percentage fallback when one is
written and is invalid without one. The following in-flow block stays where
it was. A static, relative, or sticky box, a float or other out-of-flow
anchor, an anchor inside the positioned box, a vertical box, and a non-ltr
box are rejected. ``position-area`` still moves the box after that inset is
solved. A float inside
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
down to those floats. ``display: flow-root`` is a block formatting context
on that same horizontal line: child margins stay inside it, and an empty
flow-root keeps its top and bottom margins apart. Beside a float, an
automatic width fills the leftover inline space and a specified width that
does not fit starts under the float. A plain block still keeps its full
width and only shortens its lines. A vertical writing mode, a replaced
flow-root, and columns on a flow-root stay rejected. Text in the float is wrapped in its content box.
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
glyphs. A uniform line shortened by a float records those glyphs from that
line's left edge: a Hebrew word beside the float starts after it, and a
Hebrew word under the float returns to the content start. A direction-rtl
paragraph keeps that float on the physical left of its own content box, and
the shortened line packs toward the content's right edge. A short Hebrew
word therefore stays on that edge instead of starting after the float, and
the following block still starts under the float. A right float occupies
the physical right of the same content box, and the line packs against it.
Justification and a relative inline still omit glyphs. A vertical writing
mode, and a following sibling whose own direction is rtl, stay rejected.
``line-height: normal`` uses the font
size as the strut. ``text-align`` shifts each line inside its line box.
``justify`` and ``justify-all`` give the aligner one item per word, so leftover
inline space is added to the interior gaps instead of sitting after the line.
The last line of ``justify`` stays packed unless ``text-align-last: justify``
or ``justify-all`` stretches it. ``text-justify: none`` leaves the gaps alone,
and ``inter-character`` also opens the gaps inside a word. A line with no
interior gap does not move, and leftover space is never compressed. Preserved
white space, a non-ltr direction, a mixed font, an inline-block, and a
relative inline stay rejected. ``vertical-rl`` and ``vertical-lr`` open those
gaps down the inline axis: a word's physical height is its advance and its
physical width is the column. ``sideways-lr`` stays rejected. ``text-indent`` moves the first line of a
horizontal left-to-right block and shortens that line's wrap measure by the
same amount. ``hanging`` inverts that: the first line stays at the content
edge and uses the full measure, and every later line starts at the indent
and wraps in the shortened measure. ``each-line`` restarts that choice after
a preserved newline, so each forced segment indents its first line and a
soft wrap inside the segment does not. ``hanging each-line`` indents only
those soft wraps. The keywords may precede or follow the length, in either
order. A length may be negative and can start the affected line outside
the content edge. A percentage is resolved against the containing block's
inline size and is inherited as that percentage, so a child can clear it
with zero. A float intrusion,
an inline-block, a mixed font, an inside marker, and a vertical writing mode
stay rejected. ``letter-spacing`` is a length inserted between characters of a
horizontal line and omitted after the last character, so a positive value
wraps sooner and a negative value shortens the line. ``word-spacing`` is added
only to word separators. Both inherit, ``normal`` is zero, and a percentage is
invalid. Justification of a spaced line, a vertical writing mode, an inside
marker, and a declaration on an inline stay rejected. ``text-autospace`` is
inherited. An omitted value stays flush. ``normal`` and ``ideograph-alpha``
open an eighth of an ideograph between a CJK letter and a non-CJK letter;
``ideograph-numeric`` does that between a CJK letter and a digit. The gap is
a soft wrap opportunity, so a narrow measure breaks where the scripts meet.
``insert`` keeps a real space, and ``replace`` spends that space on the gap.
``no-autospace`` clears an inherited value. ``auto``, ``punctuation``, a
vertical writing mode, and a declaration on an inline are rejected.
``text-transform`` is
inherited and applied before wrapping. ``uppercase`` and ``lowercase`` use
Unicode case mapping, so a German eszett becomes two letters and can push
the next word onto the following line. ``capitalize`` titlecases the first
letter of each word and leaves the rest of the word unchanged. ``none`` is
the initial value. A flex, grid, or table box, a vertical writing mode, a
non-ltr direction, and a declaration on an inline are rejected. ``tab-size`` is
inherited as a number of space advances or as a ``px`` length. Preserved
white space advances a tab from the line content start to the next multiple
of that interval, so the glyphs after the tab and the following block use
the stop. ``normal`` and ``nowrap`` still collapse the tab into one space.
Zero is an empty advance. A negative value, a percentage, and a declaration
on an inline are rejected. ``overflow-wrap`` and
``word-break`` are inherited and change those breaks. ``anywhere`` and
``break-all`` split a word that does not fit and lower a shrink-to-fit minimum
to one character. ``break-word`` splits the same definite line and leaves that
minimum at the whole word. ``keep-all`` keeps a Han run together for the
minimum and still wraps it inside a definite measure. ``word-wrap`` is the
same property as ``overflow-wrap``. Any other keyword is invalid, and a
declaration of either property on an inline is rejected. ``hyphens`` is
inherited. ``manual`` breaks only at a soft hyphen, and ``none`` does not
break there. ``auto`` also breaks an English word, when the element's
language is ``en``, at a Liang pattern boundary and draws U+2010 on the
line that takes the break. A word shorter than five letters, or a break
that would leave fewer than two letters on either side, stays whole.
Another language has no patterns. Those automatic breaks do not lower a
float's min-content, so shrink-to-fit keeps the whole word. An inline
``hyphens`` declaration, and an inline whose language differs from that
block, are rejected. ``hyphenate-character`` is inherited. ``auto`` draws
U+2010. A quoted string replaces that mark on every taken automatic or
soft-hyphen break, and an empty string keeps the break without the advance,
so a later opportunity can fit and a longer string can prevent the default
break and move the following block. Each character of the string is one em.
Automatic breaks still leave a float's min-content at the whole word. An
unquoted value, an inline declaration, and a vertical or non-ltr box whose
used string is not U+2010 are rejected. ``text-wrap: balance``
and ``text-wrap-style: balance`` keep that first-fit line count and choose the
partition whose leftover inline space has the lower variance. ``wrap`` and
``auto`` stay on the first-fit breaks. A group of more than ten lines stays
on those breaks. A float, a text indent, an inside marker, a mixed font, an
inline-block, a relative inline, a vertical writing mode, and a declaration
on an inline are rejected for that balance. ``text-wrap: pretty`` and
``text-wrap-style: pretty`` keep the first-fit line count and, when the last
line is one word, move the previous wrap opportunity onto it if the enlarged
line still fits. Earlier lines stay on the first-fit breaks. A float, a text
indent, an inside marker, a mixed font, an inline-block, a relative inline, a
vertical writing mode, and a declaration on an inline are rejected for that
pretty wrap. ``line-clamp`` is not
inherited. ``none`` keeps every line. A positive integer keeps that many
lines of a horizontal left-to-right block; when a later line was discarded,
the last kept line ends with U+2026 and drops end characters until that mark
fits the content box. A block that already fits, including a nowrap line
wider than the box, is not ellipsized, and the following block starts under
the clamped lines. Zero, ``inherit``, preserved white space, spacing,
justification, indent, balance, a float beside the text, an inline-block, a
marker, a vertical writing mode, and an inline declaration are rejected. A
block child does not take the clamp. ``hanging-punctuation`` is inherited.
``first`` keeps one opening mark, Unicode Ps or Pi, out of the first line's
measure, so the following word can stay on that line. ``last`` keeps one
closing mark, Pe or Pf, out of the final line's measure. ``force-end`` always
keeps a stop or comma out of the line that ends with it, and ``allow-end``
does that only when the mark would otherwise overflow. The mark stays in the
line text. ``none`` is the initial value. ``force-end`` together with
``allow-end`` is invalid, and a declaration on an inline is rejected. A
vertical writing mode or a non-ltr direction is rejected when the used value
is not ``none``. A block that also
has block children keeps those children and does not build
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
on a later sibling starts that sibling below the float. Mixed-size runs
in that text keep their own advances in the shortened line. A relative
inline in that uniform text paints on the shortened line and does not move
the following block. A relative inline in a mixed-size run, and an atomic
box taller than the strut, stay rejected. A
shaped float uses the chord of each line's used height. An
absolute or fixed box still leaves the loose text out. An inline child may set font-size and line-height. Each run advances
by its own font size, and the line grows to the tallest run without
shrinking the parent's strut. ``white-space: nowrap`` on one of those
inlines removes wrap opportunities inside that inline. A short measure
keeps the span's words together on the next line, and words outside it
still wrap. ``pre``, nowrap inside other white space, a float, an atomic
box, and a mixed run stay rejected. text-align on an inline stays rejected.
A float beside those runs shortens each line to the
float's margin edge, or to the shape-outside chord of that used height,
and keeps each run's own advance. A word that fits the strut chord but
not the taller chord moves to the first later gap that holds it. A
vertical writing mode stays rejected. A non-replaced inline keeps its
horizontal margin, border, and padding on the first and last glyph of that
element. The following word starts after that used chrome, and a space can
break before the inline when the chrome does not fit. A split inline keeps
the start chrome on the first fragment and the end chrome on the last.
``box-decoration-break: clone`` repeats both edges on every fragment, so
``AA BB CC`` with 10px of padding on each side is three 40px lines in a 50px
measure and also three lines in a 65px measure. ``slice`` keeps widths 30, 20,
and 30 in the 50px measure, and keeps ``AA BB`` together at width 60 in the
65px measure. The omitted property is ``slice``. ``inherit`` is rejected.
Vertical padding does not change the strut. A percentage, a negative
margin, an empty inline, a mixed font, and a vertical writing mode stay
rejected. A non-replaced inline's ``vertical-align`` shifts its own glyphs
on that line. A length or a percentage of its line-height raises them, and
a negative length lowers them. ``top`` meets the line top. The line grows
to cover the shifted glyphs, and baseline neighbors stay on the strut.
Nested lengths add. An inline-block on that line keeps its own alignment:
a baseline atomic box stays on the strut while those glyphs move, and
``top`` still meets the grown line. ``super`` raises the baseline by the
nearest pixel of one third of the parent font size, and ``sub`` lowers it
by the nearest pixel of one fifth, so the line grows and the following
block moves. A keyword nested inside a shifted inline, preserved white
space, and a vertical writing mode stay rejected. A ``ruby`` element with omitted ``display`` or
``display: ruby`` is an atomic inline. Its base text stays on the parent
baseline and one ``rt`` annotation is centered above that base. A second
``rt`` is centered under the base. The ruby width is the widest of those
runs, so a wider under annotation can push the ruby onto the next line.
The line grows to cover both annotations, and the following block starts
under that grown line. The base stays on the parent baseline, so the under
annotation hangs below it. A third annotation, a float beside the ruby, a
vertical writing mode, and a specified ruby size are rejected. An
inline-block is an atomic inline: automatic width is the shrink-to-fit of
its text, the words before and after stay on the line, and the atomic box
moves intact to the next line when it does not fit. Its bottom margin edge
rests on the parent baseline when overflow is not visible or it has no line
box; otherwise the baseline is its last line. ``vertical-align`` moves that
margin box: ``top`` and ``bottom`` meet the line edges, ``middle`` centers it
on the baseline, ``text-top`` and ``text-bottom`` meet the parent content
edges, and a length or percentage raises the baseline alignment. ``super``
and ``sub`` use those same parent-font ratios. A block child is laid out in that atomic box:
automatic width shrinks to the block, a specified width wraps it, and the
block's vertical margin stays inside the border. The surrounding words
align to that block's last line. Loose text beside that block becomes an
anonymous block in the same stack: the atomic box shrinks to the wider of
the text and the block, a specified atomic width wraps that text at spaces, and the
surrounding words align to the last line of the stack. A left float inside
that atomic box is contained by it: automatic width fits the float and the
unwrapped words beside it, and a specified width wraps those words beside
the float and then under it. Words that precede the float keep that full
width and the float starts under them; only the words after it shorten
beside the float. The surrounding words align to the last in-flow line.
A nested inline-block is an atomic item of that same line. Automatic width
fits its margin box and the unwrapped words beside it. A specified width
wraps the nested box under those words when it does not fit, and the
surrounding line aligns to the last of those lines. A right float, a mixed
font, and positioned content stay rejected.
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
places that run before a later item. A preserved newline in ``pre``,
``pre-wrap``, ``break-spaces``, or ``pre-line`` is a forced line break on
that anonymous item or on a flex item that sets the same white space. The
max-content width is the longest line, so spaces on a ``pre`` line stay and
a short second line does not widen the item. The automatic cross size is
those line boxes, and the following block starts under the stack. A tab and
a different font on the run stay rejected.
``display: inline-flex`` is that same row as an atomic inline. A definite
width flexes the items inside the line, and the words before and after stay
on that line. An automatic width with ``flex: none`` shrinks to the items'
text. The whole margin box moves to the next line when it does not fit.
A column, wrapping, a growing automatic width, a float, and positioned
content stay rejected.
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
axis. ``justify-content`` and ``align-content`` then pack the tracks in the
definite content box. ``end``, ``flex-end``, and ``center`` shift them, and a
negative leftover still shifts those two. ``space-between``,
``space-around``, and ``space-evenly`` add to every gutter, so a spanned
item's area grows by the extra gutter, and they fall back when the leftover
is negative or the axis has one track. ``normal`` and ``stretch`` keep
growing automatic columns and flexible rows, then leave any remainder at the
start. ``start`` and ``flex-start`` do not grow those columns. A share that
is not an integer pixel is rejected. An automatic block size has no free
block space.
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
``widows`` and ``orphans`` are inherited. On that fixed fill's only text
child they fragment its line boxes: a break leaves at least the orphans
count before it and at least the widows count after it, and a missing
partner defaults to 2. A column that cannot hold a legal break is skipped
until the block has started, then the current column keeps the rest and may
overflow. The child's border box stays with the first fragment and shrinks
to it; later lines keep their column positions. The following block stays
under the specified height. Both values omitted, or ``initial``, ``unset``,
and ``revert``, keep the unbreakable box. Zero, a negative, and any other
token are invalid. A sibling, a spanner, ``column-height``, a balanced fill,
mixed line heights, and padding or border on that child are rejected.
``column-span: all`` inside that fixed fill balances and shortens the line
above the spanner, lays the spanner across the content box, and fills the
leftover block size in source order. The multicol keeps its specified
height. A nested formatting context, a non-zero margin, and a
non-horizontal writing mode stay rejected. An omitted ``column-gap`` is
``1em``. ``column-height`` fixes the block size of every column in a row.
A partly filled row keeps that size, so the multicol is taller than its
content and the following block starts under the row. ``column-wrap: auto``
and ``wrap`` put a box that does not fit into the next column, and a full
row starts another row. ``row-gap: normal`` is 1em between those rows.
A box taller than the column stays in the column where it started and
overflows the row; the next row still starts after the fixed height and
the gap. ``column-span: all`` ends a row that already holds a box, then
occupies the next row across the whole content box. That row keeps the
column height, so a later box starts after the height and the row gap,
and a spanner taller than the column overflows across the gap without
pushing the later box or growing the multicol. A spanner in an empty row
stays in that row. ``column-wrap: nowrap``, a specified height, and a
forced column break are rejected when a column height is set. ``wrap``
without a column height keeps the balanced single row. A column height
without a column count or column width is rejected.
``column-rule`` paints one stroke in the middle of each gap whose two
neighboring columns both hold a box. The stroke is as tall as that column
box, so a fixed ``column-height`` row includes the unused block and a
``column-fill: auto`` row uses the leftover block size. A
``column-span: all`` row and a trailing empty column have no stroke.
``none``, ``hidden``, and a zero width paint nothing. The omitted style is
``none`` and the omitted width is ``medium`` (3px). The omitted color is
the used ``color``. A rule wider than the gap stays centered and overflows;
an odd leftover pixel stays on the inline end. The stroke does not move
the column boxes or the following block. A negative width is invalid, and
``inherit`` is rejected.
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
automatic axis keeps the intrinsic ratio. A CSS ``aspect-ratio`` on an in-flow
replaced box is that preferred ratio. A plain ratio replaces the intrinsic
one, so a 400 by 200 image with width 100px and ``1 / 1`` paints 100 by 100
and the following block starts under that square. ``auto`` with a ratio keeps
the intrinsic ratio when both attributes exist, and otherwise uses the
specified ratio, so that image stays 100 by 50 and an image with no attributes
and width 80px paints 80 by 80. Both automatic axes still use both intrinsic
dimensions. A specified height stays specified. A maximum on the automatic
axis clamps that axis and leaves the definite axis alone. The block
transferred-height floor does not also apply. An absolute or fixed image
uses that same preferred ratio, so a 400 by 200 image with width 100px and
``1 / 1`` paints 100 by 100 while the following block stays at its static
position. A block's automatic horizontal
margins then center that used width. An inline replaced element is an atomic
line item whose bottom margin edge rests on the strut baseline. ``object-fit``
places the concrete object inside the content box. An absolute or fixed image
uses that intrinsic or preferred-ratio size and then the absolute inset
equation, so definite insets do not stretch it. Automatic insets use its static position, including
the line slot of an inline image. A maximum width shrinks that size and keeps
the ratio. ``box-sizing: border-box`` reads a specified width, height,
minimum, or maximum as the border box. Padding and border shrink the content
box and do not let it go below zero, so chrome larger than the specified
size grows the used border box to that chrome. A plain ``aspect-ratio`` maps
the border box. ``auto`` with a ratio, and the intrinsic ratio, map the
content box. An inline relative or sticky image, a vertical writing mode,
and a child stay rejected.
An ``li`` and any other ``display: list-item`` principal box lays out as a
block and paints a marker from the ``list-item`` counter. ``ol`` and ``ul``
reset that counter. The initial marker is a disc; an ``ol`` uses decimal
unless the author sets another type. ``list-style-position: outside`` ends
the marker on the content start and does not move the principal line.
``inside`` places the marker on the first line and wraps the remaining text
at the full content width. ``none`` paints nothing. A float, a non-horizontal
writing mode, and an inside marker beside a block child stay rejected.
``text-combine-upright`` is not inherited. On an inline with no element
children and no generated text, ``all`` compresses that text into one em and
``digits`` compresses each ASCII run, two digits unless a count from 2 to 4
is set, into one em. ``vertical-rl`` and ``vertical-lr`` then scale the run
into that em and center it on the column, so two 10px digits paint 5 by 5,
side by side, two pixels below the em. The column's inline size loses the
saved ems and the next block starts under that shorter column. A horizontal
box keeps the property and does not change advances. A count outside 2 to 4,
a scale that is not an integer pixel, white space, a nested element, a
sideways mode, and a line that would split the run are rejected.
Writing mode, direction and text orientation inherit. Other CSS-wide keywords
on box properties use their initial values.
A text-only orthogonal block wraps down its used content height and stacks
its lines from block-start. Once the columns determine its width, the
horizontal parent resolves auto margins and stacks the physical border box.
Widths and heights in line records are physical. Text uses the engine's
uniform glyph advances. Static block children in that same writing mode and
direction stack on the block axis, from the right for ``vertical-rl`` and
from the left for ``vertical-lr``. Each child lays out its own text. A
definite parent height stretches an automatic child to that content box and
wraps the child inside it. An automatic parent is as wide as the children
and as tall as the tallest one. A child margin, a percentage size, a float,
and loose text beside those children stay rejected. A horizontal-tb child
with direction ltr and text-orientation mixed keeps horizontal lines: an
automatic parent block size uses that child's max-content width. A definite
parent block size shrinks the child to fit that width, so a longer line wraps
and a shorter child keeps its max-content width. Each such child stacks from
the block-start edge, including beside a vertical sibling, and a later child
crosses the block-end edge when the sum exceeds that width. A definite parent
inline size does not stretch the child. A length width is that child's
content width: a short word does not shrink the border box, a breakable line
wraps inside the length, and an unbreakable word overflows it. A length
height is the content height, so the border box and the parent's automatic
height keep that length when it differs from the line boxes. A percentage, a
minimum or maximum size, border-box, an aspect ratio, a margin, a float, and
a nested child stay rejected. A horizontal child may mix font sizes. Each
run keeps its own advance, a larger letter grows that line, and a word that
no longer fits wraps, so the vertical parent's border box follows that used
size. Justification of a mixed-font orthogonal line stays rejected.
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
``attr()`` copies that element's attribute into the same text. A missing
attribute is empty, so it adds no glyphs, and a parent's attribute is not
read. A fallback, a type, or any other function stays rejected.
``open-quote`` and ``close-quote`` insert one pair from the element's
``quotes`` value. The initial value is the English pairs U+201C U+201D and
U+2018 U+2019; ``auto`` is that same value, and ``none`` inserts nothing.
Depth is the number of earlier open quotes minus the number of earlier close
quotes, with ``::before`` before the element's children and ``::after`` after
them. An open quote uses the pair at that depth and then increments it. A
close quote decrements first and then uses the pair at the new depth; the
last pair repeats when the depth runs past the list. A close at depth zero
is ignored and inserts nothing. ``no-open-quote`` and ``no-close-quote``
change the depth without a glyph. ``quotes: none`` still changes the depth,
so a child with its own pairs can use a later pair. ``display: none`` does
not. Each quote character is one em, so the glyphs wrap with the line and
can move the following block. An odd string list is invalid. A vertical
writing mode or a non-ltr direction is rejected when a quote keyword is used.
``font-size`` and ``line-height`` on ``::before`` and ``::after`` size only those glyphs.
The element's own text keeps its metrics, and the line grows to the taller
run without shrinking the strut. A percentage font-size is invalid. A flex,
grid, or table box, and an absolute box that paints its own text, stay
rejected when the pseudo carries those properties. Any other property on a
pseudo that generates a box stays rejected. A flex, grid, or table box and
a flex or grid item stay rejected when the content still has a counter.
``::first-letter`` with ``initial-letter`` set to one integer of 2 or more
drops that many line boxes. The first ASCII letter leaves the line and
becomes a square whose side is that count times the strut, at the content
origin. The next lines of the remaining text start after the square, and
the first line past the drop returns to the content start. A shorter
remainder still grows the block to the square. A second integer is the
sink: the square's side stays the size, and the first line moves down by
each size line the sink does not cover. ``raise`` sinks one line and
``drop`` repeats the size. Either keyword may precede or follow the
integer. A size below 2, a sink below 1 or larger than the size, a
non-integer, a non-letter, an inline, a float, a list item, a vertical
writing mode, a word wider than the gap beside the square, and any other
property on that pseudo stay rejected.
``font-family`` names faces collected from ``@font-face``. Each finished
line records the face that covers its characters. A later family is used
when an earlier unicode-range misses, ``font-weight`` and ``font-style``
choose among the faces of the inherited family, and a character no face
covers stays in the line with no face. A stylesheet with no ``@font-face``
does not add those face runs.
``text-decoration`` and ``text-decoration-line`` are not inherited.
``underline``, ``overline``, and ``line-through`` paint across that
element's inline text and the inline text of its descendants. A descendant
``none`` does not remove an ancestor line. An inline-block is a gap in the
ancestor line. The line position uses the decorating element's font size
and that line's baseline: underline is one tenth of an em below it,
line-through one third of an em above it, and overline at the top of the
em. The line box does not grow to cover the ink. A vertical writing mode,
a non-ltr direction, a float, justification, spacing, a list marker, and a
shifted vertical-align stay rejected.
``text-emphasis`` is inherited. On a horizontal left-to-right block whose own
content is normal text, each non-space character with a positive advance gets
one mark. ``filled`` and ``open`` select the dot when the shape is omitted, a
named shape defaults to filled, and a one-character string is that mark.
``none`` paints nothing. The mark band is half an em, at least one pixel,
centered in the character advance with a leftover pixel on the inline end.
``over`` sits above the em and moves the baseline down by that band; ``under``
keeps the baseline and sits below the em. The line box grows by the band, so
the following block starts lower. ``left`` and ``right`` may accompany the
block side and do not move that horizontal mark. A bare side is invalid. An
empty string, a string of any other length, and both the shorthand and
``text-emphasis-style`` together are invalid. The mark uses the used
``color``. An inline declaration, a vertical or non-ltr box, a float, a list
item, spacing, indentation, justification, a clamp, and a block child beside
the text stay rejected.
``scrollbar-gutter`` is not inherited. A horizontal left-to-right scroll
container reserves this engine's 15px classic scrollbar on the inline-end
edge, between the border and the padding. The border box keeps its allotted
size and the content box narrows, so a percentage child and the line measure
use the remainder. ``stable`` reserves that gutter for ``hidden``, ``scroll``,
and ``auto`` even when the content fits. ``stable both-edges`` also reserves
the inline-start edge and shifts the content by 15px. ``auto`` reserves it
for ``scroll``, and for ``auto`` only after the first layout shows block
overflow. Overlay scrollbars reserve nothing. ``visible`` and ``clip`` reserve
nothing. A vertical writing mode or a non-ltr direction keeps the full content
box. A gutter wider than the content box is rejected. ``both-edges`` without
``stable`` is invalid.
``align-content`` on a horizontal left-to-right ``block`` or ``flow-root``
packs that box's in-flow content as one unit inside the content box.
``end`` and ``flex-end`` place the unit on the block end, ``center`` splits
the free space in half toward the start, and ``start`` and ``flex-start``
keep the unit on the block start. ``space-between`` and ``stretch`` use the
start fallback, and ``space-around`` and ``space-evenly`` use the center
fallback, because the contents are a single alignment subject. Every value
other than ``normal`` also makes the box a block formatting context, so a
child margin stays inside it. The default overflow position is safe: a unit
taller than the content box stays at the start, while ``unsafe`` honors a
negative shift. The following sibling stays at the container's border edge.
A vertical writing mode, a non-ltr direction, a float, a sticky or
out-of-flow box, a non-visible overflow, a list item, a line box beside a
block child, and ``baseline`` stay rejected.
``offset-path`` then slides that box so the anchor point meets the path
point inside the containing block's border box. ``path()`` and a basic
shape are measured in that border box, not from the element's static
corner, so a path point above the static position moves the box upward.
``offset-anchor: auto`` is the center of the element's own border box, and
two lengths select another point. ``offset-rotate`` is recorded on the box
and does not rotate the border rectangle. Descendants move with the box.
The following sibling stays at the static flow position. A float, an
absolute or fixed box, a sticky box, a vertical or non-ltr box, the
``offset`` shorthand, and a path the motion reader cannot parse are rejected.
``animation-timeline: scroll()`` then samples that same box's opacity from
the viewport scroll. Progress is ``scroll_y`` divided by the root border
box's bottom edge minus the viewport height. A root that does not overflow
keeps the declared opacity, and neither value moves the box or the following
block. The effect needs one ``@keyframes`` opacity rule plus
``animation-name``, ``animation-duration``, and the underlying opacity on a
horizontal block. A broken keyframe block, the ``animation`` shorthand, a
float, an absolute or sticky box, and a vertical or non-ltr box are rejected.
``transition-property: height`` then replaces that block's specified height
with the used length of one CSS transition at ``transition_sample_ms``.
``transition_changes`` maps an id to the specified heights that retarget it.
Reversing toward the length that started the running transition shortens
the return, and the next sibling's top edge tracks the used border height.
A float, an absolute or sticky box, a vertical or non-ltr box, the
``transition`` shorthand, and an unparsable duration are rejected.
``element_from_document`` then clips each descendant to the padding edge of
an ancestor whose overflow is ``hidden``, ``clip``, ``scroll``, or ``auto``.
The rectangle is that ancestor's border box inset by its used border. A
point on the border, outside the padding edge, hits the ancestor even when
a descendant's border box covers it. A point past that border box does not
hit the descendant. ``visible`` does not clip, so those same points hit the
descendant. The scrollport's border box and the following block stay put.
``transform`` other than ``none`` then moves only the hit. The recorded border
box stays where flow put it, and the following block stays there too. A
clockwise ``rotate(90deg)`` around the top-left corner selects a point in the
negative x half and misses the old rectangle. ``transform-origin`` defaults to
``50% 50%``. An unparsable transform or origin is invalid.
``outline`` paints outside the border edge and does not change that border
box, the following block, or the page height. The recorded rectangle is the
outer edge of the stroke: ``outline-offset`` plus the used thickness. The
omitted color is the used ``color``, including a color inherited from an
ancestor. ``none`` and a zero thickness record nothing. A non-replaced inline
with a visible outline is rejected. An unparsable outline is invalid.
``box-shadow`` is not inherited and does not move the border box or the
following block. Each comma-separated shadow records a physical offset, a
non-negative blur, a spread, a color, and whether it is inset. Blur does
not enlarge the recorded rectangle. An outset rectangle is the border-box
shadow shape: expanded by the spread, then shifted by the offsets. An
inset rectangle is the unshadowed hole inside the padding edge: that
padding box contracted by the spread and shifted by the offsets, with the
padding edge recorded as the clip. ``none`` records nothing. A negative
blur, a percentage, and a non-replaced inline are rejected.
``scroll-snap-type`` other than ``none`` rests a horizontal scrollport on
the alignment of its descendant snap areas. The recorded ``snap`` is that
resting offset. ``y mandatory`` chooses the nearest start and breaks a tie
toward the end. ``proximity`` keeps an intended offset farther than the
snapport. ``scroll-padding`` insets the snapport and ``scroll-margin``
outsets an area. The areas and the following block stay where flow put
them. An unparsable snap is invalid. A vertical writing mode or a visible
overflow port is rejected.
``margin-trim`` on a horizontal block container discards descendant margins
that adjoin the named block edges, including a grandchild margin collapsed
through the first child. ``block`` trims both edges. The container's own
margin and a sibling margin that does not adjoin the trimmed edge stay, so
the following block moves up when an escaped or interior edge margin
disappears. ``inline`` is invalid. A vertical writing mode or columns with
a trim are rejected.
``text-box-trim`` is not inherited. On a horizontal left-to-right block
whose own content is normal text, ``trim-start`` removes the half-leading
above the first line's em box, ``trim-end`` removes the half-leading below
the last line's em box, and ``trim-both`` removes both. The em box is this
engine's font size above the baseline and nothing below it, so a 10px font
on a 20px line loses 5px at each trimmed edge. Later lines move up with the
start trim, and the following block starts at the new content edge.
``text-box`` is that shorthand and resets an omitted edge to ``auto``.
``text-box-edge`` names the metric that trim meets. ``auto`` and ``text``
stay on the em box. This engine has no font file, so the Latin cap-height
is seven tenths of the em and the x-height is half an em, the length CSS
uses for ``ex`` when the font cannot be measured. ``cap`` and ``ex`` are
over edges only, so ``cap alphabetic`` and ``ex alphabetic`` cut the first
line down from the em top by the remainder of the em. The alphabetic
baseline is the em bottom because the strut descent is zero, and a lone
``cap`` or ``ex`` is invalid. ``ideographic`` and ``ideographic-ink`` stay
unsupported. A specified height, a vertical or non-ltr box, a float, a
replaced box, columns, flex, grid, table, and a block child are rejected.
``content-visibility: hidden`` skips that element's contents. The used
block size is the size the box would have with no content: an automatic
height becomes zero, ``contain-intrinsic-block-size`` supplies that empty
content height, and a specified height stays. Padding and border stay.
The following block starts at the collapsed border edge. Descendant boxes
are not hit targets, and the skipped text leaves no line. ``visible``,
``auto``, and an omitted property keep the content height.
``contain-intrinsic-block-size`` does nothing without ``hidden``.
A vertical or non-ltr box, an inline, a float, an absolute or sticky box,
a list item, a replaced box, columns, and an aspect ratio are rejected.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from xml.etree.ElementTree import Element

from blackhole_agent.css_absolute import place_absolute
from blackhole_agent.css_animation import _Invalid as _AnimInvalid
from blackhole_agent.css_animation import _extract_keyframes, _strip_comments as _strip_animation_comments
from blackhole_agent.css_scroll_snap import resolve_scroll_snap
from blackhole_agent.css_scroll_timeline import sample_scroll_driven_animation, scroll_timeline_progress
from blackhole_agent.css_anchor_query import parse_anchor_size_call, resolve_anchor_size
from blackhole_agent.css_anchor_position import parse_anchor_call, place_anchored, used_anchor_inset
from blackhole_agent.css_aspect_ratio import block_ratio_limits, parse_aspect_ratio
from blackhole_agent.css_container_query import match_container_query
from blackhole_agent.css_counters import format_counter, format_counters, resolve_counters
from blackhole_agent.css_bidi import bidi_line_order
from blackhole_agent.css_border_radius import used_border_radii
from blackhole_agent.css_color_mix import _Invalid as _ColorInvalid
from blackhole_agent.css_color_mix import _convert as _convert_color
from blackhole_agent.css_color_mix import _parse_color
from blackhole_agent.css_auto_table import layout_auto_columns
from blackhole_agent.css_collapsed_border import resolve_collapsed_grid
from blackhole_agent.css_fixed_table import layout_fixed_columns
from blackhole_agent.css_font_match import _Invalid as _FontInvalid
from blackhole_agent.css_font_match import _requested_style, _requested_weight, select_font_face
from blackhole_agent.css_flex_align import flex_line_cross_size, place_flex_alignment
from blackhole_agent.css_flex_base import resolve_flex_base
from blackhole_agent.css_flex_line import resolve_flex_line
from blackhole_agent.css_flex_wrap import wrap_flex_lines
from blackhole_agent.css_float_lines import seek_shaped_gap, shaped_gap_at
from blackhole_agent.css_float_placement import place_floats
from blackhole_agent.css_scrollbar_gutter import (
    ScrollbarGutterError,
    parse_scrollbar_gutter,
    reserve_scrollbar_gutter,
)
from blackhole_agent.css_shape_outside import ShapeError, prepare_shape
from blackhole_agent.css_sticky import sticky_offset
from blackhole_agent.css_subgrid import place_subgrid_items
from blackhole_agent.css_grid_align import align_grid_item
from blackhole_agent.css_grid_areas import place_named_grid
from blackhole_agent.css_grid_content import size_content_grid_tracks
from blackhole_agent.css_grid_pack import grid_content_stretches, pack_grid_content
from blackhole_agent.css_grid_placement import place_grid_items
from blackhole_agent.css_grid_tracks import size_grid_tracks
from blackhole_agent.css_hit_test import element_from_point
from blackhole_agent.css_object_fit import fit_object
from blackhole_agent.css_offset_path import travel_offset_path
from blackhole_agent.css_replaced import used_replaced_size
from blackhole_agent.css_inline_line import layout_inline_line
from blackhole_agent.css_length_math import is_length_math
from blackhole_agent.css_line_break import _default_advance, balance_lines, pretty_lines, wrap_lines
from blackhole_agent.css_relative import place_relative
from blackhole_agent.css_table_rows import layout_table_rows
from blackhole_agent.css_text_align import align_inline_line
from blackhole_agent.css_text_caret import element_text_offset, uniform_caret_edge
from blackhole_agent.css_transform import map_transformed_point
from blackhole_agent.css_transition import interrupt_css_transition
from blackhole_agent.css_text_decoration import (
    DecorationError,
    paint_decoration_events,
    parse_text_decoration,
)
from blackhole_agent.css_text_emphasis import (
    EmphasisError,
    emphasis_band,
    resolve_emphasis_position,
    resolve_emphasis_style,
)
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
from blackhole_agent.css_multicol import layout_column_rows, layout_multicol
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
    resolve_initial_letter,
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
        "inline-flex",
        "grid",
        "table",
        "table-row",
        "table-cell",
        "table-caption",
        "none",
        "contents",
        "flow-root",
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
    "letter-spacing": "0px",
    "word-spacing": "0px",
    "text-autospace": "no-autospace",
    "text-transform": "none",
    "tab-size": "8",
    "white-space": "normal",
    "overflow-wrap": "normal",
    "word-break": "normal",
    "hyphens": "manual",
    "hyphenate-character": "\u2010",
    "lang": "",
    "hanging-punctuation": "none",
    "widows": "",
    "orphans": "",
    "text-wrap-style": "auto",
    "list-style-type": "disc",
    "list-style-position": "outside",
    "font-family": "",
    "font-weight": "400",
    "font-style": "normal",
    "color": "#000000",
    "text-emphasis-mark": "",
    "text-emphasis-position": "over",
}
# CSS 2.1 leaves the initial quotes value to the user agent. This engine uses
# the English double then single pairs from that specification's table.
_AUTO_QUOTES = (("\u201c", "\u201d"), ("\u2018", "\u2019"))
_QUOTE_PARTS = frozenset({"open-quote", "close-quote", "no-open-quote", "no-close-quote"})
_ALIGNS = frozenset(
    {"start", "end", "left", "right", "center", "justify", "justify-all", "match-parent"}
)
_LAST_ALIGNS = frozenset({"auto", "start", "end", "left", "right", "center", "justify"})
_JUSTIFY_MODES = frozenset({"auto", "none", "inter-word", "inter-character"})
_WHITES = frozenset({"normal", "nowrap", "pre", "pre-wrap", "break-spaces", "pre-line"})
_OVERFLOW_WRAPS = frozenset({"normal", "break-word", "anywhere"})
_WORD_BREAKS = frozenset({"normal", "keep-all", "break-all", "break-word"})
_HYPHENS = frozenset({"none", "manual", "auto"})
_TRANSFORMS = frozenset({"none", "uppercase", "lowercase", "capitalize"})
_TRANSFORM_REJECTED_DISPLAYS = frozenset(
    {"flex", "inline-flex", "grid", "table", "table-row", "table-cell", "table-caption"}
)
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
_FORCED_SEGMENT_WHITE = frozenset({"pre", "pre-wrap", "break-spaces", "pre-line"})
_INLINE_REJECTED = (
    "text-align",
    "white-space",
    "letter-spacing",
    "word-spacing",
    "text-autospace",
    "tab-size",
    "overflow-wrap",
    "word-wrap",
    "word-break",
    "hyphens",
    "hyphenate-character",
    "hanging-punctuation",
    "text-wrap",
    "text-wrap-style",
    "line-clamp",
    "text-transform",
    "text-box",
    "text-box-trim",
    "text-box-edge",
)


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
    extra: list[int] = field(default_factory=list)
    vertical_align: str | int = "baseline"
    nowrap: bool = False
    origin: tuple[Element, bool] | None = None  # element.text or child.tail
    marks: tuple[tuple[str, int, str], ...] = ()
    combine: tuple[tuple[int, int], ...] = ()
    clone_ranges: tuple[tuple[int, int, int, int], ...] = ()


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
    truncated: bool = False
    decorations: list[dict[str, object]] = field(default_factory=list)
    combines: list[dict[str, object]] = field(default_factory=list)
    emphasis: list[dict[str, object]] = field(default_factory=list)


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
    scroll_port_x: int = 0
    scroll_port_y: int = 0
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
    letter_spacing: int = 0
    word_spacing: int = 0
    text_transform: str = "none"
    tab_size: str = "8"
    containing_inline: int | None = None
    white_space: str = "normal"
    overflow_wrap: str = "normal"
    word_break: str = "normal"
    hyphens: str = "manual"
    hyphenate_character: str = "\u2010"
    lang: str = ""
    hanging_punctuation: str = "none"
    text_wrap_style: str = "auto"
    font_family: str = ""
    font_weight: str = "400"
    font_style: str = "normal"
    line_clamp: int | None = None
    initial_letter: int = 0
    initial_sink: int = 0
    drop_cap: dict[str, object] | None = None
    parent_direction: str | None = None
    inline_text: str | None = None
    static_index: int = 0
    line_static: tuple[str, tuple[int, ...]] | None = None
    flow_y: int = 0
    lines: list[_Line] = field(default_factory=list)
    atoms: list[_Box] = field(default_factory=list)
    pieces: list[_Piece] = field(default_factory=list)
    nowrap_ranges: tuple[tuple[int, int], ...] = ()
    clone_ranges: tuple[tuple[int, int, int, int], ...] = ()
    relative_layers: dict[int, _Shift] = field(default_factory=dict)
    local_x: int = 0
    flex: dict[str, object] | None = None
    grid: dict[str, object] | None = None
    table: dict[str, object] | None = None
    multicol: dict[str, object] | None = None
    column_span: str = "none"
    break_before: str = "auto"
    break_after: str = "auto"
    widows: int | None = None
    orphans: int | None = None
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
    ruby: bool = False
    ruby_pair: dict[str, object] | None = None
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
    intrinsic_block: int | None = None
    transform_origin: str = "50% 50%"
    scrollbar_gutter: str = "auto"
    scrollbars: str = "classic"
    gutter_start: int = 0
    gutter_end: int = 0
    gutter_pending: bool = False
    allotted_content_width: int | None = None
    align_mode: str = "normal"
    align_safe: bool = True
    margin_trim: str = "none"
    text_box_trim: str = "none"
    text_box_edge: tuple[str, str] = ("text", "text")
    offset_path: str = ""
    offset_distance: str = "0px"
    offset_rotate: str = "auto"
    offset_anchor: str = "auto"
    offset_angle: int | float | None = None
    scroll_rule: str = ""
    scroll_opacity: int | float | None = None
    border_radius: str = ""
    border_curve: tuple[float, float, float, float, float, float, float, float] | None = None
    color: str = "#000000"
    color_valid: bool = True
    emphasis_mark: str = ""
    emphasis_position: str = "over"
    outline: tuple[str, int, str, int] | None = None
    shadows: tuple[tuple[bool, int, int, int, int, str], ...] = ()
    column_rule: tuple[str, int, str] | None = None
    column_rules: tuple[tuple[int, int, int, int, str, str], ...] = ()
    snap_type: str = ""
    snap_align: tuple[str, str] = ("none", "none")
    scroll_padding: tuple[int, int, int, int] = (0, 0, 0, 0)
    scroll_margin: tuple[int, int, int, int] = (0, 0, 0, 0)
    snap: dict[str, object] | None = None
    height_transition: tuple[str, str, str] | None = None
    text_autospace: str = "no-autospace"


def layout_normal_flow(
    markup: str,
    stylesheet: str,
    *,
    viewport_width: int,
    viewport_height: int | None = None,
    scroll_x: int = 0,
    scroll_y: int = 0,
    port_scroll: dict[str, tuple[int, int]] | None = None,
    scrollbars: str = "classic",
    transition_sample_ms: int | None = None,
    transition_changes: dict[str, list[dict[str, object]]] | None = None,
) -> dict[str, object]:
    """Return viewport border boxes for the document's normal-flow blocks.

    ``viewport_width`` is the initial containing block's width in CSS pixels.
    ``viewport_height`` is that block's height, or indefinite when omitted.
    ``scroll_x`` and ``scroll_y`` are that viewport's scroll offsets. They
    move a sticky box whose scrollport is the viewport and sample
    ``animation-timeline: scroll()`` opacity. Every other box stays at its
    static position. ``port_scroll`` maps a scrollport id to
    ``(x, y)`` offsets. A horizontal left-to-right ``hidden``, ``auto``, or
    ``scroll`` port then shifts only the sticky boxes it contains; in-flow
    siblings stay at their static positions. Omitted ports stay at scroll
    zero. ``scrollbars`` is ``classic`` or ``overlay``. Classic scrollbars
    reserve a 15px gutter under ``scrollbar-gutter``; overlay scrollbars do
    not.     ``x`` and ``y`` are the border edges measured
    from the unscrolled viewport origin, before ``transform``. A transform
    moves hits and leaves these edges in place. Lengths are ``px`` or percentages. A
    unitless zero is rejected. ``sibling-index()`` and ``sibling-count()``
    inside a box length use the element's DOM siblings before that length is
    solved. Rules come from the stylesheet; a style
    attribute is not read. Relative offsets are applied after the static
    positions, then sticky offsets. Absolute and fixed boxes are included
    in the returned boxes. ``align-content`` then packs a horizontal block's
    in-flow content inside its content box, before relative and sticky offsets.
    ``offset-path`` then translates the box so its anchor meets the path point
    in the containing block border box. Following siblings stay put.
    ``border-radius`` does not move those rectangles. An unparsable radius
    rejects the document. ``outline`` records the outer edge of a stroke
    around that same border box. The stroke does not move the box.
    ``box-shadow`` records each shadow's shape or inset hole in that same
    space. The rectangles do not move the box.
    ``text-emphasis`` records one mark on each non-space character and grows
    that line by half an em. ``over`` moves the baseline down with the em.
    The following block starts under the enlarged line.
    ``open-quote`` and ``close-quote`` insert the ``quotes`` pair for the
    current quotation depth. Those glyphs use the same em advance as other
    text, so a wrap moves the following block.
    ``column-rule`` records one centered stroke in each gap between two
    occupied columns. Those rectangles do not move the column boxes.
    ``widows`` and ``orphans`` split that multicol's only text child across
    a fixed ``column-fill: auto`` height. Later lines stay in their columns,
    and the following block stays under the specified height.
    ``scroll-snap-type`` records the resting scroll of a horizontal
    scrollport. The snap areas stay at their flow positions.
    ``transition_sample_ms`` samples a ``transition-property: height``
    transition. ``transition_changes`` maps an element id to retargets
    whose ``time_ms`` and ``value`` are the new specified height. The
    used height replaces the specified height before flow is solved, so
    the next sibling moves with it.
    """

    try:
        root = _placed_root(
            markup,
            stylesheet,
            viewport_width=viewport_width,
            viewport_height=viewport_height,
            scroll_x=scroll_x,
            scroll_y=scroll_y,
            port_scroll=port_scroll,
            scrollbars=scrollbars,
            transition_sample_ms=transition_sample_ms,
            transition_changes=transition_changes,
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
    port_scroll: dict[str, tuple[int, int]] | None = None,
    scrollbars: str = "classic",
) -> dict[str, object]:
    """Return the frontmost element whose border box contains ``(x, y)``.

    The document is laid out by ``layout_normal_flow``. Paint order is CSS 2.2
    Appendix E, so a float is in front of an overlapping in-flow block, a
    positive z-index is in front of a later auto-positioned sibling, and a
    negative z-index that escapes its parent is behind that parent.
    ``pointer-events: none`` and ``visibility: hidden`` are not targets.
    ``content-visibility: hidden`` sizes the box as if it had no content,
    and its descendants are not targets.
    A flex, inline-flex, grid, table, table-row, or table-cell box is a
    target. A point in a flex container's unoccupied gap hits that container,
    and a positive z-index still paints above the flex item it covers.
    A hit inside uniform horizontal text also has a ``caret``. Its ``line`` is
    zero-based and its ``offset`` counts UTF-16 code units in the element's
    original text, before wrapping and whitespace collapse. A hyphen mark
    painted by a taken automatic or soft break is not in that text. A pointer
    on the mark, and on either fragment, still reports the caret. An automatic
    break maps each mark glyph to the source boundary where the break was
    taken. A source soft hyphen keeps that character's caret span. A box hit in
    empty space or on text without a source mapping has no caret field.
    ``overflow: hidden``, ``clip``, ``scroll``, and ``auto`` clip descendants
    to the padding edge. The element's own border box stays a target, and
    ``visible`` does not clip.     ``transform`` other than ``none`` moves the
    hit through the inverse matrix of that element and its ancestors. Layout
    coordinates stay untransformed. The initial ``transform-origin`` is
    ``50% 50%``. An unparsable transform or origin rejects the document.
    ``border-radius`` drops a point outside the used outer curve from that
    element's own target. A descendant in the corner remains a target, and
    the border boxes stay where flow put them. An unparsable radius rejects
    the document.
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
            port_scroll=port_scroll,
            scrollbars=scrollbars,
        )
        tree, boxes = _document_hit_tree(root)
    except (CssSelectorError, _Invalid) as exc:
        return {"outcome": "invalid", "id": None, "reason": str(exc)}
    found = element_from_point(tree, x, y)
    found.setdefault("reason", None)
    if found["outcome"] == "hit":
        box = next(box for box in boxes if box.id == found["id"])
        if not _chain_has_transform(box):
            caret = _hit_text(box, x, y)
            if caret is not None:
                found["caret"] = caret
    return found


def _hit_text(box: _Box, x: float, y: float) -> dict[str, int] | None:
    source = box.inline_text
    if (
        not source or box.element is None or box.writing_mode != "horizontal-tb"
        or box.letter_spacing or box.word_spacing or box.atoms or box.drop_cap
        or box.hanging_punctuation != "none" or box.text_transform != "none"
    ):
        return None
    for index, line in enumerate(box.lines):
        if not (line.y <= y < line.y + line.height and line.x <= x < line.x + line.content_width):
            continue
        if line.runs or line.truncated:
            return None
        edge = uniform_caret_edge(
            source, [row.text for row in box.lines[:index + 1]], box.white_space,
            box.direction, box.font_size, line.content_width, x - line.x,
            hyphen_mark=box.hyphenate_character,
        )
        if edge is not None:
            offset = _source_offset(box, *edge)
            if offset is not None:
                return {"line": index, "offset": offset}
    return None


def _source_offset(box: _Box, character: int, after: bool) -> int | None:
    for piece in box.pieces:
        if character < len(piece.text):
            if piece.origin is None:
                return None
            return element_text_offset(box.element, piece.origin, character + int(after))
        character -= len(piece.text)
    # Some formatting contexts lay out a leaf directly, without inline pieces.
    if not box.pieces and box.inline_text == box.element.text:
        return element_text_offset(box.element, (box.element, False), character + int(after))
    return None


def _placed_root(
    markup: str,
    stylesheet: str,
    *,
    viewport_width: int,
    viewport_height: int | None,
    scroll_x: int,
    scroll_y: int,
    port_scroll: object = None,
    scrollbars: str = "classic",
    transition_sample_ms: int | None = None,
    transition_changes: dict[str, list[dict[str, object]]] | None = None,
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
    if scrollbars not in {"classic", "overlay"}:
        raise _Invalid("scrollbar style is invalid")
    tree.scrollbars = scrollbars
    if not order:
        raise _Invalid("document is empty")
    layout_stylesheet, scroll_source = _split_scroll_keyframes(stylesheet)
    container_rules: list[tuple[str, object]] = []
    font_faces: list[dict[str, object]] = []
    declarations, registrations = _stylesheet(
        layout_stylesheet, container_rules=container_rules, font_faces=font_faces
    )
    if font_faces:
        checked = select_font_face(str(font_faces[0].get("family") or "x"), font_faces, " ")
        if checked.get("outcome") == "invalid":
            raise _Invalid(str(checked.get("reason") or "font face is invalid"))
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
    generated_fonts: dict[int, tuple[dict, dict]] = {}
    raw_plans: dict[int, tuple[list, list]] = {}
    for element in order:
        try:
            before, after, before_font, after_font = resolve_generated_plans(
                tree, element, declarations, styles[element][0]
            )
        except CssSelectorError as exc:
            raise _Invalid(str(exc)) from exc
        raw_plans[id(element)] = (before, after)
        if before_font or after_font:
            generated_fonts[id(element)] = (before_font, after_font)
    raw_plans = _resolve_quote_plans(tree, order, styles, declarations, raw_plans)
    for element in order:
        before, after = raw_plans[id(element)]
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
    tree.generated_fonts = generated_fonts
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
    _apply_height_transitions(root, transition_sample_ms, transition_changes)
    _solve(root, viewport_width, viewport_height, viewport_height, 0)
    _seal_skipped_contents(root)
    placed = place_collapsed_margins(_collapse_spec(root))
    if placed.get("outcome") != "placed" or not isinstance(placed.get("boxes"), list):
        raise _Invalid(str(placed.get("reason") or "margin collapse failed"))
    by_id = {str(item["id"]): item for item in placed["boxes"] if isinstance(item, dict)}
    margin_top = _px(root.solved.get("margin_top"), "margin-top")
    _assign_y(root, by_id, margin_top)
    _pack_block_align(root)
    _shift_relatives(root, viewport_width, viewport_height)
    _apply_port_scroll(root, port_scroll)
    _shift_stickies(root, viewport_width, viewport_height, scroll_x, scroll_y)
    _place_positioned(root, _Edge(0, 0, viewport_width, viewport_height))
    _shift_offsets(root, viewport_width, viewport_height)
    _apply_scroll_opacities(root, scroll_source, viewport_height, scroll_y)
    _stamp_font_faces(root, tuple(font_faces))
    _bind_border_curves(root)
    _apply_scroll_snap(root)
    return root


def _invalid(reason: str) -> dict[str, object]:
    return {"outcome": "invalid", "reason": reason, "boxes": None}


_HIT_DISPLAYS = frozenset(
    {
        "block",
        "flow-root",
        "inline",
        "inline-block",
        "inline-flex",
        "flex",
        "grid",
        "table",
        "table-row",
        "table-cell",
    }
)


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


def _document_hit_tree(root: _Box) -> tuple[dict[str, object], list[_Box]]:
    boxes: list[_Box] = []
    seen: set[int] = set()
    listed_by: dict[int, _Box] = {}
    stack = [root]
    while stack:
        box = stack.pop()
        marker = id(box)
        if marker in seen:
            continue
        seen.add(marker)
        boxes.append(box)
        for child in (*box.positioned, *box.floats, *box.children, *box.atoms):
            listed_by.setdefault(id(child), box)
            stack.append(child)
    by_parent: dict[int, list[_Box]] = {}
    for box in boxes:
        if box is root or box.anonymous:
            continue
        parent = box.parent_box
        if parent is None:
            parent = listed_by.get(id(box))
        while parent is not None and parent.anonymous:
            parent = parent.parent_box or listed_by.get(id(parent))
        if parent is None:
            continue
        by_parent.setdefault(id(parent), []).append(box)
    return _hit_node(root, by_parent, "auto", "visible", None, 1.0), boxes


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
    children = (
        []
        if _skips_contents(box)
        else sorted(by_parent.get(id(box), ()), key=lambda child: _hit_sibling_key(box, child))
    )
    node: dict[str, object] = {
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
    transform = _active_transform(box)
    if transform is not None:
        node["transform"] = transform
        node["origin"] = box.transform_origin
    clip = _overflow_hit_clip(box)
    if clip is not None:
        node["clip"] = clip
    if box.border_curve is not None:
        node["radius"] = list(box.border_curve)
    return node


def _overflow_hit_clip(box: _Box) -> list[float] | None:
    """Padding edge of a scrollport, in that box's border-box coordinates."""

    if box.overflow not in _SCROLLPORTS:
        return None
    left = _solved_edge(box, "border_left")
    top = _solved_edge(box, "border_top")
    right = box.border_width - _solved_edge(box, "border_right")
    bottom = box.border_height - _solved_edge(box, "border_bottom")
    return [float(left), float(top), float(right), float(bottom)]


def _solved_edge(box: _Box, key: str) -> int:
    value = box.solved.get(key, 0)
    if value is None:
        return 0
    return _px(value, key)


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
        if box.display == "inline-flex":
            if box.position != "static" or box.float_side != "none":
                raise _Invalid("inline-flex is outside the line")
            if box.writing_mode != "horizontal-tb" or box.direction != "ltr":
                raise _Invalid("inline-flex writing mode is unsupported")
            items, _item_floats, _item_flow, _item_positioned = _walk_flex(
                tree,
                child,
                _modes(box),
                _fonts(box),
                styles,
                declarations,
                ids,
                counter,
                box,
            )
            box.children = items
            for item in items:
                item.parent_box = box
            host.counter_children.append(box)
            host.atoms.append(box)
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
                    not _block_container(box)
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
            if (
                box.positioned
                or not _inline_block_float_ready(box)
                or not _inline_block_blocks(box, tree, child)
                or not _inline_block_nested_ready(box)
            ):
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
    raw_display = _declared(winners, "display", custom)
    ruby = tag == "ruby" and _ruby_element_display(raw_display)
    if ruby:
        display = "inline-block"
        list_item = False
    else:
        display = _keyword(
            raw_display,
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
    parent_em = _positive_px(fonts["font-size"], "font-size")
    font_size = _font_size(_declared(winners, "font-size", custom), fonts["font-size"])
    line_height = _line_height(_declared(winners, "line-height", custom), fonts["line-height"])
    font_family = _read_font_family(_declared(winners, "font-family", custom), fonts["font-family"])
    font_weight = _read_font_weight(_declared(winners, "font-weight", custom), fonts["font-weight"])
    font_style = _read_font_style(_declared(winners, "font-style", custom), fonts["font-style"])
    columns = _read_columns(winners, custom, font_size)
    shape_outside, shape_margin = _read_float_shape(winners, custom) if float_side != "none" else ("", 0.0)
    position_anchor, position_area = _read_position_anchor(winners, custom, position, mode, direction)
    try:
        initial_size, initial_sink = resolve_initial_letter(tree, element, declarations, custom)
    except CssSelectorError as exc:
        raise _Invalid(str(exc)) from exc
    if initial_size and (
        display not in {"block", "flow-root"}
        or list_item
        or replaced
        or float_side != "none"
        or position != "static"
    ):
        raise _Invalid("initial letter is unsupported")
    align_mode, align_safe = _block_align_mode(display, _declared(winners, "align-content", custom))
    text_box_trim, text_box_edge = _read_text_box_trim(winners, custom)
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
        font_family=font_family,
        font_weight=font_weight,
        font_style=font_style,
        vertical_align=(
            _read_inline_align(
                _declared(winners, "vertical-align", custom),
                font_size,
                line_height,
                parent_em,
            )
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
        letter_spacing=_used_spacing_px(
            _read_spacing(_declared(winners, "letter-spacing", custom), fonts["letter-spacing"], "letter-spacing")
        ),
        word_spacing=_used_spacing_px(
            _read_spacing(_declared(winners, "word-spacing", custom), fonts["word-spacing"], "word-spacing")
        ),
        text_autospace=_read_text_autospace(
            _declared(winners, "text-autospace", custom), fonts["text-autospace"]
        ),
        text_transform=_used_text_transform(
            _declared(winners, "text-transform", custom),
            fonts["text-transform"],
            mode,
            direction,
            display,
        ),
        tab_size=_read_tab_size(_declared(winners, "tab-size", custom), fonts["tab-size"]),
        white_space=_inherited_keyword(
            _declared(winners, "white-space", custom),
            _WHITES,
            fonts["white-space"],
            _FONT["white-space"],
            "white-space",
        ),
        overflow_wrap=_inherited_keyword(
            _declared_latest(winners, ("overflow-wrap", "word-wrap"), custom),
            _OVERFLOW_WRAPS,
            fonts["overflow-wrap"],
            _FONT["overflow-wrap"],
            "overflow-wrap",
        ),
        word_break=_inherited_keyword(
            _declared(winners, "word-break", custom),
            _WORD_BREAKS,
            fonts["word-break"],
            _FONT["word-break"],
            "word-break",
        ),
        hyphens=_inherited_keyword(
            _declared(winners, "hyphens", custom),
            _HYPHENS,
            fonts["hyphens"],
            _FONT["hyphens"],
            "hyphens",
        ),
        hyphenate_character=_read_hyphenate_character(
            _declared(winners, "hyphenate-character", custom),
            fonts["hyphenate-character"],
        ),
        lang=_read_lang(element, fonts["lang"]),
        hanging_punctuation=_read_hanging(
            _declared(winners, "hanging-punctuation", custom), fonts["hanging-punctuation"]
        ),
        text_wrap_style=_text_wrap_style(winners, custom, fonts["text-wrap-style"]),
        line_clamp=_read_line_clamp(_declared(winners, "line-clamp", custom)),
        align_mode=align_mode,
        align_safe=align_safe,
        margin_trim=_read_margin_trim(_declared(winners, "margin-trim", custom)),
        text_box_trim=text_box_trim,
        text_box_edge=text_box_edge,
        initial_letter=initial_size,
        initial_sink=initial_sink,
        parent_direction=parent_direction,
        multicol=columns,
        column_span=_read_column_span(winners, custom),
        break_before=_read_fragment_break(winners, custom, "break-before"),
        break_after=_read_fragment_break(winners, custom, "break-after"),
        widows=_read_line_break_count(
            _declared(winners, "widows", custom), fonts.get("widows", ""), "widows"
        ),
        orphans=_read_line_break_count(
            _declared(winners, "orphans", custom), fonts.get("orphans", ""), "orphans"
        ),
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
    if _autospace_on(box) and (box.writing_mode != "horizontal-tb" or box.direction != "ltr"):
        raise _Invalid("text-autospace writing mode is unsupported")
    _bind_plane_transform(box, winners, custom)
    boxes = getattr(tree, "box_of", None)
    if not isinstance(boxes, dict):
        boxes = {}
        tree.box_of = boxes
    boxes[id(element)] = box
    box.ruby = ruby
    try:
        box.scrollbar_gutter = parse_scrollbar_gutter(_declared(winners, "scrollbar-gutter", custom))
    except ScrollbarGutterError as exc:
        raise _Invalid(exc.reason) from exc
    style = getattr(tree, "scrollbars", "classic")
    box.scrollbars = style if style in {"classic", "overlay"} else "classic"
    path, distance, rotate, anchor = _read_offset(winners, custom)
    box.offset_path = path
    box.offset_distance = distance
    box.offset_rotate = rotate
    box.offset_anchor = anchor
    box.scroll_rule = _read_scroll_rule(winners, custom)
    box.border_radius = _read_border_radius(winners, custom)
    box.color, box.color_valid = _used_color(_declared(winners, "color", custom), fonts)
    box.emphasis_mark, box.emphasis_position = _read_text_emphasis(winners, custom, fonts)
    if box.display == "inline" and not box.replaced and _emphasis_authored(winners):
        raise _Invalid("inline text emphasis is unsupported")
    if box.emphasis_mark and (
        box.writing_mode != "horizontal-tb"
        or box.direction != "ltr"
        or box.display not in {"block", "flow-root"}
        or box.list_item
        or box.float_side != "none"
        or box.replaced
    ):
        raise _Invalid("text emphasis is unsupported")
    box.outline = _read_outline(winners, custom, box.color, box.color_valid)
    if box.display == "inline" and not box.replaced and box.outline is not None:
        raise _Invalid("inline outline is unsupported")
    box.shadows = _read_box_shadow(winners, custom, box.color, box.color_valid)
    if box.display == "inline" and not box.replaced and box.shadows:
        raise _Invalid("inline box-shadow is unsupported")
    box.column_rule = _read_column_rule(winners, custom, box.color, box.color_valid)
    box.snap_type, box.snap_align, box.scroll_padding, box.scroll_margin = _read_scroll_snap(
        winners, custom
    )
    _bind_height_transition(box, winners, custom)
    box.intrinsic_block = _read_intrinsic_block(winners, custom)
    _reject_skipped_box(box)
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


def _declared_latest(winners: list[tuple[int, str, str]], names: tuple[str, ...], custom: dict) -> str | None:
    """The latest declared alias. ``word-wrap`` and ``overflow-wrap`` are one property."""

    chosen: tuple[int, str, str] | None = None
    allowed = set(names)
    for order, prop, value in winners:
        if prop in allowed and (chosen is None or order >= chosen[0]):
            chosen = (order, prop, value)
    if chosen is None:
        return None
    return _declared([chosen], chosen[1], custom)


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


def _vertical_frame(
    box: _Box, flow: dict[str, object], width: int, height: int | None, height_limit: int | None,
):
    """Physical slot solver for one vertical box in a horizontal containing block."""

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

    return slots, sizing, geometry


def _vertical_loose_text(box: _Box) -> bool:
    element = box.element
    if element is None or box.tree is None:
        return bool((box.inline_text or "").strip())
    before, after = _generated(box.tree, element)
    if before.strip() or after.strip():
        return True
    if str(element.text or "").strip():
        return True
    return any(str(getattr(node, "tail", "") or "").strip() for node in list(element))


def _physical_height_auto(box: _Box) -> bool:
    token = _physical_slots(box).get("height", "auto").strip().lower()
    return token in {"auto", "initial", "unset", "revert"}


def _physical_width_auto(box: _Box) -> bool:
    token = _physical_slots(box).get("width", "auto").strip().lower()
    return token in {"auto", "initial", "unset", "revert"}


def _orthogonal_horizontal(child: _Box, parent: _Box) -> bool:
    """A horizontal block whose inline axis is the vertical parent's block axis."""

    return (
        parent.writing_mode in {"vertical-rl", "vertical-lr"}
        and child.writing_mode == "horizontal-tb"
        and child.direction == "ltr"
        and child.text_orientation == "mixed"
    )


def _orthogonal_axis_px(slots: dict[str, str], name: str) -> int | None:
    """Content-box length, or None when that axis is automatic."""

    token = slots.get(name, "auto").strip().lower()
    if token in {"auto", "initial", "unset", "revert"}:
        return None
    if not token.endswith("px"):
        raise _Invalid("orthogonal nested size is unsupported")
    try:
        number = float(token[:-2])
    except ValueError as exc:
        raise _Invalid("orthogonal nested size is unsupported") from exc
    if number < 0:
        raise _Invalid("orthogonal nested size is unsupported")
    return _px(number, name)


def _layout_orthogonal_child(child: _Box, block_size: int | None) -> None:
    """Size one horizontal block against a vertical parent's block size.

    An indefinite block size uses the child's max-content width, which breaks
    the cyclic stretch. A definite block size uses the float shrink-to-fit
    equation when width is automatic: available space clamps the max-content,
    and the min-content still wins when the text cannot break. A specified
    width is the content width even when the text is shorter or cannot break.
    A specified height is the content height, so the border box does not
    follow the line boxes. An automatic height stays the stacked lines.
    Mixed font sizes use each run's advance, so a larger letter can grow a line.
    """

    if child.children or child.floats or child.atoms or child.positioned:
        raise _Invalid("orthogonal nested block is unsupported")
    if not (child.inline_text or "").strip():
        raise _Invalid("orthogonal nested block is unsupported")
    _reject_vertical_margins(child)
    if _box_sizing(child) != "content-box" or child.aspect_ratio is not None:
        raise _Invalid("orthogonal nested size is unsupported")
    if _has_explicit_limit(child, _WIDTH_LIMITS + _HEIGHT_LIMITS):
        raise _Invalid("orthogonal nested size is unsupported")
    slots = _physical_slots(child)
    specified = _orthogonal_axis_px(slots, "width")
    _orthogonal_axis_px(slots, "height")
    if specified is None:
        if block_size is None:
            _minimum, maximum = _intrinsic_text_sizes(child)
            measure = maximum
        else:
            measure = _shrink_float_width(child, block_size)
    else:
        measure = specified
    _solve(child, measure, None, None, 0, None)


def _auto_slot(slots: dict[str, str], name: str) -> bool:
    return slots.get(name, "auto").strip().lower() in {"auto", "initial", "unset", "revert"}


def _reject_vertical_child(child: _Box) -> None:
    if (
        child.display != "block"
        or child.position != "static"
        or child.float_side != "none"
        or child.multicol is not None
        or child.flex is not None
        or child.grid is not None
        or child.table is not None
        or child.replaced
    ):
        raise _Invalid("vertical nested block is unsupported")


def _reject_vertical_margins(child: _Box) -> None:
    """Reject an author margin. The horizontal equation's end slack is not one.

    A vertical child is sized with the horizontal containing block's equation,
    so a used inline-end margin absorbs leftover space. That slack is not a
    margin on the vertical block axis.
    """

    slots = _physical_slots(child)
    for side in ("top", "right", "bottom", "left"):
        raw = slots.get(f"margin-{side}", "0px").strip().lower()
        if raw in {"0", "0px", "auto", "initial", "unset", "revert"}:
            continue
        if raw.endswith("px") and _px(float(raw[:-2]), "margin") == 0:
            continue
        raise _Invalid("vertical nested margin is unsupported")


def _stack_vertical_x(box: _Box) -> None:
    content_x = box.x + _edge_extent(box.solved, "left")
    for child in box.children:
        child.x = content_x + child.local_x
        if child.anchor_laid:
            _stack_vertical_x(child)


def _vertical_child_stack(
    box: _Box, flow: dict[str, object], width: int, height: int | None, height_limit: int | None,
) -> dict[str, object]:
    """Stack parallel vertical blocks on the parent's block axis."""

    if box.floats or box.atoms or box.positioned or box.inline_text or _mixed_runs(box) or _vertical_loose_text(box):
        raise _Invalid("vertical block requires uniform inline text")
    slots, sizing, geometry = _vertical_frame(box, flow, width, height, height_limit)
    preview = geometry()
    specified = preview.get("content_height")
    parent_content_height = None if specified == "auto" else _px(specified, "content height")
    # Auto physical width is stretched by the horizontal equation. The slot,
    # not the preview, tells whether the vertical block size is indefinite.
    block_auto = _auto_slot(slots, "width")
    parent_content_width = None if block_auto else _px(preview.get("content_width"), "content width")
    available = parent_content_height if parent_content_height is not None else height_limit
    orthogonal = [child for child in box.children if _orthogonal_horizontal(child, box)]
    for child in box.children:
        _reject_vertical_child(child)
        is_orthogonal = child in orthogonal
        if not is_orthogonal and (
            child.writing_mode != box.writing_mode
            or child.direction != box.direction
            or child.text_orientation != box.text_orientation
        ):
            raise _Invalid("vertical nested writing mode is unsupported")
        child_slots = _physical_slots(child)
        if "%" in child_slots.get("width", "") or "%" in child_slots.get("height", ""):
            raise _Invalid("vertical nested percentage is unsupported")
        if is_orthogonal:
            _layout_orthogonal_child(child, parent_content_width)
            continue
        height_auto = _physical_height_auto(child)
        _solve(child, width, available, None, 0, None)
        _reject_vertical_margins(child)
        if parent_content_height is not None and height_auto:
            chrome = _edge_extent(child.solved, "top", "bottom")
            content_target = parent_content_height - chrome
            if content_target < 0:
                raise _Invalid("vertical nested block is unsupported")
            if child.definite_height != content_target:
                fitted = parent_content_height if _box_sizing(child) == "border-box" else content_target
                child.declarations.append(("height", f"{fitted}px"))
                _solve(child, width, available, None, 0, None)
                _reject_vertical_margins(child)
    widths: list[int] = []
    inlines: list[int] = []
    for child in box.children:
        block = child.content_width + _edge_extent(child.solved, "left", "right")
        inline = (0 if child.definite_height is None else child.definite_height) + _edge_extent(
            child.solved, "top", "bottom"
        )
        child.border_width = block
        child.border_height = inline
        child.content_height = 0 if child.definite_height is None else child.definite_height
        widths.append(block)
        inlines.append(inline)
    if _auto_slot(slots, "width"):
        extent = sum(widths)
        if sizing == "border-box":
            extent += _edge_extent(preview, "left", "right")
        slots["width"] = f"{extent}px"
    if parent_content_height is None:
        extent = max(inlines) if inlines else 0
        if sizing == "border-box":
            extent += _edge_extent(preview, "top", "bottom")
        slots["height"] = f"{extent}px"
    solved = geometry()
    content_w = _px(solved.get("content_width"), "content width")
    anchor = _edge_extent(solved, "top")
    if flow["block_start"] == "right":
        cursor = content_w
        for child, block in zip(box.children, widths):
            cursor -= block
            child.local_x = cursor
    else:
        cursor = 0
        for child, block in zip(box.children, widths):
            child.local_x = cursor
            cursor += block
    for child in box.children:
        child.anchor_y = anchor
    box.anchor_laid = True
    box.lines = []
    return solved


def _vertical_geometry(
    box: _Box, flow: dict[str, object], width: int, height: int | None, height_limit: int | None,
) -> dict[str, object]:
    if box.children or box.floats or box.atoms or box.positioned or _mixed_runs(box):
        raise _Invalid("vertical block requires uniform inline text")
    if _has_text_combine(box):
        if box.writing_mode not in {"vertical-rl", "vertical-lr"}:
            raise _Invalid("text-combine writing mode is unsupported")
        if str(flow["direction"]) != "ltr" or flow["line_left"] != "top":
            raise _Invalid("text-combine direction is unsupported")
        if box.text_align not in {"start", "left"} or box.text_align_last not in {"auto", "start", "left"}:
            raise _Invalid("text-combine alignment is unsupported")
        if _gap_alignment(box):
            raise _Invalid("text-combine alignment is unsupported")
    if _gap_alignment(box) and (
        flow["line_left"] != "top"
        or str(flow["direction"]) != "ltr"
        or box.writing_mode not in {"vertical-rl", "vertical-lr"}
        or _relative_pieces(box)
    ):
        raise _Invalid("vertical justification is unsupported")

    # Resolve logical declarations in the child's axes once. Physical margins
    # and percentage bases belong to its horizontal containing block.
    slots, sizing, geometry = _vertical_frame(box, flow, width, height, height_limit)
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
        column = line.height
        inline_offset = line.x
        inline_extent = line.content_width
        block_cursor = line.y
        line.x = block_size - block_cursor - column if flow["block_start"] == "right" else block_cursor
        line.y = measure - inline_offset - inline_extent if flow["line_left"] == "bottom" else inline_offset
        line.content_width = column
        line.height = inline_extent
        if line.runs:
            if flow["line_left"] != "top":
                raise _Invalid("vertical justification is unsupported")
            line.runs = [
                {
                    "text": run["text"],
                    "x": 0,
                    "y": int(run["x"]),
                    "font_size": run["font_size"],
                    "width": column,
                    "height": int(run["width"]),
                }
                for run in line.runs
            ]
        if _text_combine_active(box):
            if inline_offset != 0 or block_cursor != 0:
                raise _Invalid("text-combine alignment is unsupported")
            if column != box.font_size:
                raise _Invalid("text-combine line-height is unsupported")
            _attach_upright_combine(line, box, column)
    if _text_combine_active(box):
        if len(lines) != 1 or lines[0].text != (box.inline_text or ""):
            raise _Invalid("text-combine break is unsupported")
        if not lines[0].combines:
            raise _Invalid("text-combine is invalid")
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
    height = _column_height(_column_text(_declared(winners, "column-height", custom)))
    if count is None and width is None and height is None:
        return None
    if height is not None and count is None and width is None:
        raise _Invalid("column-height needs a column count or column width")
    return {
        "count": "auto" if count is None else count,
        "width": "auto" if width is None else width,
        "gap": _column_gap(_column_text(_declared(winners, "column-gap", custom)), font_size),
        "fill": _column_fill(_column_text(_declared(winners, "column-fill", custom))),
        "height": height,
        "wrap": _column_wrap(_column_text(_declared(winners, "column-wrap", custom))),
        "row_gap": _row_gap(_column_text(_declared(winners, "row-gap", custom)), font_size),
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


def _column_height(value: str | None) -> int | None:
    if value is None or value in {"auto", "initial", "unset", "revert"}:
        return None
    if value == "inherit":
        raise _Invalid("column-height inherit is unsupported")
    if not value.endswith("px"):
        raise _Invalid("column-height is invalid")
    number = _px(float(value[:-2]), "column-height")
    if number < 1:
        raise _Invalid("column-height is invalid")
    return number


def _column_wrap(value: str | None) -> str:
    if value is None or value in {"auto", "initial", "unset", "revert"}:
        return "auto"
    if value == "inherit":
        raise _Invalid("column-wrap inherit is unsupported")
    if value in {"nowrap", "wrap"}:
        return value
    raise _Invalid("column-wrap is invalid")


def _row_gap(value: str | None, font_size: int) -> int:
    if value is None or value in {"normal", "initial", "unset", "revert"}:
        return font_size
    if value == "inherit":
        raise _Invalid("row-gap inherit is unsupported")
    if value in {"0", "0px"}:
        return 0
    if not value.endswith("px"):
        raise _Invalid("row-gap is invalid")
    number = _px(float(value[:-2]), "row-gap")
    if number < 0:
        raise _Invalid("row-gap is invalid")
    return number


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


def _read_line_break_count(value: str | None, parent: str, name: str) -> int | None:
    """Positive ``widows`` or ``orphans``. An omitted value does not fragment lines."""

    if value is None:
        return int(parent) if parent.isdigit() else None
    text = " ".join(value.split()).lower()
    if text in {"initial", "unset", "revert"}:
        return None
    if text == "inherit":
        return int(parent) if parent.isdigit() else None
    if not text.isdigit() or text.startswith("0"):
        raise _Invalid(f"{name} is invalid")
    return int(text)


def _line_fragments(
    line_count: int, slot: int, columns: int, orphans: int, widows: int
) -> list[tuple[int, int]]:
    """Split one block so a break keeps orphans before it and widows after it.

    A column that cannot hold a legal break is skipped until the block starts.
    After that, the current column keeps every remaining line.
    """

    if line_count <= slot or columns < 2:
        return [(0, line_count)]
    remaining = line_count
    column = 0
    started = False
    placed: list[tuple[int, int]] = []
    while remaining > 0:
        if remaining <= slot or column >= columns - 1:
            placed.append((column, remaining))
            break
        minimum = orphans if not started else max(orphans, widows)
        maximum = slot
        if remaining - slot < widows:
            maximum = min(maximum, remaining - widows)
        if maximum < minimum:
            if started:
                placed.append((column, remaining))
                break
            column += 1
            continue
        placed.append((column, maximum))
        remaining -= maximum
        started = True
        column += 1
    return placed


def _spread_column_lines(
    box: _Box,
    *,
    content_x: int,
    count: int,
    gap: int,
    limit: int,
    column_width: int,
) -> None:
    """Move one text child's lines into fixed columns and shrink its first fragment."""

    if len(box.children) != 1:
        return
    child = box.children[0]
    if child.widows is None and child.orphans is None:
        return
    orphans = 2 if child.orphans is None else child.orphans
    widows = 2 if child.widows is None else child.widows
    lines = child.lines
    if not lines:
        raise _Invalid("column line fragmentation is unsupported")
    height = lines[0].height
    uniform = all(line.height == height and line.y == index * height for index, line in enumerate(lines))
    stacked = lines[-1].y + lines[-1].height
    if (
        not uniform
        or height < 1
        or child.content_height != stacked
        or _edge_extent(child.solved, "top", "bottom", "left", "right") != 0
    ):
        raise _Invalid("column line fragmentation is unsupported")
    slot = limit // height
    if slot < 1:
        raise _Invalid("column line fragmentation is unsupported")
    plan = _line_fragments(len(lines), slot, count, orphans, widows)
    if sum(taken for _column, taken in plan) != len(lines):
        raise _Invalid("column line fragmentation is unsupported")
    if plan == [(0, len(lines))]:
        return
    first_column, first_count = plan[0]
    origin = _px(box.solved.get("border_top"), "border-top") + _px(box.solved.get("padding_top"), "padding-top")
    first_x = _column_inline_offset(first_column, box.content_width, gap, count)
    child.x = content_x + first_x + child.margin_left
    child.anchor_y = origin
    index = 0
    for column, taken in plan:
        column_x = _column_inline_offset(column, box.content_width, gap, count)
        for local in range(taken):
            line = lines[index]
            line.x += column_x - first_x
            line.y = local * height
            index += 1
    child.content_height = first_count * height
    child.border_height = child.content_height
    child.definite_height = child.content_height
    _stamp_column_rules(
        box,
        [(0, limit, {column for column, taken in plan if taken})],
        count=count,
        gap=gap,
        column_width=column_width,
    )


def _place_multicol(box: _Box, content_x: int, viewport_height: int | None) -> None:
    """Lay text-only children into columns and anchor them there.

    ``column-fill: auto`` with a definite height fills that content height in
    source order. A spanner balances the line above it and the next row fills
    the block size that remains. An automatic height still balances.
    """

    spec = box.multicol or {}
    if box.floats or box.positioned or box.atoms or box.inline_text:
        raise _Invalid("column content is unsupported")
    column_block = spec.get("height")
    if column_block is not None:
        if box.definite_height is not None:
            raise _Invalid("column-height with a specified height is unsupported")
        if str(spec.get("wrap", "auto")) == "nowrap":
            raise _Invalid("column-wrap nowrap is unsupported")
    fill = str(spec.get("fill", "balance"))
    if any(child.widows is not None or child.orphans is not None for child in box.children):
        fixed_fill = column_block is None and fill == "auto" and box.definite_height is not None
        only = box.children[0] if len(box.children) == 1 else None
        if not fixed_fill or only is None or only.column_span == "all":
            raise _Invalid("column line fragmentation is unsupported")
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
        if column_block is not None and (child.break_before != "auto" or child.break_after != "auto"):
            raise _Invalid("column break with column-height is unsupported")
        _reject_column_child(child)
        measure = available if child.column_span == "all" else column_width
        _solve(child, measure, None, viewport_height, content_x)
        _reject_column_margin(child)
        chrome = _edge_extent(child.solved, "top", "bottom")
        content_height = 0 if child.definite_height is None else child.definite_height
        child.content_height = content_height
        child.border_height = content_height + chrome
        fragments.append({"id": child.id, "height": child.border_height, "span": child.column_span})
    if column_block is not None:
        _anchor_column_height_rows(box, content_x, available, fragments, column_block)
        return
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
    _stamp_column_rules(
        box,
        _content_rule_rows(placed),
        count=_px(flowed.get("column_count"), "column count"),
        gap=_px(spec.get("gap", 0), "column gap"),
        column_width=_px(flowed.get("column_width"), "column width"),
    )
    box.anchor_laid = True


def _anchor_column_height_rows(
    box: _Box,
    content_x: int,
    available: int,
    fragments: list[dict[str, object]],
    column_block: object,
) -> None:
    """Fill fixed-height rows and keep that block size, including the gaps."""

    spec = box.multicol or {}
    flowed = layout_column_rows(
        available,
        fragments,
        column_width=spec.get("width", "auto"),
        column_count=spec.get("count", "auto"),
        column_gap=spec.get("gap", 0),
        column_height=column_block,
        row_gap=spec.get("row_gap", 0),
    )
    placed = flowed.get("boxes")
    if flowed.get("outcome") != "flowed" or not isinstance(placed, list):
        raise _Invalid(str(flowed.get("reason") or "columns failed"))
    count = _px(flowed.get("column_count"), "column count")
    gap = _px(spec.get("gap", 0), "column gap")
    rows: list[dict[str, object]] = []
    for item in placed:
        if not isinstance(item, dict):
            raise _Invalid("column placement failed")
        column = _px(item.get("column"), "column")
        rows.append(
            {
                "id": item.get("id"),
                "inline": _column_inline_offset(column, available, gap, count),
                "block": item.get("block"),
            }
        )
    _anchor_column_rows(box, content_x, rows, "inline", "block")
    if box.definite_height is None:
        box.definite_height = _px(flowed.get("block_size"), "column block size")
    _stamp_column_rules(
        box,
        _fixed_height_rule_rows(
            placed,
            _px(column_block, "column height"),
            _px(spec.get("row_gap", 0), "row gap"),
        ),
        count=count,
        gap=gap,
        column_width=_px(flowed.get("column_width"), "column width"),
    )
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
    column_width = _px(preview.get("column_width"), "column width")
    limit = box.definite_height
    if limit is None:
        raise _Invalid("column block size is indefinite")
    spec = box.multicol or {}
    cursor = 0
    rows: list[dict[str, object]] = []
    rule_rows: list[tuple[int, int, set[int]]] = []
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
            row_start = cursor
            for item in placed:
                if not isinstance(item, dict):
                    raise _Invalid("column placement failed")
                take_row(item, item.get("inline"), cursor + _px(item.get("block"), "column block"))
            cursor += _px(flowed.get("block_size"), "column block size")
            rule_rows.append((row_start, cursor - row_start, _occupied_columns(placed)))
        else:
            remaining = limit - cursor if cursor < limit else 0
            row_start = cursor
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
            if remaining > 0:
                rule_rows.append((row_start, remaining, _occupied_columns(placed)))
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
    _stamp_column_rules(box, rule_rows, count=count, gap=gap, column_width=column_width)
    _spread_column_lines(
        box,
        content_x=content_x,
        count=count,
        gap=gap,
        limit=limit,
        column_width=column_width,
    )
    box.anchor_laid = True


def _occupied_columns(placed: list) -> set[int]:
    found: set[int] = set()
    for item in placed:
        if not isinstance(item, dict) or item.get("span") == "all":
            continue
        column = item.get("column")
        if type(column) is int:
            found.add(column)
    return found


def _content_rule_rows(placed: list) -> list[tuple[int, int, set[int]]]:
    """Column-box block start, size, and occupied columns. A spanner is skipped."""

    grouped: dict[int, list[dict[str, object]]] = {}
    for item in placed:
        if not isinstance(item, dict) or item.get("span") == "all":
            continue
        line = item.get("line")
        column = item.get("column")
        if type(line) is not int or type(column) is not int:
            continue
        grouped.setdefault(line, []).append(item)
    rows: list[tuple[int, int, set[int]]] = []
    for line in sorted(grouped):
        items = grouped[line]
        start = min(_px(item.get("block"), "column block") for item in items)
        end = max(
            _px(item.get("block"), "column block") + _px(item.get("height"), "column height")
            for item in items
        )
        rows.append((start, end - start, {int(item["column"]) for item in items}))
    return rows


def _fixed_height_rule_rows(
    placed: list, height: int, row_gap: int
) -> list[tuple[int, int, set[int]]]:
    """One fixed column box per content line. A spanner line has no gap."""

    occupied: dict[int, set[int]] = {}
    for item in placed:
        if not isinstance(item, dict) or item.get("span") == "all":
            continue
        line = item.get("line")
        column = item.get("column")
        if type(line) is not int or type(column) is not int:
            continue
        occupied.setdefault(line, set()).add(column)
    return [(line * (height + row_gap), height, columns) for line, columns in sorted(occupied.items())]


def _stamp_column_rules(
    box: _Box,
    rows: list[tuple[int, int, set[int]]],
    *,
    count: int,
    gap: int,
    column_width: int,
) -> None:
    """Center one stroke in every gap between two occupied columns."""

    rule = box.column_rule
    if rule is None or count < 2:
        box.column_rules = ()
        return
    style, rule_width, color = rule
    offset = (gap - rule_width) // 2
    rects: list[tuple[int, int, int, int, str, str]] = []
    for start, height, occupied in rows:
        if height <= 0:
            continue
        for index in range(count - 1):
            if index not in occupied or index + 1 not in occupied:
                continue
            gap_start = _column_inline_offset(index, box.content_width, gap, count) + column_width
            rects.append((gap_start + offset, start, rule_width, height, style, color))
    box.column_rules = tuple(rects)


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


def _apply_scrollbar_gutter(box: _Box, *, overflowing: bool | None) -> None:
    if box.allotted_content_width is None:
        box.allotted_content_width = box.content_width
    allotted = box.allotted_content_width
    try:
        reserved = reserve_scrollbar_gutter(
            overflow=box.overflow,
            gutter=box.scrollbar_gutter,
            display=box.display,
            overflowing=overflowing,
            scrollbars=box.scrollbars,
            writing_mode=box.writing_mode,
            direction=box.direction,
        )
    except ScrollbarGutterError as exc:
        raise _Invalid(exc.reason) from exc
    start = int(reserved["start"])
    end = int(reserved["end"])
    if start + end > allotted:
        raise _Invalid("scrollbar gutter exceeds the content box")
    box.gutter_start = start
    box.gutter_end = end
    box.gutter_pending = bool(reserved["pending"])
    box.content_width = allotted - start - end


def _child_border_block(child: _Box) -> int:
    content = child.definite_height
    if content is None:
        content = sum(line.height for line in child.lines)
    chrome = _edge_extent(child.solved, "top", "bottom") if child.solved else 0
    return content + chrome


def _block_overflows(box: _Box) -> bool:
    limit = box.definite_height
    if box.max_content_height is not None:
        limit = box.max_content_height if limit is None else min(limit, box.max_content_height)
    if limit is None:
        return False
    if not box.children:
        return sum(line.height for line in box.lines) > limit
    used = 0
    pending = 0
    for child in box.children:
        top = _px(child.solved.get("margin_top"), "margin-top") if child.solved else 0
        bottom = _px(child.solved.get("margin_bottom"), "margin-bottom") if child.solved else 0
        pending = max(pending, top)
        used += pending + _child_border_block(child)
        pending = bottom
    return used + pending > limit


def _lay_block_contents(
    box: _Box,
    content_x: int,
    viewport_height: int | None,
    scrollport_height: int | None,
) -> None:
    if box.text_box_trim != "none" and box.children:
        raise _Invalid("text-box-trim block children are unsupported")
    if box.line_clamp is not None and (box.display in {"flex", "grid", "table"} or box.multicol is not None):
        raise _Invalid("clamped formatting context is unsupported")
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
    if _skips_contents(box) and (box.floats or box.atoms):
        raise _Invalid("content-visibility content is unsupported")
    if box.floats and not box.children and not _skips_contents(box):
        _place_floats(box, content_x)
    if not _skips_contents(box) and not box.children and (box.inline_text or box.floats or box.atoms):
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


def _solve(
    box: _Box, parent_width: int, parent_height: int | None, viewport_height: int | None,
    parent_content_x: int, scrollport_height: int | None = None,
) -> None:
    if box.margin_trim != "none":
        if box.writing_mode != "horizontal-tb":
            raise _Invalid("margin-trim writing mode is unsupported")
        if box.multicol is not None:
            raise _Invalid("margin-trim columns are unsupported")
    if box.text_box_trim != "none":
        if box.writing_mode != "horizontal-tb" or box.direction != "ltr":
            raise _Invalid("text-box-trim writing mode is unsupported")
        if box.replaced:
            raise _Invalid("text-box-trim replaced element is unsupported")
        if box.display not in {"block", "flow-root"}:
            raise _Invalid("text-box-trim display is unsupported")
        if box.position in {"absolute", "fixed", "sticky"} or box.float_side != "none":
            raise _Invalid("text-box-trim position is unsupported")
        if box.multicol is not None:
            raise _Invalid("text-box-trim columns are unsupported")
    box.containing_inline = parent_width
    box.allotted_content_width = None
    box.gutter_start = 0
    box.gutter_end = 0
    box.gutter_pending = False
    flow = _writing_flow(box)
    horizontal = flow["horizontal"] is True
    if box.initial_letter:
        _reject_initial_letter_context(box, horizontal)
    if box.display == "flow-root":
        if not horizontal or box.direction != "ltr":
            raise _Invalid("flow-root writing mode is unsupported")
        if box.replaced:
            raise _Invalid("replaced display is unsupported")
        if box.multicol is not None:
            raise _Invalid("flow-root columns are unsupported")
    vertical_text = not horizontal and box.display == "block"
    if vertical_text:
        _reject_decoration_context(box)
        limits = [limit for limit in (parent_height, viewport_height, scrollport_height) if limit is not None]
        limit = min(limits, default=None)
        if box.children:
            solved = _vertical_child_stack(box, flow, parent_width, parent_height, limit)
        else:
            solved = _vertical_geometry(box, flow, parent_width, parent_height, limit)
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
    if vertical_text and box.anchor_laid:
        _stack_vertical_x(box)
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
    _apply_scrollbar_gutter(box, overflowing=None)
    for _ in range(2):
        content_x = box.x + _edge_extent(solved, "left") + box.gutter_start
        _lay_block_contents(box, content_x, viewport_height, scrollport_height)
        if not box.gutter_pending or not _block_overflows(box):
            break
        _apply_scrollbar_gutter(box, overflowing=True)


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


def _block_container(box: _Box) -> bool:
    return box.display in {"block", "flow-root"}


def _aspect_block(box: _Box) -> bool:
    return (
        _block_container(box)
        and not box.replaced
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
        not _block_container(box)
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


def _margin_trim_flags(box: _Box) -> tuple[bool, bool]:
    """Block-edge trim for an in-flow horizontal block container.

    ``margin-trim`` does not apply to flex, grid, table, float, or out-of-flow
    boxes. On a box it does apply to, ``block`` trims both block edges.
    """

    if box.margin_trim == "none":
        return False, False
    if (
        box.display not in {"block", "flow-root", "inline-block"}
        or box.float_side != "none"
        or box.position in {"absolute", "fixed"}
        or box.writing_mode != "horizontal-tb"
    ):
        return False, False
    return box.margin_trim in {"block", "block-start"}, box.margin_trim in {"block", "block-end"}


def _read_margin_trim(value: str | None) -> str:
    """``none``, ``block``, or the block-start and block-end edges.

    ``block`` is both edges. The two edge keywords may occur in either order.
    ``inline`` is not a value of this property.
    """

    if value is None:
        return "none"
    text = " ".join(value.strip().lower().split())
    if text in {"", "initial", "unset", "revert"}:
        return "none"
    if text == "inherit":
        raise _Invalid("margin-trim inherit is unsupported")
    if text in {"none", "block", "block-start", "block-end"}:
        return text
    parts = text.split(" ")
    if len(parts) == 2 and set(parts) == {"block-start", "block-end"}:
        return "block"
    raise _Invalid("margin-trim is invalid")


_TEXT_BOX_TRIMS = frozenset({"none", "trim-start", "trim-end", "trim-both"})
_TEXT_BOX_OVER = frozenset({"text", "cap", "ex"})
_TEXT_BOX_UNDER = frozenset({"text", "alphabetic"})
_TEXT_BOX_DOUBLED = frozenset({"text"})
_TEXT_BOX_UNSUPPORTED_EDGES = frozenset({"ideographic", "ideographic-ink"})


def _read_text_box_trim(
    winners: list[tuple[int, str, str]], custom: dict
) -> tuple[str, tuple[str, str]]:
    """Used ``text-box-trim`` and the over/under metric it meets.

    The properties are not inherited. ``auto`` and ``text`` trim to the em
    box. ``cap`` and ``ex`` name synthetic metrics inside that em.
    """

    trim_at: tuple[int, str] | None = None
    edge_at: tuple[int, str] | None = None
    for order, prop, value in winners:
        if prop not in {"text-box", "text-box-trim", "text-box-edge"}:
            continue
        raw = _declared([(order, prop, value)], prop, custom)
        if raw is None:
            continue
        if prop == "text-box":
            trim_token, edge_token = _split_text_box(raw)
            if trim_at is None or order >= trim_at[0]:
                trim_at = (order, trim_token)
            if edge_at is None or order >= edge_at[0]:
                edge_at = (order, edge_token)
            continue
        if prop == "text-box-trim":
            if trim_at is None or order >= trim_at[0]:
                trim_at = (order, raw)
            continue
        if edge_at is None or order >= edge_at[0]:
            edge_at = (order, raw)
    trim = _parse_text_box_trim(None if trim_at is None else trim_at[1])
    edge = _parse_text_box_edge(None if edge_at is None else edge_at[1])
    return trim, edge


def _split_text_box(value: str) -> tuple[str, str]:
    text = " ".join(value.strip().lower().split())
    if text in {"", "initial", "unset", "revert", "normal", "none"}:
        return "none", "auto"
    if text == "inherit":
        raise _Invalid("text-box inherit is unsupported")
    parts = text.split(" ")
    if parts[0] in _TEXT_BOX_TRIMS:
        edge = " ".join(parts[1:]) or "auto"
        return parts[0], edge
    return "none", text


def _parse_text_box_trim(value: str | None) -> str:
    if value is None:
        return "none"
    text = " ".join(value.strip().lower().split())
    if text in {"", "initial", "unset", "revert", "none"}:
        return "none"
    if text == "inherit":
        raise _Invalid("text-box-trim inherit is unsupported")
    if text in _TEXT_BOX_TRIMS:
        return text
    raise _Invalid("text-box-trim is invalid")


def _parse_text_box_edge(value: str | None) -> tuple[str, str]:
    """Over and under edges. A single keyword is kept only when it can be doubled."""

    if value is None:
        return ("text", "text")
    text = " ".join(value.strip().lower().split())
    if text in {"", "initial", "unset", "revert", "auto"}:
        return ("text", "text")
    if text == "inherit":
        raise _Invalid("text-box-edge inherit is unsupported")
    parts = text.split(" ")
    if any(part in _TEXT_BOX_UNSUPPORTED_EDGES for part in parts):
        raise _Invalid("text-box-edge is unsupported")
    if len(parts) == 1 and parts[0] in _TEXT_BOX_DOUBLED:
        return (parts[0], parts[0])
    if len(parts) == 2 and parts[0] in _TEXT_BOX_OVER and parts[1] in _TEXT_BOX_UNDER:
        return (parts[0], parts[1])
    raise _Invalid("text-box-edge is invalid")


def _over_metric_inset(font_size: int, edge: str) -> int:
    """Pixels of the em above the named over edge.

    Cap-height is seven tenths of the em. X-height is half an em. Both are
    synthetic: this engine cannot read a font file, and half an em is the
    CSS ``ex`` fallback.
    """

    if edge == "text":
        return 0
    if edge == "cap":
        return font_size - (font_size * 7 // 10)
    if edge == "ex":
        return font_size - (font_size // 2)
    raise _Invalid("text-box-edge is unsupported")


def _under_metric_inset(edge: str) -> int:
    """Pixels below the alphabetic baseline inside the em. Descent is zero."""

    if edge in {"text", "alphabetic"}:
        return 0
    raise _Invalid("text-box-edge is unsupported")


def _skips_contents(box: _Box) -> bool:
    return box.capture.get("content_visibility") == "hidden"


def _reject_skipped_box(box: _Box) -> None:
    """``hidden`` applies only to a horizontal static block or flow-root."""

    if not _skips_contents(box):
        return
    if box.writing_mode != "horizontal-tb" or box.direction != "ltr":
        raise _Invalid("content-visibility writing mode is unsupported")
    if box.display not in {"block", "flow-root"} or box.list_item or box.replaced:
        raise _Invalid("content-visibility display is unsupported")
    if box.position != "static" or box.float_side != "none":
        raise _Invalid("content-visibility position is unsupported")
    if box.multicol is not None:
        raise _Invalid("content-visibility columns are unsupported")
    if box.aspect_ratio is not None:
        raise _Invalid("content-visibility aspect ratio is unsupported")


def _read_intrinsic_block(winners, custom: dict) -> int | None:
    longhand = _declared(winners, "contain-intrinsic-block-size", custom)
    if longhand is not None:
        return _intrinsic_block_length(longhand, "contain-intrinsic-block-size")
    shorthand = _declared(winners, "contain-intrinsic-size", custom)
    if shorthand is None:
        return None
    return _intrinsic_size_block(shorthand)


def _intrinsic_block_length(value: str, name: str) -> int | None:
    token = " ".join(value.strip().lower().split())
    if token in {"none", "initial", "unset", "revert"}:
        return None
    if token == "inherit" or token == "auto" or token.startswith("auto "):
        raise _Invalid(f"{name} is invalid")
    return _nonnegative_px(token, name)


def _intrinsic_size_block(value: str) -> int | None:
    name = "contain-intrinsic-size"
    token = " ".join(value.strip().lower().split())
    if token in {"none", "initial", "unset", "revert"}:
        return None
    if token == "inherit" or "auto" in token.split(" "):
        raise _Invalid(f"{name} is invalid")
    parts = token.split(" ")
    if len(parts) > 2:
        raise _Invalid(f"{name} is invalid")
    lengths = [_nonnegative_px(part, name) for part in parts]
    return lengths[-1]


def _nonnegative_px(token: str, name: str) -> int:
    if not token.endswith("px"):
        raise _Invalid(f"{name} is invalid")
    try:
        number = _px(float(token[:-2]), name)
    except (TypeError, ValueError) as exc:
        raise _Invalid(f"{name} is invalid") from exc
    if number < 0:
        raise _Invalid(f"{name} is invalid")
    return number


def _clear_skipped_ink(box: _Box) -> None:
    box.lines = []
    box.drop_cap = None
    box.marker = None
    for child in (*box.children, *box.floats, *box.atoms, *box.positioned):
        _clear_skipped_ink(child)


def _seal_skipped_contents(box: _Box) -> None:
    """Size a skipped box as if empty, after its contents have been measured."""

    if _skips_contents(box) and box.solved:
        if box.solved.get("content_height") == "auto":
            box.definite_height = 0 if box.intrinsic_block is None else box.intrinsic_block
        elif box.definite_height is None:
            raise _Invalid("content-visibility size is unsupported")
        _clear_skipped_ink(box)
    for child in (*box.children, *box.floats, *box.atoms, *box.positioned):
        _seal_skipped_contents(child)


def _collapse_spec(box: _Box) -> dict[str, object]:
    solved = box.solved
    minimum, maximum = _used_block_limits(box)
    display = box.display if box.display in {"inline-block", "flow-root"} else "block"
    if display == "block" and box.align_mode != "normal":
        display = "flow-root"
    trim_start, trim_end = _margin_trim_flags(box)
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
        "display": display,
        "clearance": False,
        "trim_block_start": trim_start,
        "trim_block_end": trim_end,
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
    box.border_width = (
        box.content_width + box.gutter_start + box.gutter_end + _edge_extent(box.solved, "left", "right")
    )
    if box.content_height < 0:
        raise _Invalid("content height is invalid")
    content_x, content_y = _position_lines(box)
    for atom in box.atoms:
        _place_inline_atom(atom, content_x, content_y)
    for fl in box.floats:
        if not fl.float_placed:
            continue
        fl.y = content_y + fl.local_y
        _position_lines(fl)
        if fl.children:
            _position_float_children(fl)
    for child in box.children:
        _assign_y(child, by_id, origin, box.y)


_ALIGN_INITIAL = frozenset({"normal", "initial", "unset", "revert"})
_ALIGN_POSITION = {"start": "start", "flex-start": "start", "end": "end", "flex-end": "end", "center": "center"}
_ALIGN_FALLBACK = {
    "space-between": "start",
    "stretch": "start",
    "space-around": "center",
    "space-evenly": "center",
}


def _block_align_mode(display: str, value: str | None) -> tuple[str, bool]:
    """Computed ``align-content`` for a block container.

    CSS Align 3 packs the whole contents as one subject. Distribution values
    therefore use their safe fallback, and a block that is not a scroll
    container defaults to safe overflow. Other displays keep the initial value
    because flex, grid, and multicol already pack their own subjects.
    """

    if display not in {"block", "flow-root"}:
        return "normal", True
    if value is None:
        return "normal", True
    tokens = [token.lower() for token in value.split()]
    if len(tokens) == 1 and tokens[0] in _ALIGN_INITIAL:
        return "normal", True
    if tokens == ["inherit"]:
        raise _Invalid("align-content inherit is unsupported")
    explicit_safety = False
    safe = True
    if tokens and tokens[0] in {"safe", "unsafe"}:
        if len(tokens) != 2:
            raise _Invalid("align-content is invalid")
        explicit_safety = True
        safe = tokens[0] == "safe"
        tokens = tokens[1:]
    if len(tokens) != 1:
        raise _Invalid("align-content is invalid")
    token = tokens[0]
    if token in _ALIGN_FALLBACK:
        if explicit_safety:
            raise _Invalid("align-content is invalid")
        return _ALIGN_FALLBACK[token], True
    if token in _ALIGN_POSITION:
        return _ALIGN_POSITION[token], safe
    if "baseline" in token:
        raise _Invalid("align-content baseline is unsupported")
    raise _Invalid("align-content is invalid")


def _pack_block_align(box: _Box) -> None:
    """Slide each block's content unit after static positions are known."""

    for child in box.children:
        _pack_block_align(child)
    for fl in box.floats:
        if fl.float_placed:
            _pack_block_align(fl)
    for atom in box.atoms:
        _pack_block_align(atom)
    for abs_box in box.positioned:
        _reject_unpacked_align(abs_box)
    shift = _block_align_shift(box)
    if shift == 0:
        return
    for child in box.children:
        _translate_flow(child, shift)
    for line in box.lines:
        line.y += shift
    if box.marker is not None:
        box.marker["y"] = int(box.marker["y"]) + shift
    if box.drop_cap is not None:
        box.drop_cap["y"] = int(box.drop_cap["y"]) + shift
    for atom in box.atoms:
        _translate_flow(atom, shift)


def _reject_unpacked_align(box: _Box) -> None:
    """Out-of-flow boxes are not packed; a non-normal value stays rejected."""

    if box.align_mode != "normal":
        raise _Invalid("block content alignment is unsupported")
    for child in (*box.children, *box.floats, *box.atoms, *box.positioned):
        _reject_unpacked_align(child)


def _block_align_shift(box: _Box) -> int:
    if box.align_mode == "normal":
        return 0
    if (
        box.display not in {"block", "flow-root"}
        or box.writing_mode != "horizontal-tb"
        or box.direction != "ltr"
        or box.float_side != "none"
        or box.position in {"absolute", "fixed", "sticky"}
        or box.overflow != "visible"
        or box.floats
        or box.positioned
        or box.atoms
        or box.list_item
        or box.initial_letter
        or box.replaced
        or box.multicol is not None
        or box.flex is not None
        or box.grid is not None
        or box.table is not None
        or (box.children and box.lines)
    ):
        raise _Invalid("block content alignment is unsupported")
    content_top = box.y + _edge_extent(box.solved, "top")
    if box.children:
        subject = _block_child_span(box, content_top)
    elif box.lines:
        last = box.lines[-1]
        subject = last.y + last.height - content_top
    else:
        subject = 0
    if subject < 0:
        raise _Invalid("block content alignment is unsupported")
    return _align_offset(box.align_mode, box.align_safe, box.content_height - subject)


def _block_child_span(box: _Box, content_top: int) -> int:
    for child in box.children:
        if child.border_height <= 0 or child.position in {"absolute", "fixed", "sticky"} or child.float_side != "none":
            raise _Invalid("block content alignment is unsupported")
    last = box.children[-1]
    trailing = _px(last.solved.get("margin_bottom"), "margin-bottom")
    return last.y + last.border_height + trailing - content_top


def _align_offset(mode: str, safe: bool, free: int) -> int:
    if free < 0 and safe:
        return 0
    if mode == "start":
        return 0
    if mode == "end":
        return free
    if mode == "center":
        return free // 2
    raise _Invalid("align-content is invalid")


def _translate_flow(box: _Box, dy: int) -> None:
    if dy == 0:
        return
    box.y += dy
    box.flow_y += dy
    for line in box.lines:
        line.y += dy
    if box.marker is not None:
        box.marker["y"] = int(box.marker["y"]) + dy
    if box.drop_cap is not None:
        box.drop_cap["y"] = int(box.drop_cap["y"]) + dy
    for child in box.children:
        _translate_flow(child, dy)
    for fl in box.floats:
        if fl.float_placed:
            _translate_flow(fl, dy)
    for atom in box.atoms:
        _translate_flow(atom, dy)


def _place_inline_atom(atom: _Box, content_x: int, content_y: int) -> None:
    """Paint an atomic inline and the inline-blocks nested inside it."""

    atom.x = content_x + atom.local_x
    atom.y = content_y + atom.local_y
    nested_x, nested_y = _position_lines(atom)
    for child in atom.atoms:
        _place_inline_atom(child, nested_x, nested_y)
    if atom.children:
        _position_float_children(atom)
    if atom.floats:
        _position_atom_floats(atom)


def _position_lines(box: _Box) -> tuple[int, int]:
    x = box.x + _edge_extent(box.solved, "left") + box.gutter_start
    y = box.y + _edge_extent(box.solved, "top")
    for line in box.lines:
        line.x += x
        line.y += y
    if box.drop_cap is not None:
        box.drop_cap["x"] = int(box.drop_cap["x"]) + x
        box.drop_cap["y"] = int(box.drop_cap["y"]) + y
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
    if box.offset_angle is not None:
        item["offset_angle"] = box.offset_angle
    if box.scroll_opacity is not None:
        item["opacity"] = box.scroll_opacity
    if box.outline is not None:
        item["outline"] = _outline_ink(box)
    if box.shadows:
        item["shadows"] = _shadow_ink(box)
    if box.column_rules:
        origin_x = box.x + _edge_extent(box.solved, "left") + box.gutter_start
        origin_y = box.y + _edge_extent(box.solved, "top")
        item["rules"] = [
            {
                "x": origin_x + left,
                "y": origin_y + top,
                "width": width,
                "height": height,
                "style": style,
                "color": color,
            }
            for left, top, width, height, style, color in box.column_rules
        ]
    if box.snap is not None:
        item["snap"] = box.snap
    if box.object_box is not None:
        item["object"] = box.object_box
    if box.marker is not None:
        item["marker"] = {
            "text": box.marker["text"],
            "x": box.marker["x"],
            "y": box.marker["y"],
            "width": box.marker["width"],
        }
    if box.drop_cap is not None:
        item["initial_letter"] = {
            "text": box.drop_cap["text"],
            "x": box.drop_cap["x"],
            "y": box.drop_cap["y"],
            "width": box.drop_cap["width"],
            "height": box.drop_cap["height"],
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
            if "font_face" in run:
                recorded["font_face"] = run["font_face"]
            if "y" in run:
                recorded["y"] = line.y + int(run["y"])
            if "height" in run:
                recorded["height"] = int(run["height"])
            recorded_runs.append(recorded)
        item["runs"] = recorded_runs
    if line.combines:
        item["combines"] = [
            {
                "text": str(cluster["text"]),
                "x": line.x + int(cluster["x"]),
                "y": line.y + int(cluster["y"]),
                "width": int(cluster["width"]),
                "height": int(cluster["height"]),
                "glyphs": [
                    {
                        "text": str(glyph["text"]),
                        "x": line.x + int(glyph["x"]),
                        "y": line.y + int(glyph["y"]),
                        "width": int(glyph["width"]),
                        "height": int(glyph["height"]),
                    }
                    for glyph in cluster["glyphs"]
                ],
            }
            for cluster in line.combines
        ]
    if line.emphasis:
        item["baseline"] = line.baseline
        item["emphasis"] = [
            {
                "text": str(mark["text"]),
                "x": line.x + int(mark["x"]),
                "y": line.y + int(mark["y"]),
                "width": int(mark["width"]),
                "height": int(mark["height"]),
                "color": str(mark["color"]),
            }
            for mark in line.emphasis
        ]
    if line.decorations:
        item["decorations"] = [
            {
                "kind": str(mark["kind"]),
                "x": line.x + int(mark["x"]),
                "y": line.y + int(mark["y"]),
                "width": int(mark["width"]),
                "owner": str(mark["owner"]),
                "font_size": int(mark["font_size"]),
            }
            for mark in line.decorations
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


def _read_font_family(value: str | None, parent: str) -> str:
    """Computed family list. An omitted family does not name a face."""

    if value is None:
        return parent
    token = " ".join(value.split())
    lowered = token.lower()
    if lowered in {"inherit", "unset", "revert"}:
        return parent
    if lowered == "initial":
        return ""
    names: list[str] = []
    for part in token.split(","):
        name = part.strip()
        if len(name) >= 2 and name[0] == name[-1] and name[0] in {'"', "'"}:
            name = name[1:-1].strip()
        if not name:
            raise _Invalid("font-family is invalid")
        names.append(name)
    return ", ".join(names)


def _read_font_weight(value: str | None, parent: str) -> str:
    if value is None:
        return parent
    token = " ".join(value.strip().lower().split())
    if token in {"inherit", "unset", "revert"}:
        return parent
    if token == "initial":
        return "400"
    try:
        number = _requested_weight(token, parent)
    except _FontInvalid as exc:
        raise _Invalid("font-weight is invalid") from exc
    if abs(number - round(number)) <= 1e-9:
        return str(int(round(number)))
    return format(number, ".12g")


def _read_font_style(value: str | None, parent: str) -> str:
    if value is None:
        return parent
    token = " ".join(value.strip().lower().split())
    if token in {"inherit", "unset", "revert"}:
        return parent
    if token == "initial":
        return "normal"
    try:
        kind, angle = _requested_style(token)
    except _FontInvalid as exc:
        raise _Invalid("font-style is invalid") from exc
    if kind != "oblique" or angle is None:
        return kind
    shown = int(angle) if abs(angle - round(angle)) <= 1e-9 else angle
    return f"oblique {shown}deg"


def _stamp_font_faces(root: _Box, faces: tuple[dict[str, object], ...]) -> None:
    if not faces:
        return
    for box in _each(root):
        if not box.font_family:
            continue
        for line in box.lines:
            _stamp_line_faces(box, line, faces)


def _stamp_line_faces(box: _Box, line: _Line, faces: tuple[dict[str, object], ...]) -> None:
    if line.runs:
        stamped: list[dict[str, object]] = []
        for run in line.runs:
            stamped.extend(_split_run_faces(box, run, faces))
        line.runs = stamped
        return
    if not line.text:
        return
    segments = _font_segments(box, line.text, faces)
    cursor = 0
    runs: list[dict[str, object]] = []
    for segment in segments:
        part = str(segment.get("text") or "")
        width = sum(_advance_of(character, box.font_size) for character in part)
        runs.append(
            {
                "text": part,
                "x": cursor,
                "font_size": box.font_size,
                "width": width,
                "font_face": segment.get("id"),
            }
        )
        cursor += width
    line.runs = runs


def _split_run_faces(
    box: _Box, run: dict[str, object], faces: tuple[dict[str, object], ...]
) -> list[dict[str, object]]:
    text = str(run.get("text") or "")
    segments = _font_segments(box, text, faces)
    if len(segments) <= 1:
        if segments:
            run["font_face"] = segments[0].get("id")
        return [run]
    font_size = int(run.get("font_size") or box.font_size)
    cursor = int(run.get("x") or 0)
    pieces: list[dict[str, object]] = []
    for segment in segments:
        part = str(segment.get("text") or "")
        width = sum(_advance_of(character, font_size) for character in part)
        item: dict[str, object] = {
            "text": part,
            "x": cursor,
            "font_size": font_size,
            "width": width,
            "font_face": segment.get("id"),
        }
        if "y" in run:
            item["y"] = run["y"]
        pieces.append(item)
        cursor += width
    return pieces


def _font_segments(
    box: _Box, text: str, faces: tuple[dict[str, object], ...]
) -> list[dict[str, object]]:
    if text == "":
        return []
    result = select_font_face(
        box.font_family,
        list(faces),
        text,
        weight=box.font_weight,
        style=box.font_style,
    )
    if result.get("outcome") == "invalid":
        raise _Invalid(str(result.get("reason") or "font face is invalid"))
    segments = result.get("segments")
    if not isinstance(segments, list) or not segments:
        raise _Invalid("font face is invalid")
    chosen = [item for item in segments if isinstance(item, dict)]
    if "".join(str(item.get("text") or "") for item in chosen) != text:
        raise _Invalid("font face is invalid")
    return chosen


def _fonts(box: _Box) -> dict[str, str]:
    return {
        "font-size": f"{box.font_size}px",
        "line-height": box.line_height,
        "text-align": box.text_align,
        "text-align-last": box.text_align_last,
        "text-justify": box.text_justify,
        "text-indent": box.text_indent,
        "letter-spacing": f"{box.letter_spacing}px",
        "word-spacing": f"{box.word_spacing}px",
        "text-autospace": box.text_autospace,
        "text-transform": box.text_transform,
        "tab-size": box.tab_size,
        "white-space": box.white_space,
        "overflow-wrap": box.overflow_wrap,
        "word-break": box.word_break,
        "hyphens": box.hyphens,
        "hyphenate-character": box.hyphenate_character,
        "lang": box.lang,
        "hanging-punctuation": box.hanging_punctuation,
        "widows": "" if box.widows is None else str(box.widows),
        "orphans": "" if box.orphans is None else str(box.orphans),
        "text-wrap-style": box.text_wrap_style,
        "list-style-type": box.list_style_type,
        "list-style-position": box.list_style_position,
        "font-family": box.font_family,
        "font-weight": box.font_weight,
        "font-style": box.font_style,
        "color": box.color,
        "color-valid": "1" if box.color_valid else "0",
        "text-emphasis-mark": box.emphasis_mark,
        "text-emphasis-position": box.emphasis_position,
    }


def _set_inline(
    box: _Box, tree, element, styles, declarations, ids: set[str], counter: list[int]
) -> None:
    box.counters_closed = True
    if box.ruby:
        _bind_ruby(box, tree, element, styles, declarations)
        pair = box.ruby_pair if isinstance(box.ruby_pair, dict) else {}
        box.pieces = []
        box.inline_text = str(pair.get("base") or "")
        box.nowrap_ranges = ()
        return
    if box.flex is not None and box.display == "flex":
        return
    if box.display == "inline-block" and _inline_block_anonymous_ready(box) and (box.children or box.floats):
        _wrap_anonymous_blocks(box, tree, element, styles, declarations, ids, counter)
        return
    if box.children and not _anonymous_split_allowed(box):
        if box.atoms:
            raise _Invalid("inline-block beside blocks is unsupported")
        return
    if box.children:
        _wrap_anonymous_blocks(box, tree, element, styles, declarations, ids, counter)
        return
    segments = _inline_segments(
        tree, element, styles, declarations, _fonts(box), box.atoms, box.relative_layers
    )
    pieces: list[_Piece] | None = []
    for kind, run, _ in segments:
        if kind == "block":
            pieces = None
            break
        pieces = run
    if pieces is None and box.atoms:
        raise _Invalid("inline-block beside blocks is unsupported")
    box.pieces = pieces or []
    box.inline_text = None if pieces is None else "".join(piece.text for piece in pieces)
    box.nowrap_ranges = _nowrap_ranges(box.pieces)
    box.clone_ranges = box.pieces[0].clone_ranges if box.pieces else ()
    if _glyph_chrome(box) and (box.writing_mode != "horizontal-tb" or box.direction != "ltr"):
        raise _Invalid("inline chrome is unsupported")
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
        and _block_container(box)
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
        letter_spacing=parent.letter_spacing,
        word_spacing=parent.word_spacing,
        text_transform=parent.text_transform,
        tab_size=parent.tab_size,
        white_space=parent.white_space,
        overflow_wrap=parent.overflow_wrap,
        word_break=parent.word_break,
        hyphens=parent.hyphens,
        hyphenate_character=parent.hyphenate_character,
        lang=parent.lang,
        hanging_punctuation=parent.hanging_punctuation,
        text_wrap_style=parent.text_wrap_style,
        font_family=parent.font_family,
        font_weight=parent.font_weight,
        font_style=parent.font_style,
        parent_direction=parent.direction,
        color=parent.color,
        color_valid=parent.color_valid,
        emphasis_mark=parent.emphasis_mark,
        emphasis_position=parent.emphasis_position,
        anonymous=True,
        parent_box=parent,
        pieces=pieces,
        atoms=atoms,
        inline_text="".join(piece.text for piece in pieces),
        nowrap_ranges=_nowrap_ranges(pieces),
        clone_ranges=pieces[0].clone_ranges if pieces else (),
    )
    return anon


def _anonymous_id(ids: set[str], counter: list[int]) -> str:
    while True:
        counter[0] += 1
        box_id = f"anon-{counter[0]}"
        if box_id not in ids:
            ids.add(box_id)
            return box_id


def _read_text_combine(tree, element, styles, declarations) -> tuple[str, int] | None:
    """Specified ``text-combine-upright``. ``None`` means the property does nothing."""

    custom = styles.get(element, ({}, ""))[0]
    raw = _declared(_winners(tree, element, declarations), "text-combine-upright", custom)
    if raw is None:
        return None
    token = " ".join(raw.strip().lower().split())
    if token in {"none", "initial", "unset", "revert"}:
        return None
    if token == "inherit":
        raise _Invalid("text-combine-upright inherit is unsupported")
    if token == "all":
        return ("all", 0)
    if token == "digits":
        return ("digits", 2)
    parts = token.split(" ")
    if len(parts) == 2 and parts[0] == "digits" and parts[1].isdigit() and parts[1][0] != "0":
        count = int(parts[1])
        if 2 <= count <= 4:
            return ("digits", count)
    raise _Invalid("text-combine-upright is invalid")


def _combine_spans(text: str, mode: tuple[str, int]) -> tuple[tuple[int, int], ...]:
    """Half-open ranges that share one em. A single character already does."""

    if any(character.isspace() for character in text):
        raise _Invalid("text-combine white space is unsupported")
    kind, limit = mode
    if kind == "all":
        return ((0, len(text)),) if len(text) >= 2 else ()
    spans: list[tuple[int, int]] = []
    index = 0
    count = len(text)
    while index < count:
        if "0" <= text[index] <= "9":
            start = index
            index += 1
            while index < count and "0" <= text[index] <= "9":
                index += 1
            length = index - start
            while length >= 2:
                take = min(limit, length)
                spans.append((start, start + take))
                start += take
                length -= take
            continue
        index += 1
    return tuple(spans)


def _stamp_text_combine(pieces: list[_Piece], added: int, mode: tuple[str, int]) -> None:
    if len(pieces) == added:
        return
    if len(pieces) != added + 1:
        raise _Invalid("text-combine content is unsupported")
    piece = pieces[-1]
    piece.combine = _combine_spans(piece.text, mode)


def _inline_segments(
    tree,
    element,
    styles,
    declarations,
    fonts: dict[str, str],
    atoms: list[_Box],
    layers_of: dict[int, _Shift],
    float_ids: set[int] | None = None,
) -> Iterator[tuple[str, list[_Piece], list[_Box]]]:
    """Split one element's inline stream on its in-flow block children.

    A float in ``float_ids`` is its own marker, so the text before that float
    and the text after it become different anonymous blocks.
    """

    floats = float_ids or set()
    stream = iter(atoms)
    pieces: list[_Piece] = []
    used: list[_Box] = []
    piece_length = 0
    block_size = _positive_px(fonts["font-size"], "font-size")
    block_leading = fonts["line-height"]
    transform_mode = {"value": fonts.get("text-transform", "none")}
    pending_clones: list[tuple[int, int, int, int]] = []
    segment_epoch = 0

    def flush() -> Iterator[tuple[str, list[_Piece], list[_Box]]]:
        nonlocal pieces, used, piece_length, segment_epoch
        if pieces or used:
            if pending_clones:
                if not pieces:
                    raise _Invalid("box-decoration-break is unsupported")
                pieces[0].clone_ranges = tuple(pending_clones)
                pending_clones.clear()
            yield "inline", pieces, used
            pieces = []
            used = []
            piece_length = 0
            segment_epoch += 1

    def add(
        text: str,
        size: int,
        leading: str,
        layers: tuple[_Shift, ...],
        align: str | int,
        nowrap: bool = False,
        origin: tuple[Element, bool] | None = None,
        marks: tuple[tuple[str, int, str], ...] = (),
    ) -> None:
        nonlocal piece_length
        text = _transform_text(text, transform_mode["value"])
        if not text:
            return
        if layers and (size != block_size or leading != block_leading or align != "baseline"):
            raise _Invalid("relative inline font is unsupported")
        piece_length += len(text)
        pieces.append(
            _Piece(
                text,
                size,
                leading,
                shifts=layers,
                extra=[0] * len(text),
                vertical_align=align,
                nowrap=nowrap,
                origin=origin,
                marks=marks,
            )
        )

    def walk(
        node,
        parent_fonts: dict[str, str],
        inherited: tuple[_Shift, ...],
        align: str | int = "baseline",
        nowrap: bool = False,
        inherited_marks: tuple[tuple[str, int, str], ...] = (),
    ) -> Iterator[tuple[str, list[_Piece], list[_Box]]]:
        previous_transform = transform_mode["value"]
        transform_mode["value"] = parent_fonts.get("text-transform", "none")
        own = layers_of.get(id(node))
        layers = inherited + ((own,) if own is not None else ())
        size = _positive_px(parent_fonts["font-size"], "font-size")
        leading = parent_fonts["line-height"]
        here = inherited_marks + _element_marks(tree, node, styles, declarations, size)
        before, after = _generated(tree, node)
        combine = _read_text_combine(tree, node, styles, declarations)
        if combine is not None:
            if any(_local_name(child) for child in list(node)):
                raise _Invalid("text-combine content is unsupported")
            if before or after:
                raise _Invalid("text-combine content is unsupported")
        _add_own_generated(add, tree, node, "before", before, size, leading, layers, align, nowrap, here)
        added = len(pieces)
        add(node.text or "", size, leading, layers, align, nowrap, (node, False), here)
        if combine is not None:
            _stamp_text_combine(pieces, added, combine)
        for child in list(node):
            if not _local_name(child):
                continue
            kind = _flow_kind(tree, child, styles, declarations)
            if id(child) in floats or kind == "block":
                yield from flush()
                yield ("float" if id(child) in floats else "block"), [], []
            elif kind == "contents":
                held = nowrap or _inline_declares_nowrap(
                    tree, child, styles, declarations, parent_fonts
                )
                yield from walk(
                    child,
                    _inline_fonts(tree, child, styles, declarations, parent_fonts),
                    layers,
                    align,
                    held,
                    here,
                )
            elif kind == "inline-block":
                if layers:
                    raise _Invalid("relative inline content is unsupported")
                if align != "baseline":
                    raise _Invalid("vertical-align beside an inline-block is unsupported")
                try:
                    atom = next(stream)
                except StopIteration as exc:
                    raise _Invalid("inline-block is unsupported") from exc
                pieces.append(_Piece("", size, leading, atom))
                used.append(atom)
            elif kind not in {"skip", "out"}:
                _reject_inline_type(tree, child, styles, declarations, parent_fonts)
                held = nowrap or _inline_declares_nowrap(tree, child, styles, declarations, parent_fonts)
                decoration = _read_box_decoration_break(tree, child, styles, declarations)
                lead, trail = _inline_horizontal_chrome(tree, child, styles, declarations)
                epoch = segment_epoch
                start = piece_length
                child_fonts = _inline_fonts(tree, child, styles, declarations, parent_fonts)
                child_align = _nest_align(
                    align,
                    _used_text_align(
                        tree, child, styles, declarations, child_fonts, size
                    ),
                )
                yield from walk(child, child_fonts, layers, child_align, held, here)
                _remember_inline_chrome(pieces, start, piece_length, lead, trail)
                if decoration == "clone" and (lead or trail):
                    if epoch != segment_epoch or piece_length <= start:
                        raise _Invalid("box-decoration-break is unsupported")
                    pending_clones.append((start, piece_length, lead, trail))
            add(child.tail or "", size, leading, layers, align, nowrap, (child, True), here)
        _add_own_generated(add, tree, node, "after", after, size, leading, layers, align, nowrap, here)
        transform_mode["value"] = previous_transform

    yield from walk(element, fonts, ())
    if next(stream, None) is not None:
        raise _Invalid("inline-block is unsupported")
    yield from flush()


def _element_marks(tree, element, styles, declarations, font_size: int) -> tuple[tuple[str, int, str], ...]:
    """Lines this element paints. Ancestors are kept by the caller."""

    custom = styles.get(element, ({}, ""))[0]
    winners = _winners(tree, element, declarations)
    shorthand = _declared(winners, "text-decoration", custom)
    longhand = _declared(winners, "text-decoration-line", custom)
    if shorthand is not None and longhand is not None:
        raise _Invalid("text-decoration is invalid")
    try:
        kinds = parse_text_decoration(shorthand if shorthand is not None else longhand)
    except DecorationError as exc:
        raise _Invalid(exc.reason) from exc
    if not kinds:
        return ()
    owner = (_attr(element, "id") or "").strip() or (_local_name(element) or "")
    return tuple((kind, font_size, owner) for kind in kinds)


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
        "hyphens": parent.get("hyphens", "manual"),
        "hyphenate-character": parent.get("hyphenate-character", "\u2010"),
        "lang": parent.get("lang", ""),
        "text-transform": parent.get("text-transform", "none"),
    }


_CHROME_PROPS = frozenset(
    {
        "margin",
        "margin-left",
        "margin-right",
        "padding",
        "padding-left",
        "padding-right",
        "border",
        "border-left",
        "border-right",
        "border-width",
        "border-left-width",
        "border-right-width",
        "border-style",
        "border-left-style",
        "border-right-style",
    }
)
_BORDER_STYLES = frozenset(
    {"none", "hidden", "dotted", "dashed", "solid", "double", "groove", "ridge", "inset", "outset"}
)
_BORDER_WIDTHS = {"thin": 1, "medium": 3, "thick": 5}


def _glyph_chrome(box: _Box) -> bool:
    return any(any(piece.extra) for piece in box.pieces if piece.text)


def _extra_stream(pieces: list[_Piece], count: int) -> list[int]:
    extras: list[int] = []
    for piece in pieces:
        if not piece.text:
            continue
        if len(piece.extra) != len(piece.text):
            extras.extend([0] * len(piece.text))
        else:
            extras.extend(piece.extra)
    if len(extras) != count:
        raise _Invalid("inline chrome is invalid")
    return extras


def _remember_inline_chrome(pieces: list[_Piece], start: int, end: int, lead: int, trail: int) -> None:
    if lead == 0 and trail == 0:
        return
    if end <= start:
        raise _Invalid("empty inline chrome is unsupported")
    seen = 0
    first: tuple[_Piece, int] | None = None
    last: tuple[_Piece, int] | None = None
    for piece in pieces:
        for index in range(len(piece.text)):
            if start <= seen < end:
                if first is None:
                    first = (piece, index)
                last = (piece, index)
            seen += 1
    if first is None or last is None:
        raise _Invalid("empty inline chrome is unsupported")
    for piece, index, amount in ((first[0], first[1], lead), (last[0], last[1], trail)):
        if len(piece.extra) != len(piece.text):
            piece.extra = [0] * len(piece.text)
        piece.extra[index] += amount


def _reject_glyph_chrome(box: _Box) -> None:
    if not _glyph_chrome(box):
        return
    if box.writing_mode != "horizontal-tb" or box.direction != "ltr" or box.white_space != "normal":
        raise _Invalid("inline chrome is unsupported")
    if box.letter_spacing or box.word_spacing or _gap_alignment(box):
        raise _Invalid("inline chrome is unsupported")
    if box.floats or box.atoms or _mixed_runs(box) or _relative_pieces(box) or box.list_item:
        raise _Invalid("inline chrome is unsupported")
    if box.text_indent != "0px" or box.text_wrap_style in {"balance", "pretty"} or box.line_clamp is not None:
        raise _Invalid("inline chrome is unsupported")
    if box.hanging_punctuation != "none":
        raise _Invalid("inline chrome is unsupported")


def _read_box_decoration_break(tree, element, styles, declarations) -> str:
    """``slice`` keeps one pair of edges. ``clone`` repeats them on every fragment."""

    custom = styles.get(element, ({}, ""))[0]
    raw = _declared(_winners(tree, element, declarations), "box-decoration-break", custom)
    if raw is None:
        return "slice"
    text = " ".join(raw.split()).lower()
    if text in {"slice", "initial", "unset", "revert"}:
        return "slice"
    if text == "clone":
        return "clone"
    if text in {"inherit", "revert-layer"}:
        raise _Invalid("box-decoration-break is unsupported")
    raise _Invalid("box-decoration-break is invalid")


def _inline_horizontal_chrome(tree, element, styles, declarations) -> tuple[int, int]:
    custom = styles.get(element, ({}, ""))[0]
    winners = _winners(tree, element, declarations)
    if not any(prop in _CHROME_PROPS for _order, prop, _value in winners):
        return 0, 0
    pad = {"left": 0, "right": 0}
    margin = {"left": 0, "right": 0}
    width: dict[str, str | None] = {"left": None, "right": None}
    style = {"left": "none", "right": "none"}
    for _order, prop, raw in winners:
        if prop not in _CHROME_PROPS:
            continue
        value = _declared([(_order, prop, raw)], prop, custom)
        if value is None:
            continue
        text = " ".join(value.split()).lower()
        if prop in {"margin", "margin-left", "margin-right"}:
            _apply_margin(prop, text, margin)
        elif prop in {"padding", "padding-left", "padding-right"}:
            _apply_padding(prop, text, pad)
        elif prop in {"border-left-style", "border-right-style", "border-style"}:
            _apply_border_style(prop, text, style)
        elif prop in {"border-left-width", "border-right-width", "border-width"}:
            _apply_border_width(prop, text, width)
        elif prop in {"border", "border-left", "border-right"}:
            _apply_border_shorthand(prop, text, width, style)
    lead = margin["left"] + pad["left"] + _used_inline_border(width["left"], style["left"])
    trail = margin["right"] + pad["right"] + _used_inline_border(width["right"], style["right"])
    return lead, trail


def _chrome_keyword(text: str, name: str) -> bool:
    if text in {"inherit", "revert", "revert-layer"}:
        raise _Invalid(f"inline {name} is unsupported")
    return text in {"initial", "unset"}


def _quad_parts(parts: list[str], name: str) -> tuple[str, str, str, str]:
    if len(parts) == 1:
        return (parts[0], parts[0], parts[0], parts[0])
    if len(parts) == 2:
        return (parts[0], parts[1], parts[0], parts[1])
    if len(parts) == 3:
        return (parts[0], parts[1], parts[2], parts[1])
    if len(parts) == 4:
        return (parts[0], parts[1], parts[2], parts[3])
    raise _Invalid(f"inline {name} is invalid")


def _edge_px(token: str, *, negative: bool, name: str) -> int:
    text = token.strip().lower()
    if text in {"0", "0px"}:
        return 0
    if text == "auto" and name == "margin":
        return 0
    if text.endswith("%") or text.endswith("em") or text.endswith("rem") or "calc(" in text:
        raise _Invalid(f"inline {name} is unsupported")
    if not text.endswith("px"):
        raise _Invalid(f"inline {name} is invalid")
    try:
        number = float(text[:-2])
    except ValueError as exc:
        raise _Invalid(f"inline {name} is invalid") from exc
    px = _px(number, name)
    if px < 0:
        if negative:
            raise _Invalid(f"inline {name} is unsupported")
        raise _Invalid(f"inline {name} is invalid")
    return px


def _apply_margin(prop: str, text: str, margin: dict[str, int]) -> None:
    if _chrome_keyword(text, "margin"):
        if prop == "margin":
            margin["left"] = margin["right"] = 0
        else:
            margin["left" if prop == "margin-left" else "right"] = 0
        return
    if prop == "margin":
        left, right = _horizontal_lengths(text, negative=True, name="margin")
        margin["left"], margin["right"] = left, right
        return
    side = "left" if prop == "margin-left" else "right"
    margin[side] = _edge_px(text, negative=True, name="margin")


def _apply_padding(prop: str, text: str, pad: dict[str, int]) -> None:
    if _chrome_keyword(text, "padding"):
        if prop == "padding":
            pad["left"] = pad["right"] = 0
        else:
            pad["left" if prop == "padding-left" else "right"] = 0
        return
    if prop == "padding":
        left, right = _horizontal_lengths(text, negative=False, name="padding")
        pad["left"], pad["right"] = left, right
        return
    side = "left" if prop == "padding-left" else "right"
    pad[side] = _edge_px(text, negative=False, name="padding")


def _horizontal_lengths(text: str, *, negative: bool, name: str) -> tuple[int, int]:
    quad = _quad_parts(text.split(" "), name)
    _edge_px(quad[0], negative=negative, name=name)
    _edge_px(quad[2], negative=negative, name=name)
    return _edge_px(quad[3], negative=negative, name=name), _edge_px(quad[1], negative=negative, name=name)


def _apply_border_style(prop: str, text: str, style: dict[str, str]) -> None:
    if _chrome_keyword(text, "border"):
        style["left"] = style["right"] = "none"
        return
    if prop == "border-style":
        quad = _quad_parts(text.split(" "), "border")
        for token in quad:
            if token not in _BORDER_STYLES:
                raise _Invalid("inline border is invalid")
        style["right"] = quad[1]
        style["left"] = quad[3]
        return
    side = "left" if prop == "border-left-style" else "right"
    if text not in _BORDER_STYLES:
        raise _Invalid("inline border is invalid")
    style[side] = text


def _width_token(token: str) -> str:
    text = token.strip().lower()
    if text in _BORDER_WIDTHS or text in {"0", "0px"}:
        return text
    if text.endswith("%") or text.endswith("em") or "calc(" in text:
        raise _Invalid("inline border is unsupported")
    if not text.endswith("px"):
        raise _Invalid("inline border is invalid")
    _edge_px(text, negative=False, name="border")
    return text


def _apply_border_width(prop: str, text: str, width: dict[str, str | None]) -> None:
    if _chrome_keyword(text, "border"):
        width["left"] = width["right"] = None
        return
    if prop == "border-width":
        quad = _quad_parts(text.split(" "), "border")
        width["right"] = _width_token(quad[1])
        width["left"] = _width_token(quad[3])
        _width_token(quad[0])
        _width_token(quad[2])
        return
    side = "left" if prop == "border-left-width" else "right"
    width[side] = _width_token(text)


def _consume_border(text: str) -> tuple[str | None, str | None]:
    width = None
    style = None
    for part in text.split(" "):
        if style is None and part in _BORDER_STYLES:
            style = part
            continue
        if width is None and (part in _BORDER_WIDTHS or part.endswith("px") or part in {"0", "0px"} or part.endswith("%")):
            width = _width_token(part)
            continue
    return width, style


def _apply_border_shorthand(prop: str, text: str, width: dict[str, str | None], style: dict[str, str]) -> None:
    if _chrome_keyword(text, "border"):
        width["left"] = width["right"] = None
        style["left"] = style["right"] = "none"
        return
    chosen, border_style = _consume_border(text)
    sides = ("left", "right") if prop == "border" else (("left",) if prop == "border-left" else ("right",))
    for side in sides:
        width[side] = chosen
        style[side] = border_style or "none"


def _used_inline_border(width: str | None, style: str) -> int:
    if style in {"none", "hidden"}:
        return 0
    if width is None or width == "medium":
        return 3
    if width == "thin":
        return 1
    if width == "thick":
        return 5
    if width in {"0", "0px"}:
        return 0
    return _edge_px(width, negative=False, name="border")


def _flow_kind(tree, element, styles, declarations) -> str:
    if _local_name(element) in _SKIP_TAGS:
        return "skip"
    custom = styles.get(element, ({}, ""))[0]
    winners = _winners(tree, element, declarations)
    raw_display = _declared(winners, "display", custom)
    if _local_name(element) == "ruby" and _ruby_element_display(raw_display):
        return "inline-block"
    display = _keyword(
        raw_display,
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
    if display in {"inline-block", "inline-flex"}:
        return "inline-block"
    return "block"


def _inline_declares_nowrap(tree, element, styles, declarations, parent_fonts: dict[str, str] | None) -> bool:
    """True when this inline itself says nowrap and its parent still collapses normally."""

    if parent_fonts is None or parent_fonts.get("white-space") != "normal":
        return False
    custom = styles.get(element, ({}, ""))[0]
    raw = _declared(_winners(tree, element, declarations), "white-space", custom)
    return raw is not None and raw.strip().lower() == "nowrap"


def _nowrap_ranges(pieces: list[_Piece]) -> tuple[tuple[int, int], ...]:
    ranges: list[tuple[int, int]] = []
    cursor = 0
    for piece in pieces:
        end = cursor + len(piece.text)
        if piece.nowrap and end > cursor:
            if ranges and ranges[-1][1] == cursor:
                ranges[-1] = (ranges[-1][0], end)
            else:
                ranges.append((cursor, end))
        cursor = end
    return tuple(ranges)


def _reject_nowrap_context(box: _Box) -> None:
    """Keep nowrap on the plain horizontal line. Other contexts still refuse it."""

    if not box.nowrap_ranges:
        return
    if (
        box.white_space != "normal"
        or box.writing_mode != "horizontal-tb"
        or box.direction != "ltr"
        or bool(box.atoms)
        or bool(box.floats)
        or box.text_indent != "0px"
        or box.line_clamp is not None
        or _mixed_runs(box)
        or _relative_pieces(box)
        or _gap_alignment(box)
        or any(piece.vertical_align != "baseline" or piece.shifts for piece in box.pieces)
    ):
        raise _Invalid("nowrap inline is unsupported")


def _reject_inline_type(tree, element, styles, declarations, parent_fonts: dict[str, str] | None = None) -> None:
    custom = styles.get(element, ({}, ""))[0]
    winners = _winners(tree, element, declarations)
    for name in _INLINE_REJECTED:
        if _declared(winners, name, custom) is None:
            continue
        if name == "white-space" and _inline_declares_nowrap(
            tree, element, styles, declarations, parent_fonts
        ):
            continue
        raise _Invalid(f"inline {name} is unsupported")
    if parent_fonts is None or parent_fonts.get("hyphens") != "auto":
        return
    raw = _attr(element, "lang")
    if raw is None:
        raw = _attr(element, "xml:lang")
    if raw is None:
        return
    if raw.strip().casefold() != parent_fonts.get("lang", ""):
        raise _Invalid("hyphenation language is unsupported")


def _read_text_indent(value: str | None, parent: str) -> str:
    """Specified indent. A percentage is kept so a child resolves its own block.

    ``hanging`` is stored after the length and inverts which lines move.
    ``each-line`` is stored after that and restarts the choice on each
    preserved newline. Either keyword may be written before the length.
    """

    if value is None or value.strip().lower() in {"inherit", "unset", "revert"}:
        return parent
    if value.strip().lower() == "initial":
        return "0px"
    text = " ".join(value.strip().lower().split())
    hanging = False
    each_line = False
    lengths: list[str] = []
    for part in text.split(" "):
        if part == "hanging":
            if hanging:
                raise _Invalid("text-indent is invalid")
            hanging = True
            continue
        if part == "each-line":
            if each_line:
                raise _Invalid("text-indent is invalid")
            each_line = True
            continue
        lengths.append(part)
    if len(lengths) != 1:
        raise _Invalid("text-indent is unsupported" if " " in text else "text-indent is invalid")
    length = _indent_length(lengths[0])
    if length == "0px" or not (hanging or each_line):
        return length
    suffix = " hanging" if hanging else ""
    if each_line:
        suffix += " each-line"
    return f"{length}{suffix}"


def _indent_length(text: str) -> str:
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


def _text_indent_length(raw: str) -> str:
    while raw.endswith(" each-line"):
        raw = raw[: -len(" each-line")]
    if raw.endswith(" hanging"):
        return raw[: -len(" hanging")]
    return raw


def _text_indent_hanging(box: _Box) -> bool:
    raw = box.text_indent
    if raw.endswith(" each-line"):
        raw = raw[: -len(" each-line")]
    return raw.endswith(" hanging")


def _text_indent_each_line(box: _Box) -> bool:
    return box.text_indent.endswith(" each-line")


def _read_spacing(value: str | None, parent: str, name: str) -> str:
    """Specified extra spacing. ``normal`` is zero and the used value inherits."""

    if value is None or value.strip().lower() in {"inherit", "unset", "revert"}:
        return parent
    text = value.strip().lower()
    if any(character.isspace() for character in text):
        raise _Invalid(f"{name} is invalid")
    if text in {"normal", "initial", "0"}:
        return "0px"
    if text.endswith("%") or text.endswith("em") or text.endswith("rem"):
        raise _Invalid(f"{name} is invalid")
    if text.endswith("px"):
        try:
            number = float(text[:-2])
        except ValueError as exc:
            raise _Invalid(f"{name} is invalid") from exc
        return f"{_px(number, name)}px"
    raise _Invalid(f"{name} is invalid")


def _used_spacing_px(raw: str) -> int:
    if raw == "0px":
        return 0
    if not raw.endswith("px"):
        raise _Invalid("spacing is invalid")
    return _px(float(raw[:-2]), "spacing")


def _spacing_args(box: _Box) -> dict[str, int]:
    args: dict[str, int] = {}
    if box.letter_spacing:
        args["letter_spacing"] = box.letter_spacing
    if box.word_spacing:
        args["word_spacing"] = box.word_spacing
    return args


def _read_text_autospace(value: str | None, parent: str) -> str:
    """Computed ``text-autospace``. Omitted stays flush; ``normal`` opens both gaps."""

    if value is None or value.strip().lower() in {"inherit", "unset", "revert"}:
        return parent
    text = " ".join(value.strip().lower().split())
    if text in {"initial", "no-autospace"}:
        return "no-autospace"
    if text == "normal":
        return "ideograph-alpha ideograph-numeric"
    if text in {"auto", "punctuation"} or "punctuation" in text.split(" ") or "auto" in text.split(" "):
        raise _Invalid("text-autospace is unsupported")
    parts = text.split(" ")
    if len(parts) != len(set(parts)):
        raise _Invalid("text-autospace is invalid")
    allowed = {"ideograph-alpha", "ideograph-numeric", "insert", "replace"}
    if any(part not in allowed for part in parts):
        raise _Invalid("text-autospace is invalid")
    if "insert" in parts and "replace" in parts:
        raise _Invalid("text-autospace is invalid")
    if not ({"ideograph-alpha", "ideograph-numeric"} & set(parts)):
        raise _Invalid("text-autospace is invalid")
    ordered = [part for part in ("ideograph-alpha", "ideograph-numeric", "replace") if part in parts]
    return " ".join(ordered)


def _autospace_on(box: _Box) -> bool:
    return box.text_autospace not in {"", "no-autospace"}


def _autospace_args(box: _Box) -> dict[str, object]:
    if not _autospace_on(box):
        return {}
    return {"text_autospace": box.text_autospace, "autospace": box.font_size * 0.125}


def _reject_text_autospace(box: _Box) -> None:
    if not _autospace_on(box) or not (box.inline_text or "").strip():
        return
    if box.writing_mode != "horizontal-tb" or box.direction != "ltr":
        raise _Invalid("text-autospace writing mode is unsupported")
    if (
        box.floats
        or box.atoms
        or _mixed_runs(box)
        or _relative_pieces(box)
        or box.ruby
        or box.text_indent != "0px"
        or box.white_space != "normal"
    ):
        raise _Invalid("text-autospace is unsupported")


def _read_tab_size(value: str | None, parent: str) -> str:
    """Specified tab size. A number stays a number so a child uses its own space."""

    if value is None or value.strip().lower() in {"inherit", "unset", "revert"}:
        return parent
    text = value.strip().lower()
    if text == "initial":
        return "8"
    if any(character.isspace() for character in text):
        raise _Invalid("tab-size is invalid")
    if text.endswith("px"):
        try:
            number = float(text[:-2])
        except ValueError as exc:
            raise _Invalid("tab-size is invalid") from exc
        if number < 0 or number != number or number in {float("inf"), float("-inf")}:
            raise _Invalid("tab-size is invalid")
        return f"{_px(number, 'tab-size')}px"
    if not text or text[0].isalpha() or text.endswith("%"):
        raise _Invalid("tab-size is invalid")
    try:
        number = float(text)
    except ValueError as exc:
        raise _Invalid("tab-size is invalid") from exc
    if number < 0 or number != number or number in {float("inf"), float("-inf")}:
        raise _Invalid("tab-size is invalid")
    if abs(number - round(number)) <= 1e-9:
        return str(int(round(number)))
    return format(number, ".12g")


def _tab_size_number(box: _Box) -> float:
    """Tab interval as a multiple of this box's space advance."""

    raw = box.tab_size
    if raw.endswith("px"):
        space = _advance_of(" ", box.font_size)
        if space <= 0:
            return 0.0
        return float(raw[:-2]) / space
    return float(raw)


def _read_lang(element, parent: str) -> str:
    """Content language. A missing attribute inherits; a blank one is unknown."""

    raw = _attr(element, "lang")
    if raw is None:
        raw = _attr(element, "xml:lang")
    if raw is None:
        return parent
    return raw.strip().casefold()


def _break_args(box: _Box) -> dict[str, object]:
    if box.hanging_punctuation != "none" and (box.writing_mode != "horizontal-tb" or box.direction != "ltr"):
        raise _Invalid("hanging punctuation writing mode is unsupported")
    if box.hyphenate_character != "\u2010" and (box.writing_mode != "horizontal-tb" or box.direction != "ltr"):
        raise _Invalid("hyphenate-character writing mode is unsupported")
    return {
        "overflow_wrap": box.overflow_wrap,
        "word_break": box.word_break,
        "tab_size": _tab_size_number(box),
        "hyphens": box.hyphens,
        "lang": box.lang,
        "hanging_punctuation": box.hanging_punctuation,
        "hyphenate_character": box.hyphenate_character,
    }


def _read_hyphenate_character(value: str | None, parent: str) -> str:
    """Used hyphen mark. ``auto`` is U+2010; a quoted string is inserted as written."""

    if value is None or value.strip().lower() in {"inherit", "unset", "revert"}:
        return parent
    text = value.strip()
    if text.lower() in {"initial", "auto"}:
        return "\u2010"
    return _css_string(text, "hyphenate-character")


def _css_string(value: str, name: str) -> str:
    """Decode one CSS string. Anything after the closing quote is invalid."""

    if len(value) < 2 or value[0] not in {"'", '"'}:
        raise _Invalid(f"{name} is invalid")
    quote = value[0]
    index = 1
    chars: list[str] = []
    while index < len(value):
        char = value[index]
        if char == quote:
            if index != len(value) - 1:
                raise _Invalid(f"{name} is invalid")
            return "".join(chars)
        if char in "\n\r\f":
            raise _Invalid(f"{name} is invalid")
        if char == "\\":
            decoded, index = _css_escape(value, index, name)
            chars.append(decoded)
            continue
        chars.append(char)
        index += 1
    raise _Invalid(f"{name} is invalid")


def _css_escape(value: str, index: int, name: str) -> tuple[str, int]:
    index += 1
    if index >= len(value):
        raise _Invalid(f"{name} is invalid")
    char = value[index]
    if char in "\n\f":
        return "", index + 1
    if char == "\r":
        if index + 1 < len(value) and value[index + 1] == "\n":
            return "", index + 2
        return "", index + 1
    if char in "0123456789abcdefABCDEF":
        digits = [char]
        index += 1
        while index < len(value) and len(digits) < 6 and value[index] in "0123456789abcdefABCDEF":
            digits.append(value[index])
            index += 1
        if index < len(value) and value[index] in " \t":
            index += 1
        elif index < len(value) and value[index] == "\r":
            index += 2 if index + 1 < len(value) and value[index + 1] == "\n" else 1
        elif index < len(value) and value[index] in "\n\f":
            index += 1
        code = int("".join(digits), 16)
        if code == 0 or code > 0x10FFFF or 0xD800 <= code <= 0xDFFF:
            raise _Invalid(f"{name} is invalid")
        return chr(code), index
    return char, index + 1


def _css_strings(value: str, name: str) -> list[str]:
    """Decode every CSS string in ``value``. A bare token is invalid."""

    index = 0
    found: list[str] = []
    length = len(value)
    while index < length:
        while index < length and value[index].isspace():
            index += 1
        if index >= length:
            break
        if value[index] not in {"'", '"'}:
            raise _Invalid(f"{name} is invalid")
        quote = value[index]
        index += 1
        chars: list[str] = []
        closed = False
        while index < length:
            char = value[index]
            if char == quote:
                found.append("".join(chars))
                index += 1
                closed = True
                break
            if char in "\n\r\f":
                raise _Invalid(f"{name} is invalid")
            if char == "\\":
                decoded, index = _css_escape(value, index, name)
                chars.append(decoded)
                continue
            chars.append(char)
            index += 1
        if not closed:
            raise _Invalid(f"{name} is invalid")
    if not found:
        raise _Invalid(f"{name} is invalid")
    return found


def _read_quotes(
    value: str | None, parent: tuple[tuple[str, str], ...]
) -> tuple[tuple[str, str], ...]:
    """Used quote pairs. ``none`` is empty; ``auto`` is the English initial value."""

    if value is None or value.strip().lower() in {"inherit", "unset", "revert"}:
        return parent
    text = value.strip()
    lowered = " ".join(text.lower().split())
    if lowered in {"initial", "auto"}:
        return _AUTO_QUOTES
    if lowered == "none":
        return ()
    strings = _css_strings(text, "quotes")
    if len(strings) % 2:
        raise _Invalid("quotes is invalid")
    return tuple((strings[index], strings[index + 1]) for index in range(0, len(strings), 2))


def _append_quote_text(parts: list, text: str) -> None:
    if not text:
        return
    if parts and isinstance(parts[-1], tuple) and parts[-1][0] == "text":
        parts[-1] = ("text", parts[-1][1] + text)
    else:
        parts.append(("text", text))


def _apply_quote_parts(
    parts: list,
    pairs: tuple[tuple[str, str], ...],
    depth: list[int],
    mode: tuple[str, str],
) -> list:
    """Replace quote keywords. A close quote decrements before choosing its pair."""

    if not isinstance(parts, list):
        return []
    if any(isinstance(part, tuple) and part and part[0] in _QUOTE_PARTS for part in parts):
        if mode[0] != "horizontal-tb" or mode[1] != "ltr":
            raise _Invalid("quote content is unsupported")
    resolved: list = []
    for part in parts:
        if not isinstance(part, tuple) or not part or part[0] not in _QUOTE_PARTS:
            resolved.append(part)
            continue
        kind = part[0]
        if kind in {"close-quote", "no-close-quote"}:
            if depth[0] == 0:
                continue
            depth[0] -= 1
            if kind == "close-quote" and pairs:
                _append_quote_text(resolved, pairs[min(depth[0], len(pairs) - 1)][1])
            continue
        if kind == "open-quote" and pairs:
            _append_quote_text(resolved, pairs[min(depth[0], len(pairs) - 1)][0])
        depth[0] += 1
    return resolved


def _quote_box_kind(tree, element, styles, declarations) -> str:
    """``none`` and ``contents`` do not insert quotation marks of their own.

    Unknown display values stay a generating box here so the later box builder
    still reports the display error.
    """

    if _local_name(element) in _SKIP_TAGS:
        return "none"
    custom = styles.get(element, ({}, ""))[0]
    winners = _winners(tree, element, declarations)
    raw = _declared(winners, "display", custom)
    if raw is None or raw in {"initial", "unset", "revert"}:
        display = "block" if _local_name(element) in _BLOCK_TAGS else "inline"
    else:
        display = " ".join(raw.strip().lower().split())
    if display == "list-item":
        return "block"
    if display == "none":
        return "none"
    if display == "contents":
        return "contents"
    return "box"


def _resolve_quote_plans(
    tree,
    order: list,
    styles,
    declarations,
    raw: dict[int, tuple[list, list]],
) -> dict[int, tuple[list, list]]:
    """Resolve quote keywords in tree order: ``::before``, children, ``::after``."""

    pairs: dict[int, tuple[tuple[str, str], ...]] = {}
    modes: dict[int, tuple[str, str]] = {}
    kinds: dict[int, str] = {}
    for element in order:
        parent = tree.parent.get(element)
        parent_pairs = pairs.get(id(parent), _AUTO_QUOTES)
        parent_mode = modes.get(id(parent), (_INHERITED["writing-mode"], _INHERITED["direction"]))
        custom = styles.get(element, ({}, ""))[0]
        winners = _winners(tree, element, declarations)
        pairs[id(element)] = _read_quotes(_declared(winners, "quotes", custom), parent_pairs)
        inherited = {"writing-mode": parent_mode[0], "direction": parent_mode[1]}
        modes[id(element)] = (
            _inherited("writing-mode", winners, custom, inherited),
            _inherited("direction", winners, custom, inherited),
        )
        kinds[id(element)] = _quote_box_kind(tree, element, styles, declarations)
    resolved = {key: (list(before), list(after)) for key, (before, after) in raw.items()}
    depth = [0]

    def walk(element, hidden: bool) -> None:
        ident = id(element)
        kind = kinds.get(ident, "none")
        skip = hidden or kind == "none"
        before, after = resolved.get(ident, ([], []))
        if not skip and kind != "contents":
            before = _apply_quote_parts(before, pairs.get(ident, _AUTO_QUOTES), depth, modes[ident])
        for child in tree.children.get(element, []):
            walk(child, skip)
        if not skip and kind != "contents":
            after = _apply_quote_parts(after, pairs.get(ident, _AUTO_QUOTES), depth, modes[ident])
            resolved[ident] = (before, after)

    if order:
        walk(order[0], False)
    return resolved


def _read_hanging(value: str | None, parent: str) -> str:
    """Computed ``hanging-punctuation``. Keywords combine; the two end modes do not."""

    if value is None or value.strip().lower() in {"inherit", "unset", "revert"}:
        return parent
    text = " ".join(value.strip().lower().split())
    if text in {"initial", "none"}:
        return "none"
    parts = text.split(" ")
    allowed = {"first", "force-end", "allow-end", "last"}
    if len(parts) != len(set(parts)) or any(part not in allowed for part in parts):
        raise _Invalid("hanging-punctuation is invalid")
    if "force-end" in parts and "allow-end" in parts:
        raise _Invalid("hanging-punctuation is invalid")
    ordered = [part for part in ("first", "force-end", "allow-end", "last") if part in parts]
    return " ".join(ordered)


def _read_line_clamp(value: str | None) -> int | None:
    """Computed ``line-clamp``. It is not inherited; ``none`` keeps every line."""

    if value is None:
        return None
    token = value.strip().lower()
    if token in {"none", "initial", "unset", "revert"}:
        return None
    if token == "inherit":
        raise _Invalid("line-clamp inherit is unsupported")
    if not token.isascii() or not token.isdigit() or token.startswith("0"):
        raise _Invalid("line-clamp is invalid")
    return int(token)


def _text_wrap_style(winners: list[tuple[int, str, str]], custom: dict, parent: str) -> str:
    """Computed ``text-wrap-style``. The shorthand ``text-wrap`` sets it too."""

    chosen: tuple[int, str, str] | None = None
    for order, prop, value in winners:
        if prop in {"text-wrap", "text-wrap-style"} and (chosen is None or order >= chosen[0]):
            chosen = (order, prop, value)
    if chosen is None:
        return parent
    prop = chosen[1]
    raw = _declared([chosen], prop, custom)
    if raw is None or raw in {"inherit", "unset", "revert"}:
        return parent
    token = raw.strip().lower()
    if token == "initial":
        return "auto"
    mapped = {"balance": "balance", "auto": "auto", "pretty": "pretty"}
    if prop == "text-wrap":
        mapped["wrap"] = "auto"
    if token not in mapped:
        raise _Invalid("text-wrap is invalid")
    return mapped[token]


def _reject_balanced_context(box: _Box) -> None:
    if box.text_wrap_style == "balance":
        raise _Invalid("balanced text wrap is unsupported")
    if box.text_wrap_style == "pretty":
        raise _Invalid("pretty text wrap is unsupported")


def _measure_lines(box: _Box, text: str, measure: int, *, advances: object) -> dict[str, object]:
    if box.text_wrap_style == "balance":
        function = balance_lines
    elif box.text_wrap_style == "pretty":
        function = pretty_lines
    else:
        function = wrap_lines
    return function(
        text,
        measure,
        white_space=box.white_space,
        advances=advances,
        nowrap_ranges=box.nowrap_ranges,
        clone_ranges=box.clone_ranges,
        **_spacing_args(box),
        **_autospace_args(box),
        **_break_args(box),
    )


def _reject_spacing(box: _Box) -> None:
    if not box.letter_spacing and not box.word_spacing:
        return
    if box.writing_mode != "horizontal-tb":
        raise _Invalid("spaced writing mode is unsupported")
    if _gap_alignment(box):
        raise _Invalid("spaced justification is unsupported")


def _text_indent_used(box: _Box) -> int:
    raw = _text_indent_length(box.text_indent)
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


def _used_text_transform(value: str | None, parent: str, mode: str, direction: str, display: str) -> str:
    chosen = _inherited_keyword(value, _TRANSFORMS, parent, _FONT["text-transform"], "text-transform")
    if chosen != "none" and (
        mode != "horizontal-tb" or direction != "ltr" or display in _TRANSFORM_REJECTED_DISPLAYS
    ):
        raise _Invalid("text-transform is unsupported")
    return chosen


def _transform_text(text: str, mode: str) -> str:
    """Case the characters that line breaking will measure."""

    if mode == "none" or text == "":
        return text
    if mode == "uppercase":
        return text.upper()
    if mode == "lowercase":
        return text.lower()
    if mode != "capitalize":
        raise _Invalid("text-transform is invalid")
    pieces: list[str] = []
    start = True
    for character in text:
        if start and character.islower():
            pieces.append(character.title())
        else:
            pieces.append(character)
        start = character.isspace()
    return "".join(pieces)


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


def _generated_fonts(tree, element) -> tuple[dict, dict]:
    found = getattr(tree, "generated_fonts", None)
    if not isinstance(found, dict):
        return {}, {}
    pair = found.get(id(element))
    if not isinstance(pair, tuple) or len(pair) != 2:
        return {}, {}
    before, after = pair
    return (before if isinstance(before, dict) else {}, after if isinstance(after, dict) else {})


def _generated_font_declared(tree, element) -> bool:
    before, after = _generated_fonts(tree, element)
    return bool(before or after)


def _reject_generated_font(tree, element) -> None:
    if _generated_font_declared(tree, element):
        raise _Invalid("generated font is unsupported")


def _subtree_generated_font(box: _Box) -> bool:
    element = box.element
    tree = box.tree
    fonts = getattr(tree, "generated_fonts", None) if tree is not None else None
    if element is None or not isinstance(fonts, dict) or not fonts:
        return False
    stack = [element]
    while stack:
        node = stack.pop()
        if id(node) in fonts:
            return True
        stack.extend(list(node))
    return False


def _sized_generated(text: str, raw: dict, size: int, leading: str) -> tuple[str, int, str]:
    if not text or not raw:
        return text, size, leading
    return (
        text,
        _font_size(raw.get("font-size"), f"{size}px"),
        _line_height(raw.get("line-height"), leading),
    )


def _add_own_generated(
    add,
    tree,
    node,
    side: str,
    text: str,
    size: int,
    leading: str,
    layers,
    align: str | int,
    nowrap: bool = False,
    marks: tuple[tuple[str, int, str], ...] = (),
) -> None:
    before_font, after_font = _generated_fonts(tree, node)
    raw = before_font if side == "before" else after_font
    shown, font, height = _sized_generated(text, raw, size, leading)
    add(shown, font, height, layers, align, nowrap, None, marks)


def _push_generated_text(tree, node, side: str, text: str, size: int, parts: list[str], advances: list[int]) -> None:
    before_font, after_font = _generated_fonts(tree, node)
    raw = before_font if side == "before" else after_font
    shown, font, _height = _sized_generated(text, raw, size, "normal")
    _push_inline_text(shown, font, parts, advances)


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
    _reject_generated_font(tree, element)
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
        not _block_container(box)
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


def _inline_block_anonymous_ready(box: _Box) -> bool:
    """A static horizontal inline-block can wrap loose text into anonymous blocks."""

    return (
        box.position == "static"
        and box.float_side == "none"
        and not box.positioned
        and box.writing_mode == "horizontal-tb"
        and box.direction == "ltr"
        and box.white_space == "normal"
        and box.multicol is None
        and box.flex is None
        and box.grid is None
        and box.table is None
    )


def _inline_block_child(item: _Box) -> bool:
    """A real block, or the anonymous block that holds the loose text beside it."""

    if item.anonymous:
        if item.display != "block" or item.position != "static" or item.float_side != "none":
            return False
        if item.children or item.floats or item.positioned or item.atoms:
            return False
        if item.writing_mode != "horizontal-tb" or item.direction != "ltr":
            return False
        if not item.inline_text or not item.inline_text.strip():
            return False
        return all(
            piece.atom is None and not piece.shifts and piece.font_size == item.font_size
            for piece in item.pieces
        )
    return item.display == "block" and _float_block_child(item)


def _inline_block_float_ready(box: _Box) -> bool:
    """Left floats stay one contiguous run, before the text or after one earlier line group.

    Text before that run keeps the full width. Text after it shortens beside
    the floats. A float that follows the later text, a right float, and a real
    block stay rejected.
    """

    if not box.floats:
        return True
    if not _inline_block_anonymous_ready(box):
        return False
    if any(not child.anonymous for child in box.children):
        return False
    seen_float = False
    text_after_float = False
    for item in box.flow or box.floats:
        if item.float_side == "none":
            if seen_float:
                text_after_float = True
            continue
        if text_after_float or item.float_side != "left":
            return False
        if (
            item.clear != "none"
            or item.shape_outside
            or item.children
            or item.floats
            or item.positioned
            or item.atoms
            or item.position != "static"
            or item.writing_mode != "horizontal-tb"
            or item.direction != "ltr"
        ):
            return False
        try:
            _fixed_float_outer(item)
        except _Invalid:
            return False
        seen_float = True
    return True


def _has_percent(box: _Box) -> bool:
    """A percentage needs the definite containing block this shrink pass does not have."""

    return any("%" in value for _prop, value in box.declarations)


def _inline_block_nested_ready(box: _Box) -> bool:
    """A static inline-block may contain nested inline-blocks on its line.

    Block children, floats, a mixed font, a percentage, and positioned
    content stay on the paths that already reject them.
    """

    if not box.atoms:
        return True
    if box.children or box.floats or box.positioned or not _inline_block_anonymous_ready(box):
        return False
    if _mixed_runs(box) or any(piece.shifts for piece in box.pieces) or _has_percent(box):
        return False
    for atom in box.atoms:
        if atom.display != "inline-block" or atom.position != "static" or atom.float_side != "none":
            return False
        if atom.positioned or atom.children or atom.floats or atom.white_space != "normal":
            return False
        if atom.writing_mode != "horizontal-tb" or atom.direction != "ltr" or _has_percent(atom):
            return False
        if _mixed_runs(atom) or any(piece.shifts for piece in atom.pieces):
            return False
        if not _inline_block_nested_ready(atom):
            return False
    return True


def _inline_block_blocks(box: _Box, tree, element) -> bool:
    """Text-only atomic boxes stay as they are. A block child is allowed.

    Loose text beside that child must already be an anonymous block. A mixed
    font and positioned content stay rejected.
    """

    if not box.children:
        return True
    if box.writing_mode != "horizontal-tb" or box.direction != "ltr" or box.white_space != "normal":
        return False
    if any(not _inline_block_child(item) for item in box.children):
        return False
    loose = _float_loose_text(tree, element, box.white_space)
    if loose and not any(item.anonymous for item in box.children):
        return False
    return True


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


def _plain_width_percentage(value: object) -> bool:
    """True for one non-negative percentage token, not calc or a keyword."""

    if not isinstance(value, str):
        return False
    text = value.strip().lower()
    if len(text) < 2 or not text.endswith("%"):
        return False
    try:
        number = float(text[:-1])
    except ValueError:
        return False
    return number >= 0 and number == number and number not in {float("inf"), float("-inf")}


def _float_child_span(
    box: _Box,
    *,
    reason: str = "float content is unsupported",
    cyclic_percentage: bool = False,
) -> tuple[int, int]:
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
    cyclic = cyclic_percentage and _plain_width_percentage(specified)
    if _specified_auto(specified) or cyclic:
        if box.children:
            pairs = [
                _float_child_span(child, reason=reason, cyclic_percentage=cyclic_percentage)
                for child in box.children
            ]
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
    """Min-content and max-content of an absolute box from its block children.

    A plain percentage width is cyclic during this pass. The used percentage
    is resolved later, once this box has a definite shrink width.
    """

    pairs = [
        _float_child_span(
            child,
            reason="absolute shrink-to-fit is unsupported",
            cyclic_percentage=True,
        )
        for child in box.children
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


def _position_atom_floats(atom: _Box) -> None:
    """Move an inline-block's floats from its content origin to the viewport."""

    origin_x = atom.x + _edge_extent(atom.solved, "left")
    origin_y = atom.y + _edge_extent(atom.solved, "top")
    for fl in atom.floats:
        if not fl.float_placed:
            continue
        fl.x += origin_x
        fl.y = origin_y + fl.local_y
        _position_lines(fl)
        if fl.children:
            _position_float_children(fl)


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


_SCROLL_LONGHANDS = (
    "animation-name",
    "animation-duration",
    "animation-timing-function",
    "animation-delay",
    "animation-iteration-count",
    "animation-direction",
    "animation-fill-mode",
    "opacity",
)
_SCROLL_REQUIRED = ("animation-name", "animation-duration", "opacity")


def _split_scroll_keyframes(stylesheet: str) -> tuple[str, str]:
    """Drop valid ``@keyframes`` from the layout sheet and keep them for sampling.

    A stylesheet with no keyframes is returned unchanged. A broken keyframes
    block is rejected here so the selector reader never sees it as an unknown
    at-rule.
    """

    stripped = _strip_animation_comments(stylesheet)
    if "@keyframes" not in stripped.lower():
        return stylesheet, ""
    try:
        _found, rest = _extract_keyframes(stripped)
    except _AnimInvalid as exc:
        raise _Invalid("scroll animation is invalid") from exc
    return rest, stripped


def _read_scroll_rule(winners, custom: dict) -> str:
    """Style body for one ``scroll()`` opacity animation, or empty when unused."""

    raw = _latest_declared(winners, "animation-timeline")
    if raw is None:
        return ""
    timeline = _declared(winners, "animation-timeline", custom)
    if timeline is None:
        raise _Invalid("scroll timeline is invalid")
    text = "".join(timeline.split()).lower()
    if text == "inherit":
        raise _Invalid("scroll timeline inherit is unsupported")
    if text in {"auto", "none", "initial", "unset", "revert"}:
        return ""
    if text != "scroll()":
        raise _Invalid("scroll timeline is invalid")
    shorthand = _latest_declared(winners, "animation")
    if shorthand is not None and " ".join(shorthand.split()).lower() not in {
        "none",
        "initial",
        "unset",
        "revert",
    }:
        raise _Invalid("animation shorthand is unsupported")
    parts: list[str] = []
    present: set[str] = set()
    for name in _SCROLL_LONGHANDS:
        if _latest_declared(winners, name) is None:
            continue
        value = _declared(winners, name, custom)
        if value is None:
            raise _Invalid("scroll animation is invalid")
        parts.append(f"{name}: {' '.join(value.split())};")
        present.add(name)
    if any(name not in present for name in _SCROLL_REQUIRED):
        raise _Invalid("scroll animation is invalid")
    return " ".join(parts)


def _apply_scroll_opacities(
    root: _Box,
    scroll_source: str,
    viewport_height: int | None,
    scroll_y: int,
) -> None:
    boxes = [box for box in _each(root) if box.scroll_rule]
    if not boxes:
        return
    progress = _scroll_opacity_progress(root, viewport_height, scroll_y)
    if not scroll_source:
        raise _Invalid("scroll animation is invalid")
    for box in boxes:
        _apply_one_scroll_opacity(box, scroll_source, progress)


def _scroll_opacity_progress(
    root: _Box,
    viewport_height: int | None,
    scroll_y: int,
) -> object:
    if viewport_height is None:
        raise _Invalid("scroll timeline is unsupported")
    overflow = root.y + root.border_height
    if overflow <= viewport_height:
        return None
    progressed = scroll_timeline_progress(scroll_y, overflow, viewport_height)
    if progressed.get("outcome") != "active":
        raise _Invalid(str(progressed.get("reason") or "scroll timeline is invalid"))
    return progressed.get("progress")


def _apply_one_scroll_opacity(box: _Box, scroll_source: str, progress: object) -> None:
    if box.writing_mode != "horizontal-tb" or box.direction != "ltr":
        raise _Invalid("scroll timeline writing mode is unsupported")
    if box.float_side != "none" or box.position not in {"static", "relative"}:
        raise _Invalid("scroll timeline position is unsupported")
    if box.display not in {"block", "flow-root"} or box.list_item:
        raise _Invalid("scroll timeline display is unsupported")
    sampled = sample_scroll_driven_animation(
        scroll_source + "\n#scroll-sample {\n" + box.scroll_rule + "\n}\n",
        progress,
        property="opacity",
    )
    outcome = sampled.get("outcome")
    if outcome not in {"sampled", "inactive"}:
        raise _Invalid("scroll animation is invalid")
    value = sampled.get("value")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _Invalid("scroll animation is invalid")
    box.scroll_opacity = value


def _read_offset(winners, custom: dict) -> tuple[str, str, str, str]:
    shorthand = _latest_declared(winners, "offset")
    if shorthand is not None and shorthand.strip().lower() not in {"none", "initial", "unset", "revert"}:
        raise _Invalid("offset shorthand is unsupported")
    raw = _latest_declared(winners, "offset-path")
    if raw is None:
        return "", "0px", "auto", "auto"
    path = _declared(winners, "offset-path", custom)
    if path is None:
        raise _Invalid("offset path is invalid")
    text = " ".join(path.split())
    lowered = text.lower()
    if lowered == "inherit":
        raise _Invalid("offset path inherit is unsupported")
    if lowered in {"none", "initial", "unset", "revert"}:
        return "", "0px", "auto", "auto"
    return (
        text,
        _offset_longhand(winners, custom, "offset-distance", "0px", "offset distance"),
        _offset_longhand(winners, custom, "offset-rotate", "auto", "offset rotate"),
        _offset_longhand(winners, custom, "offset-anchor", "auto", "offset anchor"),
    )


def _offset_longhand(winners, custom: dict, name: str, default: str, label: str) -> str:
    if _latest_declared(winners, name) is None:
        return default
    value = _declared(winners, name, custom)
    if value is None:
        raise _Invalid(f"{label} is invalid")
    text = " ".join(value.split()).lower()
    if text == "inherit":
        raise _Invalid(f"{label} inherit is unsupported")
    if text in {"initial", "unset", "revert"}:
        return default
    return text


def _latest_declared(winners, name: str) -> str | None:
    found = None
    for _order, prop, value in winners:
        if prop == name:
            found = value
    return found


def _shift_offsets(box: _Box, viewport_width: int, viewport_height: int | None) -> None:
    if box.offset_path:
        dx, dy, angle = _offset_delta(box, viewport_width, viewport_height)
        box.offset_angle = angle
        _translate_painted(box, dx, dy)
    for child in box.children:
        _shift_offsets(child, viewport_width, viewport_height)
    for fl in box.floats:
        _shift_offsets(fl, viewport_width, viewport_height)
    for atom in box.atoms:
        _shift_offsets(atom, viewport_width, viewport_height)
    for abs_box in box.positioned:
        _shift_offsets(abs_box, viewport_width, viewport_height)


def _translate_painted(box: _Box, dx: int, dy: int) -> None:
    if dx == 0 and dy == 0:
        return
    _translate(box, dx, dy)
    if not box.anonymous:
        for atom in box.atoms:
            _translate_painted(atom, dx, dy)
    for abs_box in box.positioned:
        _translate_painted(abs_box, dx, dy)


def _offset_delta(
    box: _Box,
    viewport_width: int,
    viewport_height: int | None,
) -> tuple[int, int, int | float]:
    if box.writing_mode != "horizontal-tb" or box.direction != "ltr":
        raise _Invalid("offset path writing mode is unsupported")
    if box.float_side != "none" or box.position not in {"static", "relative"}:
        raise _Invalid("offset path position is unsupported")
    parent = box.parent_box
    if parent is None:
        origin_x = 0
        origin_y = 0
        ref_w = viewport_width
        ref_h = viewport_height if viewport_height is not None else box.border_height
    else:
        origin_x = parent.x
        origin_y = parent.y
        ref_w = parent.border_width
        ref_h = parent.border_height
    placed = travel_offset_path(
        box.offset_path,
        box.offset_distance,
        rotate=box.offset_rotate,
        box_width=ref_w,
        box_height=ref_h,
    )
    if placed.get("outcome") != "resolved":
        reason = str(placed.get("reason") or "path")
        if reason == "distance":
            raise _Invalid("offset distance is invalid")
        if reason == "rotate":
            raise _Invalid("offset rotate is invalid")
        if reason == "box":
            raise _Invalid("offset path box is unsupported")
        raise _Invalid("offset path is invalid")
    point_x = placed.get("x")
    point_y = placed.get("y")
    angle = placed.get("angle")
    if isinstance(point_x, bool) or isinstance(point_y, bool) or isinstance(angle, bool):
        raise _Invalid("offset path is invalid")
    if not isinstance(point_x, (int, float)) or not isinstance(point_y, (int, float)):
        raise _Invalid("offset path is invalid")
    if not isinstance(angle, (int, float)):
        raise _Invalid("offset path is invalid")
    anchor_x, anchor_y = _offset_anchor_point(box)
    dx = _px((origin_x + float(point_x)) - (box.x + anchor_x), "offset x")
    dy = _px((origin_y + float(point_y)) - (box.y + anchor_y), "offset y")
    return dx, dy, angle


def _offset_anchor_point(box: _Box) -> tuple[float, float]:
    raw = " ".join(box.offset_anchor.lower().split())
    if raw in {"auto", "initial", "unset", "revert"}:
        return box.border_width / 2.0, box.border_height / 2.0
    parts = raw.split()
    if len(parts) != 2:
        raise _Invalid("offset anchor is invalid")
    return _offset_anchor_axis(parts[0], box.border_width), _offset_anchor_axis(parts[1], box.border_height)


def _offset_anchor_axis(token: str, size: int) -> float:
    try:
        if token in {"0", "+0", "-0"}:
            return 0.0
        if token.endswith("%") and token != "%":
            return float(token[:-1]) * size / 100.0
        if token.endswith("px") and token != "px":
            return float(token[:-2])
    except ValueError as exc:
        raise _Invalid("offset anchor is invalid") from exc
    raise _Invalid("offset anchor is invalid")


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
        _translate(box, *_sticky_delta(box, viewport_width, viewport_height, scroll_x, scroll_y))
    for child in box.children:
        _shift_stickies(child, viewport_width, viewport_height, scroll_x, scroll_y)
    for fl in box.floats:
        _shift_stickies(fl, viewport_width, viewport_height, scroll_x, scroll_y)
    for atom in box.atoms:
        _shift_stickies(atom, viewport_width, viewport_height, scroll_x, scroll_y)
    for abs_box in box.positioned:
        _shift_stickies(abs_box, viewport_width, viewport_height, scroll_x, scroll_y)


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


_SCROLLABLE_PORTS = frozenset({"hidden", "auto", "scroll"})
_SNAP_AXES = frozenset({"x", "y", "block", "inline", "both", "pair"})
_SNAP_STRICT = frozenset({"mandatory", "proximity"})
_SNAP_ALIGNS = frozenset({"none", "start", "end", "center"})
_SNAP_RESET = frozenset({"initial", "unset", "revert"})


def _read_scroll_snap(
    winners, custom: dict
) -> tuple[str, tuple[str, str], tuple[int, int, int, int], tuple[int, int, int, int]]:
    """Used snap type, alignment, scroll-padding, and scroll-margin."""

    return (
        _read_snap_type(_declared(winners, "scroll-snap-type", custom)),
        _read_snap_align(_declared(winners, "scroll-snap-align", custom)),
        _read_snap_edges(winners, custom, "scroll-padding", negative=False),
        _read_snap_edges(winners, custom, "scroll-margin", negative=True),
    )


def _read_snap_type(value: str | None) -> str:
    if value is None:
        return ""
    keyword = " ".join(value.split()).lower()
    if keyword in _SNAP_RESET or keyword == "none":
        return ""
    if keyword == "inherit":
        raise _Invalid("scroll snap inherit is unsupported")
    parts = keyword.split()
    if len(parts) == 1 and parts[0] in _SNAP_AXES:
        return f"{parts[0]} proximity"
    if len(parts) == 2 and parts[0] in _SNAP_AXES and parts[1] in _SNAP_STRICT:
        return keyword
    raise _Invalid("scroll snap is invalid")


def _read_snap_align(value: str | None) -> tuple[str, str]:
    if value is None:
        return ("none", "none")
    keyword = " ".join(value.split()).lower()
    if keyword in _SNAP_RESET or keyword == "none":
        return ("none", "none")
    if keyword == "inherit":
        raise _Invalid("scroll snap inherit is unsupported")
    parts = keyword.split()
    if len(parts) == 1 and parts[0] in _SNAP_ALIGNS:
        return (parts[0], parts[0])
    if len(parts) == 2 and parts[0] in _SNAP_ALIGNS and parts[1] in _SNAP_ALIGNS:
        return (parts[0], parts[1])
    raise _Invalid("scroll snap is invalid")


def _read_snap_edges(winners, custom: dict, name: str, *, negative: bool) -> tuple[int, int, int, int]:
    """Top, right, bottom, left. A later longhand replaces one shorthand side."""

    edges = (0, 0, 0, 0)
    seen = False
    longhands = {
        f"{name}-top": 0,
        f"{name}-right": 1,
        f"{name}-bottom": 2,
        f"{name}-left": 3,
    }
    for _order, prop, raw in winners:
        if prop != name and prop not in longhands:
            continue
        seen = True
        value = _declared([(_order, prop, raw)], prop, custom)
        if prop == name:
            edges = _snap_edge_shorthand(value, negative=negative, label=name)
            continue
        side = _snap_one_edge(value, negative=negative, label=name)
        mutable = list(edges)
        mutable[longhands[prop]] = side
        edges = (mutable[0], mutable[1], mutable[2], mutable[3])
    if not seen:
        return (0, 0, 0, 0)
    return edges


def _snap_edge_shorthand(value: str | None, *, negative: bool, label: str) -> tuple[int, int, int, int]:
    if value is None:
        return (0, 0, 0, 0)
    keyword = " ".join(value.split()).lower()
    if keyword in _SNAP_RESET or (keyword == "auto" and not negative):
        return (0, 0, 0, 0)
    if keyword == "inherit":
        raise _Invalid(f"{label} inherit is unsupported")
    tokens = keyword.split()
    if not 1 <= len(tokens) <= 4:
        raise _Invalid(f"{label} is invalid")
    lengths = tuple(_snap_px(token, negative=negative, label=label) for token in tokens)
    if len(lengths) == 1:
        return (lengths[0], lengths[0], lengths[0], lengths[0])
    if len(lengths) == 2:
        return (lengths[0], lengths[1], lengths[0], lengths[1])
    if len(lengths) == 3:
        return (lengths[0], lengths[1], lengths[2], lengths[1])
    return lengths


def _snap_one_edge(value: str | None, *, negative: bool, label: str) -> int:
    if value is None:
        return 0
    keyword = " ".join(value.split()).lower()
    if keyword in _SNAP_RESET or (keyword == "auto" and not negative):
        return 0
    if keyword == "inherit":
        raise _Invalid(f"{label} inherit is unsupported")
    if len(keyword.split()) != 1:
        raise _Invalid(f"{label} is invalid")
    return _snap_px(keyword, negative=negative, label=label)


def _snap_px(token: str, *, negative: bool, label: str) -> int:
    text = token.lower()
    sign = 1
    if text.startswith("+"):
        text = text[1:]
    elif text.startswith("-"):
        if not negative:
            raise _Invalid(f"{label} is invalid")
        sign = -1
        text = text[1:]
    if text in {"0", "0px"}:
        return 0
    if not text.endswith("px") or text == "px":
        raise _Invalid(f"{label} is invalid")
    try:
        number = float(text[:-2])
    except ValueError as exc:
        raise _Invalid(f"{label} is invalid") from exc
    if number < 0 or number != number or number in {float("inf"), float("-inf")}:
        raise _Invalid(f"{label} is invalid")
    try:
        return sign * _px(number, label)
    except _Invalid as exc:
        raise _Invalid(f"{label} is invalid") from exc


_TRANSITION_RESET = frozenset({"initial", "unset", "revert"})


def _bind_height_transition(box: _Box, winners, custom: dict) -> None:
    """Record a height transition, or reject a box that cannot run one."""

    spec = _read_height_transition(winners, custom)
    if spec is None:
        return
    if (
        box.root
        or box.anonymous
        or box.float_side != "none"
        or box.position in {"absolute", "fixed", "sticky"}
        or box.writing_mode != "horizontal-tb"
        or box.direction != "ltr"
        or box.display not in {"block", "flow-root"}
    ):
        raise _Invalid("height transition is unsupported")
    if _specified_px_height(box) is None:
        raise _Invalid("height transition is invalid")
    box.height_transition = spec


def _read_height_transition(winners, custom: dict) -> tuple[str, str, str] | None:
    shorthand = _declared(winners, "transition", custom)
    if shorthand is not None and " ".join(shorthand.split()).lower() not in {"none", *_TRANSITION_RESET}:
        raise _Invalid("transition shorthand is unsupported")
    raw = _declared(winners, "transition-property", custom)
    if raw is None:
        return None
    token = " ".join(raw.split()).lower()
    if token in {"none", "all", *_TRANSITION_RESET}:
        return None
    if token == "inherit":
        raise _Invalid("height transition inherit is unsupported")
    if token != "height":
        return None
    duration = _transition_clock(_declared(winners, "transition-duration", custom), "0s")
    delay = _transition_clock(_declared(winners, "transition-delay", custom), "0s")
    easing = _transition_easing(_declared(winners, "transition-timing-function", custom))
    probe = interrupt_css_transition(
        "0px",
        [
            {
                "time_ms": 0,
                "value": "0px",
                "duration": duration,
                "delay": delay,
                "easing": easing,
                "transition": True,
            }
        ],
        0,
    )
    if probe.get("outcome") == "invalid":
        raise _Invalid("height transition is invalid")
    return (duration, delay, easing)


def _transition_clock(value: str | None, default: str) -> str:
    if value is None:
        return default
    token = " ".join(value.split()).lower()
    if token in _TRANSITION_RESET:
        return default
    if token == "inherit":
        raise _Invalid("height transition inherit is unsupported")
    return token


def _transition_easing(value: str | None) -> str:
    if value is None:
        return "ease"
    token = " ".join(value.split()).lower()
    if token in _TRANSITION_RESET:
        return "ease"
    if token == "inherit":
        raise _Invalid("height transition inherit is unsupported")
    return token


def _specified_px_height(box: _Box) -> str | None:
    found = None
    for prop, value in box.declarations:
        if prop == "height":
            found = value
    if found is None:
        return None
    token = " ".join(found.split()).lower()
    if token.startswith("+"):
        token = token[1:]
    if not token.endswith("px") or token == "px":
        return None
    number = token[:-2]
    if not number.isdigit():
        return None
    return f"{int(number)}px"


def _apply_height_transitions(
    root: _Box,
    sample_ms: int | None,
    changes: dict[str, list[dict[str, object]]] | None,
) -> None:
    """Substitute each transitioning height before normal flow is solved."""

    boxes = [box for box in _each(root) if box.height_transition is not None]
    if not boxes or sample_ms is None:
        return
    if type(sample_ms) is not int:
        raise _Invalid("height transition sample is invalid")
    if changes is None:
        changes = {}
    if isinstance(changes, (str, bytes)) or not isinstance(changes, dict):
        raise _Invalid("height transition is invalid")
    for box in boxes:
        spec = box.height_transition
        if spec is None:
            continue
        raw = changes.get(box.id, [])
        if raw is None:
            raw = []
        if isinstance(raw, (str, bytes)) or not isinstance(raw, list):
            raise _Invalid("height transition is invalid")
        duration, delay, easing = spec
        events: list[dict[str, object]] = []
        for item in raw:
            if not isinstance(item, dict):
                raise _Invalid("height transition is invalid")
            events.append(
                {
                    "time_ms": item.get("time_ms"),
                    "value": item.get("value"),
                    "duration": duration,
                    "delay": delay,
                    "easing": easing,
                    "transition": True,
                }
            )
        before = _specified_px_height(box)
        if before is None:
            raise _Invalid("height transition is invalid")
        result = interrupt_css_transition(before, events, sample_ms)
        if result.get("outcome") == "invalid" or result.get("unit") != "px":
            raise _Invalid("height transition is invalid")
        _replace_specified_height(box, f"{_px(result.get('value'), 'height transition')}px")


def _replace_specified_height(box: _Box, used_px: str) -> None:
    rewritten: list[tuple[str, str]] = []
    replaced = False
    for prop, value in box.declarations:
        if prop == "height":
            rewritten.append((prop, used_px))
            replaced = True
        else:
            rewritten.append((prop, value))
    if not replaced:
        rewritten.append(("height", used_px))
    box.declarations = rewritten


def _apply_scroll_snap(root: _Box) -> None:
    """Record the resting scroll of each horizontal snapport. Areas stay put."""

    for box in _each(root):
        if not box.snap_type:
            continue
        if box.writing_mode != "horizontal-tb" or box.direction != "ltr":
            raise _Invalid("scroll snap is unsupported")
        if box.overflow not in _SCROLLPORTS:
            raise _Invalid("scroll snap is unsupported")
        box.snap = _rest_scroll_snap(box)


def _rest_scroll_snap(port: _Box) -> dict[str, object]:
    origin_x, origin_y, port_w, port_h = _snap_port_rect(port)
    descendants = _snap_descendants(port)
    bottom = 0
    right = 0
    for item in descendants:
        right = max(right, item.x + item.border_width - origin_x)
        bottom = max(bottom, item.y + item.border_height - origin_y)
    areas = _snap_areas(port, descendants, origin_x, origin_y)
    top, right_pad, bottom_pad, left = port.scroll_padding
    result = resolve_scroll_snap(
        {
            "port_x": port_w,
            "port_y": port_h,
            "padding_top": top,
            "padding_right": right_pad,
            "padding_bottom": bottom_pad,
            "padding_left": left,
            "max_x": max(0, right - port_w),
            "max_y": max(0, bottom - port_h),
            "intended_x": port.scroll_port_x,
            "intended_y": port.scroll_port_y,
            "intent": "absolute",
            "snap_type": port.snap_type,
            "writing_mode": "horizontal-tb",
            "direction": "ltr",
        },
        areas,
    )
    if result.get("outcome") not in {"snapped", "unsnapped"}:
        raise _Invalid("scroll snap is invalid")
    return {
        "x": result.get("x"),
        "y": result.get("y"),
        "inline": result.get("snapped_inline"),
        "block": result.get("snapped_block"),
    }


def _snap_port_rect(box: _Box) -> tuple[int, int, int, int]:
    left = _snap_edge(box, "border_left")
    right = _snap_edge(box, "border_right")
    top = _snap_edge(box, "border_top")
    bottom = _snap_edge(box, "border_bottom")
    width = box.border_width - left - right
    height = box.border_height - top - bottom
    if width <= 0 or height <= 0:
        raise _Invalid("scroll snap is invalid")
    return box.x + left, box.y + top, width, height


def _snap_edge(box: _Box, name: str) -> int:
    raw = box.solved.get(name)
    if raw is None:
        return 0
    try:
        return _px(raw, "scroll snap")
    except _Invalid as exc:
        raise _Invalid("scroll snap is invalid") from exc


def _snap_descendants(port: _Box) -> list[_Box]:
    found: list[_Box] = []

    def walk(box: _Box) -> None:
        for child in (*box.children, *box.floats, *box.atoms, *box.positioned):
            if not child.anonymous:
                found.append(child)
            walk(child)

    walk(port)
    return found


def _snap_areas(
    port: _Box, descendants: list[_Box], origin_x: int, origin_y: int
) -> list[dict[str, object]]:
    aligned = {
        item.id
        for item in descendants
        if item.snap_align != ("none", "none")
    }
    areas: list[dict[str, object]] = []
    for item in descendants:
        block, inline = item.snap_align
        if block == "none" and inline == "none":
            continue
        parent_id = None
        cursor = item.parent_box
        while cursor is not None and cursor is not port:
            if cursor.id in aligned:
                parent_id = cursor.id
                break
            cursor = cursor.parent_box
        top, right, bottom, left = item.scroll_margin
        area: dict[str, object] = {
            "id": item.id,
            "x": item.x - origin_x,
            "y": item.y - origin_y,
            "width": item.border_width,
            "height": item.border_height,
            "margin_top": top,
            "margin_right": right,
            "margin_bottom": bottom,
            "margin_left": left,
            "align_block": block,
            "align_inline": inline,
        }
        if parent_id is not None:
            area["parent"] = parent_id
        areas.append(area)
    return areas


def _apply_port_scroll(root: _Box, port_scroll: object) -> None:
    """Store each named scrollport's own offset before sticky placement.

    Viewport ``scroll_x`` and ``scroll_y`` do not feed these ports. A missing
    name, a negative offset, ``visible``, ``clip``, and a non-horizontal port
    are rejected. In-flow boxes are not translated.
    """

    if port_scroll is None:
        return
    if isinstance(port_scroll, (str, bytes)) or not isinstance(port_scroll, dict):
        raise _Invalid("port scroll is invalid")
    located = {box.id: box for box in _each(root)}
    for key, value in port_scroll.items():
        if not isinstance(key, str) or not key or key.strip() != key:
            raise _Invalid("port scroll is invalid")
        target = located.get(key)
        if target is None:
            raise _Invalid("scrollport is missing")
        offset_x, offset_y = _port_pair(value)
        if (
            target.overflow not in _SCROLLABLE_PORTS
            or target.writing_mode != "horizontal-tb"
            or target.direction != "ltr"
        ):
            raise _Invalid("scrollport is not scrollable")
        target.scroll_port_x = offset_x
        target.scroll_port_y = offset_y


def _port_pair(value: object) -> tuple[int, int]:
    if isinstance(value, (str, bytes)) or not isinstance(value, (tuple, list)) or len(value) != 2:
        raise _Invalid("port scroll is invalid")
    return _port_offset(value[0]), _port_offset(value[1])


def _port_offset(value: object) -> int:
    if type(value) is not int or value < 0:
        raise _Invalid("port scroll is invalid")
    return value


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
            return x, y, width, height, current.scroll_port_x, current.scroll_port_y
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
    if area and not anchor:
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


def _active_transform(box: _Box) -> str | None:
    token = " ".join(str(box.capture.get("transform", "none")).strip().lower().split())
    if token in {"", "none"}:
        return None
    return token


def _chain_has_transform(box: _Box) -> bool:
    current: _Box | None = box
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if _active_transform(current) is not None:
            return True
        current = current.parent_box
    return False


_OUTLINE_PROPS = frozenset(
    {"outline", "outline-style", "outline-width", "outline-color", "outline-offset"}
)
_OUTLINE_STYLES = frozenset(
    {"none", "dotted", "dashed", "solid", "double", "groove", "ridge", "inset", "outset", "auto"}
)
_OUTLINE_RESET = frozenset({"initial", "unset", "revert"})


def _used_color(raw: str | None, fonts: dict[str, str]) -> tuple[str, bool]:
    """Used ``color``. An unparsable specified value stays invalid for outline ink."""

    parent = fonts.get("color", "#000000")
    parent_valid = fonts.get("color-valid", "1") == "1"
    if raw is None:
        return parent, parent_valid
    keyword = " ".join(raw.split()).lower()
    if keyword in {"inherit", "unset", "revert", "currentcolor"}:
        return parent, parent_valid
    if keyword == "initial":
        return "#000000", True
    try:
        return _css_color_hex(raw, reason="color is invalid"), True
    except _Invalid:
        return parent, False


def _read_outline(
    winners, custom: dict, current: str, valid: bool
) -> tuple[str, int, str, int] | None:
    """Used outline, or ``None`` when the stroke has no ink."""

    style = "none"
    width = 3
    color: str | None = None
    offset = 0
    seen = False
    for order, prop, raw in winners:
        if prop not in _OUTLINE_PROPS:
            continue
        seen = True
        value = _declared([(order, prop, raw)], prop, custom)
        if prop == "outline":
            style, width, color = _parse_outline_shorthand(value)
        elif prop == "outline-style":
            style = _parse_outline_style(value)
        elif prop == "outline-width":
            width = _parse_outline_width(value)
        elif prop == "outline-color":
            color = _parse_outline_color(value)
        else:
            offset = _parse_outline_offset(value)
    if not seen or style == "none" or width <= 0:
        return None
    if color is None:
        if not valid:
            raise _Invalid("color is invalid")
        color = current
    return style, width, color, offset


def _parse_outline_shorthand(value: str | None) -> tuple[str, int, str | None]:
    if value is None:
        return "none", 3, None
    keyword = " ".join(value.split()).lower()
    if keyword in _OUTLINE_RESET:
        return "none", 3, None
    if keyword == "inherit":
        raise _Invalid("outline inherit is unsupported")
    tokens = _outline_tokens(value)
    if not tokens or len(tokens) > 3:
        raise _Invalid("outline is invalid")
    style = "none"
    width = 3
    color: str | None = None
    saw_style = False
    saw_width = False
    saw_color = False
    for token in tokens:
        lowered = token.lower()
        if lowered in _OUTLINE_STYLES and not saw_style:
            style = lowered
            saw_style = True
            continue
        parsed_width = _outline_width_token(token)
        if parsed_width is not None and not saw_width:
            width = parsed_width
            saw_width = True
            continue
        if saw_color:
            raise _Invalid("outline is invalid")
        color = _outline_color_token(token)
        saw_color = True
    return style, width, color


def _parse_outline_style(value: str | None) -> str:
    if value is None or value in _OUTLINE_RESET:
        return "none"
    if value == "inherit":
        raise _Invalid("outline inherit is unsupported")
    keyword = " ".join(value.split()).lower()
    if keyword in _OUTLINE_STYLES:
        return keyword
    raise _Invalid("outline is invalid")


def _parse_outline_width(value: str | None) -> int:
    if value is None or value in _OUTLINE_RESET:
        return 3
    if value == "inherit":
        raise _Invalid("outline inherit is unsupported")
    width = _outline_width_token(" ".join(value.split()))
    if width is None:
        raise _Invalid("outline is invalid")
    return width


def _outline_color_token(token: str) -> str | None:
    keyword = token.lower()
    if keyword == "currentcolor":
        return None
    if keyword in _OUTLINE_RESET or keyword == "inherit":
        raise _Invalid("outline is invalid")
    return _css_color_hex(token, reason="outline is invalid")


def _parse_outline_color(value: str | None) -> str | None:
    if value is None:
        return None
    keyword = " ".join(value.split()).lower()
    if keyword in _OUTLINE_RESET or keyword == "currentcolor":
        return None
    if keyword == "inherit":
        raise _Invalid("outline inherit is unsupported")
    return _css_color_hex(value.strip(), reason="outline is invalid")


def _parse_outline_offset(value: str | None) -> int:
    if value is None or value in _OUTLINE_RESET:
        return 0
    if value == "inherit":
        raise _Invalid("outline inherit is unsupported")
    token = " ".join(value.split())
    if token.lower() == "0" or token.lower().endswith("px"):
        return _outline_px(token, negative=True)
    raise _Invalid("outline is invalid")


def _outline_width_token(token: str) -> int | None:
    text = token.lower()
    if text in _BORDER_WIDTHS:
        return _BORDER_WIDTHS[text]
    if text == "0" or text.endswith("px"):
        return _outline_px(text, negative=False)
    return None


def _outline_px(token: str, *, negative: bool) -> int:
    text = token.lower()
    if text == "0":
        return 0
    if not text.endswith("px"):
        raise _Invalid("outline is invalid")
    try:
        number = float(text[:-2])
    except ValueError as exc:
        raise _Invalid("outline is invalid") from exc
    if not negative and number < 0:
        raise _Invalid("outline is invalid")
    try:
        return _px(number, "outline")
    except _Invalid as exc:
        raise _Invalid("outline is invalid") from exc


def _outline_tokens(value: str) -> list[str]:
    tokens: list[str] = []
    chunk: list[str] = []
    depth = 0
    for char in value.strip():
        if char == "(":
            depth += 1
            chunk.append(char)
            continue
        if char == ")" and depth:
            depth -= 1
            chunk.append(char)
            continue
        if char.isspace() and depth == 0:
            if chunk:
                tokens.append("".join(chunk))
                chunk = []
            continue
        chunk.append(char)
    if depth:
        raise _Invalid("outline is invalid")
    if chunk:
        tokens.append("".join(chunk))
    return tokens


def _css_color_hex(text: str, *, reason: str) -> str:
    try:
        parsed = _parse_color(text.strip())
        srgb = _convert_color(parsed, "srgb")
    except (_ColorInvalid, KeyError, ValueError, ZeroDivisionError, OverflowError) as exc:
        raise _Invalid(reason) from exc
    channels = srgb.channels
    if len(channels) != 3:
        raise _Invalid(reason)
    red, green, blue = (_color_byte(channel, reason) for channel in channels)
    alpha = srgb.alpha
    if alpha is None or abs(float(alpha) - 1.0) <= 1e-6:
        return f"#{red:02x}{green:02x}{blue:02x}"
    if not isinstance(alpha, (int, float)) or isinstance(alpha, bool) or alpha < 0 or alpha > 1:
        raise _Invalid(reason)
    return f"#{red:02x}{green:02x}{blue:02x}{_color_byte(float(alpha), reason):02x}"


def _color_byte(channel: object, reason: str) -> int:
    if isinstance(channel, bool) or not isinstance(channel, (int, float)):
        raise _Invalid(reason)
    number = float(channel)
    if number != number or number in {float("inf"), float("-inf")}:
        raise _Invalid(reason)
    scaled = number * 255.0
    if scaled < 0:
        scaled = 0.0
    if scaled > 255:
        scaled = 255.0
    return int(scaled + 0.5)


_COLUMN_RULE_PROPS = frozenset(
    {"column-rule", "column-rule-style", "column-rule-width", "column-rule-color"}
)
_COLUMN_RULE_STYLES = frozenset(
    {"none", "hidden", "dotted", "dashed", "solid", "double", "groove", "ridge", "inset", "outset"}
)
_COLUMN_RULE_RESET = frozenset({"initial", "unset", "revert"})


def _read_column_rule(
    winners, custom: dict, current: str, valid: bool
) -> tuple[str, int, str] | None:
    """Used column rule, or ``None`` when the stroke has no ink."""

    style = "none"
    width = 3
    color: str | None = None
    seen = False
    for order, prop, raw in winners:
        if prop not in _COLUMN_RULE_PROPS:
            continue
        seen = True
        value = _declared([(order, prop, raw)], prop, custom)
        if prop == "column-rule":
            style, width, color = _parse_column_rule_shorthand(value)
        elif prop == "column-rule-style":
            style = _parse_column_rule_style(value)
        elif prop == "column-rule-width":
            width = _parse_column_rule_width(value)
        else:
            color = _parse_column_rule_color(value)
    if not seen or style in {"none", "hidden"} or width <= 0:
        return None
    if color is None:
        if not valid:
            raise _Invalid("color is invalid")
        color = current
    return style, width, color


def _parse_column_rule_shorthand(value: str | None) -> tuple[str, int, str | None]:
    if value is None:
        return "none", 3, None
    keyword = " ".join(value.split()).lower()
    if keyword in _COLUMN_RULE_RESET:
        return "none", 3, None
    if keyword == "inherit":
        raise _Invalid("column-rule inherit is unsupported")
    tokens = _outline_tokens(value)
    if not tokens or len(tokens) > 3:
        raise _Invalid("column-rule is invalid")
    style = "none"
    width = 3
    color: str | None = None
    saw_style = False
    saw_width = False
    saw_color = False
    for token in tokens:
        lowered = token.lower()
        if lowered in _COLUMN_RULE_STYLES and not saw_style:
            style = lowered
            saw_style = True
            continue
        parsed_width = _column_rule_width_token(token, reason="column-rule is invalid")
        if parsed_width is not None and not saw_width:
            width = parsed_width
            saw_width = True
            continue
        if saw_color:
            raise _Invalid("column-rule is invalid")
        color = _column_rule_color_token(token)
        saw_color = True
    return style, width, color


def _parse_column_rule_style(value: str | None) -> str:
    if value is None or value in _COLUMN_RULE_RESET:
        return "none"
    if value == "inherit":
        raise _Invalid("column-rule inherit is unsupported")
    keyword = " ".join(value.split()).lower()
    if keyword in _COLUMN_RULE_STYLES:
        return keyword
    raise _Invalid("column-rule-style is invalid")


def _parse_column_rule_width(value: str | None) -> int:
    if value is None or value in _COLUMN_RULE_RESET:
        return 3
    if value == "inherit":
        raise _Invalid("column-rule inherit is unsupported")
    parsed = _column_rule_width_token(" ".join(value.split()), reason="column-rule-width is invalid")
    if parsed is None:
        raise _Invalid("column-rule-width is invalid")
    return parsed


def _parse_column_rule_color(value: str | None) -> str | None:
    keyword = "" if value is None else " ".join(value.split()).lower()
    if value is None or keyword in _COLUMN_RULE_RESET or keyword == "currentcolor":
        return None
    if keyword == "inherit":
        raise _Invalid("column-rule inherit is unsupported")
    return _css_color_hex(value.strip(), reason="column-rule-color is invalid")


def _column_rule_color_token(token: str) -> str | None:
    keyword = token.lower()
    if keyword == "currentcolor":
        return None
    if keyword in _COLUMN_RULE_RESET or keyword == "inherit":
        raise _Invalid("column-rule is invalid")
    return _css_color_hex(token, reason="column-rule is invalid")


def _column_rule_width_token(token: str, *, reason: str) -> int | None:
    text = token.lower()
    if text in _BORDER_WIDTHS:
        return _BORDER_WIDTHS[text]
    if text == "0":
        return 0
    if not text.endswith("px"):
        return None
    try:
        number = float(text[:-2])
    except ValueError:
        return None
    if number < 0:
        raise _Invalid(reason)
    try:
        return _px(number, "column-rule")
    except _Invalid as exc:
        raise _Invalid(reason) from exc


def _read_box_shadow(
    winners, custom: dict, current: str, valid: bool
) -> tuple[tuple[bool, int, int, int, int, str], ...]:
    """Used shadows, outer first. An empty result paints nothing."""

    raw = _declared(winners, "box-shadow", custom)
    if raw is None:
        return ()
    keyword = " ".join(raw.split()).lower()
    if keyword in {"none", "initial", "unset", "revert"}:
        return ()
    if keyword == "inherit":
        raise _Invalid("box-shadow inherit is unsupported")
    return tuple(_one_shadow(layer, current, valid) for layer in _shadow_layers(raw))


def _shadow_layers(value: str) -> list[str]:
    layers: list[str] = []
    chunk: list[str] = []
    depth = 0
    for char in value:
        if char == "(":
            depth += 1
        elif char == ")" and depth:
            depth -= 1
        elif char == "," and depth == 0:
            layers.append("".join(chunk).strip())
            chunk = []
            continue
        chunk.append(char)
    if depth:
        raise _Invalid("box-shadow is invalid")
    layers.append("".join(chunk).strip())
    if not layers or any(not layer for layer in layers):
        raise _Invalid("box-shadow is invalid")
    return layers


def _shadow_tokens(layer: str) -> list[str]:
    tokens: list[str] = []
    chunk: list[str] = []
    depth = 0
    for char in layer.strip():
        if char == "(":
            depth += 1
            chunk.append(char)
            continue
        if char == ")" and depth:
            depth -= 1
            chunk.append(char)
            continue
        if char.isspace() and depth == 0:
            if chunk:
                tokens.append("".join(chunk))
                chunk = []
            continue
        chunk.append(char)
    if depth:
        raise _Invalid("box-shadow is invalid")
    if chunk:
        tokens.append("".join(chunk))
    if not tokens:
        raise _Invalid("box-shadow is invalid")
    return tokens


def _shadow_length(token: str) -> int | None:
    text = token.lower()
    if text in {"0", "+0", "-0", "0px", "+0px", "-0px"}:
        return 0
    if not text.endswith("px"):
        return None
    try:
        number = float(text[:-2])
    except ValueError:
        return None
    if number != number or number in {float("inf"), float("-inf")}:
        raise _Invalid("box-shadow is invalid")
    try:
        return _px(number, "box-shadow")
    except _Invalid as exc:
        raise _Invalid("box-shadow is invalid") from exc


def _shadow_color(token: str, *, current: str, valid: bool) -> str:
    if token.lower() == "currentcolor":
        if not valid:
            raise _Invalid("color is invalid")
        return current
    return _css_color_hex(token, reason="box-shadow is invalid")


def _one_shadow(layer: str, current: str, valid: bool) -> tuple[bool, int, int, int, int, str]:
    inset = False
    color: str | None = None
    lengths: list[int] = []
    for token in _shadow_tokens(layer):
        if token.lower() == "inset":
            if inset:
                raise _Invalid("box-shadow is invalid")
            inset = True
            continue
        length = _shadow_length(token)
        if length is not None:
            if len(lengths) >= 4 or (len(lengths) == 2 and length < 0):
                raise _Invalid("box-shadow is invalid")
            lengths.append(length)
            continue
        if color is not None:
            raise _Invalid("box-shadow is invalid")
        color = _shadow_color(token, current=current, valid=valid)
    if len(lengths) not in {2, 3, 4}:
        raise _Invalid("box-shadow is invalid")
    while len(lengths) < 4:
        lengths.append(0)
    if color is None:
        if not valid:
            raise _Invalid("color is invalid")
        color = current
    return inset, lengths[0], lengths[1], lengths[2], lengths[3], color


def _padding_box(box: _Box) -> tuple[int, int, int, int]:
    """Padding edge in the same space as the border box."""

    left = _solved_edge(box, "border_left")
    top = _solved_edge(box, "border_top")
    right = _solved_edge(box, "border_right")
    bottom = _solved_edge(box, "border_bottom")
    return (
        box.x + left,
        box.y + top,
        box.border_width - left - right,
        box.border_height - top - bottom,
    )


def _shadow_ink(box: _Box) -> list[dict[str, object]]:
    """Outset shadow shapes and inset holes. Blur stays a radius, not an outset."""

    pad_x, pad_y, pad_w, pad_h = _padding_box(box)
    recorded: list[dict[str, object]] = []
    for inset, offset_x, offset_y, blur, spread, color in box.shadows:
        if inset:
            item: dict[str, object] = {
                "inset": True,
                "geometry": "hole",
                "color": color,
                "offset_x": offset_x,
                "offset_y": offset_y,
                "blur": blur,
                "spread": spread,
                "x": pad_x + offset_x + spread,
                "y": pad_y + offset_y + spread,
                "width": pad_w - 2 * spread,
                "height": pad_h - 2 * spread,
                "clip_x": pad_x,
                "clip_y": pad_y,
                "clip_width": pad_w,
                "clip_height": pad_h,
            }
        else:
            item = {
                "inset": False,
                "geometry": "shape",
                "color": color,
                "offset_x": offset_x,
                "offset_y": offset_y,
                "blur": blur,
                "spread": spread,
                "x": box.x + offset_x - spread,
                "y": box.y + offset_y - spread,
                "width": box.border_width + 2 * spread,
                "height": box.border_height + 2 * spread,
            }
        recorded.append(item)
    return recorded


def _outline_ink(box: _Box) -> dict[str, object]:
    """Outer edge of the outline stroke, in the same space as the border box."""

    style, thickness, color, offset = box.outline or ("none", 0, "#000000", 0)
    outset = offset + thickness
    return {
        "style": style,
        "color": color,
        "thickness": thickness,
        "offset": offset,
        "x": box.x - outset,
        "y": box.y - outset,
        "width": box.border_width + 2 * outset,
        "height": box.border_height + 2 * outset,
    }


def _read_border_radius(winners, custom: dict) -> str:
    raw = _declared(winners, "border-radius", custom)
    if raw is None or raw in {"initial", "unset", "revert"}:
        return ""
    if raw == "inherit":
        raise _Invalid("border-radius inherit is unsupported")
    token = " ".join(raw.split())
    if not token:
        raise _Invalid("border-radius is invalid")
    return token


def _bind_border_curves(root: _Box) -> None:
    """Store used outer radii. An unparsable declaration rejects the document."""

    seen: set[int] = set()
    pending = [root]
    while pending:
        box = pending.pop()
        marker = id(box)
        if marker in seen:
            continue
        seen.add(marker)
        pending.extend((*box.positioned, *box.floats, *box.children, *box.atoms))
        if not box.border_radius:
            continue
        resolved = used_border_radii(box.border_width, box.border_height, box.border_radius)
        corners = resolved.get("corners")
        if resolved.get("outcome") != "resolved" or not isinstance(corners, dict):
            raise _Invalid("border-radius is invalid")
        radii: list[float] = []
        for name in ("top-left", "top-right", "bottom-right", "bottom-left"):
            corner = corners.get(name)
            if not isinstance(corner, dict):
                raise _Invalid("border-radius is invalid")
            horizontal = corner.get("outer_x")
            vertical = corner.get("outer_y")
            if isinstance(horizontal, bool) or isinstance(vertical, bool):
                raise _Invalid("border-radius is invalid")
            if not isinstance(horizontal, (int, float)) or not isinstance(vertical, (int, float)):
                raise _Invalid("border-radius is invalid")
            radii.append(float(horizontal))
            radii.append(float(vertical))
        if any(value > 0 for value in radii):
            box.border_curve = (
                radii[0],
                radii[1],
                radii[2],
                radii[3],
                radii[4],
                radii[5],
                radii[6],
                radii[7],
            )


def _bind_plane_transform(box: _Box, winners, custom: dict) -> None:
    """Reject a transform the hit tester cannot invert. ``none`` stays put."""

    if _active_transform(box) is None:
        return
    origin = _declared(winners, "transform-origin", custom)
    if origin is None or origin in {"initial", "unset", "revert", "revert-layer"}:
        box.transform_origin = "50% 50%"
    elif origin == "inherit":
        raise _Invalid("transform-origin inherit is unsupported")
    else:
        token = " ".join(origin.split())
        if not token:
            raise _Invalid("transform-origin is invalid")
        box.transform_origin = token
    mapped = map_transformed_point(
        {
            "x": 0,
            "y": 0,
            "width": 100,
            "height": 100,
            "transform": box.capture.get("transform", "none"),
            "origin": box.transform_origin,
        },
        {"x": 0, "y": 0},
    )
    if mapped.get("outcome") == "mapped":
        return
    if mapped.get("reason") == "origin":
        raise _Invalid("transform-origin is invalid")
    raise _Invalid("transform is invalid")


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
        _place_one_absolute(abs_box, cb, box, anchors)
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

    if not _block_container(box) or box.position != "static" or box.float_side != "none":
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
    box.border_width = (
        box.content_width + box.gutter_start + box.gutter_end + _edge_extent(box.solved, "left", "right")
    )
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
    _push_generated_text(tree, node, "before", before, size, parts, advances)
    _push_inline_text(node.text or "", size, parts, advances)
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
    _push_generated_text(tree, node, "after", after, size, parts, advances)
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
    _push_generated_text(tree, node, "before", before, size, parts, advances)
    _push_inline_text(node.text or "", size, parts, advances)
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
    _push_generated_text(tree, node, "after", after, size, parts, advances)


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
    wrapped = wrap_lines(
        text, measure, white_space=parent.white_space, advances=list(advances), **_spacing_args(parent),
        **_break_args(parent),
    )
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


_ANCHOR_SIZE_AXIS = {
    "width": "width",
    "min-width": "width",
    "max-width": "width",
    "height": "height",
    "min-height": "height",
    "max-height": "height",
}


def _anchor_size_text(value: object) -> bool:
    return isinstance(value, str) and value.strip().lower().startswith("anchor-size(")


def _apply_anchor_sizes(
    box: _Box,
    slots: dict[str, str],
    anchors: dict[str, _Box],
    cb: _Edge,
) -> None:
    """Replace anchor-size() sizing values with the anchor's border-box length."""

    queried = [prop for prop in _ANCHOR_SIZE_AXIS if _anchor_size_text(slots.get(prop))]
    if not queried:
        return
    if box.writing_mode != "horizontal-tb" or box.direction != "ltr":
        raise _Invalid("anchor-size is unsupported")
    for prop in queried:
        parsed = parse_anchor_size_call(slots[prop])
        if parsed.get("outcome") != "parsed":
            raise _Invalid(str(parsed.get("reason") or "anchor-size is invalid"))
        name = parsed.get("anchor") or box.position_anchor
        anchor = anchors.get(str(name)) if name else None
        if anchor is not None:
            if anchor.position in {"absolute", "fixed"} or anchor.float_side != "none":
                raise _Invalid("anchor is out of flow")
            if _box_contains(box, anchor):
                raise _Invalid("anchor is inside the positioned box")
            measured = {"width": anchor.border_width, "height": anchor.border_height}
        else:
            measured = None
        axis = _ANCHOR_SIZE_AXIS[prop]
        basis = cb.width if axis == "width" else cb.height
        resolved = resolve_anchor_size(
            measured,
            parsed.get("keyword"),
            used_in=prop,
            fallback=parsed.get("fallback"),
            containing_writing_mode="horizontal-tb",
            containing_direction="ltr",
            box_writing_mode=box.writing_mode,
            box_direction=box.direction,
            percentage_basis=basis,
            absolutely_positioned=True,
        )
        if resolved.get("outcome") not in {"resolved", "fallback"}:
            raise _Invalid(str(resolved.get("reason") or "anchor-size is invalid"))
        length = resolved.get("length")
        if isinstance(length, bool) or not isinstance(length, (int, float)) or float(length) < 0:
            raise _Invalid("anchor-size is invalid")
        slots[prop] = f"{length}px"


def _anchor_call_text(value: object) -> bool:
    return isinstance(value, str) and value.strip().lower().startswith("anchor(")


def _anchor_fallback_px(text: object, prop: str, cb: _Edge) -> tuple[float | None, bool]:
    """Pixels of a written fallback, and whether a percentage has no basis yet."""

    if text is None:
        return None, False
    token = str(text).strip().lower()
    if token.endswith("px"):
        return float(token[:-2]), False
    if token.endswith("%"):
        basis = cb.width if prop in {"left", "right"} else cb.height
        if basis is None:
            return None, True
        return float(basis) * float(token[:-1]) / 100.0, False
    raise _Invalid("anchor() is invalid")


def _apply_anchor_insets(
    box: _Box,
    slots: dict[str, str],
    anchors: dict[str, _Box],
    cb: _Edge,
) -> None:
    """Replace anchor() insets with the px length the absolute equation solves."""

    props = [side for side in ("top", "right", "bottom", "left") if _anchor_call_text(_inset(slots, side))]
    if not props:
        return
    if box.writing_mode != "horizontal-tb" or box.direction != "ltr":
        raise _Invalid("anchor() is unsupported")
    containing = {
        "x": cb.x,
        "y": cb.y,
        "width": cb.width,
        "height": 0 if cb.height is None else cb.height,
        "writing_mode": "horizontal-tb",
        "direction": "ltr",
    }
    for prop in props:
        parsed = parse_anchor_call(_inset(slots, prop))
        if parsed.get("outcome") != "parsed":
            raise _Invalid(str(parsed.get("reason") or "anchor() is invalid"))
        name = parsed.get("anchor") or box.position_anchor
        anchor = anchors.get(str(name)) if name else None
        if anchor is not None:
            if anchor.position in {"absolute", "fixed"} or anchor.float_side != "none":
                raise _Invalid("anchor is out of flow")
            if anchor.writing_mode != "horizontal-tb" or anchor.direction != "ltr":
                raise _Invalid("anchor() is unsupported")
            if _box_contains(box, anchor):
                raise _Invalid("anchor is inside the positioned box")
            measured: dict[str, object] | None = {
                "x": anchor.x,
                "y": anchor.y,
                "width": anchor.border_width,
                "height": anchor.border_height,
                "writing_mode": "horizontal-tb",
                "direction": "ltr",
            }
        else:
            measured = None
        if prop == "bottom" and cb.height is None and measured is not None:
            raise _Invalid("anchor containing block is indefinite")
        fallback, unresolved_fallback = _anchor_fallback_px(parsed.get("fallback"), prop, cb)
        if measured is None and fallback is None and not unresolved_fallback:
            raise _Invalid("default anchor is missing")
        resolved = used_anchor_inset(
            containing,
            measured,
            prop=prop,
            side=parsed.get("side"),
            fallback=fallback,
        )
        if resolved.get("outcome") != "resolved":
            if unresolved_fallback:
                raise _Invalid("anchor() is invalid")
            raise _Invalid(str(resolved.get("reason") or "anchor() is invalid"))
        length = resolved.get("length")
        if isinstance(length, bool) or not isinstance(length, (int, float)):
            raise _Invalid("anchor() is invalid")
        number = float(length)
        token = str(int(number)) if number == int(number) else str(number)
        slots[f"inset-{prop}"] = f"{token}px"


def _place_absolute_replaced(box: _Box, cb: _Edge, parent: _Box, anchors: dict[str, _Box]) -> None:
    """Give an out-of-flow replaced box its used size, then solve the insets."""

    if box.writing_mode != "horizontal-tb" or box.direction != "ltr":
        raise _Invalid("replaced writing mode is unsupported")
    if box.children or box.floats or box.positioned or box.atoms:
        raise _Invalid("positioned replaced element is unsupported")
    slots = _physical_slots(box)
    _apply_anchor_sizes(box, slots, anchors, cb)
    _apply_anchor_insets(box, slots, anchors, cb)
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
        padding_top=slots.get("padding-top", 0),
        padding_bottom=slots.get("padding-bottom", 0),
        border_left=_border_arg(slots, "left"),
        border_right=_border_arg(slots, "right"),
        border_top=_border_arg(slots, "top"),
        border_bottom=_border_arg(slots, "bottom"),
        box_sizing=_box_sizing(box),
        ratio_box=_replaced_ratio_box(box),
        intrinsic_width=box.intrinsic_width,
        intrinsic_height=box.intrinsic_height,
        intrinsic_ratio=_preferred_replaced_ratio(box),
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


def _place_one_absolute(
    box: _Box,
    cb: _Edge,
    parent: _Box,
    anchors: dict[str, _Box],
) -> None:
    if box.replaced:
        _place_absolute_replaced(box, cb, parent, anchors)
        return
    slots = _physical_slots(box)
    _apply_anchor_sizes(box, slots, anchors, cb)
    _apply_anchor_insets(box, slots, anchors, cb)
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
        if _subtree_generated_font(box):
            raise _Invalid("generated font is unsupported")
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


def _has_text_combine(box: _Box) -> bool:
    return any(piece.combine for piece in box.pieces)


def _text_combine_active(box: _Box) -> bool:
    return box.writing_mode in {"vertical-rl", "vertical-lr"} and _has_text_combine(box)


def _combine_layout(box: _Box) -> tuple[list[int], list[tuple[int, str]]]:
    """Per-character advances and each upright cluster's inline start."""

    text = box.inline_text or ""
    if any(character.isspace() for character in text):
        raise _Invalid("text-combine white space is unsupported")
    advances: list[int] = []
    clusters: list[tuple[int, str]] = []
    inline = 0
    for piece in box.pieces:
        if not piece.text:
            continue
        size = piece.font_size
        if size != box.font_size or piece.line_height != box.line_height:
            raise _Invalid("text-combine font is unsupported")
        if any(piece.extra) or piece.shifts or not _baseline_align(piece.vertical_align):
            raise _Invalid("text-combine glyph is unsupported")
        owners: dict[int, tuple[int, int]] = {}
        for start, end in piece.combine:
            if end - start < 2 or start < 0 or end > len(piece.text):
                raise _Invalid("text-combine is invalid")
            if size % (end - start) != 0:
                raise _Invalid("text-combine scale is not integral")
            for index in range(start, end):
                if _advance_of(piece.text[index], size) != size or index in owners:
                    raise _Invalid("text-combine glyph is unsupported")
                owners[index] = (start, end)
        index = 0
        while index < len(piece.text):
            span = owners.get(index)
            if span is None:
                step = _advance_of(piece.text[index], size)
                advances.append(step)
                inline += step
                index += 1
                continue
            start, end = span
            if index != start:
                raise _Invalid("text-combine is invalid")
            clusters.append((inline, piece.text[start:end]))
            advances.append(size)
            advances.extend(0 for _ in range(start + 1, end))
            inline += size
            index = end
    if len(advances) != len(text):
        raise _Invalid("text-combine is invalid")
    return advances, clusters


def _attach_upright_combine(line: _Line, box: _Box, column: int) -> None:
    """Paint each compressed run horizontally inside its one-em square."""

    records: list[dict[str, object]] = []
    for origin, text in _combine_layout(box)[1]:
        count = len(text)
        glyph = column // count
        if glyph < 1 or glyph * count != column:
            raise _Invalid("text-combine scale is not integral")
        pad = (column - glyph) // 2
        records.append(
            {
                "text": text,
                "x": 0,
                "y": origin,
                "width": column,
                "height": column,
                "glyphs": [
                    {
                        "text": character,
                        "x": index * glyph,
                        "y": origin + pad,
                        "width": glyph,
                        "height": glyph,
                    }
                    for index, character in enumerate(text)
                ],
            }
        )
    line.combines = records


def _shrink_advances(box: _Box) -> dict[str, int] | list[int]:
    text = box.inline_text or ""
    if _text_combine_active(box):
        return _combine_layout(box)[0]
    if _mixed_runs(box):
        styles = _style_stream(box.pieces)
        if len(styles) != len(text):
            raise _Invalid("inline run is invalid")
        extras = _extra_stream(box.pieces, len(text))
        return [_advance_of(ch, styles[index][0]) + extras[index] for index, ch in enumerate(text)]
    if _glyph_chrome(box):
        extras = _extra_stream(box.pieces, len(text))
        return [_advance_of(ch, box.font_size) + extras[index] for index, ch in enumerate(text)]
    return {ch: box.font_size * _default_advance(ch) for ch in set(text) | {" "}}


def _intrinsic_text_sizes(box: _Box) -> tuple[int, int]:
    text = box.inline_text or ""
    if (
        "\n" in text
        and _text_indent_each_line(box)
        and box.white_space in _FORCED_SEGMENT_WHITE
    ):
        saved = box.inline_text
        pairs: list[tuple[int, int]] = []
        try:
            for part in text.split("\n"):
                box.inline_text = part
                pairs.append(_intrinsic_text_sizes(box))
        finally:
            box.inline_text = saved
        return max(pair[0] for pair in pairs), max(pair[1] for pair in pairs)
    measured = wrap_lines(
        text,
        0,
        white_space=box.white_space,
        advances=_shrink_advances(box),
        clone_ranges=box.clone_ranges,
        **_spacing_args(box),
        **_break_args(box),
    )
    if measured["outcome"] != "wrapped":
        raise _Invalid(str(measured.get("reason") or "text measurement failed"))
    minimum = _px(measured["min_content"], "min-content")
    maximum = _px(measured["max_content"], "max-content")
    indent = _text_indent_used(box)
    if _text_indent_hanging(box):
        # The unwrapped line is not indented. A real wrap indents the remainder.
        if indent > 0 and maximum > minimum:
            return minimum + indent, maximum
        return minimum, maximum
    if indent > 0:
        return minimum + indent, maximum + indent
    if indent < 0:
        return minimum, max(0, maximum + indent)
    return minimum, maximum


def _fixed_float_outer(box: _Box) -> int:
    """Margin-box width of a float whose size does not depend on its container."""

    minimum, maximum = _float_child_span(box, reason="inline-block content is unsupported")
    if minimum != maximum:
        raise _Invalid("inline-block content is unsupported")
    return maximum


def _shrink_inline_block_floats(box: _Box, available: int) -> int:
    """Shrink-to-fit width when left floats lead the text or follow an earlier line.

    Earlier words take the full width. Later words sit beside the whole float
    run, so the preferred width is the wider of those two contributions.
    """

    pre_min = 0
    pre_max = 0
    post_min = 0
    post_max = 0
    float_max = 0
    beside = 0
    seen_float = False
    for item in box.flow or box.floats:
        if item.float_side != "none":
            outer = _fixed_float_outer(item)
            float_max = max(float_max, outer)
            beside += outer
            seen_float = True
            continue
        minimum, maximum = _float_child_span(item, reason="inline-block content is unsupported")
        if seen_float:
            post_min = max(post_min, minimum)
            post_max = max(post_max, maximum)
        else:
            pre_min = max(pre_min, minimum)
            pre_max = max(pre_max, maximum)
    minimum = max(pre_min, post_min, float_max)
    maximum = max(pre_max, post_max + beside, float_max, minimum)
    room = available if available > 0 else 0
    return min(max(minimum, room), maximum)


def _shrink_inline_block_atoms(box: _Box, available: int) -> int:
    """Shrink-to-fit width of text and nested inline-blocks on one line."""

    saved = box.content_width
    box.content_width = 100000
    try:
        measured = {atom.id: _measure_float(box, atom) for atom in box.atoms}
        entries = _atom_sources(box)
        source = "".join(item[0] for item in entries)
        wrapped = wrap_lines(
            source,
            0,
            white_space=box.white_space,
            advances=_atom_advances(entries, measured),
            **_spacing_args(box),
            **_break_args(box),
        )
    finally:
        box.content_width = saved
    if wrapped.get("outcome") != "wrapped":
        raise _Invalid(str(wrapped.get("reason") or "inline-block measurement failed"))
    minimum = _px(wrapped.get("min_content"), "min-content")
    maximum = _px(wrapped.get("max_content"), "max-content")
    room = available if available > 0 else 0
    return min(max(minimum, room), maximum)


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


def _preferred_replaced_ratio(box: _Box) -> float | None:
    """Width over height for a replaced box.

    A plain ``aspect-ratio`` replaces the intrinsic ratio. ``auto`` together
    with a ratio keeps that intrinsic ratio when both attributes supply it.
    """

    parsed = box.aspect_ratio
    if parsed is None:
        return None
    width_part, height_part, defer_to_natural = parsed
    if width_part <= 0.0 or height_part <= 0.0:
        return None
    if (
        defer_to_natural
        and box.intrinsic_width is not None
        and box.intrinsic_height is not None
        and box.intrinsic_height > 0
    ):
        return None
    return width_part / height_part


def _replaced_ratio_box(box: _Box) -> str:
    """A plain aspect-ratio maps the box-sizing box. ``auto`` maps content."""

    parsed = box.aspect_ratio
    if parsed is None:
        return "content"
    width_part, height_part, content_box = parsed
    if content_box or width_part <= 0.0 or height_part <= 0.0:
        return "content"
    return "border"


def _used_replaced(
    box: _Box,
    containing_width: int,
    containing_height: int | None,
    solved: dict,
) -> dict:
    if box.writing_mode != "horizontal-tb" or box.direction != "ltr":
        raise _Invalid("replaced writing mode is unsupported")
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
        padding_top=_px(solved.get("padding_top"), "padding-top"),
        padding_bottom=_px(solved.get("padding_bottom"), "padding-bottom"),
        border_left=_px(solved.get("border_left"), "border-left"),
        border_right=_px(solved.get("border_right"), "border-right"),
        border_top=_px(solved.get("border_top"), "border-top"),
        border_bottom=_px(solved.get("border_bottom"), "border-bottom"),
        box_sizing=_box_sizing(box),
        ratio_box=_replaced_ratio_box(box),
        intrinsic_width=box.intrinsic_width,
        intrinsic_height=box.intrinsic_height,
        intrinsic_ratio=_preferred_replaced_ratio(box),
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


def _finish_contained_height(box: _Box) -> None:
    if box.definite_height is None:
        box.definite_height = 0
    vertical = _edge_extent(box.solved, "top", "bottom")
    box.content_height = box.definite_height
    box.border_height = box.content_height + vertical


def _stamp_atom_line_baselines(box: _Box) -> None:
    """Give each shortened line the strut baseline the atomic box aligns to."""

    for child in box.children:
        if not child.lines:
            continue
        used = _used_line_height(child.line_height, child.font_size)
        _height, baseline = _strut_metrics(child.font_size, used)
        for line in child.lines:
            line.baseline = baseline


def _lay_atom_floats(box: _Box) -> None:
    """Lay a left float inside an inline-block and shorten the lines beside it."""

    if box.children:
        for child in box.children:
            _solve(child, box.content_width, box.definite_height, None, 0)
        _lay_sibling_floats(box, 0)
        _stamp_atom_line_baselines(box)
    else:
        _place_floats(box, 0)
        if box.definite_height is None:
            bottom = 0
            for fl in box.floats:
                if fl.float_band is not None:
                    bottom = max(bottom, fl.float_band[1] + fl.float_band[3])
            box.definite_height = bottom
    _finish_contained_height(box)


def _shrink_inline_flex(box: _Box, available: int) -> int:
    """Max-content width of a nowrap row whose items neither grow nor shrink."""

    spec = box.flex or {}
    if str(spec.get("direction") or "row") != "row" or str(spec.get("wrap") or "nowrap") != "nowrap":
        raise _Invalid("inline-flex shrink-to-fit is unsupported")
    sizes: list[int] = []
    for item in box.children:
        flex = item.flex if isinstance(item.flex, dict) else {}
        grow = flex.get("grow", 0.0)
        shrink = flex.get("shrink", 1.0)
        if isinstance(grow, bool) or isinstance(shrink, bool):
            raise _Invalid("inline-flex shrink-to-fit is unsupported")
        if not isinstance(grow, (int, float)) or not isinstance(shrink, (int, float)) or grow != 0 or shrink != 0:
            raise _Invalid("inline-flex shrink-to-fit is unsupported")
        specified = _main_size(_box_decl(item, "width"), "auto")
        if isinstance(specified, bool) or not isinstance(specified, (int, float, str)):
            raise _Invalid("inline-flex shrink-to-fit is unsupported")
        if isinstance(specified, str):
            if specified != "auto":
                raise _Invalid("inline-flex shrink-to-fit is unsupported")
            sizes.append(_flex_content_inline(item))
        else:
            sizes.append(_px(specified, "width"))
    preferred = _gapped_span(sizes, _px(spec.get("column_gap", 0), "flex gap"))
    room = available if available > 0 else 0
    return min(max(preferred, room), preferred)


def _finish_inline_flex(
    box: _Box, padding_top: int, padding_bottom: int, border_top: int, border_bottom: int
) -> None:
    if box.writing_mode != "horizontal-tb" or box.direction != "ltr":
        raise _Invalid("inline-flex writing mode is unsupported")
    _place_flex_row(box, 0)
    if box.definite_height is None:
        box.definite_height = 0
    box.content_height = box.definite_height
    box.border_height = box.content_height + padding_top + padding_bottom + border_top + border_bottom


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
    if fl.ruby:
        if not width_auto or not height_auto:
            raise _Invalid("ruby size is unsupported")
        if any(
            item != 0
            for item in (
                margin_left,
                margin_right,
                margin_top,
                margin_bottom,
                border_left,
                border_right,
                border_top,
                border_bottom,
                padding_left,
                padding_right,
                padding_top,
                padding_bottom,
            )
        ):
            raise _Invalid("ruby box is unsupported")
        pair = fl.ruby_pair
        if not isinstance(pair, dict):
            raise _Invalid("ruby is unsupported")
        content_width = int(pair["width"])
    elif width_auto:
        if _has_explicit_limit(fl, _WIDTH_LIMITS):
            raise _Invalid("float intrinsic limit is unsupported")
        if any(prop == "box-sizing" and value.strip().lower() == "border-box" for prop, value in fl.declarations):
            raise _Invalid("float shrink-to-fit box is unsupported")
        available = (
            box.content_width
            - margin_left
            - margin_right
            - border_left
            - border_right
            - padding_left
            - padding_right
        )
        if fl.display == "inline-flex":
            content_width = _shrink_inline_flex(fl, available)
        elif fl.floats:
            content_width = _shrink_inline_block_floats(fl, available)
        elif fl.atoms:
            content_width = _shrink_inline_block_atoms(fl, available)
        else:
            content_width = _shrink_float_width(fl, available)
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
    if fl.display == "inline-flex":
        _finish_inline_flex(fl, padding_top, padding_bottom, border_top, border_bottom)
        return {
            "outer_width": margin_left + fl.border_width + margin_right,
            "outer_height": margin_top + fl.border_height + margin_bottom,
            "margin_left": margin_left,
            "margin_top": margin_top,
        }
    if fl.floats:
        _lay_atom_floats(fl)
    elif fl.children:
        _lay_float_blocks(fl)
    else:
        if fl.inline_text or fl.atoms:
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
    if box.writing_mode != "horizontal-tb" or box.direction not in {"ltr", "rtl"}:
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


def _declared_px(box: _Box, name: str) -> int:
    """Author length. Auto and the initial value contribute nothing.

    The solved inline-end margin of a specified width absorbs leftover space
    in the full containing block. That slack is not part of the border box
    that has to fit beside a float.
    """

    raw = None
    for prop, value in box.declarations:
        if prop == name:
            raw = value
    if raw is None:
        return 0
    token = " ".join(str(raw).strip().lower().split())
    if token in {"auto", "initial", "unset", "revert", "revert-layer"}:
        return 0
    if token.endswith("px"):
        return _px(float(token[:-2]), name)
    raise _Invalid("flow-root beside a float is unsupported")


def _outer_inline_chrome(box: _Box) -> int:
    solved = box.solved
    return (
        _px(solved.get("margin_left"), "margin-left")
        + _px(solved.get("margin_right"), "margin-right")
        + _edge_extent(solved, "left", "right")
    )


def _commit_content_height(box: _Box) -> None:
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


def _refill_flow_root(box: _Box, content_width: int) -> None:
    auto = box.solved.get("content_height") == "auto"
    saved = box.definite_height
    box.content_width = content_width
    if auto:
        box.definite_height = None
    box.lines = []
    _fill_lines(box)
    if not auto:
        box.definite_height = saved
    _commit_content_height(box)


def _flow_root_slot(
    box: _Box,
    bands: list[tuple[int, int, int, int, str, str, float]],
    containing: int,
    start: int,
) -> tuple[int, int, int | None]:
    """Border y, left inset, and the automatic content width beside floats.

    ``None`` keeps the content width already solved. A specified width that
    does not fit the gap is tried again below the floats.
    """

    if any(band[5] for band in bands):
        raise _Invalid("flow-root beside a shaped float is unsupported")
    events = {start}
    for band in bands:
        bottom = band[1] + band[3]
        if bottom > start:
            events.add(bottom)
    specified = not _specified_auto(box.solved.get("specified_width"))
    chrome = _outer_inline_chrome(box)
    for y in sorted(events):
        left, right, _bottoms = _exclusion(y, 1, bands, containing)
        room = right - left
        if specified:
            outer = (
                box.content_width
                + _edge_extent(box.solved, "left", "right")
                + _declared_px(box, "margin-left")
                + _declared_px(box, "margin-right")
            )
            if outer <= room:
                return y, left, None
            continue
        content = room - chrome
        if content < 0:
            continue
        narrowed = None if left == 0 and right == containing else content
        return y, left, narrowed
    raise _Invalid("flow-root beside a float is unsupported")


def _place_flow_root_beside(
    box: _Box,
    bands: list[tuple[int, int, int, int, str, str, float]],
    containing: int,
    cursor: int,
    origin: int,
) -> int:
    if box.children or box.floats or box.atoms or _mixed_runs(box) or _relative_pieces(box):
        raise _Invalid("flow-root beside a float is unsupported")
    margin_top = _px(box.solved.get("margin_top"), "margin-top")
    margin_bottom = _px(box.solved.get("margin_bottom"), "margin-bottom")
    start = max(cursor + margin_top, _clear_floor(box.clear, bands))
    border_y, inset, narrowed = _flow_root_slot(box, bands, containing, start)
    if narrowed is None:
        _commit_content_height(box)
        if not _specified_auto(box.solved.get("specified_width")):
            left, right, _bottoms = _exclusion(border_y, 1, bands, containing)
            box.margin_right = (right - left) - box.content_width - _edge_extent(
                box.solved, "left", "right"
            ) - _declared_px(box, "margin-left")
            box.solved["margin_right"] = box.margin_right
    else:
        _refill_flow_root(box, narrowed)
    box.x += inset
    box.anchor_y = origin + border_y
    return border_y + box.border_height + margin_bottom


def _lay_sibling_floats(box: _Box, content_x: int) -> None:
    """Place floats in source order and shorten each following block's lines."""

    if box.writing_mode != "horizontal-tb" or box.direction != "ltr":
        raise _Invalid("float writing mode is unsupported")
    measured = {fl.id: _measure_float(box, fl) for fl in box.floats}
    for child in box.children:
        if child.display not in {"block", "flow-root"} or child.children or child.floats:
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
        if item.display == "flow-root":
            cursor = _place_flow_root_beside(item, bands, box.content_width, cursor, origin)
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
    if flow != "ltr" or box.writing_mode not in {"horizontal-tb", "vertical-rl", "vertical-lr"}:
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
    _reject_decoration_context(box)
    if box.nowrap_ranges:
        raise _Invalid("nowrap inline is unsupported")
    if _relative_pieces(box) and (
        _mixed_runs(box)
        or box.atoms
        or box.list_item
        or box.writing_mode != "horizontal-tb"
        or box.direction != "ltr"
        or box.white_space != "normal"
        or _gap_alignment(box)
        or box.text_indent != "0px"
        or box.letter_spacing
        or box.word_spacing
        or box.hanging_punctuation != "none"
    ):
        raise _Invalid("relative inline beside a float is unsupported")
    if _mixed_runs(box):
        _fill_mixed_beside_floats(box, bands, contain=contain)
        return
    _reject_balanced_context(box)
    text = box.inline_text or ""
    shift_rows: list[tuple[_Shift, ...]] | None = None
    if _relative_pieces(box):
        text, shift_rows = _collapse_shift_text(text, _source_shifts(box))
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
        wrapped = wrap_lines(
            remaining,
            max(available, 0),
            white_space=box.white_space,
            advances=advances,
            **_spacing_args(box),
            **_break_args(box),
        )
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
        if shift_rows is not None:
            if runs or not remaining.startswith(rendered):
                raise _Invalid("relative inline beside a float is unsupported")
            line_shifts = shift_rows[: len(rendered)]
            if len(line_shifts) != len(rendered):
                raise _Invalid("relative inline beside a float is unsupported")
            shift_rows = shift_rows[len(rendered) :]
            dropped = len(remaining) - len(rendered) - len(rest)
            if dropped < 0 or dropped > len(shift_rows):
                raise _Invalid("relative inline beside a float is unsupported")
            if dropped:
                shift_rows = shift_rows[dropped:]
            runs = _relative_runs(
                rendered,
                line_shifts,
                box.font_size,
                box.content_width,
                box.definite_height,
                content,
            )
        glyphs: list[dict[str, object]] = []
        if shift_rows is None and not runs:
            glyphs = _bidi_glyphs(rendered, box.direction, box.font_size, content)
        records.append(
            _Line(
                text=rendered,
                x=_px(left, "line x") + offset,
                y=cursor,
                height=height,
                content_width=used,
                glyphs=glyphs,
                runs=runs,
            )
        )
        remaining = rest
        cursor += height
    else:
        raise _Invalid("line break failed")
    if shift_rows:
        raise _Invalid("relative inline beside a float is unsupported")
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


def _baseline_align(value: str | int) -> bool:
    return value in {"baseline", 0}


def _nest_align(parent: str | int, own: str | int) -> str | int:
    """Child lengths add to a shifted parent. A keyword inside a shift is rejected."""

    if _baseline_align(parent):
        return "baseline" if _baseline_align(own) else own
    if _baseline_align(own):
        return parent
    if isinstance(parent, int) and isinstance(own, int):
        total = parent + own
        return "baseline" if total == 0 else total
    raise _Invalid("nested vertical-align is unsupported")


def _used_text_align(
    tree, element, styles, declarations, fonts: dict[str, str], parent_em: int
) -> str | int:
    """Used vertical-align of one non-replaced inline. The initial value is baseline."""

    custom = styles.get(element, ({}, ""))[0]
    raw = _declared(_winners(tree, element, declarations), "vertical-align", custom)
    if raw is None:
        return "baseline"
    chosen = _read_inline_align(
        raw,
        _positive_px(fonts["font-size"], "font-size"),
        fonts["line-height"],
        parent_em,
    )
    if chosen == 0:
        return "baseline"
    return chosen if isinstance(chosen, str) else int(chosen)


def _shifted_text(box: _Box) -> bool:
    return any(piece.text and not _baseline_align(piece.vertical_align) for piece in box.pieces)


def _reject_shifted_text(box: _Box) -> None:
    if not _shifted_text(box):
        return
    if box.writing_mode != "horizontal-tb" or box.direction != "ltr" or box.white_space not in {
        "normal",
        "nowrap",
        "pre-line",
    }:
        raise _Invalid("vertical-align is unsupported")


def _mixed_runs(box: _Box) -> bool:
    return any(
        run.font_size != box.font_size
        or run.line_height != box.line_height
        or not _baseline_align(run.vertical_align)
        for run in box.pieces
        if run.text
    )


def _style_stream(runs: list[_Piece]) -> list[tuple[int, str, str | int, tuple[tuple[str, int, str], ...]]]:
    styles: list[tuple[int, str, str | int, tuple[tuple[str, int, str], ...]]] = []
    for run in runs:
        align: str | int = "baseline" if _baseline_align(run.vertical_align) else run.vertical_align
        styles.extend((run.font_size, run.line_height, align, run.marks) for _ in run.text)
    return styles


def _advance_of(ch: str, size: int) -> int:
    return _px(size * _default_advance(ch), "advance")


def _collapse_styled(
    text: str, styles: list[tuple[int, str, str | int, tuple[tuple[str, int, str], ...]]]
) -> tuple[str, list[tuple[int, str, str | int, tuple[tuple[str, int, str], ...]]]]:
    pieces: list[str] = []
    chosen: list[tuple[int, str, str | int, tuple[tuple[str, int, str], ...]]] = []
    index = 0
    count = len(text)
    gap: tuple[int, str, str | int, tuple[tuple[str, int, str], ...]] | None = None
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
    styles: list[tuple[int, str, str | int, tuple[tuple[str, int, str], ...]]],
    rendered: str,
    white_space: str,
) -> tuple[
    list[tuple[int, str, str | int, tuple[tuple[str, int, str], ...]]],
    str,
    list[tuple[int, str, str | int, tuple[tuple[str, int, str], ...]]],
]:
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


def _group_runs(
    rendered: str, styles: list[tuple[int, str, str | int, tuple[tuple[str, int, str], ...]]]
) -> list[tuple[str, int, str, int, str | int]]:
    if len(rendered) != len(styles):
        raise _Invalid("inline font break is unsupported")
    groups: list[tuple[str, int, str, int, str | int]] = []
    for ch, (size, leading, align, _marks) in zip(rendered, styles, strict=True):
        width = _advance_of(ch, size)
        if groups and groups[-1][1] == size and groups[-1][2] == leading and groups[-1][4] == align:
            text, _, _, previous, _ = groups[-1]
            groups[-1] = (text + ch, size, leading, previous + width, align)
            continue
        groups.append((ch, size, leading, width, align))
    return groups


def _runs_line_height(
    box: _Box, groups: list[tuple[str, int, str, int, str | int]]
) -> tuple[int, int, list[int]]:
    boxes = []
    for index, (_text, size, leading, _width, align) in enumerate(groups):
        boxes.append(
            {
                "id": f"r{index}",
                "kind": "text",
                "vertical_align": align,
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
    placed = laid.get("boxes") if laid.get("outcome") == "resolved" else None
    if not isinstance(placed, list):
        raise _Invalid(str(laid.get("reason") or "line box failed"))
    by_id = {str(item.get("id")): item for item in placed if isinstance(item, dict)}
    tops: list[int] = []
    for index in range(len(groups)):
        item = by_id.get(f"r{index}")
        if not isinstance(item, dict):
            raise _Invalid("line box failed")
        tops.append(_px(item.get("top"), "text top"))
    return _px(laid.get("line_height"), "line height"), _px(laid.get("baseline"), "baseline"), tops


def _record_text_runs(
    groups: list[tuple[str, int, str, int, str | int]], tops: list[int]
) -> list[dict[str, object]]:
    aligned = any(group[4] != "baseline" for group in groups)
    runs: list[dict[str, object]] = []
    local = 0
    for (piece, size, _leading, width, _align), top in zip(groups, tops, strict=True):
        run: dict[str, object] = {"text": piece, "x": local, "font_size": size, "width": width}
        if aligned:
            run["y"] = top
        runs.append(run)
        local += width
    return runs


def _line_gap(
    y: int,
    line_height: int,
    bands: list[tuple[int, int, int, int, str, str, float] | None],
    containing: int,
) -> tuple[int, int, list[int], list[dict[str, object]] | None]:
    """Inline gap at one line. A shape uses that line's used height."""

    shaped = _shaped_float_payload(bands)
    if shaped is None:
        left, right, bottoms = _exclusion(y, line_height, bands, containing)
        return left, right, bottoms, None
    gap = shaped_gap_at(containing, shaped, line_height, y)
    if gap.get("outcome") != "placed":
        raise _Invalid(str(gap.get("reason") or "shape-outside is invalid"))
    return _px(gap.get("left"), "line x"), _px(gap.get("right"), "line x"), [], shaped


def _fill_mixed_beside_floats(
    box: _Box,
    bands: list[tuple[int, int, int, int, str, str, float]] | None = None,
    *,
    contain: bool = True,
) -> None:
    """Shorten mixed-font lines to a float margin box or its shape-outside."""

    _reject_decoration_context(box)
    if box.nowrap_ranges:
        raise _Invalid("nowrap inline is unsupported")
    _reject_balanced_context(box)
    text = box.inline_text or ""
    if "\t" in text:
        raise _Invalid("inline font tab is unsupported")
    if bands is None:
        bands = [fl.float_band for fl in box.floats if fl.float_placed and fl.float_band is not None]
    styles = _style_stream(box.pieces)
    if text and len(styles) != len(text):
        raise _Invalid("inline run is invalid")
    if not text or (box.white_space in _COLLAPSED_EMPTY and not text.strip()):
        box.lines = []
        if box.definite_height is None:
            box.definite_height = _band_bottom(bands) if contain else 0
        return
    records: list[_Line] = []
    cursor = 0
    remaining = text
    remaining_styles = styles
    strut = _strut_height(box.font_size, _used_line_height(box.line_height, box.font_size))
    for _ in range(10000):
        if not remaining or (box.white_space in _COLLAPSED_EMPTY and not remaining.strip()):
            break
        assumed = strut
        placed = False
        advanced = False
        for _attempt in range(4):
            left, right, bottoms, shaped = _line_gap(cursor, assumed, bands, box.content_width)
            available = right - left
            advances = [_advance_of(ch, remaining_styles[index][0]) for index, ch in enumerate(remaining)]
            wrapped = wrap_lines(
                remaining,
                max(available, 0),
                white_space=box.white_space,
                advances=advances,
                **_spacing_args(box),
                **_break_args(box),
            )
            lines = wrapped.get("lines") if wrapped.get("outcome") == "wrapped" else None
            if not isinstance(lines, list) or not lines or not isinstance(lines[0], dict):
                raise _Invalid(str(wrapped.get("reason") or "line break failed"))
            rendered = str(lines[0].get("text") or "")
            content = _px(lines[0].get("content_width"), "line width")
            obstructed = not (left == 0 and right == box.content_width)
            if available <= 0 or (content > available and obstructed):
                if shaped is not None:
                    found = seek_shaped_gap(box.content_width, shaped, assumed, cursor, content)
                    if found.get("outcome") != "placed":
                        raise _Invalid(str(found.get("reason") or "shape-outside is invalid"))
                    nxt = _px(found.get("y"), "float clearance")
                elif not bottoms:
                    raise _Invalid("line break failed")
                else:
                    nxt = min(bottoms)
                if nxt <= cursor:
                    raise _Invalid("line break failed")
                cursor = _px(nxt, "float clearance")
                advanced = True
                break
            if not rendered and content == 0:
                raise _Invalid("line break failed")
            line_styles, rest, rest_styles = _split_styled(
                remaining, remaining_styles, rendered, box.white_space
            )
            if rest == remaining:
                raise _Invalid("line break failed")
            groups = _group_runs(rendered, line_styles)
            height, baseline, tops = _runs_line_height(box, groups)
            if height != assumed:
                left2, right2, _bottoms2, _shaped2 = _line_gap(cursor, height, bands, box.content_width)
                if (left2, right2) != (left, right):
                    assumed = height
                    continue
            last = rest == "" or (box.white_space in _COLLAPSED_EMPTY and not rest.strip())
            offset = _text_offset(box, available, content, last)
            runs = _record_text_runs(groups, tops)
            records.append(
                _Line(
                    text=rendered,
                    x=_px(left, "line x") + offset,
                    y=cursor,
                    height=height,
                    content_width=content,
                    runs=runs,
                    baseline=baseline,
                    decorations=_styled_decorations(line_styles, rendered, baseline, content),
                )
            )
            remaining = rest
            remaining_styles = rest_styles
            cursor += height
            placed = True
            break
        if placed or advanced:
            continue
        raise _Invalid("line break failed")
    else:
        raise _Invalid("line break failed")
    box.lines = records
    if box.definite_height is None:
        box.definite_height = max(cursor, _band_bottom(bands)) if contain else cursor


def _styled_decorations(
    styles: list[tuple[int, str, str | int, tuple[tuple[str, int, str], ...]]],
    rendered: str,
    baseline: int,
    content: int,
) -> list[dict[str, object]]:
    if not any(item[3] for item in styles):
        return []
    return _text_decorations(
        rendered,
        [item[3] for item in styles],
        [_advance_of(ch, item[0]) for ch, item in zip(rendered, styles, strict=True)],
        baseline,
        content,
    )


def _fill_mixed(box: _Box) -> None:
    _reject_decoration_context(box)
    if box.nowrap_ranges:
        raise _Invalid("nowrap inline is unsupported")
    _reject_balanced_context(box)
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
        wrapped = wrap_lines(
            remaining,
            box.content_width,
            white_space=box.white_space,
            advances=advances,
            **_spacing_args(box),
            **_break_args(box),
        )
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
        height, baseline, tops = _runs_line_height(box, groups)
        last = rest == "" or (box.white_space in _COLLAPSED_EMPTY and not rest.strip())
        offset = _text_offset(box, box.content_width, content, last)
        runs = _record_text_runs(groups, tops)
        records.append(
            _Line(
                text=rendered,
                x=offset,
                y=cursor,
                height=height,
                content_width=content,
                runs=runs,
                baseline=baseline,
                decorations=_styled_decorations(line_styles, rendered, baseline, content),
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


def _atomic_content_baseline(atom: _Box) -> int | None:
    """Last in-flow line baseline, measured from the atomic content top."""

    atom_top = _edge_extent(atom.solved, "top")
    found: int | None = None

    def visit(box: _Box) -> None:
        nonlocal found
        if box is not atom and (box.float_side != "none" or box.position in {"absolute", "fixed"}):
            return
        if box.lines:
            if box is atom:
                origin = 0
            else:
                if box.anchor_y is None:
                    raise _Invalid("inline-block baseline is invalid")
                origin = box.anchor_y + _edge_extent(box.solved, "top") - atom_top
            chosen = box.lines[-1]
            if box is atom and box.ruby and len(box.lines) >= 2:
                chosen = box.lines[1]
            found = origin + chosen.y + chosen.baseline
        for child in box.children:
            visit(child)

    visit(atom)
    return found


def _atom_edges(parent: _Box, atom: _Box, row: dict[str, int]) -> tuple[int, int]:
    solved = atom.solved
    margin_top = row["margin_top"]
    margin_bottom = _float_margin(atom, "margin-bottom", parent.content_width)
    border_top = _px(solved.get("border_top"), "border-top")
    border_bottom = _px(solved.get("border_bottom"), "border-bottom")
    padding_top = _px(solved.get("padding_top"), "padding-top")
    padding_bottom = _px(solved.get("padding_bottom"), "padding-bottom")
    if atom.overflow != "visible":
        return row["outer_height"], 0
    content_base = _atomic_content_baseline(atom)
    if content_base is None:
        return row["outer_height"], 0
    above = margin_top + border_top + padding_top + content_base
    below = atom.content_height - content_base + padding_bottom + border_bottom + margin_bottom
    if below < 0:
        raise _Invalid("inline-block baseline is invalid")
    return above, below


def _script_shift(parent_em: int, kind: str) -> int:
    """Nearest pixel of the css-inline-3 script ratios of the parent em.

    ``super`` raises by one third of that em. ``sub`` lowers by one fifth.
    This engine has no font file, so the offset is the ratio rather than an
    OpenType superscript position.
    """

    em = _px(parent_em, "font-size")
    if em <= 0:
        raise _Invalid("vertical-align is unsupported")
    if kind == "super":
        return (em + 1) // 3
    if kind == "sub":
        return -((em + 2) // 5)
    raise _Invalid("vertical-align is unsupported")


def _read_inline_align(
    value: str | None, font_size: int, line_height: str, parent_em: int
) -> str | float:
    """Used vertical-align for an inline-block. The initial value is baseline."""

    if value is None or value in {"initial", "unset", "revert", "baseline"}:
        return "baseline"
    if value == "inherit":
        raise _Invalid("vertical-align inherit is unsupported")
    token = value.strip().lower()
    if token in {"top", "bottom", "middle", "text-top", "text-bottom", "baseline"}:
        return token
    if token in {"sub", "super"}:
        return _script_shift(parent_em, token)
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
    groups: list[tuple[str, int, str, int, str | int]],
    atoms_here: list[tuple[_Box, int]],
    measured: dict[str, dict[str, int]],
) -> tuple[int, int, list[int]]:
    payload: list[dict[str, object]] = []
    for index, (_text, size, leading, _width, align) in enumerate(groups):
        payload.append(
            {
                "id": f"t{index}",
                "kind": "text",
                "vertical_align": align,
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
    text_tops: list[int] = []
    for index in range(len(groups)):
        item = placed.get(f"t{index}")
        if not isinstance(item, dict):
            raise _Invalid("line box failed")
        text_tops.append(_px(item.get("top"), "text top"))
    tops: list[int] = []
    for index, _atom in enumerate(atoms_here):
        item = placed.get(f"a{index}")
        if not isinstance(item, dict):
            raise _Invalid("line box failed")
        tops.append(_px(item.get("top"), "atom top"))
    return height, baseline, tops, text_tops


def _fill_inline_blocks(box: _Box) -> None:
    """Place inline-blocks as atomic line items around the parent's text."""

    _reject_decoration_context(box)
    if box.nowrap_ranges:
        raise _Invalid("nowrap inline is unsupported")
    _reject_balanced_context(box)
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
        **_spacing_args(box),
            **_break_args(box),
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


def _atom_sources(
    box: _Box,
) -> list[tuple[str, int, str, str | int, _Box | None, tuple[tuple[str, int, str], ...]]]:
    entries: list[tuple[str, int, str, str | int, _Box | None, tuple[tuple[str, int, str], ...]]] = []
    serial = 0
    for piece in box.pieces:
        align: str | int = "baseline" if _baseline_align(piece.vertical_align) else piece.vertical_align
        if piece.atom is None:
            for ch in piece.text:
                if ch in "\t\r\n" or ch == _ZWSP or _MARK <= ord(ch) <= _MARK + 31:
                    raise _Invalid("inline-block break is unsupported")
                entries.append((ch, piece.font_size, piece.line_height, align, None, piece.marks))
            continue
        mark = chr(_MARK + serial)
        serial += 1
        entries.append((_ZWSP, piece.font_size, piece.line_height, "baseline", None, ()))
        entries.append((mark, piece.font_size, piece.line_height, "baseline", piece.atom, ()))
        entries.append((_ZWSP, piece.font_size, piece.line_height, "baseline", None, ()))
    if serial != len(box.atoms):
        raise _Invalid("inline-block is unsupported")
    return entries


def _atom_advances(
    entries: list[tuple[str, int, str, str | int, _Box | None, tuple[tuple[str, int, str], ...]]],
    measured: dict[str, dict[str, int]],
) -> list[int]:
    advances: list[int] = []
    for ch, size, _leading, _align, atom, _marks in entries:
        if ch == _ZWSP:
            advances.append(0)
        elif atom is not None:
            advances.append(measured[atom.id]["outer_width"])
        else:
            advances.append(_advance_of(ch, size))
    return advances


def _match_atom_line(
    entries: list[tuple[str, int, str, str | int, _Box | None, tuple[tuple[str, int, str], ...]]],
    index: int,
    rendered: str,
) -> tuple[list[tuple[str, int, str, str | int, _Box | None, tuple[tuple[str, int, str], ...]]], int]:
    chosen: list[tuple[str, int, str, str | int, _Box | None, tuple[tuple[str, int, str], ...]]] = []
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
    groups: list[tuple[str, int, str, int, str | int]] = []
    runs: list[dict[str, object]] = []
    atom_records: list[dict[str, object]] = []
    atoms_here: list[tuple[_Box, int]] = []
    cursor = 0
    buf = ""
    buf_size = 0
    buf_leading = ""
    buf_align: str | int = "baseline"
    buf_width = 0
    buf_x = 0
    events: list[tuple] = []

    def flush() -> None:
        nonlocal buf, buf_width
        if not buf:
            return
        groups.append((buf, buf_size, buf_leading, buf_width, buf_align))
        runs.append({"text": buf, "x": buf_x, "font_size": buf_size, "width": buf_width})
        buf = ""
        buf_width = 0

    for ch, size, leading, align, atom, marks in chosen:
        if ch == _ZWSP:
            continue
        if atom is not None:
            flush()
            row = measured[atom.id]
            border_x = cursor + row["margin_left"]
            atoms_here.append((atom, border_x))
            atom_records.append({"id": atom.id, "x": border_x, "width": row["outer_width"]})
            events.append(("gap", row["outer_width"]))
            cursor += row["outer_width"]
            placed.add(atom.id)
            continue
        advance = _advance_of(ch, size)
        events.append(("text", advance, marks))
        if buf and (size != buf_size or leading != buf_leading or align != buf_align):
            flush()
        if not buf:
            buf_x = cursor
            buf_size = size
            buf_leading = leading
            buf_align = align
        buf += ch
        buf_width += advance
        cursor += advance
    flush()
    if cursor != content:
        raise _Invalid("inline-block line is invalid")
    height, above, tops, text_tops = _line_extent(box, groups, atoms_here, measured)
    if len(text_tops) != len(runs):
        raise _Invalid("inline-block line is invalid")
    shifted = any(group[4] != "baseline" for group in groups)
    for run, text_top in zip(runs, text_tops, strict=True):
        if shifted or text_top:
            run["y"] = text_top
    offset = _text_offset(box, measure, content, last)
    for (atom, border_x), top in zip(atoms_here, tops, strict=True):
        atom.local_x = left + offset + border_x
        atom.local_y = cursor_y + top + measured[atom.id]["margin_top"]
    visible = "".join(
        ch for ch, _size, _leading, _align, atom, _marks in chosen if atom is None and ch != _ZWSP
    )
    decorations: list[dict[str, object]] = []
    if any(event[0] == "text" and event[2] for event in events):
        try:
            decorations = paint_decoration_events(events, above)
        except DecorationError as exc:
            raise _Invalid(exc.reason) from exc
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
            decorations=decorations,
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

    _reject_decoration_context(box)
    if box.nowrap_ranges:
        raise _Invalid("nowrap inline is unsupported")

    _reject_balanced_context(box)
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
            **_spacing_args(box),
            **_break_args(box),
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
        last = not any(ch.strip() and ch != _ZWSP for ch, _size, _leading, _align, _atom, _marks in rest)
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


_ELLIPSIS = "\u2026"


def _reject_line_clamp(box: _Box, direction: str) -> None:
    if box.line_clamp is None:
        return
    if box.writing_mode != "horizontal-tb" or direction != "ltr":
        raise _Invalid("clamped writing mode is unsupported")
    if box.white_space not in {"normal", "nowrap", "pre-line"}:
        raise _Invalid("clamped white-space is unsupported")
    if box.letter_spacing or box.word_spacing:
        raise _Invalid("clamped spacing is unsupported")
    if box.text_indent != "0px":
        raise _Invalid("clamped text-indent is unsupported")
    if box.text_wrap_style in {"balance", "pretty"}:
        raise _Invalid("clamped text wrap is unsupported")
    if _gap_alignment(box):
        raise _Invalid("clamped justification is unsupported")
    if box.floats or box.atoms or _mixed_runs(box) or _relative_pieces(box) or box.list_item:
        raise _Invalid("clamped block content is unsupported")


def _clamp_advances(box: _Box) -> dict[str, int]:
    raw = _shrink_advances(box)
    if not isinstance(raw, dict):
        raise _Invalid("clamped block content is unsupported")
    table = {key: _px(value, "advance") for key, value in raw.items()}
    table.setdefault(_ELLIPSIS, _advance_of(_ELLIPSIS, box.font_size))
    return table


def _clamp_width(box: _Box, table: dict[str, int], text: str) -> int:
    total = 0
    for ch in text:
        total += table[ch] if ch in table else _advance_of(ch, box.font_size)
    return total


def _clamp_plain_lines(
    box: _Box,
    records: list[_Line],
    measure: int,
    direction: str,
    place_glyphs: bool,
) -> list[_Line]:
    """Drop lines past ``line-clamp`` and end the last kept line with an ellipsis."""

    limit = box.line_clamp
    if limit is None or len(records) <= limit:
        return records
    kept = list(records[:limit])
    last = kept[-1]
    table = _clamp_advances(box)
    mark = _clamp_width(box, table, _ELLIPSIS)
    if mark > measure:
        raise _Invalid("line clamp does not fit")
    prefix = last.text
    while prefix and _clamp_width(box, table, prefix) + mark > measure:
        prefix = prefix[:-1]
    rendered = prefix + _ELLIPSIS
    content = _clamp_width(box, table, rendered)
    if content > measure:
        raise _Invalid("line clamp does not fit")
    offset, used, runs = _align_content(box, measure, rendered, content, True, direction)
    glyphs = _bidi_glyphs(rendered, direction, box.font_size, used) if place_glyphs and not runs else []
    kept[-1] = _Line(
        text=rendered,
        truncated=True,
        x=offset,
        y=last.y,
        height=last.height,
        content_width=used,
        baseline=last.baseline,
        glyphs=glyphs,
        runs=runs,
    )
    return kept


def _ruby_element_display(value: str | None) -> bool:
    """True for a ruby box's own display, not for ``display: inline``."""

    if value is None:
        return True
    return value.strip().lower() == "ruby"


def _ruby_advance(text: str, size: int) -> int:
    total = 0
    for ch in text:
        total += _advance_of(ch, size)
    return total


def _ruby_annotation_run(box: _Box, tree, node, styles, declarations) -> dict[str, object]:
    """One ``rt`` run, with its own strut and no nested content."""

    if (node.tail or "").strip():
        raise _Invalid("ruby base is unsupported")
    if any(_local_name(child) for child in tree.children.get(node, [])):
        raise _Invalid("ruby annotation is unsupported")
    text = node.text or ""
    if not text or any(ch.isspace() for ch in text):
        raise _Invalid("ruby annotation is unsupported")
    fonts = _inline_fonts(tree, node, styles, declarations, _fonts(box))
    if fonts.get("text-transform", "none") != "none":
        raise _Invalid("ruby spacing is unsupported")
    size = _positive_px(fonts["font-size"], "font-size")
    height, baseline = _strut_metrics(size, _used_line_height(fonts["line-height"], size))
    return {"text": text, "width": _ruby_advance(text, size), "height": height, "baseline": baseline}


def _bind_ruby(box: _Box, tree, element, styles, declarations) -> None:
    """Record the base, the annotation above it, and an optional one under it."""

    if box.writing_mode != "horizontal-tb" or box.direction != "ltr":
        raise _Invalid("ruby writing mode is unsupported")
    if box.white_space != "normal":
        raise _Invalid("ruby white-space is unsupported")
    if box.position != "static" or box.float_side != "none":
        raise _Invalid("ruby position is unsupported")
    if box.text_transform != "none" or box.letter_spacing or box.word_spacing:
        raise _Invalid("ruby spacing is unsupported")
    base = element.text or ""
    if not base or any(ch.isspace() for ch in base):
        raise _Invalid("ruby base is unsupported")
    nodes = [node for node in tree.children.get(element, []) if _local_name(node)]
    if not nodes or len(nodes) > 2 or any(_local_name(node) != "rt" for node in nodes):
        raise _Invalid("ruby annotation is unsupported")
    runs = [_ruby_annotation_run(box, tree, node, styles, declarations) for node in nodes]
    over = runs[0]
    under = runs[1] if len(runs) == 2 else None
    base_size = box.font_size
    base_height, base_baseline = _strut_metrics(base_size, _used_line_height(box.line_height, base_size))
    base_width = _ruby_advance(base, base_size)
    under_width = int(under["width"]) if under is not None else 0
    pair: dict[str, object] = {
        "base": base,
        "annotation": over["text"],
        "width": max(base_width, int(over["width"]), under_width),
        "base_width": base_width,
        "anno_width": over["width"],
        "base_height": base_height,
        "anno_height": over["height"],
        "base_baseline": base_baseline,
        "anno_baseline": over["baseline"],
    }
    if under is not None:
        pair["under"] = under["text"]
        pair["under_width"] = under["width"]
        pair["under_height"] = under["height"]
        pair["under_baseline"] = under["baseline"]
    box.ruby_pair = pair


def _paint_ruby_lines(box: _Box) -> None:
    pair = box.ruby_pair
    if not isinstance(pair, dict):
        raise _Invalid("ruby is unsupported")
    width = int(pair["width"])
    if box.content_width != width:
        raise _Invalid("ruby width is unsupported")
    anno_height = int(pair["anno_height"])
    base_height = int(pair["base_height"])
    anno_width = int(pair["anno_width"])
    base_width = int(pair["base_width"])
    under_width = int(pair["under_width"]) if "under" in pair else 0
    under_height = int(pair["under_height"]) if "under" in pair else 0
    if anno_width > width or base_width > width or under_width > width:
        raise _Invalid("ruby width is unsupported")
    lines = [
        _Line(
            text=str(pair["annotation"]),
            x=(width - anno_width) // 2,
            y=0,
            height=anno_height,
            content_width=anno_width,
            baseline=int(pair["anno_baseline"]),
        ),
        _Line(
            text=str(pair["base"]),
            x=(width - base_width) // 2,
            y=anno_height,
            height=base_height,
            content_width=base_width,
            baseline=int(pair["base_baseline"]),
        ),
    ]
    if "under" in pair:
        lines.append(
            _Line(
                text=str(pair["under"]),
                x=(width - under_width) // 2,
                y=anno_height + base_height,
                height=under_height,
                content_width=under_width,
                baseline=int(pair["under_baseline"]),
            )
        )
    box.lines = lines
    box.definite_height = anno_height + base_height + under_height
    box.content_height = box.definite_height


def _reject_text_box_trim(box: _Box) -> None:
    """Keep em-box trimming on one horizontal auto-height run of plain text."""

    if box.writing_mode != "horizontal-tb" or box.direction != "ltr":
        raise _Invalid("text-box-trim writing mode is unsupported")
    if box.display not in {"block", "flow-root"}:
        raise _Invalid("text-box-trim display is unsupported")
    if box.solved.get("content_height") not in {None, "auto"}:
        raise _Invalid("text-box-trim specified height is unsupported")
    if box.white_space != "normal":
        raise _Invalid("text-box-trim white-space is unsupported")
    if (
        box.text_indent != "0px"
        or box.letter_spacing
        or box.word_spacing
        or box.hanging_punctuation != "none"
        or box.text_wrap_style not in {"auto", "wrap"}
        or box.line_clamp is not None
        or box.initial_letter
        or box.list_item
        or box.floats
        or box.atoms
        or box.children
        or box.aspect_ratio is not None
        or _mixed_runs(box)
        or _relative_pieces(box)
        or _gap_alignment(box)
        or _has_decoration(box)
    ):
        raise _Invalid("text-box-trim content is unsupported")


def _apply_text_box_trim(box: _Box) -> None:
    """Drop leading outside the named text edge on the first and last lines.

    ``text`` meets the em box. ``cap`` and ``ex`` continue into the em by the
    synthetic metric. The line top stays at the content start. A start trim
    shortens the first line and pulls every later line up. An end trim
    shortens only the last line. The block's automatic height is the trimmed
    stack.
    """

    if box.text_box_trim == "none" or not box.lines:
        return
    used = _used_line_height(box.line_height, box.font_size)
    height, baseline = _strut_metrics(box.font_size, used)
    trim = box.text_box_trim
    over, under = box.text_box_edge
    start_lead = max(0, baseline - box.font_size)
    end_lead = max(0, height - baseline)
    start = (
        start_lead + _over_metric_inset(box.font_size, over)
        if trim in {"trim-start", "trim-both"}
        else 0
    )
    end = end_lead + _under_metric_inset(under) if trim in {"trim-end", "trim-both"} else 0
    if start == 0 and end == 0:
        return
    for line in box.lines:
        if line.height != height or line.baseline != baseline:
            raise _Invalid("text-box-trim line metrics are unsupported")
    first = box.lines[0]
    last = box.lines[-1]
    if start:
        first.height -= start
        first.baseline -= start
        for line in box.lines[1:]:
            line.y -= start
    if end:
        last.height -= end
    if first.height < 1 or last.height < 1 or first.baseline < 0:
        raise _Invalid("text-box-trim is unsupported")


def _fill_lines(box: _Box) -> None:
    if box.emphasis_mark and (box.floats or box.atoms or box.ruby or _mixed_runs(box) or box.children):
        raise _Invalid("text emphasis is unsupported")
    if box.text_box_trim != "none":
        _reject_text_box_trim(box)
    _reject_text_autospace(box)
    if box.ruby:
        _paint_ruby_lines(box)
        return
    if box.floats and any(atom.ruby for atom in box.atoms):
        raise _Invalid("ruby beside a float is unsupported")
    _reject_nowrap_context(box)
    _reject_shifted_text(box)
    _reject_glyph_chrome(box)
    _reject_line_clamp(box, box.direction)
    _reject_spacing(box)
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
        if _mixed_runs(box):
            raise _Invalid("relative inline font is unsupported")
    if box.atoms:
        if box.floats:
            _fill_atoms_beside_floats(box)
            return
        _fill_inline_blocks(box)
        return
    if box.floats and not box.children:
        _fill_lines_beside_floats(box)
        return
    if _mixed_runs(box):
        _fill_mixed(box)
        return
    box.lines = _plain_lines(box, box.content_width, box.direction, place_glyphs=True)
    _apply_text_box_trim(box)
    if box.definite_height is None:
        end = 0
        if box.lines:
            tail = box.lines[-1]
            end = tail.y + tail.height
        cap_height = 0 if box.drop_cap is None else int(box.drop_cap["height"])
        if end or cap_height:
            box.definite_height = max(end, cap_height)


def _bidi_glyphs(text: str, direction: str, font_size: int, content: int) -> list[dict[str, object]]:
    """Visual x of one line when UAX #9 order differs from the source text.

    ``x`` is the distance from the line's left edge. Characters removed by
    bidi controls are omitted. A line whose visual string matches its source
    returns nothing, so an already-left-to-right line stays a plain line.
    """

    if direction not in {"ltr", "rtl"} or not text:
        return []
    order, _ = bidi_line_order(text, direction)
    visual = "".join(text[i] for i in order)
    if visual == text:
        return []
    glyphs: list[dict[str, object]] = []
    cursor = 0
    for ch in visual:
        width = _advance_of(ch, font_size)
        glyphs.append({"ch": ch, "x": cursor, "width": width})
        cursor += width
    return glyphs if cursor == content else []


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
        glyphs = _bidi_glyphs(rendered, direction, box.font_size, content) if place_glyphs and not runs else []
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


def _indented_wrap(
    box: _Box,
    text: str,
    measure: int,
    indent: int,
    *,
    hanging: bool = False,
    each_line: bool = False,
) -> list:
    """Wrap one run, or each preserved segment when ``each-line`` is set.

    A plain indent shortens the first line of a segment. ``hanging`` shortens
    every later line of that segment and leaves its first line on the full
    measure. A preserved newline starts a new segment only for ``each-line``.
    """

    if each_line and "\n" in text and box.white_space in _FORCED_SEGMENT_WHITE:
        lines: list = []
        for segment in text.split("\n"):
            lines.extend(_indented_segment(box, segment, measure, indent, hanging=hanging))
        return lines
    return _indented_segment(box, text, measure, indent, hanging=hanging)


def _affected_indent(line: object, index: int, hanging: bool) -> bool:
    if isinstance(line, dict) and "indented" in line:
        return bool(line["indented"])
    return (hanging and index > 0) or (not hanging and index == 0)


def _indented_segment(box: _Box, text: str, measure: int, indent: int, *, hanging: bool) -> list:
    head = measure if hanging else measure - indent
    tail_measure = measure - indent if hanging else measure
    if head < 0:
        head = 0
    if tail_measure < 0:
        tail_measure = 0
    advances = _shrink_advances(box)
    lines = _kept_lines(
        box,
        wrap_lines(
            text, head, white_space=box.white_space, advances=advances, **_spacing_args(box),
            **_break_args(box),
        ),
    )
    if not lines:
        return []
    first = lines[0]
    if not isinstance(first, dict):
        raise _Invalid("line is invalid")
    first["indented"] = not hanging
    rest = _drop_prefix(text, str(first.get("text") or ""), box.white_space)
    if not rest or (box.white_space in _COLLAPSED_EMPTY and not rest.strip()):
        return [first]
    tail = _kept_lines(
        box,
        wrap_lines(
            rest, tail_measure, white_space=box.white_space, advances=advances, **_spacing_args(box),
            **_break_args(box),
        ),
    )
    for line in tail:
        if isinstance(line, dict):
            line["indented"] = hanging
    return [first, *tail]


def _reject_initial_letter_context(box: _Box, horizontal: bool) -> None:
    """Keep the drop cap on one horizontal left-to-right block of plain text."""

    if (
        not horizontal
        or box.direction != "ltr"
        or box.display not in {"block", "flow-root"}
        or box.position != "static"
        or box.float_side != "none"
        or box.white_space != "normal"
        or box.children
        or box.floats
        or box.atoms
        or box.positioned
        or box.list_item
        or box.replaced
        or not box.inline_text
        or box.letter_spacing
        or box.word_spacing
        or box.text_indent != "0px"
        or box.hanging_punctuation != "none"
        or box.text_wrap_style not in {"auto", "wrap"}
        or box.line_clamp is not None
        or box.font_family
        or box.text_align not in {"start", "left"}
        or box.multicol is not None
        or _mixed_runs(box)
        or _relative_pieces(box)
        or _glyph_chrome(box)
        or box.nowrap_ranges
        or _gap_alignment(box)
    ):
        raise _Invalid("initial letter is unsupported")


def _cap_exclusion_lines(
    box: _Box, text: str, measure: int, cap_width: int, sink: int
) -> tuple[list, list]:
    """Wrap the first ``sink`` lines in the gap beside the square, then the rest."""

    short = measure - cap_width
    if short < 0:
        raise _Invalid("initial letter is unsupported")
    advances = _shrink_advances(box)
    beside: list = []
    rest = text
    for _ in range(sink):
        if not rest or (box.white_space in _COLLAPSED_EMPTY and not rest.strip()):
            break
        wrapped = _kept_lines(
            box,
            wrap_lines(
                rest,
                short,
                white_space=box.white_space,
                advances=advances,
                **_spacing_args(box),
                **_break_args(box),
            ),
        )
        if not wrapped:
            break
        first = wrapped[0]
        if not isinstance(first, dict):
            raise _Invalid("line is invalid")
        content = _px(first.get("content_width"), "line width")
        if content > short:
            raise _Invalid("initial letter is unsupported")
        beside.append(first)
        rest = _drop_prefix(rest, str(first.get("text") or ""), box.white_space)
    tail: list = []
    if rest and not (box.white_space in _COLLAPSED_EMPTY and not rest.strip()):
        tail = _kept_lines(
            box,
            wrap_lines(
                rest,
                max(measure, 0),
                white_space=box.white_space,
                advances=advances,
                **_spacing_args(box),
                **_break_args(box),
            ),
        )
    return beside, tail


def _prepare_drop_cap(
    box: _Box, text: str, measure: int, strut: int
) -> tuple[list, int, int, int]:
    """Pull the first ASCII letter into a square and wrap what remains.

    The square's side is the size. Lines beside it are the sink. A size
    taller than the sink keeps the square on the content origin and starts
    the first line lower by the uncovered lines.
    """

    collapsed = " ".join(text.split())
    if not collapsed or not collapsed[0].isascii() or not collapsed[0].isalpha():
        raise _Invalid("initial letter is unsupported")
    if strut < 1:
        raise _Invalid("initial letter is unsupported")
    size = box.initial_letter
    sink = box.initial_sink or size
    if sink < 1 or sink > size:
        raise _Invalid("initial letter is unsupported")
    side = size * strut
    if side > measure:
        raise _Invalid("initial letter is unsupported")
    rest = collapsed[1:]
    if rest.startswith(" "):
        rest = rest[1:]
    box.drop_cap = {"text": collapsed[0], "x": 0, "y": 0, "width": side, "height": side}
    beside, tail = _cap_exclusion_lines(box, rest, measure, side, sink)
    return [*beside, *tail], side, len(beside), (size - sink) * strut


def _has_decoration(box: _Box) -> bool:
    return any(piece.marks for piece in box.pieces)


def _reject_decoration_context(box: _Box) -> None:
    """Keep decoration on horizontal left-to-right lines whose advances match the text."""

    if not _has_decoration(box):
        return
    if box.writing_mode != "horizontal-tb" or box.direction != "ltr":
        raise _Invalid("text decoration is unsupported")
    if box.white_space != "normal" or box.text_align not in {"start", "left"}:
        raise _Invalid("text decoration is unsupported")
    if (
        box.letter_spacing
        or box.word_spacing
        or box.text_indent != "0px"
        or box.floats
        or box.list_item
        or box.initial_letter
        or box.line_clamp is not None
        or box.text_wrap_style not in {"auto", "wrap"}
        or _relative_pieces(box)
        or _gap_alignment(box)
    ):
        raise _Invalid("text decoration is unsupported")
    if any(piece.text and not _baseline_align(piece.vertical_align) for piece in box.pieces):
        raise _Invalid("text decoration is unsupported")


def _source_marks(box: _Box) -> list[tuple[tuple[str, int, str], ...]]:
    marks: list[tuple[tuple[str, int, str], ...]] = []
    for piece in box.pieces:
        if piece.atom is not None:
            raise _Invalid("text decoration is unsupported")
        marks.extend((piece.marks,) * len(piece.text))
    text = box.inline_text or ""
    if len(marks) != len(text):
        raise _Invalid("text decoration is unsupported")
    return marks


def _collapse_mark_text(
    text: str, marks: list[tuple[tuple[str, int, str], ...]]
) -> tuple[str, list[tuple[tuple[str, int, str], ...]]]:
    if len(marks) != len(text):
        raise _Invalid("text decoration is unsupported")
    chars: list[str] = []
    chosen: list[tuple[tuple[str, int, str], ...]] = []
    index = 0
    count = len(text)
    gap: tuple[tuple[str, int, str], ...] | None = None
    while index < count:
        if text[index].isspace():
            if gap is None:
                gap = marks[index]
            index += 1
            continue
        if chars:
            if gap is None:
                raise _Invalid("text decoration is unsupported")
            chars.append(" ")
            chosen.append(gap)
        gap = None
        while index < count and not text[index].isspace():
            chars.append(text[index])
            chosen.append(marks[index])
            index += 1
    return "".join(chars), chosen


def _text_decorations(
    text: str,
    marks: list[tuple[tuple[str, int, str], ...]],
    advances: list[int],
    baseline: int,
    content: int,
) -> list[dict[str, object]]:
    if not any(marks):
        return []
    if len(text) != len(marks) or len(text) != len(advances) or sum(advances) != content:
        raise _Invalid("text decoration is unsupported")
    events = [("text", width, mark) for width, mark in zip(advances, marks, strict=True)]
    try:
        return paint_decoration_events(events, baseline)
    except DecorationError as exc:
        raise _Invalid(exc.reason) from exc


_EMPHASIS_PROPERTIES = ("text-emphasis", "text-emphasis-style", "text-emphasis-position")


def _emphasis_authored(winners) -> bool:
    return any(_latest_declared(winners, name) is not None for name in _EMPHASIS_PROPERTIES)


def _read_text_emphasis(winners, custom: dict, fonts: dict[str, str]) -> tuple[str, str]:
    raw_shorthand = _latest_declared(winners, "text-emphasis")
    raw_style = _latest_declared(winners, "text-emphasis-style")
    if raw_shorthand is not None and raw_style is not None:
        raise _Invalid("text emphasis is invalid")
    style = _declared(winners, "text-emphasis", custom)
    if style is None:
        style = _declared(winners, "text-emphasis-style", custom)
    position = _declared(winners, "text-emphasis-position", custom)
    parent_mark = fonts.get("text-emphasis-mark", "")
    parent_position = fonts.get("text-emphasis-position", "over")
    try:
        mark = resolve_emphasis_style(style, parent_mark)
        side = resolve_emphasis_position(position, parent_position)
    except EmphasisError as exc:
        raise _Invalid(exc.reason) from exc
    return mark, side


def _reject_emphasis_layout(box: _Box) -> None:
    if (
        box.writing_mode != "horizontal-tb"
        or box.direction != "ltr"
        or box.white_space != "normal"
        or box.letter_spacing
        or box.word_spacing
        or box.text_indent != "0px"
        or box.hanging_punctuation != "none"
        or box.line_clamp is not None
        or box.text_box_trim != "none"
        or box.initial_letter
        or box.hyphens == "auto"
        or box.hyphenate_character != "\u2010"
        or box.floats
        or box.atoms
        or box.ruby
        or _gap_alignment(box)
        or _relative_pieces(box)
        or _mixed_runs(box)
        or not box.color_valid
    ):
        raise _Invalid("text emphasis is unsupported")


def _apply_text_emphasis(box: _Box, records: list[_Line]) -> list[_Line]:
    if not box.emphasis_mark or not records:
        return records
    _reject_emphasis_layout(box)
    band = emphasis_band(box.font_size)
    over = box.emphasis_position == "over"
    cursor = 0
    for line in records:
        total = 0
        marks: list[dict[str, object]] = []
        strut = line.height
        for ch in line.text:
            advance = _advance_of(ch, box.font_size)
            if advance > 0 and not ch.isspace():
                marks.append(
                    {
                        "text": box.emphasis_mark,
                        "x": total + max(0, (advance - band) // 2),
                        "y": 0 if over else strut,
                        "width": band,
                        "height": band,
                        "color": box.color,
                    }
                )
            total += advance
        if total != line.content_width:
            raise _Invalid("text emphasis is unsupported")
        if over:
            line.baseline += band
        line.height = strut + band
        line.y = cursor
        line.emphasis = marks
        cursor += line.height
    return records


def _plain_lines(box: _Box, measure: int, direction: str, *, place_glyphs: bool = False) -> list[_Line]:
    _reject_decoration_context(box)
    _reject_spacing(box)
    text = box.inline_text or ""
    if not text:
        return []
    _reject_nowrap_context(box)
    _reject_line_clamp(box, direction)
    text_indent = _text_indent_used(box)
    hanging_indent = _text_indent_hanging(box)
    if text_indent and direction != "ltr":
        raise _Invalid("text-indent writing mode is unsupported")
    shifted = _relative_pieces(box)
    if shifted and box.white_space != "normal":
        raise _Invalid("relative inline is unsupported")
    used = _used_line_height(box.line_height, box.font_size)
    height, baseline = _strut_metrics(box.font_size, used)
    indent = _inside_marker_indent(box)
    if indent and box.nowrap_ranges:
        raise _Invalid("nowrap inline is unsupported")
    if text_indent and indent:
        raise _Invalid("text-indent beside a marker is unsupported")
    if text_indent and _mixed_runs(box):
        raise _Invalid("text-indent is unsupported")
    if indent and (_MARKER_SENTINEL in text or _MARKER_BREAK in text):
        raise _Invalid("inside marker content is unsupported")
    if indent and (box.letter_spacing or box.word_spacing):
        raise _Invalid("spaced marker is unsupported")
    if box.text_wrap_style in {"balance", "pretty"} and (
        text_indent or indent or shifted or box.writing_mode != "horizontal-tb" or box.direction != "ltr"
    ):
        if box.text_wrap_style == "balance":
            raise _Invalid("balanced text wrap is unsupported")
        raise _Invalid("pretty text wrap is unsupported")
    cap_width = 0
    beside_count = 0
    cap_raise = 0
    if box.initial_letter:
        lines, cap_width, beside_count, cap_raise = _prepare_drop_cap(box, text, measure, height)
    elif indent:
        lines = _kept_lines(
            box,
            wrap_lines(
                _MARKER_SENTINEL + _MARKER_BREAK + text,
                measure,
                white_space=box.white_space,
                advances=[indent, 0, *[_advance_of(character, box.font_size) for character in text]],
                **_break_args(box),
            ),
        )
    elif text_indent:
        lines = _indented_wrap(
            box,
            text,
            measure,
            text_indent,
            hanging=hanging_indent,
            each_line=_text_indent_each_line(box),
        )
    else:
        lines = _kept_lines(
            box,
            _measure_lines(box, text, measure, advances=_shrink_advances(box)),
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
    mark_text = ""
    collapsed_marks: list[tuple[tuple[str, int, str], ...]] | None = None
    if _has_decoration(box):
        mark_text, collapsed_marks = _collapse_mark_text(text, _source_marks(box))
    records: list[_Line] = []
    cursor = cap_raise
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
        if beside_count and index < beside_count:
            line_measure = max(measure - cap_width, 0)
            origin = cap_width
        elif text_indent and _affected_indent(line, index, hanging_indent):
            line_measure = measure - text_indent
            if line_measure < 0:
                line_measure = 0
            origin = text_indent
        offset, used, runs = _align_content(box, line_measure, rendered, content, index == last, direction)
        glyphs = _bidi_glyphs(rendered, direction, box.font_size, content) if place_glyphs and not runs else []
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
        line_marks: list[tuple[tuple[str, int, str], ...]] = []
        if collapsed_marks is not None:
            if rendered and not mark_text.startswith(rendered):
                raise _Invalid("text decoration is unsupported")
            line_marks = collapsed_marks[: len(rendered)]
            mark_text = mark_text[len(rendered) :]
            collapsed_marks = collapsed_marks[len(rendered) :]
            if mark_text.startswith(" "):
                mark_text = mark_text[1:]
                collapsed_marks = collapsed_marks[1:]
        decorations = _text_decorations(
            rendered,
            line_marks,
            [_advance_of(ch, box.font_size) for ch in rendered],
            baseline,
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
                decorations=decorations,
            )
        )
        cursor += height
    if shifted and collapsed.strip():
        raise _Invalid("relative inline is unsupported")
    if collapsed_marks is not None and mark_text.strip():
        raise _Invalid("text decoration is unsupported")
    return _apply_text_emphasis(box, _clamp_plain_lines(box, records, measure, direction, place_glyphs))


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

    if generate:
        _reject_generated_font(tree, element)
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


def _flex_has_preserved_break(item: _Box) -> bool:
    """True when this flex item's white space keeps a newline as a line break.

    A tab is still refused: the flex max-content path does not own tab stops.
    """

    text = item.inline_text or ""
    if item.white_space not in {"pre", "pre-wrap", "break-spaces", "pre-line"}:
        return False
    if "\t" in text:
        raise _Invalid("flex preserved break is unsupported")
    return "\n" in text or "\r" in text


def _flex_content_inline(item: _Box) -> int:
    """Max-content inline size. A preserved newline uses the longest line."""

    if _flex_has_preserved_break(item):
        return _intrinsic_text_sizes(item)[1]
    return _text_main(item.inline_text or "", item.font_size, item.letter_spacing, item.word_spacing)


def _flex_preserved_block_size(item: _Box, measure: int) -> int:
    """Stacked strut height of the forced lines at ``measure``."""

    measured = wrap_lines(
        item.inline_text or "",
        measure,
        white_space=item.white_space,
        advances=_shrink_advances(item),
        **_spacing_args(item),
        **_break_args(item),
    )
    lines = measured.get("lines")
    if measured.get("outcome") != "wrapped" or not isinstance(lines, list):
        raise _Invalid(str(measured.get("reason") or "flex preserved break is unsupported"))
    if not lines:
        return 0
    return _strut_height(item.font_size, _used_line_height(item.line_height, item.font_size)) * len(lines)


def _flex_anonymous_text(raw: str, white_space: str) -> str | None:
    if white_space in {"normal", "nowrap"}:
        collapsed = " ".join(raw.split())
        return collapsed or None
    if white_space == "pre-line":
        if not raw.strip():
            return None
        if "\t" in raw:
            raise _Invalid("flex preserved break is unsupported")
        if "\n" in raw or "\r" in raw:
            return raw
        return " ".join(raw.split())
    if white_space in {"pre", "pre-wrap", "break-spaces"}:
        if not raw.strip():
            return None
        if "\t" in raw:
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
            letter_spacing=host.letter_spacing,
            word_spacing=host.word_spacing,
            text_transform=host.text_transform,
            tab_size=host.tab_size,
            white_space=host.white_space,
            overflow_wrap=host.overflow_wrap,
            word_break=host.word_break,
            hyphens=host.hyphens,
            hyphenate_character=host.hyphenate_character,
            lang=host.lang,
            hanging_punctuation=host.hanging_punctuation,
            text_wrap_style=host.text_wrap_style,
            font_family=host.font_family,
            font_weight=host.font_weight,
            font_style=host.font_style,
            parent_direction=host.direction,
            color=host.color,
            color_valid=host.color_valid,
            emphasis_mark=host.emphasis_mark,
            emphasis_position=host.emphasis_position,
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


def _text_main(text: str, font_size: int, letter: int = 0, word: int = 0) -> int:
    if not letter and not word:
        return sum(_advance_of(ch, font_size) for ch in text)
    width = 0
    seen = False
    for character in text:
        if seen:
            width += letter
        width += _advance_of(character, font_size)
        if character == " ":
            width += word
        seen = True
    return width


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
    if item.inline_text and (not column or _flex_has_preserved_break(item)):
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
        preserved = _flex_has_preserved_break(item)
        text_width = (
            _intrinsic_text_sizes(item)[1]
            if preserved
            else _text_main(text, item.font_size, item.letter_spacing, item.word_spacing)
        )
        if preserved:
            specified_width = _main_size(_box_decl(item, "width"), "auto")
            block_measure = (
                _px(specified_width, "width")
                if column
                and isinstance(specified_width, (int, float))
                and not isinstance(specified_width, bool)
                else text_width
            )
            text_height = _flex_preserved_block_size(item, block_measure)
        else:
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
_GRID_ALIGN = frozenset(
    {
        "normal",
        "stretch",
        "start",
        "end",
        "center",
        "space-between",
        "space-around",
        "space-evenly",
        "flex-start",
        "flex-end",
    }
)
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
    align = "normal"
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
            align = _choice(value, "normal", _GRID_ALIGN, prop)
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
        "align": align,
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


def _grid_content_shift(container: int, sizes: list[int], gap: int, keyword: str) -> tuple[int, int]:
    """Leading offset and extra gutter after the tracks have their used sizes."""

    packed = pack_grid_content(container, sizes, gap, keyword)
    if packed.get("outcome") != "packed":
        raise _Invalid(str(packed.get("reason") or "grid content alignment is invalid"))
    return (
        _px(packed.get("leading"), "grid content alignment"),
        _px(packed.get("extra"), "grid content alignment"),
    )


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
    column_leading, column_extra = _grid_content_shift(
        box.content_width,
        column_sizes,
        column_gap,
        str(spec.get("justify") or "normal"),
    )
    text_heights = _measure_grid_items(
        box,
        located,
        column_sizes,
        column_gap,
        content_x,
        viewport_height,
        column_leading,
        column_extra,
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
    block_size = specified_height if specified_height is not None else _gapped_span(row_sizes, row_gap)
    row_leading, row_extra = _grid_content_shift(
        block_size,
        row_sizes,
        row_gap,
        str(spec.get("align") or "normal"),
    )
    for item in box.children:
        entry = located.get(item.id)
        if entry is None:
            raise _Invalid("grid placement failed")
        row = int(entry.get("row") or 0) - 1
        row_span = int(entry.get("row_span") or 0)
        specified = (item.grid or {}).get("height", "auto")
        area = _grid_span(row_sizes, row, row_span, row_gap + row_extra)
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
            + row_leading
            + _grid_offset(row_sizes, row, row_gap + row_extra)
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
            stretch=grid_content_stretches(str(spec.get("justify") or "normal")),
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
    leading: int = 0,
    extra: int = 0,
) -> dict[str, int]:
    heights: dict[str, int] = {}
    for item in box.children:
        entry = located.get(item.id)
        if entry is None:
            raise _Invalid("grid placement failed")
        column = int(entry.get("column") or 0) - 1
        column_span = int(entry.get("column_span") or 0)
        area = _grid_span(column_sizes, column, column_span, column_gap + extra)
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
        item.x = (
            content_x
            + leading
            + _grid_offset(column_sizes, column, column_gap + extra)
            + _px(aligned.get("start"), "grid item")
        )
        item.border_width = item.content_width + chrome_x
        if (item.grid or {}).get("column_subgrid"):
            if leading or extra:
                raise _Invalid("subgrid content alignment is unsupported")
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
