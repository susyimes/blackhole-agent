"""Map a horizontal text cell to its source character and DOM text offset."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from xml.etree.ElementTree import Element

from blackhole_agent.css_bidi import bidi_line_order
from blackhole_agent.css_line_break import source_line_tokens


def uniform_caret_edge(
    source: str, lines: Sequence[str], white_space: str, direction: str, font_size: int, width: int, x: float
) -> tuple[int, bool] | None:
    """Return (source character index, after) on the last line, at x from its painted text edge."""
    if not lines or not 0 <= x < width or "\t" in lines[-1]:
        return None
    tokens = source_line_tokens(source, white_space, lines)
    if not tokens:
        return None
    order, levels = bidi_line_order(lines[-1], direction)
    # A grapheme can contain several code points. Keep both caret edges on
    # its source boundaries even when some members occupy no painted width.
    owner: list[int] = []
    ends: dict[int, int] = {}
    first = 0
    for i, token in enumerate(tokens):
        if token.grapheme_start:
            first = i
        owner.append(first)
        ends[first] = token.end
    # Insertion order is physical paint order, including repeated characters.
    widths: dict[int, float] = {}
    for i in order:
        first = owner[i]
        widths[first] = widths.get(first, 0) + tokens[i].advance * font_size
    if sum(widths.values()) != width:
        return None
    for first, advance in widths.items():
        if x < advance:
            # On an odd embedding level the physical left edge is the logical end.
            after = (x >= advance / 2) != bool(levels[first] % 2)
            return (ends[first] - 1 if after else tokens[first].start), after
        x -= advance
    return None


def _text_nodes(element: Element) -> Iterator[tuple[tuple[Element, bool], str]]:
    """DOM textContent order. ElementTree stores text following a child on its tail."""
    if element.text:
        yield (element, False), element.text
    for child in element:
        if isinstance(child.tag, str):
            yield from _text_nodes(child)
        if child.tail:
            yield (child, True), child.tail


def element_text_offset(element: Element, origin: tuple[Element, bool], boundary: int) -> int | None:
    """Convert a boundary in the original text node to UTF-16 units from the element start."""
    offset = 0
    for node, text in _text_nodes(element):
        if node == origin:
            return offset + len(text[:boundary].encode("utf-16-le", "surrogatepass")) // 2
        offset += len(text.encode("utf-16-le", "surrogatepass")) // 2
    return None
