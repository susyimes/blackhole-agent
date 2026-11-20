"""Resting scroll offset of a CSS scroll-snap container.

CSS Scroll Snap Level 1. The snapport is the scrollport inset by
scroll-padding. A snap area is the border box outset by scroll-margin.
``start``, ``end``, and ``center`` name the edges that meet. An area larger
than the snapport also accepts every offset where it still covers the
snapport, when the previous and next alignment snaps are farther apart than
the snapport; a missing neighbor counts as an open side. An alignment that
leaves the area fully outside the snapport is dropped. An alignment past the
scrollable overflow clamps to the reachable edge and is kept only when the
area is still visible there.

``mandatory`` absolute and stationary scrolls use the nearest remaining
offset. An equal distance resolves toward the end. A relative scroll ignores
the offset it is leaving once the travel exceeds one snapport, will not jump
onward by more than one snapport, and stops at the first ``always`` alignment
it would pass. The specification leaves proximity and that escape distance to
the user agent; this reader uses one snapport for both. ``both`` snaps the
block axis, then the inline axis, and drops an area the other axis has pushed
fully outside the snapport. ``pair`` requires one area to supply both axes.
A larger area resolves start and end in its own writing mode and direction.
A targeted area is the only absolute or stationary snap on its axis. When
several areas align, a descendant wins over its ancestor.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

_EPS = 1e-9
_ALIGNS = frozenset({"none", "start", "end", "center"})
_MODES = frozenset({"horizontal-tb", "vertical-rl", "vertical-lr"})
_DIRECTIONS = frozenset({"ltr", "rtl"})
_INTENTS = frozenset({"absolute", "relative", "stationary"})
_STOPS = frozenset({"normal", "always"})
_AXES = frozenset({"x", "y", "block", "inline", "both", "pair"})
_STRICT = frozenset({"mandatory", "proximity"})
_CONTAINER_FIELDS = frozenset(
    {
        "port_x",
        "port_y",
        "padding_left",
        "padding_right",
        "padding_top",
        "padding_bottom",
        "max_x",
        "max_y",
        "intended_x",
        "intended_y",
        "current_x",
        "current_y",
        "intent",
        "snap_type",
        "writing_mode",
        "direction",
    }
)
_AREA_FIELDS = frozenset(
    {
        "id",
        "x",
        "y",
        "width",
        "height",
        "margin_left",
        "margin_right",
        "margin_top",
        "margin_bottom",
        "align",
        "align_block",
        "align_inline",
        "snap_stop",
        "writing_mode",
        "direction",
        "focused",
        "targeted",
        "parent",
    }
)


class _Invalid(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class _Area:
    id: str
    x: float
    y: float
    width: float
    height: float
    margin_left: float
    margin_right: float
    margin_top: float
    margin_bottom: float
    align_block: str
    align_inline: str
    snap_stop: str
    writing_mode: str | None
    direction: str | None
    focused: bool
    targeted: bool
    parent: str | None
    order: int


@dataclass(frozen=True)
class _Container:
    port_x: float
    port_y: float
    padding_left: float
    padding_right: float
    padding_top: float
    padding_bottom: float
    max_x: float
    max_y: float
    intended_x: float
    intended_y: float
    current_x: float
    current_y: float
    intent: str
    axis: str
    strictness: str
    writing_mode: str
    direction: str


@dataclass(frozen=True)
class _Geom:
    physical: str
    port: float
    pad_min: float
    pad_max: float
    max_scroll: float
    snapport: float


def resolve_scroll_snap(container: object, areas: object = ()) -> dict[str, object]:
    """Return the resting ``x`` and ``y`` scroll offsets.

    ``container`` carries the scrollport, scroll-padding, scroll range,
    intended and current offsets, ``intent`` (``absolute``, ``relative``, or
    ``stationary``), and ``snap_type`` (``none``, or an axis plus optional
    ``mandatory`` or ``proximity``). Each area carries its border box,
    scroll-margin, ``align`` (block then inline), and optional ``snap_stop``,
    ``writing_mode``, ``direction``, ``focused``, ``targeted``, and ``parent``.
    Lengths are CSS pixels already resolved by the caller. ``auto``
    scroll-padding is zero.
    """

    try:
        parsed_container = _container(container)
        parsed_areas = _areas(areas)
        return _resolve(parsed_container, parsed_areas)
    except _Invalid as exc:
        return _invalid(exc.reason)


def _resolve(container: _Container, areas: list[_Area]) -> dict[str, object]:
    x = _clamp(container.intended_x, container.max_x)
    y = _clamp(container.intended_y, container.max_y)
    x_snapped = False
    y_snapped = False
    if container.axis == "none":
        return _result(container, areas, x, y, False, False)
    if container.axis == "pair":
        x, y, x_snapped, y_snapped = _solve_pair(container, areas, x, y)
        return _result(container, areas, x, y, x_snapped, y_snapped)
    active = _active_axes(container)
    if container.axis == "both":
        x, y, x_snapped, y_snapped = _solve_both(container, areas, active, x, y)
    else:
        if "x" in active:
            x, x_snapped = _solve_axis(container, areas, _geom(container, "x"), use_2d=False, other_scroll=y)
        if "y" in active:
            y, y_snapped = _solve_axis(container, areas, _geom(container, "y"), use_2d=False, other_scroll=x)
    return _result(container, areas, x, y, x_snapped, y_snapped)


def _solve_both(
    container: _Container,
    areas: list[_Area],
    active: set[str],
    x: float,
    y: float,
) -> tuple[float, float, bool, bool]:
    mapping = _physical_axes(container.writing_mode)
    order = [mapping["block"], mapping["inline"]]
    x_snapped = False
    y_snapped = False
    seen: set[tuple[float, float]] = set()
    for _ in range(8):
        key = (round(x, 6), round(y, 6))
        if key in seen:
            break
        seen.add(key)
        previous = (x, y, x_snapped, y_snapped)
        for physical in order:
            if physical not in active:
                continue
            other = y if physical == "x" else x
            offset, snapped = _solve_axis(
                container,
                areas,
                _geom(container, physical),
                use_2d=True,
                other_scroll=other,
            )
            if physical == "x":
                x, x_snapped = offset, snapped
            else:
                y, y_snapped = offset, snapped
        if (x, y, x_snapped, y_snapped) == previous:
            break
    return x, y, x_snapped, y_snapped


def _solve_axis(
    container: _Container,
    areas: list[_Area],
    geom: _Geom,
    *,
    use_2d: bool,
    other_scroll: float,
) -> tuple[float, bool]:
    pool = [area for area in areas if _logical_align(area, geom.physical, container) != "none"]
    targeted = [area for area in pool if area.targeted]
    if targeted and container.intent != "relative":
        offset, snapped = _select_axis(container, targeted, geom, use_2d=use_2d, other_scroll=other_scroll)
        if snapped:
            return offset, True
    return _select_axis(container, pool, geom, use_2d=use_2d, other_scroll=other_scroll)


def _select_axis(
    container: _Container,
    areas: list[_Area],
    geom: _Geom,
    *,
    use_2d: bool,
    other_scroll: float,
) -> tuple[float, bool]:
    intended = _clamp(_axis_value(container, geom.physical, "intended"), geom.max_scroll)
    current = _clamp(_axis_value(container, geom.physical, "current"), geom.max_scroll)
    direction = 0
    if container.intent == "relative":
        if intended > current + _EPS:
            direction = 1
        elif intended < current - _EPS:
            direction = -1
    relative = direction != 0
    travel = abs(intended - current)
    short = travel <= geom.snapport + _EPS
    other = _other_geom(container, geom.physical)
    discrete: list[tuple[float, _Area]] = []
    for area in areas:
        raw = _alignment_offset(area, geom, container)
        if raw is None:
            continue
        offset = _clamp(raw, geom.max_scroll)
        if _visible(area, geom, offset, use_2d=use_2d, other_scroll=other_scroll, other=other):
            discrete.append((offset, area))
    if relative:
        trap = _snap_stop(discrete, current, intended)
        if trap is not None:
            return trap, True
    points = _merge([offset for offset, _area in discrete])
    best: tuple[float, float, float] | None = None

    def offer(offset: float) -> None:
        nonlocal best
        if relative:
            if not short and abs(offset - current) <= _EPS:
                return
            if direction > 0 and offset < current - _EPS:
                return
            if direction < 0 and offset > current + _EPS:
                return
            if abs(offset - intended) > geom.snapport + _EPS:
                return
        item = (abs(offset - intended), -offset, offset)
        if best is None or item < best:
            best = item

    for offset, _area in discrete:
        offer(offset)
    gaps = _wide_gaps(points, geom.snapport, geom.max_scroll)
    for area in areas:
        if not _large(area, geom, container):
            continue
        if use_2d and not _interval_hits(*_edges(area, other.physical), *_snapport(other, other_scroll)):
            continue
        cover = _cover_interval(area, geom)
        if cover is None:
            continue
        for gap in gaps:
            segment = _overlap(cover, gap)
            if segment is None:
                continue
            offer(_project(intended, segment))
    if best is None:
        return intended, False
    chosen = best[2]
    if not relative and container.strictness == "proximity" and abs(chosen - intended) > geom.snapport + _EPS:
        return intended, False
    return chosen, True


def _solve_pair(
    container: _Container,
    areas: list[_Area],
    fallback_x: float,
    fallback_y: float,
) -> tuple[float, float, bool, bool]:
    eligible = [area for area in areas if area.align_block != "none" and area.align_inline != "none"]
    targeted = [area for area in eligible if area.targeted]
    if targeted and container.intent != "relative":
        found = _best_pair(container, targeted)
        if found is not None:
            return found
    found = _best_pair(container, eligible)
    if found is None:
        return fallback_x, fallback_y, False, False
    return found


def _best_pair(container: _Container, areas: list[_Area]) -> tuple[float, float, bool, bool] | None:
    if not areas:
        return None
    x_geom = _geom(container, "x")
    y_geom = _geom(container, "y")
    intended_x = _clamp(container.intended_x, container.max_x)
    intended_y = _clamp(container.intended_y, container.max_y)
    current_x = _clamp(container.current_x, container.max_x)
    current_y = _clamp(container.current_y, container.max_y)
    x_points = _merge(
        offset
        for area in areas
        for offset in _pair_axis_points(area, x_geom, container)
    )
    y_points = _merge(
        offset
        for area in areas
        for offset in _pair_axis_points(area, y_geom, container)
    )
    x_gaps = _wide_gaps(x_points, x_geom.snapport, x_geom.max_scroll)
    y_gaps = _wide_gaps(y_points, y_geom.snapport, y_geom.max_scroll)
    best: tuple[tuple[float, float, float, float, int], float, float] | None = None
    for area in areas:
        x_options = _pair_options(area, x_geom, container, intended_x, x_gaps)
        y_options = _pair_options(area, y_geom, container, intended_y, y_gaps)
        for x_offset in x_options:
            for y_offset in y_options:
                if not _rect_hits(area, x_geom, x_offset, y_geom, y_offset):
                    continue
                if not _pair_allows(
                    container,
                    x_offset,
                    y_offset,
                    intended_x,
                    intended_y,
                    current_x,
                    current_y,
                    x_geom.snapport,
                    y_geom.snapport,
                ):
                    continue
                key = (
                    (x_offset - intended_x) ** 2 + (y_offset - intended_y) ** 2,
                    -x_offset,
                    -y_offset,
                    area.order,
                )
                if best is None or key < best[0]:
                    best = (key, x_offset, y_offset)
    if best is None:
        return None
    return best[1], best[2], True, True


def _pair_axis_points(area: _Area, geom: _Geom, container: _Container) -> list[float]:
    raw = _alignment_offset(area, geom, container)
    if raw is None:
        return []
    offset = _clamp(raw, geom.max_scroll)
    if not _visible(area, geom, offset, use_2d=False, other_scroll=0.0, other=_other_geom(container, geom.physical)):
        return []
    return [offset]


def _pair_options(
    area: _Area,
    geom: _Geom,
    container: _Container,
    intended: float,
    gaps: list[tuple[float, float]],
) -> list[float]:
    options = _pair_axis_points(area, geom, container)
    if _large(area, geom, container):
        cover = _cover_interval(area, geom)
        if cover is not None:
            for gap in gaps:
                segment = _overlap(cover, gap)
                if segment is not None:
                    options.append(_project(intended, segment))
    return _merge(options)


def _pair_allows(
    container: _Container,
    x_offset: float,
    y_offset: float,
    intended_x: float,
    intended_y: float,
    current_x: float,
    current_y: float,
    snapport_x: float,
    snapport_y: float,
) -> bool:
    if container.intent == "relative":
        if not _relative_point(x_offset, intended_x, current_x, snapport_x):
            return False
        if not _relative_point(y_offset, intended_y, current_y, snapport_y):
            return False
        return True
    if container.strictness == "proximity":
        if abs(x_offset - intended_x) > snapport_x + _EPS:
            return False
        if abs(y_offset - intended_y) > snapport_y + _EPS:
            return False
    return True


def _relative_point(offset: float, intended: float, current: float, snapport: float) -> bool:
    if abs(intended - current) <= _EPS:
        return abs(offset - intended) <= snapport + _EPS
    direction = 1 if intended > current else -1
    travel = abs(intended - current)
    if travel > snapport + _EPS and abs(offset - current) <= _EPS:
        return False
    if direction > 0 and offset < current - _EPS:
        return False
    if direction < 0 and offset > current + _EPS:
        return False
    return abs(offset - intended) <= snapport + _EPS


def _snap_stop(discrete: list[tuple[float, _Area]], current: float, intended: float) -> float | None:
    lo, hi = (current, intended) if current < intended else (intended, current)
    traps = [
        offset
        for offset, area in discrete
        if area.snap_stop == "always" and lo + _EPS < offset < hi - _EPS
    ]
    if not traps:
        return None
    direction = 1 if intended > current else -1
    traps.sort(key=lambda offset: (abs(offset - current), -direction * offset))
    return traps[0]


def _result(
    container: _Container,
    areas: list[_Area],
    x: float,
    y: float,
    x_snapped: bool,
    y_snapped: bool,
) -> dict[str, object]:
    inline_axis, block_axis = _logical_physical(container.writing_mode)
    snapped_inline = None
    snapped_block = None
    if _axis_participates(container, inline_axis, x_snapped, y_snapped):
        snapped_inline = _snapped_box(container, areas, inline_axis, x, y)
    if _axis_participates(container, block_axis, x_snapped, y_snapped):
        snapped_block = _snapped_box(container, areas, block_axis, x, y)
    return {
        "outcome": "snapped" if x_snapped or y_snapped else "unsnapped",
        "x": _number(x),
        "y": _number(y),
        "snapped_inline": snapped_inline,
        "snapped_block": snapped_block,
        "reason": None,
    }


def _axis_participates(container: _Container, physical: str, x_snapped: bool, y_snapped: bool) -> bool:
    if container.axis == "none":
        return False
    if container.axis == "pair":
        return x_snapped and y_snapped
    return x_snapped if physical == "x" else y_snapped


def _snapped_box(
    container: _Container,
    areas: list[_Area],
    physical: str,
    x: float,
    y: float,
) -> str | None:
    aligned = [area for area in areas if _aligned(area, container, areas, physical, x, y)]
    if not aligned:
        return None
    if any(area.focused or _has_flag(area, areas, "focused") for area in aligned):
        aligned = [area for area in aligned if area.focused or _has_flag(area, areas, "focused")]
    elif any(area.targeted or _has_flag(area, areas, "targeted") for area in aligned):
        aligned = [area for area in aligned if area.targeted or _has_flag(area, areas, "targeted")]
    kept = [area for area in aligned if not any(_is_ancestor(area, other, areas) for other in aligned)]
    if not kept:
        return None
    kept.sort(key=lambda area: area.order)
    inline_physical, block_physical = _logical_physical(container.writing_mode)
    if physical == inline_physical:
        inline = kept
        block = [area for area in areas if _aligned(area, container, areas, block_physical, x, y)]
    else:
        block = kept
        inline = [area for area in areas if _aligned(area, container, areas, inline_physical, x, y)]
    inline_ids = {area.id for area in inline}
    block_ids = {area.id for area in block}
    if inline_ids & block_ids:
        shared = inline_ids & block_ids
        kept = [area for area in kept if area.id in shared]
        kept.sort(key=lambda area: area.order)
    return kept[0].id if kept else None


def _aligned(
    area: _Area,
    container: _Container,
    areas: list[_Area],
    physical: str,
    x: float,
    y: float,
) -> bool:
    if _logical_align(area, physical, container) == "none":
        return False
    geom = _geom(container, physical)
    other = _other_geom(container, physical)
    scroll = x if physical == "x" else y
    other_scroll = y if physical == "x" else x
    if not _visible(area, geom, scroll, use_2d=True, other_scroll=other_scroll, other=other):
        return False
    raw = _alignment_offset(area, geom, container)
    if raw is not None and abs(_clamp(raw, geom.max_scroll) - scroll) <= _EPS:
        return True
    if not _large(area, geom, container):
        return False
    cover = _cover_interval(area, geom)
    if cover is None or not (cover[0] - _EPS <= scroll <= cover[1] + _EPS):
        return False
    points: list[float] = []
    for candidate in areas:
        candidate_raw = _alignment_offset(candidate, geom, container)
        if candidate_raw is None:
            continue
        offset = _clamp(candidate_raw, geom.max_scroll)
        if _visible(candidate, geom, offset, use_2d=True, other_scroll=other_scroll, other=other):
            points.append(offset)
    gaps = _wide_gaps(_merge(points), geom.snapport, geom.max_scroll)
    return any(gap[0] - _EPS <= scroll <= gap[1] + _EPS for gap in gaps)


def _has_flag(area: _Area, areas: list[_Area], flag: str) -> bool:
    children: dict[str, list[_Area]] = {}
    for candidate in areas:
        if candidate.parent:
            children.setdefault(candidate.parent, []).append(candidate)
    stack = list(children.get(area.id, ()))
    seen = {area.id}
    while stack:
        child = stack.pop()
        if child.id in seen:
            continue
        seen.add(child.id)
        if flag == "focused" and child.focused:
            return True
        if flag == "targeted" and child.targeted:
            return True
        stack.extend(children.get(child.id, ()))
    return False


def _is_ancestor(candidate: _Area, other: _Area, areas: list[_Area]) -> bool:
    if candidate.id == other.id:
        return False
    by_id = {area.id: area for area in areas}
    seen: set[str] = set()
    current = other.parent
    while current:
        if current == candidate.id:
            return True
        if current in seen:
            return False
        seen.add(current)
        parent = by_id.get(current)
        if parent is None:
            return False
        current = parent.parent
    return False


def _alignment_offset(area: _Area, geom: _Geom, container: _Container) -> float | None:
    align = _logical_align(area, geom.physical, container)
    if align == "none":
        return None
    area_min, area_max = _edges(area, geom.physical)
    mode, direction = _edge_mode(area, container, area_max - area_min, geom.snapport)
    start_min = _start_is_physical_min(mode, direction, geom.physical)
    if align == "center":
        center = (area_min + area_max) / 2
        return center - (geom.pad_min + geom.port - geom.pad_max) / 2
    toward_min = start_min if align == "start" else not start_min
    if toward_min:
        return area_min - geom.pad_min
    return area_max - geom.port + geom.pad_max


def _large(area: _Area, geom: _Geom, container: _Container) -> bool:
    del container
    area_min, area_max = _edges(area, geom.physical)
    return area_max - area_min > geom.snapport + _EPS


def _cover_interval(area: _Area, geom: _Geom) -> tuple[float, float] | None:
    area_min, area_max = _edges(area, geom.physical)
    lo = max(area_min - geom.pad_min, 0.0)
    hi = min(area_max - geom.port + geom.pad_max, geom.max_scroll)
    if hi < lo - _EPS:
        return None
    return lo, hi


def _edge_mode(area: _Area, container: _Container, size: float, snapport: float) -> tuple[str, str]:
    if size > snapport + _EPS:
        return area.writing_mode or container.writing_mode, area.direction or container.direction
    return container.writing_mode, container.direction


def _visible(
    area: _Area,
    geom: _Geom,
    scroll: float,
    *,
    use_2d: bool,
    other_scroll: float,
    other: _Geom,
) -> bool:
    if not _interval_hits(*_edges(area, geom.physical), *_snapport(geom, scroll)):
        return False
    if not use_2d:
        return True
    return _interval_hits(*_edges(area, other.physical), *_snapport(other, other_scroll))


def _rect_hits(area: _Area, x_geom: _Geom, x_offset: float, y_geom: _Geom, y_offset: float) -> bool:
    return _visible(area, x_geom, x_offset, use_2d=True, other_scroll=y_offset, other=y_geom)


def _edges(area: _Area, physical: str) -> tuple[float, float]:
    if physical == "x":
        return area.x - area.margin_left, area.x + area.width + area.margin_right
    return area.y - area.margin_top, area.y + area.height + area.margin_bottom


def _snapport(geom: _Geom, scroll: float) -> tuple[float, float]:
    return scroll + geom.pad_min, scroll + geom.port - geom.pad_max


def _interval_hits(area_min: float, area_max: float, port_min: float, port_max: float) -> bool:
    return area_max > port_min + _EPS and area_min < port_max - _EPS


def _logical_align(area: _Area, physical: str, container: _Container) -> str:
    mapping = _physical_axes(container.writing_mode)
    if mapping["inline"] == physical:
        return area.align_inline
    return area.align_block


def _logical_physical(writing_mode: str) -> tuple[str, str]:
    mapping = _physical_axes(writing_mode)
    return mapping["inline"], mapping["block"]


def _physical_axes(writing_mode: str) -> dict[str, str]:
    if writing_mode == "horizontal-tb":
        return {"inline": "x", "block": "y"}
    return {"inline": "y", "block": "x"}


def _start_is_physical_min(writing_mode: str, direction: str, physical: str) -> bool:
    if physical == "x":
        if writing_mode == "horizontal-tb":
            return direction == "ltr"
        if writing_mode == "vertical-rl":
            return False
        return True
    if writing_mode == "horizontal-tb":
        return True
    return direction == "ltr"


def _active_axes(container: _Container) -> set[str]:
    if container.axis in {"both", "pair"}:
        return {"x", "y"}
    if container.axis in {"x", "y"}:
        return {container.axis}
    mapping = _physical_axes(container.writing_mode)
    return {mapping[container.axis]}


def _geom(container: _Container, physical: str) -> _Geom:
    if physical == "x":
        port = container.port_x
        pad_min = container.padding_left
        pad_max = container.padding_right
        limit = container.max_x
    else:
        port = container.port_y
        pad_min = container.padding_top
        pad_max = container.padding_bottom
        limit = container.max_y
    return _Geom(physical, port, pad_min, pad_max, limit, port - pad_min - pad_max)


def _other_geom(container: _Container, physical: str) -> _Geom:
    return _geom(container, "y" if physical == "x" else "x")


def _axis_value(container: _Container, physical: str, kind: str) -> float:
    if physical == "x":
        return container.intended_x if kind == "intended" else container.current_x
    return container.intended_y if kind == "intended" else container.current_y


def _wide_gaps(points: list[float], snapport: float, max_scroll: float) -> list[tuple[float, float]]:
    if not points:
        return [(0.0, max_scroll)]
    gaps: list[tuple[float, float]] = []
    if points[0] > _EPS:
        gaps.append((0.0, points[0]))
    for left, right in zip(points, points[1:]):
        if right - left > snapport + _EPS:
            gaps.append((left, right))
    if max_scroll - points[-1] > _EPS:
        gaps.append((points[-1], max_scroll))
    return gaps


def _merge(values: object) -> list[float]:
    ordered = sorted(float(value) for value in values)  # type: ignore[union-attr]
    if not ordered:
        return []
    merged = [ordered[0]]
    for value in ordered[1:]:
        if value - merged[-1] > _EPS:
            merged.append(value)
    return merged


def _overlap(
    left: tuple[float, float],
    right: tuple[float, float],
) -> tuple[float, float] | None:
    lo = max(left[0], right[0])
    hi = min(left[1], right[1])
    if hi < lo - _EPS:
        return None
    return lo, hi


def _project(target: float, segment: tuple[float, float]) -> float:
    if target < segment[0]:
        return segment[0]
    if target > segment[1]:
        return segment[1]
    return target


def _clamp(value: float, limit: float) -> float:
    if value < 0:
        return 0.0
    if value > limit:
        return limit
    return value


def _container(value: object) -> _Container:
    if not isinstance(value, Mapping):
        raise _Invalid("container")
    unknown = set(value) - _CONTAINER_FIELDS
    if unknown:
        raise _Invalid("container")
    port_x = _positive(value.get("port_x"), "scrollport")
    port_y = _positive(value.get("port_y"), "scrollport")
    padding_left = _padding(value.get("padding_left", 0))
    padding_right = _padding(value.get("padding_right", 0))
    padding_top = _padding(value.get("padding_top", 0))
    padding_bottom = _padding(value.get("padding_bottom", 0))
    if padding_left + padding_right > port_x + _EPS or padding_top + padding_bottom > port_y + _EPS:
        raise _Invalid("scroll-padding")
    axis, strictness = _snap_type(value.get("snap_type", "none"))
    writing_mode = _choice(value.get("writing_mode", "horizontal-tb"), _MODES, "writing-mode")
    direction = _choice(value.get("direction", "ltr"), _DIRECTIONS, "direction")
    return _Container(
        port_x=port_x,
        port_y=port_y,
        padding_left=padding_left,
        padding_right=padding_right,
        padding_top=padding_top,
        padding_bottom=padding_bottom,
        max_x=_nonnegative(value.get("max_x", 0), "max-scroll"),
        max_y=_nonnegative(value.get("max_y", 0), "max-scroll"),
        intended_x=_finite(value.get("intended_x", 0), "intended"),
        intended_y=_finite(value.get("intended_y", 0), "intended"),
        current_x=_finite(value.get("current_x", value.get("intended_x", 0)), "current"),
        current_y=_finite(value.get("current_y", value.get("intended_y", 0)), "current"),
        intent=_choice(value.get("intent", "absolute"), _INTENTS, "intent"),
        axis=axis,
        strictness=strictness,
        writing_mode=writing_mode,
        direction=direction,
    )


def _areas(value: object) -> list[_Area]:
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise _Invalid("areas")
    areas = [_area(item, index) for index, item in enumerate(value)]
    ids = [area.id for area in areas]
    if len(ids) != len(set(ids)):
        raise _Invalid("id")
    by_id = {area.id: area for area in areas}
    for area in areas:
        if area.parent is None:
            continue
        if area.parent not in by_id:
            raise _Invalid("parent")
        seen = {area.id}
        current = area.parent
        while current:
            if current in seen:
                raise _Invalid("parent")
            seen.add(current)
            parent = by_id[current]
            current = parent.parent
    return areas


def _area(value: object, order: int) -> _Area:
    if not isinstance(value, Mapping):
        raise _Invalid("area")
    if set(value) - _AREA_FIELDS:
        raise _Invalid("area")
    identity = value.get("id")
    if not isinstance(identity, str) or not identity.strip():
        raise _Invalid("id")
    align_block, align_inline = _align_fields(value)
    writing_mode = value.get("writing_mode")
    if writing_mode is not None:
        writing_mode = _choice(writing_mode, _MODES, "writing-mode")
    direction = value.get("direction")
    if direction is not None:
        direction = _choice(direction, _DIRECTIONS, "direction")
    parent = value.get("parent")
    if parent is not None and (not isinstance(parent, str) or not parent.strip()):
        raise _Invalid("parent")
    width = _nonnegative(value.get("width"), "area")
    height = _nonnegative(value.get("height"), "area")
    return _Area(
        id=identity,
        x=_finite(value.get("x"), "area"),
        y=_finite(value.get("y"), "area"),
        width=width,
        height=height,
        margin_left=_finite(value.get("margin_left", 0), "scroll-margin"),
        margin_right=_finite(value.get("margin_right", 0), "scroll-margin"),
        margin_top=_finite(value.get("margin_top", 0), "scroll-margin"),
        margin_bottom=_finite(value.get("margin_bottom", 0), "scroll-margin"),
        align_block=align_block,
        align_inline=align_inline,
        snap_stop=_choice(value.get("snap_stop", "normal"), _STOPS, "snap-stop"),
        writing_mode=writing_mode,
        direction=direction,
        focused=_flag(value.get("focused", False), "focused"),
        targeted=_flag(value.get("targeted", False), "targeted"),
        parent=parent,
        order=order,
    )


def _align_fields(value: Mapping[str, object]) -> tuple[str, str]:
    if "align" in value:
        block, inline = _align_pair(value.get("align"))
    else:
        block, inline = "none", "none"
    if "align_block" in value:
        block = _choice(value.get("align_block"), _ALIGNS, "align")
    if "align_inline" in value:
        inline = _choice(value.get("align_inline"), _ALIGNS, "align")
    return block, inline


def _align_pair(value: object) -> tuple[str, str]:
    if not isinstance(value, str):
        raise _Invalid("align")
    parts = value.lower().split()
    if len(parts) == 1 and parts[0] in _ALIGNS:
        return parts[0], parts[0]
    if len(parts) == 2 and parts[0] in _ALIGNS and parts[1] in _ALIGNS:
        return parts[0], parts[1]
    raise _Invalid("align")


def _snap_type(value: object) -> tuple[str, str]:
    if not isinstance(value, str) or not value.strip():
        raise _Invalid("snap-type")
    parts = value.lower().split()
    if parts == ["none"]:
        return "none", "proximity"
    if len(parts) == 1:
        axis, strictness = parts[0], "proximity"
    elif len(parts) == 2:
        axis, strictness = parts
    else:
        raise _Invalid("snap-type")
    if axis not in _AXES or strictness not in _STRICT:
        raise _Invalid("snap-type")
    return axis, strictness


def _padding(value: object) -> float:
    if value == "auto":
        return 0.0
    number = _finite(value, "scroll-padding")
    if number < 0:
        raise _Invalid("scroll-padding")
    return number


def _positive(value: object, name: str) -> float:
    number = _finite(value, name)
    if number <= 0:
        raise _Invalid(name)
    return number


def _nonnegative(value: object, name: str) -> float:
    number = _finite(value, name)
    if number < 0:
        raise _Invalid(name)
    return number


def _finite(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _Invalid(name)
    number = float(value)
    if not math.isfinite(number):
        raise _Invalid(name)
    return number


def _choice(value: object, allowed: frozenset[str], name: str) -> str:
    if not isinstance(value, str) or value.lower() not in allowed:
        raise _Invalid(name)
    return value.lower()


def _flag(value: object, name: str) -> bool:
    if not isinstance(value, bool):
        raise _Invalid(name)
    return value


def _number(value: float) -> int | float:
    rounded = round(value)
    if abs(value - rounded) <= _EPS:
        return int(rounded)
    return value


def _invalid(reason: str) -> dict[str, object]:
    return {
        "outcome": "invalid",
        "x": None,
        "y": None,
        "snapped_inline": None,
        "snapped_block": None,
        "reason": reason,
    }
