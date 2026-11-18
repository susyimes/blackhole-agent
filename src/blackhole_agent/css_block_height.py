"""Used content height of one in-flow non-replaced block.

CSS 2.1 §10.6.3 ends an automatic height at the last in-flow edge that stays
inside the parent. A bottom margin that collapses out is not part of that
height. §10.6.7 then extends a block formatting context to the bottom margin
edge of a participating float. A visible overflow block does not. A specified
height replaces both results. min-height and max-height clamp afterwards, and
the minimum wins when they disagree.

A percentage resolves against a definite containing-block height. An automatic
containing height turns a percentage height into auto, a percentage min-height
into zero, and a percentage max-height into none. A border-box length includes
vertical padding and border; the content box floors at zero. An automatic box
with no in-flow child uses the caller's line-box bottom. This does not place
floats or solve an absolutely positioned box.
"""

from __future__ import annotations

from blackhole_agent.css_margin_collapse import place_collapsed_margins

_AUTO = "auto"
_NONE = "none"
_CONTENT = "content-box"
_BORDER = "border-box"
_EXTRAS = frozenset({"box_sizing", "line_bottom", "max_height"})
_OVERFLOWS = frozenset({"visible", "hidden", "auto", "scroll", "clip"})
_FLOATS = frozenset({"none", "left", "right"})
_DISPLAYS = frozenset({"block", "inline-block"})
_POSITIONS = frozenset({"static", "relative", "absolute", "fixed"})


class _Invalid(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def used_block_height(
    box: object,
    *,
    containing_height: object = _AUTO,
    floats: object = (),
) -> dict[str, object]:
    """Return the used content height and border-box height.

    ``containing_height`` is a definite length or ``auto``. ``floats`` lists
    the participating floats' bottom margin edges, measured from this box's
    content top. Those edges extend the height only when this box forms a
    block formatting context. ``line_bottom`` is the bottom of the last line
    box and is valid only when the box has no in-flow block children.
    """

    try:
        spec = _box(box)
        containing = _containing(containing_height)
        bottoms = _float_bottoms(floats)
        height = _resolve(spec["height"], containing, indefinite=_AUTO)
        minimum = _resolve(spec["minimum"], containing, indefinite=0.0)
        if minimum == _AUTO:
            minimum = 0.0
        maximum = _resolve(spec["maximum"], containing, indefinite=_NONE)
        if spec["line_bottom"] is not None and spec["children"]:
            raise _Invalid("line box")
        in_flow = _in_flow(spec["probe"])
        if spec["line_bottom"] is not None:
            in_flow = spec["line_bottom"]
    except _Invalid as exc:
        return _invalid(exc.reason)

    if height == _AUTO:
        content = float(in_flow)
        if spec["bfc"] and bottoms:
            content = max(content, max(bottoms))
    else:
        content = _content_length(float(height), spec["chrome"], spec["sizing"])
    if maximum != _NONE:
        cap = _content_length(float(maximum), spec["chrome"], spec["sizing"])
        if content > cap:
            content = cap
    floor = _content_length(float(minimum), spec["chrome"], spec["sizing"])
    if content < floor:
        content = floor
    return {
        "outcome": "sized",
        "reason": None,
        "content_height": _number(content),
        "border_box": _number(content + spec["chrome"]),
    }


def _box(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise _Invalid("box")
    position = _choice(value, "position", _POSITIONS, "static")
    if position in {"absolute", "fixed"}:
        raise _Invalid("position")
    overflow = _choice(value, "overflow", _OVERFLOWS, "visible")
    side = _choice(value, "float", _FLOATS, "none")
    display = _choice(value, "display", _DISPLAYS, "block")
    sizing = _choice(value, "box_sizing", {_CONTENT, _BORDER}, _CONTENT)
    children = value.get("children", [])
    if not isinstance(children, list):
        raise _Invalid("children")
    chrome = (
        _gap(value, "padding_top")
        + _gap(value, "padding_bottom")
        + _gap(value, "border_top")
        + _gap(value, "border_bottom")
    )
    probe = {key: item for key, item in value.items() if key not in _EXTRAS}
    probe["height"] = _AUTO
    probe["min_height"] = 0
    return {
        "height": _axis(value.get("height", _AUTO), allow_auto=True, name="height"),
        "minimum": _axis(value.get("min_height", 0), allow_auto=True, name="min-height"),
        "maximum": _axis(value.get("max_height", _NONE), allow_none=True, name="max-height"),
        "line_bottom": _line_bottom(value),
        "children": children,
        "chrome": chrome,
        "sizing": sizing,
        "bfc": overflow != "visible" or side != "none" or display == "inline-block",
        "probe": probe,
    }


def _in_flow(probe: dict[str, object]) -> int:
    placed = place_collapsed_margins(probe)
    if placed.get("outcome") != "placed":
        raise _Invalid(str(placed.get("reason") or "layout"))
    boxes = placed.get("boxes")
    if not isinstance(boxes, list) or not boxes or not isinstance(boxes[0], dict):
        raise _Invalid("layout")
    border_height = boxes[0].get("border_height")
    if type(border_height) is not int:
        raise _Invalid("layout")
    chrome = (
        _gap(probe, "padding_top")
        + _gap(probe, "padding_bottom")
        + _gap(probe, "border_top")
        + _gap(probe, "border_bottom")
    )
    return border_height - chrome


def _float_bottoms(value: object) -> list[float]:
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise _Invalid("floats")
    bottoms: list[float] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict) or set(item) != {"bottom"}:
            raise _Invalid(f"float {index}")
        bottom = item["bottom"]
        if isinstance(bottom, bool) or not isinstance(bottom, (int, float)) or bottom < 0:
            raise _Invalid(f"float {index}")
        bottoms.append(float(bottom))
    return bottoms


def _containing(value: object) -> float | None:
    if value == _AUTO:
        return None
    if isinstance(value, str) and value.strip().lower() == _AUTO:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise _Invalid("containing height")
    return float(value)


def _resolve(spec: tuple[str, float], containing: float | None, *, indefinite: float | str) -> float | str:
    kind, number = spec
    if kind in {_AUTO, _NONE}:
        return kind
    if kind == "%":
        if containing is None:
            return indefinite
        return containing * number / 100.0
    return number


def _content_length(size: float, chrome: int, sizing: str) -> float:
    if sizing == _BORDER:
        return max(0.0, size - chrome)
    return size


def _axis(value: object, *, allow_auto: bool = False, allow_none: bool = False, name: str) -> tuple[str, float]:
    if isinstance(value, bool):
        raise _Invalid(name)
    if isinstance(value, (int, float)):
        if value < 0:
            raise _Invalid(name)
        return ("px", float(value))
    if not isinstance(value, str):
        raise _Invalid(name)
    text = value.strip().lower()
    if allow_auto and text == _AUTO:
        return (_AUTO, 0.0)
    if allow_none and text == _NONE:
        return (_NONE, 0.0)
    if text.endswith("%"):
        try:
            number = float(text[:-1])
        except ValueError as exc:
            raise _Invalid(name) from exc
        if number < 0:
            raise _Invalid(name)
        return ("%", number)
    if text.endswith("px"):
        try:
            number = float(text[:-2])
        except ValueError as exc:
            raise _Invalid(name) from exc
        if number < 0:
            raise _Invalid(name)
        return ("px", number)
    raise _Invalid(name)


def _line_bottom(box: dict[str, object]) -> int | None:
    if "line_bottom" not in box:
        return None
    value = box["line_bottom"]
    if type(value) is not int or value < 0:
        raise _Invalid("line box")
    return value


def _gap(box: object, name: str) -> int:
    if not isinstance(box, dict):
        raise _Invalid(name)
    value = box.get(name, 0)
    if type(value) is not int or value < 0:
        raise _Invalid(name)
    return value


def _choice(box: dict[str, object], name: str, allowed: set[str] | frozenset[str], default: str) -> str:
    value = box.get(name, default)
    if not isinstance(value, str) or value not in allowed:
        raise _Invalid(name)
    return value


def _number(value: float) -> int | float:
    return int(value) if value.is_integer() else value


def _invalid(reason: str) -> dict[str, object]:
    return {"outcome": "invalid", "reason": reason, "content_height": None, "border_box": None}
