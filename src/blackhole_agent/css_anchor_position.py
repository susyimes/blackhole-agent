"""Place one absolutely positioned box against a CSS anchor.

CSS Anchor Positioning Level 1. ``position-area`` selects tracks of the
3×3 grid whose lines are the containing block edges and the default anchor
edges, in the containing block's writing mode. The box then packs toward
the anchor, or centers on it when the track is the anchor itself or the
whole axis. A margin box that does not fit inside that area tries
``flip-block``, ``flip-inline``, ``flip-x``, and ``flip-y`` in the requested
order. ``most-width``, ``most-height``, ``most-block-size``, and
``most-inline-size`` stably sort those areas, largest first. If none fit,
the base position is kept.

``anchor()`` resolves to the inset that lines the inset-modified edge up
with the requested anchor edge. An unresolvable reference uses its fallback
length. A physical side on the wrong axis is unresolvable. This placer
does not scroll-shift. ``resolve_anchor_size`` and
``resolve_position_visibility`` answer ``anchor-size()`` and
``position-visibility``.
"""

from __future__ import annotations

from blackhole_agent.css_writing_mode import resolve_writing_mode

_EPS = 1e-9
_ORDERS = frozenset({"normal", "most-width", "most-height", "most-block-size", "most-inline-size"})
_TACTICS = frozenset({"flip-block", "flip-inline", "flip-x", "flip-y"})
_SWAP = {
    "start": "end",
    "end": "start",
    "center": "center",
    "span-start": "span-end",
    "span-end": "span-start",
    "span-all": "span-all",
}
_OPPOSITE = {"top": "bottom", "bottom": "top", "left": "right", "right": "left"}
_PHYSICAL = frozenset(_OPPOSITE)
_AUTO = "auto"


class _Invalid(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def place_anchored(
    containing: object,
    anchor: object = None,
    box: object = None,
    *,
    fallbacks: object = (),
    order: object = "normal",
) -> dict[str, object]:
    """Return the border box of one anchored absolutely positioned box.

    ``containing`` and ``anchor`` are border or padding rectangles with
    ``x``, ``y``, ``width``, ``height``, and an optional writing mode.
    ``box`` carries ``width``, ``height``, margins, ``position_area``, and
    ``insets``. An inset is ``auto``, a length, or ``anchor()`` as a mapping
    with ``side`` and an optional ``fallback`` length. ``fallbacks`` are
    tactic strings or mappings that replace ``position_area``. ``order`` is
    ``normal`` or a ``most-*`` size.
    """

    try:
        parsed_order = _keyword(order, _ORDERS, "position-try-order")
        container = _rect(containing, "containing block", sized=True)
        target = None if anchor is None else _rect(anchor, "anchor", sized=True)
        item = _box(box)
        options = _options(item, fallbacks, container, target)
    except _Invalid as exc:
        return _invalid(exc.reason)

    ranked = _rank(options, parsed_order, container)
    chosen = None
    for option in ranked:
        if option["fits"]:
            chosen = option
            break
    if chosen is None:
        chosen = options[0]
    return _payload(chosen)


def _options(item: dict[str, object], fallbacks: object, container: dict[str, object], anchor: dict[str, object] | None) -> list[dict[str, object]]:
    if isinstance(fallbacks, (str, bytes)) or not isinstance(fallbacks, (list, tuple)):
        raise _Invalid("position-try-fallbacks is invalid")
    built = [_option(item, None, container, anchor, "base")]
    for index, fallback in enumerate(fallbacks):
        built.append(_option(item, fallback, container, anchor, _fallback_label(fallback, index)))
    return built


def _option(
    item: dict[str, object],
    fallback: object,
    container: dict[str, object],
    anchor: dict[str, object] | None,
    label: str,
) -> dict[str, object]:
    area_value = item["position_area"]
    insets = item["insets"]
    if isinstance(fallback, str):
        tactics = fallback.split()
        if not tactics or any(part not in _TACTICS for part in tactics):
            raise _Invalid("position-try-fallbacks is invalid")
        if isinstance(area_value, str):
            area_value = _flip_area(area_value, tactics, container, item)
        else:
            insets = _flip_insets(insets, tactics, container)
    elif isinstance(fallback, dict):
        if set(fallback) != {"position_area"}:
            raise _Invalid("position-try-fallbacks is invalid")
        area_value = fallback["position_area"]
    elif fallback is not None:
        raise _Invalid("position-try-fallbacks is invalid")
    placed = _place(item, area_value, insets, container, anchor)
    placed["option"] = label
    return placed


def _place(
    item: dict[str, object],
    area_value: object,
    insets: dict[str, object],
    container: dict[str, object],
    anchor: dict[str, object] | None,
) -> dict[str, object]:
    if isinstance(area_value, tuple):
        if anchor is None:
            raise _Invalid("default anchor is missing")
        return _place_area(item, area_value, container, anchor)
    if isinstance(area_value, str):
        if anchor is None:
            raise _Invalid("default anchor is missing")
        tracks = _tracks(area_value, container["flow"], item["flow"])
        return _place_area(item, tracks, container, anchor)
    if area_value is not None:
        raise _Invalid("position-area is invalid")
    return _place_insets(item, insets, container, anchor)


def _place_area(
    item: dict[str, object],
    tracks: tuple[str, str],
    container: dict[str, object],
    anchor: dict[str, object],
) -> dict[str, object]:
    flow = container["flow"]
    block = _interval(container, anchor, flow, "block", tracks[0])
    inline = _interval(container, anchor, flow, "inline", tracks[1])
    horizontal, vertical = _physical_intervals(flow, block, inline)
    area = _bounds(horizontal, vertical)
    margin_w = float(item["width"]) + float(item["margin_left"]) + float(item["margin_right"])
    margin_h = float(item["height"]) + float(item["margin_top"]) + float(item["margin_bottom"])
    x = _align_origin(
        horizontal,
        _axis_edges(anchor, flow, "inline" if _horizontal(flow, "inline") else "block"),
        margin_w,
        _align_for(tracks[1] if _horizontal(flow, "inline") else tracks[0]),
        _start_is_min(flow, "inline" if _horizontal(flow, "inline") else "block"),
    )
    y = _align_origin(
        vertical,
        _axis_edges(anchor, flow, "block" if _horizontal(flow, "inline") else "inline"),
        margin_h,
        _align_for(tracks[0] if _horizontal(flow, "inline") else tracks[1]),
        _start_is_min(flow, "block" if _horizontal(flow, "inline") else "inline"),
    )
    return _boxed(item, area, x + float(item["margin_left"]), y + float(item["margin_top"]), None, None, None, None)


def _place_insets(
    item: dict[str, object],
    insets: dict[str, object],
    container: dict[str, object],
    anchor: dict[str, object] | None,
) -> dict[str, object]:
    resolved = {side: _inset(insets[side], side, container, item, anchor) for side in ("top", "right", "bottom", "left")}
    left, right = _over_constrain(resolved["left"], resolved["right"], str(item["flow"]["direction"]))
    top, bottom = resolved["top"], None if resolved["top"] is not None else resolved["bottom"]
    width = float(item["width"])
    height = float(item["height"])
    if left is not None:
        x = float(container["x"]) + left + float(item["margin_left"])
    elif right is not None:
        x = float(container["x"]) + float(container["width"]) - right - float(item["margin_right"]) - width
    else:
        x = float(container["x"]) + float(item["margin_left"])
    if top is not None:
        y = float(container["y"]) + top + float(item["margin_top"])
    elif bottom is not None:
        y = float(container["y"]) + float(container["height"]) - bottom - float(item["margin_bottom"]) - height
    else:
        y = float(container["y"]) + float(item["margin_top"])
    area = _inset_area(container, resolved)
    return _boxed(item, area, x, y, resolved["top"], resolved["right"], resolved["bottom"], resolved["left"])


def _boxed(
    item: dict[str, object],
    area: dict[str, float],
    x: float,
    y: float,
    top: float | None,
    right: float | None,
    bottom: float | None,
    left: float | None,
) -> dict[str, object]:
    margin = {
        "x": x - float(item["margin_left"]),
        "y": y - float(item["margin_top"]),
        "width": float(item["width"]) + float(item["margin_left"]) + float(item["margin_right"]),
        "height": float(item["height"]) + float(item["margin_top"]) + float(item["margin_bottom"]),
    }
    fits = area["width"] >= -_EPS and area["height"] >= -_EPS and _contains(area, margin)
    return {
        "x": x,
        "y": y,
        "width": float(item["width"]),
        "height": float(item["height"]),
        "fits": fits,
        "area": area,
        "top": top,
        "right": right,
        "bottom": bottom,
        "left": left,
    }


def _rank(options: list[dict[str, object]], order: str, container: dict[str, object]) -> list[dict[str, object]]:
    if order == "normal":
        return list(options)
    kind = order.removeprefix("most-")
    return sorted(options, key=lambda option: -_measure(option["area"], kind, container["flow"]))


def _measure(area: dict[str, float], kind: str, flow: dict[str, object]) -> float:
    if kind == "width":
        return area["width"]
    if kind == "height":
        return area["height"]
    axis = "block" if kind == "block-size" else "inline"
    return area["width"] if _horizontal(flow, axis) else area["height"]


def _flip_area(
    value: str,
    tactics: list[str],
    container: dict[str, object],
    item: dict[str, object],
) -> tuple[str, str]:
    block, inline = _tracks(value, container["flow"], item["flow"])
    flow = container["flow"]
    horizontal = "inline" if _horizontal(flow, "inline") else "block"
    vertical = "block" if horizontal == "inline" else "inline"
    for tactic in tactics:
        if tactic == "flip-block":
            axis = "block"
        elif tactic == "flip-inline":
            axis = "inline"
        elif tactic == "flip-x":
            axis = horizontal
        else:
            axis = vertical
        if axis == "block":
            block = _SWAP[block]
        else:
            inline = _SWAP[inline]
    return block, inline


def _flip_insets(insets: dict[str, object], tactics: list[str], container: dict[str, object]) -> dict[str, object]:
    current = dict(insets)
    flow = container["flow"]
    for tactic in tactics:
        if tactic == "flip-x":
            pair = ("left", "right")
        elif tactic == "flip-y":
            pair = ("top", "bottom")
        elif tactic == "flip-block":
            pair = _logical_pair(flow, "block")
        else:
            pair = _logical_pair(flow, "inline")
        current = _swap_insets(current, pair)
    return current


def _logical_pair(flow: dict[str, object], axis: str) -> tuple[str, str]:
    start = str(flow[f"{axis}_start"])
    end = str(flow[f"{axis}_end"])
    return start, end


def _swap_insets(insets: dict[str, object], pair: tuple[str, str]) -> dict[str, object]:
    start, end = pair
    opposing = _OPPOSITE[start] == end
    swapped = dict(insets)
    swapped[start] = _retarget(insets[end], end, start, opposing)
    swapped[end] = _retarget(insets[start], start, end, opposing)
    return swapped


def _retarget(value: object, old: str, new: str, opposing: bool) -> object:
    if not isinstance(value, dict):
        return value
    side = value.get("side")
    mapped = side
    if isinstance(side, str):
        if side in _PHYSICAL:
            mapped = _map_physical(side, old, new)
        elif side in {"start", "self-start"} and opposing:
            mapped = "self-end" if side.startswith("self") else "end"
        elif side in {"end", "self-end"} and opposing:
            mapped = "self-start" if side.startswith("self") else "start"
    elif isinstance(side, (int, float)) and not isinstance(side, bool) and opposing:
        mapped = 100 - float(side)
    elif isinstance(side, str) and side.endswith("%") and opposing:
        mapped = 100 - _percentage(side, "anchor()")
    copied = dict(value)
    copied["side"] = mapped
    return copied


def _map_physical(side: str, old: str, new: str) -> str:
    if side == old:
        return new
    if side == _OPPOSITE[old]:
        return _OPPOSITE[new]
    return side


def _tracks(value: object, cb_flow: dict[str, object], box_flow: dict[str, object]) -> tuple[str, str]:
    if not isinstance(value, str) or not value.strip():
        raise _Invalid("position-area is invalid")
    parts = value.split()
    if len(parts) > 2:
        raise _Invalid("position-area is invalid")
    keys = [_keyword_spec(part) for part in parts]
    if len(keys) == 1:
        axis, track = _resolve_key(keys[0], cb_flow, box_flow)
        if axis is None:
            return track, track
        if axis == "block":
            return track, "span-all"
        return "span-all", track
    first = _resolve_key(keys[0], cb_flow, box_flow)
    second = _resolve_key(keys[1], cb_flow, box_flow)
    return _assign(first, second)


def _assign(first: tuple[str | None, str], second: tuple[str | None, str]) -> tuple[str, str]:
    left_axis, left_track = first
    right_axis, right_track = second
    if left_axis is None and right_axis is None:
        left_axis, right_axis = "block", "inline"
    elif left_axis is None:
        left_axis = "inline" if right_axis == "block" else "block"
    elif right_axis is None:
        right_axis = "inline" if left_axis == "block" else "block"
    if left_axis == right_axis:
        raise _Invalid("position-area is invalid")
    block = left_track if left_axis == "block" else right_track
    inline = right_track if right_axis == "inline" else left_track
    return block, inline


def _resolve_key(spec: tuple[str, str, bool], cb_flow: dict[str, object], box_flow: dict[str, object]) -> tuple[str | None, str]:
    kind, track, own = spec
    flow = box_flow if own else cb_flow
    if kind == "ambiguous":
        return None, track
    if kind == "side":
        return _side_track(track, cb_flow)
    if kind == "span-side":
        axis, resolved = _side_track(track, cb_flow)
        return axis, _span(resolved)
    if kind in {"block", "inline"} and not own:
        return kind, track
    if kind in {"block", "inline"}:
        side = str(flow[f"{kind}_{_base(track)}"])
        axis, resolved = _side_track(side, cb_flow)
        return axis, _span(resolved) if track.startswith("span-") else resolved
    side = _axis_side(flow, kind, _base(track))
    axis, resolved = _side_track(side, cb_flow)
    return axis, _span(resolved) if track.startswith("span-") else resolved


def _keyword_spec(token: str) -> tuple[str, str, bool]:
    table = {
        "left": ("side", "left", False),
        "right": ("side", "right", False),
        "top": ("side", "top", False),
        "bottom": ("side", "bottom", False),
        "span-left": ("span-side", "left", False),
        "span-right": ("span-side", "right", False),
        "span-top": ("span-side", "top", False),
        "span-bottom": ("span-side", "bottom", False),
        "center": ("ambiguous", "center", False),
        "span-all": ("ambiguous", "span-all", False),
        "start": ("ambiguous", "start", False),
        "end": ("ambiguous", "end", False),
        "span-start": ("ambiguous", "span-start", False),
        "span-end": ("ambiguous", "span-end", False),
        "self-start": ("ambiguous", "start", True),
        "self-end": ("ambiguous", "end", True),
        "span-self-start": ("ambiguous", "span-start", True),
        "span-self-end": ("ambiguous", "span-end", True),
    }
    if token in table:
        return table[token]
    named = _named_keyword(token)
    if named is None:
        raise _Invalid("position-area is invalid")
    return named


def _named_keyword(token: str) -> tuple[str, str, bool] | None:
    own = False
    body = token
    if body.startswith("span-self-"):
        own = True
        body = "span-" + body.removeprefix("span-self-")
    elif body.startswith("self-"):
        own = True
        body = body.removeprefix("self-")
    axes = ("block", "inline", "x", "y")
    for axis in axes:
        for track in ("span-start", "span-end", "start", "end"):
            if track.startswith("span-"):
                head, tail = track.split("-", 1)
                expected = f"{head}-{axis}-{tail}"
            else:
                expected = f"{axis}-{track}"
            if body == expected:
                return axis, track, own
    return None


def _span(track: str) -> str:
    if track == "start":
        return "span-start"
    if track == "end":
        return "span-end"
    raise _Invalid("position-area is invalid")


def _base(track: str) -> str:
    if track == "span-start":
        return "start"
    if track == "span-end":
        return "end"
    return track


def _side_track(side: str, flow: dict[str, object]) -> tuple[str, str]:
    for axis in ("block", "inline"):
        if side == flow[f"{axis}_start"]:
            return axis, "start"
        if side == flow[f"{axis}_end"]:
            return axis, "end"
    raise _Invalid("position-area is invalid")


def _axis_side(flow: dict[str, object], physical: str, which: str) -> str:
    horizontal_axis = "block" if str(flow["block_start"]) in {"left", "right"} else "inline"
    logical = horizontal_axis if physical == "x" else "inline" if horizontal_axis == "block" else "block"
    if which not in {"start", "end"}:
        raise _Invalid("position-area is invalid")
    return str(flow[f"{logical}_{which}"])


def _interval(
    container: dict[str, object],
    anchor: dict[str, object],
    flow: dict[str, object],
    axis: str,
    track: str,
) -> tuple[float, float]:
    cb_start, cb_end = _axis_edges(container, flow, axis)
    anchor_start, anchor_end = _axis_edges(anchor, flow, axis)
    start_ward = cb_start >= cb_end
    line1 = max(cb_start, anchor_start) if start_ward else min(cb_start, anchor_start)
    line4 = min(cb_end, anchor_end) if start_ward else max(cb_end, anchor_end)
    lines = {
        "start": (line1, anchor_start),
        "center": (anchor_start, anchor_end),
        "end": (anchor_end, line4),
        "span-start": (line1, anchor_end),
        "span-end": (anchor_start, line4),
        "span-all": (line1, line4),
    }
    if track not in lines:
        raise _Invalid("position-area is invalid")
    return lines[track]


def _axis_edges(rect: dict[str, object], flow: dict[str, object], axis: str) -> tuple[float, float]:
    return _edge(rect, str(flow[f"{axis}_start"])), _edge(rect, str(flow[f"{axis}_end"]))


def _edge(rect: dict[str, object], side: str) -> float:
    if side == "left":
        return float(rect["x"])
    if side == "right":
        return float(rect["x"]) + float(rect["width"])
    if side == "top":
        return float(rect["y"])
    if side == "bottom":
        return float(rect["y"]) + float(rect["height"])
    raise _Invalid("writing-mode is invalid")


def _physical_intervals(
    flow: dict[str, object],
    block: tuple[float, float],
    inline: tuple[float, float],
) -> tuple[tuple[float, float], tuple[float, float]]:
    if _horizontal(flow, "inline"):
        return inline, block
    return block, inline


def _horizontal(flow: dict[str, object], axis: str) -> bool:
    return str(flow[f"{axis}_start"]) in {"left", "right"}


def _start_is_min(flow: dict[str, object], axis: str) -> bool:
    return str(flow[f"{axis}_start"]) in {"left", "top"}


def _align_for(track: str) -> str:
    if track == "center":
        return "center"
    if track == "span-all":
        return "anchor-center"
    if track in {"start", "span-start"}:
        return "end"
    if track in {"end", "span-end"}:
        return "start"
    raise _Invalid("position-area is invalid")


def _align_origin(
    area: tuple[float, float],
    anchor: tuple[float, float],
    size: float,
    mode: str,
    start_is_min: bool,
) -> float:
    area_start, area_end = area
    if mode == "center":
        return (area_start + area_end) / 2 - size / 2
    if mode == "anchor-center":
        return (anchor[0] + anchor[1]) / 2 - size / 2
    if mode == "start":
        return area_start if start_is_min else area_start - size
    return area_end - size if start_is_min else area_end


def _bounds(horizontal: tuple[float, float], vertical: tuple[float, float]) -> dict[str, float]:
    x0, x1 = horizontal
    y0, y1 = vertical
    return {"x": min(x0, x1), "y": min(y0, y1), "width": abs(x1 - x0), "height": abs(y1 - y0)}


def _inset_area(container: dict[str, object], insets: dict[str, float | None]) -> dict[str, float]:
    top = 0.0 if insets["top"] is None else insets["top"]
    right = 0.0 if insets["right"] is None else insets["right"]
    bottom = 0.0 if insets["bottom"] is None else insets["bottom"]
    left = 0.0 if insets["left"] is None else insets["left"]
    return {
        "x": float(container["x"]) + left,
        "y": float(container["y"]) + top,
        "width": float(container["width"]) - left - right,
        "height": float(container["height"]) - top - bottom,
    }


def _inset(
    value: object,
    prop: str,
    container: dict[str, object],
    item: dict[str, object],
    anchor: dict[str, object] | None,
) -> float | None:
    if value is None or value == _AUTO:
        return None
    if isinstance(value, dict):
        try:
            return _anchor_inset(value, prop, container, item, anchor)
        except _Invalid:
            if "fallback" not in value:
                raise
            return _length(value.get("fallback"), "anchor()", allow_negative=True)
    return _length(value, prop, allow_negative=True)


def _anchor_inset(
    value: dict[str, object],
    prop: str,
    container: dict[str, object],
    item: dict[str, object],
    anchor: dict[str, object] | None,
) -> float:
    if set(value) - {"side", "fallback"}:
        raise _Invalid("anchor() is invalid")
    if anchor is None:
        raise _Invalid("default anchor is missing")
    point = _anchor_point(value.get("side"), prop, container, item, anchor)
    if prop == "top":
        return point - float(container["y"])
    if prop == "bottom":
        return float(container["y"]) + float(container["height"]) - point
    if prop == "left":
        return point - float(container["x"])
    return float(container["x"]) + float(container["width"]) - point


def _anchor_point(
    side: object,
    prop: str,
    container: dict[str, object],
    item: dict[str, object],
    anchor: dict[str, object],
) -> float:
    physical = _anchor_side(side, prop, container["flow"], item["flow"])
    if physical in {"left", "right", "top", "bottom"}:
        return _edge(anchor, physical)
    flow = item["flow"] if isinstance(side, str) and side.startswith("self") else container["flow"]
    start, end = _axis_edges(anchor, flow, _property_axis(prop, flow))
    return start + (end - start) * (_anchor_percentage(side) / 100)


def _anchor_side(side: object, prop: str, cb_flow: dict[str, object], box_flow: dict[str, object]) -> str:
    if side == "inside":
        return prop
    if side == "outside":
        return _OPPOSITE[prop]
    if isinstance(side, str) and side in _PHYSICAL:
        if _physical_axis(side) != _physical_axis(prop):
            raise _Invalid("anchor() side is on the wrong axis")
        return side
    return ""


def _anchor_percentage(side: object) -> float:
    if side in {"center", "inside", "outside"} or side in _PHYSICAL:
        return 50.0 if side == "center" else 0.0
    if side in {"start", "self-start"}:
        return 0.0
    if side in {"end", "self-end"}:
        return 100.0
    if isinstance(side, str) and side.endswith("%"):
        return _percentage(side, "anchor()")
    return _length(side, "anchor()", allow_negative=False)


def _property_axis(prop: str, flow: dict[str, object]) -> str:
    horizontal = _physical_axis(prop) == "x"
    block_horizontal = str(flow["block_start"]) in {"left", "right"}
    if horizontal:
        return "block" if block_horizontal else "inline"
    return "inline" if block_horizontal else "block"


def _physical_axis(side: str) -> str:
    if side in {"left", "right"}:
        return "x"
    if side in {"top", "bottom"}:
        return "y"
    raise _Invalid("anchor() is invalid")


def _over_constrain(start: float | None, end: float | None, direction: str) -> tuple[float | None, float | None]:
    if start is None or end is None:
        return start, end
    if direction == "rtl":
        return None, end
    return start, None


def _contains(outer: dict[str, float], inner: dict[str, float]) -> bool:
    return (
        inner["x"] >= outer["x"] - _EPS
        and inner["y"] >= outer["y"] - _EPS
        and inner["x"] + inner["width"] <= outer["x"] + outer["width"] + _EPS
        and inner["y"] + inner["height"] <= outer["y"] + outer["height"] + _EPS
    )


def _rect(value: object, name: str, *, sized: bool) -> dict[str, object]:
    if not isinstance(value, dict):
        raise _Invalid(f"{name} is invalid")
    allowed = {"x", "y", "width", "height", "writing_mode", "direction", "text_orientation"}
    if set(value) - allowed:
        raise _Invalid(f"{name} is invalid")
    flow = _flow(value.get("writing_mode", "horizontal-tb"), value.get("direction", "ltr"), value.get("text_orientation", "mixed"))
    rect = {
        "x": _length(value.get("x", 0), f"{name} x", allow_negative=True),
        "y": _length(value.get("y", 0), f"{name} y", allow_negative=True),
        "width": _length(value.get("width", 0), f"{name} width", allow_negative=False),
        "height": _length(value.get("height", 0), f"{name} height", allow_negative=False),
        "flow": flow,
    }
    if sized and (float(rect["width"]) < 0 or float(rect["height"]) < 0):
        raise _Invalid(f"{name} is invalid")
    return rect


def _box(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise _Invalid("box is invalid")
    allowed = {
        "width",
        "height",
        "margin_top",
        "margin_right",
        "margin_bottom",
        "margin_left",
        "position_area",
        "insets",
        "writing_mode",
        "direction",
        "text_orientation",
    }
    if set(value) - allowed:
        raise _Invalid("box is invalid")
    insets = _insets(value.get("insets", _AUTO))
    area = value.get("position_area")
    if area is not None and not isinstance(area, str):
        raise _Invalid("position-area is invalid")
    return {
        "width": _length(value.get("width"), "width", allow_negative=False),
        "height": _length(value.get("height"), "height", allow_negative=False),
        "margin_top": _length(value.get("margin_top", 0), "margin-top", allow_negative=True),
        "margin_right": _length(value.get("margin_right", 0), "margin-right", allow_negative=True),
        "margin_bottom": _length(value.get("margin_bottom", 0), "margin-bottom", allow_negative=True),
        "margin_left": _length(value.get("margin_left", 0), "margin-left", allow_negative=True),
        "position_area": area,
        "insets": insets,
        "flow": _flow(value.get("writing_mode", "horizontal-tb"), value.get("direction", "ltr"), value.get("text_orientation", "mixed")),
    }


def _insets(value: object) -> dict[str, object]:
    if value is None or value == _AUTO:
        return {side: None for side in ("top", "right", "bottom", "left")}
    if not isinstance(value, dict):
        raise _Invalid("insets are invalid")
    if set(value) - {"top", "right", "bottom", "left"}:
        raise _Invalid("insets are invalid")
    return {side: value.get(side) for side in ("top", "right", "bottom", "left")}


def _flow(writing_mode: object, direction: object, text_orientation: object) -> dict[str, object]:
    resolved = resolve_writing_mode(writing_mode, direction, text_orientation=text_orientation)
    if resolved.get("outcome") != "resolved":
        raise _Invalid(str(resolved.get("reason") or "writing-mode is invalid"))
    return resolved


def _fallback_label(fallback: object, index: int) -> str:
    if isinstance(fallback, str) and fallback.strip():
        return fallback
    if isinstance(fallback, dict) and isinstance(fallback.get("position_area"), str):
        return str(fallback["position_area"])
    return f"fallback-{index + 1}"


def _keyword(value: object, allowed: frozenset[str], name: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise _Invalid(f"{name} is invalid")
    return value


def _percentage(value: str, name: str) -> float:
    try:
        number = float(value[:-1])
    except ValueError as exc:
        raise _Invalid(f"{name} is invalid") from exc
    return _length(number, name, allow_negative=False)


def _length(value: object, name: str, *, allow_negative: bool) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _Invalid(f"{name} is invalid")
    number = float(value)
    if number != number or number in {float("inf"), float("-inf")}:
        raise _Invalid(f"{name} is invalid")
    if not allow_negative and number < 0:
        raise _Invalid(f"{name} is invalid")
    return number


def _payload(option: dict[str, object]) -> dict[str, object]:
    area = option["area"]
    assert isinstance(area, dict)
    return {
        "outcome": "placed",
        "reason": None,
        "x": _number(float(option["x"])),
        "y": _number(float(option["y"])),
        "width": _number(float(option["width"])),
        "height": _number(float(option["height"])),
        "option": option["option"],
        "fits": bool(option["fits"]),
        "area_x": _number(float(area["x"])),
        "area_y": _number(float(area["y"])),
        "area_width": _number(float(area["width"])),
        "area_height": _number(float(area["height"])),
        "top": _maybe(option["top"]),
        "right": _maybe(option["right"]),
        "bottom": _maybe(option["bottom"]),
        "left": _maybe(option["left"]),
    }


def _invalid(reason: str) -> dict[str, object]:
    return {
        "outcome": "invalid",
        "reason": reason,
        "x": None,
        "y": None,
        "width": None,
        "height": None,
        "option": None,
        "fits": False,
        "area_x": None,
        "area_y": None,
        "area_width": None,
        "area_height": None,
        "top": None,
        "right": None,
        "bottom": None,
        "left": None,
    }


def _maybe(value: object) -> int | float | None:
    if value is None:
        return None
    return _number(float(value))


def _number(value: float) -> int | float:
    nearest = round(value)
    if abs(value - nearest) <= _EPS:
        return int(nearest)
    return value
