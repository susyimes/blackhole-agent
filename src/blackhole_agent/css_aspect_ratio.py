"""Preferred aspect ratio for one horizontal in-flow block.

CSS Sizing 4 maps a definite inline size through ``aspect-ratio`` when the
block size is automatic. A plain ratio uses the box selected by
``box-sizing``. ``auto`` together with a ratio always uses the content box.
A zero component is degenerate and behaves as ``auto``. This does not size
flex, grid, table, or replaced boxes.
"""

from __future__ import annotations

import re

_NUMBER = re.compile(r"\d+(?:\.\d+)?|\.\d+")


class _Invalid(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def parse_aspect_ratio(value: str) -> tuple[float, float, bool] | None:
    """Return ``(width, height, content_box)`` or None for auto.

    ``content_box`` is true when ``auto`` is combined with a ratio. A
    degenerate ratio returns None. Malformed text raises ``ValueError``.
    """

    tokens = value.replace("/", " / ").split()
    if not tokens:
        raise ValueError("aspect-ratio is invalid")
    content_box = "auto" in tokens
    parts = [token for token in tokens if token != "auto"]
    if content_box and not parts:
        return None
    if len(parts) == 1:
        width, height = _component(parts[0]), 1.0
    elif len(parts) == 3 and parts[1] == "/":
        width, height = _component(parts[0]), _component(parts[2])
    else:
        raise ValueError("aspect-ratio is invalid")
    if width == 0.0 or height == 0.0:
        return None
    return width, height, content_box


def transferred_content_height(
    content_width: int,
    horizontal_chrome: int,
    vertical_chrome: int,
    ratio: tuple[float, float],
    *,
    content_box: bool,
    box_sizing: str,
) -> int:
    """Content-box block size transferred from the used inline size."""

    width_part, height_part = ratio
    if width_part <= 0.0 or height_part <= 0.0:
        raise _Invalid("aspect-ratio is invalid")
    if content_box or box_sizing != "border-box":
        raw = content_width * height_part / width_part
    else:
        raw = (content_width + horizontal_chrome) * height_part / width_part - vertical_chrome
    if raw < 0.0:
        raw = 0.0
    return int(round(raw))


def block_ratio_limits(
    *,
    content_width: int,
    horizontal_chrome: int,
    vertical_chrome: int,
    ratio: tuple[float, float],
    content_box: bool,
    box_sizing: str,
    min_is_auto: bool,
    clips: bool,
    min_content_height: int,
    max_content_height: int | None,
) -> tuple[int | None, int]:
    """Return a locked content height, or a floor when height stays automatic.

    A scrollport or an explicit minimum locks the transferred size so extra
    content overflows. Otherwise the transferred size is a content floor,
    capped by a definite maximum, and a taller stack may still grow.
    """

    transferred = transferred_content_height(
        content_width,
        horizontal_chrome,
        vertical_chrome,
        ratio,
        content_box=content_box,
        box_sizing=box_sizing,
    )
    if clips or not min_is_auto:
        return transferred, min_content_height
    floor = transferred
    if max_content_height is not None and floor > max_content_height:
        floor = max_content_height
    if floor < min_content_height:
        floor = min_content_height
    return None, floor


def _component(token: str) -> float:
    if _NUMBER.fullmatch(token) is None:
        raise ValueError("aspect-ratio is invalid")
    return float(token)
