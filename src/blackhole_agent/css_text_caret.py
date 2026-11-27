"""Visual grapheme cells for horizontal text painting and DOM caret hits."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import NamedTuple
from xml.etree.ElementTree import Element

from blackhole_agent.css_bidi import bidi_line_order
from blackhole_agent.css_line_break import _Tok, source_line_tokens


class _Cell(NamedTuple):
    start: int
    stop: int
    width: int
    rtl: bool


def _visual_cells(text: str, tokens: Sequence[_Tok], direction: str, font_size: int) -> list[_Cell]:
    """Group visual indices by grapheme while retaining their logical boundaries."""
    order, levels = bidi_line_order(text, direction)
    owner: list[int] = []
    stops: dict[int, int] = {}
    first = 0
    for i, token in enumerate(tokens):
        if token.grapheme_start:
            first = i
        owner.append(first)
        stops[first] = i + 1
    widths: dict[int, int] = {}
    for i in order:
        first = owner[i]
        widths[first] = widths.get(first, 0) + int(tokens[i].advance * font_size)
    return [_Cell(i, stops[i], width, bool(levels[i] % 2)) for i, width in widths.items()]


def ellipsis_glyphs(
    text: str, direction: str, font_size: int, width: int, available: int,
) -> list[dict[str, object]] | None:
    """Paint an overflowing uniform line. Coordinates are relative to its full left edge."""
    tokens = source_line_tokens(text, "pre", (text,))
    if not tokens or "\t" in text:
        return None
    cells = _visual_cells(text, tokens, direction, font_size)
    if sum(cell.width for cell in cells) != width:
        return None
    rtl = direction == "rtl"
    kept: list[tuple[str, int]] = []
    used = 0
    for cell in reversed(cells) if rtl else cells:
        # The inline-start character must survive, even when the edge clips it.
        if used and used + cell.width + font_size > available:
            break
        kept.append((text[cell.start:cell.stop], cell.width))
        used += cell.width
    if used < available:
        kept.append(("\u2026", font_size))
        used += font_size
    x = width - used if rtl else 0
    glyphs = []
    for ch, advance in reversed(kept) if rtl else kept:
        glyphs.append({"ch": ch, "x": x, "width": advance})
        x += advance
    return glyphs


def uniform_caret_edge(
    source: str,
    lines: Sequence[str],
    white_space: str,
    direction: str,
    font_size: int,
    width: int,
    x: float,
    *,
    hyphen_mark: str = "",
) -> tuple[int, bool] | None:
    """Return (source character index, after) on the last line, at x from its painted text edge.

    ``hyphen_mark`` is the string painted at a taken hyphen break. Those glyphs
    are not extra source characters; they still occupy caret cells.
    """
    if not lines or not 0 <= x < width or "\t" in lines[-1]:
        return None
    tokens = source_line_tokens(source, white_space, lines, hyphen_mark=hyphen_mark)
    if not tokens:
        return None
    cells = _visual_cells(lines[-1], tokens, direction, font_size)
    if sum(cell.width for cell in cells) != width:
        return None
    for cell in cells:
        if x < cell.width:
            after = (x >= cell.width / 2) != cell.rtl
            return (tokens[cell.stop - 1].end - 1 if after else tokens[cell.start].start), after
        x -= cell.width
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
