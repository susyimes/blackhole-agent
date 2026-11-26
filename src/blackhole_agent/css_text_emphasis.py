"""CSS text-emphasis marks for one horizontal line.

CSS Text Decoration 3. ``filled`` and ``open`` select the dot when the shape
is omitted, and a named shape defaults to filled. A one-character string is
that mark. ``none`` paints nothing. The position's over or under side is the
block axis; ``left`` and ``right`` are accepted beside it and do not move a
horizontal mark. A bare side, with no over or under, is invalid.

This engine has no emphasis glyph in a font file. The mark band is half the
em, at least one pixel, and the mark box is that square centered in the
character advance. A leftover pixel stays on the inline end.
"""

from __future__ import annotations

_FILLED = {
    "dot": "\u2022",
    "circle": "\u25cf",
    "double-circle": "\u25c9",
    "triangle": "\u25b2",
    "sesame": "\ufe45",
}
_OPEN = {
    "dot": "\u25e6",
    "circle": "\u25cb",
    "double-circle": "\u25ce",
    "triangle": "\u25b3",
    "sesame": "\ufe46",
}
_WIDE = frozenset({"inherit", "unset", "revert"})


class EmphasisError(ValueError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def resolve_emphasis_style(value: str | None, parent: str) -> str:
    """Computed mark character. An empty string paints nothing."""

    if value is None:
        return parent
    token = " ".join(value.strip().split())
    lowered = token.lower()
    if lowered in _WIDE:
        return parent
    if lowered == "initial":
        return ""
    if lowered == "revert-layer":
        raise EmphasisError("text emphasis is invalid")
    return _parse_style(token)


def resolve_emphasis_position(value: str | None, parent: str) -> str:
    """Computed block side, ``over`` or ``under``."""

    if value is None:
        return parent or "over"
    token = " ".join(value.strip().split())
    lowered = token.lower()
    if lowered in _WIDE:
        return parent or "over"
    if lowered == "initial":
        return "over"
    if lowered == "revert-layer":
        raise EmphasisError("text emphasis is invalid")
    return _parse_position(lowered)


def emphasis_band(font_size: int) -> int:
    if isinstance(font_size, bool) or not isinstance(font_size, int) or font_size < 1:
        raise EmphasisError("text emphasis is invalid")
    return max(1, font_size // 2)


def _parse_style(value: str) -> str:
    if value[:1] in {'"', "'"}:
        return _parse_string(value)
    parts = value.lower().split()
    if parts == ["none"]:
        return ""
    if not parts or "none" in parts:
        raise EmphasisError("text emphasis is invalid")
    filled = True
    saw_fill = False
    shape: str | None = None
    for part in parts:
        if part in {"filled", "open"}:
            if saw_fill:
                raise EmphasisError("text emphasis is invalid")
            saw_fill = True
            filled = part == "filled"
            continue
        if part in _FILLED:
            if shape is not None:
                raise EmphasisError("text emphasis is invalid")
            shape = part
            continue
        raise EmphasisError("text emphasis is invalid")
    if shape is None and not saw_fill:
        raise EmphasisError("text emphasis is invalid")
    chosen = shape or "dot"
    return (_FILLED if filled else _OPEN)[chosen]


def _parse_string(value: str) -> str:
    if len(value) < 2 or value[0] not in {'"', "'"} or value[-1] != value[0]:
        raise EmphasisError("text emphasis is invalid")
    body = value[1:-1]
    if len(body) != 1 or "\\" in body or body in {'"', "'"}:
        raise EmphasisError("text emphasis is invalid")
    return body


def _parse_position(value: str) -> str:
    parts = value.split()
    block: str | None = None
    side: str | None = None
    for part in parts:
        if part in {"over", "under"}:
            if block is not None:
                raise EmphasisError("text emphasis is invalid")
            block = part
            continue
        if part in {"left", "right"}:
            if side is not None:
                raise EmphasisError("text emphasis is invalid")
            side = part
            continue
        raise EmphasisError("text emphasis is invalid")
    if block is None:
        raise EmphasisError("text emphasis is invalid")
    return block
