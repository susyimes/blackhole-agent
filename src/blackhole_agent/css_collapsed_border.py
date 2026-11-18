"""Choose the used border where collapsed CSS table borders meet.

CSS 2.2 §17.6.2.1 looks at every element that paints the same grid edge:
the table, a column group, a column, a row group, a row, and the cells.
``hidden`` prevents every other style and leaves the edge with no width.
``none`` loses to any other style, including a zero-width solid. A wider
border then beats a narrower one, before style is considered, so a wide
dotted border beats a narrow double. Equal widths prefer ``double``, then
``solid``, ``dashed``, ``dotted``, ``ridge``, ``outset``, ``groove``, and
``inset``. Equal width and style prefer a cell over a row, a row group, a
column, a column group, and the table. Two contributors of the same kind
prefer the one further toward the top, then the one further toward the
start side: left when direction is ``ltr``, right when it is ``rtl``.
"""

from __future__ import annotations

_STYLES = ("double", "solid", "dashed", "dotted", "ridge", "outset", "groove", "inset")
_STYLE_RANK = {name: len(_STYLES) - index for index, name in enumerate(_STYLES)}
_SOURCES = ("cell", "row", "row-group", "column", "column-group", "table")
_SOURCE_RANK = {name: index for index, name in enumerate(_SOURCES)}
_FIELDS = frozenset({"source", "style", "width", "color", "row", "column"})
_NONE = "none"
_HIDDEN = "hidden"


class _Invalid(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def resolve_collapsed_border(borders: object, *, direction: object = "ltr") -> dict[str, object]:
    """Return the one border that wins at a shared collapsed edge.

    Each contributor maps ``source``, ``style``, ``width``, ``color``,
    ``row``, and ``column``. ``source`` is ``cell``, ``row``, ``row-group``,
    ``column``, ``column-group``, or ``table``. ``style`` is a CSS border
    style. ``width`` is a non-negative length. ``row`` and ``column`` are
    the contributor's position, with smaller numbers further toward the top
    and the left. ``direction`` is ``ltr`` or ``rtl``.
    """

    try:
        inline = _direction(direction)
        parsed = _borders(borders)
    except _Invalid as exc:
        return _invalid(exc.reason)

    hidden = [item for item in parsed if item["style"] == _HIDDEN]
    if hidden:
        winner = _prefer(hidden, inline)
        return _resolved(winner, width=0, suppressed=True)
    visible = [item for item in parsed if item["style"] != _NONE]
    if not visible:
        return _resolved(_prefer(parsed, inline), width=0, suppressed=False)

    widest = max(float(item["width"]) for item in visible)
    pool = [item for item in visible if float(item["width"]) == widest]
    best_style = max(int(item["style_rank"]) for item in pool)
    pool = [item for item in pool if int(item["style_rank"]) == best_style]
    winner = _prefer(pool, inline)
    return _resolved(winner, width=float(winner["width"]), suppressed=False)


def _prefer(items: list[dict[str, object]], direction: str) -> dict[str, object]:
    return min(items, key=lambda item: _key(item, direction))


def _key(item: dict[str, object], direction: str) -> tuple[int, int, int, int]:
    column = int(item["column"])
    if direction == "rtl":
        column = -column
    return (int(item["source_rank"]), int(item["row"]), column, int(item["index"]))


def _resolved(winner: dict[str, object], *, width: float, suppressed: bool) -> dict[str, object]:
    return {
        "outcome": "resolved",
        "style": winner["style"],
        "width": _number(width),
        "color": winner["color"],
        "source": winner["source"],
        "suppressed": suppressed,
    }


def _invalid(reason: str) -> dict[str, object]:
    return {
        "outcome": "invalid",
        "reason": reason,
        "style": None,
        "width": None,
        "color": None,
        "source": None,
        "suppressed": None,
    }


def _borders(value: object) -> list[dict[str, object]]:
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise _Invalid("borders must be a list")
    if not value:
        raise _Invalid("borders must not be empty")
    return [_border(raw, index) for index, raw in enumerate(value)]


def _border(raw: object, index: int) -> dict[str, object]:
    if not isinstance(raw, dict):
        raise _Invalid(f"border {index} must be a mapping")
    unknown = set(raw) - _FIELDS
    if unknown:
        raise _Invalid(f"border {index} has an unknown field")
    missing = _FIELDS - set(raw)
    if missing:
        raise _Invalid(f"border {index} is missing a field")
    source = _token(raw["source"], _SOURCE_RANK, f"border {index} source")
    style = _style(raw["style"], index)
    return {
        "index": index,
        "source": source,
        "source_rank": _SOURCE_RANK[source],
        "style": style,
        "style_rank": _STYLE_RANK.get(style, 0),
        "width": _width(raw["width"], index),
        "color": _color(raw["color"], index),
        "row": _coordinate(raw["row"], f"border {index} row"),
        "column": _coordinate(raw["column"], f"border {index} column"),
    }


def _style(value: object, index: int) -> str:
    if not isinstance(value, str):
        raise _Invalid(f"border {index} style is invalid")
    style = _normalize(value)
    if style not in _STYLE_RANK and style not in {_NONE, _HIDDEN}:
        raise _Invalid(f"border {index} style is invalid")
    return style


def _width(value: object, index: int) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _Invalid(f"border {index} width is invalid")
    number = float(value)
    if number != number or number in {float("inf"), float("-inf")} or number < 0:
        raise _Invalid(f"border {index} width is invalid")
    return number


def _color(value: object, index: int) -> str:
    if not isinstance(value, str):
        raise _Invalid(f"border {index} color is invalid")
    return " ".join(value.split())


def _coordinate(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise _Invalid(f"{name} is invalid")
    return value


def _direction(value: object) -> str:
    if not isinstance(value, str):
        raise _Invalid("direction is invalid")
    direction = value.strip().lower()
    if direction not in {"ltr", "rtl"}:
        raise _Invalid("direction is invalid")
    return direction


def _token(value: object, allowed: dict[str, int], name: str) -> str:
    if not isinstance(value, str):
        raise _Invalid(f"{name} is invalid")
    token = _normalize(value)
    if token not in allowed:
        raise _Invalid(f"{name} is invalid")
    return token


def _normalize(value: str) -> str:
    return "-".join(value.strip().lower().split())


def _number(value: float) -> int | float:
    nearest = round(value)
    if abs(value - nearest) <= 1e-9:
        return int(nearest)
    return value
