"""Wrap one inline into CSS Text line boxes.

CSS Text Level 3 collapses or preserves white space, then breaks the line at
the farthest soft wrap opportunity that fits. This reader does that for a
single inline: no bidi reordering, no shaping, and no font fallback.

A collapsible segment break (U+000A under normal or nowrap) becomes one space,
except it disappears when both neighbors have East Asian width F, W, or H and
neither is Hangul. That is the Level 3 rule left to the UA; it is the rule
that reproduces the spec's English, Korean, and Chinese examples. U+000D is a
space, not a segment break. hyphens:auto adds English Liang breaks, and
the line that takes one draws U+2010. ``hyphenate_character`` replaces that
mark: an empty string keeps the break and adds no advance, and each character
of another string uses the preceding letter's advance. Those automatic breaks
are omitted from min-content. hyphens:manual still breaks only at U+00AD, and
hyphens:none does not. line-break:auto uses the normal
strictness list. Tab stops are multiples of the space advance measured from
the line's content start. ``letter_spacing`` is inserted between grapheme
clusters and is not applied after the last cluster on a line. ``word_spacing``
is added to each space and to each other Unicode Zs separator.
``text_spacing_trim`` of ``trim-start`` then halves the advance of a
fullwidth opening punctuation glyph when that glyph is the first on a line.
An even advance loses exactly half. An odd pixel advance keeps the floor of
half so the used width stays integral. ``normal`` leaves that line-start
opening full. It halves a fullwidth opening after a fullwidth opening, a
fullwidth middle dot, an ideographic space, any Ps character, or a fullwidth
closing of the same or larger advance, and halves a fullwidth closing before
a fullwidth closing, a fullwidth middle dot, an ideographic space, any Pe
character, or a fullwidth opening of a strictly larger advance. A fullwidth
closing that ends a line becomes half-width only when the untrimmed line
does not fit. Colon punctuation is a middle dot and dot punctuation is
closing, the Japanese horizontal classes. ``space-all`` leaves every advance
alone.

``balance_lines`` is CSS Text Level 4 ``text-wrap-style: balance``. Forced
line breaks split the block into independent groups. A group keeps the
first-fit breaks when it has fewer than two lines or more than ten, or when
wrapping is not allowed. Otherwise the breaks are a partition into that same
number of lines. The partition that strictly lowers the population variance
of leftover inline space (the measure minus each line's content width) wins.
A tie keeps the first-fit breaks. Emergency breaks are not rearranged.
``pretty_lines`` is ``text-wrap-style: pretty``. A group keeps those first-fit
breaks, then moves the last break back to the previous legal wrap opportunity
when the last line is a single word, the enlarged line still fits, and the
previous line still has text. Earlier lines stay put. ``min_content`` and
``max_content`` stay the first-fit measures for both.
"""

from __future__ import annotations

import contextvars
import math
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass

from blackhole_agent.css_hyphenate import hyphenation_offsets

_EPS = 1e-9
_BALANCE_LINE_CAP = 10
_BALANCE_NODE_CAP = 200_000
_WHITES = frozenset({"normal", "nowrap", "pre", "pre-wrap", "break-spaces", "pre-line"})
_OVERFLOWS = frozenset({"normal", "break-word", "anywhere"})
_WORDS = frozenset({"normal", "keep-all", "break-all", "break-word"})
_LINES = frozenset({"auto", "loose", "normal", "strict", "anywhere"})
_HYPHENS = frozenset({"none", "manual", "auto"})
_HANGS = frozenset({"first", "force-end", "allow-end", "last"})
_STOPS = frozenset(",.\u060c\u06d4\u3001\u3002\uff0c\uff0e\ufe50\ufe51\ufe52\uff61\uff64")
_HANGING: contextvars.ContextVar[frozenset[str]] = contextvars.ContextVar(
    "css_hanging_punctuation", default=frozenset()
)
_DEFAULT_HYPHEN = "\u2010"
_HYPHEN_MARK: contextvars.ContextVar[str] = contextvars.ContextVar(
    "css_hyphenate_character", default=_DEFAULT_HYPHEN
)
_OPENING: contextvars.ContextVar[bool] = contextvars.ContextVar("css_hanging_opening", default=False)
_CLONE: contextvars.ContextVar[tuple[tuple[int, int, float, float], ...]] = contextvars.ContextVar(
    "css_clone_decoration", default=()
)
_TRIM_MODE: contextvars.ContextVar[str] = contextvars.ContextVar(
    "css_text_spacing_trim", default=""
)
_FULLWIDTH_DOT = frozenset("\u3001\u3002\uff0c\uff0e")
_FULLWIDTH_COLON = frozenset("\uff1a\uff1b")
_MIDDLE_DOT = frozenset("\u00b7\u2027\u30fb") | _FULLWIDTH_COLON
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
    autospace: float = 0.0
    nowrap: bool = False
    start: int = 0
    end: int = 0


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
    hanging_punctuation: object = "none",
    nowrap_ranges: object = (),
    clone_ranges: object = (),
    text_autospace: object = "off",
    autospace: object = 0,
    hyphenate_character: object = _DEFAULT_HYPHEN,
    text_spacing_trim: object = "space-all",
) -> dict[str, object]:
    """Wrap ``text`` into line boxes of ``width``.

    Each line reports the rendered ``text`` (hanging spaces included, trimmed
    collapsible spaces omitted, an unused soft hyphen omitted), the
    ``content_width`` that was tested against the measure, and ``width``
    including hanging advances. ``min_content`` ignores overflow-wrap
    break-word opportunities. ``max_content`` is the widest line when the
    measure is infinite. ``letter_spacing`` sits between grapheme clusters and
    does not follow the last cluster. ``word_spacing`` widens space and other
    Zs separators only. ``hanging_punctuation`` keeps an opening mark out of
    the first line's measure, a closing mark out of the final line's measure,
    and a stop or comma out of the line that ends with it. The mark stays in
    the rendered text. Its advance stays in ``width`` and leaves ``content_width``.
    ``clone_ranges`` are source spans whose start and end chrome already sit on
    the first and last characters. Each other fragment of that span adds the
    missing edge to the measured width.
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
        hanging = _hanging_modes(hanging_punctuation)
        held = _nowrap_ranges(nowrap_ranges)
        clones = _clone_ranges(clone_ranges, len(source))
        hyphen_mark = _used_hyphen_mark(hyphenate_character)
        trim_mode = _trim_mode(text_spacing_trim)
        if word == "break-word":
            word = "normal"
            overflow = "anywhere"
        adv = _Adv(source, advances)
        tokens = _mark_graphemes(_phase1(source, white, adv, held))
        _stamp_spacing(tokens, letter, spacing)
        _apply_autospace(tokens, text_autospace, autospace)
    except _Invalid as exc:
        return _invalid(exc.reason)

    token = _HANGING.set(hanging)
    clone_token = _CLONE.set(clones)
    mark_token = _HYPHEN_MARK.set(hyphen_mark)
    trim_token = _TRIM_MODE.set(trim_mode)
    try:
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
    finally:
        _HANGING.reset(token)
        _CLONE.reset(clone_token)
        _HYPHEN_MARK.reset(mark_token)
        _TRIM_MODE.reset(trim_token)
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
    hanging_punctuation: object = "none",
    nowrap_ranges: object = (),
    clone_ranges: object = (),
    text_autospace: object = "off",
    autospace: object = 0,
    hyphenate_character: object = _DEFAULT_HYPHEN,
    text_spacing_trim: object = "space-all",
) -> dict[str, object]:
    """Choose first-fit breaks, then rebalance a short block.

    The line count of each forced-break group is preserved. Leftover inline
    space is the measure minus the line's content width, taken before
    justification. More than ten lines in a group stays on the first-fit
    breaks. ``min_content`` and ``max_content`` stay the first-fit measures.
    """

    return _styled_breaks(
        text,
        width,
        layout=_balance_lay_out,
        white_space=white_space,
        overflow_wrap=overflow_wrap,
        word_break=word_break,
        line_break=line_break,
        hyphens=hyphens,
        tab_size=tab_size,
        lang=lang,
        advances=advances,
        letter_spacing=letter_spacing,
        word_spacing=word_spacing,
        hanging_punctuation=hanging_punctuation,
        nowrap_ranges=nowrap_ranges,
        clone_ranges=clone_ranges,
        text_autospace=text_autospace,
        autospace=autospace,
        hyphenate_character=hyphenate_character,
        text_spacing_trim=text_spacing_trim,
    )


def pretty_lines(
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
    hanging_punctuation: object = "none",
    nowrap_ranges: object = (),
    clone_ranges: object = (),
    text_autospace: object = "off",
    autospace: object = 0,
    hyphenate_character: object = _DEFAULT_HYPHEN,
    text_spacing_trim: object = "space-all",
) -> dict[str, object]:
    """Keep the first-fit breaks, then lengthen a one-word last line.

    Only the break between the last two lines moves, and only back to the
    previous legal wrap opportunity. The line count stays the same. A last
    line that already holds two words, a move that would overflow, and a
    previous line that would become empty stay on the first-fit breaks.
    ``min_content`` and ``max_content`` stay the first-fit measures.
    """

    return _styled_breaks(
        text,
        width,
        layout=_pretty_lay_out,
        white_space=white_space,
        overflow_wrap=overflow_wrap,
        word_break=word_break,
        line_break=line_break,
        hyphens=hyphens,
        tab_size=tab_size,
        lang=lang,
        advances=advances,
        letter_spacing=letter_spacing,
        word_spacing=word_spacing,
        hanging_punctuation=hanging_punctuation,
        nowrap_ranges=nowrap_ranges,
        clone_ranges=clone_ranges,
        text_autospace=text_autospace,
        autospace=autospace,
        hyphenate_character=hyphenate_character,
        text_spacing_trim=text_spacing_trim,
    )


def _styled_breaks(
    text: object,
    width: object,
    *,
    layout,
    white_space: object,
    overflow_wrap: object,
    word_break: object,
    line_break: object,
    hyphens: object,
    tab_size: object,
    lang: object,
    advances: object,
    letter_spacing: object,
    word_spacing: object,
    hanging_punctuation: object,
    nowrap_ranges: object,
    clone_ranges: object,
    text_autospace: object,
    autospace: object,
    hyphenate_character: object = _DEFAULT_HYPHEN,
    text_spacing_trim: object = "space-all",
) -> dict[str, object]:
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
        hanging = _hanging_modes(hanging_punctuation)
        held = _nowrap_ranges(nowrap_ranges)
        clones = _clone_ranges(clone_ranges, len(source))
        hyphen_mark = _used_hyphen_mark(hyphenate_character)
        trim_mode = _trim_mode(text_spacing_trim)
        if word == "break-word":
            word = "normal"
            overflow = "anywhere"
        adv = _Adv(source, advances)
        tokens = _mark_graphemes(_phase1(source, white, adv, held))
        _stamp_spacing(tokens, letter, spacing)
        _apply_autospace(tokens, text_autospace, autospace)
    except _Invalid as exc:
        return _invalid(exc.reason)

    token = _HANGING.set(hanging)
    clone_token = _CLONE.set(clones)
    mark_token = _HYPHEN_MARK.set(hyphen_mark)
    trim_token = _TRIM_MODE.set(trim_mode)
    try:
        try:
            lines = layout(
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
    finally:
        _HANGING.reset(token)
        _CLONE.reset(clone_token)
        _HYPHEN_MARK.reset(mark_token)
        _TRIM_MODE.reset(trim_token)
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
    if hyphens == "auto" and not intrinsic:
        tokens = _with_auto_hyphens(tokens, lang)
    segments = _segments(tokens)
    last = len(segments) - 1
    lines: list[dict[str, object]] = []
    for index, segment in enumerate(segments):
        marker = _OPENING.set(index == 0)
        try:
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
        finally:
            _OPENING.reset(marker)
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
    if hyphens == "auto":
        tokens = _with_auto_hyphens(tokens, lang)
    segments = _segments(tokens)
    last = len(segments) - 1
    lines: list[dict[str, object]] = []
    for index, segment in enumerate(segments):
        marker = _OPENING.set(index == 0)
        try:
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
        finally:
            _OPENING.reset(marker)
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


def _pretty_lay_out(
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
    if hyphens == "auto":
        tokens = _with_auto_hyphens(tokens, lang)
    segments = _segments(tokens)
    last = len(segments) - 1
    lines: list[dict[str, object]] = []
    for index, segment in enumerate(segments):
        marker = _OPENING.set(index == 0)
        try:
            lines.extend(
                _pretty_segment(
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
        finally:
            _OPENING.reset(marker)
    return lines


def _pretty_segment(
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
    """Slide only the final break back one opportunity when the last line is one word."""

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
    if white not in _WRAPS or len(fitted) < 2 or not tokens:
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
    if len(ends) != len(fitted) or ends[-1] != len(tokens):
        return fitted
    prev_end = ends[-2]
    if not _span_is_one_word(tokens, prev_end, ends[-1], white):
        return fitted
    prev_start = ends[-3] if len(ends) > 2 else 0
    candidate = _previous_wrap(breaks, relaxed, prev_start, prev_end)
    if candidate is None:
        return fitted
    last_text, last_content, last_full = _measure(
        tokens,
        candidate,
        ends[-1],
        white=white,
        hyphens=hyphens,
        tab_size=tab_size,
        space_advance=space_advance,
        width=width,
        at_segment_end=True,
        before_forced=before_forced,
    )
    if not last_text or last_content > width + _EPS:
        return fitted
    prev_text, prev_content, prev_full = _measure(
        tokens,
        prev_start,
        candidate,
        white=white,
        hyphens=hyphens,
        tab_size=tab_size,
        space_advance=space_advance,
        width=width,
        at_segment_end=False,
        before_forced=before_forced,
    )
    if not prev_text or prev_content > width + _EPS:
        return fitted
    adjusted = list(fitted)
    adjusted[-2] = _line(prev_text, prev_content, prev_full)
    adjusted[-1] = _line(last_text, last_content, last_full)
    return adjusted


def _span_is_one_word(tokens: list[_Tok], start: int, end: int, white: str) -> bool:
    low = start
    while low < end and tokens[low].kind == "space" and tokens[low].collapsible:
        low += 1
    high = end
    while high > low and _is_trail(tokens[high - 1], white):
        high -= 1
    if low >= high:
        return False
    return all(tok.kind not in {"space", "tab", "sep", "break"} for tok in tokens[low:high])


def _previous_wrap(
    breaks: list[bool],
    relaxed: list[bool] | None,
    start: int,
    end: int,
) -> int | None:
    for index in range(end - 1, start, -1):
        if breaks[index] or (relaxed is not None and index < len(relaxed) and relaxed[index]):
            return index
    return None


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
        if end < count and tokens[end - 1].nowrap and tokens[end].nowrap:
            continue
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
    while end < count and (
        not tokens[end].grapheme_start or (tokens[end - 1].nowrap and tokens[end].nowrap)
    ):
        end += 1
    return end


def _next_opportunity(start: int, breaks: list[bool], count: int) -> int:
    end = start + 1
    while end < count and not breaks[end]:
        end += 1
    return end


def _hanging_modes(value: object) -> frozenset[str]:
    if not isinstance(value, str):
        raise _Invalid("hanging_punctuation is not a supported keyword")
    text = " ".join(value.strip().lower().split())
    if text in {"", "none"}:
        return frozenset()
    parts = text.split(" ")
    if len(parts) != len(set(parts)) or any(part not in _HANGS for part in parts):
        raise _Invalid("hanging_punctuation is not a supported keyword")
    if "force-end" in parts and "allow-end" in parts:
        raise _Invalid("hanging_punctuation is not a supported keyword")
    return frozenset(parts)


def _content_ink(tok: _Tok) -> float:
    extra = tok.word_spacing if tok.kind in {"space", "sep"} else 0.0
    return tok.advance + extra


def _opens(ch: str) -> bool:
    return _category(ch) in {"Ps", "Pi"}


def _closes(ch: str) -> bool:
    return _category(ch) in {"Pe", "Pf"}


def _trim_mode(value: object) -> str:
    if not isinstance(value, str):
        raise _Invalid("text_spacing_trim is not a supported keyword")
    text = " ".join(value.strip().lower().split())
    if text in {"", "space-all", "off"}:
        return ""
    if text in {"trim-start", "normal"}:
        return text
    raise _Invalid("text_spacing_trim is not a supported keyword")


def _fullwidth_opening(ch: str) -> bool:
    """CSS Text fullwidth opening punctuation, plus the two quote exceptions."""

    if ch in {"\u2018", "\u201c"}:
        return True
    if len(ch) != 1 or _category(ch) != "Ps":
        return False
    code = ord(ch)
    if 0x3000 <= code <= 0x303F:
        return True
    return _east(ch) == "F"


def _trimmed_half(advance: float) -> float:
    """Pixels removed so a line-start opening glyph keeps at most half its advance."""

    nearest = round(advance)
    if abs(advance - nearest) <= _EPS:
        whole = int(nearest)
        if whole <= 0:
            return 0.0
        return float(whole - whole // 2)
    half = advance / 2.0
    return half if half > 0 else 0.0


def _fullwidth_closing(ch: str) -> bool:
    """CSS Text fullwidth closing punctuation. Japanese colon stays a middle dot."""

    if ch in {"\u2019", "\u201d"} or ch in _FULLWIDTH_DOT:
        return True
    if ch in _MIDDLE_DOT or len(ch) != 1 or _category(ch) != "Pe":
        return False
    code = ord(ch)
    if 0x3000 <= code <= 0x303F:
        return True
    return _east(ch) == "F"


def _middle_dot(ch: str) -> bool:
    return ch in _MIDDLE_DOT


def _spacing_characters(tokens: list[_Tok], low: int, high: int) -> list[int]:
    return [
        index
        for index in range(low, high)
        if tokens[index].grapheme_start
        and tokens[index].ch
        and tokens[index].kind in {"glyph", "sep", "nbsp", "space"}
    ]


def _opening_trim(tokens: list[_Tok], low: int, high: int) -> float:
    if _TRIM_MODE.get() != "trim-start" or low >= high:
        return 0.0
    tok = tokens[low]
    if not tok.grapheme_start or tok.kind != "glyph" or not _fullwidth_opening(tok.ch):
        return 0.0
    return _trimmed_half(tok.advance)


def _opening_collapses(tok: _Tok, previous: _Tok | None) -> bool:
    if previous is None or tok.kind != "glyph" or not _fullwidth_opening(tok.ch):
        return False
    if _fullwidth_opening(previous.ch) or _middle_dot(previous.ch) or previous.ch == "\u3000":
        return True
    if _category(previous.ch) == "Ps":
        return True
    return _fullwidth_closing(previous.ch) and previous.advance + _EPS >= tok.advance


def _closing_collapses(tok: _Tok, following: _Tok | None) -> bool:
    if following is None or tok.kind != "glyph" or not _fullwidth_closing(tok.ch):
        return False
    if _fullwidth_closing(following.ch) or _middle_dot(following.ch) or following.ch == "\u3000":
        return True
    if _category(following.ch) == "Pe":
        return True
    return _fullwidth_opening(following.ch) and following.advance > tok.advance + _EPS


def _adjacent_trim(tokens: list[_Tok], low: int, high: int) -> float:
    """Half-width advance removed from punctuation that touches a neighbor."""

    if _TRIM_MODE.get() != "normal" or low >= high:
        return 0.0
    indexes = _spacing_characters(tokens, low, high)
    removed = 0.0
    for pos, index in enumerate(indexes):
        tok = tokens[index]
        previous = tokens[indexes[pos - 1]] if pos else None
        following = tokens[indexes[pos + 1]] if pos + 1 < len(indexes) else None
        if _opening_collapses(tok, previous) or _closing_collapses(tok, following):
            removed += _trimmed_half(tok.advance)
    return removed


def _allow_end_trim(tokens: list[_Tok], low: int, high: int, content: float, width: float) -> float:
    """Half-width removed from a line-end closing mark that does not fit."""

    if _TRIM_MODE.get() != "normal" or low >= high or content <= width + _EPS:
        return 0.0
    if not math.isfinite(width) or width <= 0:
        return 0.0
    indexes = _spacing_characters(tokens, low, high)
    if not indexes:
        return 0.0
    tok = tokens[indexes[-1]]
    if tok.kind != "glyph" or not _fullwidth_closing(tok.ch):
        return 0.0
    return _trimmed_half(tok.advance)


def _hanging_deduction(
    tokens: list[_Tok],
    low: int,
    high: int,
    *,
    start: int,
    content: float,
    width: float,
    at_segment_end: bool,
    before_forced: bool,
) -> float:
    """Advance excluded from the fit measure. The rendered text keeps the mark."""

    modes = _HANGING.get()
    if not modes or low >= high:
        return 0.0
    deduct = 0.0
    taken: set[int] = set()
    if "first" in modes and _OPENING.get() and start == 0 and _opens(tokens[low].ch):
        deduct += _content_ink(tokens[low])
        taken.add(low)
    end = high - 1
    if end in taken:
        return deduct
    tok = tokens[end]
    hang = False
    if "last" in modes and at_segment_end and not before_forced and _closes(tok.ch):
        hang = True
    if tok.ch in _STOPS:
        if "force-end" in modes:
            hang = True
        elif "allow-end" in modes and content - deduct > width + _EPS:
            hang = True
    if hang:
        deduct += _content_ink(tok)
    return deduct


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
        text, content, full = base_text, base_width, base_width
    else:
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
            text, content, full = base_text + trail_text, base_width, base_width + trail_width
        else:
            content = base_width + trail_width
            if base_text and trail_text and low < len(tokens) and tokens[low].letter_spacing:
                content += tokens[low].letter_spacing
            text, content, full = base_text + trail_text, content, content
    content -= _hanging_deduction(
        tokens,
        low,
        high,
        start=start,
        content=content,
        width=width,
        at_segment_end=at_segment_end,
        before_forced=before_forced,
    )
    trimmed = _opening_trim(tokens, low, high) + _adjacent_trim(tokens, low, high)
    content -= trimmed
    full -= trimmed
    if content < 0:
        content = 0.0
    end_trim = _allow_end_trim(tokens, low, high, content, width)
    content -= end_trim
    full -= end_trim
    if content < 0:
        content = 0.0
    if full < content:
        full = content
    clone = _clone_fragment_chrome(tokens, low, high)
    if clone:
        content += clone
        full += clone
    return text, content, full


def _clone_ranges(value: object, length: int) -> tuple[tuple[int, int, float, float], ...]:
    """Source spans that repeat their end edges on every fragment."""

    if value in (None, (), []):
        return ()
    if not isinstance(value, (list, tuple)):
        raise _Invalid("clone ranges are unsupported")
    parsed: list[tuple[int, int, float, float]] = []
    for item in value:
        if not isinstance(item, (list, tuple)) or len(item) != 4:
            raise _Invalid("clone ranges are unsupported")
        start, end, lead, trail = item
        if isinstance(start, bool) or isinstance(end, bool):
            raise _Invalid("clone ranges are unsupported")
        if not isinstance(start, int) or not isinstance(end, int):
            raise _Invalid("clone ranges are unsupported")
        if start < 0 or end > length or start >= end:
            raise _Invalid("clone ranges are unsupported")
        parsed.append((start, end, _nonneg(lead, "clone lead"), _nonneg(trail, "clone trail")))
    return tuple(parsed)


def _clone_fragment_chrome(tokens: list[_Tok], low: int, high: int) -> float:
    """Chrome a fragment still owes after the first and last characters paid theirs."""

    ranges = _CLONE.get()
    if not ranges or low >= high:
        return 0.0
    extra = 0.0
    for start, end, lead, trail in ranges:
        last = end - 1
        present = False
        covers_first = False
        covers_last = False
        for tok in tokens[low:high]:
            if tok.end <= start or tok.start >= end:
                continue
            present = True
            if tok.start <= start < tok.end:
                covers_first = True
            if tok.start <= last < tok.end:
                covers_last = True
        if not present:
            continue
        if not covers_first:
            extra += lead
        if not covers_last:
            extra += trail
    return extra


def _used_hyphen_mark(value: object) -> str:
    """String drawn when a hyphenation break is taken."""

    if not isinstance(value, str):
        raise _Invalid("hyphenate_character is invalid")
    return value


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

    def _before(tok: _Tok) -> None:
        nonlocal x
        if not seen or not tok.grapheme_start:
            return
        if letter:
            x += letter
        if tok.autospace:
            x += tok.autospace

    for index, tok in enumerate(tokens):
        if tok.kind == "shy":
            if show_shy and index == last:
                mark = _HYPHEN_MARK.get()
                if mark:
                    _before(tok)
                    parts.append(mark)
                    x += tok.advance * len(mark)
                    if letter and len(mark) > 1:
                        x += letter * (len(mark) - 1)
                    seen = True
            continue
        if tok.kind == "tab":
            _before(tok)
            parts.append("\t")
            advance = _tab_advance(x, tab_size, space_advance)
            x += advance
            seen = True
            continue
        _before(tok)
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
        if prev.nowrap and cur.nowrap:
            continue
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
        if cur.autospace > _EPS:
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


def _phase1(
    text: str,
    white: str,
    adv: _Adv,
    ranges: tuple[tuple[int, int], ...] = (),
) -> list[_Tok]:
    """Tokenize once with the source span of each visible or collapsed unit."""
    pieces: list[_Tok] = []
    collapse = white in _COLLAPSE
    start = 0
    while start < len(text):
        ch = text[start]
        end = start + 1
        collapsible = collapse and ch in " \t\n\r"
        if collapsible:
            while end < len(text) and text[end] in " \t\n\r":
                end += 1
        held = _covers(ranges, start, end)
        if collapsible:
            if "\n" in text[start:end]:
                if white == "pre-line":
                    pieces.extend(
                        _Tok("break", "", 0.0, nowrap=held, start=i, end=i + 1)
                        for i in range(start, end) if text[i] == "\n"
                    )
                    start = end
                    continue
                if start > 0 and end < len(text) and _unspaced(text[start - 1]) and _unspaced(text[end]):
                    start = end
                    continue
            kind, ch, advance = "space", " ", adv.at(start)
        elif ch == "\n":
            kind, ch, advance = "break", "", 0.0
        elif ch == "\t":
            kind, advance = "tab", 0.0
        else:
            if ch in " \r":
                kind, ch = "space", " "
            elif ch == "\u00a0":
                kind = "nbsp"
            elif ch == "\u00ad":
                kind = "shy"
            elif _other_sep(ch):
                kind = "sep"
            else:
                kind = "glyph"
            advance = adv.of(ch, start)
        pieces.append(_Tok(kind, ch, advance, collapsible=collapsible, nowrap=held, start=start, end=end))
        start = end
    return pieces


def _nowrap_ranges(value: object) -> tuple[tuple[int, int], ...]:
    """Half-open source spans whose internal soft wraps are suppressed."""

    if value in (None, (), []):
        return ()
    if not isinstance(value, (list, tuple)):
        raise _Invalid("nowrap ranges are unsupported")
    ranges: list[tuple[int, int]] = []
    last = 0
    for item in value:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise _Invalid("nowrap ranges are unsupported")
        start, end = item
        if isinstance(start, bool) or isinstance(end, bool):
            raise _Invalid("nowrap ranges are unsupported")
        if not isinstance(start, int) or not isinstance(end, int) or start < last or end < start:
            raise _Invalid("nowrap ranges are unsupported")
        if end > start:
            ranges.append((start, end))
            last = end
    return tuple(ranges)


def _covers(ranges: tuple[tuple[int, int], ...], start: int, end: int) -> bool:
    if not ranges or end <= start:
        return False
    for low, high in ranges:
        if low <= start and end <= high:
            return True
        if low >= end:
            break
    return False


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


def source_line_tokens(
    source: str,
    white_space: str,
    rendered_lines: Iterable[str],
    *,
    hyphen_mark: str = "",
) -> list[_Tok]:
    """Recover the last supplied line's source spans, consuming earlier lines in order.

    A trimmed separator, a forced break, or an invisible soft hyphen may be
    skipped. ``hyphen_mark`` is the string painted at a taken hyphen break.
    When that string is not the next source character, an automatic break maps
    every mark glyph to the source boundary where the break was taken. A
    source soft hyphen keeps that character's span on the first glyph, and
    any further mark glyphs sit on the boundary after it. Any other synthetic
    glyph leaves the line unmapped.
    """

    mark = hyphen_mark if isinstance(hyphen_mark, str) else ""
    stream = iter(_phase1(source, white_space, _Adv(source, None)))
    token = next(stream, None)
    line: list[_Tok] = []
    for rendered in rendered_lines:
        line = []
        index = 0
        while index < len(rendered):
            ch = rendered[index]
            while token is not None and token.ch != ch:
                if _hyphen_mark_at(rendered, index, mark, token):
                    break
                at_break = not line and (token.kind == "break" or _trimmed_token(token, white_space))
                if token.kind != "shy" and not at_break:
                    return []
                token = next(stream, None)
            if _hyphen_mark_at(rendered, index, mark, token):
                if token is not None and token.kind == "shy":
                    advance = token.advance
                    boundary = token.end
                    token.ch = mark[0]
                    line.append(token)
                    for glyph in mark[1:]:
                        line.append(_Tok("shy", glyph, advance, start=boundary, end=boundary))
                    token = next(stream, None)
                else:
                    boundary = token.start if token is not None else len(source)
                    advance = line[-1].advance if line else 1.0
                    for glyph in mark:
                        line.append(_Tok("shy", glyph, advance, start=boundary, end=boundary))
                index += len(mark)
                continue
            if token is None:
                return []
            line.append(token)
            token = next(stream, None)
            index += 1
        if len(line) != len(rendered):
            return []
    return _mark_graphemes(line)


def _hyphen_mark_at(rendered: str, index: int, mark: str, token: _Tok | None) -> bool:
    """True when ``mark`` is painted here and is not the next source glyph."""

    if not mark or not rendered.startswith(mark, index):
        return False
    if token is not None and token.kind == "shy":
        return True
    return token is None or token.ch != rendered[index]


def _hyphen_letter(token: _Tok) -> bool:
    return token.kind == "glyph" and len(token.ch) == 1 and token.ch.isascii() and token.ch.isalpha()


def _with_auto_hyphens(tokens: list[_Tok], lang: str) -> list[_Tok]:
    """Insert soft-hyphen tokens at English pattern boundaries.

    The existing shy renderer draws U+2010 only when that boundary is the
    break actually taken. Min-content skips this pass. The hyphen uses the
    preceding letter's advance, which is one em in this measurer.
    """

    result: list[_Tok] = []
    index = 0
    count = len(tokens)
    while index < count:
        if not _hyphen_letter(tokens[index]):
            result.append(tokens[index])
            index += 1
            continue
        end = index + 1
        while end < count and _hyphen_letter(tokens[end]):
            end += 1
        word = "".join(tokens[cursor].ch for cursor in range(index, end))
        cuts = set(hyphenation_offsets(word, lang))
        for cursor in range(index, end):
            if cursor > index and (cursor - index) in cuts:
                result.append(_Tok("shy", "\u00ad", tokens[cursor - 1].advance))
            result.append(tokens[cursor])
        index = end
    return result


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


def _apply_autospace(tokens: list[_Tok], text_autospace: object, autospace: object) -> None:
    """Insert 1/8 ic between an ideograph and a Latin letter or digit.

    ``insert`` leaves an existing space alone. ``replace`` spends that space's
    advance and keeps only the autospace gap. The gap is also a soft wrap
    opportunity, so a narrow measure can break where the scripts meet.
    """

    mode = " ".join(str(text_autospace or "off").lower().split())
    if mode in {"", "off", "no-autospace"}:
        return
    parts = mode.split(" ")
    alpha = "ideograph-alpha" in parts
    numeric = "ideograph-numeric" in parts
    if not alpha and not numeric:
        return
    size = _finite(autospace, "autospace")
    if size <= _EPS:
        return
    _stamp_autospace(tokens, size, alpha=alpha, numeric=numeric, replace_spaces="replace" in parts)


def _autospace_class(ch: str) -> str:
    if _cjk_letter(ch):
        return "ideo"
    if _letter(ch):
        return "alpha"
    if _category(ch) == "Nd":
        return "num"
    return ""


def _autospace_boundary(left: str, right: str, *, alpha: bool, numeric: bool) -> bool:
    if not left or not right or left == right or "ideo" not in {left, right}:
        return False
    other = right if left == "ideo" else left
    if other == "alpha":
        return alpha
    if other == "num":
        return numeric
    return False


def _stamp_autospace(
    tokens: list[_Tok],
    size: float,
    *,
    alpha: bool,
    numeric: bool,
    replace_spaces: bool,
) -> None:
    last = ""
    spaces: list[_Tok] = []
    for tok in tokens:
        if tok.kind == "break":
            last = ""
            spaces = []
            continue
        if tok.kind in {"space", "sep", "tab"}:
            if last:
                spaces.append(tok)
            continue
        if not tok.grapheme_start or tok.kind not in {"glyph", "shy", "nbsp"}:
            continue
        current = _autospace_class(tok.ch)
        if _autospace_boundary(last, current, alpha=alpha, numeric=numeric):
            if not spaces:
                tok.autospace += size
            elif replace_spaces:
                for space in spaces:
                    space.advance = 0.0
                tok.autospace += size
        if current:
            last = current
            spaces = []
        else:
            last = ""
            spaces = []


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
