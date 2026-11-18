"""Lay out fixed CSS table columns from the table, the columns, and the first row.

A column width wins over a cell. A span divides its width across the columns
it is still allowed to set. Pixel columns keep their lengths, overflowing
percentages shrink, and open columns share only what remains. An auto table
width does not invent columns.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree without the layout still exits 0.
"""

from __future__ import annotations

import json

_KEYS = (
    "outcome",
    "reason",
    "column_widths",
    "table_width",
    "used_table_width",
    "assignable",
    "spacing",
)


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_fixed_table import layout_fixed_columns
    except Exception as exc:  # noqa: BLE001 - baseline without the layout still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}
    checks: list[bool] = []

    def take(name: str, table_width: object, columns: object, **kwargs: object) -> dict[str, object]:
        try:
            result = layout_fixed_columns(table_width, columns, **kwargs)
        except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
            result = {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}"}
        packed = result if isinstance(result, dict) else {"outcome": "error"}
        observed[name] = {key: packed.get(key) for key in _KEYS}
        return observed[name]

    def expect(name: str, fields: dict[str, object], table_width: object, columns: object, **kwargs: object) -> None:
        got = take(name, table_width, columns, **kwargs)
        checks.append(all(got.get(key) == value for key, value in fields.items()))

    expect(
        "four_open",
        {"outcome": "resolved", "column_widths": [100, 100, 100, 100], "used_table_width": 400, "assignable": 400},
        400,
        ["auto", "auto", "auto", "auto"],
    )
    expect(
        "specified_and_open",
        {"outcome": "resolved", "column_widths": [150, 200, 50], "used_table_width": 400},
        400,
        [150, "auto", 50],
    )
    expect(
        "column_overrides_cell",
        {"outcome": "resolved", "column_widths": [80, 40], "used_table_width": 120},
        120,
        [80, "auto"],
        cells=[{"width": 10}, {"width": 40}],
    )
    expect(
        "span_skips_set_column",
        {"outcome": "resolved", "column_widths": [100, 100, 100], "used_table_width": 300},
        300,
        [100, "auto", "auto"],
        cells=[{"span": 3, "width": 200}],
    )
    span_row = [{"span": 2, "width": 200}, {"width": 50}]
    expect(
        "span_exact",
        {"outcome": "resolved", "column_widths": [100, 100, 50], "used_table_width": 250},
        250,
        ["auto", "auto", "auto"],
        cells=span_row,
    )
    expect(
        "span_extra_to_lengths",
        {"outcome": "resolved", "column_widths": [160, 160, 80], "used_table_width": 400},
        400,
        ["auto", "auto", "auto"],
        cells=span_row,
    )
    expect(
        "length_absorbs_extra",
        {"outcome": "resolved", "column_widths": [300, 100], "used_table_width": 400},
        400,
        [100, "25%"],
    )
    expect(
        "percentage_shrinks",
        {"outcome": "resolved", "column_widths": [300, 100], "used_table_width": 400},
        400,
        [300, "50%"],
    )
    expect(
        "two_percentages_shrink",
        {"outcome": "resolved", "column_widths": [200, 200], "used_table_width": 400},
        400,
        ["80%", "80%"],
    )
    expect(
        "pixels_grow_table",
        {
            "outcome": "resolved",
            "column_widths": [200, 200],
            "table_width": 100,
            "used_table_width": 400,
        },
        100,
        [200, 200],
    )
    expect(
        "spacing_open",
        {
            "outcome": "resolved",
            "column_widths": [105, 105],
            "assignable": 210,
            "used_table_width": 220,
            "spacing": 10,
        },
        220,
        ["auto", "auto"],
        spacing=10,
    )
    expect(
        "spacing_percent",
        {
            "outcome": "resolved",
            "column_widths": [90, 90],
            "assignable": 180,
            "used_table_width": 200,
            "spacing": 20,
        },
        200,
        ["50%", "50%"],
        spacing=20,
    )
    expect(
        "zero_percentages_share",
        {"outcome": "resolved", "column_widths": [20, 20], "used_table_width": 40},
        40,
        ["0%", "0%"],
    )
    expect(
        "open_stays_zero",
        {"outcome": "resolved", "column_widths": [400, 0, 0], "used_table_width": 400},
        400,
        [400, "auto", "auto"],
    )
    expect(
        "automatic",
        {"outcome": "automatic", "column_widths": None, "used_table_width": None},
        "auto",
        ["auto", "auto"],
    )
    expect(
        "max_content",
        {"outcome": "automatic", "reason": "fixed layout requires a definite table width", "column_widths": None},
        "max-content",
        [100, "auto"],
    )
    negative = take("negative_table", -1, ["auto"])
    checks.append(negative.get("outcome") == "invalid" and negative.get("column_widths") is None)
    boolean = take("boolean_width", 40, [True])
    checks.append(boolean.get("outcome") == "invalid" and boolean.get("column_widths") is None)
    overrun = take("cell_overrun", 40, ["auto"], cells=[{"span": 2, "width": 10}])
    checks.append(overrun.get("outcome") == "invalid" and overrun.get("column_widths") is None)

    return all(checks), observed


def _emit(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=True))


def main() -> int:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - the probe must exit 0 either way
        passed, observed = False, {"error": f"{type(exc).__name__}: {exc}"}
    if not observed:
        observed = {"error": "empty observation"}
    _emit({"passed": bool(passed), "observed": observed})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
