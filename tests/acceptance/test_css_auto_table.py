"""Automatic CSS tables take a width from every row's content.

Fixed layout returns no columns for an automatic table width. Here a 10/30
column and a 10/90 column at auto become 30 and 90. A definite 70 interpolates
them to 20 and 50. A table width of 5 grows to the floors 10 and 20. A column
length of 40 stays 40 beside a 10/100 neighbor when the table is 200, and the
neighbor takes the leftover at 160. A cell length of 40 on content 10/100,
beside another 10/100 column, at table width 30 interpolates to 20 and 10.
A 50% column beside 20/40 and 10/30 content at table width 200 is 100 and 100.
Two 80% columns at table width 100 clamp to 80 and 20. Spacing 4 around two
10px columns makes the table 32. A span of 40 across two 10px columns makes
20 and 20, and the same span across empty columns at table width 100 makes
50 and 50. A 50% span over columns whose caps are 10 and 0 keeps 50 for the
percentage column and gives the other 50 of a 100px table to its neighbor. A later row of max 70 replaces a first row of max 10. A maximum
width of 20 caps content 80. A minimum width of 50 wins over a maximum of 20.
A containing block of 100 limits a 50% column and its neighbor to 35 and 35.
min-content and max-content select the floors and the caps. Two empty columns
in a table of 40 share it as 20 and 20. Invalid input reports no widths.

Prints JSON with boolean passed and nonempty observed. Exit 0 either way.
"""

from __future__ import annotations

import json


def _close(got: object, expected: float) -> bool:
    if isinstance(got, bool) or not isinstance(got, (int, float)):
        return False
    return abs(float(got) - expected) <= 1e-6


def _widths(result: object, widths: tuple[float, ...], used: float) -> bool:
    if not isinstance(result, dict) or result.get("outcome") != "resolved":
        return False
    got = result.get("column_widths")
    if not isinstance(got, list) or len(got) != len(widths):
        return False
    if any(not _close(item, want) for item, want in zip(got, widths)):
        return False
    return _close(result.get("used_table_width"), used)


def _invalid(result: object) -> bool:
    return (
        isinstance(result, dict)
        and result.get("outcome") == "invalid"
        and result.get("column_widths") is None
        and result.get("used_table_width") is None
    )


def _cell(column: int, minimum: float, maximum: float, **extra: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "column": column,
        "span": extra.pop("span", 1),
        "min_content": minimum,
        "max_content": maximum,
    }
    payload.update(extra)
    return payload


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_auto_table import layout_auto_columns
    except Exception as exc:  # noqa: BLE001 - baseline without the layout still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}
    checks: list[bool] = []

    def place(name: str, *args: object, **kwargs: object) -> dict[str, object]:
        try:
            result = layout_auto_columns(*args, **kwargs)  # type: ignore[arg-type]
        except Exception as exc:  # noqa: BLE001 - a raised call is an unmet outcome
            result = {"outcome": "error", "error": f"{type(exc).__name__}: {exc}"}
        observed[name] = result
        return result if isinstance(result, dict) else {"outcome": "error"}

    content = [_cell(0, 10, 30), _cell(1, 10, 90)]
    checks.append(_widths(place("auto_caps", "auto", ["auto", "auto"], content), (30, 90), 120))
    checks.append(_widths(place("interpolated", 70, ["auto", "auto"], content), (20, 50), 70))
    checks.append(
        _widths(
            place("min_content_keyword", "min-content", ["auto", "auto"], content),
            (10, 10),
            20,
        )
    )
    checks.append(
        _widths(
            place("max_content_keyword", "max-content", ["auto", "auto"], content),
            (30, 90),
            120,
        )
    )
    floors = [_cell(0, 10, 10), _cell(1, 20, 20)]
    checks.append(_widths(place("below_floors", 5, ["auto", "auto"], floors), (10, 20), 30))

    neighbor = [_cell(0, 10, 100), _cell(1, 10, 100)]
    checks.append(
        _widths(
            place("column_length_floor", 200, [{"width": 40}, "auto"], neighbor),
            (40, 160),
            200,
        )
    )
    checks.append(
        _widths(
            place("column_length_raises_the_used_width", 30, [{"width": 40}, "auto"], neighbor),
            (40, 10),
            50,
        )
    )
    preferred = [_cell(0, 10, 100, width=40), _cell(1, 10, 100)]
    checks.append(_widths(place("cell_length_is_a_cap", 30, ["auto", "auto"], preferred), (20, 10), 30))

    percent = [_cell(0, 20, 40, width="50%"), _cell(1, 10, 30)]
    checks.append(_widths(place("percent_keeps_its_share", 200, ["auto", "auto"], percent), (100, 100), 200))
    checks.append(
        _widths(
            place("containing_block_limits_auto", "auto", ["auto", "auto"], percent, containing=100),
            (35, 35),
            70,
        )
    )
    checks.append(_widths(place("percentages_clamp_at_100", 100, ["80%", "80%"], []), (80, 20), 100))

    spaced = [_cell(0, 10, 10), _cell(1, 10, 10)]
    checks.append(_widths(place("edges_and_gap", "auto", ["auto", "auto"], spaced, spacing=4), (10, 10), 32))

    spanned = [_cell(0, 10, 10), _cell(1, 10, 10), _cell(0, 40, 40, span=2)]
    checks.append(_widths(place("span_spreads_the_extra", "auto", ["auto", "auto"], spanned), (20, 20), 40))
    checks.append(
        _widths(
            place("span_of_empty_columns", 100, ["auto", "auto"], [_cell(0, 40, 40, span=2)]),
            (50, 50),
            100,
        )
    )
    checks.append(
        _widths(
            place(
                "span_percent_reserves_a_share",
                100,
                ["auto", "auto"],
                [_cell(0, 0, 10), _cell(1, 0, 0), _cell(0, 0, 0, span=2, width="50%")],
            ),
            (50, 50),
            100,
        )
    )
    checks.append(
        _widths(
            place("later_row_wins", "auto", ["auto"], [_cell(0, 10, 10), _cell(0, 5, 70)]),
            (70,),
            70,
        )
    )
    checks.append(
        _widths(
            place(
                "max_width_caps_content",
                "auto",
                ["auto"],
                [_cell(0, 10, 80, max_width=20)],
            ),
            (20,),
            20,
        )
    )
    checks.append(
        _widths(
            place(
                "minimum_wins",
                "auto",
                ["auto"],
                [_cell(0, 10, 80, min_width=50, max_width=20)],
            ),
            (50,),
            50,
        )
    )
    checks.append(_widths(place("empty_columns_share", 40, ["auto", "auto"], []), (20, 20), 40))

    checks.append(_invalid(place("empty_column_list", "auto", [], [])))
    checks.append(_invalid(place("unknown_table_width", "stretch", ["auto"], [])))
    checks.append(_invalid(place("span_past_the_end", "auto", ["auto"], [_cell(0, 10, 10, span=2)])))
    checks.append(_invalid(place("boolean_content", "auto", ["auto"], [_cell(0, True, 10)])))  # type: ignore[arg-type]
    checks.append(_invalid(place("negative_spacing", "auto", ["auto"], [], spacing=-1)))
    checks.append(_invalid(place("content_max_below_min", "auto", ["auto"], [_cell(0, 30, 10)])))

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
