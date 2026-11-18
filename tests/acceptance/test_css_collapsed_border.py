"""Collapsed CSS table borders pick one winner at a shared edge.

The CSS 2.2 example gives the table 5px solid yellow, column 1 3px solid
black, ordinary cells 1px solid red, cell 5 5px dashed blue, and cell 6
5px solid green. The outer left of cell 1 stays yellow. The edge between
cell 1 and cell 2 stays the column's black. Between cell 5 and cell 6, and
on cell 6's outer right, the green solid wins. Above cell 5 the dashed blue
wins because it is wider than the red solid. Hidden leaves width 0. None
loses to a zero-width solid. Dotted width 3 beats double width 1. A cell
beats a table at the same solid width. The upper cell beats the lower cell,
and the start-side cell wins for ltr and for rtl. Invalid input has no border.

Prints JSON with boolean passed and nonempty observed. Exit 0 either way.
"""

from __future__ import annotations

import json


def _edge(
    source: str,
    style: str,
    width: float,
    color: str,
    row: int,
    column: int,
) -> dict[str, object]:
    return {
        "source": source,
        "style": style,
        "width": width,
        "color": color,
        "row": row,
        "column": column,
    }


def _won(result: object, *, style: str, width: float, color: str, source: str, suppressed: bool) -> bool:
    if not isinstance(result, dict) or result.get("outcome") != "resolved":
        return False
    if result.get("style") != style or result.get("color") != color or result.get("source") != source:
        return False
    if result.get("suppressed") is not suppressed:
        return False
    got = result.get("width")
    if isinstance(got, bool) or not isinstance(got, (int, float)):
        return False
    return abs(float(got) - width) <= 1e-9


def _invalid(result: object) -> bool:
    return (
        isinstance(result, dict)
        and result.get("outcome") == "invalid"
        and result.get("style") is None
        and result.get("width") is None
        and result.get("color") is None
        and result.get("source") is None
        and result.get("suppressed") is None
    )


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_collapsed_border import resolve_collapsed_border
    except Exception as exc:  # noqa: BLE001 - baseline without the resolver still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}
    checks: list[bool] = []

    def resolve(name: str, borders: object, **kwargs: object) -> dict[str, object]:
        try:
            result = resolve_collapsed_border(borders, **kwargs)  # type: ignore[arg-type]
        except Exception as exc:  # noqa: BLE001 - a raised call is an unmet outcome
            result = {"outcome": "error", "error": f"{type(exc).__name__}: {exc}"}
        observed[name] = result
        return result if isinstance(result, dict) else {"outcome": "error"}

    outer_left = resolve(
        "cell1_outer_left",
        [
            _edge("table", "solid", 5, "yellow", 0, 0),
            _edge("column", "solid", 3, "black", 0, 0),
            _edge("cell", "solid", 1, "red", 0, 0),
        ],
    )
    checks.append(_won(outer_left, style="solid", width=5, color="yellow", source="table", suppressed=False))

    between_1_and_2 = resolve(
        "between_cell1_and_cell2",
        [
            _edge("cell", "solid", 1, "red", 0, 0),
            _edge("cell", "solid", 1, "red", 0, 1),
            _edge("column", "solid", 3, "black", 0, 0),
        ],
    )
    checks.append(_won(between_1_and_2, style="solid", width=3, color="black", source="column", suppressed=False))

    between_5_and_6 = resolve(
        "between_cell5_and_cell6",
        [
            _edge("cell", "dashed", 5, "blue", 1, 1),
            _edge("cell", "solid", 5, "green", 1, 2),
        ],
    )
    checks.append(_won(between_5_and_6, style="solid", width=5, color="green", source="cell", suppressed=False))

    above_5 = resolve(
        "above_cell5",
        [
            _edge("cell", "solid", 1, "red", 0, 1),
            _edge("cell", "dashed", 5, "blue", 1, 1),
        ],
    )
    checks.append(_won(above_5, style="dashed", width=5, color="blue", source="cell", suppressed=False))

    outer_right = resolve(
        "cell6_outer_right",
        [
            _edge("table", "solid", 5, "yellow", 1, 2),
            _edge("cell", "solid", 5, "green", 1, 2),
        ],
    )
    checks.append(_won(outer_right, style="solid", width=5, color="green", source="cell", suppressed=False))

    hidden = resolve(
        "hidden_prevents_solid",
        [
            _edge("table", "solid", 8, "black", 0, 0),
            _edge("cell", "hidden", 1, "red", 0, 1),
        ],
    )
    checks.append(_won(hidden, style="hidden", width=0, color="red", source="cell", suppressed=True))

    omitted = resolve(
        "every_style_none",
        [
            _edge("table", "none", 4, "yellow", 0, 0),
            _edge("cell", "none", 2, "red", 0, 0),
        ],
    )
    checks.append(_won(omitted, style="none", width=0, color="red", source="cell", suppressed=False))

    zero_solid = resolve(
        "zero_solid_beats_none",
        [
            _edge("row", "none", 3, "blue", 0, 0),
            _edge("cell", "solid", 0, "red", 0, 1),
        ],
    )
    checks.append(_won(zero_solid, style="solid", width=0, color="red", source="cell", suppressed=False))

    wide_dotted = resolve(
        "dotted_3_beats_double_1",
        [
            _edge("cell", "double", 1, "navy", 0, 0),
            _edge("column", "dotted", 3, "gray", 0, 0),
        ],
    )
    checks.append(_won(wide_dotted, style="dotted", width=3, color="gray", source="column", suppressed=False))

    styles = (
        ("double", "navy"),
        ("solid", "green"),
        ("dashed", "blue"),
        ("dotted", "gray"),
        ("ridge", "purple"),
        ("outset", "orange"),
        ("groove", "teal"),
        ("inset", "olive"),
    )
    for drop in range(len(styles)):
        borders = [
            _edge("table", style, 2, color, 0, index)
            for index, (style, color) in enumerate(styles[drop:])
        ]
        chosen = styles[drop]
        result = resolve(f"style_{chosen[0]}", borders)
        checks.append(
            _won(result, style=chosen[0], width=2, color=chosen[1], source="table", suppressed=False)
        )

    sources = (
        ("cell", "red"),
        ("row", "blue"),
        ("row-group", "green"),
        ("column", "purple"),
        ("column-group", "orange"),
        ("table", "yellow"),
    )
    for drop in range(len(sources) - 1):
        borders = [
            _edge(source, "solid", 2, color, 0, 0)
            for source, color in reversed(sources[drop:])
        ]
        chosen = sources[drop]
        result = resolve(f"source_{chosen[0]}", borders)
        checks.append(
            _won(result, style="solid", width=2, color=chosen[1], source=chosen[0], suppressed=False)
        )

    upper = resolve(
        "upper_cell_beats_lower_cell",
        [
            _edge("cell", "solid", 2, "blue", 1, 0),
            _edge("cell", "solid", 2, "red", 0, 2),
        ],
    )
    checks.append(_won(upper, style="solid", width=2, color="red", source="cell", suppressed=False))

    left = resolve(
        "ltr_start_cell",
        [
            _edge("cell", "solid", 2, "blue", 0, 1),
            _edge("cell", "solid", 2, "red", 0, 0),
        ],
        direction="ltr",
    )
    checks.append(_won(left, style="solid", width=2, color="red", source="cell", suppressed=False))

    right = resolve(
        "rtl_start_cell",
        [
            _edge("cell", "solid", 2, "blue", 0, 1),
            _edge("cell", "solid", 2, "red", 0, 0),
        ],
        direction="rtl",
    )
    checks.append(_won(right, style="solid", width=2, color="blue", source="cell", suppressed=False))

    checks.append(_invalid(resolve("empty", [])))
    checks.append(_invalid(resolve("unknown_style", [_edge("cell", "wave", 1, "red", 0, 0)])))
    checks.append(_invalid(resolve("negative_width", [_edge("cell", "solid", -1, "red", 0, 0)])))
    checks.append(_invalid(resolve("boolean_width", [_edge("cell", "solid", True, "red", 0, 0)])))  # type: ignore[arg-type]
    checks.append(_invalid(resolve("unknown_direction", [_edge("cell", "solid", 1, "red", 0, 0)], direction="down")))

    return all(checks), observed


def main() -> int:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - the probe must exit 0 either way
        passed, observed = False, {"error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps({"passed": bool(passed), "observed": observed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
