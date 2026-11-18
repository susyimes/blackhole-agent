"""Place CSS grid items with the automatic-placement cursor.

CSS Grid §8.5 keeps a sparse cursor, restarts that search when packing is
dense, and swaps the axes for column flow. §8.3 resolves lines before any of
those items move. Prints JSON with boolean passed and nonempty observed.
Exit 0 for both a miss and a hit. A tree without the cursor still exits 0.
"""

from __future__ import annotations

import json

_KEYS = (
    "outcome",
    "flow",
    "dense",
    "column_start_line",
    "column_count",
    "row_start_line",
    "row_count",
    "placements",
)


def _auto(ident: str, *, column: str | None = None, row: str | None = None) -> dict[str, object]:
    item: dict[str, object] = {"id": ident}
    if column is not None:
        item["column_start"] = column
    if row is not None:
        item["row_start"] = row
    return item


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_grid_placement import place_grid_items
    except Exception as exc:  # noqa: BLE001 - baseline without the cursor still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}
    checks: list[bool] = []

    def take(name: str, columns: int, rows: int, items: list[dict[str, object]], **kwargs: object) -> dict[str, object]:
        try:
            result = place_grid_items(columns, rows, items, **kwargs)
        except Exception as exc:  # noqa: BLE001 - a raised cursor is an unmet outcome
            result = {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}"}
        packed = result if isinstance(result, dict) else {"outcome": "error"}
        observed[name] = {key: packed.get(key) for key in _KEYS}
        return observed[name]

    def expect(
        name: str,
        columns: int,
        rows: int,
        items: list[dict[str, object]],
        placements: list[list[object]],
        *,
        column_count: int,
        row_count: int,
        column_start_line: int = 1,
        row_start_line: int = 1,
        packing: str = "row",
        flow: str = "row",
        dense: bool = False,
    ) -> None:
        got = take(name, columns, rows, items, flow=packing)
        areas = [
            [area.get("id"), area.get("column"), area.get("row"), area.get("column_span"), area.get("row_span")]
            for area in got.get("placements") or []
            if isinstance(area, dict)
        ]
        checks.append(
            got.get("outcome") == "placed"
            and got.get("flow") == flow
            and got.get("dense") is dense
            and got.get("column_count") == column_count
            and got.get("row_count") == row_count
            and got.get("column_start_line") == column_start_line
            and got.get("row_start_line") == row_start_line
            and areas == placements
        )

    spans = [
        _auto("a", column="span 2"),
        _auto("b", column="span 2"),
        _auto("c"),
    ]
    expect(
        "sparse_wrap",
        3,
        0,
        spans,
        [["a", 1, 1, 2, 1], ["b", 1, 2, 2, 1], ["c", 3, 2, 1, 1]],
        column_count=3,
        row_count=2,
    )
    expect(
        "dense_hole",
        3,
        0,
        spans,
        [["a", 1, 1, 2, 1], ["b", 1, 2, 2, 1], ["c", 3, 1, 1, 1]],
        column_count=3,
        row_count=2,
        packing="row dense",
        flow="row",
        dense=True,
    )

    locked_cursor = [
        {"id": "x", "column_start": 2, "row_start": 1},
        {"id": "b", "column_start": 3},
        {"id": "c", "column_start": 1},
    ]
    expect(
        "cursor_holds_column",
        3,
        0,
        locked_cursor,
        [["x", 2, 1, 1, 1], ["b", 3, 1, 1, 1], ["c", 1, 2, 1, 1]],
        column_count=3,
        row_count=2,
    )
    expect(
        "dense_restarts_cursor",
        3,
        0,
        locked_cursor,
        [["x", 2, 1, 1, 1], ["b", 3, 1, 1, 1], ["c", 1, 1, 1, 1]],
        column_count=3,
        row_count=1,
        packing="dense",
        dense=True,
    )

    locked_row = [
        {"id": "x", "column_start": 2, "row_start": 1},
        {"id": "a", "column_start": "span 2", "row_start": 1},
        {"id": "b", "row_start": 1},
    ]
    expect(
        "locked_sparse",
        4,
        0,
        locked_row,
        [["x", 2, 1, 1, 1], ["a", 3, 1, 2, 1], ["b", 5, 1, 1, 1]],
        column_count=5,
        row_count=1,
    )
    expect(
        "locked_dense",
        4,
        0,
        locked_row,
        [["x", 2, 1, 1, 1], ["a", 3, 1, 2, 1], ["b", 1, 1, 1, 1]],
        column_count=4,
        row_count=1,
        packing="row dense",
        dense=True,
    )

    column_items = [
        _auto("a", row="span 2"),
        _auto("b", row="span 2"),
        _auto("c"),
    ]
    expect(
        "column_sparse",
        0,
        3,
        column_items,
        [["a", 1, 1, 1, 2], ["b", 2, 1, 1, 2], ["c", 2, 3, 1, 1]],
        column_count=2,
        row_count=3,
        packing="column",
        flow="column",
    )
    expect(
        "column_dense",
        0,
        3,
        column_items,
        [["a", 1, 1, 1, 2], ["b", 2, 1, 1, 2], ["c", 1, 3, 1, 1]],
        column_count=2,
        row_count=3,
        packing="column dense",
        flow="column",
        dense=True,
    )

    expect(
        "definite_span_grows",
        5,
        0,
        [{"id": "a", "column_start": 4, "column_end": "span 3", "row_start": 1}],
        [["a", 4, 1, 3, 1]],
        column_count=6,
        row_count=1,
    )
    expect(
        "negative_end_line",
        3,
        1,
        [{"id": "a", "column_end": -1, "row_start": 1}],
        [["a", 3, 1, 1, 1]],
        column_count=3,
        row_count=1,
    )
    expect(
        "swapped_lines",
        5,
        1,
        [{"id": "a", "column_start": 5, "column_end": 2, "row_start": 1}],
        [["a", 2, 1, 3, 1]],
        column_count=5,
        row_count=1,
    )
    expect(
        "dropped_end_span",
        4,
        0,
        [_auto("a", column="span 3") | {"column_end": "span 2"}],
        [["a", 1, 1, 3, 1]],
        column_count=4,
        row_count=1,
    )
    expect(
        "equal_lines",
        4,
        0,
        [{"id": "a", "column_start": 4, "column_end": 4}],
        [["a", 4, 1, 1, 1]],
        column_count=4,
        row_count=1,
    )
    expect(
        "cursor_starts_before_explicit_rows",
        2,
        0,
        [
            {"id": "a", "column_start": 1, "row_start": "span 1", "row_end": 1},
            _auto("b"),
        ],
        [["a", 1, 0, 1, 1], ["b", 2, 0, 1, 1]],
        column_count=2,
        row_count=1,
        row_start_line=0,
    )
    expect(
        "locked_row_stays_on_positive_lines",
        3,
        0,
        [
            {"id": "c", "column_start": "span 1", "column_end": 1, "row_start": 2},
            {"id": "x", "column_start": 1, "row_start": 1},
            {"id": "b", "row_start": 1},
        ],
        [["c", 0, 2, 1, 1], ["x", 1, 1, 1, 1], ["b", 2, 1, 1, 1]],
        column_count=4,
        row_count=2,
        column_start_line=0,
    )
    expect(
        "row_span_blocks_next_line",
        2,
        0,
        [_auto("a", row="span 2"), _auto("b"), _auto("c")],
        [["a", 1, 1, 1, 2], ["b", 2, 1, 1, 1], ["c", 2, 2, 1, 1]],
        column_count=2,
        row_count=2,
    )

    def reject(name: str, columns: object, rows: object, items: object, **kwargs: object) -> None:
        got = take(name, columns, rows, items, **kwargs)  # type: ignore[arg-type]
        checks.append(got.get("outcome") == "invalid" and got.get("placements") is None)

    reject("zero_line", 3, 0, [{"id": "a", "column_start": 0}])
    reject("zero_span", 3, 0, [_auto("a", column="span 0")])
    reject("boolean_line", 3, 0, [{"id": "a", "column_start": True}])
    reject("duplicate_id", 3, 0, [_auto("a"), _auto("a")])
    reject("unknown_flow", 3, 0, [_auto("a")], flow="diagonal")
    reject("negative_tracks", -1, 0, [_auto("a")])

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
