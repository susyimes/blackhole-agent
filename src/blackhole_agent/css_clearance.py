"""Signed clearance above one in-flow block.

CSS 2.2 §9.5.2. The hypothetical top edge is where this block's top border
edge would be if ``clear`` were ``none`` and adjoining margins stayed
collapsed. ``place_collapsed_margins`` measures that edge. ``y`` grows
downward from the root's top border edge.

Clearance is introduced only when the hypothetical edge is strictly above
the lowest bottom outer edge of the floats on the sides ``clear`` names.
Introducing it stops those adjoining margins from collapsing. The two
amounts in the specification then agree: the greater of them is the
distance from the separated top edge to that float bottom. The distance is
negative when the separated margins already pass the float, which is the
specification's second example. The used top edge lands on the float bottom.

The caller supplies earlier floats in the same block formatting context.
This does not place those floats. A clearance flag already stored on the
tree is ignored. An empty block that collapses through has no top border
edge to clear.
"""

from __future__ import annotations

from blackhole_agent.css_margin_collapse import place_collapsed_margins

_CLEARS = frozenset({"none", "left", "right", "both"})
_SIDES = frozenset({"left", "right"})


class _Invalid(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def resolve_clearance(
    box: object,
    *,
    element: object,
    clear: object,
    floats: object,
) -> dict[str, object]:
    """Return the signed clearance and the used top edge of ``element``.

    ``clear`` is ``none``, ``left``, ``right``, or ``both``. Each float has
    ``side`` and an integer ``bottom`` in the same coordinate space as the
    margin-collapse edges. Clearance is zero when it is not introduced.
    """

    try:
        target = _element(element)
        sides = _clear(clear)
        bottoms = _floats(floats)
        hypothetical = _edge(_tree(box, target, separate=False), target)
        relevant = [bottom for side, bottom in bottoms if side in sides]
        floor = max(relevant) if relevant else None
        if floor is None or hypothetical >= floor:
            return _resolved(
                introduced=False,
                clearance=0,
                hypothetical=hypothetical,
                separated=None,
                used=hypothetical,
                floor=floor,
            )
        separated = _edge(_tree(box, target, separate=True), target)
        flush = floor - separated
        restore = hypothetical - separated
        clearance = flush if flush >= restore else restore
        return _resolved(
            introduced=True,
            clearance=clearance,
            hypothetical=hypothetical,
            separated=separated,
            used=separated + clearance,
            floor=floor,
        )
    except _Invalid as exc:
        return _invalid(exc.reason)


def _element(value: object) -> str:
    if not isinstance(value, str) or value == "":
        raise _Invalid("element")
    return value


def _clear(value: object) -> frozenset[str]:
    if not isinstance(value, str) or value not in _CLEARS:
        raise _Invalid("clear")
    sides: set[str] = set()
    if value in {"left", "both"}:
        sides.add("left")
    if value in {"right", "both"}:
        sides.add("right")
    return frozenset(sides)


def _floats(value: object) -> list[tuple[str, int]]:
    if not isinstance(value, list):
        raise _Invalid("floats")
    parsed: list[tuple[str, int]] = []
    for item in value:
        if not isinstance(item, dict) or set(item) - {"side", "bottom"}:
            raise _Invalid("float")
        side = item.get("side")
        bottom = item.get("bottom")
        if side not in _SIDES or type(bottom) is not int:
            raise _Invalid("float")
        parsed.append((side, bottom))
    return parsed


def _tree(box: object, element: str, *, separate: bool) -> object:
    if not isinstance(box, dict):
        return box
    copied: dict[str, object] = {}
    for key, value in box.items():
        if key == "clearance":
            continue
        if key == "children" and isinstance(value, list):
            copied[key] = [_tree(child, element, separate=separate) for child in value]
            continue
        copied[key] = value
    if separate and copied.get("id") == element:
        copied["clearance"] = True
    return copied


def _edge(box: object, element: str) -> int:
    placed = place_collapsed_margins(box)
    if placed.get("outcome") != "placed":
        raise _Invalid(str(placed.get("reason") or "margin"))
    boxes = placed.get("boxes")
    if not isinstance(boxes, list):
        raise _Invalid("margin")
    for item in boxes:
        if not isinstance(item, dict) or item.get("id") != element:
            continue
        if item.get("through") is True:
            raise _Invalid("collapsed-through")
        edge = item.get("y")
        if type(edge) is not int:
            raise _Invalid("margin")
        return edge
    raise _Invalid("element")


def _resolved(
    *,
    introduced: bool,
    clearance: int,
    hypothetical: int,
    separated: int | None,
    used: int,
    floor: int | None,
) -> dict[str, object]:
    return {
        "outcome": "resolved",
        "introduced": introduced,
        "clearance": clearance,
        "hypothetical_border": hypothetical,
        "separated_border": separated,
        "used_border": used,
        "float_bottom": floor,
    }


def _invalid(reason: str) -> dict[str, object]:
    return {
        "outcome": "invalid",
        "reason": reason,
        "introduced": None,
        "clearance": None,
        "hypothetical_border": None,
        "separated_border": None,
        "used_border": None,
        "float_bottom": None,
    }
