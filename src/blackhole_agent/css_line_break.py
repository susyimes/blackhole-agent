"""Wrap one inline into CSS Text line boxes.

CSS Text Level 3 collapses or preserves white space, then breaks the line at
the farthest soft wrap opportunity that fits. This reader does that for a
single inline: no bidi reordering, no shaping, and no font fallback.

A collapsible segment break (U+000A under normal or nowrap) becomes one space,
except it disappears when both neighbors have East Asian width F, W, or H and
neither is Hangul. That is the Level 3 rule left to the UA; it is the rule
that reproduces the spec's English, Korean, and Chinese examples. U+000D is a
space, not a segment break. hyphens:auto has no dictionary, so only U+00AD
introduces a hyphenation opportunity. line-break:auto uses the normal
strictness list. Tab stops are multiples of the space advance measured from
the line's content start. ``letter_spacing`` is inserted between grapheme
clusters and is not applied after the last cluster on a line. ``word_spacing``
is added to each space and to each other Unicode Zs separator.

``balance_lines`` is CSS Text Level 4 ``text-wrap-style: balance``. Forced
line breaks split the block into independent groups. A group keeps the
first-fit breaks when it has fewer than two lines or more than ten, or when
wrapping is not allowed. Otherwise the breaks are a partition into that same
number of lines. The partition that strictly lowers the population variance
of leftover inline space (the measure minus each line's content width) wins.
A tie keeps the first-fit breaks. Emergency breaks are not rearranged.
"""

from __future__ import annotations

import math
import unicodedata
from dataclasses import dataclass

_EPS = 1e-9
_BALANCE_LINE_CAP = 10
_BALANCE_NODE_CAP = 200_000
_WHITES = frozenset({"normal", "nowrap", "pre", "pre-wrap", "break-spaces", "pre-line"})
_OVERFLOWS = frozenset({"normal", "break-word", "anywhere"})
_WORDS = frozenset({"normal", "keep-all", "break-all", "break-word"})
_LINES = frozenset({"auto", "loose", "normal", "strict", "anywhere"})
_HYPHENS = frozenset({"none", "manual", "auto"})
_COLLAPSE = frozenset({"normal", "nowrap", "pre-line"})
_WRAPS = frozenset({"normal", "pre-wrap", "break-spaces", "pre-line"})
_AFTER_HYPHEN = frozenset("-\u2010\u2013")
_WAVEDASH = frozenset("\u301c\u30a0")
_LOOSE_HYPHEN = frozenset("\u2010\u2013")
_ITERATION = frozenset("\u3005\u303b\u309d\u309e\u30fd\u30fe")
_SMALL_KANA = frozenset(
    "ぁぃぅぇぉっゃゅょゎゕゖァィゥェォッャュョヮヵヶ\u30fc"
)
_CJ = _ITERATION | _SMALL_KANA
_INSEPARABLE = frozenset("\u2025\u2026")
_CENTERED = frozenset("\u30fb\uff1a\uff1b\uff65\u203c\u2047\u2048\u2049\uff01\uff1f")
_AFTER_CLOSING = frozenset("，。、」』】）》〉〕〗〙〛")
_HANGUL = (
    (0x1100, 0x11FF),
    (0x3130, 0x318F),
    (0xA960, 0xA97F),
    (0xAC00, 0xD7AF),
    (0xD7B0, 0xD7FF),
)


class _Invalid(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass
class _Tok:
    kind: str
    ch: str
    advance: float
    collapsible: bool = False
    grapheme_start: bool = True
    letter_spacing: float = 0.0
    word_spacing: float = 0.0


class _Adv:
    def __init__(self, text: str, raw: object) -> None:
        self.kind = "none"
        self.map: dict[str, float] = {}
        self.list: list[float] = []
        if raw is None:
            return
        if isinstance(raw, dict):
            self.kind = "dict"
            for key, value in raw.items():
                if not isinstance(key, str) or len(key) != 1:
                    raise _Invalid("advances keys must be single characters")
                self.map[key] = _nonneg(value, f"advance of {key!r}")
            return
        if isinstance(raw, (list, tuple)) and not isinstance(raw, (str, bytes)):
            if len(raw) != len(text):
                raise _Invalid("advances must match the text length")
            self.kind = "list"
            self.list = [_nonneg(value, f"advance {index}") for index, value in enumerate(raw)]
            return
        raise _Invalid("advances must be a mapping or a list")

    def of(self, ch: str, index: int) -> float:
        if self.kind == "dict":
            return self.map[ch] if ch in self.map else _default_advance(ch)
        if self.kind == "list":
            return self.list[index]
        return _default_advance(ch)

    def space(self) -> float:
        if self.kind == "dict" and " " in self.map:
            return self.map[" "]
        return 1.0

    def at(self, index: int) -> float:
        """Width of one collapsed space taken from this source index.

        A dict or omitted map keeps the single space advance. A per-character
        list uses the advance stored at the whitespace that survived.
        """

        if self.kind == "list":
            return self.list[index]
        return self.space()


def wrap_lines(
    text: object,
    width: object,
    *,
    white_space: object = "normal",
    overflow_wrap: object = "normal",
    word_break: object = "normal",
    line_break: object = "auto",
    hyphens: object = "manual",
    tab_size: object = 8,
    lang: object = "",
    advances: object = None,
    letter_spacing: object = 0,
    word_spacing: object = 0,
) -> dict[str, object]:
    """Wrap ``text`` into line boxes of ``width``.

    Each line reports the rendered ``text`` (hanging spaces included, trimmed
    collapsible spaces omitted, an unused soft hyphen omitted), the
    ``content_width`` that was tested against the measure, and ``width``
    including hanging advances. ``min_content`` ignores overflow-wrap
    break-word opportunities. ``max_content`` is the widest line when the
    measure is infinite. ``letter_spacing`` sits between grapheme clusters and
    does not follow the last cluster. ``word_spacing`` widens space and other
    Zs separators only.
    """

    try:
        source = _text(text)
        measure = _nonneg(width, "width")
        white = _keyword(white_space, _WHITES, "white_space")
        overflow = _keyword(overflow_wrap, _OVERFLOWS, "overflow_wrap")
        word = _keyword(word_break, _WORDS, "word_break")
        strictness = _keyword(line_break, _LINES, "line_break")
        hyphenation = _keyword(hyphens, _HYPHENS, "hyphens")
        tabs = _nonneg(tab_size, "tab_size")
        language = _lang(lang)
        letter = _finite(letter_spacing, "letter_spacing")
        spacing = _finite(word_spacing, "word_spacing")
        if word == "break-word":
            word = "normal"
            overflow = "anywhere"
        adv = _Adv(source, advances)
        tokens = _mark_graphemes(_phase1(source, white, adv))
        _stamp_spacing(tokens, letter, spacing)
    except _Invalid as exc:
        return _invalid(exc.reason)

    lines = _lay_out(
        tokens,
        measure,
        white=white,
        overflow=overflow,
        word=word,
        strictness=strictness,
        hyphens=hyphenation,
        lang=language,
        tab_size=tabs,
        space_advance=adv.space(),
        intrinsic=False,
    )
    minimum = _widest(
        _lay_out(
            tokens,
            0.0,
            white=white,
            overflow=overflow,
            word=word,
            strictness=strictness,
            hyphens=hyphenation,
            lang=language,
            tab_size=tabs,
            space_advance=adv.space(),
            intrinsic=True,
        )
    )
    maximum = _widest(
        _lay_out(
            tokens,
            math.inf,
            white=white,
            overflow=overflow,
            word=word,
            strictness=strictness,
            hyphens=hyphenation,
            lang=language,
            tab_size=tabs,
            space_advance=adv.space(),
            intrinsic=False,
        )
    )
    return {
        "outcome": "wrapped",
        "lines": lines,
        "min_content": _number(minimum),
        "max_content": _number(maximum),
    }


def balance_lines(
    text: object,
    width: object,
    *,
    white_space: object = "normal",
    overflow_wrap: object = "normal",
    word_break: object = "normal",
    line_break: object = "auto",
    hyphens: object = "manual",
    tab_size: object = 8,
    lang: object = "",
    advances: object = None,
    letter_spacing: object = 0,
    word_spacing: object = 0,
) -> dict[str, object]:
    """Choose first-fit breaks, then rebalance a short block.

    The line count of each forced-break group is preserved. Leftover inline
    space is the measure minus the line's content width, taken before
    justification. More than ten lines in a group stays on the first-fit
    breaks. ``min_content`` and ``max_content`` stay the first-fit measures.
    """

    try:
        source = _text(text)
        measure = _nonneg(width, "width")
        white = _keyword(white_space, _WHITES, "white_space")
        overflow = _keyword(overflow_wrap, _OVERFLOWS, "overflow_wrap")
        word = _keyword(word_break, _WORDS, "word_break")
        strictness = _keyword(line_break, _LINES, "line_break")
        hyphenation = _keyword(hyphens, _HYPHENS, "hyphens")
        tabs = _nonneg(tab_size, "tab_size")
        language = _lang(lang)
        letter = _finite(letter_spacing, "letter_spacing")
        spacing = _finite(word_spacing, "word_spacing")
        if word == "break-word":
            word = "normal"
            overflow = "anywhere"
        adv = _Adv(source, advances)
        tokens = _mark_graphemes(_phase1(source, white, adv))
        _stamp_spacing(tokens, letter, spacing)
    except _Invalid as exc:
        return _invalid(exc.reason)

    try:
        lines = _balance_lay_out(
            tokens,
            measure,
            white=white,
            overflow=overflow,
            word=word,
            strictness=strictness,
            hyphens=hyphenation,
            lang=language,
            tab_size=tabs,
            space_advance=adv.space(),
        )
    except _Invalid as exc:
        return _invalid(exc.reason)
    minimum = _widest(
        _lay_out(
            tokens,
            0.0,
            white=white,
            overflow=overflow,
            word=word,
            strictness=strictness,
            hyphens=hyphenation,
            lang=language,
            tab_size=tabs,
            space_advance=adv.space(),
            intrinsic=True,
        )
    )
    maximum = _widest(
        _lay_out(
            tokens,
            math.inf,
            white=white,
            overflow=overflow,
            word=word,
            strictness=strictness,
            hyphens=hyphenation,
            lang=language,
            tab_size=tabs,
            space_advance=adv.space(),
            intrinsic=False,
        )
    )
    return {
        "outcome": "wrapped",
        "lines": lines,
        "min_content": _number(minimum),
        "max_content": _number(maximum),
    }


def _invalid(reason: str) -> dict[str, object]:
    return {
        "outcome": "invalid",
        "reason": reason,
        "lines": None,
        "min_content": None,
        "max_content": None,
    }


def _lay_out(
    tokens: list[_Tok],
    width: float,
    *,
    white: str,
    overflow: str,
    word: str,
    strictness: str,
    hyphens: str,
    lang: str,
    tab_size: float,
    space_advance: float,
    intrinsic: bool,
) -> list[dict[str, object]]:
    segments = _segments(tokens)
    last = len(segments) - 1
    lines: list[dict[str, object]] = []
    for index, segment in enumerate(segments):
        lines.extend(
            _segment(
                segment,
                width,
                white=white,
                overflow=overflow,
                word=word,
                strictness=strictness,
                hyphens=hyphens,
                lang=lang,
                tab_size=tab_size,
                space_advance=space_advance,
                before_forced=index < last,
                intrinsic=intrinsic,
            )
        )
    return lines


def _balance_lay_out(
    tokens: list[_Tok],
    width: float,
    *,
    white: str,
    overflow: str,
    word: str,
    strictness: str,
    hyphens: str,
    lang: str,
    tab_size: float,
    space_advance: float,
) -> list[dict[str, object]]:
    segments = _segments(tokens)
    last = len(segments) - 1
    lines: list[dict[str, object]] = []
    for index, segment in enumerate(segments):
        lines.extend(
            _balance_segment(
                segment,
                width,
                white=white,
                overflow=overflow,
                word=word,
                strictness=strictness,
                hyphens=hyphens,
                lang=lang,
                tab_size=tab_size,
                space_advance=space_advance,
                before_forced=index < last,
            )
        )
    return lines


def _balance_segment(
    tokens: list[_Tok],
    width: float,
    *,
    white: str,
    overflow: str,
    word: str,
    strictness: str,
    hyphens: str,
    lang: str,
    tab_size: float,
    space_advance: float,
    before_forced: bool,
) -> list[dict[str, object]]:
    fitted = _segment(
        tokens,
        width,
        white=white,
        overflow=overflow,
        word=word,
        strictness=strictness,
        hyphens=hyphens,
        lang=lang,
        tab_size=tab_size,
        space_advance=space_advance,
        before_forced=before_forced,
        intrinsic=False,
    )
    count = len(fitted)
    if white not in _WRAPS or count < 2 or count > _BALANCE_LINE_CAP or not tokens:
        return fitted
    breaks = _opportunities(
        tokens, white=white, word=word, strictness=strictness, hyphens=hyphens, lang=lang
    )
    relaxed = None
    if word == "keep-all" and overflow == "normal" and strictness != "anywhere":
        relaxed = _opportunities(
            tokens,
            white=white,
            word="normal",
            strictness=strictness,
            hyphens=hyphens,
            lang=lang,
        )
    legal = {len(tokens)}
    for index, allowed in enumerate(breaks):
        if allowed:
            legal.add(index)
    if relaxed is not None:
        for index, allowed in enumerate(relaxed):
            if allowed:
                legal.add(index)
    ends = _greedy_ends(
        tokens,
        width,
        breaks,
        relaxed,
        _emergency_enabled(white, overflow, strictness, False),
        white=white,
        hyphens=hyphens,
        tab_size=tab_size,
        space_advance=space_advance,
        before_forced=before_forced,
    )
    if len(ends) != count or any(end not in legal for end in ends):
        return fitted
    points = [0, *[index for index in range(1, len(tokens)) if index in legal], len(tokens)]
    cache: dict[tuple[int, int], tuple[str, float, float, bool]] = {}

    def piece(start: int, end: int) -> tuple[str, float, float, bool]:
        key = (start, end)
        found = cache.get(key)
        if found is not None:
            return found
        text, content, full = _measure(
            tokens,
            start,
            end,
            white=white,
            hyphens=hyphens,
            tab_size=tab_size,
            space_advance=space_advance,
            width=width,
            at_segment_end=end == len(tokens),
            before_forced=before_forced,
        )
        found = (text, content, full, content <= width + _EPS)
        cache[key] = found
        return found

    auto_contents = [float(line["content_width"]) for line in fitted]
    best_score = _leftover_variance(auto_contents, width)
    best: list[int] | None = None
    nodes = 0

    def search(point: int, left: int, contents: list[float], chosen: list[int]) -> None:
        nonlocal best_score, best, nodes
        nodes += 1
        if nodes > _BALANCE_NODE_CAP:
            return
        start = points[point]
        if left == 1:
            _text_value, content, _full, fits = piece(start, len(tokens))
            if not fits:
                return
            score = _leftover_variance([*contents, content], width)
            if score + 1e-6 < best_score:
                best_score = score
                best = [*chosen, len(tokens)]
            return
        last_choice = len(points) - 1
        for index in range(point + 1, last_choice):
            if last_choice - index < left - 1:
                break
            _text_value, content, _full, fits = piece(start, points[index])
            if not fits:
                continue
            contents.append(content)
            chosen.append(points[index])
            search(index, left - 1, contents, chosen)
            chosen.pop()
            contents.pop()

    search(0, count, [], [])
    if best is None:
        return fitted
    built: list[dict[str, object]] = []
    start = 0
    for end in best:
        text, content, full, _fits = piece(start, end)
        built.append(_line(text, content, full))
        start = end
    return built


def _greedy_ends(
    tokens: list[_Tok],
    width: float,
    breaks: list[bool],
    relaxed: list[bool] | None,
    emergency: bool,
    *,
    white: str,
    hyphens: str,
    tab_size: float,
    space_advance: float,
    before_forced: bool,
) -> list[int]:
    ends: list[int] = []
    start = 0
    count = len(tokens)
    guard = 0
    while start < count:
        guard += 1
        if guard > count + 2:
            raise _Invalid("wrap did not advance")
        end = _choose_end(
            tokens,
            start,
            width,
            breaks,
            relaxed,
            emergency,
            white=white,
            hyphens=hyphens,
            tab_size=tab_size,
            space_advance=space_advance,
            before_forced=before_forced,
        )
        if end <= start:
            end = min(count, start + 1)
        ends.append(end)
        start = end
    return ends


def _leftover_variance(contents: list[float], width: float) -> float:
    count = len(contents)
    if count == 0:
        return 0.0
    leftovers = [width - content for content in contents]
    mean = sum(leftovers) / count
    return sum((item - mean) ** 2 for item in leftovers) / count


def _segment(
    tokens: list[_Tok],
    width: float,
    *,
    white: str,
    overflow: str,
    word: str,
    strictness: str,
    hyphens: str,
    lang: str,
    tab_size: float,
    space_advance: float,
    before_forced: bool,
    intrinsic: bool,
) -> list[dict[str, object]]:
    if not tokens:
        return [_line("", 0.0, 0.0)]
    breaks = _opportunities(
        tokens, white=white, word=word, strictness=strictness, hyphens=hyphens, lang=lang
    )
    relaxed = None
    if word == "keep-all" and not intrinsic and overflow == "normal" and strictness != "anywhere":
        relaxed = _opportunities(
            tokens,
            white=white,
            word="normal",
            strictness=strictness,
            hyphens=hyphens,
            lang=lang,
        )
    emergency = _emergency_enabled(white, overflow, strictness, intrinsic)
    if white not in _WRAPS:
        text, content, full = _measure(
            tokens,
            0,
            len(tokens),
            white=white,
            hyphens=hyphens,
            tab_size=tab_size,
            space_advance=space_advance,
            width=width,
            at_segment_end=True,
            before_forced=before_forced,
        )
        return [_line(text, content, full)]

    lines: list[dict[str, object]] = []
    start = 0
    count = len(tokens)
    guard = 0
    while start < count:
        guard += 1
        if guard > count + 2:
            raise _Invalid("wrap did not advance")
        end = _choose_end(
            tokens,
            start,
            width,
            breaks,
            relaxed,
            emergency,
            white=white,
            hyphens=hyphens,
            tab_size=tab_size,
            space_advance=space_advance,
            before_forced=before_forced,
        )
        if end <= start:
            end = min(count, start + 1)
        text, content, full = _measure(
            tokens,
            start,
            end,
            white=white,
            hyphens=hyphens,
            tab_size=tab_size,
            space_advance=space_advance,
            width=width,
            at_segment_end=end == count,
            before_forced=before_forced,
        )
        lines.append(_line(text, content, full))
        start = end
    return lines


def _emergency_enabled(white: str, overflow: str, strictness: str, intrinsic: bool) -> bool:
    if white not in _WRAPS:
        return False
    if strictness == "anywhere":
        return False
    if intrinsic:
        return overflow == "anywhere"
    return overflow in {"anywhere", "break-word"}


def _choose_end(
    tokens: list[_Tok],
    start: int,
    width: float,
    breaks: list[bool],
    relaxed: list[bool] | None,
    emergency: bool,
    *,
    white: str,
    hyphens: str,
    tab_size: float,
    space_advance: float,
    before_forced: bool,
) -> int:
    found = _search(
        tokens,
        start,
        width,
        breaks,
        white=white,
        hyphens=hyphens,
        tab_size=tab_size,
        space_advance=space_advance,
        before_forced=before_forced,
    )
    if found is None and relaxed is not None:
        found = _search(
            tokens,
            start,
            width,
            relaxed,
            white=white,
            hyphens=hyphens,
            tab_size=tab_size,
            space_advance=space_advance,
            before_forced=before_forced,
        )
    if found is None and emergency:
        found = _emergency_end(
            tokens,
            start,
            width,
            white=white,
            hyphens=hyphens,
            tab_size=tab_size,
            space_advance=space_advance,
            before_forced=before_forced,
        )
    if found is None:
        found = _next_opportunity(start, relaxed if relaxed is not None else breaks, len(tokens))
    return found


def _search(
    tokens: list[_Tok],
    start: int,
    width: float,
    breaks: list[bool],
    *,
    white: str,
    hyphens: str,
    tab_size: float,
    space_advance: float,
    before_forced: bool,
) -> int | None:
    count = len(tokens)
    best: int | None = None
    for end in range(start + 1, count + 1):
        if end < count and not breaks[end]:
            continue
        _text_value, content, _full = _measure(
            tokens,
            start,
            end,
            white=white,
            hyphens=hyphens,
            tab_size=tab_size,
            space_advance=space_advance,
            width=width,
            at_segment_end=end == count,
            before_forced=before_forced,
        )
        if content <= width + _EPS:
            best = end
    return best


def _emergency_end(
    tokens: list[_Tok],
    start: int,
    width: float,
    *,
    white: str,
    hyphens: str,
    tab_size: float,
    space_advance: float,
    before_forced: bool,
) -> int:
    count = len(tokens)
    best: int | None = None
    end = start
    while end < count:
        end += 1
        while end < count and not tokens[end].grapheme_start:
            end += 1
        if end < count and tokens[end].kind in {"space", "tab", "sep"} and white != "break-spaces":
            continue
        _text_value, content, _full = _measure(
            tokens,
            start,
            end,
            white=white,
            hyphens=hyphens,
            tab_size=tab_size,
            space_advance=space_advance,
            width=width,
            at_segment_end=end == count,
            before_forced=before_forced,
        )
        if content <= width + _EPS:
            best = end
        else:
            break
    if best is not None:
        return best
    end = start + 1
    while end < count and not tokens[end].grapheme_start:
        end += 1
    return end


def _next_opportunity(start: int, breaks: list[bool], count: int) -> int:
    end = start + 1
    while end < count and not breaks[end]:
        end += 1
    return end


def _measure(
    tokens: list[_Tok],
    start: int,
    end: int,
    *,
    white: str,
    hyphens: str,
    tab_size: float,
    space_advance: float,
    width: float,
    at_segment_end: bool,
    before_forced: bool,
) -> tuple[str, float, float]:
    low = start
    while low < end and tokens[low].kind == "space" and tokens[low].collapsible:
        low += 1
    high = end
    while high > low and _is_trail(tokens[high - 1], white):
        high -= 1
    visible = [tok for tok in tokens[high:end] if not _trimmed_token(tok, white)]
    show_shy = (
        hyphens != "none"
        and not visible
        and end > low
        and tokens[end - 1].kind == "shy"
        and not at_segment_end
    )
    base_text, base_width = _render(
        tokens, low, high, show_shy=show_shy, tab_size=tab_size, space_advance=space_advance, x0=0.0
    )
    if not visible:
        return base_text, base_width, base_width
    trail_text, trail_width = _render_tokens(
        visible, show_shy=False, tab_size=tab_size, space_advance=space_advance, x0=base_width
    )
    mode = _trail_mode(
        white=white,
        at_segment_end=at_segment_end,
        before_forced=before_forced,
        base_width=base_width,
        trail_width=trail_width,
        width=width,
    )
    if mode == "hang":
        return base_text + trail_text, base_width, base_width + trail_width
    content = base_width + trail_width
    if base_text and trail_text and low < len(tokens) and tokens[low].letter_spacing:
        content += tokens[low].letter_spacing
    return base_text + trail_text, content, content


def _render(
    tokens: list[_Tok],
    start: int,
    end: int,
    *,
    show_shy: bool,
    tab_size: float,
    space_advance: float,
    x0: float,
) -> tuple[str, float]:
    return _render_tokens(
        tokens[start:end],
        show_shy=show_shy,
        tab_size=tab_size,
        space_advance=space_advance,
        x0=x0,
    )


def _render_tokens(
    tokens: list[_Tok],
    *,
    show_shy: bool,
    tab_size: float,
    space_advance: float,
    x0: float,
) -> tuple[str, float]:
    x = x0
    parts: list[str] = []
    last = len(tokens) - 1
    letter = tokens[0].letter_spacing if tokens else 0.0
    word = tokens[0].word_spacing if tokens else 0.0
    seen = False
    for index, tok in enumerate(tokens):
        if tok.kind == "shy":
            if show_shy and index == last:
                if letter and seen and tok.grapheme_start:
                    x += letter
                parts.append("\u2010")
                x += tok.advance
                seen = True
            continue
        if tok.kind == "tab":
            if letter and seen and tok.grapheme_start:
                x += letter
            parts.append("\t")
            advance = _tab_advance(x, tab_size, space_advance)
            x += advance
            seen = True
            continue
        if letter and seen and tok.grapheme_start:
            x += letter
        parts.append(tok.ch)
        advance = tok.advance
        if word and tok.kind in {"space", "sep"}:
            advance += word
        x += advance
        seen = True
    return "".join(parts), x - x0


def _tab_advance(x: float, tab_size: float, space_advance: float) -> float:
    unit = tab_size * space_advance
    if unit <= _EPS:
        return 0.0
    nxt = (math.floor((x / unit) + 1e-12) + 1) * unit
    if nxt - x < (0.5 * space_advance) - _EPS:
        nxt += unit
    return nxt - x


def _trail_mode(
    *,
    white: str,
    at_segment_end: bool,
    before_forced: bool,
    base_width: float,
    trail_width: float,
    width: float,
) -> str:
    if white in {"pre", "break-spaces"}:
        return "keep"
    if white == "pre-wrap" and at_segment_end and before_forced and base_width + trail_width <= width + _EPS:
        return "keep"
    return "hang"


def _trimmed_token(tok: _Tok, white: str) -> bool:
    if tok.kind == "space" and tok.collapsible:
        return True
    return tok.ch == "\u1680" and white in _COLLAPSE


def _is_trail(tok: _Tok, white: str) -> bool:
    if tok.kind == "space" and tok.collapsible:
        return True
    if tok.ch == "\u1680" and white in _COLLAPSE:
        return True
    if white in {"pre", "pre-wrap", "break-spaces"} and tok.kind in {"space", "tab", "sep"}:
        return True
    return white in _COLLAPSE and tok.kind == "sep"


def _opportunities(
    tokens: list[_Tok],
    *,
    white: str,
    word: str,
    strictness: str,
    hyphens: str,
    lang: str,
) -> list[bool]:
    before = [False] * len(tokens)
    if white not in _WRAPS:
        return before
    east = lang.split("-", 1)[0] in {"zh", "ja"}
    for index in range(1, len(tokens)):
        if not tokens[index].grapheme_start:
            continue
        prev = tokens[index - 1]
        cur = tokens[index]
        if strictness == "anywhere" and _anywhere_boundary(cur, white):
            before[index] = True
        if _after_white_space(prev, cur, white):
            before[index] = True
        if hyphens != "none" and prev.kind == "shy":
            before[index] = True
        if (prev.ch in _AFTER_HYPHEN or prev.ch in _AFTER_CLOSING) and not _cj_blocked(cur, strictness):
            before[index] = True
        if prev.ch == "\u200b":
            before[index] = True
        if _before_punctuation(prev, cur, strictness, word, east):
            before[index] = True
        if word == "break-all" and _break_all_pair(prev, cur):
            before[index] = True
        if word != "keep-all" and _cjk_pair(prev, cur) and not _cj_blocked(cur, strictness):
            before[index] = True
        if cur.ch in _INSEPARABLE and prev.ch in _INSEPARABLE and strictness == "loose":
            before[index] = True
    return before


def _anywhere_boundary(cur: _Tok, white: str) -> bool:
    if cur.kind in {"space", "tab", "sep"} and white != "break-spaces":
        return False
    return True


def _after_white_space(prev: _Tok, cur: _Tok, white: str) -> bool:
    if white in _COLLAPSE and prev.kind == "space" and prev.collapsible:
        return True
    if white in _COLLAPSE and prev.kind == "sep":
        return True
    run = {"space", "tab", "sep"}
    if white == "pre-wrap":
        return prev.kind in run and cur.kind not in run
    if white == "break-spaces":
        return prev.kind in run
    return False


def _before_punctuation(prev: _Tok, cur: _Tok, strictness: str, word: str, east: bool) -> bool:
    ch = cur.ch
    if ch in _WAVEDASH:
        return east and strictness in {"auto", "normal", "loose"}
    if ch in _CENTERED:
        return east and strictness == "loose"
    if ch in _CJ:
        return word != "keep-all" and strictness == "loose"
    if ch in _LOOSE_HYPHEN and strictness == "loose":
        return _ideograph(prev.ch) or (word == "break-all" and _letter(prev.ch))
    return False


def _break_all_pair(prev: _Tok, cur: _Tok) -> bool:
    return prev.kind in {"glyph", "shy"} and cur.kind in {"glyph", "shy"}


def _cjk_pair(prev: _Tok, cur: _Tok) -> bool:
    return _cjk_letter(prev.ch) and _cjk_letter(cur.ch)


def _cj_blocked(cur: _Tok, strictness: str) -> bool:
    return cur.ch in _CJ and strictness != "loose"


def _phase1(text: str, white: str, adv: _Adv) -> list[_Tok]:
    if white in _COLLAPSE:
        return _collapse(text, white, adv)
    return _preserve(text, adv)


def _collapse(text: str, white: str, adv: _Adv) -> list[_Tok]:
    pieces: list[_Tok] = []
    index = 0
    count = len(text)
    while index < count:
        if text[index] in " \t\n\r":
            end = index
            newlines = 0
            while end < count and text[end] in " \t\n\r":
                if text[end] == "\n":
                    newlines += 1
                end += 1
            advance = adv.at(index)
            if newlines:
                if white == "pre-line":
                    pieces.extend(_Tok("break", "", 0.0) for _ in range(newlines))
                else:
                    pieces.append(_Tok("segment", "", advance, collapsible=True))
            else:
                pieces.append(_Tok("space", " ", advance, collapsible=True))
            index = end
            continue
        pieces.append(_atom(text, index, adv))
        index += 1
    return _join_segments(pieces)


def _join_segments(pieces: list[_Tok]) -> list[_Tok]:
    joined: list[_Tok] = []
    for index, tok in enumerate(pieces):
        if tok.kind != "segment":
            joined.append(tok)
            continue
        prev = _neighbor(pieces, index, -1)
        nxt = _neighbor(pieces, index, 1)
        if prev is not None and nxt is not None and _unspaced(prev.ch) and _unspaced(nxt.ch):
            continue
        joined.append(_Tok("space", " ", tok.advance, collapsible=True))
    return joined


def _neighbor(pieces: list[_Tok], index: int, step: int) -> _Tok | None:
    cursor = index + step
    while 0 <= cursor < len(pieces):
        if pieces[cursor].kind != "segment":
            return pieces[cursor]
        cursor += step
    return None


def _preserve(text: str, adv: _Adv) -> list[_Tok]:
    pieces: list[_Tok] = []
    for index, ch in enumerate(text):
        if ch == "\n":
            pieces.append(_Tok("break", "", 0.0))
        elif ch == "\t":
            pieces.append(_Tok("tab", "\t", 0.0))
        elif ch in " \r":
            pieces.append(_Tok("space", " ", adv.of(" ", index) if ch == "\r" else adv.of(ch, index)))
        else:
            pieces.append(_atom(text, index, adv))
    return pieces


def _atom(text: str, index: int, adv: _Adv) -> _Tok:
    ch = text[index]
    advance = adv.of(ch, index)
    if ch == "\u00a0":
        return _Tok("nbsp", ch, advance)
    if ch == "\u00ad":
        return _Tok("shy", ch, advance)
    if _other_sep(ch):
        return _Tok("sep", ch, advance)
    return _Tok("glyph", ch, advance)


def _mark_graphemes(tokens: list[_Tok]) -> list[_Tok]:
    previous: _Tok | None = None
    regional = 0
    for tok in tokens:
        if tok.kind == "break":
            tok.grapheme_start = True
            previous = None
            regional = 0
            continue
        start = True
        category = _category(tok.ch)
        if previous is not None:
            if category.startswith("M") or _variation(tok.ch):
                start = False
            elif previous.ch == "\u200d" or tok.ch == "\u200d":
                start = False
            elif _regional_indicator(previous.ch) and _regional_indicator(tok.ch) and regional % 2 == 1:
                start = False
        if _regional_indicator(tok.ch):
            regional = 1 if start else regional + 1
        else:
            regional = 0
        tok.grapheme_start = start
        previous = tok
    return tokens


def _segments(tokens: list[_Tok]) -> list[list[_Tok]]:
    parts: list[list[_Tok]] = [[]]
    for tok in tokens:
        if tok.kind == "break":
            parts.append([])
        else:
            parts[-1].append(tok)
    return parts


def _other_sep(ch: str) -> bool:
    return ch not in {" ", "\u00a0"} and _category(ch) == "Zs"


def _unspaced(ch: str) -> bool:
    return bool(ch) and not _hangul(ch) and _east(ch) in {"F", "W", "H"}


def _hangul(ch: str) -> bool:
    code = ord(ch)
    return any(start <= code <= end for start, end in _HANGUL)


def _cjk_letter(ch: str) -> bool:
    if not ch or ch in _CJ or ch in _WAVEDASH or ch in _CENTERED:
        return False
    if _hangul(ch):
        return True
    code = ord(ch)
    if 0x3040 <= code <= 0x30FF or 0x31F0 <= code <= 0x31FF:
        return _category(ch).startswith("L")
    name = _name(ch)
    return "CJK UNIFIED IDEOGRAPH" in name or "CJK COMPATIBILITY IDEOGRAPH" in name


def _ideograph(ch: str) -> bool:
    name = _name(ch)
    return "CJK UNIFIED IDEOGRAPH" in name or "CJK COMPATIBILITY IDEOGRAPH" in name


def _letter(ch: str) -> bool:
    return _category(ch).startswith("L")


def _regional_indicator(ch: str) -> bool:
    return bool(ch) and 0x1F1E6 <= ord(ch) <= 0x1F1FF


def _variation(ch: str) -> bool:
    return bool(ch) and 0xFE00 <= ord(ch) <= 0xFE0F


def _east(ch: str) -> str:
    try:
        return unicodedata.east_asian_width(ch)
    except ValueError:
        return "N"


def _category(ch: str) -> str:
    if not ch:
        return ""
    try:
        return unicodedata.category(ch)
    except ValueError:
        return "Cn"


def _name(ch: str) -> str:
    if not ch:
        return ""
    try:
        return unicodedata.name(ch, "")
    except ValueError:
        return ""


def _default_advance(ch: str) -> float:
    if ch == "\u00ad":
        return 1.0
    category = _category(ch)
    if category.startswith("M") or category == "Cf":
        return 0.0
    return 1.0


def _line(text: str, content: float, full: float) -> dict[str, object]:
    return {"text": text, "content_width": _number(content), "width": _number(full)}


def _widest(lines: list[dict[str, object]]) -> float:
    widest = 0.0
    for line in lines:
        value = line["content_width"]
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            widest = max(widest, float(value))
    return widest


def _text(value: object) -> str:
    if not isinstance(value, str):
        raise _Invalid("text must be a string")
    return value


def _lang(value: object) -> str:
    if not isinstance(value, str):
        raise _Invalid("lang must be a string")
    return value.casefold()


def _keyword(value: object, allowed: frozenset[str], name: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise _Invalid(f"{name} is not a supported keyword")
    return value


def _stamp_spacing(tokens: list[_Tok], letter: float, word: float) -> None:
    if not letter and not word:
        return
    for tok in tokens:
        tok.letter_spacing = letter
        tok.word_spacing = word


def _finite(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _Invalid(f"{name} must be a number")
    number = float(value)
    if not math.isfinite(number):
        raise _Invalid(f"{name} must be a finite number")
    return number


def _nonneg(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _Invalid(f"{name} must be a number")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise _Invalid(f"{name} must be a non-negative finite number")
    return number


def _number(value: float) -> int | float:
    nearest = round(value)
    if abs(value - nearest) <= _EPS:
        return int(nearest)
    return value
