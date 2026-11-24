"""Reserve a classic scrollbar gutter inside a scroll container.

CSS Overflow Level 3. The gutter lies between the inner border edge and the
outer padding edge. This engine's classic scrollbar is 15px on the inline-end
side. Overlay scrollbars do not consume space. ``stable`` reserves the gutter
for ``hidden``, ``scroll``, and ``auto`` whether or not the box overflows.
``auto`` reserves it for ``scroll``, and for ``auto`` only when the box
overflows. ``both-edges`` repeats a gutter that is already present on the
inline-start side. ``visible`` and ``clip`` are not scroll containers.

Only a horizontal left-to-right box is reported here. Other writing modes
receive an empty gutter so an existing vertical layout is left in place.
"""

from __future__ import annotations

CLASSIC_SCROLLBAR_PX = 15
_SCROLL_CONTAINERS = frozenset({"hidden", "scroll", "auto"})
_DISPLAYS = frozenset(
    {"block", "flow-root", "flex", "inline-flex", "grid", "inline-block", "table"}
)


class ScrollbarGutterError(ValueError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def parse_scrollbar_gutter(value: object) -> str:
    """Return ``auto``, ``stable``, or ``stable both-edges``."""

    if value is None:
        return "auto"
    if not isinstance(value, str):
        raise ScrollbarGutterError("scrollbar-gutter is invalid")
    text = " ".join(value.strip().lower().split())
    if text in {"", "initial", "unset", "revert"}:
        return "auto"
    if text == "inherit":
        raise ScrollbarGutterError("scrollbar-gutter inherit is unsupported")
    if text == "auto":
        return "auto"
    parts = text.split(" ")
    if parts == ["stable"]:
        return "stable"
    if len(parts) == 2 and set(parts) == {"stable", "both-edges"}:
        return "stable both-edges"
    raise ScrollbarGutterError("scrollbar-gutter is invalid")


def reserve_scrollbar_gutter(
    *,
    overflow: str,
    gutter: str,
    display: str,
    overflowing: bool | None,
    scrollbars: str,
    writing_mode: str,
    direction: str,
) -> dict[str, object]:
    """Return the inline-start and inline-end gutters in CSS pixels.

    ``overflowing`` is ``None`` before the first layout. ``auto`` on an
    ``overflow: auto`` box then reports ``pending`` and a zero gutter, so the
    caller can lay out once and reserve only if that layout overflows.
    """

    if scrollbars not in {"classic", "overlay"}:
        raise ScrollbarGutterError("scrollbar style is invalid")
    if gutter not in {"auto", "stable", "stable both-edges"}:
        raise ScrollbarGutterError("scrollbar-gutter is invalid")
    if (
        scrollbars == "overlay"
        or writing_mode != "horizontal-tb"
        or direction != "ltr"
        or display not in _DISPLAYS
        or overflow not in _SCROLL_CONTAINERS
    ):
        return _reserved(0, 0, pending=False)
    stable = gutter != "auto"
    wanted = _wanted(overflow, stable, overflowing)
    if wanted is None:
        return _reserved(0, 0, pending=True)
    if not wanted:
        return _reserved(0, 0, pending=False)
    end = CLASSIC_SCROLLBAR_PX
    start = CLASSIC_SCROLLBAR_PX if gutter == "stable both-edges" else 0
    return _reserved(start, end, pending=False)


def _wanted(overflow: str, stable: bool, overflowing: bool | None) -> bool | None:
    if overflow == "scroll":
        return True
    if overflow == "hidden":
        return stable
    if stable:
        return True
    if overflowing is None:
        return None
    return bool(overflowing)


def _reserved(start: int, end: int, *, pending: bool) -> dict[str, object]:
    return {"outcome": "reserved", "start": start, "end": end, "pending": pending}
