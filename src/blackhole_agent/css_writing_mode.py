"""Physical edges of a writing mode, and the used size of one block container.

CSS Writing Modes Level 4 §6.4 maps ``writing-mode`` and ``direction`` onto
physical edges. ``sideways-rl`` uses the same flow as ``vertical-rl``.
``sideways-lr`` starts its inline direction at the bottom when direction is
ltr, and its line-over edge is the left. In a vertical writing mode,
``text-orientation: upright`` forces the used direction to ltr. It does not
change a horizontal mode.

§7.3 sizes an orthogonal child in the child's own writing mode. Its available
inline size is the containing block's block size, and its available block
size is the containing block's inline size. Parallel vertical modes, such as
``vertical-rl`` inside ``vertical-lr``, keep the ordinary axes. A percentage
block size uses that available block size. An indefinite percentage block
size becomes automatic, as a percentage height does in CSS 2.1. An indefinite
percentage inline size stays unresolved.

A parallel block container stretches an automatic inline size into a definite
available measure. An orthogonal block container does not. §7.3.2 sizes a
non-wrapping orthogonal box at its max-content inline size, and a wrapping
one with ``min(max-content, max(min-content, constraint))``. The constraint
is the definite available inline size, or the caller's fallback measure when
that size is indefinite. One column is used, so an automatic block size is
the max-content block size rather than the stretch-fit of the other axis.
"""

from __future__ import annotations

import math

_AUTO = "auto"
_ORIENTATIONS = frozenset({"mixed", "upright", "sideways"})
_DIRECTIONS = frozenset({"ltr", "rtl"})
_EDGES = (
    "block_start",
    "block_end",
    "inline_start",
    "inline_end",
    "over",
    "under",
    "line_left",
    "line_right",
)


class _Invalid(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def _flow(
    *,
    block_size_axis: str,
    inline_size_axis: str,
    block_start: str,
    block_end: str,
    over: str,
    under: str,
    line_left: str,
    line_right: str,
    inline_ltr: tuple[str, str],
    inline_rtl: tuple[str, str],
) -> dict[str, object]:
    return {
        "block_size_axis": block_size_axis,
        "inline_size_axis": inline_size_axis,
        "block_start": block_start,
        "block_end": block_end,
        "over": over,
        "under": under,
        "line_left": line_left,
        "line_right": line_right,
        "inline_ltr": inline_ltr,
        "inline_rtl": inline_rtl,
    }


_HORIZONTAL = _flow(
    block_size_axis="height",
    inline_size_axis="width",
    block_start="top",
    block_end="bottom",
    over="top",
    under="bottom",
    line_left="left",
    line_right="right",
    inline_ltr=("left", "right"),
    inline_rtl=("right", "left"),
)
_VERTICAL_RL = _flow(
    block_size_axis="width",
    inline_size_axis="height",
    block_start="right",
    block_end="left",
    over="right",
    under="left",
    line_left="top",
    line_right="bottom",
    inline_ltr=("top", "bottom"),
    inline_rtl=("bottom", "top"),
)
_VERTICAL_LR = _flow(
    block_size_axis="width",
    inline_size_axis="height",
    block_start="left",
    block_end="right",
    over="right",
    under="left",
    line_left="top",
    line_right="bottom",
    inline_ltr=("top", "bottom"),
    inline_rtl=("bottom", "top"),
)
_SIDEWAYS_LR = _flow(
    block_size_axis="width",
    inline_size_axis="height",
    block_start="left",
    block_end="right",
    over="left",
    under="right",
    line_left="bottom",
    line_right="top",
    inline_ltr=("bottom", "top"),
    inline_rtl=("top", "bottom"),
)
_MODES = {
    "horizontal-tb": _HORIZONTAL,
    "vertical-rl": _VERTICAL_RL,
    "sideways-rl": _VERTICAL_RL,
    "vertical-lr": _VERTICAL_LR,
    "sideways-lr": _SIDEWAYS_LR,
}


def resolve_writing_mode(
    writing_mode: object,
    direction: object = "ltr",
    *,
    text_orientation: object = "mixed",
) -> dict[str, object]:
    """Map one writing mode onto physical edges.

    ``direction`` is ``ltr`` or ``rtl``. ``text_orientation`` is ``mixed``,
    ``upright``, or ``sideways``. The returned ``direction`` is the used
    value after the upright rule.
    """

    try:
        mode, specified, used, orientation = _mode_parts(writing_mode, direction, text_orientation)
    except _Invalid as exc:
        return _mode_invalid(exc.reason)
    return _mode_payload(mode, specified, used, orientation)


def resolve_flow_size(child: object, containing: object) -> dict[str, object]:
    """Resolve the used logical size of one block container.

    ``child`` carries ``writing_mode``, optional ``direction``,
    ``text_orientation``, ``inline_size``, ``block_size``, ``wraps``, and the
    content measures ``min_content_inline``, ``max_content_inline``, and
    ``max_content_block``. Sizes are CSS pixels, ``auto``, or a percentage
    string. ``containing`` carries ``writing_mode``, ``inline_size``,
    ``block_size``, and an optional ``constraint`` fallback. A missing
    containing size is indefinite.
    """

    try:
        child_map = _mapping(child, "child")
        parent_map = _mapping(containing, "containing block")
        mode, specified, used, orientation = _mode_parts(
            child_map.get("writing_mode"),
            child_map.get("direction", "ltr"),
            child_map.get("text_orientation", "mixed"),
        )
        parent_mode = _keyword(parent_map.get("writing_mode"), set(_MODES), "containing writing-mode")
        wraps = _flag(child_map.get("wraps", False), "wraps")
        inline_spec = _specified(child_map.get("inline_size", _AUTO), "inline size")
        block_spec = _specified(child_map.get("block_size", _AUTO), "block size")
        parent_inline = _available(parent_map.get("inline_size", None), "containing inline size")
        parent_block = _available(parent_map.get("block_size", None), "containing block size")
        constraint = _optional_length(parent_map, "constraint")
        _supplied_pair(child_map)
    except _Invalid as exc:
        return _flow_invalid(exc.reason)

    flow = _MODES[mode]
    orthogonal = (mode == "horizontal-tb") != (parent_mode == "horizontal-tb")
    if orthogonal:
        available_inline = parent_block
        available_block = parent_inline
    else:
        available_inline = parent_inline
        available_block = parent_block
    try:
        inline_kind, inline_size = _used_inline(
            inline_spec,
            available_inline,
            orthogonal=orthogonal,
            wraps=wraps,
            constraint=constraint,
            child=child_map,
        )
        block_kind, block_size = _used_block(block_spec, available_block, child_map)
    except _Invalid as exc:
        return _flow_invalid(exc.reason)

    width, height = _physical(flow, inline_size, block_size)
    indefinite = inline_size is None or block_size is None
    payload = _mode_payload(mode, specified, used, orientation)
    payload.update(
        {
            "outcome": "indefinite" if indefinite else "resolved",
            "reason": "indefinite size" if indefinite else None,
            "orthogonal": orthogonal,
            "available_inline": _number(available_inline) if available_inline is not None else None,
            "available_block": _number(available_block) if available_block is not None else None,
            "inline_size": _number(inline_size) if inline_size is not None else None,
            "block_size": _number(block_size) if block_size is not None else None,
            "inline_size_kind": inline_kind,
            "block_size_kind": block_kind,
            "width": width,
            "height": height,
        }
    )
    return payload


def _mode_parts(
    writing_mode: object,
    direction: object,
    text_orientation: object,
) -> tuple[str, str, str, str]:
    mode = _keyword(writing_mode, set(_MODES), "writing-mode")
    specified = _keyword(direction, set(_DIRECTIONS), "direction")
    orientation = _keyword(text_orientation, set(_ORIENTATIONS), "text-orientation")
    used = "ltr" if orientation == "upright" and mode != "horizontal-tb" else specified
    return mode, specified, used, orientation


def _mode_payload(mode: str, specified: str, used: str, orientation: str) -> dict[str, object]:
    flow = _MODES[mode]
    inline_start, inline_end = flow["inline_ltr"] if used == "ltr" else flow["inline_rtl"]
    if not isinstance(inline_start, str) or not isinstance(inline_end, str):
        raise _Invalid("writing-mode is invalid")
    return {
        "outcome": "resolved",
        "reason": None,
        "writing_mode": mode,
        "direction": used,
        "specified_direction": specified,
        "text_orientation": orientation,
        "horizontal": mode == "horizontal-tb",
        "block_size_axis": flow["block_size_axis"],
        "inline_size_axis": flow["inline_size_axis"],
        "block_start": flow["block_start"],
        "block_end": flow["block_end"],
        "inline_start": inline_start,
        "inline_end": inline_end,
        "over": flow["over"],
        "under": flow["under"],
        "line_left": flow["line_left"],
        "line_right": flow["line_right"],
    }


def _used_inline(
    spec: tuple[str, float],
    available: float | None,
    *,
    orthogonal: bool,
    wraps: bool,
    constraint: float | None,
    child: dict[str, object],
) -> tuple[str, float | None]:
    kind, number = spec
    if kind == "px":
        return "length", number
    if kind == "pct":
        if available is None:
            return "indefinite", None
        return "percentage", available * number / 100.0
    if not orthogonal:
        if available is not None:
            return "stretch", available
        return "max-content", _measure(child, "max_content_inline", "max-content inline size")
    if not wraps:
        return "max-content", _measure(child, "max_content_inline", "max-content inline size")
    limit = available if available is not None else constraint
    min_content = _measure(child, "min_content_inline", "min-content inline size")
    max_content = _measure(child, "max_content_inline", "max-content inline size")
    if min_content > max_content:
        raise _Invalid("min-content inline size exceeds max-content")
    if limit is None:
        return "max-content", max_content
    return "shrink-to-fit", min(max_content, max(min_content, limit))


def _used_block(
    spec: tuple[str, float],
    available: float | None,
    child: dict[str, object],
) -> tuple[str, float | None]:
    kind, number = spec
    if kind == "px":
        return "length", number
    if kind == "pct" and available is not None:
        return "percentage", available * number / 100.0
    return "max-content", _measure(child, "max_content_block", "max-content block size")


def _physical(
    flow: dict[str, object],
    inline_size: float | None,
    block_size: float | None,
) -> tuple[int | float | None, int | float | None]:
    if flow["block_size_axis"] == "height":
        width, height = inline_size, block_size
    else:
        width, height = block_size, inline_size
    return _maybe(width), _maybe(height)


def _mapping(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise _Invalid(f"{name} must be a mapping")
    return value


def _keyword(value: object, allowed: set[str], name: str) -> str:
    if not isinstance(value, str):
        raise _Invalid(f"{name} is invalid")
    token = value.strip().lower()
    if token not in allowed:
        raise _Invalid(f"{name} is invalid")
    return token


def _flag(value: object, name: str) -> bool:
    if type(value) is not bool:
        raise _Invalid(f"{name} is invalid")
    return value


def _specified(value: object, name: str) -> tuple[str, float]:
    if value is None:
        raise _Invalid(f"{name} is invalid")
    if isinstance(value, str) and value.strip().lower() == _AUTO:
        return (_AUTO, 0.0)
    kind, number = _length_token(value, name)
    return kind, number


def _available(value: object, name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, str) and value.strip().lower() == _AUTO:
        return None
    kind, number = _length_token(value, name)
    if kind == "pct":
        raise _Invalid(f"{name} must be a length")
    return number


def _optional_length(mapping: dict[str, object], name: str) -> float | None:
    if name not in mapping or mapping[name] is None:
        return None
    kind, number = _length_token(mapping[name], name)
    if kind == "pct":
        raise _Invalid(f"{name} must be a length")
    return number


def _supplied_pair(child: dict[str, object]) -> None:
    if "min_content_inline" not in child or "max_content_inline" not in child:
        return
    if child["min_content_inline"] is None or child["max_content_inline"] is None:
        return
    minimum = _finite(child["min_content_inline"], "min-content inline size")
    maximum = _finite(child["max_content_inline"], "max-content inline size")
    if minimum > maximum:
        raise _Invalid("min-content inline size exceeds max-content")


def _measure(child: dict[str, object], key: str, name: str) -> float:
    if key not in child or child[key] is None:
        raise _Invalid(f"{name} is missing")
    return _finite(child[key], name)


def _length_token(value: object, name: str) -> tuple[str, float]:
    if isinstance(value, str):
        text = value.strip().lower()
        if text.endswith("%"):
            return "pct", _finite_text(text[:-1], name)
        if text.endswith("px"):
            return "px", _finite_text(text[:-2], name)
        raise _Invalid(f"{name} is invalid")
    return "px", _finite(value, name)


def _finite_text(text: str, name: str) -> float:
    try:
        number = float(text)
    except ValueError as exc:
        raise _Invalid(f"{name} is invalid") from exc
    return _finite(number, name)


def _finite(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _Invalid(f"{name} is invalid")
    number = float(value)
    if not math.isfinite(number) or number < 0.0:
        raise _Invalid(f"{name} is invalid")
    return number


def _maybe(value: float | None) -> int | float | None:
    if value is None:
        return None
    return _number(value)


def _number(value: float) -> int | float:
    nearest = round(value)
    if abs(value - nearest) <= 1e-9:
        return int(nearest)
    return value


def _mode_invalid(reason: str) -> dict[str, object]:
    payload: dict[str, object] = {
        "outcome": "invalid",
        "reason": reason,
        "writing_mode": None,
        "direction": None,
        "specified_direction": None,
        "text_orientation": None,
        "horizontal": None,
        "block_size_axis": None,
        "inline_size_axis": None,
    }
    for edge in _EDGES:
        payload[edge] = None
    return payload


def _flow_invalid(reason: str) -> dict[str, object]:
    payload = _mode_invalid(reason)
    payload.update(
        {
            "orthogonal": None,
            "available_inline": None,
            "available_block": None,
            "inline_size": None,
            "block_size": None,
            "inline_size_kind": None,
            "block_size_kind": None,
            "width": None,
            "height": None,
        }
    )
    return payload
