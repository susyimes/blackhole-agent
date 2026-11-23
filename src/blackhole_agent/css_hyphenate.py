"""Liang hyphenation for CSS ``hyphens: auto``.

A pattern is letters with a digit at each boundary. The highest level at a
boundary wins, and an odd level is a break. These patterns are a compact
English morphology, not a word list and not a copied TeX dictionary. A
language whose primary tag is not ``en`` has no resource. ``hyphenate-limit-chars:
auto`` uses the recommended 5 2 2 limits: the word must contain five letters,
and a break must leave two letters on each side. Explicit soft hyphens stay
the caller's job.
"""

from __future__ import annotations

_BEFORE = 2
_AFTER = 2
_MINIMUM = 5
_PATTERNS = (
    ".hy3ph",
    "n1a",
    "1tio",
    "1ter",
    "1ing",
)


def _compile(pattern: str) -> tuple[str, tuple[int, ...]]:
    chars: list[str] = []
    levels: list[int] = []
    pending = 0
    for ch in pattern:
        if ch.isdigit():
            pending = int(ch)
            continue
        levels.append(pending)
        pending = 0
        chars.append(ch.casefold())
    levels.append(pending)
    return "".join(chars), tuple(levels)


_COMPILED = tuple(_compile(pattern) for pattern in _PATTERNS)


def hyphenation_offsets(word: str, lang: str) -> tuple[int, ...]:
    """Return indexes in ``word`` after which an automatic hyphen may be drawn.

    An empty result leaves the word intact. Offsets point at the rendered
    letter run, not at the leading dot used by the patterns.
    """

    if len(word) < _MINIMUM or not word.isascii() or not word.isalpha():
        return ()
    primary = str(lang or "").casefold().split("-", 1)[0]
    if primary != "en":
        return ()
    padded = f".{word.casefold()}."
    points = [0] * (len(padded) + 1)
    for letters, levels in _COMPILED:
        start = 0
        while True:
            found = padded.find(letters, start)
            if found < 0:
                break
            for offset, level in enumerate(levels):
                index = found + offset
                if level > points[index]:
                    points[index] = level
            start = found + 1
    offsets: list[int] = []
    last = len(word) - _AFTER
    for count in range(_BEFORE, last + 1):
        if points[count + 1] % 2 == 1:
            offsets.append(count)
    return tuple(offsets)
