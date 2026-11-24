"""Paint non-inherited CSS text-decoration lines on one inline line.

``text-decoration`` and ``text-decoration-line`` are not inherited. A
descendant ``none`` adds no line of its own and does not remove an ancestor
line. An atomic inline-level box is a gap: the ancestor line stops before
that box and starts again after it.

This engine has no font file. The line baseline is the one the inline
layout already resolved. Underline sits one tenth of the decorating em
below that baseline, at least one pixel. Line-through sits one third of
that em above the baseline, at least one pixel. Overline sits at the top
of that em. Ink may fall outside the line box; the line box does not grow.
"""

from __future__ import annotations

_KINDS = ("overline", "underline", "line-through")
_KIND_SET = frozenset(_KINDS)
_KIND_ORDER = {kind: index for index, kind in enumerate(_KINDS)}


class DecorationError(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def parse_text_decoration(value: str | None) -> tuple[str, ...]:
    """Return the used line kinds. ``none`` and the initial value are empty.

    Color, style, and thickness are not accepted. Repeating a kind is
    invalid. The result is always overline, then underline, then line-through.
    """

    if value is None:
        return ()
    token = " ".join(value.strip().lower().split())
    if token in {"", "initial", "unset", "revert", "none"}:
        return ()
    if token == "inherit":
        raise DecorationError("text-decoration inherit is unsupported")
    parts = token.split(" ")
    if any(part not in _KIND_SET for part in parts) or len(set(parts)) != len(parts):
        raise DecorationError("text-decoration is invalid")
    return tuple(kind for kind in _KINDS if kind in parts)


def decoration_dy(kind: str, font_size: int) -> int:
    """Pixel offset from the baseline, positive downward."""

    if isinstance(font_size, bool) or not isinstance(font_size, int) or font_size < 1:
        raise DecorationError("text decoration is invalid")
    if kind == "underline":
        return max(1, font_size // 10)
    if kind == "line-through":
        return -max(1, font_size // 3)
    if kind == "overline":
        return -font_size
    raise DecorationError("text decoration is invalid")


def paint_decoration_events(events: list[tuple], baseline: int) -> list[dict[str, object]]:
    """Merge abutting text events that carry the same decoration.

    Each event is ``("text", width, marks)`` or ``("gap", width)``. ``marks``
    is a tuple of ``(kind, font_size, owner)``. A gap closes every open line.
    Coordinates are local to the line's content start and its top.
    """

    if isinstance(baseline, bool) or not isinstance(baseline, int):
        raise DecorationError("text decoration is invalid")
    open_x: dict[tuple[str, int, str], int] = {}
    closed: list[tuple[tuple[str, int, str], int, int]] = []
    cursor = 0

    def sync(active: tuple[tuple[str, int, str], ...]) -> None:
        wanted = set(active)
        for mark in list(open_x):
            if mark not in wanted:
                start = open_x.pop(mark)
                if cursor > start:
                    closed.append((mark, start, cursor - start))
        for mark in active:
            if mark not in open_x:
                open_x[mark] = cursor

    for event in events:
        if not event or event[0] not in {"text", "gap"}:
            raise DecorationError("text decoration is invalid")
        width = event[1]
        if isinstance(width, bool) or not isinstance(width, int) or width < 0:
            raise DecorationError("text decoration is invalid")
        if event[0] == "gap":
            sync(())
            cursor += width
            continue
        marks = event[2]
        if not isinstance(marks, tuple):
            raise DecorationError("text decoration is invalid")
        sync(marks)
        cursor += width
    sync(())
    closed.sort(key=lambda item: (item[1], _KIND_ORDER.get(item[0][0], 9), item[0][2], item[0][0]))
    painted: list[dict[str, object]] = []
    for mark, start, width in closed:
        if width <= 0:
            continue
        kind, font_size, owner = mark
        painted.append(
            {
                "kind": kind,
                "x": start,
                "y": baseline + decoration_dy(kind, font_size),
                "width": width,
                "owner": owner,
                "font_size": font_size,
            }
        )
    return painted
