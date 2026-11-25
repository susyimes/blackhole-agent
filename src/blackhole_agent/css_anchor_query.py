"""Resolve CSS anchor-size() and position-visibility.

CSS Anchor Positioning Level 1. ``anchor-size()`` is the distance between
the anchor box's opposing edges. ``width`` and ``height`` are physical.
``block`` and ``inline`` use the containing block's writing mode.
``self-block`` and ``self-inline`` use the positioned box's own writing
mode, not the anchor's. An omitted keyword follows the axis of the property
the function is used in, so ``top`` stays ``height`` even when the block
axis is horizontal. The function resolves only for an absolutely positioned
box with a definite anchor size. Otherwise a length fallback is used, a
percentage fallback resolves against a definite basis, and a missing
fallback makes the declaration invalid. ``parse_anchor_size_call`` splits one
written function into that anchor name, size keyword, and fallback text.

``position-visibility`` computes ``force-hidden`` when one of its conditions
fails. ``anchor-valid`` hides a referenced default anchor that does not
resolve. ``anchor-visible`` hides a resolved anchor that is invisible or
fully clipped by an intervening box, a descendant of the containing block.
A clip outside that chain does not count, and a partial overlap stays
visible. A non-zero area anchor needs a non-zero intersection; a zero-area
anchor is clipped only when it misses the clip. ``no-overflow`` hides a
margin box that is not contained in the inset-modified containing block
after position fallback. ``always`` ignores those conditions. The legacy
names ``anchors-valid`` and ``anchors-visible`` are the same conditions.
Rectangles are supplied by the caller. This does not scroll-shift, walk a
document, or evaluate ``clip-path``.
"""

from __future__ import annotations

import math

from blackhole_agent.css_writing_mode import resolve_writing_mode

_EPS = 1e-9
_SIZE_KEYWORDS = frozenset({"width", "height", "block", "inline", "self-block", "self-inline"})
_PROPERTY_AXIS = {
    "width": "width",
    "min-width": "width",
    "max-width": "width",
    "left": "width",
    "right": "width",
    "margin-left": "width",
    "margin-right": "width",
    "height": "height",
    "min-height": "height",
    "max-height": "height",
    "top": "height",
    "bottom": "height",
    "margin-top": "height",
    "margin-bottom": "height",
    "block-size": "block",
    "min-block-size": "block",
    "max-block-size": "block",
    "inline-size": "inline",
    "min-inline-size": "inline",
    "max-inline-size": "inline",
}
_VISIBILITY_FLAGS = ("anchor-valid", "anchor-visible", "no-overflow")
_VISIBILITY_ALIAS = {"anchors-valid": "anchor-valid", "anchors-visible": "anchor-visible"}


class _Invalid(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def _anchor_size_payload(
    outcome: str,
    reason: str | None,
    anchor: str | None,
    keyword: str | None,
    fallback: str | None,
) -> dict[str, object]:
    return {
        "outcome": outcome,
        "reason": reason,
        "anchor": anchor,
        "keyword": keyword,
        "fallback": fallback,
    }


def _dashed_anchor(token: str) -> bool:
    if len(token) < 3 or not token.startswith("--"):
        return False
    body = token[2:]
    first = body[0]
    if not first.isascii() or not (first.isalpha() or first == "_"):
        return False
    return all(char.isascii() and (char.isalnum() or char in "_-") for char in body)


def _split_anchor_args(text: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    for char in text:
        if char == "(":
            depth += 1
        elif char == ")":
            if depth == 0:
                raise _Invalid("anchor-size is invalid")
            depth -= 1
        if char == "," and depth == 0:
            parts.append("".join(buf).strip())
            buf = []
            continue
        buf.append(char)
    if depth != 0:
        raise _Invalid("anchor-size is invalid")
    parts.append("".join(buf).strip())
    return parts


def parse_anchor_size_call(value: object) -> dict[str, object]:
    """Parse one ``anchor-size()`` value into an anchor, a keyword, and a fallback.

    The function name and size keyword are case-insensitive. A dashed anchor
    name keeps the case written in the value. The fallback is the text after
    the top-level comma, still unresolved. A value that is not this function
    is ``absent``.
    """

    if not isinstance(value, str):
        return _anchor_size_payload("absent", None, None, None, None)
    text = " ".join(value.strip().split())
    lowered = text.lower()
    prefix = "anchor-size("
    if not lowered.startswith(prefix) or not text.endswith(")"):
        return _anchor_size_payload("absent", None, None, None, None)
    try:
        inner = text[len(prefix) : -1].strip()
        if not inner:
            return _anchor_size_payload("parsed", None, None, None, None)
        parts = _split_anchor_args(inner)
        if len(parts) > 2 or not parts[0] or (len(parts) == 2 and not parts[1]):
            raise _Invalid("anchor-size is invalid")
        anchor = None
        keyword = None
        for token in parts[0].split(" "):
            folded = token.lower()
            if folded in _SIZE_KEYWORDS:
                if keyword is not None:
                    raise _Invalid("anchor-size is invalid")
                keyword = folded
                continue
            if _dashed_anchor(token):
                if anchor is not None:
                    raise _Invalid("anchor-size is invalid")
                anchor = token
                continue
            raise _Invalid("anchor-size is invalid")
        fallback = parts[1] if len(parts) == 2 else None
        return _anchor_size_payload("parsed", None, anchor, keyword, fallback)
    except _Invalid as exc:
        return _anchor_size_payload("invalid", exc.reason, None, None, None)


def resolve_anchor_size(
    anchor: object = None,
    size: object = None,
    *,
    used_in: object = None,
    fallback: object = None,
    containing_writing_mode: object = "horizontal-tb",
    containing_direction: object = "ltr",
    box_writing_mode: object = "horizontal-tb",
    box_direction: object = "ltr",
    percentage_basis: object = None,
    absolutely_positioned: object = True,
) -> dict[str, object]:
    """Return the used length of one anchor-size() query.

    ``anchor`` is ``None`` or a mapping with ``width`` and ``height``. A
    ``None`` axis is indefinite. ``size`` is a keyword; when it is omitted,
    ``used_in`` supplies the property whose axis is the default. ``fallback``
    is a number, a ``px`` length, or a percentage. ``percentage_basis`` is
    the definite containing-block size for that percentage.
    """

    def fail(reason: str) -> dict[str, object]:
        return {"outcome": "invalid", "reason": reason, "length": None, "axis": None, "keyword": None}

    def succeed(outcome: str, length: float, axis: str, keyword: str) -> dict[str, object]:
        return {
            "outcome": outcome,
            "reason": None,
            "length": _number(length),
            "axis": axis,
            "keyword": keyword,
        }

    def plain(text: str, name: str) -> float:
        token = text.strip()
        if not token or token in {"+", "-"}:
            raise _Invalid(f"{name} is invalid")
        try:
            number = float(token)
        except ValueError as exc:
            raise _Invalid(f"{name} is invalid") from exc
        if not math.isfinite(number):
            raise _Invalid(f"{name} is invalid")
        return number

    def fallback_value() -> tuple[str, float]:
        if isinstance(fallback, bool):
            raise _Invalid("anchor-size fallback is invalid")
        if isinstance(fallback, (int, float)):
            number = float(fallback)
            if not math.isfinite(number):
                raise _Invalid("anchor-size fallback is invalid")
            return "length", number
        if not isinstance(fallback, str):
            raise _Invalid("anchor-size fallback is invalid")
        text = fallback.strip()
        if text.endswith("%"):
            return "percentage", plain(text[:-1], "anchor-size fallback")
        if text.endswith("px"):
            return "length", plain(text[:-2], "anchor-size fallback")
        return "length", plain(text, "anchor-size fallback")

    def size_box(value: object) -> dict[str, float | None]:
        mapping = _mapping(value, "anchor")
        if "width" not in mapping or "height" not in mapping:
            raise _Invalid("anchor size is missing")
        return {
            "width": _optional_length(mapping["width"], "anchor width"),
            "height": _optional_length(mapping["height"], "anchor height"),
        }

    def flow(mode: object, direction: object, name: str) -> dict[str, object]:
        resolved = resolve_writing_mode(mode, direction)
        if resolved.get("outcome") != "resolved":
            raise _Invalid(str(resolved.get("reason") or f"{name} is invalid"))
        return resolved

    def physical(keyword: str, containing: dict[str, object], box: dict[str, object]) -> str:
        if keyword in {"width", "height"}:
            return keyword
        source = box if keyword.startswith("self-") else containing
        field = "block_size_axis" if keyword.endswith("block") else "inline_size_axis"
        axis = source.get(field)
        if axis not in {"width", "height"}:
            raise _Invalid("writing-mode is invalid")
        return str(axis)

    try:
        if size is None:
            if not isinstance(used_in, str) or used_in not in _PROPERTY_AXIS:
                raise _Invalid("anchor-size property is invalid")
            keyword = _PROPERTY_AXIS[used_in]
        elif not isinstance(size, str) or size not in _SIZE_KEYWORDS:
            raise _Invalid("anchor-size is invalid")
        else:
            keyword = size
        containing = flow(containing_writing_mode, containing_direction, "containing writing-mode")
        box = flow(box_writing_mode, box_direction, "writing-mode")
        axis = physical(keyword, containing, box)
        positioned = _flag(absolutely_positioned, "absolutely positioned")
        measured = None if anchor is None else size_box(anchor)
        if positioned and measured is not None and measured[axis] is not None:
            return succeed("resolved", float(measured[axis]), axis, keyword)
        if fallback is None:
            return fail("anchor-size fallback is missing")
        kind, number = fallback_value()
        if kind == "length":
            return succeed("fallback", number, axis, keyword)
        if percentage_basis is None:
            return fail("percentage basis is indefinite")
        basis = _length(percentage_basis, "percentage basis", allow_negative=False)
        return succeed("fallback", basis * number / 100.0, axis, keyword)
    except _Invalid as exc:
        return fail(exc.reason)


def resolve_position_visibility(
    value: object = None,
    *,
    references_anchor: object = False,
    anchor_resolved: object = False,
    anchor_invisible: object = False,
    anchor_box: object = None,
    clips: object = (),
    margin_box: object = None,
    containing_block: object = None,
) -> dict[str, object]:
    """Return whether position-visibility leaves the box shown.

    ``value`` is ``always``, a combination of ``anchor-valid``,
    ``anchor-visible``, and ``no-overflow``, or one of the legacy aliases.
    Omitted, it is the initial value ``anchor-visible``. ``clips`` are
    overflow clip rectangles. ``intervening`` defaults to true; a false clip
    is outside the chain between the containing block and the anchor.
    ``margin_box`` and ``containing_block`` are the used rectangles after
    position fallback.
    """

    def fail(reason: str) -> dict[str, object]:
        return {
            "outcome": "invalid",
            "reason": reason,
            "shown": None,
            "visibility": None,
            "hidden_by": [],
            "conditions": [],
        }

    def tokens(raw: object) -> list[str]:
        if raw is None:
            return ["anchor-visible"]
        parts: list[str] = []
        if isinstance(raw, str):
            parts = raw.split()
        elif isinstance(raw, (list, tuple)):
            for item in raw:
                if not isinstance(item, str):
                    raise _Invalid("position-visibility is invalid")
                parts.extend(item.split())
        else:
            raise _Invalid("position-visibility is invalid")
        if not parts:
            raise _Invalid("position-visibility is invalid")
        normalized = [_VISIBILITY_ALIAS.get(part, part) for part in parts]
        if "always" in normalized:
            if normalized != ["always"]:
                raise _Invalid("position-visibility is invalid")
            return ["always"]
        seen: set[str] = set()
        for token in normalized:
            if token not in _VISIBILITY_FLAGS or token in seen:
                raise _Invalid("position-visibility is invalid")
            seen.add(token)
        return normalized

    def right(rect: dict[str, float]) -> float:
        return rect["x"] + rect["width"]

    def bottom(rect: dict[str, float]) -> float:
        return rect["y"] + rect["height"]

    def intersection_area(left: dict[str, float], other: dict[str, float]) -> float:
        width = min(right(left), right(other)) - max(left["x"], other["x"])
        height = min(bottom(left), bottom(other)) - max(left["y"], other["y"])
        if width <= _EPS or height <= _EPS:
            return 0.0
        return width * height

    def touches(left: dict[str, float], other: dict[str, float]) -> bool:
        return (
            right(left) >= other["x"] - _EPS
            and left["x"] <= right(other) + _EPS
            and bottom(left) >= other["y"] - _EPS
            and left["y"] <= bottom(other) + _EPS
        )

    def fully_clipped(ink: dict[str, float], boxes: list[dict[str, float]]) -> bool:
        intervening = [box for box in boxes if box["intervening"] > 0]
        if not intervening:
            return False
        area = ink["width"] * ink["height"]
        for box in intervening:
            if area > _EPS:
                if intersection_area(ink, box) <= _EPS:
                    return True
            elif not touches(ink, box):
                return True
        return False

    def contained(outer: dict[str, float], inner: dict[str, float]) -> bool:
        return (
            inner["x"] >= outer["x"] - _EPS
            and inner["y"] >= outer["y"] - _EPS
            and right(inner) <= right(outer) + _EPS
            and bottom(inner) <= bottom(outer) + _EPS
        )

    try:
        conditions = tokens(value)
        references = _flag(references_anchor, "references anchor")
        resolved = _flag(anchor_resolved, "anchor resolved")
        invisible = _flag(anchor_invisible, "anchor invisible")
        parsed_clips = _clips(clips)
        ink = None if anchor_box is None else _rect(anchor_box, "anchor box")
        active = set(conditions)
        hidden: list[str] = []
        if "anchor-valid" in active and references and not resolved:
            hidden.append("anchor-valid")
        if "anchor-visible" in active and references and resolved and (
            invisible or (ink is not None and fully_clipped(ink, parsed_clips))
        ):
            hidden.append("anchor-visible")
        if "anchor-visible" in active and references and resolved and not invisible:
            if any(box["intervening"] > 0 for box in parsed_clips) and ink is None:
                raise _Invalid("anchor box is missing")
        if "no-overflow" in active:
            if margin_box is None or containing_block is None:
                raise _Invalid("inset-modified containing block is missing")
            margin = _rect(margin_box, "margin box")
            block = _rect(containing_block, "containing block")
            if not contained(block, margin):
                hidden.append("no-overflow")
        else:
            if margin_box is not None:
                _rect(margin_box, "margin box")
            if containing_block is not None:
                _rect(containing_block, "containing block")
        shown = not hidden
        return {
            "outcome": "resolved",
            "reason": None,
            "shown": shown,
            "visibility": "visible" if shown else "force-hidden",
            "hidden_by": hidden,
            "conditions": conditions,
        }
    except _Invalid as exc:
        return fail(exc.reason)


def _optional_length(value: object, name: str) -> float | None:
    if value is None:
        return None
    return _length(value, name, allow_negative=False)


def _length(value: object, name: str, *, allow_negative: bool) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _Invalid(f"{name} is invalid")
    number = float(value)
    if not math.isfinite(number) or (not allow_negative and number < 0):
        raise _Invalid(f"{name} is invalid")
    return number


def _flag(value: object, name: str) -> bool:
    if not isinstance(value, bool):
        raise _Invalid(f"{name} is invalid")
    return value


def _mapping(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise _Invalid(f"{name} is invalid")
    return value


def _rect(value: object, name: str) -> dict[str, float]:
    mapping = _mapping(value, name)
    for field in ("x", "y", "width", "height"):
        if field not in mapping:
            raise _Invalid(f"{name} {field} is missing")
    width = _length(mapping["width"], f"{name} width", allow_negative=False)
    height = _length(mapping["height"], f"{name} height", allow_negative=False)
    return {
        "x": _length(mapping["x"], f"{name} x", allow_negative=True),
        "y": _length(mapping["y"], f"{name} y", allow_negative=True),
        "width": width,
        "height": height,
    }


def _clips(value: object) -> list[dict[str, float]]:
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise _Invalid("clips are invalid")
    parsed: list[dict[str, float]] = []
    for item in value:
        rect = _rect(item, "clip")
        mapping = _mapping(item, "clip")
        intervening = True if "intervening" not in mapping else _flag(mapping["intervening"], "clip intervening")
        rect["intervening"] = 1.0 if intervening else 0.0
        parsed.append(rect)
    return parsed


def _number(value: float) -> int | float:
    nearest = round(value)
    if abs(value - nearest) <= _EPS:
        return int(nearest)
    return value
