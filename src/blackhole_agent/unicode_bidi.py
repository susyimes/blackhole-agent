"""Resolve one bidirectional paragraph to embedding levels and visual order.

UAX #9 classifies each character, applies explicit isolates and embeddings,
then resolves weak numbers, neutrals, and brackets. An isolate keeps the
characters inside it from changing the direction of the letters outside it.
A European number after an Arabic letter becomes an Arabic number, and a
separator between two numbers of the same kind joins them. A bracket pair
takes the direction of the strong text it encloses when that text has one.
Automatic paragraph direction follows the first strong character that is
not inside an isolate. The result is the left-to-right visual order.

Paired brackets are the Unicode 15.1 Bidi_Paired_Bracket set, the same
Unicode version as this interpreter's character database. Levels are the
resolved embedding levels after rule L1. Characters removed by rule X9 are
reported as missing levels and are absent from the visual order.
``resolve_bidi`` treats the paragraph as one line and does not mirror glyphs.
``reorder_bidi_lines`` applies L1 at each supplied line end, then L2, puts
combining marks back after an odd-level base, and mirrors an odd-level
character to its Unicode 15.1 mate.
"""

from __future__ import annotations

import unicodedata

_MAX_DEPTH = 125
_ISOLATES = frozenset({"LRI", "RLI", "FSI"})
_REMOVED = frozenset({"RLE", "LRE", "RLO", "LRO", "PDF", "BN"})
_NEUTRALS = frozenset({"B", "S", "WS", "ON", "FSI", "LRI", "RLI", "PDI"})
_TRAILING = frozenset({"WS", "FSI", "LRI", "RLI", "PDI"})
_DIRECTIONS = {"ltr": 0, "rtl": 1, "auto": 2}

# Opener maps to the closing mate. Unicode 15.1 BidiBrackets, including the
# crossed square brackets with ticks (U+298D/U+2990 and U+298F/U+298E).
_OPEN_MATE = {
    0x0028: 0x0029,
    0x005B: 0x005D,
    0x007B: 0x007D,
    0x0F3A: 0x0F3B,
    0x0F3C: 0x0F3D,
    0x169B: 0x169C,
    0x2045: 0x2046,
    0x207D: 0x207E,
    0x208D: 0x208E,
    0x2308: 0x2309,
    0x230A: 0x230B,
    0x2329: 0x232A,
    0x2768: 0x2769,
    0x276A: 0x276B,
    0x276C: 0x276D,
    0x276E: 0x276F,
    0x2770: 0x2771,
    0x2772: 0x2773,
    0x2774: 0x2775,
    0x27C5: 0x27C6,
    0x27E6: 0x27E7,
    0x27E8: 0x27E9,
    0x27EA: 0x27EB,
    0x27EC: 0x27ED,
    0x27EE: 0x27EF,
    0x2983: 0x2984,
    0x2985: 0x2986,
    0x2987: 0x2988,
    0x2989: 0x298A,
    0x298B: 0x298C,
    0x298D: 0x2990,
    0x298F: 0x298E,
    0x2991: 0x2992,
    0x2993: 0x2994,
    0x2995: 0x2996,
    0x2997: 0x2998,
    0x29D8: 0x29D9,
    0x29DA: 0x29DB,
    0x29FC: 0x29FD,
    0x2E22: 0x2E23,
    0x2E24: 0x2E25,
    0x2E26: 0x2E27,
    0x2E28: 0x2E29,
    0x2E55: 0x2E56,
    0x2E57: 0x2E58,
    0x2E59: 0x2E5A,
    0x2E5B: 0x2E5C,
    0x3008: 0x3009,
    0x300A: 0x300B,
    0x300C: 0x300D,
    0x300E: 0x300F,
    0x3010: 0x3011,
    0x3014: 0x3015,
    0x3016: 0x3017,
    0x3018: 0x3019,
    0x301A: 0x301B,
    0xFE59: 0xFE5A,
    0xFE5B: 0xFE5C,
    0xFE5D: 0xFE5E,
    0xFF08: 0xFF09,
    0xFF3B: 0xFF3D,
    0xFF5B: 0xFF5D,
    0xFF5F: 0xFF60,
    0xFF62: 0xFF63,
}
_CLOSERS = frozenset(_OPEN_MATE.values())
# U+2329/U+3008 share a canonical mate, as do their closers U+232A/U+3009.
_CANON_CLOSE = {0x232A: 0x3009, 0x3009: 0x232A}


class _Invalid(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class _Char:
    __slots__ = ("index", "cp", "orig", "type", "level")

    def __init__(self, index: int, cp: int, bidi_type: str) -> None:
        self.index = index
        self.cp = cp
        self.orig = bidi_type
        self.type = bidi_type
        self.level: int | None = None


def resolve_bidi(text: object, direction: object = "ltr") -> dict[str, object]:
    """Return embedding levels and left-to-right visual order for one string.

    ``direction`` is ``ltr``, ``rtl``, or ``auto``. ``auto`` uses the first
    strong character outside an isolate, and is left to right when there is
    none. A paragraph separator starts a new paragraph. Removed formatting
    marks and boundary neutrals have a missing level.
    """

    if isinstance(text, str) and isinstance(direction, str) and direction in _DIRECTIONS:
        return _resolve(text, _DIRECTIONS[direction])
    reason = "text must be a string" if not isinstance(text, str) else "direction must be ltr, rtl, or auto"
    return {
        "outcome": "invalid",
        "reason": reason,
        "paragraph_level": None,
        "levels": None,
        "visual_order": None,
    }


def _resolve(text: str, direction: int) -> dict[str, object]:
    chars = [_Char(index, ord(ch), _class(ch)) for index, ch in enumerate(text)]
    paragraphs = _paragraphs(chars)
    levels: list[int | None] = [None] * len(chars)
    visual: list[int] = []
    paragraph_levels: list[int] = []
    for content, separator in paragraphs:
        paragraph_level = _paragraph_level(content, direction)
        paragraph_levels.append(paragraph_level)
        _explicit(content, paragraph_level)
        _resolve_runs(content, paragraph_level)
        _line_level(content, paragraph_level)
        visual.extend(_reorder(content))
        if separator is not None:
            separator.level = paragraph_level
            visual.append(separator.index)
    for ch in chars:
        levels[ch.index] = ch.level
    return {
        "outcome": "resolved",
        "paragraph_level": paragraph_levels[0],
        "levels": levels,
        "visual_order": visual,
    }


def reorder_bidi_lines(text: object, line_ends: object, direction: object = "ltr") -> dict[str, object]:
    """Reorder each line after resolving the paragraph.

    ``line_ends`` are exclusive logical indexes. They must advance from the
    start and the last end must be the length of ``text``. An empty string
    has one empty line at ``[0]``. A line may include the paragraph separator
    that ends its paragraph, and may not continue into the next paragraph.
    Trailing whitespace on that line is reset to the paragraph embedding
    level before the line is reversed. The returned ``text`` is the visual
    string: combining marks follow an odd-level base, and an odd-level
    mirrored character is replaced by its mate.
    """

    if not isinstance(text, str):
        return _invalid_lines("text must be a string")
    if not isinstance(direction, str) or direction not in _DIRECTIONS:
        return _invalid_lines("direction must be ltr, rtl, or auto")
    try:
        ends = _ends(line_ends, len(text))
    except _Invalid as exc:
        return _invalid_lines(exc.reason)
    if not text:
        level = 1 if direction == "rtl" else 0
        return {
            "outcome": "reordered",
            "paragraph_level": level,
            "lines": [{"text": "", "levels": [], "visual_order": []}],
        }
    chars, base, paragraphs, paragraph_levels = _prepare(text, _DIRECTIONS[direction])
    lines: list[dict[str, object]] = []
    start = 0
    for end in ends:
        if len({paragraphs[index] for index in range(start, end)}) != 1:
            return _invalid_lines("line crosses a paragraph")
        segment = chars[start:end]
        for ch in segment:
            ch.level = base[ch.index]
        _line_level(segment, paragraph_levels[start])
        order = _place_marks(_reorder(segment), chars)
        lines.append(
            {
                "text": "".join(_mirrored(chars[index]) for index in order),
                "levels": [chars[index].level for index in order],
                "visual_order": order,
            }
        )
        start = end
    return {
        "outcome": "reordered",
        "paragraph_level": paragraph_levels[0],
        "lines": lines,
    }


def _invalid_lines(reason: str) -> dict[str, object]:
    return {
        "outcome": "invalid",
        "reason": reason,
        "paragraph_level": None,
        "lines": None,
    }


def _ends(value: object, length: int) -> list[int]:
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise _Invalid("line ends must be a list of indexes")
    if length == 0:
        if len(value) == 1 and value[0] == 0:
            return [0]
        raise _Invalid("line ends must cover the string")
    ends: list[int] = []
    previous = 0
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int):
            raise _Invalid("line ends must be a list of indexes")
        if item == previous:
            raise _Invalid("line is empty")
        if item < previous or item > length:
            raise _Invalid("line ends must cover the string")
        ends.append(item)
        previous = item
    if previous != length:
        raise _Invalid("line ends must cover the string")
    return ends


def _prepare(
    text: str, direction: int
) -> tuple[list[_Char], list[int | None], list[int], list[int]]:
    chars = [_Char(index, ord(ch), _class(ch)) for index, ch in enumerate(text)]
    paragraphs = [0] * len(chars)
    paragraph_levels = [0] * len(chars)
    paragraph_id = 0
    for content, separator in _paragraphs(chars):
        level = _paragraph_level(content, direction)
        _explicit(content, level)
        _resolve_runs(content, level)
        for ch in content:
            paragraphs[ch.index] = paragraph_id
            paragraph_levels[ch.index] = level
        if separator is not None:
            separator.level = level
            paragraphs[separator.index] = paragraph_id
            paragraph_levels[separator.index] = level
        paragraph_id += 1
    return chars, [ch.level for ch in chars], paragraphs, paragraph_levels


def _place_marks(order: list[int], chars: list[_Char]) -> list[int]:
    """Move combining marks that L2 left in front of an odd-level base."""

    visual = list(order)
    index = 0
    while index < len(visual):
        if not _combining(chars[visual[index]]):
            index += 1
            continue
        end = index
        while end < len(visual) and _combining(chars[visual[end]]):
            end += 1
        if end >= len(visual):
            break
        base = visual[end]
        base_level = chars[base].level
        if (
            base_level is None
            or base_level % 2 == 0
            or any(chars[visual[cursor]].level != base_level for cursor in range(index, end))
        ):
            index = end + 1
            continue
        marks = list(reversed(visual[index:end]))
        del visual[index:end]
        visual[index + 1 : index + 1] = marks
        index += 1 + len(marks)
    return visual


def _combining(ch: _Char) -> bool:
    return unicodedata.category(chr(ch.cp)).startswith("M")


def _mirrored(ch: _Char) -> str:
    glyph = chr(ch.cp)
    level = 0 if ch.level is None else ch.level
    if level % 2 == 0 or not unicodedata.mirrored(glyph):
        return glyph
    mate = _MIRROR_OF.get(ch.cp)
    return glyph if mate is None else chr(mate)


def _class(ch: str) -> str:
    bidi = unicodedata.bidirectional(ch)
    return bidi or "L"


def _paragraphs(chars: list[_Char]) -> list[tuple[list[_Char], _Char | None]]:
    parts: list[tuple[list[_Char], _Char | None]] = []
    current: list[_Char] = []
    for ch in chars:
        if ch.orig == "B":
            parts.append((current, ch))
            current = []
        else:
            current.append(ch)
    parts.append((current, None))
    return parts


def _paragraph_level(chars: list[_Char], direction: int) -> int:
    if direction != 2:
        return direction
    depth = 0
    for ch in chars:
        kind = ch.orig
        if kind in _ISOLATES:
            depth += 1
        elif kind == "PDI" and depth:
            depth -= 1
        elif depth == 0 and kind in {"R", "AL"}:
            return 1
        elif depth == 0 and kind == "L":
            return 0
    return 0


def _next_level(level: int, odd: bool) -> int:
    if odd:
        return level + 1 if level % 2 == 0 else level + 2
    return level + 2 if level % 2 == 0 else level + 1


def _explicit(chars: list[_Char], paragraph_level: int) -> None:
    stack: list[tuple[int, str | None, bool]] = [(paragraph_level, None, False)]
    overflow_isolate = 0
    overflow_embedding = 0
    valid_isolate = 0
    for index, ch in enumerate(chars):
        kind = ch.orig
        ch.level = paragraph_level
        if kind in {"RLE", "LRE", "RLO", "LRO"}:
            odd = kind in {"RLE", "RLO"}
            override = "R" if kind == "RLO" else "L" if kind == "LRO" else None
            if overflow_isolate:
                continue
            if overflow_embedding or _next_level(stack[-1][0], odd) > _MAX_DEPTH:
                overflow_embedding += 1
                continue
            stack.append((_next_level(stack[-1][0], odd), override, False))
            continue
        if kind in _ISOLATES:
            odd = kind == "RLI" or (kind == "FSI" and _isolate_rtl(chars, index))
            level, override, _isolate_flag = stack[-1]
            ch.level = level
            if override is not None:
                ch.type = override
            if overflow_isolate or overflow_embedding or _next_level(level, odd) > _MAX_DEPTH:
                overflow_isolate += 1
                continue
            stack.append((_next_level(level, odd), None, True))
            valid_isolate += 1
            continue
        if kind == "PDI":
            if overflow_isolate:
                overflow_isolate -= 1
            elif valid_isolate:
                overflow_embedding = 0
                while not stack[-1][2]:
                    stack.pop()
                stack.pop()
                valid_isolate -= 1
            level, override, _isolate_flag = stack[-1]
            ch.level = level
            if override is not None:
                ch.type = override
            continue
        if kind == "PDF":
            if overflow_isolate:
                continue
            if overflow_embedding:
                overflow_embedding -= 1
            elif len(stack) > 1 and not stack[-1][2]:
                stack.pop()
            continue
        if kind in {"BN", "B"}:
            continue
        level, override, _isolate_flag = stack[-1]
        ch.level = level
        if override is not None:
            ch.type = override
    for ch in chars:
        if ch.orig in _REMOVED:
            ch.level = None


def _isolate_rtl(chars: list[_Char], start: int) -> bool:
    depth = 1
    for ch in chars[start + 1 :]:
        if ch.orig in _ISOLATES:
            depth += 1
        elif ch.orig == "PDI":
            depth -= 1
            if depth == 0:
                return False
        elif depth == 1 and ch.orig in {"R", "AL"}:
            return True
        elif depth == 1 and ch.orig == "L":
            return False
    return False


def _resolve_runs(chars: list[_Char], paragraph_level: int) -> None:
    active = [ch for ch in chars if ch.level is not None]
    for content, sos, eor in _sequences(active, paragraph_level):
        for ch in content:
            if ch.type in _ISOLATES or ch.type == "PDI":
                ch.type = "ON"
        _weak(content, sos)
        _brackets(content, sos)
        _neutrals(content, sos, eor)
        _implicit(content)


def _sequences(chars: list[_Char], paragraph_level: int) -> list[tuple[list[_Char], str, str]]:
    """Group characters into isolating run sequences of one embedding level.

    An embedding changes the level and therefore starts another sequence.
    An isolate initiator is chained to the level run that begins with its
    matching PDI, while the characters inside the isolate form their own
    sequences.
    """

    if not chars:
        return []
    runs: list[list[_Char]] = [[chars[0]]]
    for ch in chars[1:]:
        if ch.level == runs[-1][-1].level:
            runs[-1].append(ch)
        else:
            runs.append([ch])
    matched: dict[int, _Char] = {}
    stack: list[_Char] = []
    for ch in chars:
        if ch.orig in _ISOLATES:
            stack.append(ch)
        elif ch.orig == "PDI" and stack:
            matched[id(stack.pop())] = ch
    matched_pdis = {id(pdi) for pdi in matched.values()}
    run_index = {id(run[0]): index for index, run in enumerate(runs)}
    consumed: set[int] = set()
    located = {id(ch): index for index, ch in enumerate(chars)}
    sequences: list[tuple[list[_Char], str, str]] = []
    for index, run in enumerate(runs):
        if index in consumed or id(run[0]) in matched_pdis:
            continue
        parts = [run]
        while True:
            tail = parts[-1][-1]
            pdi = matched.get(id(tail))
            if pdi is None:
                break
            continuation = run_index.get(id(pdi))
            if continuation is None or runs[continuation][0] is not pdi:
                break
            consumed.add(continuation)
            parts.append(runs[continuation])
        content = [ch for part in parts for ch in part]
        first = located[id(content[0])]
        last = located[id(content[-1])]
        before = paragraph_level if first == 0 else chars[first - 1].level or paragraph_level
        unmatched = content[-1].orig in _ISOLATES and id(content[-1]) not in matched
        if unmatched or last + 1 == len(chars):
            after = paragraph_level
        else:
            after = chars[last + 1].level or paragraph_level
        sos_level = max(content[0].level or 0, before)
        eor_level = max(content[-1].level or 0, after)
        sos = "L" if sos_level % 2 == 0 else "R"
        eor = "L" if eor_level % 2 == 0 else "R"
        sequences.append((content, sos, eor))
    return sequences


def _weak(chars: list[_Char], sos: str) -> None:
    for index, ch in enumerate(chars):
        if ch.type == "NSM":
            ch.type = chars[index - 1].type if index else sos
    for index, ch in enumerate(chars):
        if ch.type != "EN":
            continue
        previous = sos
        for earlier in range(index - 1, -1, -1):
            if chars[earlier].type in {"L", "R", "AL"}:
                previous = chars[earlier].type
                break
        if previous == "AL":
            ch.type = "AN"
    for ch in chars:
        if ch.type == "AL":
            ch.type = "R"
    for index in range(1, len(chars) - 1):
        kind = chars[index].type
        left = chars[index - 1].type
        right = chars[index + 1].type
        if kind == "ES" and left == "EN" and right == "EN":
            chars[index].type = "EN"
        elif kind == "CS" and left == right and left in {"EN", "AN"}:
            chars[index].type = left
    index = 0
    while index < len(chars):
        if chars[index].type != "ET":
            index += 1
            continue
        start = index
        while index < len(chars) and chars[index].type == "ET":
            index += 1
        before = start > 0 and chars[start - 1].type == "EN"
        after = index < len(chars) and chars[index].type == "EN"
        if before or after:
            for cursor in range(start, index):
                chars[cursor].type = "EN"
    for ch in chars:
        if ch.type in {"ES", "ET", "CS"}:
            ch.type = "ON"
    for index, ch in enumerate(chars):
        if ch.type != "EN":
            continue
        previous = sos
        for earlier in range(index - 1, -1, -1):
            if chars[earlier].type in {"L", "R"}:
                previous = chars[earlier].type
                break
        if previous == "L":
            ch.type = "L"


def _brackets(chars: list[_Char], sos: str) -> None:
    for opening, closing in _bracket_pairs(chars):
        embed = "L" if (chars[opening].level or 0) % 2 == 0 else "R"
        opposite = "R" if embed == "L" else "L"
        matched = False
        other = False
        for ch in chars[opening + 1 : closing]:
            side = _strong_side(ch.type)
            if side == embed:
                matched = True
                break
            if side is not None:
                other = True
        if matched:
            direction = embed
        elif other:
            previous = sos
            for earlier in range(opening - 1, -1, -1):
                side = _strong_side(chars[earlier].type)
                if side is not None:
                    previous = side
                    break
            direction = opposite if previous == opposite else embed
        else:
            continue
        chars[opening].type = direction
        chars[closing].type = direction
        for bracket_at in (opening, closing):
            cursor = bracket_at + 1
            while cursor < len(chars) and chars[cursor].orig == "NSM":
                chars[cursor].type = direction
                cursor += 1


def _bracket_pairs(chars: list[_Char]) -> list[tuple[int, int]]:
    stack: list[tuple[int, int]] = []
    pairs: list[tuple[int, int]] = []
    for index, ch in enumerate(chars):
        if ch.type != "ON":
            continue
        mate = _OPEN_MATE.get(ch.cp)
        if mate is not None:
            if len(stack) >= 63:
                return []
            stack.append((index, mate))
            continue
        if ch.cp not in _CLOSERS:
            continue
        match = None
        for slot in range(len(stack) - 1, -1, -1):
            expected = stack[slot][1]
            if expected == ch.cp or _CANON_CLOSE.get(expected) == ch.cp:
                match = slot
                break
        if match is None:
            continue
        pairs.append((stack[match][0], index))
        del stack[match:]
    pairs.sort()
    return pairs


def _neutrals(chars: list[_Char], sos: str, eor: str) -> None:
    index = 0
    while index < len(chars):
        if not _is_neutral(chars[index].type):
            index += 1
            continue
        start = index
        index += 1
        while index < len(chars) and _is_neutral(chars[index].type):
            index += 1
        left = sos if start == 0 else _strong_side(chars[start - 1].type)
        right = eor if index == len(chars) else _strong_side(chars[index].type)
        if left is not None and left == right:
            for cursor in range(start, index):
                chars[cursor].type = left
        else:
            for cursor in range(start, index):
                level = chars[cursor].level or 0
                chars[cursor].type = "L" if level % 2 == 0 else "R"


def _implicit(chars: list[_Char]) -> None:
    for ch in chars:
        level = ch.level or 0
        if level % 2 == 0:
            if ch.type == "R":
                ch.level = level + 1
            elif ch.type in {"AN", "EN"}:
                ch.level = level + 2
        elif ch.type in {"L", "AN", "EN"}:
            ch.level = level + 1


def _line_level(chars: list[_Char], paragraph_level: int) -> None:
    for index, ch in enumerate(chars):
        if ch.level is not None and ch.orig in {"S", "B"}:
            ch.level = paragraph_level
            _reset_before(chars, index - 1, paragraph_level)
    _reset_before(chars, len(chars) - 1, paragraph_level)


def _reset_before(chars: list[_Char], start: int, paragraph_level: int) -> None:
    cursor = start
    while cursor >= 0:
        ch = chars[cursor]
        if ch.level is None:
            cursor -= 1
            continue
        if ch.orig not in _TRAILING:
            break
        ch.level = paragraph_level
        cursor -= 1


def _reorder(chars: list[_Char]) -> list[int]:
    order = [ch.index for ch in chars if ch.level is not None]
    if not order:
        return []
    levels = {ch.index: ch.level for ch in chars}
    highest = max(level for level in levels.values() if level is not None)
    for threshold in range(highest, 0, -1):
        updated: list[int] = []
        run: list[int] = []
        for index in order:
            level = levels[index]
            if level is not None and level >= threshold:
                run.append(index)
                continue
            updated.extend(reversed(run))
            run = []
            updated.append(index)
        updated.extend(reversed(run))
        order = updated
    return order


def _strong_side(kind: str) -> str | None:
    if kind == "L":
        return "L"
    if kind in {"R", "EN", "AN"}:
        return "R"
    return None


def _is_neutral(kind: str) -> bool:
    return kind in _NEUTRALS


# Unicode 15.1 Bidi_Mirroring_Glyph, four hex digits each direction.
_MIRROR_HEX = (
    "0028002900290028003C003E003E003C005B005D005D005B007B007D007D007B00AB00BB00BB00AB0F3A0F3B0F3B0F3A0F3C0F3D0F3D0F3C"
    "169B169C169C169B2039203A203A20392045204620462045207D207E207E207D208D208E208E208D2208220B2209220C220A220D220B2208"
    "220C2209220D220A221529F5221F2BFE222029A32221299B222229A022242AEE223C223D223D223C224322CD2245224C224C224522522253"
    "225322522254225522552254226422652265226422662267226722662268226922692268226A226B226B226A226E226F226F226E22702271"
    "227122702272227322732272227422752275227422762277227722762278227922792278227A227B227B227A227C227D227D227C227E227F"
    "227F227E22802281228122802282228322832282228422852285228422862287228722862288228922892288228A228B228B228A228F2290"
    "2290228F2291229222922291229829B822A222A322A322A222A62ADE22A82AE422A92AE322AB2AE522B022B122B122B022B222B322B322B2"
    "22B422B522B522B422B622B722B722B622B827DC22C922CA22CA22C922CB22CC22CC22CB22CD224322D022D122D122D022D622D722D722D6"
    "22D822D922D922D822DA22DB22DB22DA22DC22DD22DD22DC22DE22DF22DF22DE22E022E122E122E022E222E322E322E222E422E522E522E4"
    "22E622E722E722E622E822E922E922E822EA22EB22EB22EA22EC22ED22ED22EC22F022F122F122F022F222FA22F322FB22F422FC22F622FD"
    "22F722FE22FA22F222FB22F322FC22F422FD22F622FE22F72308230923092308230A230B230B230A2329232A232A23292768276927692768"
    "276A276B276B276A276C276D276D276C276E276F276F276E27702771277127702772277327732772277427752775277427C327C427C427C3"
    "27C527C627C627C527C827C927C927C827CB27CD27CD27CB27D527D627D627D527DC22B827DD27DE27DE27DD27E227E327E327E227E427E5"
    "27E527E427E627E727E727E627E827E927E927E827EA27EB27EB27EA27EC27ED27ED27EC27EE27EF27EF27EE298329842984298329852986"
    "2986298529872988298829872989298A298A2989298B298C298C298B298D2990298E298F298F298E2990298D299129922992299129932994"
    "2994299329952996299629952997299829982997299B222129A0222229A3222029A429A529A529A429A829A929A929A829AA29AB29AB29AA"
    "29AC29AD29AD29AC29AE29AF29AF29AE29B8229829C029C129C129C029C429C529C529C429CF29D029D029CF29D129D229D229D129D429D5"
    "29D529D429D829D929D929D829DA29DB29DB29DA29E829E929E929E829F5221529F829F929F929F829FC29FD29FD29FC2A2B2A2C2A2C2A2B"
    "2A2D2A2E2A2E2A2D2A342A352A352A342A3C2A3D2A3D2A3C2A642A652A652A642A792A7A2A7A2A792A7B2A7C2A7C2A7B2A7D2A7E2A7E2A7D"
    "2A7F2A802A802A7F2A812A822A822A812A832A842A842A832A852A862A862A852A872A882A882A872A892A8A2A8A2A892A8B2A8C2A8C2A8B"
    "2A8D2A8E2A8E2A8D2A8F2A902A902A8F2A912A922A922A912A932A942A942A932A952A962A962A952A972A982A982A972A992A9A2A9A2A99"
    "2A9B2A9C2A9C2A9B2A9D2A9E2A9E2A9D2A9F2AA02AA02A9F2AA12AA22AA22AA12AA62AA72AA72AA62AA82AA92AA92AA82AAA2AAB2AAB2AAA"
    "2AAC2AAD2AAD2AAC2AAF2AB02AB02AAF2AB12AB22AB22AB12AB32AB42AB42AB32AB52AB62AB62AB52AB72AB82AB82AB72AB92ABA2ABA2AB9"
    "2ABB2ABC2ABC2ABB2ABD2ABE2ABE2ABD2ABF2AC02AC02ABF2AC12AC22AC22AC12AC32AC42AC42AC32AC52AC62AC62AC52AC72AC82AC82AC7"
    "2AC92ACA2ACA2AC92ACB2ACC2ACC2ACB2ACD2ACE2ACE2ACD2ACF2AD02AD02ACF2AD12AD22AD22AD12AD32AD42AD42AD32AD52AD62AD62AD5"
    "2ADE22A62AE322A92AE422A82AE522AB2AEC2AED2AED2AEC2AEE22242AF72AF82AF82AF72AF92AFA2AFA2AF92BFE221F2E022E032E032E02"
    "2E042E052E052E042E092E0A2E0A2E092E0C2E0D2E0D2E0C2E1C2E1D2E1D2E1C2E202E212E212E202E222E232E232E222E242E252E252E24"
    "2E262E272E272E262E282E292E292E282E552E562E562E552E572E582E582E572E592E5A2E5A2E592E5B2E5C2E5C2E5B3008300930093008"
    "300A300B300B300A300C300D300D300C300E300F300F300E3010301130113010301430153015301430163017301730163018301930193018"
    "301A301B301B301AFE59FE5AFE5AFE59FE5BFE5CFE5CFE5BFE5DFE5EFE5EFE5DFE64FE65FE65FE64FF08FF09FF09FF08FF1CFF1EFF1EFF1C"
    "FF3BFF3DFF3DFF3BFF5BFF5DFF5DFF5BFF5FFF60FF60FF5FFF62FF63FF63FF62"
)


def _mirror_map() -> dict[int, int]:
    raw = "".join(_MIRROR_HEX)
    return {
        int(raw[index : index + 4], 16): int(raw[index + 4 : index + 8], 16)
        for index in range(0, len(raw), 8)
    }


_MIRROR_OF = _mirror_map()
