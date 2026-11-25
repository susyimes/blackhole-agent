"""Map CSS logical box properties onto physical edges and solve the inline size.

CSS Logical Properties Level 1. Declarations are already in cascade order.
A logical longhand and the physical longhand that names the same side in
this writing mode compete, and the later declaration wins. The other sides
stay as they were. ``text-orientation: upright`` forces the used direction
to ``ltr`` in a vertical writing mode before that mapping.

The inline-size equation is CSS 2.1 §10.3.3 on the inline axis, not on
physical width. In ``vertical-rl`` that axis is height, so an automatic
inline margin splits the top and bottom edges. An over-constrained line
recomputes the inline-end margin. A definite ``max-inline-size`` restarts
the same equation. Block-axis automatic margins used-value to zero, as an
automatic vertical margin does for a normal block. An automatic block size
stays automatic because it depends on content. ``content_min_height`` and
``content_max_height`` are still resolved for a horizontal physical height,
so a caller can clamp after that content is measured. A percentage with an
indefinite containing height becomes zero for the minimum and stays absent
for the maximum.

Percentage margins and padding use ``percentage_basis`` (the containing
block's physical width). Inline-size percentages use ``containing_inline``.
Block-size percentages use ``containing_block``. Inset percentages are
rejected. A used border width is zero when its style is ``none`` or
``hidden``; otherwise ``thin``, ``medium``, and ``thick`` are 1px, 3px, and
5px. An omitted width next to a visible style is medium.
"""

from __future__ import annotations

from blackhole_agent.css_anchor_query import parse_anchor_size_call
from blackhole_agent.css_block_width import used_block_width
from blackhole_agent.css_length_math import is_length_math, resolve_length_math
from blackhole_agent.css_writing_mode import resolve_writing_mode

_SIDES = ("top", "right", "bottom", "left")
_EDGE_SUFFIX = (
    ("inline_start", "inline-start"),
    ("inline_end", "inline-end"),
    ("block_start", "block-start"),
    ("block_end", "block-end"),
)
_STYLES = frozenset({"none", "hidden", "dotted", "dashed", "solid", "double", "groove", "ridge", "inset", "outset"})
_LINE_WIDTH = {"thin": 1.0, "medium": 3.0, "thick": 5.0}
_HIDDEN_STYLES = frozenset({"none", "hidden"})


class _Invalid(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def _logical_edges() -> dict[str, tuple[str, str]]:
    table: dict[str, tuple[str, str]] = {}
    for edge, suffix in _EDGE_SUFFIX:
        table[f"margin-{suffix}"] = ("margin", edge)
        table[f"padding-{suffix}"] = ("padding", edge)
        table[f"border-{suffix}-width"] = ("border-width", edge)
        table[f"border-{suffix}-style"] = ("border-style", edge)
        table[f"inset-{suffix}"] = ("inset", edge)
    return table


def _size_words() -> dict[str, tuple[str, str]]:
    table: dict[str, tuple[str, str]] = {}
    for kind, prefix in (("size", ""), ("min", "min-"), ("max", "max-")):
        table[f"{prefix}inline-size"] = (kind, "inline")
        table[f"{prefix}block-size"] = (kind, "block")
    return table


_LOGICAL = _logical_edges()
_SIZES = _size_words()
_PHYSICAL_SHORTHAND = {
    "margin": "margin",
    "padding": "padding",
    "border-width": "border-width",
    "border-style": "border-style",
    "inset": "inset",
}
_LOGICAL_SHORTHAND = {}
for _family, _axis in (
    ("margin", "margin"),
    ("padding", "padding"),
    ("inset", "inset"),
):
    _LOGICAL_SHORTHAND[f"{_family}-inline"] = (f"{_family}-inline-start", f"{_family}-inline-end")
    _LOGICAL_SHORTHAND[f"{_family}-block"] = (f"{_family}-block-start", f"{_family}-block-end")
_LOGICAL_SHORTHAND["border-inline-width"] = ("border-inline-start-width", "border-inline-end-width")
_LOGICAL_SHORTHAND["border-block-width"] = ("border-block-start-width", "border-block-end-width")
_LOGICAL_SHORTHAND["border-inline-style"] = ("border-inline-start-style", "border-inline-end-style")
_LOGICAL_SHORTHAND["border-block-style"] = ("border-block-start-style", "border-block-end-style")


def _physical_names() -> dict[str, str]:
    names: dict[str, str] = {
        "width": "width",
        "height": "height",
        "min-width": "min-width",
        "min-height": "min-height",
        "max-width": "max-width",
        "max-height": "max-height",
        "box-sizing": "box-sizing",
    }
    for side in _SIDES:
        names[f"margin-{side}"] = f"margin-{side}"
        names[f"padding-{side}"] = f"padding-{side}"
        names[f"border-{side}-width"] = f"border-{side}-width"
        names[f"border-{side}-style"] = f"border-{side}-style"
        names[side] = f"inset-{side}"
    return names


_PHYSICAL = _physical_names()


def resolve_logical_box(
    declarations: object,
    *,
    writing_mode: object = "horizontal-tb",
    direction: object = "ltr",
    text_orientation: object = "mixed",
    containing_inline: object,
    percentage_basis: object = None,
    containing_block: object = None,
) -> dict[str, object]:
    """Return physical used edges for one element.

    ``declarations`` is a sequence of ``(property, value)`` pairs. The last
    pair that maps to a physical side wins. ``containing_inline`` is the
    definite inline measure the margin box must fill. ``percentage_basis``
    defaults to that measure; pass the containing block's physical width
    when a vertical writing mode makes the two differ.
    """

    try:
        flow = resolve_writing_mode(writing_mode, direction, text_orientation=text_orientation)
        if flow.get("outcome") != "resolved":
            raise _Invalid(str(flow.get("reason") or "writing-mode is invalid"))
        inline_size = _finite_input(containing_inline, "containing inline size")
        basis = inline_size if percentage_basis is None else _finite_input(percentage_basis, "percentage basis")
        block_basis = None if containing_block is None else _finite_input(containing_block, "containing block")
        slots = _cascade(declarations, flow)
        box_sizing = _keyword(slots.get("box-sizing", "content-box"), {"content-box", "border-box"}, "box-sizing")
        solved = _solve(flow, slots, inline_size, basis, block_basis, box_sizing)
    except _Invalid as exc:
        return _invalid(exc.reason)
    solved["writing_mode"] = flow["writing_mode"]
    solved["direction"] = flow["direction"]
    solved["specified_direction"] = flow["specified_direction"]
    solved["text_orientation"] = flow["text_orientation"]
    solved["box_sizing"] = box_sizing
    solved["outcome"] = "resolved"
    solved["reason"] = None
    return solved


def _invalid(reason: str) -> dict[str, object]:
    payload: dict[str, object] = {"outcome": "invalid", "reason": reason}
    for side in _SIDES:
        payload[f"margin_{side}"] = None
        payload[f"padding_{side}"] = None
        payload[f"border_{side}"] = None
        payload[f"inset_{side}"] = None
    payload.update(
        {
            "content_width": None,
            "content_height": None,
            "inline_content": None,
            "inline_margin_start": None,
            "inline_margin_end": None,
            "specified_width": None,
            "specified_height": None,
            "writing_mode": None,
            "direction": None,
            "specified_direction": None,
            "text_orientation": None,
            "box_sizing": None,
        }
    )
    return payload


def _finite_input(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _Invalid(f"{name} is invalid")
    number = float(value)
    if number < 0.0 or number != number or number in (float("inf"), float("-inf")):
        raise _Invalid(f"{name} is invalid")
    return number


def _keyword(value: str, allowed: set[str], name: str) -> str:
    token = value.strip().lower()
    if token not in allowed:
        raise _Invalid(f"{name} is invalid")
    return token


def _cascade(declarations: object, flow: dict[str, object]) -> dict[str, str]:
    if isinstance(declarations, (str, bytes)) or not isinstance(declarations, (list, tuple)):
        raise _Invalid("declarations are invalid")
    slots: dict[str, str] = {}
    horizontal = flow.get("horizontal") is True
    for item in declarations:
        if not isinstance(item, (list, tuple)) or len(item) != 2 or not isinstance(item[0], str):
            raise _Invalid("declarations are invalid")
        prop = item[0].strip().lower()
        if not isinstance(item[1], str) or not prop or "!important" in item[1].lower():
            raise _Invalid("property is invalid")
        value = " ".join(item[1].split()).lower()
        if not value:
            raise _Invalid("property is invalid")
        for longhand, component in _expand(prop, value):
            _check_component(longhand, component)
            slots[_slot(longhand, flow, horizontal)] = component
    return slots


def _expand(prop: str, value: str) -> list[tuple[str, str]]:
    parts = _split_values(value)
    if not parts:
        raise _Invalid("property is invalid")
    if prop in _LOGICAL_SHORTHAND:
        if len(parts) == 1:
            parts = [parts[0], parts[0]]
        elif len(parts) != 2:
            raise _Invalid(f"{prop} is invalid")
        start, end = _LOGICAL_SHORTHAND[prop]
        return [(start, parts[0]), (end, parts[1])]
    if prop in _PHYSICAL_SHORTHAND:
        if len(parts) == 1:
            chosen = (parts[0], parts[0], parts[0], parts[0])
        elif len(parts) == 2:
            chosen = (parts[0], parts[1], parts[0], parts[1])
        elif len(parts) == 3:
            chosen = (parts[0], parts[1], parts[2], parts[1])
        elif len(parts) == 4:
            chosen = (parts[0], parts[1], parts[2], parts[3])
        else:
            raise _Invalid(f"{prop} is invalid")
        family = _PHYSICAL_SHORTHAND[prop]
        return [(_physical_longhand(family, side), component) for side, component in zip(_SIDES, chosen, strict=True)]
    if prop in _LOGICAL or prop in _SIZES or prop in _PHYSICAL:
        if len(parts) != 1:
            raise _Invalid("property is invalid")
        return [(prop, parts[0])]
    raise _Invalid("property is invalid")


def _physical_longhand(family: str, side: str) -> str:
    if family == "inset":
        return side
    if family == "border-width":
        return f"border-{side}-width"
    if family == "border-style":
        return f"border-{side}-style"
    return f"{family}-{side}"


def _split_values(value: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    for char in value:
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth < 0:
                raise _Invalid("property is invalid")
        if char in " \t\n\r\f" and depth == 0:
            if buf:
                parts.append("".join(buf))
                buf = []
            continue
        buf.append(char)
    if depth != 0:
        raise _Invalid("property is invalid")
    if buf:
        parts.append("".join(buf))
    return parts


def _check_component(longhand: str, value: str) -> None:
    family = _family(longhand)
    if family == "border-style":
        _keyword(value, set(_STYLES), "border style")
        return
    if family == "border-width":
        if value.lower() in _LINE_WIDTH:
            return
        _parse_length(value, negative=False, percent=False, name="border width")
        return
    if family == "box-sizing":
        _keyword(value, {"content-box", "border-box"}, "box-sizing")
        return
    if family == "inset":
        if value.lower() == "auto":
            return
        _parse_length(value, negative=True, percent=False, name="inset")
        return
    if family == "margin":
        if value.lower() == "auto":
            return
        _parse_length(value, negative=True, percent=True, name="margin")
        return
    if family == "padding":
        _parse_length(value, negative=False, percent=True, name="padding")
        return
    if family in {"size", "min"}:
        if value.lower() == "auto":
            return
        if _anchor_size_component(value):
            return
        _parse_length(value, negative=False, percent=True, name="size")
        return
    if family == "max":
        if value.lower() == "none":
            return
        if _anchor_size_component(value):
            return
        _parse_length(value, negative=False, percent=True, name="size")
        return
    raise _Invalid("property is invalid")


def _anchor_size_component(value: str) -> bool:
    parsed = parse_anchor_size_call(value)
    if parsed.get("outcome") == "absent":
        return False
    if parsed.get("outcome") != "parsed":
        raise _Invalid(str(parsed.get("reason") or "anchor-size is invalid"))
    return True


def _family(longhand: str) -> str:
    if longhand in _SIZES:
        return _SIZES[longhand][0]
    if longhand in _LOGICAL:
        return _LOGICAL[longhand][0]
    if longhand == "box-sizing":
        return "box-sizing"
    if longhand in {"width", "height"}:
        return "size"
    if longhand in {"min-width", "min-height"}:
        return "min"
    if longhand in {"max-width", "max-height"}:
        return "max"
    if longhand.startswith("margin-"):
        return "margin"
    if longhand.startswith("padding-"):
        return "padding"
    if longhand.startswith("border-") and longhand.endswith("-style"):
        return "border-style"
    if longhand.startswith("border-") and longhand.endswith("-width"):
        return "border-width"
    if longhand in _SIDES:
        return "inset"
    raise _Invalid("property is invalid")


def _parse_length(value: str, *, negative: bool, percent: bool, name: str) -> None:
    if is_length_math(value):
        return
    text = value.strip().lower()
    unit = ""
    if text.endswith("%"):
        unit = "%"
        text = text[:-1]
    elif text.endswith("px"):
        unit = "px"
        text = text[:-2]
    else:
        raise _Invalid(f"{name} is invalid")
    if unit == "%" and not percent:
        raise _Invalid(f"{name} is invalid")
    try:
        number = float(text)
    except ValueError as exc:
        raise _Invalid(f"{name} is invalid") from exc
    if number != number or number in (float("inf"), float("-inf")):
        raise _Invalid(f"{name} is invalid")
    if number < 0.0 and not negative:
        raise _Invalid(f"{name} is invalid")


def _slot(longhand: str, flow: dict[str, object], horizontal: bool) -> str:
    if longhand in _LOGICAL:
        family, edge = _LOGICAL[longhand]
        side = flow.get(edge)
        if not isinstance(side, str):
            raise _Invalid("writing-mode is invalid")
        return _slot_name(family, side)
    if longhand in _SIZES:
        kind, axis = _SIZES[longhand]
        physical = "width" if (axis == "inline") == horizontal else "height"
        if kind == "size":
            return physical
        return f"{kind}-{physical}"
    slot = _PHYSICAL.get(longhand)
    if slot is None:
        raise _Invalid("property is invalid")
    return slot


def _slot_name(family: str, side: str) -> str:
    if family == "inset":
        return f"inset-{side}"
    if family == "border-width":
        return f"border-{side}-width"
    if family == "border-style":
        return f"border-{side}-style"
    return f"{family}-{side}"


def _solve(
    flow: dict[str, object],
    slots: dict[str, str],
    containing_inline: float,
    percentage_basis: float,
    containing_block: float | None,
    box_sizing: str,
) -> dict[str, object]:
    horizontal = flow.get("horizontal") is True
    start = str(flow["inline_start"])
    end = str(flow["inline_end"])
    block_start = str(flow["block_start"])
    block_end = str(flow["block_end"])
    inline_axis = "width" if horizontal else "height"
    block_axis = "height" if horizontal else "width"

    def used_border(side: str) -> float:
        style = slots.get(f"border-{side}-style", "none")
        width = slots.get(f"border-{side}-width")
        if width is not None and width.lower() not in _LINE_WIDTH:
            _length(width, percentage_basis, negative=False, percent=False, name="border width")
        if style in _HIDDEN_STYLES:
            return 0.0
        if width is None or width.lower() == "medium":
            return 3.0
        if width.lower() in _LINE_WIDTH:
            return _LINE_WIDTH[width.lower()]
        return _length(width, percentage_basis, negative=False, percent=False, name="border width")

    borders = {side: used_border(side) for side in _SIDES}
    padding = {
        side: _length(slots.get(f"padding-{side}", "0px"), percentage_basis, negative=False, percent=True, name="padding")
        for side in _SIDES
    }
    block_margins = {
        side: _block_margin(slots.get(f"margin-{side}", "0px"), percentage_basis)
        for side in (block_start, block_end)
    }
    equation = used_block_width(
        containing_inline,
        width=_equation_size(slots.get(inline_axis, "auto"), containing_inline),
        margin_left=_equation_margin(slots.get(f"margin-{start}", "0px"), percentage_basis),
        margin_right=_equation_margin(slots.get(f"margin-{end}", "0px"), percentage_basis),
        padding_left=padding[start],
        padding_right=padding[end],
        border_left=borders[start],
        border_right=borders[end],
        box_sizing=box_sizing,
        min_width=_equation_limit(slots.get(f"min-{inline_axis}", "auto"), containing_inline, allow_auto=True),
        max_width=_equation_limit(slots.get(f"max-{inline_axis}", "none"), containing_inline, allow_auto=False),
        direction="ltr",
    )
    if equation.get("outcome") != "sized":
        raise _Invalid(str(equation.get("reason") or "size is invalid"))

    margins = {
        start: equation["margin_left"],
        end: equation["margin_right"],
        block_start: block_margins[block_start],
        block_end: block_margins[block_end],
    }
    block_chrome = padding[block_start] + padding[block_end] + borders[block_start] + borders[block_end]
    block_content = _block_content(slots, block_axis, box_sizing, block_chrome, containing_block)
    inline_content = equation["content"]
    content_width = inline_content if horizontal else block_content
    content_height = block_content if horizontal else inline_content
    if horizontal:
        height_chrome = padding["top"] + padding["bottom"] + borders["top"] + borders["bottom"]
        content_min = _content_box_limit(
            _optional_axis(slots.get("min-height", "auto"), containing_block, indefinite_percentage=0.0),
            box_sizing,
            height_chrome,
        )
        content_max = _content_box_limit(
            _optional_axis(slots.get("max-height", "none"), containing_block, indefinite_percentage=None),
            box_sizing,
            height_chrome,
        )
    else:
        content_min = None
        content_max = None
    payload: dict[str, object] = {
        "content_width": content_width,
        "content_height": content_height,
        "content_min_height": None if content_min is None else _number(content_min),
        "content_max_height": None if content_max is None else _number(content_max),
        "inline_content": inline_content,
        "inline_margin_start": equation["margin_left"],
        "inline_margin_end": equation["margin_right"],
        "specified_width": slots.get("width", "auto"),
        "specified_height": slots.get("height", "auto"),
    }
    for side in _SIDES:
        payload[f"margin_{side}"] = margins[side]
        payload[f"padding_{side}"] = _number(padding[side])
        payload[f"border_{side}"] = _number(borders[side])
        payload[f"inset_{side}"] = _inset(slots.get(f"inset-{side}", "auto"))
    return payload


def _block_margin(raw: str, basis: float) -> int | float:
    if raw.lower() == "auto":
        return 0
    return _number(_length(raw, basis, negative=True, percent=True, name="margin"))


def _equation_margin(raw: str, basis: float) -> object:
    if raw.lower() == "auto":
        return "auto"
    return _length(raw, basis, negative=True, percent=True, name="margin")


def _equation_size(raw: str, basis: float) -> object:
    if raw.lower() == "auto":
        return "auto"
    return _length(raw, basis, negative=False, percent=True, name="size")


def _equation_limit(raw: str, basis: float, *, allow_auto: bool) -> object:
    token = raw.lower()
    if allow_auto and token == "auto":
        return "auto"
    if token == "none":
        return "none"
    return _length(raw, basis, negative=False, percent=True, name="size")


def _block_content(
    slots: dict[str, str],
    axis: str,
    box_sizing: str,
    chrome: float,
    containing_block: float | None,
) -> object:
    specified = _axis_length(slots.get(axis, "auto"), containing_block, allow_auto=True, allow_none=False)
    if specified is None:
        return "auto"
    minimum = _axis_length(slots.get(f"min-{axis}", "auto"), containing_block, allow_auto=True, allow_none=False)
    maximum = _axis_length(slots.get(f"max-{axis}", "none"), containing_block, allow_auto=False, allow_none=True)
    size = specified
    if maximum is not None and size > maximum:
        size = maximum
    if minimum is not None and size < minimum:
        size = minimum
    if box_sizing == "border-box":
        size = max(0.0, size - chrome)
    return _number(size)


def _optional_axis(raw: str, containing: float | None, *, indefinite_percentage: float | None) -> float | None:
    """Resolve one min or max length. An indefinite percentage uses the sentinel."""

    if _needs_basis(raw) and containing is None:
        token = raw.strip().lower()
        if token in {"auto", "none"}:
            return None
        return indefinite_percentage
    token = raw.strip().lower()
    if token in {"auto", "none"}:
        return None
    basis = 0.0 if containing is None else float(containing)
    return _length(raw, basis, negative=False, percent=containing is not None, name="size")


def _content_box_limit(size: float | None, box_sizing: str, chrome: float) -> float | None:
    if size is None:
        return None
    if box_sizing == "border-box":
        return max(0.0, size - chrome)
    return size


def _axis_length(raw: str, containing_block: float | None, *, allow_auto: bool, allow_none: bool) -> float | None:
    token = raw.lower()
    if allow_auto and token == "auto":
        return None
    if allow_none and token == "none":
        return None
    if _needs_basis(raw) and containing_block is None:
        raise _Invalid("containing block is invalid")
    basis = 0.0 if containing_block is None else containing_block
    return _length(raw, basis, negative=False, percent=containing_block is not None, name="size")


def _needs_basis(raw: str) -> bool:
    text = raw.strip().lower()
    if text.endswith("%"):
        return True
    return is_length_math(raw)


def _inset(raw: str) -> object:
    if raw.lower() == "auto":
        return "auto"
    return _number(_length(raw, 0.0, negative=True, percent=False, name="inset"))


def _length(raw: str, basis: float, *, negative: bool, percent: bool, name: str) -> float:
    if is_length_math(raw):
        solved = resolve_length_math(raw, percentage_basis=basis, allow_percentage=percent)
        if solved.get("outcome") != "resolved":
            raise _Invalid(f"{name} is invalid")
        number = solved.get("px")
        if isinstance(number, bool) or not isinstance(number, (int, float)):
            raise _Invalid(f"{name} is invalid")
        value = float(number)
    else:
        text = raw.strip().lower()
        unit = ""
        if text.endswith("%"):
            unit = "%"
            text = text[:-1]
        elif text.endswith("px"):
            unit = "px"
            text = text[:-2]
        else:
            raise _Invalid(f"{name} is invalid")
        if unit == "%" and not percent:
            raise _Invalid(f"{name} is invalid")
        try:
            value = float(text)
        except ValueError as exc:
            raise _Invalid(f"{name} is invalid") from exc
        if unit == "%":
            value = basis * value / 100.0
    if value != value or value in (float("inf"), float("-inf")):
        raise _Invalid(f"{name} is invalid")
    if value < 0.0 and not negative:
        raise _Invalid(f"{name} is invalid")
    return value


def _number(value: float) -> int | float:
    nearest = round(value)
    if abs(value - nearest) <= 1e-9:
        return int(nearest)
    return value
