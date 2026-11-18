"""Break a definite flex container into lines before resolving free space.

A nowrap line shrinks neighbors together. wrap leaves a 90px item at 90
beside an empty remainder and puts the next 20px item on the following line.
A minimum wraps early, a maximum wraps late, and a negative margin can keep
an otherwise overflowing item on the line. order regroups items.
wrap-reverse reverses lines only. row-reverse moves the main start.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree without the line breaker still exits 0.
"""

from __future__ import annotations

import json


def _close(got: object, expected: float) -> bool:
    if isinstance(got, bool) or not isinstance(got, (int, float)):
        return False
    return abs(float(got) - expected) <= 1e-6


def _item(ident: str, base: float, **extra: object) -> dict[str, object]:
    row: dict[str, object] = {"id": ident, "base": base}
    row.update(extra)
    return row


def _matches(result: object, ids: list[list[str]], sizes: list[list[float]]) -> bool:
    if not isinstance(result, dict) or result.get("outcome") != "wrapped":
        return False
    lines = result.get("lines")
    if not isinstance(lines, list) or len(lines) != len(ids):
        return False
    for line, want_ids, want_sizes in zip(lines, ids, sizes):
        if not isinstance(line, dict) or line.get("ids") != want_ids:
            return False
        got = line.get("main_sizes")
        if not isinstance(got, list) or len(got) != len(want_sizes):
            return False
        if any(not _close(item, want) for item, want in zip(got, want_sizes)):
            return False
    return True


def _invalid(result: object) -> bool:
    return isinstance(result, dict) and result.get("outcome") == "invalid" and result.get("lines") is None


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_flex_wrap import wrap_flex_lines
    except Exception as exc:  # noqa: BLE001 - baseline without the breaker still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}
    checks: list[bool] = []

    def keep(name: str, container: object, items: object, **kwargs: object) -> dict[str, object]:
        try:
            result = wrap_flex_lines(container, items, **kwargs)  # type: ignore[arg-type]
        except Exception as exc:  # noqa: BLE001 - a raised call is an unmet outcome
            result = {"outcome": "error", "error": f"{type(exc).__name__}: {exc}"}
        observed[name] = result
        return result if isinstance(result, dict) else {"outcome": "error"}

    wide = [_item("a", 60), _item("b", 60), _item("c", 60)]
    nowrap = keep("nowrap_shrinks_together", 100, wide)
    checks.append(_matches(nowrap, [["a", "b", "c"]], [[100 / 3, 100 / 3, 100 / 3]]))
    checks.append(nowrap.get("main_start") == "start")

    wrapped = keep("wrap_keeps_hypothetical", 100, wide, wrap="wrap")
    checks.append(_matches(wrapped, [["a"], ["b"], ["c"]], [[60], [60], [60]]))

    pair = [_item("a", 90), _item("b", 20)]
    leftover = keep("wrap_does_not_pull_back", 100, pair, wrap="wrap")
    checks.append(_matches(leftover, [["a"], ["b"]], [[90], [20]]))
    shrunk = keep("nowrap_shrinks_the_same_pair", 100, pair)
    checks.append(_matches(shrunk, [["a", "b"]], [[900 / 11, 200 / 11]]))

    raised = keep(
        "minimum_wraps_early",
        100,
        [_item("a", 10, minimum=80), _item("b", 30)],
        wrap="wrap",
    )
    checks.append(_matches(raised, [["a"], ["b"]], [[80], [30]]))

    lowered = keep(
        "maximum_wraps_late",
        100,
        [_item("a", 90, maximum=40), _item("b", 50)],
        wrap="wrap",
    )
    checks.append(_matches(lowered, [["a", "b"]], [[40, 50]]))

    checks.append(
        _matches(
            keep("minimum_beats_maximum", 60, [_item("a", 10, minimum=50, maximum=20), _item("b", 20)], wrap="wrap"),
            [["a"], ["b"]],
            [[50], [20]],
        )
    )

    gap_fit = keep("gap_fits_exactly", 100, [_item("a", 40), _item("b", 40)], wrap="wrap", gap=20)
    checks.append(_matches(gap_fit, [["a", "b"]], [[40, 40]]))
    gap_next = keep(
        "gap_exact_then_next_line",
        100,
        [_item("a", 40), _item("b", 40), _item("c", 1)],
        wrap="wrap",
        gap=20,
    )
    checks.append(_matches(gap_next, [["a", "b"], ["c"]], [[40, 40], [1]]))
    gap_split = keep("gap_forces_split", 100, [_item("a", 40), _item("b", 40)], wrap="wrap", gap=30)
    checks.append(_matches(gap_split, [["a"], ["b"]], [[40], [40]]))

    pulled = keep(
        "negative_margin_stays",
        100,
        [_item("a", 120), _item("b", 10, margin=-40)],
        wrap="wrap",
    )
    checks.append(_matches(pulled, [["a", "b"]], [[120, 10]]))
    alone = keep("wide_item_shrinks_alone", 100, [_item("a", 150), _item("b", 10)], wrap="wrap")
    checks.append(_matches(alone, [["a"], ["b"]], [[100], [10]]))

    ordered = keep(
        "order_regroups",
        100,
        [_item("a", 30, order=2), _item("b", 80, order=0), _item("c", 30, order=1)],
        wrap="wrap",
    )
    checks.append(_matches(ordered, [["b"], ["c", "a"]], [[80], [30, 30]]))
    negative = keep(
        "negative_order_sorts_first",
        100,
        [_item("a", 60, order=0), _item("z", 60, order=-1)],
        wrap="wrap",
    )
    checks.append(_matches(negative, [["z"], ["a"]], [[60], [60]]))

    reversed_lines = keep("wrap_reverse_stacks_from_cross_end", 100, wide, wrap="wrap-reverse")
    checks.append(_matches(reversed_lines, [["c"], ["b"], ["a"]], [[60], [60], [60]]))
    preserved = keep(
        "wrap_reverse_keeps_item_order",
        100,
        [_item("a", 30), _item("b", 30), _item("c", 50)],
        wrap="wrap-reverse",
    )
    checks.append(_matches(preserved, [["c"], ["a", "b"]], [[50], [30, 30]]))

    row_reverse = keep("row_reverse_same_groups", 100, wide, wrap="wrap", direction="row-reverse")
    checks.append(row_reverse.get("main_start") == "end")
    checks.append(_matches(row_reverse, [["a"], ["b"], ["c"]], [[60], [60], [60]]))
    column_reverse = keep("column_reverse_same_groups", 100, wide, wrap="wrap", direction="column-reverse")
    checks.append(column_reverse.get("main_start") == "end")
    checks.append(_matches(column_reverse, [["a"], ["b"], ["c"]], [[60], [60], [60]]))
    column_reverse_wrap = keep(
        "column_wrap_reverse_keeps_main_start",
        100,
        wide,
        wrap="wrap-reverse",
        direction="column",
    )
    checks.append(column_reverse_wrap.get("main_start") == "start")
    checks.append(_matches(column_reverse_wrap, [["c"], ["b"], ["a"]], [[60], [60], [60]]))

    scaled = keep("scaled_grow_on_its_line", 100, [_item("a", 40, grow=0.5)], wrap="wrap")
    checks.append(_matches(scaled, [["a"]], [[70]]))

    empty = keep("empty", 100, [], wrap="wrap-reverse")
    checks.append(empty.get("outcome") == "wrapped" and empty.get("lines") == [])

    checks.append(_invalid(keep("negative_container", -1, wide, wrap="wrap")))
    checks.append(_invalid(keep("boolean_gap", 100, wide, wrap="wrap", gap=True)))
    checks.append(_invalid(keep("unknown_wrap", 100, wide, wrap="reverse")))
    checks.append(_invalid(keep("unknown_direction", 100, wide, wrap="wrap", direction="rtl")))
    checks.append(_invalid(keep("boolean_order", 100, [_item("a", 10, order=True)], wrap="wrap")))
    checks.append(_invalid(keep("duplicate_id", 100, [_item("a", 10), _item("a", 20)], wrap="wrap")))

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
