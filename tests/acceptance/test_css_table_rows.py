"""CSS table rows align on a shared baseline and distribute height.

A baseline cell with ascent 24 beside one with ascent 8 puts the row baseline
at 24. A bottom-aligned cell 50 tall grows that row to 50, and a middle cell
12 tall then starts at 19. A top-aligned cell of 80 covering rows of 10 and 30
becomes 20 and 60, leaving the baselines at the first-pass line boxes 10 and
30. Table height 100 gives the leftover to the automatic row: a specified row
of 40 beside content 20 becomes 40 and 60. The same table height blends an 80%
row of content 10 with an automatic row of 30 into 70 and 30. Two 80% rows
with no content blend to 50 and 50 instead of each taking 80. A definite table
height of 40 does not shrink content of 80. Spacing 4 around two 10px rows
makes the table 32. An empty row list, a span past the last row, a negative
cell height, and a boolean content height report an invalid outcome and no
row heights.

Prints JSON with boolean passed and nonempty observed. Exit 0 either way.
"""

from __future__ import annotations

import json


def _close(got: object, expected: float) -> bool:
    if isinstance(got, bool) or not isinstance(got, (int, float)):
        return False
    return abs(float(got) - expected) <= 1e-6


def _heights(result: object, heights: tuple[float, ...], baselines: tuple[float, ...], used: float) -> bool:
    if not isinstance(result, dict) or result.get("outcome") != "resolved":
        return False
    got = result.get("row_heights")
    lines = result.get("row_baselines")
    if not isinstance(got, list) or not isinstance(lines, list):
        return False
    if len(got) != len(heights) or len(lines) != len(baselines):
        return False
    if any(not _close(item, want) for item, want in zip(got, heights)):
        return False
    if any(not _close(item, want) for item, want in zip(lines, baselines)):
        return False
    return _close(result.get("used_table_height"), used)


def _cell_at(result: object, name: str, top: float, border_top: float, border_height: float) -> bool:
    if not isinstance(result, dict):
        return False
    cells = result.get("cells")
    if not isinstance(cells, list):
        return False
    for cell in cells:
        if isinstance(cell, dict) and cell.get("id") == name:
            return (
                _close(cell.get("content_top"), top)
                and _close(cell.get("border_top"), border_top)
                and _close(cell.get("border_height"), border_height)
            )
    return False


def _invalid(result: object) -> bool:
    return (
        isinstance(result, dict)
        and result.get("outcome") == "invalid"
        and result.get("row_heights") is None
        and result.get("row_baselines") is None
        and result.get("used_table_height") is None
        and result.get("cells") is None
    )


def _cell(name: str, row: int, content: float, **extra: object) -> dict[str, object]:
    payload: dict[str, object] = {"id": name, "row": row, "content_height": content}
    payload.update(extra)
    return payload


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_table_rows import layout_table_rows
    except Exception as exc:  # noqa: BLE001 - baseline without the layout still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}
    checks: list[bool] = []

    def place(name: str, *args: object, **kwargs: object) -> dict[str, object]:
        try:
            result = layout_table_rows(*args, **kwargs)  # type: ignore[arg-type]
        except Exception as exc:  # noqa: BLE001 - a raised call is an unmet outcome
            result = {"outcome": "error", "error": f"{type(exc).__name__}: {exc}"}
        observed[name] = result
        return result if isinstance(result, dict) else {"outcome": "error"}

    aligned = place(
        "baseline_and_bottom",
        ["auto"],
        [
            _cell("short", 0, 20, baseline=8),
            _cell("tall", 0, 30, baseline=24),
            _cell("low", 0, 50, vertical_align="bottom"),
            _cell("mid", 0, 12, vertical_align="middle"),
        ],
    )
    checks.append(_heights(aligned, (50,), (24,), 50))
    checks.append(_cell_at(aligned, "short", 16, 0, 50))
    checks.append(_cell_at(aligned, "tall", 0, 0, 50))
    checks.append(_cell_at(aligned, "low", 0, 0, 50))
    checks.append(_cell_at(aligned, "mid", 19, 0, 50))

    other = place(
        "other_values_align_baseline",
        ["auto"],
        [_cell("sub", 0, 20, baseline=5, vertical_align="sub"), _cell("base", 0, 20, baseline=15)],
    )
    checks.append(_heights(other, (30,), (15,), 30))
    checks.append(_cell_at(other, "sub", 10, 0, 30))

    below = place("baseline_below_the_border", ["auto"], [_cell("past", 0, 10, baseline=40)])
    checks.append(_heights(below, (10,), (40,), 10))
    checks.append(_cell_at(below, "past", 0, 0, 10))

    spanned = place(
        "span_follows_current_heights",
        ["auto", "auto"],
        [
            _cell("a", 0, 10, vertical_align="top"),
            _cell("b", 1, 30, vertical_align="top"),
            _cell("span", 0, 80, rowspan=2, vertical_align="top"),
        ],
    )
    checks.append(_heights(spanned, (20, 60), (10, 30), 80))
    checks.append(_cell_at(spanned, "span", 0, 0, 80))
    checks.append(_cell_at(spanned, "b", 0, 20, 60))

    zero_rows = place(
        "span_of_empty_rows",
        ["auto", "auto"],
        [_cell("span", 0, 80, rowspan=2, vertical_align="top")],
    )
    checks.append(_heights(zero_rows, (40, 40), (0, 0), 80))

    larger = place(
        "larger_span_wins",
        ["auto", "auto"],
        [
            _cell("a", 0, 10, vertical_align="top"),
            _cell("b", 1, 10, vertical_align="top"),
            _cell("small", 0, 40, rowspan=2, vertical_align="top"),
            _cell("large", 0, 100, rowspan=2, vertical_align="top"),
        ],
    )
    checks.append(_heights(larger, (50, 50), (10, 10), 100))

    gapped = place(
        "span_reserves_the_inner_gap",
        ["auto", "auto"],
        [
            _cell("a", 0, 10, vertical_align="top"),
            _cell("b", 1, 30, vertical_align="top"),
            _cell("span", 0, 80, rowspan=2, vertical_align="top"),
        ],
        border_spacing=4,
    )
    checks.append(_heights(gapped, (19, 57), (10, 30), 88))
    checks.append(_cell_at(gapped, "span", 0, 4, 80))
    checks.append(_cell_at(gapped, "b", 0, 27, 57))

    edges = place(
        "edges_and_gap",
        ["auto", "auto"],
        [_cell("a", 0, 10, vertical_align="top"), _cell("b", 1, 10, vertical_align="top")],
        border_spacing=4,
    )
    checks.append(_heights(edges, (10, 10), (10, 10), 32))
    checks.append(_cell_at(edges, "a", 0, 4, 10))
    checks.append(_cell_at(edges, "b", 0, 18, 10))

    leftover = place(
        "automatic_row_takes_leftover",
        [{"height": 40}, "auto"],
        [_cell("fixed", 0, 10, vertical_align="top"), _cell("flex", 1, 20, vertical_align="top")],
        table_height=100,
    )
    checks.append(_heights(leftover, (40, 60), (10, 20), 100))

    zero_specified = place(
        "specified_zero_does_not_count_as_automatic",
        [{"height": 0}, "auto"],
        [_cell("fixed", 0, 20, vertical_align="top"), _cell("flex", 1, 20, vertical_align="top")],
        table_height=100,
    )
    checks.append(_heights(zero_specified, (20, 80), (20, 20), 100))

    shared = place(
        "specified_rows_share_leftover",
        [{"height": 40}, {"height": 40}],
        [_cell("a", 0, 10, vertical_align="top"), _cell("b", 1, 10, vertical_align="top")],
        table_height=100,
    )
    checks.append(_heights(shared, (50, 50), (10, 10), 100))

    blended = place(
        "percentage_blends_with_content",
        [{"height": "80%"}, "auto"],
        [_cell("pct", 0, 10, vertical_align="top"), _cell("auto", 1, 30, vertical_align="top")],
        table_height=100,
    )
    checks.append(_heights(blended, (70, 30), (10, 30), 100))

    capped = place(
        "two_percentages_blend_to_the_table",
        [{"height": "80%"}, {"height": "80%"}],
        [_cell("a", 0, 0, vertical_align="top"), _cell("b", 1, 0, vertical_align="top")],
        table_height=100,
    )
    checks.append(_heights(capped, (50, 50), (0, 0), 100))

    cell_percent = place(
        "cell_percentage_is_not_an_automatic_row",
        ["auto", "auto"],
        [
            _cell("pct", 0, 10, vertical_align="top", height="50%"),
            _cell("auto", 1, 10, vertical_align="top"),
        ],
        table_height=200,
    )
    checks.append(_heights(cell_percent, (100, 100), (10, 10), 200))

    kept = place(
        "table_height_does_not_shrink_content",
        ["auto"],
        [_cell("tall", 0, 80, vertical_align="top")],
        table_height=40,
    )
    checks.append(_heights(kept, (80,), (80,), 80))

    grown = place(
        "specified_row_lowers_the_bottom_only",
        [{"height": 40}],
        [_cell("mid", 0, 10, vertical_align="middle")],
    )
    checks.append(_heights(grown, (40,), (10,), 40))
    checks.append(_cell_at(grown, "mid", 15, 0, 40))

    checks.append(_invalid(place("empty_row_list", [])))
    checks.append(_invalid(place("span_past_the_end", ["auto"], [_cell("a", 0, 10, rowspan=2)])))
    checks.append(_invalid(place("negative_cell_height", ["auto"], [_cell("a", 0, -1)])))
    checks.append(_invalid(place("boolean_content", ["auto"], [_cell("a", 0, True)])))  # type: ignore[arg-type]
    checks.append(_invalid(place("negative_spacing", ["auto"], [], border_spacing=-1)))
    checks.append(_invalid(place("percentage_table_height", ["auto"], [], table_height="50%")))

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
