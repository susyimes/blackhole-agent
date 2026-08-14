"""Foraging fixture: an uncooperative module with mixed candidates.

Ships no manifest, no spec, and no probe cases. The foraging plane must
infer everything. Contains one viable unary string transform (``shout``),
a second viable one (``whisper``), a selection-only decoy (``brittle``
passes every selection probe but raises on the held-out empty input), a
two-argument candidate, and non-callable/private noise that introspection
must ignore.
"""

CONSTANT = 42


def shout(text):
    return text.upper() + "!"


def whisper(text):
    return text.lower()


def brittle(text):
    if not text:
        raise ValueError("empty input refused")
    return text.strip().title()


def needs_two(first, second):
    return first + second


def _hidden(text):
    return text
