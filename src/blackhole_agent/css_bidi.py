"""Reorder one CSS bidi paragraph into visual order.

CSS Writing Modes sets the paragraph embedding level from ``direction``
(UAX #9 HL1). ``unicode-bidi: plaintext`` is the exception and uses rules
P2–P3. On a block, ``embed`` and ``isolate`` do not add controls;
``bidi-override`` and ``isolate-override`` wrap the root inline in LRO or
RLO. Inline boxes use ``bidi_controls`` for the same table, including
isolates. The paragraph is then reordered by UAX #9: explicit levels,
isolating runs, weak and neutral resolution, implicit levels, and L1–L3.

Characters removed by rule X9 (embeddings, overrides, PDF, and boundary
neutrals) are omitted from ``visual``. Their ``levels`` entries keep the
explicit embedding level. Bracket matching uses the Unicode 18 bracket
pairs. Glyph mirroring (L4) stays a font choice; the stored character is
returned.
"""

from __future__ import annotations

import unicodedata

_MAX_DEPTH = 125
_MAX_BRACKETS = 63
_DIRECTIONS = frozenset({"ltr", "rtl"})
_BIDI = frozenset({"normal", "embed", "isolate", "bidi-override", "isolate-override", "plaintext"})
_REMOVED = frozenset({"RLE", "LRE", "RLO", "LRO", "PDF", "BN"})
_ISOLATE = frozenset({"LRI", "RLI", "FSI"})
_NI = frozenset({"B", "S", "WS", "ON", "FSI", "LRI", "RLI", "PDI"})
_L1_TRAIL = frozenset({"WS", "FSI", "LRI", "RLI", "PDI"})
_CANON = {0x2329: 0x3008, 0x232A: 0x3009}

# Unicode 18 BidiBrackets.txt. Each opening maps to its closing mate.
_PAIRS = (
    (0x0028, 0x0029), (0x005B, 0x005D), (0x007B, 0x007D), (0x0F3A, 0x0F3B),
    (0x0F3C, 0x0F3D), (0x169B, 0x169C), (0x2045, 0x2046), (0x207D, 0x207E),
    (0x208D, 0x208E), (0x2308, 0x2309), (0x230A, 0x230B), (0x2329, 0x232A),
    (0x2768, 0x2769), (0x276A, 0x276B), (0x276C, 0x276D), (0x276E, 0x276F),
    (0x2770, 0x2771), (0x2772, 0x2773), (0x2774, 0x2775), (0x27C5, 0x27C6),
    (0x27E6, 0x27E7), (0x27E8, 0x27E9), (0x27EA, 0x27EB), (0x27EC, 0x27ED),
    (0x27EE, 0x27EF), (0x2983, 0x2984), (0x2985, 0x2986), (0x2987, 0x2988),
    (0x2989, 0x298A), (0x298B, 0x298C), (0x298D, 0x2990), (0x298F, 0x298E),
    (0x2991, 0x2992), (0x2993, 0x2994), (0x2995, 0x2996), (0x2997, 0x2998),
    (0x29D8, 0x29D9), (0x29DA, 0x29DB), (0x29FC, 0x29FD), (0x2E22, 0x2E23),
    (0x2E24, 0x2E25), (0x2E26, 0x2E27), (0x2E28, 0x2E29), (0x2E55, 0x2E56),
    (0x2E57, 0x2E58), (0x2E59, 0x2E5A), (0x2E5B, 0x2E5C), (0x2E62, 0x2E63),
    (0x3008, 0x3009), (0x300A, 0x300B), (0x300C, 0x300D), (0x300E, 0x300F),
    (0x3010, 0x3011), (0x3014, 0x3015), (0x3016, 0x3017), (0x3018, 0x3019),
    (0x301A, 0x301B), (0xFE59, 0xFE5A), (0xFE5B, 0xFE5C), (0xFE5D, 0xFE5E),
    (0xFF08, 0xFF09), (0xFF3B, 0xFF3D), (0xFF5B, 0xFF5D), (0xFF5F, 0xFF60),
    (0xFF62, 0xFF63),
)
_OPEN = {left: right for left, right in _PAIRS}
_CLOSE = {right for _left, right in _PAIRS}


class _Invalid(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def bidi_controls(direction: object, unicode_bidi: object = "isolate") -> tuple[str, str]:
    """Return the start and end controls CSS injects for one inline box.

    ``normal`` injects nothing. ``isolate-override`` nests an override inside
    an FSI. ``plaintext`` uses FSI for either direction.
    """

    flow = _keyword(direction, _DIRECTIONS, "direction")
    mode = _keyword(unicode_bidi, _BIDI, "unicode-bidi")
    if mode == "normal":
        return "", ""
    if mode == "embed":
        return ("\u202a", "\u202c") if flow == "ltr" else ("\u202b", "\u202c")
    if mode == "isolate":
        return ("\u2066", "\u2069") if flow == "ltr" else ("\u2067", "\u2069")
    if mode == "bidi-override":
        return ("\u202d", "\u202c") if flow == "ltr" else ("\u202e", "\u202c")
    if mode == "isolate-override":
        return ("\u2068\u202d", "\u202c\u2069") if flow == "ltr" else ("\u2068\u202e", "\u202c\u2069")
    return "\u2068", "\u2069"


def reorder_css_bidi(
    text: object,
    *,
    direction: object = "ltr",
    unicode_bidi: object = "normal",
) -> dict[str, object]:
    """Return the visual order and embedding level of one bidi paragraph.

    ``direction`` is the paragraph's containing block. ``unicode_bidi``
    ``plaintext`` takes the first strong character of each paragraph instead.
    A block's ``embed`` or ``isolate`` does not wrap the paragraph; use
    ``bidi_controls`` for an inline box. Paragraph separators stay with the
    preceding paragraph and are reordered with it.
    """

    try:
        flow = _keyword(direction, _DIRECTIONS, "direction")
        mode = _keyword(unicode_bidi, _BIDI, "unicode-bidi")
        if not isinstance(text, str):
            raise _Invalid("text is invalid")
    except _Invalid as exc:
        return _invalid(exc.reason)
    prepared, mapping, forced = _prepare(text, flow, mode)
    order, levels, paragraph_levels = _reorder(prepared, forced)
    projected = [0] * len(text)
    for index, source in enumerate(mapping):
        if source is not None:
            projected[source] = levels[index]
    fallback = 0 if forced is None else forced
    return {
        "outcome": "reordered",
        "visual": "".join(prepared[index] for index in order),
        "levels": projected,
        "paragraph_level": paragraph_levels[0] if paragraph_levels else fallback,
        "paragraph_levels": paragraph_levels,
    }


def _prepare(text: str, direction: str, unicode_bidi: str) -> tuple[str, list[int | None], int | None]:
    forced = None if unicode_bidi == "plaintext" else (0 if direction == "ltr" else 1)
    if unicode_bidi not in {"bidi-override", "isolate-override"}:
        return text, list(range(len(text))), forced
    prefix = "\u202d" if direction == "ltr" else "\u202e"
    suffix = "\u202c"
    chars: list[str] = []
    mapping: list[int | None] = []
    start = 0

    def flush(end: int) -> None:
        if start == end:
            return
        chars.append(prefix)
        mapping.append(None)
        for index in range(start, end):
            chars.append(text[index])
            mapping.append(index)
        chars.append(suffix)
        mapping.append(None)

    for index, char in enumerate(text):
        if _class(char) == "B":
            flush(index)
            chars.append(char)
            mapping.append(index)
            start = index + 1
    flush(len(text))
    return "".join(chars), mapping, forced


def bidi_line_order(text: str, direction: str) -> tuple[list[int], list[int]]:
    """Return visual source indices and logical embedding levels for a laid-out line."""
    flow = _keyword(direction, _DIRECTIONS, "direction")
    order, levels, _ = _reorder(text, 1 if flow == "rtl" else 0)
    return order, levels


def _reorder(text: str, forced: int | None) -> tuple[list[int], list[int], list[int]]:
    original = [_class(char) for char in text]
    levels = [0] * len(text)
    order: list[int] = []
    paragraph_levels: list[int] = []
    for start, end in _paragraph_spans(original):
        base = forced if forced is not None else _auto_level(original, start, end)
        paragraph_levels.append(base)
        order.extend(_paragraph(text, original, levels, start, end, base))
    return order, levels, paragraph_levels


def _paragraph(
    text: str,
    original: list[str],
    levels: list[int],
    start: int,
    end: int,
    base: int,
) -> list[int]:
    types = original[start:end]
    explicit = [base] * (end - start)
    removed = [False] * (end - start)
    matching = _explicit(types, explicit, removed, base)
    for sequence in _sequences(types, explicit, removed, matching):
        _resolve(text, original, types, explicit, removed, levels, sequence, matching, base, start)
    for offset, gone in enumerate(removed):
        if gone:
            levels[start + offset] = explicit[offset]
    retained = [start + offset for offset, gone in enumerate(removed) if not gone]
    _reset_line_edges(original, levels, retained, base)
    order = _reverse_levels(levels, retained)
    return _restore_marks(original, order)


def _explicit(
    types: list[str],
    explicit: list[int],
    removed: list[bool],
    base: int,
) -> dict[int, int]:
    """Rules X1–X8. Return paragraph-local initiator index to matching PDI."""

    structural = _isolate_matches(types)
    stack: list[tuple[int, str, bool, int | None]] = [(base, "neutral", False, None)]
    overflow_isolate = 0
    overflow_embedding = 0
    valid_isolate = 0
    matching: dict[int, int] = {}
    for offset, kind in enumerate(types):
        if kind == "B":
            explicit[offset] = base
            continue
        if kind == "FSI":
            stop = structural.get(offset, len(types))
            kind = "RLI" if _auto_level(types, offset + 1, stop) == 1 else "LRI"
            types[offset] = kind
        level, override, _isolate, _initiator = stack[-1]
        if kind in {"RLE", "LRE", "RLO", "LRO"}:
            explicit[offset] = level
            removed[offset] = True
            odd = kind in {"RLE", "RLO"}
            nxt = _next_level(level, odd)
            if nxt <= _MAX_DEPTH and overflow_isolate == 0 and overflow_embedding == 0:
                status = "neutral" if kind in {"RLE", "LRE"} else ("R" if kind == "RLO" else "L")
                stack.append((nxt, status, False, None))
            elif overflow_isolate == 0:
                overflow_embedding += 1
            continue
        if kind in {"RLI", "LRI"}:
            explicit[offset] = level
            if override != "neutral":
                types[offset] = "L" if override == "L" else "R"
            nxt = _next_level(level, kind == "RLI")
            if nxt <= _MAX_DEPTH and overflow_isolate == 0 and overflow_embedding == 0:
                valid_isolate += 1
                stack.append((nxt, "neutral", True, offset))
            else:
                overflow_isolate += 1
            continue
        if kind == "PDI":
            if overflow_isolate > 0:
                overflow_isolate -= 1
            elif valid_isolate > 0:
                overflow_embedding = 0
                while not stack[-1][2]:
                    stack.pop()
                initiator = stack.pop()[3]
                valid_isolate -= 1
                if initiator is not None:
                    matching[initiator] = offset
            level, override, _isolate, _initiator = stack[-1]
            explicit[offset] = level
            if override != "neutral":
                types[offset] = "L" if override == "L" else "R"
            continue
        if kind == "PDF":
            removed[offset] = True
            if overflow_isolate > 0:
                pass
            elif overflow_embedding > 0:
                overflow_embedding -= 1
            elif not stack[-1][2] and len(stack) >= 2:
                stack.pop()
            explicit[offset] = stack[-1][0]
            continue
        if kind == "BN":
            explicit[offset] = level
            removed[offset] = True
            continue
        explicit[offset] = level
        if override == "L":
            types[offset] = "L"
        elif override == "R":
            types[offset] = "R"
    return matching


def _sequences(
    types: list[str],
    explicit: list[int],
    removed: list[bool],
    matching: dict[int, int],
) -> list[list[int]]:
    """BD13 isolating run sequences of paragraph-local indexes."""

    runs: list[list[int]] = []
    current: list[int] = []
    last_level: int | None = None
    for offset, gone in enumerate(removed):
        if gone:
            continue
        level = explicit[offset]
        if last_level is None or level != last_level:
            if current:
                runs.append(current)
            current = [offset]
            last_level = level
        else:
            current.append(offset)
    if current:
        runs.append(current)
    starts = {run[0]: index for index, run in enumerate(runs)}
    sequences: list[list[int]] = []
    consumed: set[int] = set()
    for index, run in enumerate(runs):
        if index in consumed:
            continue
        chosen = [index]
        consumed.add(index)
        while True:
            last = runs[chosen[-1]][-1]
            pdi = matching.get(last)
            if pdi is None or types[last] not in _ISOLATE:
                break
            nxt = starts.get(pdi)
            if nxt is None:
                break
            chosen.append(nxt)
            consumed.add(nxt)
        merged: list[int] = []
        for run_index in chosen:
            merged.extend(runs[run_index])
        sequences.append(merged)
    return sequences


def _resolve(
    text: str,
    original: list[str],
    types: list[str],
    explicit: list[int],
    removed: list[bool],
    levels: list[int],
    sequence: list[int],
    matching: dict[int, int],
    base: int,
    origin: int,
) -> None:
    if not sequence:
        return
    level = explicit[sequence[0]]
    first = sequence[0]
    last = sequence[-1]
    sos = _edge(explicit[first], _neighbor(explicit, removed, first, -1, base))
    if types[last] in _ISOLATE and last not in matching:
        eos_level = base
    else:
        eos_level = _neighbor(explicit, removed, last, 1, base)
    eos = _edge(explicit[last], eos_level)
    local = [types[offset] for offset in sequence]
    _weak(local, sos)
    _neutrals(text, original, local, sequence, level, sos, eos, origin)
    for slot, offset in enumerate(sequence):
        types[offset] = local[slot]
        levels[origin + offset] = _implicit(level, local[slot])


def _weak(types: list[str], sos: str) -> None:
    for index, kind in enumerate(types):
        if kind != "NSM":
            continue
        if index == 0:
            types[index] = sos
            continue
        previous = types[index - 1]
        types[index] = "ON" if previous in _ISOLATE or previous == "PDI" else previous
    for index, kind in enumerate(types):
        if kind == "EN" and _previous_strong(types, index, sos, arabic=True, numbers=False) == "AL":
            types[index] = "AN"
    for index, kind in enumerate(types):
        if kind == "AL":
            types[index] = "R"
    for index in range(1, len(types) - 1):
        kind = types[index]
        left, right = types[index - 1], types[index + 1]
        if kind == "ES" and left == "EN" and right == "EN":
            types[index] = "EN"
        elif kind == "CS" and left == right and left in {"EN", "AN"}:
            types[index] = left
    index = 0
    while index < len(types):
        if types[index] != "ET":
            index += 1
            continue
        end = index
        while end < len(types) and types[end] == "ET":
            end += 1
        left = types[index - 1] if index else ""
        right = types[end] if end < len(types) else ""
        if left == "EN" or right == "EN":
            for slot in range(index, end):
                types[slot] = "EN"
        index = end
    for index, kind in enumerate(types):
        if kind in {"ES", "CS", "ET"}:
            types[index] = "ON"
    for index, kind in enumerate(types):
        if kind == "EN" and _previous_strong(types, index, sos, arabic=False, numbers=False) == "L":
            types[index] = "L"


def _neutrals(
    text: str,
    original: list[str],
    types: list[str],
    sequence: list[int],
    level: int,
    sos: str,
    eos: str,
    origin: int,
) -> None:
    embed = "R" if level % 2 else "L"
    for opening, closing in _bracket_pairs(text, types, sequence, origin):
        _resolve_bracket(original, types, sequence, opening, closing, embed, sos, origin)
    index = 0
    while index < len(types):
        if types[index] not in _NI:
            index += 1
            continue
        end = index
        while end < len(types) and types[end] in _NI:
            end += 1
        left = _side(types[index - 1] if index else sos)
        right = _side(types[end] if end < len(types) else eos)
        if left is not None and left == right:
            for slot in range(index, end):
                types[slot] = left
        index = end
    for index, kind in enumerate(types):
        if kind in _NI:
            types[index] = embed


def _resolve_bracket(
    original: list[str],
    types: list[str],
    sequence: list[int],
    opening: int,
    closing: int,
    embed: str,
    sos: str,
    origin: int,
) -> None:
    open_at = sequence.index(opening)
    close_at = sequence.index(closing)
    matched = False
    opposite = False
    for slot in range(open_at + 1, close_at):
        side = _strong(types[slot])
        if side == embed:
            matched = True
            break
        if side is not None:
            opposite = True
    if matched:
        chosen = embed
    elif opposite:
        previous = _previous_strong(types, open_at, sos, arabic=False, numbers=True)
        chosen = previous if previous != embed else embed
    else:
        return
    types[open_at] = chosen
    types[close_at] = chosen
    for slot in (open_at, close_at):
        nxt = slot + 1
        while nxt < len(types) and nxt != close_at and original[origin + sequence[nxt]] == "NSM":
            types[nxt] = chosen
            nxt += 1


def _bracket_pairs(text: str, types: list[str], sequence: list[int], origin: int) -> list[tuple[int, int]]:
    stack: list[tuple[int, int]] = []
    pairs: list[tuple[int, int]] = []
    for slot, offset in enumerate(sequence):
        if types[slot] != "ON":
            continue
        code = ord(text[origin + offset])
        mate = _OPEN.get(code)
        if mate is not None:
            if len(stack) == _MAX_BRACKETS:
                return []
            stack.append((_canon(mate), offset))
            continue
        if code not in _CLOSE:
            continue
        found = None
        for depth in range(len(stack) - 1, -1, -1):
            if stack[depth][0] == _canon(code):
                found = depth
                break
        if found is None:
            continue
        pairs.append((stack[found][1], offset))
        del stack[found:]
    pairs.sort()
    return pairs


def _reset_line_edges(original: list[str], levels: list[int], retained: list[int], base: int) -> None:
    reset = [False] * len(retained)
    for pos, index in enumerate(retained):
        if original[index] not in {"S", "B"}:
            continue
        reset[pos] = True
        prev = pos - 1
        while prev >= 0 and original[retained[prev]] in _L1_TRAIL:
            reset[prev] = True
            prev -= 1
    pos = len(retained) - 1
    while pos >= 0 and original[retained[pos]] in _L1_TRAIL:
        reset[pos] = True
        pos -= 1
    for pos, index in enumerate(retained):
        if reset[pos]:
            levels[index] = base


def _reverse_levels(levels: list[int], retained: list[int]) -> list[int]:
    order = list(retained)
    if not order:
        return order
    highest = max(levels[index] for index in order)
    for level in range(highest, 0, -1):
        merged: list[int] = []
        index = 0
        while index < len(order):
            if levels[order[index]] < level:
                merged.append(order[index])
                index += 1
                continue
            end = index + 1
            while end < len(order) and levels[order[end]] >= level:
                end += 1
            merged.extend(reversed(order[index:end]))
            index = end
        order = merged
    return order


def _restore_marks(original: list[str], order: list[int]) -> list[int]:
    restored: list[int] = []
    index = 0
    while index < len(order):
        if original[order[index]] != "NSM":
            restored.append(order[index])
            index += 1
            continue
        end = index
        while end < len(order) and original[order[end]] == "NSM":
            end += 1
        if end == len(order):
            restored.extend(order[index:end])
            break
        cluster = order[index : end + 1]
        cluster.reverse()
        restored.extend(cluster)
        index = end + 1
    return restored


def _neighbor(explicit: list[int], removed: list[bool], offset: int, step: int, base: int) -> int:
    index = offset + step
    while 0 <= index < len(explicit) and removed[index]:
        index += step
    if not 0 <= index < len(explicit):
        return base
    return explicit[index]


def _edge(level: int, other: int) -> str:
    return "R" if max(level, other) % 2 else "L"


def _previous_strong(types: list[str], index: int, sos: str, *, arabic: bool, numbers: bool) -> str:
    for slot in range(index - 1, -1, -1):
        kind = types[slot]
        if kind in {"L", "R"}:
            return kind
        if arabic and kind == "AL":
            return "AL"
        if numbers and kind in {"EN", "AN"}:
            return "R"
    return sos


def _strong(kind: str) -> str | None:
    if kind == "L":
        return "L"
    if kind in {"R", "EN", "AN"}:
        return "R"
    return None


def _side(kind: str) -> str | None:
    if kind == "L":
        return "L"
    if kind in {"R", "EN", "AN"}:
        return "R"
    return None


def _implicit(level: int, kind: str) -> int:
    if level % 2 == 0:
        if kind == "R":
            return level + 1
        if kind in {"AN", "EN"}:
            return level + 2
        return level
    if kind in {"L", "EN", "AN"}:
        return level + 1
    return level


def _next_level(level: int, odd: bool) -> int:
    if odd:
        return level + 1 if level % 2 == 0 else level + 2
    return level + 2 if level % 2 == 0 else level + 1


def _isolate_matches(types: list[str]) -> dict[int, int]:
    match: dict[int, int] = {}
    stack: list[int] = []
    for offset, kind in enumerate(types):
        if kind in _ISOLATE:
            stack.append(offset)
        elif kind == "PDI" and stack:
            match[stack.pop()] = offset
    return match


def _auto_level(types: list[str], start: int, end: int) -> int:
    structural = _isolate_matches(types)
    index = start
    while index < end:
        kind = types[index]
        if kind in _ISOLATE:
            index = structural.get(index, end - 1) + 1
            continue
        if kind in {"R", "AL"}:
            return 1
        if kind == "L":
            return 0
        index += 1
    return 0


def _paragraph_spans(types: list[str]) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    start = 0
    for index, kind in enumerate(types):
        if kind == "B":
            spans.append((start, index + 1))
            start = index + 1
    if start < len(types) or not spans:
        spans.append((start, len(types)))
    return spans


def _class(char: str) -> str:
    kind = unicodedata.bidirectional(char)
    return kind or "ON"


def _canon(code: int) -> int:
    return _CANON.get(code, code)


def _keyword(value: object, allowed: frozenset[str], name: str) -> str:
    if not isinstance(value, str) or value.lower() not in allowed:
        raise _Invalid(f"{name} is invalid")
    return value.lower()


def _invalid(reason: str) -> dict[str, object]:
    return {
        "outcome": "invalid",
        "visual": None,
        "levels": None,
        "paragraph_level": None,
        "paragraph_levels": None,
        "reason": reason,
    }
