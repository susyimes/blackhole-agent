"""Fragment a fixed-height CSS column row on forced and avoided breaks.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
correct row and a tree the baseline cannot fragment.
"""

from __future__ import annotations

import json


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_column_break import fragment_columns
    except Exception as exc:  # noqa: BLE001 - baseline without the reader still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}
    checks: list[bool] = []

    def keep(name: str, count: int, limit: int, fragments: list[dict[str, object]]) -> dict[str, object]:
        try:
            result = fragment_columns(count, limit, fragments)
        except Exception as exc:  # noqa: BLE001 - a raised row is an unmet outcome
            result = {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}"}
        observed[name] = result if isinstance(result, dict) else {"outcome": "error"}
        return observed[name]

    def expect(
        name: str,
        count: int,
        limit: int,
        fragments: list[dict[str, object]],
        boxes: list[dict[str, object]],
    ) -> None:
        result = keep(name, count, limit, fragments)
        found = result.get("boxes")
        checks.append(
            result.get("outcome") == "fragmented"
            and result.get("column_count") == count
            and result.get("column_block_size") == limit
            and found == boxes
        )

    def box(ident: str, column: int, block: int, height: int, overflow: bool) -> dict[str, object]:
        return {"id": ident, "column": column, "block": block, "height": height, "overflow": overflow}

    expect(
        "forced_split",
        2,
        100,
        [{"id": "a", "height": 40}, {"id": "b", "height": 40, "break_before": "column"}],
        [box("a", 0, 0, 40, False), box("b", 1, 0, 40, False)],
    )
    expect(
        "forced_first",
        2,
        100,
        [{"id": "a", "height": 40, "break_before": "column"}, {"id": "b", "height": 40}],
        [box("a", 0, 0, 40, False), box("b", 0, 40, 40, False)],
    )
    expect(
        "collapsed_force",
        3,
        100,
        [
            {"id": "a", "height": 30, "break_after": "column"},
            {"id": "b", "height": 30, "break_before": "always"},
            {"id": "c", "height": 30},
        ],
        [box("a", 0, 0, 30, False), box("b", 1, 0, 30, False), box("c", 1, 30, 30, False)],
    )
    for name, value in (("page", "page"), ("left", "left"), ("region", "region")):
        expect(
            f"physical_{name}",
            2,
            100,
            [{"id": "a", "height": 40}, {"id": "b", "height": 40, "break_before": value}],
            [box("a", 0, 0, 40, False), box("b", 0, 40, 40, False)],
        )
    expect(
        "avoid_pull",
        3,
        100,
        [
            {"id": "a", "height": 40},
            {"id": "b", "height": 40},
            {"id": "c", "height": 40, "break_before": "avoid-column"},
        ],
        [box("a", 0, 0, 40, False), box("b", 1, 0, 40, False), box("c", 1, 40, 40, False)],
    )
    expect(
        "avoid_after",
        3,
        100,
        [
            {"id": "a", "height": 40},
            {"id": "b", "height": 40, "break_after": "avoid"},
            {"id": "c", "height": 40},
        ],
        [box("a", 0, 0, 40, False), box("b", 1, 0, 40, False), box("c", 1, 40, 40, False)],
    )
    for name, value in (("avoid_page", "avoid-page"), ("avoid_region", "avoid-region")):
        expect(
            name,
            3,
            100,
            [
                {"id": "a", "height": 40},
                {"id": "b", "height": 40},
                {"id": "c", "height": 40, "break_before": value},
            ],
            [box("a", 0, 0, 40, False), box("b", 0, 40, 40, False), box("c", 1, 0, 40, False)],
        )
    expect(
        "avoid_too_tall",
        2,
        100,
        [{"id": "a", "height": 60}, {"id": "b", "height": 60, "break_before": "avoid"}],
        [box("a", 0, 0, 60, False), box("b", 1, 0, 60, False)],
    )
    expect(
        "force_beats_avoid",
        2,
        100,
        [
            {"id": "a", "height": 40, "break_after": "always"},
            {"id": "b", "height": 40, "break_before": "avoid"},
        ],
        [box("a", 0, 0, 40, False), box("b", 1, 0, 40, False)],
    )
    expect(
        "tall_box",
        2,
        100,
        [{"id": "a", "height": 150}, {"id": "b", "height": 30}],
        [box("a", 0, 0, 150, True), box("b", 1, 0, 30, False)],
    )
    expect(
        "last_column",
        1,
        100,
        [{"id": "a", "height": 60}, {"id": "b", "height": 60, "break_before": "column"}],
        [box("a", 0, 0, 60, False), box("b", 0, 60, 60, True)],
    )
    expect(
        "zero_occupies",
        2,
        100,
        [{"id": "a", "height": 0}, {"id": "b", "height": 10, "break_before": "column"}],
        [box("a", 0, 0, 0, False), box("b", 1, 0, 10, False)],
    )
    expect(
        "avoid_chain",
        2,
        100,
        [
            {"id": "a", "height": 50},
            {"id": "b", "height": 20, "break_after": "avoid"},
            {"id": "c", "height": 20, "break_before": "avoid"},
            {"id": "d", "height": 50, "break_before": "avoid"},
        ],
        [
            box("a", 0, 0, 50, False),
            box("b", 1, 0, 20, False),
            box("c", 1, 20, 20, False),
            box("d", 1, 40, 50, False),
        ],
    )
    expect(
        "avoid_partial",
        2,
        100,
        [
            {"id": "a", "height": 30, "break_after": "avoid"},
            {"id": "b", "height": 30, "break_after": "avoid"},
            {"id": "c", "height": 30, "break_after": "avoid"},
            {"id": "d", "height": 50},
        ],
        [
            box("a", 0, 0, 30, False),
            box("b", 0, 30, 30, False),
            box("c", 1, 0, 30, False),
            box("d", 1, 30, 50, False),
        ],
    )
    expect(
        "avoid_fits",
        2,
        100,
        [
            {"id": "a", "height": 40},
            {"id": "b", "height": 40},
            {"id": "c", "height": 20, "break_before": "avoid"},
        ],
        [box("a", 0, 0, 40, False), box("b", 0, 40, 40, False), box("c", 0, 80, 20, False)],
    )
    expect(
        "exact_fit",
        1,
        100,
        [{"id": "a", "height": 100}],
        [box("a", 0, 0, 100, False)],
    )
    expect(
        "all_forces",
        2,
        100,
        [{"id": "a", "height": 40}, {"id": "b", "height": 40, "break_before": "all"}],
        [box("a", 0, 0, 40, False), box("b", 1, 0, 40, False)],
    )
    expect(
        "inside_unbroken",
        2,
        100,
        [
            {"id": "a", "height": 40},
            {"id": "b", "height": 40, "break_inside": "avoid"},
            {"id": "c", "height": 40},
        ],
        [box("a", 0, 0, 40, False), box("b", 0, 40, 40, False), box("c", 1, 0, 40, False)],
    )
    expect(
        "trailing_force",
        2,
        100,
        [{"id": "a", "height": 40, "break_after": "column"}],
        [box("a", 0, 0, 40, False)],
    )
    duplicate = keep("duplicate", 1, 100, [{"id": "a", "height": 1}, {"id": "a", "height": 1}])
    unknown = keep("unknown", 1, 100, [{"id": "a", "height": 1, "break_before": "page-break"}])
    checks.append(
        duplicate.get("outcome") == "invalid"
        and duplicate.get("reason") == "duplicate id"
        and duplicate.get("boxes") is None
    )
    checks.append(
        unknown.get("outcome") == "invalid"
        and unknown.get("reason") == "break_before"
        and unknown.get("boxes") is None
    )
    return all(checks), observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"observed": observed, "passed": passed}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
