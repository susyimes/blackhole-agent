"""Resolve named grid areas and named lines into occupied cells.

A rectangular template places the item that names the area. A bent area is
rejected. An earlier explicit line beats the area edge. A named span stops
on the next line of that name, and a missing name starts on the first
implicit line after the explicit grid.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree without the resolver still exits 0.
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
    "reason",
)
_SPEC_LINES = [["A"], ["B"], ["C"], ["A"], ["B"], ["C"], ["A"], ["B"], ["C"]]


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_grid_areas import place_named_grid
    except Exception as exc:  # noqa: BLE001 - baseline without the resolver still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}
    checks: list[bool] = []

    def take(name: str, columns: object, rows: object, items: object, **kwargs: object) -> dict[str, object]:
        try:
            result = place_named_grid(columns, rows, items, **kwargs)
        except Exception as exc:  # noqa: BLE001 - a raised resolver is an unmet outcome
            result = {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}"}
        packed = result if isinstance(result, dict) else {"outcome": "error"}
        observed[name] = {key: packed.get(key) for key in _KEYS}
        return observed[name]

    def placed(
        name: str,
        columns: object,
        rows: object,
        items: object,
        placements: list[list[object]],
        *,
        column_count: int,
        row_count: int,
        column_start_line: int = 1,
        row_start_line: int = 1,
        **kwargs: object,
    ) -> None:
        got = take(name, columns, rows, items, **kwargs)
        areas = [
            [area.get("id"), area.get("column"), area.get("row"), area.get("column_span"), area.get("row_span")]
            for area in got.get("placements") or []
            if isinstance(area, dict)
        ]
        checks.append(
            got.get("outcome") == "placed"
            and got.get("column_count") == column_count
            and got.get("row_count") == row_count
            and got.get("column_start_line") == column_start_line
            and got.get("row_start_line") == row_start_line
            and areas == placements
        )

    def rejected(name: str, columns: object, rows: object, items: object, **kwargs: object) -> None:
        got = take(name, columns, rows, items, **kwargs)
        checks.append(got.get("outcome") == "invalid" and got.get("placements") is None)

    placed(
        "header_nav_auto",
        0,
        0,
        [
            {"id": "header", "area": "header"},
            {"id": "nav", "area": "nav"},
            {"id": "extra"},
        ],
        [["header", 1, 1, 2, 1], ["nav", 1, 2, 1, 1], ["extra", 2, 2, 1, 1]],
        column_count=2,
        row_count=2,
        areas=["header header", "nav ."],
    )
    placed(
        "spec_template",
        0,
        0,
        [
            {"id": "head", "area": "head"},
            {"id": "nav", "area": "nav"},
            {"id": "main", "area": "main"},
            {"id": "foot", "area": "foot"},
            {"id": "extra"},
        ],
        [
            ["head", 1, 1, 2, 1],
            ["nav", 1, 2, 1, 1],
            ["main", 2, 2, 1, 1],
            ["foot", 1, 3, 1, 1],
            ["extra", 2, 3, 1, 1],
        ],
        column_count=2,
        row_count=3,
        areas=["head head", "nav main", "foot ...."],
    )
    rejected("bent_area", 0, 0, [{"id": "a", "area": "a"}], areas=["a a", "a b"])
    rejected("disconnected_area", 0, 0, [{"id": "a", "area": "a"}], areas=["a b", "b a"])
    rejected("uneven_areas", 0, 0, [{"id": "a", "area": "a"}], areas=["a a", "a"])
    placed(
        "explicit_line_ahead",
        0,
        0,
        [{"id": "box", "area": "header"}],
        [["box", 1, 1, 3, 1]],
        column_count=3,
        row_count=1,
        areas=[". header header"],
        column_lines=[["header-start"], [], [], []],
    )
    placed(
        "area_beats_same_line_name",
        2,
        1,
        [{"id": "box", "column_start": "header", "row_start": 1}],
        [["box", 2, 1, 1, 1]],
        column_count=2,
        row_count=1,
        column_lines=[["header"], ["header-start"], []],
    )
    placed(
        "named_span",
        8,
        1,
        [{"id": "box", "column_start": "C", "column_end": "span C", "row_start": 1}],
        [["box", 3, 1, 3, 1]],
        column_count=8,
        row_count=1,
        column_lines=_SPEC_LINES,
    )
    placed(
        "named_span_from_end",
        8,
        1,
        [{"id": "box", "column_start": "span C", "column_end": "C -1", "row_start": 1}],
        [["box", 6, 1, 3, 1]],
        column_count=8,
        row_count=1,
        column_lines=_SPEC_LINES,
    )
    placed(
        "second_named_line",
        8,
        1,
        [{"id": "box", "column_start": "B 2", "row_start": 1}],
        [["box", 5, 1, 1, 1]],
        column_count=8,
        row_count=1,
        column_lines=_SPEC_LINES,
    )
    placed(
        "named_spans_collapse",
        8,
        1,
        [{"id": "box", "column_start": "span C", "column_end": "span C", "row_start": 1}],
        [["box", 1, 1, 1, 1]],
        column_count=8,
        row_count=1,
        column_lines=_SPEC_LINES,
    )
    placed(
        "missing_name",
        3,
        1,
        [{"id": "box", "column_start": "missing", "row_start": 1}],
        [["box", 5, 1, 1, 1]],
        column_count=5,
        row_count=1,
    )
    placed(
        "span_before_explicit_grid",
        1,
        1,
        [{"id": "box", "column_start": "span foo", "column_end": 4, "row_start": 1}],
        [["box", 0, 1, 4, 1]],
        column_count=4,
        row_count=1,
        column_start_line=0,
    )
    placed(
        "negative_numeric_line",
        3,
        1,
        [{"id": "box", "column_end": -1, "row_start": 1}],
        [["box", 3, 1, 1, 1]],
        column_count=3,
        row_count=1,
    )
    rejected("zero_line", 3, 1, [{"id": "box", "column_start": 0}])

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
