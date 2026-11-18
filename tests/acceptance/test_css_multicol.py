"""Flow unbreakable fragments through a CSS multicol container.

Used column-count and column-width follow the multicol pseudo-algorithm.
A count is clamped by the slots that fit, and a column narrower than the
available size still becomes one column of that size. Balance uses the
shortest block size that fits the run, then fills columns in order. A
column-span all box balances the run above it and starts the next run
below.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree without the module still exits 0.
"""

from __future__ import annotations

import json


def _box(
    ident: str,
    span: str,
    column: int | None,
    line: int | None,
    inline: int | float,
    block: int,
    width: int | float,
    height: int,
) -> dict[str, object]:
    return {
        "id": ident,
        "span": span,
        "column": column,
        "line": line,
        "inline": inline,
        "block": block,
        "width": width,
        "height": height,
    }


def _invalid(result: object) -> bool:
    if not isinstance(result, dict):
        return False
    return (
        result.get("outcome") == "invalid"
        and result.get("boxes") is None
        and result.get("column_count") is None
        and result.get("column_width") is None
        and result.get("block_size") is None
    )


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_multicol import layout_multicol
    except Exception as exc:  # noqa: BLE001 - baseline without the module still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}
    checks: list[bool] = []

    def keep(name: str, **kwargs: object) -> dict[str, object]:
        try:
            result = layout_multicol(**kwargs)
        except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
            result = {"outcome": "error", "error": f"{type(exc).__name__}: {exc}"}
        observed[name] = result if isinstance(result, dict) else {"outcome": "error"}
        return observed[name]

    def expect(
        name: str,
        used_count: int,
        used_width: object,
        block_size: int,
        boxes: list[dict[str, object]],
        **kwargs: object,
    ) -> None:
        result = keep(name, **kwargs)
        checks.append(result.get("outcome") == "flowed")
        checks.append(result.get("column_count") == used_count)
        checks.append(result.get("column_width") == used_width)
        checks.append(result.get("column_gap") == kwargs.get("column_gap", 0))
        checks.append(result.get("block_size") == block_size)
        checks.append(result.get("boxes") == boxes)

    expect(
        "fixed_count",
        3,
        100,
        50,
        [
            _box("a", "none", 0, 0, 0, 0, 100, 30),
            _box("b", "none", 1, 0, 110, 0, 100, 40),
            _box("c", "none", 2, 0, 220, 0, 100, 50),
        ],
        available_inline=320,
        fragments=[
            {"id": "a", "height": 30},
            {"id": "b", "height": 40},
            {"id": "c", "height": 50},
        ],
        column_count=3,
        column_gap=10,
    )
    expect(
        "clamped_count",
        2,
        220,
        15,
        [_box("a", "none", 0, 0, 0, 0, 220, 15)],
        available_inline=450,
        fragments=[{"id": "a", "height": 15}],
        column_width=100,
        column_count=2,
        column_gap=10,
    )
    expect(
        "auto_count",
        4,
        105,
        0,
        [],
        available_inline=450,
        fragments=[],
        column_width=100,
        column_gap=10,
    )
    expect(
        "narrow_available",
        1,
        50,
        12,
        [_box("a", "none", 0, 0, 0, 0, 50, 12)],
        available_inline=50,
        fragments=[{"id": "a", "height": 12}],
        column_width=100,
        column_count=5,
        column_gap=10,
    )
    expect(
        "shortest_run",
        2,
        100,
        20,
        [
            _box("a", "none", 0, 0, 0, 0, 100, 10),
            _box("b", "none", 0, 0, 0, 10, 100, 10),
            _box("c", "none", 1, 0, 100, 0, 100, 10),
        ],
        available_inline=200,
        fragments=[
            {"id": "a", "height": 10},
            {"id": "b", "height": 10},
            {"id": "c", "height": 10},
        ],
        column_count=2,
    )
    expect(
        "sequential_fill",
        2,
        100,
        11,
        [
            _box("a", "none", 0, 0, 0, 0, 100, 10),
            _box("b", "none", 0, 0, 0, 10, 100, 1),
            _box("c", "none", 1, 0, 100, 0, 100, 10),
        ],
        available_inline=200,
        fragments=[
            {"id": "a", "height": 10},
            {"id": "b", "height": 1},
            {"id": "c", "height": 10},
        ],
        column_count=2,
    )
    expect(
        "spanner_split",
        2,
        100,
        105,
        [
            _box("a", "none", 0, 0, 0, 0, 100, 30),
            _box("b", "none", 0, 0, 0, 30, 100, 40),
            _box("c", "none", 1, 0, 110, 0, 100, 50),
            _box("s", "all", None, None, 0, 70, 210, 15),
            _box("d", "none", 0, 1, 0, 85, 100, 20),
            _box("e", "none", 1, 1, 110, 85, 100, 20),
        ],
        available_inline=210,
        fragments=[
            {"id": "a", "height": 30},
            {"id": "b", "height": 40},
            {"id": "c", "height": 50},
            {"id": "s", "height": 15, "span": "all"},
            {"id": "d", "height": 20},
            {"id": "e", "height": 20},
        ],
        column_count=2,
        column_gap=10,
    )
    stretched_width = (100 - 20) / 3
    expect(
        "stretched_width",
        3,
        stretched_width,
        9,
        [
            _box("a", "none", 0, 0, 0, 0, stretched_width, 9),
            _box("b", "none", 1, 0, (100 + 10) / 3, 0, stretched_width, 9),
        ],
        available_inline=100,
        fragments=[{"id": "a", "height": 9}, {"id": "b", "height": 9}],
        column_count=3,
        column_gap=10,
    )
    same = keep(
        "balance_all",
        available_inline=200,
        fragments=[
            {"id": "a", "height": 10},
            {"id": "b", "height": 1},
            {"id": "c", "height": 10},
        ],
        column_count=2,
        column_fill="balance-all",
    )
    sequential = observed["sequential_fill"]
    checks.append(
        isinstance(sequential, dict)
        and same.get("outcome") == "flowed"
        and same.get("boxes") == sequential.get("boxes")
        and same.get("block_size") == 11
        and same.get("column_count") == 2
    )

    not_multicol = keep("not_multicol", available_inline=200, fragments=[])
    checks.append(_invalid(not_multicol) and not_multicol.get("reason") == "not a multicol container")
    auto_fill = keep(
        "auto_fill",
        available_inline=200,
        fragments=[{"id": "a", "height": 10}],
        column_count=2,
        column_fill="auto",
    )
    checks.append(_invalid(auto_fill) and auto_fill.get("reason") == "column_fill")
    zero_size = keep(
        "zero_column_size",
        available_inline=80,
        fragments=[],
        column_width=0,
        column_gap=0,
    )
    checks.append(_invalid(zero_size) and zero_size.get("reason") == "column size")
    for name, kwargs in (
        ("negative_gap", {"available_inline": 80, "fragments": [], "column_count": 1, "column_gap": -1}),
        ("bool_width", {"available_inline": True, "fragments": [], "column_count": 1}),
        ("bad_span", {"available_inline": 80, "fragments": [{"id": "a", "height": 1, "span": "column"}], "column_count": 1}),
        ("duplicate", {"available_inline": 80, "fragments": [{"id": "a", "height": 1}, {"id": "a", "height": 2}], "column_count": 1}),
        ("negative_height", {"available_inline": 80, "fragments": [{"id": "a", "height": -1}], "column_count": 1}),
    ):
        checks.append(_invalid(keep(name, **kwargs)))

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
